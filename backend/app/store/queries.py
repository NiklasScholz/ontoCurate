from app.store.client import sparql_select
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
