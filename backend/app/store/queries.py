from rdflib import Graph, URIRef

from app.pipeline.utils.turtle_utils import (
    load_entity_information,
    sparql_binding_to_term,
)
from app.store.client import curation_graph, sparql_select
from app.store.utils import (
    OWL_SAME_AS,
    PACO_CANDIDATE,
    PACO_CURRENT,
    PACO_OBJECT,
    PACO_PREDICATE,
    PACO_REJECTED,
    PACO_SOURCE_DOCUMENT,
    PACO_STATUS,
    PACO_SUBJECT,
    PROV_DERIVED_FROM,
    create_source_document_entity,
)


def get_prior_entities(
    workspace_id: str, exclude_document_ids: list[str]
) -> list[dict]:
    """Gets entities from all current-version, non-rejected CandidateStatements
    in {workspaceid} provenance graph
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
