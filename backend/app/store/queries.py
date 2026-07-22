from app.store.client import ExportFormat, sparql_construct, sparql_select, curation_graph
from rdflib import Graph, URIRef

from app.pipeline.utils.turtle_utils import (
    load_entity_information,
    sparql_binding_to_term,
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
            f"<{create_source_document_entity(workspace_id, doc_id).value}>"
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
    graph: str, document_entity: str, format: ExportFormat = ExportFormat.turtle
) -> str:
    """Return the accepted (subject, predicate, object) triples derived from one
    document, serialized in the given format, reconstructed from the curation
    graph since the data graph itself carries no document linkage."""
    return sparql_construct(
        f"""
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
        """,
        format,
    )


def export_document_provenance(
    graph: str, document_entity: str, format: ExportFormat = ExportFormat.turtle
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

    return sparql_construct(
        f"""
        CONSTRUCT {{ ?s ?p ?o }}
        WHERE {{
            GRAPH <{graph}> {{
                VALUES ?s {{ {values} }}
                ?s ?p ?o .
            }}
        }}
        """,
        format,
    )
