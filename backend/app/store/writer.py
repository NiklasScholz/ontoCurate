import uuid
from datetime import datetime, timezone
from urllib.parse import urlparse
from uuid import uuid4

from pyoxigraph import Literal, NamedNode, RdfFormat, Triple, serialize

from app.schemas.run import StatementEdit
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
    PACO_EDITED,
    PACO_EDITED_AT,
    PACO_EDITING_ACTIVITY,
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
    XSD_FLOAT,
    XSD_INTEGER,
)


def validate_iri(value: str, field_name: str) -> None:
    parsed = urlparse(value)
    if not parsed.scheme or not parsed.netloc:
        raise ValueError(f"{field_name} must be a valid IRI")


def load_candidate_statement(stmt_id: str, graph: str) -> dict:

    # Retrieve the statement via the statement id

    payload = sparql_select(f"""
        SELECT ?p ?o WHERE {{
            GRAPH <{graph}> {{
                <{stmt_id}> ?p ?o
            }}
        }}
        ORDER BY ?p ?o
        """)

    # Process the query results

    bindings = payload.get("results", {}).get("bindings", [])

    if not bindings:
        raise ValueError(f"Statement {stmt_id} not found")

    props = {b["p"]["value"]: b["o"]["value"] for b in bindings}

    # Get the subject and predicate for the statement
    old_subject = props.get(PACO_SUBJECT)
    old_predicate = props.get(PACO_PREDICATE)

    # Get the object binding for the statement (can be either a URI or a literal)
    old_object_binding = next(
        (b["o"] for b in bindings if b["p"]["value"] == PACO_OBJECT),
        None,
    )

    if old_subject is None or old_predicate is None or old_object_binding is None:
        raise ValueError(f"Statement {stmt_id} is missing subject/predicate/object")

    old_object_value = old_object_binding.get("value")
    old_object_type = old_object_binding.get("type")

    if old_object_value is None:
        raise ValueError(f"Statement {stmt_id} is missing object value")

    if old_object_type == "uri":
        object_node = NamedNode(old_object_value)
    else:
        object_node = Literal(old_object_value)

    # Get confidence score
    confidence_score = props.get(PACO_CONFIDENCE)

    if confidence_score is None:
        raise ValueError(f"Statement {stmt_id} is missing confidence score")

    # Get text span if exists
    text_span_start = None
    text_span_end = None
    if PACO_TEXT_SPAN_START in props:
        text_span_start = props[PACO_TEXT_SPAN_START]
    if PACO_TEXT_SPAN_END in props:
        text_span_end = props[PACO_TEXT_SPAN_END]

    return {
        "props": props,
        "subject": old_subject,
        "predicate": old_predicate,
        "object_node": object_node,
        "confidence_score": confidence_score,
        "text_span_start": text_span_start,
        "text_span_end": text_span_end,
    }


def write_candidate_statements(statements: list[dict], workspace_id: str) -> None:
    pass


def accept_statement(stmt_id: str, triggered_by: uuid.UUID, workspace_id: str) -> None:
    graph = curation_graph(workspace_id)
    accepted_graph = data_graph(workspace_id)

    # Load the candidate statement
    candidate_statement = load_candidate_statement(stmt_id, graph)

    old_subject = candidate_statement["subject"]
    old_predicate = candidate_statement["predicate"]
    object_node = candidate_statement["object_node"]
    confidence_score = candidate_statement["confidence_score"]
    text_span_start = candidate_statement["text_span_start"]
    text_span_end = candidate_statement["text_span_end"]

    # Get the current timestamp in ISO 8601 format with UTC timezone
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
            Triple(new_statement, NamedNode(PACO_OBJECT), object_node),
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
                new_statement,
                NamedNode(PACO_CONFIDENCE),
                Literal(confidence_score, datatype=NamedNode(XSD_FLOAT)),
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

    data_triples_text = serialize(
        [
            Triple(NamedNode(old_subject), NamedNode(old_predicate), object_node),
        ],
        format=RdfFormat.N_TRIPLES,
    ).decode("utf-8")

    # write tripples to data graph
    sparql_update(f"""
        INSERT DATA {{
            GRAPH <{accepted_graph}> {{
                {data_triples_text}
            }}
        }}
    """)


def reject_statement(stmt_id: str, triggered_by: uuid.UUID, workspace_id: str) -> None:
    graph = curation_graph(workspace_id)

    # Load the candidate statement

    candidate_statement = load_candidate_statement(stmt_id, graph)

    old_subject = candidate_statement["subject"]
    old_predicate = candidate_statement["predicate"]
    object_node = candidate_statement["object_node"]
    confidence_score = candidate_statement["confidence_score"]
    text_span_start = candidate_statement["text_span_start"]
    text_span_end = candidate_statement["text_span_end"]

    # Get the current timestamp in ISO 8601 format with UTC timezone

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
            Triple(new_statement, NamedNode(PACO_OBJECT), object_node),
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
                new_statement,
                NamedNode(PACO_CONFIDENCE),
                Literal(confidence_score, datatype=NamedNode(XSD_FLOAT)),
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


def edit_statement(
    stmt_id: str,
    triggered_by: uuid.UUID,
    workspace_id: str,
    edit: StatementEdit,
) -> None:
    graph = curation_graph(workspace_id)

    # Check that either object_iri or object_value is provided, but not both

    if edit.object_iri is not None and edit.object_value is not None:
        raise ValueError("Use either object_iri or object_value, not both")

    # Load the candidate statement

    candidate_statement = load_candidate_statement(stmt_id, graph)

    old_subject = candidate_statement["subject"]
    old_predicate = candidate_statement["predicate"]
    object_node = candidate_statement["object_node"]
    confidence_score = candidate_statement["confidence_score"]
    text_span_start = candidate_statement["text_span_start"]
    text_span_end = candidate_statement["text_span_end"]

    new_subject = edit.subject or old_subject
    new_predicate = edit.predicate or old_predicate

    # Determine the new object node based on the provided edit

    if edit.object_iri is not None:
        new_object = NamedNode(edit.object_iri)
    elif edit.object_value is not None:
        new_object = Literal(edit.object_value)
    else:
        new_object = object_node

    # Check whether subject, predicate, or object has changed; if not, raise an error

    no_subject_change = edit.subject is None or edit.subject == old_subject
    no_predicate_change = edit.predicate is None or edit.predicate == old_predicate
    no_object_change = edit.object_iri is None and edit.object_value is None

    if no_subject_change and no_predicate_change and no_object_change:
        raise ValueError("No changes detected in subject, predicate, or object")

    # Check if the new subject, predicate and object are valid IRIs or literals; if not, raise an error

    if edit.subject is not None:
        validate_iri(edit.subject, "subject")

    if edit.predicate is not None:
        validate_iri(edit.predicate, "predicate")

    if edit.object_iri is not None:
        validate_iri(edit.object_iri, "object_iri")

    # Get the current timestamp in ISO 8601 format with UTC timezone

    edited_at = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    created_at = edited_at

    editing_activity_id = (
        f"https://example.org/workspaces/{workspace_id}/activities/edit/{uuid4()}"
    )

    edited_statement_id = (
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

    # Create the new edited statement and link it to the editing activity

    rdf_type = NamedNode(RDF_TYPE)

    new_statement = NamedNode(edited_statement_id)
    editing_activity = NamedNode(editing_activity_id)

    candidate_class = NamedNode(PACO_CANDIDATE)
    editing_activity_class = NamedNode(PACO_EDITING_ACTIVITY)

    prov_entity = NamedNode(PROV_ENTITY)
    prov_activity = NamedNode(PROV_ACTIVITY)
    prov_agent = NamedNode(PROV_AGENT)

    curator = NamedNode(f"https://example.org/users/{triggered_by}")
    curator_class = NamedNode(PACO_CURATOR)

    triples = []

    triples.extend(
        [
            Triple(editing_activity, rdf_type, editing_activity_class),
            Triple(editing_activity, rdf_type, prov_activity),
            Triple(curator, rdf_type, curator_class),
            Triple(curator, rdf_type, prov_agent),
            Triple(editing_activity, NamedNode(PROV_ASSOCIATED_WITH), curator),
            Triple(editing_activity, NamedNode(PROV_USED), NamedNode(stmt_id)),
            Triple(
                editing_activity,
                NamedNode(PACO_EDITED_AT),
                Literal(edited_at, datatype=NamedNode(XSD_DATETIME)),
            ),
            Triple(new_statement, rdf_type, candidate_class),
            Triple(new_statement, rdf_type, prov_entity),
            Triple(new_statement, NamedNode(PACO_SUBJECT), NamedNode(new_subject)),
            Triple(new_statement, NamedNode(PACO_PREDICATE), NamedNode(new_predicate)),
            Triple(new_statement, NamedNode(PACO_OBJECT), new_object),
            Triple(new_statement, NamedNode(PACO_STATUS), NamedNode(PACO_EDITED)),
            Triple(new_statement, NamedNode(PACO_CURRENT), Literal(True)),
            Triple(
                new_statement,
                NamedNode(PACO_CREATED_AT),
                Literal(created_at, datatype=NamedNode(XSD_DATETIME)),
            ),
            Triple(new_statement, NamedNode(PACO_ORIGIN), curator),
            Triple(new_statement, NamedNode(PROV_GENERATED_BY), editing_activity),
            Triple(new_statement, NamedNode(PROV_DERIVED_FROM), NamedNode(stmt_id)),
            Triple(
                new_statement,
                NamedNode(PACO_CONFIDENCE),
                Literal(confidence_score, datatype=NamedNode(XSD_FLOAT)),
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
