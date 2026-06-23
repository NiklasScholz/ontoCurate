import uuid
from datetime import datetime, timezone
from uuid import uuid4

from pyoxigraph import Literal, NamedNode, RdfFormat, Triple, serialize

from app.store.client import curation_graph, data_graph, sparql_select, sparql_update
from app.store.utils import (
    PACO_ACCEPTED,
    PACO_ACCEPTED_AT,
    PACO_ACCEPTING_ACTIVITY,
    PACO_CANDIDATE,
    PACO_CONFIDENCE,
    PACO_CREATED_AT,
    PACO_CURATOR,
    PACO_CURRENT,
    PACO_OBJECT,
    PACO_ORIGIN,
    PACO_PREDICATE,
    PACO_REJECTED,
    PACO_REJECTED_AT,
    PACO_REJECTING_ACTIVITY,
    PACO_STATUS,
    PACO_SUBJECT,
    PACO_TEXT_SPAN_END,
    PACO_TEXT_SPAN_START,
    PROV_ACTIVITY,
    PROV_AGENT,
    PROV_ASSOCIATED_WITH,
    PROV_DERIVED_FROM,
    PROV_ENTITY,
    PROV_GENERATED_BY,
    PROV_USED,
    RDF_TYPE,
    XSD_DATETIME,
    XSD_INTEGER,
)


def write_candidate_statements(statements: list[dict], workspace_id: str) -> None:
    pass


def accept_statement(stmt_id: str, triggered_by: uuid.UUID, workspace_id: str) -> None:
    graph = curation_graph(workspace_id)
    accepted_graph = data_graph(workspace_id)

    # Retrieve the statement via the statement id
    payload = sparql_select(f"""
        SELECT ?p ?o WHERE {{
            GRAPH <{graph}> {{
                <{stmt_id}> ?p ?o
            }}
        }}
        ORDER BY ?p ?o
    """)

    bindings = payload.get("results", {}).get("bindings", [])

    if not bindings:
        raise ValueError(f"Statement {stmt_id} not found")

    props = {b["p"]["value"]: b["o"]["value"] for b in bindings}

    old_subject = props.get(PACO_SUBJECT)
    old_predicate = props.get(PACO_PREDICATE)
    old_object = props.get(PACO_OBJECT)
    confidence_score = props.get(PACO_CONFIDENCE)

    # get text span if exists
    text_span_start = None
    text_span_end = None
    if PACO_TEXT_SPAN_START in props:
        text_span_start = props[PACO_TEXT_SPAN_START]
    if PACO_TEXT_SPAN_END in props:
        text_span_end = props[PACO_TEXT_SPAN_END]

    if old_subject is None or old_predicate is None or old_object is None:
        raise ValueError(f"Statement {stmt_id} is missing subject/predicate/object")

    if confidence_score is None:
        raise ValueError(f"Statement {stmt_id} is missing confidence score")

    accepted_at = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    created_at = accepted_at

    accepting_activity_id = (
        f"https://example.org/workspaces/{workspace_id}/activities/accept/{uuid4()}"
    )

    accepted_statement_id = (
        f"https://example.org/workspaces/{workspace_id}/candidate-statements/{uuid4()}"
    )

    # Mark the old statement as not current

    sparql_update(f"""
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
    """)

    # Create the new accepted statement with the same subject/predicate/object but with curation status accepted, and link it to the accepting activity

    rdf_type = NamedNode(RDF_TYPE)

    new_statement = NamedNode(accepted_statement_id)
    accepting_activity = NamedNode(accepting_activity_id)

    candidate_class = NamedNode(PACO_CANDIDATE)
    accepting_activity_class = NamedNode(PACO_ACCEPTING_ACTIVITY)

    prov_entity = NamedNode(PROV_ENTITY)
    prov_activity = NamedNode(PROV_ACTIVITY)
    prov_agent = NamedNode(PROV_AGENT)

    curator = NamedNode(f"https://example.org/users/{triggered_by}")
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
            Triple(
                new_statement, NamedNode(PACO_CONFIDENCE), Literal(confidence_score)
            ),
        ]
    )

    if text_span_start is not None and text_span_end is not None:
        triples.append(
            Triple(
                new_statement,
                NamedNode(PACO_TEXT_SPAN_START),
                Literal(text_span_start, datatype=NamedNode(XSD_INTEGER)),
            )
        )
        triples.append(
            Triple(
                new_statement,
                NamedNode(PACO_TEXT_SPAN_END),
                Literal(text_span_end, datatype=NamedNode(XSD_INTEGER)),
            )
        )

    triples_text = serialize(triples, format=RdfFormat.N_TRIPLES).decode("utf-8")

    # write tripples to curation graph
    sparql_update(f"""
        INSERT DATA {{
            GRAPH <{graph}> {{
                {triples_text}
            }}
        }}
    """)

    # write tripples to data graph
    sparql_update(f"""
        INSERT DATA {{
            GRAPH <{accepted_graph}> {{
                <{old_subject}> <{old_predicate}> <{old_object}> .
            }}
        }}
    """)


def reject_statement(stmt_id: str, triggered_by: uuid.UUID, workspace_id: str) -> None:
    graph = curation_graph(workspace_id)

    # Retrieve the statement via the statement id
    payload = sparql_select(f"""
        SELECT ?p ?o WHERE {{
            GRAPH <{graph}> {{
                <{stmt_id}> ?p ?o
            }}
        }}
        ORDER BY ?p ?o
    """)

    bindings = payload.get("results", {}).get("bindings", [])

    if not bindings:
        raise ValueError(f"Statement {stmt_id} not found")

    props = {b["p"]["value"]: b["o"]["value"] for b in bindings}

    old_subject = props.get(PACO_SUBJECT)
    old_predicate = props.get(PACO_PREDICATE)
    old_object = props.get(PACO_OBJECT)
    confidence_score = props.get(PACO_CONFIDENCE)

    # get text span if exists
    text_span_start = None
    text_span_end = None
    if PACO_TEXT_SPAN_START in props:
        text_span_start = props[PACO_TEXT_SPAN_START]
    if PACO_TEXT_SPAN_END in props:
        text_span_end = props[PACO_TEXT_SPAN_END]

    if old_subject is None or old_predicate is None or old_object is None:
        raise ValueError(f"Statement {stmt_id} is missing subject/predicate/object")

    if confidence_score is None:
        raise ValueError(f"Statement {stmt_id} is missing confidence score")

    rejected_at = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    created_at = rejected_at

    rejecting_activity_id = (
        f"https://example.org/workspaces/{workspace_id}/activities/reject/{uuid4()}"
    )

    rejected_statement_id = (
        f"https://example.org/workspaces/{workspace_id}/candidate-statements/{uuid4()}"
    )

    # Mark the old statement as not current

    sparql_update(f"""
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
    """)

    # Create the new rejected statement with the same subject/predicate/object but with curation status rejected, and link it to the rejecting activity

    rdf_type = NamedNode(RDF_TYPE)

    new_statement = NamedNode(rejected_statement_id)
    rejecting_activity = NamedNode(rejecting_activity_id)

    candidate_class = NamedNode(PACO_CANDIDATE)
    rejecting_activity_class = NamedNode(PACO_REJECTING_ACTIVITY)

    prov_entity = NamedNode(PROV_ENTITY)
    prov_activity = NamedNode(PROV_ACTIVITY)
    prov_agent = NamedNode(PROV_AGENT)

    curator = NamedNode(f"https://example.org/users/{triggered_by}")
    curator_class = NamedNode(PACO_CURATOR)

    triples = []

    triples.extend(
        [
            Triple(rejecting_activity, rdf_type, rejecting_activity_class),
            Triple(rejecting_activity, rdf_type, prov_activity),
            Triple(curator, rdf_type, curator_class),
            Triple(curator, rdf_type, prov_agent),
            Triple(rejecting_activity, NamedNode(PROV_ASSOCIATED_WITH), curator),
            Triple(rejecting_activity, NamedNode(PROV_USED), NamedNode(stmt_id)),
            Triple(
                rejecting_activity,
                NamedNode(PACO_REJECTED_AT),
                Literal(rejected_at, datatype=NamedNode(XSD_DATETIME)),
            ),
            Triple(new_statement, rdf_type, candidate_class),
            Triple(new_statement, rdf_type, prov_entity),
            Triple(new_statement, NamedNode(PACO_SUBJECT), NamedNode(old_subject)),
            Triple(new_statement, NamedNode(PACO_PREDICATE), NamedNode(old_predicate)),
            Triple(new_statement, NamedNode(PACO_OBJECT), NamedNode(old_object)),
            Triple(new_statement, NamedNode(PACO_STATUS), NamedNode(PACO_REJECTED)),
            Triple(new_statement, NamedNode(PACO_CURRENT), Literal(True)),
            Triple(
                new_statement,
                NamedNode(PACO_CREATED_AT),
                Literal(created_at, datatype=NamedNode(XSD_DATETIME)),
            ),
            Triple(new_statement, NamedNode(PACO_ORIGIN), curator),
            Triple(new_statement, NamedNode(PROV_GENERATED_BY), rejecting_activity),
            Triple(new_statement, NamedNode(PROV_DERIVED_FROM), NamedNode(stmt_id)),
            Triple(
                new_statement, NamedNode(PACO_CONFIDENCE), Literal(confidence_score)
            ),
        ]
    )

    if text_span_start is not None and text_span_end is not None:
        triples.append(
            Triple(
                new_statement,
                NamedNode(PACO_TEXT_SPAN_START),
                Literal(text_span_start, datatype=NamedNode(XSD_INTEGER)),
            )
        )
        triples.append(
            Triple(
                new_statement,
                NamedNode(PACO_TEXT_SPAN_END),
                Literal(text_span_end, datatype=NamedNode(XSD_INTEGER)),
            )
        )

    triples_text = serialize(triples, format=RdfFormat.N_TRIPLES).decode("utf-8")

    # write tripples to curation graph
    sparql_update(f"""
        INSERT DATA {{
            GRAPH <{graph}> {{
                {triples_text}
            }}
        }}
    """)
