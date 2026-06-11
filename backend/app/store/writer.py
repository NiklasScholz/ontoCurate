from datetime import datetime, timezone
from uuid import uuid4

from pyoxigraph import Literal, NamedNode, RdfFormat, Triple, serialize

from app.store.client import curation_graph, sparql_select, sparql_update

PACO = "https://example.org/provenance-and-curation-ontology/"
PROV = "http://www.w3.org/ns/prov#"


PACO_SUBJECT = f"{PACO}subject"
PACO_PREDICATE = f"{PACO}predicate"
PACO_OBJECT = f"{PACO}object"
PACO_STATUS = f"{PACO}curationStatus"
PACO_CREATED_AT = f"{PACO}createdAt"
PACO_CURRENT = f"{PACO}isCurrentVersion"
PACO_CONFIDENCE = f"{PACO}confidence"
PACO_CURATOR = f"{PACO}Curator"

PROV_GENERATED_BY = f"{PROV}wasGeneratedBy"
PROV_DERIVED_FROM = f"{PROV}wasDerivedFrom"
RDF = "http://www.w3.org/1999/02/22-rdf-syntax-ns#"
XSD = "http://www.w3.org/2001/XMLSchema#"
XSD_DATETIME = f"{XSD}dateTime"

RDF_TYPE = f"{RDF}type"

PACO_CANDIDATE = f"{PACO}CandidateStatement"
PACO_ACCEPTING_ACTIVITY = f"{PACO}AcceptingActivity"
PACO_ACCEPTED = f"{PACO}accepted"
PACO_ACCEPTED_AT = f"{PACO}acceptedAt"
PACO_ORIGIN = f"{PACO}origin"

PROV_ACTIVITY = f"{PROV}Activity"
PROV_ENTITY = f"{PROV}Entity"
PROV_AGENT = f"{PROV}Agent"
PROV_USED = f"{PROV}used"
PROV_GENERATED = f"{PROV}generated"
PROV_ASSOCIATED_WITH = f"{PROV}wasAssociatedWith"


def write_candidate_statements(statements: list[dict], workspace_id: str) -> None:
    pass


def accept_statement(stmt_id: str, curator_id: str, workspace_id: str) -> None:
    graph = curation_graph(workspace_id)

    # Retrieve the statement via the statement id
    payload = sparql_select(
        f"""
        SELECT ?p ?o WHERE {{
            GRAPH <{graph}> {{
                <{stmt_id}> ?p ?o
            }}
        }}
        ORDER BY ?p ?o
    """
    )

    bindings = payload.get("results", {}).get("bindings", [])

    if not bindings:
        raise ValueError(f"Statement {stmt_id} not found")

    props = {b["p"]["value"]: b["o"]["value"] for b in bindings}

    old_subject = props.get(PACO_SUBJECT)
    old_predicate = props.get(PACO_PREDICATE)
    old_object = props.get(PACO_OBJECT)

    if old_subject is None or old_predicate is None or old_object is None:
        raise ValueError(f"Statement {stmt_id} is missing subject/predicate/object")

    accepted_at = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    created_at = accepted_at

    accepting_activity_id = (
        f"https://example.org/workspaces/{workspace_id}/activities/accept/{uuid4()}"
    )

    accepted_statement_id = (
        f"https://example.org/workspaces/{workspace_id}/candidate-statements/{uuid4()}"
    )

    # Mark the old statement as not current

    sparql_update(
        f"""
        DELETE {{
            GRAPH <{graph}> {{
                <{stmt_id}> <{PACO_CURRENT}> true .
            }}
        }}
        INSERT {{
            GRAPH <{graph}> {{
                <{stmt_id}> <{PACO_CURRENT}> false .
            }}
        }}
        WHERE {{
            GRAPH <{graph}> {{
                <{stmt_id}> <{PACO_CURRENT}> true .
            }}
        }}
    """
    )

    # Create the new accepted statement with the same subject/predicate/object but with curation status accepted, and link it to the accepting activity

    rdf_type = NamedNode(RDF_TYPE)

    new_statement = NamedNode(accepted_statement_id)
    accepting_activity = NamedNode(accepting_activity_id)

    candidate_class = NamedNode(PACO_CANDIDATE)
    accepting_activity_class = NamedNode(PACO_ACCEPTING_ACTIVITY)

    prov_entity = NamedNode(PROV_ENTITY)
    prov_activity = NamedNode(PROV_ACTIVITY)
    prov_agent = NamedNode(PROV_AGENT)

    curator = NamedNode(curator_id)
    curator_class = NamedNode(PACO_CURATOR)

    triples = []

    triples.extend(
        [
            Triple(accepting_activity, rdf_type, accepting_activity_class),
            Triple(accepting_activity, rdf_type, prov_activity),
            Triple(curator, rdf_type, curator_class),
            Triple(curator, rdf_type, prov_agent),
            Triple(accepting_activity, NamedNode(PROV_ASSOCIATED_WITH), curator),
            Triple(accepting_activity, NamedNode(PROV_USED), NamedNode(stmt_id)),
            Triple(accepting_activity, NamedNode(PROV_GENERATED), new_statement),
            Triple(
                accepting_activity,
                NamedNode(PACO_ACCEPTED_AT),
                Literal(accepted_at, datatype=NamedNode(XSD_DATETIME)),
            ),
            Triple(new_statement, rdf_type, candidate_class),
            Triple(new_statement, rdf_type, prov_entity),
            Triple(new_statement, NamedNode(PACO_SUBJECT), NamedNode(old_subject)),
            Triple(new_statement, NamedNode(PACO_PREDICATE), NamedNode(old_predicate)),
            Triple(new_statement, NamedNode(PACO_OBJECT), NamedNode(old_object)),
            Triple(new_statement, NamedNode(PACO_STATUS), NamedNode(PACO_ACCEPTED)),
            Triple(new_statement, NamedNode(PACO_CURRENT), Literal(True)),
            Triple(
                new_statement,
                NamedNode(PACO_CREATED_AT),
                Literal(created_at, datatype=NamedNode(XSD_DATETIME)),
            ),
            Triple(new_statement, NamedNode(PACO_ORIGIN), curator),
            Triple(new_statement, NamedNode(PROV_GENERATED_BY), accepting_activity),
            Triple(new_statement, NamedNode(PROV_DERIVED_FROM), NamedNode(stmt_id)),
        ]
    )

    triples_text = serialize(triples, format=RdfFormat.N_TRIPLES).decode("utf-8")

    sparql_update(
        f"""
        INSERT DATA {{
            GRAPH <{graph}> {{
                {triples_text}
            }}
        }}
    """
    )


def reject_statement(stmt_id: str, curator_id: str, workspace_id: str) -> None:
    pass
