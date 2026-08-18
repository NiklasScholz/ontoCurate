import json
import uuid
from datetime import datetime, timezone
from hashlib import sha256
from pathlib import Path
from typing import Union
from urllib.parse import urlparse
from uuid import uuid4

from pyoxigraph import Literal, NamedNode, RdfFormat, Triple, serialize

from app.schemas.statement import StatementEdit, StatementResponse
from app.store.client import curation_graph, data_graph, sparql_select, sparql_update
from app.store.utils import *


def validate_iri(value: str, field_name: str) -> None:
    parsed = urlparse(value)
    if not parsed.scheme or not parsed.netloc:
        raise ValueError(f"{field_name} must be a valid IRI")


def curator_node(user_id: uuid.UUID) -> NamedNode:
    return NamedNode(f"{USERS}{user_id}")


def upsert_curator(
    workspace_id: str,
    user_id: uuid.UUID,
    name: str | None,
    email: str,
    username: str | None,
) -> None:
    """
    Adds curator information into provenance graph for more informative provenance querying.
    Workspace owners typically do not know the user_id of the curators, so we allow upserting curator information with the user_id, name, email, and username until their account gets deleted when this data is being anonymized.
    """
    graph = curation_graph(workspace_id)
    curator = curator_node(user_id)

    # ensure idempotence by deleting existing user with this information
    sparql_update(f"""
        DELETE {{
            GRAPH <{graph}> {{
                <{curator.value}> <{SCHEMA_NAME}> ?name .
                <{curator.value}> <{SCHEMA_EMAIL}> ?email .
                <{curator.value}> <{PACO_USERNAME}> ?username .
            }}
        }}
        WHERE {{
            GRAPH <{graph}> {{
                OPTIONAL {{ <{curator.value}> <{SCHEMA_NAME}> ?name . }}
                OPTIONAL {{ <{curator.value}> <{SCHEMA_EMAIL}> ?email . }}
                OPTIONAL {{ <{curator.value}> <{PACO_USERNAME}> ?username . }}
            }}
        }}
    """)

    triples = [
        Triple(curator, N_RDF_TYPE, N_PACO_CURATOR),
        Triple(curator, N_RDF_TYPE, N_PROV_AGENT),
        Triple(curator, N_SCHEMA_NAME, Literal(name or username or str(user_id))),
        Triple(curator, N_SCHEMA_EMAIL, Literal(email)),
    ]
    if username:
        triples.append(Triple(curator, N_PACO_USERNAME, Literal(username)))

    triples_text = serialize(triples, format=RdfFormat.N_TRIPLES).decode("utf-8")
    sparql_update(f"INSERT DATA {{ GRAPH <{graph}> {{\n{triples_text}\n}} }}")


def anonymize_curator(user_id: uuid.UUID) -> None:
    """Strips curators identifying information from the graph when their account is deleted."""
    curator = curator_node(user_id)

    sparql_update(f"""
        DELETE {{
            GRAPH ?g {{
                <{curator.value}> <{SCHEMA_NAME}> ?name .
                <{curator.value}> <{SCHEMA_EMAIL}> ?email .
                <{curator.value}> <{PACO_USERNAME}> ?username .
            }}
        }}
        INSERT {{
            GRAPH ?g {{
                <{curator.value}> <{SCHEMA_NAME}> "Deleted user" .
                <{curator.value}> <{PACO_DELETED}> true .
            }}
        }}
        WHERE {{
            GRAPH ?g {{
                <{curator.value}> <{RDF_TYPE}> <{PACO_CURATOR}> .
                OPTIONAL {{ <{curator.value}> <{SCHEMA_NAME}> ?name . }}
                OPTIONAL {{ <{curator.value}> <{SCHEMA_EMAIL}> ?email . }}
                OPTIONAL {{ <{curator.value}> <{PACO_USERNAME}> ?username . }}
            }}
        }}
    """)


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

    source_document = create_source_document_entity(document_key)
    extraction_activity = NamedNode(f"{EXTRACTION_ACTIVITIES}{uuid4()}")

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
        candidate = NamedNode(f"{CANDIDATE_STATEMENTS}{fingerprint}")
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
        confidence = ann["confidence"] if ann is not None else 0.0

        candidate_triples.append(
            Triple(
                candidate,
                N_PACO_CONFIDENCE,
                Literal(str(confidence), datatype=N_XSD_FLOAT),
            )
        )
        if ann is not None and "span_start" in ann and "span_end" in ann:
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
            f"pyoxigraph parsing is unavailable; cannot import candidate statements: {
                exc
            }"
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

    bindings = payload.get("results", {}).get("bindings", [])

    if not bindings:
        raise ValueError(f"Statement {stmt_id} not found")

    return _parse_candidate_statement_bindings(stmt_id, bindings)


def load_candidate_statements_bulk(stmt_ids: list[str], graph: str) -> dict[str, dict]:
    """Same as load_candidate_statement, but loads many statements at once."""
    if not stmt_ids:
        return {}
    values_clause = " ".join(f"<{stmt_id}>" for stmt_id in stmt_ids)
    payload = sparql_select(f"""
        SELECT ?s ?p ?o WHERE {{
            GRAPH <{graph}> {{
                VALUES ?s {{ {values_clause} }}
                ?s ?p ?o
            }}
        }}
        ORDER BY ?s ?p ?o
        """)

    bindings_by_subject = {}
    for binding in payload.get("results", {}).get("bindings", []):
        bindings_by_subject.setdefault(binding["s"]["value"], []).append(binding)

    result = {}
    for stmt_id in stmt_ids:
        bindings = bindings_by_subject.get(stmt_id)
        if not bindings:
            raise ValueError(f"Statement {stmt_id} not found")
        result[stmt_id] = _parse_candidate_statement_bindings(stmt_id, bindings)
    return result


def _parse_candidate_statement_bindings(stmt_id: str, bindings: list) -> dict:
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
        old_object_datatype = old_object_binding.get("datatype")
        object_node = Literal(
            old_object_value,
            language=old_object_binding.get("xml:lang"),
            datatype=NamedNode(old_object_datatype) if old_object_datatype else None,
        )

    # Get confidence score
    confidence_score = props.get(PACO_CONFIDENCE)

    # Get text span if exists
    text_span_start = None
    text_span_end = None
    if PACO_TEXT_SPAN_START in props:
        text_span_start = props[PACO_TEXT_SPAN_START]
    if PACO_TEXT_SPAN_END in props:
        text_span_end = props[PACO_TEXT_SPAN_END]

    # Get is_current, status, origin, and created_at properties
    is_current = props.get(PACO_CURRENT)
    status = props.get(PACO_STATUS)
    origin = props.get(PACO_ORIGIN)
    created_at = props.get(PACO_CREATED_AT)

    return {
        "props": props,
        "subject": old_subject,
        "predicate": old_predicate,
        "object_node": object_node,
        "confidence_score": confidence_score,
        "text_span_start": text_span_start,
        "text_span_end": text_span_end,
        "is_current": is_current,
        "status": status,
        "origin": origin,
        "created_at": created_at,
    }


def find_original_candidate_statement(
    stmt_id: str,
    graph: str,
) -> str:
    payload = sparql_select(f"""
        SELECT DISTINCT ?originalStatement
        WHERE {{
            GRAPH <{graph}> {{
                <{stmt_id}>
                    <{PROV_DERIVED_FROM}>*
                    ?originalStatement .

                ?originalStatement
                    <{RDF_TYPE}>
                    <{PACO_CANDIDATE}> .

                ?originalStatement
                    <{PROV_DERIVED_FROM}>
                    ?sourceDocument .

                ?sourceDocument
                    <{RDF_TYPE}>
                    <{PACO_SOURCE_DOCUMENT}> .
            }}
        }}
        """)

    bindings = payload.get("results", {}).get("bindings", [])

    if len(bindings) == 0:
        raise ValueError(
            f"No original CandidateStatement found for statement {stmt_id}"
        )

    if len(bindings) > 1:
        raise ValueError(
            f"Expected exactly one original CandidateStatement for {stmt_id}, "
            f"found {len(bindings)}"
        )

    return bindings[0]["originalStatement"]["value"]


def set_to_not_current(stmt_id: str, graph: str) -> None:
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


def write_alignment_results(
    alignments: list[tuple[str, str, float]],
    workspace_id: str,
    run_id: str | None = None,
    document_ids: list[str] | None = None,
) -> None:
    """Writes owl:sameAs CandidateStatements for proposed entity alignments."""
    if not alignments:
        return

    run_key = run_id or "unknown-run"
    now = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    doc_ids = document_ids or []

    if len(doc_ids) == 1:
        doc_key = doc_ids[0]
        alignment_activity = NamedNode(f"{ALIGNMENT_ACTIVITIES}{uuid4()}")
    else:
        sorted_ids = sorted(doc_ids)
        doc_key = "|".join(sorted_ids) if doc_ids else "unknown"
        alignment_activity = NamedNode(
            f"{CROSS_DOCUMENT_ALIGNMENT_ACTIVITIES}{uuid4()}"
        )

    triples = [
        Triple(N_PACO_ENTITY_ALIGNMENT, N_RDF_TYPE, N_PROV_SOFTWARE_AGENT),
        Triple(N_PACO_ENTITY_ALIGNMENT, N_SCHEMA_NAME, Literal("entity-alignment")),
        Triple(alignment_activity, N_RDF_TYPE, N_PACO_ALIGNMENT_ACTIVITY),
        Triple(alignment_activity, N_RDF_TYPE, N_PROV_ACTIVITY),
        Triple(alignment_activity, N_PROV_ASSOCIATED_WITH, N_PACO_ENTITY_ALIGNMENT),
        Triple(
            alignment_activity,
            N_PACO_CREATED_AT,
            Literal(now, datatype=N_XSD_DATETIME),
        ),
    ]

    for canonical, duplicate, score in alignments:
        fingerprint = sha256(
            f"{workspace_id}|{run_key}|{doc_key}|{duplicate}|{canonical}".encode()
        ).hexdigest()[:24]
        candidate = NamedNode(f"{CANDIDATE_STATEMENTS}{fingerprint}")
        triples.extend(
            [
                Triple(candidate, N_RDF_TYPE, N_PACO_CANDIDATE),
                Triple(candidate, N_RDF_TYPE, N_PROV_ENTITY),
                Triple(candidate, N_PACO_SUBJECT, NamedNode(duplicate)),
                Triple(candidate, N_PACO_PREDICATE, N_OWL_SAME_AS),
                Triple(candidate, N_PACO_OBJECT, NamedNode(canonical)),
                Triple(candidate, N_PACO_ORIGIN, N_PACO_ENTITY_ALIGNMENT),
                Triple(candidate, N_PACO_STATUS, N_PACO_PENDING),
                Triple(
                    candidate,
                    N_PACO_CONFIDENCE,
                    Literal(str(round(score, 6)), datatype=N_XSD_FLOAT),
                ),
                Triple(
                    candidate,
                    N_PACO_CREATED_AT,
                    Literal(now, datatype=N_XSD_DATETIME),
                ),
                Triple(candidate, N_PACO_CURRENT, Literal(True)),
                Triple(candidate, N_PROV_GENERATED_BY, alignment_activity),
                Triple(alignment_activity, N_PROV_GENERATED, candidate),
            ]
        )
        for d in doc_ids:
            triples.append(
                Triple(
                    candidate,
                    N_PROV_DERIVED_FROM,
                    create_source_document_entity(d),
                )
            )

    graph = curation_graph(workspace_id)
    triples_text = serialize(triples, format=RdfFormat.N_TRIPLES).decode("utf-8")
    sparql_update(f"INSERT DATA {{ GRAPH <{graph}> {{\n{triples_text}\n}} }}")


def write_lookup_results(
    lookups: list[tuple[str, str, float]],
    workspace_id: str,
    source: str = "wikidata",
    run_id: str | None = None,
    document_ids: list[str] | None = None,
) -> None:
    """
    Writes owl:sameAs CandidateStatements for proposed entity lookup tuples.

    Each lookup tuple contains:

        (
            local_entity_uri,
            candidate_entity_uri,
            confidence_score,
        )

    `source` identifies which lookup source produced the candidates
    The generated statements remain pending until a curator accepts
    or rejects them.
    """
    if not lookups:
        return

    run_key = run_id or "unknown-run"
    now = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")

    # Remove duplicates so provenance links are not written multiple times.
    doc_ids = sorted(set(document_ids or []))
    document_key = "|".join(doc_ids) if doc_ids else "unknown-documents"

    lookup_activity = NamedNode(f"{LOOKUP_ACTIVITIES}{uuid4()}")
    lookup_agent = NamedNode(f"{PACO}{source}-lookup")

    triples = [
        Triple(lookup_agent, N_RDF_TYPE, N_PROV_SOFTWARE_AGENT),
        Triple(lookup_agent, N_SCHEMA_NAME, Literal(f"{source}-lookup")),
        Triple(lookup_activity, N_RDF_TYPE, N_PACO_LOOKUP_ACTIVITY),
        Triple(lookup_activity, N_RDF_TYPE, N_PROV_ACTIVITY),
        Triple(lookup_activity, N_PROV_ASSOCIATED_WITH, lookup_agent),
        Triple(
            lookup_activity,
            N_PACO_CREATED_AT,
            Literal(now, datatype=N_XSD_DATETIME),
        ),
    ]

    # Record the documents used by the lookup activity.
    for document_id in doc_ids:
        source_document = create_source_document_entity(document_id)

        triples.append(
            Triple(
                lookup_activity,
                N_PROV_USED,
                source_document,
            )
        )

    for local_uri, candidate_uri, score in lookups:
        fingerprint = sha256(
            (
                f"{workspace_id}|"
                f"{run_key}|"
                f"{document_key}|"
                f"{local_uri}|"
                f"{candidate_uri}"
            ).encode("utf-8")
        ).hexdigest()[:24]

        candidate = NamedNode(f"{CANDIDATE_STATEMENTS}{fingerprint}")

        triples.extend(
            [
                Triple(candidate, N_RDF_TYPE, N_PACO_CANDIDATE),
                Triple(candidate, N_RDF_TYPE, N_PROV_ENTITY),
                Triple(candidate, N_PACO_SUBJECT, NamedNode(local_uri)),
                Triple(candidate, N_PACO_PREDICATE, N_OWL_SAME_AS),
                Triple(candidate, N_PACO_OBJECT, NamedNode(candidate_uri)),
                Triple(candidate, N_PACO_ORIGIN, lookup_agent),
                Triple(candidate, N_PACO_STATUS, N_PACO_PENDING),
                Triple(
                    candidate,
                    N_PACO_CONFIDENCE,
                    Literal(
                        str(round(score, 6)),
                        datatype=N_XSD_FLOAT,
                    ),
                ),
                Triple(
                    candidate,
                    N_PACO_CREATED_AT,
                    Literal(
                        now,
                        datatype=N_XSD_DATETIME,
                    ),
                ),
                Triple(candidate, N_PACO_CURRENT, Literal(True)),
                Triple(candidate, N_PROV_GENERATED_BY, lookup_activity),
                Triple(lookup_activity, N_PROV_GENERATED, candidate),
            ]
        )

        for document_id in doc_ids:
            triples.append(
                Triple(
                    candidate,
                    N_PROV_DERIVED_FROM,
                    create_source_document_entity(document_id),
                )
            )

    graph = curation_graph(workspace_id)
    triples_text = serialize(triples, format=RdfFormat.N_TRIPLES).decode("utf-8")
    sparql_update(f"INSERT DATA {{GRAPH <{graph}> {{{triples_text}}} }}")


def delete_document_data(workspace_id: str, document_id: str) -> None:
    """Removes everything a document contributed to a workspace from oxigraph"""
    graph = curation_graph(workspace_id)
    accepted_graph = data_graph(workspace_id)
    source_document = create_source_document_entity(document_id)

    # remove data graph triples from the document
    sparql_update(f"""
        DELETE {{
            GRAPH <{accepted_graph}> {{ ?s ?p ?o }}
        }}
        WHERE {{
            GRAPH <{graph}> {{
                ?cs <{PACO_SUBJECT}> ?s ;
                    <{PACO_PREDICATE}> ?p ;
                    <{PACO_OBJECT}> ?o ;
                    <{PROV_DERIVED_FROM}>+ <{source_document.value}> .
            }}
            GRAPH <{accepted_graph}> {{ ?s ?p ?o }}
        }}
    """)

    # remove all activities that are associated with the document
    sparql_update(f"""
        DELETE {{
            GRAPH <{graph}> {{ ?activity ?ap ?ao }}
        }}
        WHERE {{
            GRAPH <{graph}> {{
                {{
                    ?activity <{PROV_USED}> <{source_document.value}> .
                }} UNION {{
                    ?cs <{PROV_DERIVED_FROM}>+ <{source_document.value}> .
                    ?activity <{PROV_USED}> ?cs .
                }} UNION {{
                    ?cs <{PROV_DERIVED_FROM}>+ <{source_document.value}> .
                    ?activity <{PROV_GENERATED}> ?cs .
                }}
                ?activity ?ap ?ao .
            }}
        }}
    """)

    # Remove all candidate statements associated with the document
    sparql_update(f"""
        DELETE {{
            GRAPH <{graph}> {{ ?cs ?p ?o }}
        }}
        WHERE {{
            GRAPH <{graph}> {{
                ?cs <{PROV_DERIVED_FROM}>+ <{source_document.value}> ;
                    ?p ?o .
            }}
        }}
    """)

    # Remove the source document entity triples
    sparql_update(f"""
        DELETE {{
            GRAPH <{graph}> {{ <{source_document.value}> ?p ?o }}
        }}
        WHERE {{
            GRAPH <{graph}> {{ <{source_document.value}> ?p ?o }}
        }}
    """)


def accept_statement(stmt_id: str, triggered_by: uuid.UUID, workspace_id: str) -> str:
    return accept_statements_bulk([stmt_id], triggered_by, workspace_id)[stmt_id]


def accept_statements_bulk(
    stmt_ids: list[str], triggered_by: uuid.UUID, workspace_id: str
) -> dict[str, str]:
    """Accept many statements with 2 queries: one SELECT to load candidates and one UPDATE to adapt old statements and add new statements."""
    if not stmt_ids:
        return {}

    graph = curation_graph(workspace_id)
    accepted_graph = data_graph(workspace_id)

    candidates = load_candidate_statements_bulk(stmt_ids, graph)

    for stmt_id in stmt_ids:
        is_current = candidates[stmt_id]["is_current"]
        if is_current is None or is_current.lower() != "true":
            raise ValueError(f"Statement {stmt_id} is not the current version")

    accepted_at = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    created_at = accepted_at

    rdf_type = NamedNode(RDF_TYPE)
    candidate_class = NamedNode(PACO_CANDIDATE)
    accepting_activity_class = NamedNode(PACO_ACCEPTING_ACTIVITY)
    prov_entity = NamedNode(PROV_ENTITY)
    prov_activity = NamedNode(PROV_ACTIVITY)
    prov_agent = NamedNode(PROV_AGENT)
    curator = curator_node(triggered_by)
    curator_class = NamedNode(PACO_CURATOR)

    curation_triples = [
        Triple(curator, rdf_type, curator_class),
        Triple(curator, rdf_type, prov_agent),
    ]
    data_triples = []
    new_ids: dict[str, str] = {}

    for stmt_id in stmt_ids:
        candidate_statement = candidates[stmt_id]
        old_subject = candidate_statement["subject"]
        old_predicate = candidate_statement["predicate"]
        object_node = candidate_statement["object_node"]
        confidence_score = candidate_statement["confidence_score"]
        text_span_start = candidate_statement["text_span_start"]
        text_span_end = candidate_statement["text_span_end"]

        accepting_activity_id = f"{ACCEPT_ACTIVITIES}{uuid4()}"
        accepted_statement_id = f"{CANDIDATE_STATEMENTS}{uuid4()}"
        new_ids[stmt_id] = accepted_statement_id

        new_statement = NamedNode(accepted_statement_id)
        accepting_activity = NamedNode(accepting_activity_id)

        curation_triples.extend(
            [
                Triple(accepting_activity, rdf_type, accepting_activity_class),
                Triple(accepting_activity, rdf_type, prov_activity),
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
                Triple(
                    new_statement, NamedNode(PACO_PREDICATE), NamedNode(old_predicate)
                ),
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
            ]
        )

        if confidence_score is not None:
            curation_triples.append(
                Triple(
                    new_statement,
                    NamedNode(PACO_CONFIDENCE),
                    Literal(confidence_score, datatype=NamedNode(XSD_FLOAT)),
                )
            )

        if text_span_start is not None and text_span_end is not None:
            curation_triples.append(
                Triple(
                    new_statement,
                    NamedNode(PACO_TEXT_SPAN_START),
                    Literal(text_span_start, datatype=NamedNode(XSD_INTEGER)),
                )
            )
            curation_triples.append(
                Triple(
                    new_statement,
                    NamedNode(PACO_TEXT_SPAN_END),
                    Literal(text_span_end, datatype=NamedNode(XSD_INTEGER)),
                )
            )

        data_triples.append(
            Triple(NamedNode(old_subject), NamedNode(old_predicate), object_node)
        )

    curation_triples_text = serialize(
        curation_triples, format=RdfFormat.N_TRIPLES
    ).decode("utf-8")
    data_triples_text = serialize(data_triples, format=RdfFormat.N_TRIPLES).decode(
        "utf-8"
    )
    not_current_values_clause = " ".join(f"<{stmt_id}>" for stmt_id in stmt_ids)

    # make the old statements not-current, write
    # the new accepted statements + provenance to the curation graph, and write
    # their bare subject/predicate/object triples to the accepted data graph.
    sparql_update(f"""
        DELETE {{
            GRAPH <{graph}> {{ ?stmt <{PACO_CURRENT}> true }}
        }}
        INSERT {{
            GRAPH <{graph}> {{ ?stmt <{PACO_CURRENT}> false }}
        }}
        WHERE {{
            GRAPH <{graph}> {{
                VALUES ?stmt {{ {not_current_values_clause} }}
                ?stmt <{PACO_CURRENT}> true .
            }}
        }} ;
        INSERT DATA {{
            GRAPH <{graph}> {{
                {curation_triples_text}
            }}
        }} ;
        INSERT DATA {{
            GRAPH <{accepted_graph}> {{
                {data_triples_text}
            }}
        }}
    """)

    return new_ids


def reject_statement(stmt_id: str, triggered_by: uuid.UUID, workspace_id: str) -> str:
    graph = curation_graph(workspace_id)
    accepted_graph = data_graph(workspace_id)

    # Load the candidate statement

    candidate_statement = load_candidate_statement(stmt_id, graph)

    # Check that the statement is the current version
    if (
        candidate_statement["is_current"] is None
        or candidate_statement["is_current"].lower() != "true"
    ):
        raise ValueError(f"Statement {stmt_id} is not the current version")

    old_subject = candidate_statement["subject"]
    old_predicate = candidate_statement["predicate"]
    object_node = candidate_statement["object_node"]
    confidence_score = candidate_statement["confidence_score"]
    text_span_start = candidate_statement["text_span_start"]
    text_span_end = candidate_statement["text_span_end"]

    # Remove persisted triple if already accepted
    if candidate_statement["status"] == PACO_ACCEPTED:
        current_data_triple = Triple(
            NamedNode(old_subject),
            NamedNode(old_predicate),
            object_node,
        )
        current_data_triple_text = serialize(
            [current_data_triple],
            format=RdfFormat.N_TRIPLES,
        ).decode("utf-8")

        sparql_update(f"""
            DELETE DATA {{
                GRAPH <{accepted_graph}> {{
                    {current_data_triple_text}
                }}
            }}
            """)

    # Get the current timestamp in ISO 8601 format with UTC timezone

    rejected_at = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    created_at = rejected_at

    rejecting_activity_id = f"{REJECT_ACTIVITIES}{uuid4()}"

    rejected_statement_id = f"{CANDIDATE_STATEMENTS}{uuid4()}"

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

    curator = curator_node(triggered_by)
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
        ]
    )

    if confidence_score is not None:
        triples.append(
            Triple(
                new_statement,
                NamedNode(PACO_CONFIDENCE),
                Literal(confidence_score, datatype=NamedNode(XSD_FLOAT)),
            )
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

    return rejected_statement_id


def edit_statement(
    stmt_id: str,
    triggered_by: uuid.UUID,
    workspace_id: str,
    edit: StatementEdit,
) -> str:
    graph = curation_graph(workspace_id)
    accepted_graph = data_graph(workspace_id)

    # Check that either object_iri or object_value is provided, but not both

    if edit.object_iri is not None and edit.object_value is not None:
        raise ValueError("Use either object_iri or object_value, not both")

    # Load the candidate statement

    candidate_statement = load_candidate_statement(stmt_id, graph)

    # Check that the statement is the current version
    if (
        candidate_statement["is_current"] is None
        or candidate_statement["is_current"].lower() != "true"
    ):
        raise ValueError(f"Statement {stmt_id} is not the current version")

    old_subject = candidate_statement["subject"]
    old_predicate = candidate_statement["predicate"]
    old_status = candidate_statement["status"]
    object_node = candidate_statement["object_node"]
    confidence_score = candidate_statement["confidence_score"]
    text_span_start = candidate_statement["text_span_start"]
    text_span_end = candidate_statement["text_span_end"]

    # Remove persisted triple if accepted
    if candidate_statement["status"] == PACO_ACCEPTED:
        current_data_triple = Triple(
            NamedNode(old_subject),
            NamedNode(old_predicate),
            object_node,
        )

        current_data_triple_text = serialize(
            [current_data_triple],
            format=RdfFormat.N_TRIPLES,
        ).decode("utf-8")

        sparql_update(f"""
            DELETE DATA {{
                GRAPH <{accepted_graph}> {{
                    {current_data_triple_text}
                }}
            }}
            """)

    new_subject = edit.subject or old_subject
    new_predicate = edit.predicate or old_predicate

    # Determine the new object node based on the provided edit

    if edit.object_iri is not None:
        new_object = NamedNode(edit.object_iri)
    elif edit.object_value is not None:
        if isinstance(object_node, NamedNode):
            raise ValueError(
                f"This statement requires a URI object. Use object_iri instead of object_value."
            )
        new_object = Literal(edit.object_value)
    else:
        new_object = object_node

    # Check whether subject, predicate, or object has changed; if not, raise an error

    no_subject_change = edit.subject is None or edit.subject == old_subject
    no_predicate_change = edit.predicate is None or edit.predicate == old_predicate
    no_object_change = (
        edit.object_iri is None and edit.object_value is None
    ) or new_object == object_node

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

    editing_activity_id = f"{EDIT_ACTIVITIES}{uuid4()}"

    edited_statement_id = f"{CANDIDATE_STATEMENTS}{uuid4()}"

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

    curator = curator_node(triggered_by)
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
            Triple(new_statement, NamedNode(PACO_STATUS), Literal(old_status)),
            Triple(new_statement, NamedNode(PACO_CURRENT), Literal(True)),
            Triple(
                new_statement,
                NamedNode(PACO_CREATED_AT),
                Literal(created_at, datatype=NamedNode(XSD_DATETIME)),
            ),
            Triple(new_statement, NamedNode(PACO_ORIGIN), curator),
            Triple(new_statement, NamedNode(PROV_GENERATED_BY), editing_activity),
            Triple(new_statement, NamedNode(PROV_DERIVED_FROM), NamedNode(stmt_id)),
        ]
    )

    if confidence_score is not None:
        triples.append(
            Triple(
                new_statement,
                NamedNode(PACO_CONFIDENCE),
                Literal(confidence_score, datatype=NamedNode(XSD_FLOAT)),
            )
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

    return edited_statement_id


def reset_statement(
    stmt_id: str,
    triggered_by: uuid.UUID,
    workspace_id: str,
) -> StatementResponse:
    graph = curation_graph(workspace_id)
    accepted_graph = data_graph(workspace_id)

    # Load the current candidate statement and verify that it is current.
    current_statement = load_candidate_statement(stmt_id, graph)

    if not current_statement["is_current"] == "true":
        raise ValueError("Only the current statement version can be reset")

    # Find and load the original candidate statement.
    original_stmt_id = find_original_candidate_statement(stmt_id, graph)
    original_statement = load_candidate_statement(original_stmt_id, graph)
    if original_statement["is_current"] == "true":
        raise ValueError("The original statement is already the current version")

    original_subject = original_statement["subject"]
    original_predicate = original_statement["predicate"]
    original_object_node = original_statement["object_node"]
    original_confidence_score = original_statement["confidence_score"]
    original_text_span_start = original_statement["text_span_start"]
    original_text_span_end = original_statement["text_span_end"]

    # If the current version is accepted, remove its materialized triple.
    if current_statement["status"] == PACO_ACCEPTED:
        current_data_triple = Triple(
            NamedNode(current_statement["subject"]),
            NamedNode(current_statement["predicate"]),
            current_statement["object_node"],
        )

        current_data_triple_text = serialize(
            [current_data_triple],
            format=RdfFormat.N_TRIPLES,
        ).decode("utf-8")

        sparql_update(f"""
            DELETE DATA {{
                GRAPH <{accepted_graph}> {{
                    {current_data_triple_text}
                }}
            }}
            """)

    # Mark the current version as no longer current.
    set_to_not_current(stmt_id, graph)

    reset_at = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    created_at = reset_at

    resetting_activity_id = f"{RESET_ACTIVITIES}{uuid4()}"

    reset_statement_id = f"{CANDIDATE_STATEMENTS}{uuid4()}"

    rdf_type = NamedNode(RDF_TYPE)

    new_statement = NamedNode(reset_statement_id)
    resetting_activity = NamedNode(resetting_activity_id)

    candidate_class = NamedNode(PACO_CANDIDATE)
    resetting_activity_class = NamedNode(PACO_RESETTING_ACTIVITY)

    prov_entity = NamedNode(PROV_ENTITY)
    prov_activity = NamedNode(PROV_ACTIVITY)
    prov_agent = NamedNode(PROV_AGENT)

    curator = curator_node(triggered_by)
    curator_class = NamedNode(PACO_CURATOR)

    triples = [
        Triple(resetting_activity, rdf_type, resetting_activity_class),
        Triple(resetting_activity, rdf_type, prov_activity),
        Triple(curator, rdf_type, curator_class),
        Triple(curator, rdf_type, prov_agent),
        Triple(
            resetting_activity,
            NamedNode(PROV_ASSOCIATED_WITH),
            curator,
        ),
        Triple(
            resetting_activity,
            NamedNode(PROV_USED),
            NamedNode(stmt_id),
        ),
        Triple(
            resetting_activity,
            NamedNode(PACO_RESET_AT),
            Literal(reset_at, datatype=NamedNode(XSD_DATETIME)),
        ),
        Triple(new_statement, rdf_type, candidate_class),
        Triple(new_statement, rdf_type, prov_entity),
        Triple(
            new_statement,
            NamedNode(PACO_SUBJECT),
            NamedNode(original_subject),
        ),
        Triple(
            new_statement,
            NamedNode(PACO_PREDICATE),
            NamedNode(original_predicate),
        ),
        Triple(
            new_statement,
            NamedNode(PACO_OBJECT),
            original_object_node,
        ),
        Triple(
            new_statement,
            NamedNode(PACO_STATUS),
            NamedNode(PACO_PENDING),
        ),
        Triple(
            new_statement,
            NamedNode(PACO_CURRENT),
            Literal(True),
        ),
        Triple(
            new_statement,
            NamedNode(PACO_CREATED_AT),
            Literal(created_at, datatype=NamedNode(XSD_DATETIME)),
        ),
        Triple(
            new_statement,
            NamedNode(PACO_ORIGIN),
            curator,
        ),
        Triple(
            new_statement,
            NamedNode(PROV_GENERATED_BY),
            resetting_activity,
        ),
        Triple(
            new_statement,
            NamedNode(PROV_DERIVED_FROM),
            NamedNode(stmt_id),
        ),
    ]

    if original_confidence_score is not None:
        triples.append(
            Triple(
                new_statement,
                NamedNode(PACO_CONFIDENCE),
                Literal(original_confidence_score),
            )
        )

    if original_text_span_start is not None and original_text_span_end is not None:
        triples.extend(
            [
                Triple(
                    new_statement,
                    NamedNode(PACO_TEXT_SPAN_START),
                    Literal(
                        original_text_span_start,
                        datatype=NamedNode(XSD_INTEGER),
                    ),
                ),
                Triple(
                    new_statement,
                    NamedNode(PACO_TEXT_SPAN_END),
                    Literal(
                        original_text_span_end,
                        datatype=NamedNode(XSD_INTEGER),
                    ),
                ),
            ]
        )

    triples_text = serialize(
        triples,
        format=RdfFormat.N_TRIPLES,
    ).decode("utf-8")

    sparql_update(f"""
        INSERT DATA {{
            GRAPH <{graph}> {{
                {triples_text}
            }}
        }}
        """)

    if isinstance(original_object_node, NamedNode):
        object = original_object_node.value
    elif isinstance(original_object_node, Literal):
        object = original_object_node.value

    return StatementResponse(
        id=reset_statement_id,
        subject=original_subject,
        predicate=original_predicate,
        object=object,
        object_is_uri=isinstance(original_object_node, NamedNode),
        confidence=original_confidence_score,
        text_span_start=original_text_span_start,
        text_span_end=original_text_span_end,
        curation_status=PACO_PENDING,
        origin=curator.value,
        created_at=created_at,
    )
