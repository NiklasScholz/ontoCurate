from app.store.client import sparql_construct_ttl, sparql_select
from app.store.utils import *


def get_statements() -> dict:
    pass


def get_entity_list() -> dict:
    pass


def get_entity_statements() -> list[dict]:
    pass


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


def export_document_data_ttl(graph: str, document_entity: str) -> str:
    """Return the accepted (subject, predicate, object) triples derived from one
    document as a Turtle string, reconstructed from the curation graph since the
    data graph itself carries no document linkage."""
    return sparql_construct_ttl(f"""
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


def export_document_provenance_ttl(graph: str, document_entity: str) -> str:
    """Return the full provenance history for one document as a Turtle string:
    every CandidateStatement version derived from it, the activities that
    generated those versions, and the agents associated with those activities."""
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

    return sparql_construct_ttl(f"""
        CONSTRUCT {{ ?s ?p ?o }}
        WHERE {{
            GRAPH <{graph}> {{
                VALUES ?s {{ {values} }}
                ?s ?p ?o .
            }}
        }}
        """)
