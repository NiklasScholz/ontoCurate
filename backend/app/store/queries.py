import re

from rdflib import Graph, URIRef

from app.pipeline.utils.turtle_utils import (
    load_entity_information,
    sparql_binding_to_term,
)
from app.schemas.statement import TextSpan
from app.store.client import (
    ExportFormat,
    curation_graph,
    data_graph,
    serialize_export,
    sparql_construct,
    sparql_select,
)
from app.store.utils import *


def get_prior_entities(
    workspace_id: str, exclude_document_ids: list[str]
) -> list[dict]:
    """Gets entities from all current-version, non-rejected CandidateStatements in {workspaceid} provenance graph.
    Additionally excludes {exclude_document_ids} from the results, so that a new run's entities are not compared against themselves.
    Used to perform cross-document cross-run entity alignment.
    """
    graph = curation_graph(workspace_id)

    exclude_filter = ""
    if exclude_document_ids:
        excluded_uris = ", ".join(
            f"<{create_source_document_entity(doc_id).value}>"
            for doc_id in exclude_document_ids
        )
        exclude_filter = f"FILTER (!BOUND(?doc) || ?doc NOT IN ({excluded_uris}))"

    query = f"""
        SELECT ?s ?p ?o ?doc WHERE {{
            GRAPH <{graph}> {{
                ?cs a <{PACO_CANDIDATE}> ;
                    <{PACO_CURRENT}> true ;
                    <{PACO_STATUS}> ?status ;
                    <{PACO_SUBJECT}> ?s ;
                    <{PACO_PREDICATE}> ?p ;
                    <{PACO_OBJECT}> ?o .
                FILTER (?p != <{OWL_SAME_AS}>)
                FILTER (?status != <{PACO_REJECTED}>)
                OPTIONAL {{ ?cs <{PROV_DERIVED_FROM}> ?doc . ?doc a <{PACO_SOURCE_DOCUMENT}> . }}
                {exclude_filter}
            }}
        }}
    """

    payload = sparql_select(query)
    bindings = payload.get("results", {}).get("bindings", [])

    g = Graph()
    subject_doc_map: dict[str, str] = {}
    for b in bindings:
        subject_term = URIRef(b["s"]["value"])
        predicate_term = URIRef(b["p"]["value"])
        object_term = sparql_binding_to_term(b["o"])
        g.add((subject_term, predicate_term, object_term))

        if "doc" in b:
            doc_uri = b["doc"]["value"]
            subject_doc_map[b["s"]["value"]] = doc_uri.rsplit("/", 1)[-1]

    entities = load_entity_information(g)
    for entity in entities:
        entity["source_document"] = subject_doc_map.get(entity["uri"])
        entity["is_prior"] = True

    return entities


def get_existing_alignment_pairs(workspace_id: str) -> set[frozenset[str]]:
    """Returns already aligned pairs of entities in provenance graph to ensure no duplicate comparison"""
    graph = curation_graph(workspace_id)

    query = f"""
        SELECT ?duplicateSubject ?duplicateTarget WHERE {{
            GRAPH <{graph}> {{
                ?cs a <{PACO_CANDIDATE}> ;
                    <{PACO_CURRENT}> true ;
                    <{PACO_PREDICATE}> <{OWL_SAME_AS}> ;
                    <{PACO_SUBJECT}> ?duplicateSubject ;
                    <{PACO_OBJECT}> ?duplicateTarget .
            }}
        }}
    """

    payload = sparql_select(query)
    bindings = payload.get("results", {}).get("bindings", [])

    return {
        frozenset({b["duplicateSubject"]["value"], b["duplicateTarget"]["value"]})
        for b in bindings
    }


def get_accepted_alignment_pairs(workspace_id: str) -> set[tuple[str, str]]:
    """
    Returns accepted owl:sameAs candidatestatments produced by the alignment stage.
    """
    graph = curation_graph(workspace_id)
    query = f"""
        SELECT DISTINCT ?s ?o WHERE {{
            GRAPH <{graph}> {{
                ?cs a <{PACO_CANDIDATE}> ;
                    <{PACO_CURRENT}> true ;
                    <{PACO_STATUS}> <{PACO_ACCEPTED}> ;
                    <{PACO_PREDICATE}> <{OWL_SAME_AS}> ;
                    <{PACO_SUBJECT}> ?s ;
                    <{PACO_OBJECT}> ?o ;
                    <{PROV_DERIVED_FROM}>* ?original .
                ?original <{PROV_GENERATED_BY}> ?activity .
                ?activity a <{PACO_ALIGNMENT_ACTIVITY}> .
            }}
        }}
    """
    payload = sparql_select(query)
    bindings = payload.get("results", {}).get("bindings", [])
    return {(b["s"]["value"], b["o"]["value"]) for b in bindings}


def hash_stripping_rewrite(entity_uris: set[str]) -> dict[str, str]:
    """
    Maps each fallback-hashed entity URI to its hash-free form ensuring no conflicts
    """
    stripped_groups = {}
    for uri in entity_uris:
        match = re.compile(r"^(.*)_[0-9a-f]{6}$").match(uri)
        stripped_groups.setdefault(match.group(1) if match else uri, []).append(uri)

    return {
        uris[0]: stripped
        for stripped, uris in stripped_groups.items()
        if len(uris) == 1 and uris[0] != stripped
    }


def export_deduplicated_graph(
    workspace_id: str,
    format: ExportFormat = ExportFormat.turtle,
    prefixes: dict[str, str] = BASE_PREFIXES,
) -> str:
    """
    Export the data graph with accepted aligned entities merged into a single URI without hashes.
    """
    ttl = sparql_construct(f"""
        CONSTRUCT {{ ?s ?p ?o }}
        WHERE {{ GRAPH <{data_graph(workspace_id)}> {{ ?s ?p ?o }} }}
        """)
    data = Graph()
    data.parse(data=ttl, format="turtle")

    # Union-find over accepted sameAs pairs to merge connected components into a single URI
    parent = {}

    def find(x: str) -> str:
        while parent.get(x, x) != x:
            x = parent[x]
        return x

    # traverse lookup graph
    for a, b in get_accepted_alignment_pairs(workspace_id):
        root_a, root_b = find(a), find(b)
        if root_a != root_b:
            parent[root_b] = root_a

    canonical = {member: find(member) for member in parent}

    def rewrite_aligned(term):
        if isinstance(term, URIRef) and str(term) in canonical:
            return URIRef(canonical[str(term)])
        return term

    aligned = Graph()
    for s, p, o in data:
        new_s, new_o = rewrite_aligned(s), rewrite_aligned(o)
        if new_s == new_o and s != o:
            # skip self-loops created through merge
            continue
        aligned.add((new_s, p, new_o))

    entity_uris = {
        str(term) for s, _, o in aligned for term in (s, o) if isinstance(term, URIRef)
    }
    # strip hashes from URIs without conflicts
    hash_rewrite = hash_stripping_rewrite(entity_uris)

    def rewrite_hash(term):
        if isinstance(term, URIRef) and str(term) in hash_rewrite:
            return URIRef(hash_rewrite[str(term)])
        return term

    merged = Graph()
    for s, p, o in aligned:
        merged.add((rewrite_hash(s), p, rewrite_hash(o)))
    return serialize_export(merged.serialize(format="turtle"), format, prefixes)


def get_related_spans(
    workspace_id: str,
    document_id: str,
    subject: str,
    object: str | None,
) -> tuple[list[TextSpan], list[TextSpan]]:
    """Returns the text spans of every current, literal-valued CandidateStatement
    in {document_id} whose subject is {subject} or {object}, split into two lists.
    We use this to display relevant info to the curator when looking at triples.
    """
    graph = curation_graph(workspace_id)
    document_entity = create_source_document_entity(document_id).value

    def spans_for(entity: str) -> list[TextSpan]:
        payload = sparql_select(f"""
            SELECT ?start ?end WHERE {{
                GRAPH <{graph}> {{
                    ?cs <{RDF_TYPE}> <{PACO_CANDIDATE}> .
                    ?cs <{PACO_CURRENT}> true .
                    ?cs <{PACO_SUBJECT}> <{entity}> .
                    ?cs <{PACO_TEXT_SPAN_START}> ?start .
                    ?cs <{PACO_TEXT_SPAN_END}> ?end .
                    ?cs <{PROV_DERIVED_FROM}>* ?os .
                    ?os <{PROV_GENERATED_BY}> ?e .
                    ?e <{RDF_TYPE}> <{PACO_EXTRACTION_ACTIVITY}> .
                    ?e <{PROV_USED}> <{document_entity}> .
                }}
            }}
        """)
        bindings = payload.get("results", {}).get("bindings", [])
        return [
            TextSpan(start=int(b["start"]["value"]), end=int(b["end"]["value"]))
            for b in bindings
        ]

    return spans_for(subject), (spans_for(object) if object is not None else [])


def get_document_statement_rows(
    workspace_id: str, document_id: str
) -> tuple[list[tuple[str, str, str, str, str]], list[tuple[str, str, str, str, str]]]:
    """Returns (current_rows, original_rows) for every CandidateStatement derived
    from {document_id} as (subject, predicate, object, original, object_type) tuples."""
    graph = curation_graph(workspace_id)
    document_entity = create_source_document_entity(document_id).value

    payload = sparql_select(f"""
        SELECT ?s ?p ?o ?os WHERE {{
            GRAPH <{graph}> {{
                ?s ?p ?o .
                ?s <{RDF_TYPE}> <{PACO_CANDIDATE}> .
                ?s <{PACO_CURRENT}> true .
                ?s <{PROV_DERIVED_FROM}>* ?os .
                ?os <{PROV_GENERATED_BY}> ?e .
                ?e <{RDF_TYPE}> <{PACO_EXTRACTION_ACTIVITY}> .
                ?e <{PROV_USED}> <{document_entity}> .
            }}
        }}
        ORDER BY ?s ?p ?o
        """)
    rows = [
        (
            b["s"]["value"],
            b["p"]["value"],
            b["o"]["value"],
            b["os"]["value"],
            b["o"]["type"],
        )
        for b in payload.get("results", {}).get("bindings", [])
    ]

    originals_payload = sparql_select(f"""
        SELECT ?s ?p ?o WHERE {{
            GRAPH <{graph}> {{
                ?s ?p ?o .
                ?s <{RDF_TYPE}> <{PACO_CANDIDATE}> .
                ?s <{PROV_GENERATED_BY}> ?e .
                ?e <{RDF_TYPE}> <{PACO_EXTRACTION_ACTIVITY}> .
                ?e <{PROV_USED}> <{document_entity}> .
            }}
        }}
        ORDER BY ?s ?p ?o
        """)
    originals_rows = [
        (
            b["s"]["value"],
            b["p"]["value"],
            b["o"]["value"],
            b["s"]["value"],
            b["o"]["type"],
        )
        for b in originals_payload.get("results", {}).get("bindings", [])
    ]

    return rows, originals_rows


def get_deduplication_statement_rows(
    workspace_id: str,
) -> tuple[list[tuple[str, str, str, str, str]], list[tuple[str, str, str, str, str]]]:
    """Returns (current_rows, original_rows) for every owl:sameAs CandidateStatement
    produced by alignment/lookups as (subject, predicate, object, original, object_type)
    tuples (like above).
    """
    graph = curation_graph(workspace_id)

    activity_values = f"""
        VALUES ?activity_type {{
            <{PACO_ALIGNMENT_ACTIVITY}>
            <{PACO_LOOKUP_ACTIVITY}>
        }}
    """

    payload = sparql_select(f"""
        SELECT ?s ?p ?o ?os WHERE {{
            GRAPH <{graph}> {{
                ?s ?p ?o .
                ?s <{RDF_TYPE}> <{PACO_CANDIDATE}> .
                ?s <{PACO_CURRENT}> true .
                ?s <{PROV_DERIVED_FROM}>* ?os .
                ?os <{PROV_GENERATED_BY}> ?e .
                {activity_values}
                ?e <{RDF_TYPE}> ?activity_type .
            }}
        }}
        ORDER BY ?s ?p ?o
        """)
    rows = [
        (
            b["s"]["value"],
            b["p"]["value"],
            b["o"]["value"],
            b["os"]["value"],
            b["o"]["type"],
        )
        for b in payload.get("results", {}).get("bindings", [])
    ]

    originals_payload = sparql_select(f"""
        SELECT ?s ?p ?o WHERE {{
            GRAPH <{graph}> {{
                ?s ?p ?o .
                ?s <{RDF_TYPE}> <{PACO_CANDIDATE}> .
                ?s <{PROV_GENERATED_BY}> ?e .
                {activity_values}
                ?e <{RDF_TYPE}> ?activity_type .
            }}
        }}
        ORDER BY ?s ?p ?o
        """)
    originals_rows = [
        (
            b["s"]["value"],
            b["p"]["value"],
            b["o"]["value"],
            b["s"]["value"],
            b["o"]["type"],
        )
        for b in originals_payload.get("results", {}).get("bindings", [])
    ]

    return rows, originals_rows


def get_deduplication_counts(workspace_id: str) -> tuple[int, int]:
    """Returns (total_count, pending_count) of owl:sameAs CandidateStatements
    produced by alignment/lookup."""
    graph = curation_graph(workspace_id)
    payload = sparql_select(f"""
        SELECT (COUNT(*) AS ?total) (SUM(?is_pending) AS ?pending) WHERE {{
            SELECT DISTINCT ?s (IF(?status = <{PACO_PENDING}>, 1, 0) AS ?is_pending) WHERE {{
                GRAPH <{graph}> {{
                    ?s <{RDF_TYPE}> <{PACO_CANDIDATE}> .
                    ?s <{PACO_CURRENT}> true .
                    ?s <{PACO_STATUS}> ?status .
                    ?s <{PROV_DERIVED_FROM}>* ?os .
                    ?os <{PROV_GENERATED_BY}> ?e .
                    VALUES ?activity_type {{
                        <{PACO_ALIGNMENT_ACTIVITY}>
                        <{PACO_LOOKUP_ACTIVITY}>
                    }}
                    ?e <{RDF_TYPE}> ?activity_type .
                }}
            }}
        }}
        """)
    bindings = payload.get("results", {}).get("bindings", [])
    if not bindings:
        return 0, 0
    return int(bindings[0]["total"]["value"]), int(bindings[0]["pending"]["value"])


def get_entity_neighborhood(
    workspace_id: str, entity_id: str
) -> tuple[list[tuple[str, str, str]], list[tuple[str, str, str]]]:
    """Returns (incoming, outgoing) edges for {entity_id}'s local neighborhood,
    as (predicate, other_entity, status) tuples."""
    graph = curation_graph(workspace_id)

    incoming_payload = sparql_select(f"""
        SELECT ?s ?p ?status WHERE {{
            GRAPH <{graph}> {{
                ?r <{PACO_SUBJECT}> ?s .
                ?r <{PACO_PREDICATE}> ?p .
                ?r <{PACO_OBJECT}> <{entity_id}> .
                ?r <{RDF_TYPE}> <{PACO_CANDIDATE}> .
                ?r <{PACO_CURRENT}> true .
                ?r <{PACO_STATUS}> ?status .
            }}
        }}
        ORDER BY ?p ?s
        """)
    incoming = [
        (b["p"]["value"], b["s"]["value"], b["status"]["value"])
        for b in incoming_payload.get("results", {}).get("bindings", [])
    ]

    outgoing_payload = sparql_select(f"""
        SELECT ?p ?o ?status WHERE {{
            GRAPH <{graph}> {{
                ?r <{PACO_SUBJECT}> <{entity_id}> .
                ?r <{PACO_PREDICATE}> ?p .
                ?r <{PACO_OBJECT}> ?o .
                ?r <{RDF_TYPE}> <{PACO_CANDIDATE}> .
                ?r <{PACO_CURRENT}> true .
                ?r <{PACO_STATUS}> ?status .
            }}
        }}
        ORDER BY ?p ?o
        """)
    outgoing = [
        (b["p"]["value"], b["o"]["value"], b["status"]["value"])
        for b in outgoing_payload.get("results", {}).get("bindings", [])
    ]

    return incoming, outgoing


def get_triple_counts_bulk(
    document_ids: list[str], workspace_id: str
) -> dict[str, tuple[int, int]]:
    """Returns {document_id: (extracted_count, pending_count)} for every document
    in {document_ids}."""
    if not document_ids:
        return {}

    graph = curation_graph(workspace_id)
    document_entities = {
        document_id: create_source_document_entity(document_id).value
        for document_id in document_ids
    }
    values_clause = " ".join(f"<{iri}>" for iri in document_entities.values())

    payload = sparql_select(f"""
        SELECT ?doc (COUNT(?s) AS ?extracted) (SUM(?is_pending) AS ?pending) WHERE {{
            GRAPH <{graph}> {{
                VALUES ?doc {{ {values_clause} }}
                ?s <{RDF_TYPE}> <{PACO_CANDIDATE}> .
                ?s <{PACO_CURRENT}> true .
                ?s <{PACO_STATUS}> ?status .
                BIND(IF(?status = <{PACO_PENDING}>, 1, 0) AS ?is_pending)
                ?s <{PROV_DERIVED_FROM}>* ?os .
                ?os <{PROV_GENERATED_BY}> ?e .
                ?e <{RDF_TYPE}> <{PACO_EXTRACTION_ACTIVITY}> .
                ?e <{PROV_USED}> ?doc .
            }}
        }}
        GROUP BY ?doc
        """)

    counts_by_doc_entity = {
        b["doc"]["value"]: (
            int(b["extracted"]["value"]),
            int(b["pending"]["value"]),
        )
        for b in payload.get("results", {}).get("bindings", [])
    }

    return {
        document_id: counts_by_doc_entity.get(iri, (0, 0))
        for document_id, iri in document_entities.items()
    }


def get_current_candidate_statement(
    stmt_id: str,
    graph: str,
) -> str:
    payload = sparql_select(f"""
        SELECT DISTINCT ?currentStatement
        WHERE {{
            GRAPH <{graph}> {{
                <{stmt_id}>
                    (^<{PROV_DERIVED_FROM}>)* 
                    ?currentStatement .

                ?currentStatement
                    <{RDF_TYPE}>
                    <{PACO_CANDIDATE}> .

                ?currentStatement
                    <{PACO_CURRENT}>
                    true .
            }}
        }}
        """)

    bindings = payload.get("results", {}).get("bindings", [])

    if not bindings:
        raise ValueError(f"No current CandidateStatement found for statement {stmt_id}")

    if len(bindings) > 1:
        raise ValueError(
            f"Multiple current CandidateStatements found for statement {stmt_id}"
        )

    return bindings[0]["currentStatement"]["value"]


def export_document_data(
    graph: str,
    document_entity: str,
    format: ExportFormat = ExportFormat.turtle,
    prefixes: dict[str, str] = BASE_PREFIXES,
) -> str:
    """Return the accepted (subject, predicate, object) triples derived from one
    document, serialized in the given format with URIs abbreviated per
    `prefixes`, reconstructed from the curation graph since the data graph
    itself carries no document linkage."""
    ttl = sparql_construct(f"""
        CONSTRUCT {{ ?subject ?predicate ?object }}
        WHERE {{
            GRAPH <{graph}> {{
                ?candidate
                    <{RDF_TYPE}> <{PACO_CANDIDATE}> ;
                    <{PACO_CURRENT}> true ;
                    <{PACO_STATUS}> <{PACO_ACCEPTED}> ;
                    <{PACO_SUBJECT}> ?subject ;
                    <{PACO_PREDICATE}> ?predicate ;
                    <{PACO_OBJECT}> ?object ;
                    <{PROV_DERIVED_FROM}>* ?original .

                ?original <{PROV_DERIVED_FROM}> <{document_entity}> .
            }}
        }}
        """)
    return serialize_export(ttl, format, prefixes)


def export_document_provenance(
    graph: str,
    document_entity: str,
    format: ExportFormat = ExportFormat.turtle,
    prefixes: dict[str, str] = BASE_PREFIXES,
) -> str:
    """Return the full provenance history for one document, serialized in the
    given format: every CandidateStatement version derived from it, the
    activities that generated those versions, and the agents associated with
    those activities."""
    payload = sparql_select(f"""
        SELECT DISTINCT ?candidate ?activity ?agent
        WHERE {{
            GRAPH <{graph}> {{
                <{document_entity}> (^<{PROV_DERIVED_FROM}>)* ?candidate .
                ?candidate <{RDF_TYPE}> <{PACO_CANDIDATE}> .

                OPTIONAL {{
                    ?candidate <{PROV_GENERATED_BY}> ?activity .
                    OPTIONAL {{ ?activity <{PROV_ASSOCIATED_WITH}> ?agent }}
                }}
            }}
        }}
        """)

    bindings = payload.get("results", {}).get("bindings", [])

    subjects = {document_entity}
    for binding in bindings:
        for key in ("candidate", "activity", "agent"):
            if key in binding:
                subjects.add(binding[key]["value"])

    values = " ".join(f"<{iri}>" for iri in subjects)

    ttl = sparql_construct(f"""
        CONSTRUCT {{ ?s ?p ?o }}
        WHERE {{
            GRAPH <{graph}> {{
                VALUES ?s {{ {values} }}
                ?s ?p ?o .
            }}
        }}
        """)
    return serialize_export(ttl, format, prefixes)
