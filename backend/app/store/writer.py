import uuid
from datetime import datetime, timezone
from hashlib import sha256
import json
from pathlib import Path
from urllib.parse import urlparse
from typing import Union
from uuid import uuid4

from pyoxigraph import Literal, NamedNode, RdfFormat, Triple, serialize

from app.schemas.run import StatementEdit
from app.store.client import curation_graph, data_graph, sparql_select, sparql_update
from app.store.utils import *

def validate_iri(value: str, field_name: str) -> None:
    parsed = urlparse(value)
    if not parsed.scheme or not parsed.netloc:
        raise ValueError(f"{field_name} must be a valid IRI")

def write_candidate_statements(statements: list[dict], workspace_id: str) -> None:
    return None


def load_prov(
    provenance_path: Path | None,
) -> dict[tuple[str, str, str], dict]:
    """Return a lookup dict keyed by (subject_uri, predicate_local_name, value)."""
    if provenance_path is None or not provenance_path.exists():
        return {}
    data = json.loads(provenance_path.read_text(encoding="utf-8"))
    return {
        (
            ann["subject"],
            ann["predicate"],
            ann.get("value") or ann.get("object", ""),
        ): ann
        for ann in data.get("annotations", [])
    }


def pred_local_name(uri: str) -> str:
    return uri.split("#")[-1].split("/")[-1]


def build_candidate_statement_triples(
    *,
    parsed_quads,
    workspace_id: str,
    run_id: str | None,
    document_id: str | None,
    provenance_index: dict | None = None,
    model: str = "",
):
    rdf_type_uri = f"http://www.w3.org/1999/02/22-rdf-syntax-ns#type"

    now = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    run_key = run_id or "unknown-run"
    document_key = (
        document_id or "unknown-document"
    )  # Currently only link to sql db entry, consider adding full document entity later
    workspace_key = workspace_id or "unknown-workspace"

    source_document = create_source_document_entity(workspace_key, document_key)
    extraction_activity = NamedNode(
        f"https://example.org/runs/{run_key}/documents/{document_key}/activities/extraction"
    )

    triples = [
        Triple(N_PACO_ONTOGPT, N_RDF_TYPE, N_PROV_SOFTWARE_AGENT),
        Triple(N_PACO_ONTOGPT, N_SCHEMA_NAME, Literal("ontogpt")),
        Triple(source_document, N_RDF_TYPE, N_PACO_SOURCE_DOCUMENT),
        Triple(source_document, N_RDF_TYPE, N_PROV_ENTITY),
        Triple(extraction_activity, N_RDF_TYPE, N_PACO_EXTRACTION_ACTIVITY),
        Triple(extraction_activity, N_RDF_TYPE, N_PROV_ACTIVITY),
        Triple(extraction_activity, N_PROV_USED, source_document),
        Triple(extraction_activity, N_PROV_ASSOCIATED_WITH, N_PACO_ONTOGPT),
        Triple(
            extraction_activity,
            N_PACO_EXTRACTED_AT,
            Literal(now, datatype=N_XSD_DATETIME),
        ),
    ]

    index_lookup = provenance_index or {}

    for index, quad in enumerate(parsed_quads):
        if quad.predicate.value == rdf_type_uri:
            key = (quad.subject.value, "type", quad.object.value)
            if index_lookup.get(key) is None:
                continue
        fingerprint = sha256(
            f"{workspace_key}|{run_key}|{document_key}|{index}|{quad.subject}|{quad.predicate}|{quad.object}".encode(
                "utf-8"
            )
        ).hexdigest()[
            :24
        ]  # Ensure URI uniqueness so all audits are logged independently
        candidate = NamedNode(
            f"https://example.org/workspaces/{workspace_key}/candidate-statements/{fingerprint}"
        )
        candidate_triples = [
            Triple(candidate, N_RDF_TYPE, N_PACO_CANDIDATE),
            Triple(candidate, N_RDF_TYPE, N_PROV_ENTITY),
            Triple(candidate, N_PACO_SUBJECT, quad.subject),
            Triple(candidate, N_PACO_PREDICATE, quad.predicate),
            Triple(candidate, N_PACO_OBJECT, quad.object),
            Triple(candidate, N_PACO_ORIGIN, N_PACO_ONTOGPT),
            Triple(candidate, N_PACO_STATUS, N_PACO_PENDING),
            Triple(candidate, N_PACO_CREATED_AT, Literal(now, datatype=N_XSD_DATETIME)),
            Triple(candidate, N_PACO_CURRENT, Literal(True)),
            Triple(extraction_activity, N_PROV_GENERATED, candidate),
            Triple(candidate, N_PROV_GENERATED_BY, extraction_activity),
            Triple(candidate, N_PROV_DERIVED_FROM, source_document),
        ]

        key = (
            quad.subject.value,
            pred_local_name(quad.predicate.value),
            quad.object.value,
        )
        ann = index_lookup.get(key)
        if ann is not None:
            candidate_triples.append(
                Triple(
                    candidate,
                    N_PACO_CONFIDENCE,
                    Literal(str(ann["confidence"]), datatype=N_XSD_FLOAT),
                )
            )
            if isinstance(quad.object, Literal):
                candidate_triples.extend(
                    [
                        Triple(
                            candidate,
                            N_PACO_TEXT_SPAN,
                            Literal(ann["span_text"], datatype=N_XSD_STRING),
                        ),
                        Triple(
                            candidate,
                            N_PACO_TEXT_SPAN_START,
                            Literal(str(ann["span_start"]), datatype=N_XSD_INTEGER),
                        ),
                        Triple(
                            candidate,
                            N_PACO_TEXT_SPAN_END,
                            Literal(str(ann["span_end"]), datatype=N_XSD_INTEGER),
                        ),
                    ]
                )

        triples.extend(candidate_triples)

    return triples


def write_candidate_statements_from_ttl(
    run_id: Union[str, None],
    document_id: Union[str, None],
    ttl_path: Union[str, Path],
    workspace_id: str,
    provenance_path: Union[str, Path, None] = None,
    model: Union[str, None] = None,
) -> None:
    """Load Turtle file into the workspace curation graph."""
    graph = curation_graph(workspace_id)
    ttl_text = Path(ttl_path).read_text(encoding="utf-8")

    try:
        from pyoxigraph import RdfFormat, parse
    except Exception as exc:
        raise RuntimeError(
            f"pyoxigraph parsing is unavailable; cannot import candidate statements: {exc}"
        )

    try:
        parsed_quads = list(parse(input=ttl_text, format=RdfFormat.TURTLE))
    except Exception as exc:
        raise RuntimeError(
            f"Failed to parse Turtle for candidate-statement import: {exc}"
        )

    prov_index = load_prov(Path(provenance_path) if provenance_path else None)

    triples = build_candidate_statement_triples(
        parsed_quads=parsed_quads,
        workspace_id=workspace_id,
        run_id=run_id,
        document_id=document_id,
        provenance_index=prov_index,
        model=model or "",
    )

    triples_text = serialize(triples, format=RdfFormat.N_TRIPLES).decode("utf-8")
    sparql_update(f"INSERT DATA {{ GRAPH <{graph}> {{\n{triples_text}\n}} }}")


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
