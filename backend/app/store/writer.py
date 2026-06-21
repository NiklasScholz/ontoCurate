import json
from datetime import datetime, timezone
from hashlib import sha256
from pathlib import Path
from typing import Union
from uuid import uuid4

from pyoxigraph import Literal, NamedNode, RdfFormat, Triple, serialize

from app.store.client import curation_graph, data_graph, sparql_select, sparql_update
from app.store.utils import (
    N_OWL_SAME_AS,
    N_PACO_ACCEPTED,
    N_PACO_ACCEPTED_AT,
    N_PACO_ACCEPTING_ACTIVITY,
    N_PACO_ALIGNMENT_ACTIVITY,
    N_PACO_CANDIDATE,
    N_PACO_CONFIDENCE,
    N_PACO_CREATED_AT,
    N_PACO_CURATOR,
    N_PACO_CURRENT,
    N_PACO_ENTITY_ALIGNMENT,
    N_PACO_EXTRACTED_AT,
    N_PACO_EXTRACTION_ACTIVITY,
    N_PACO_OBJECT,
    N_PACO_ONTOGPT,
    N_PACO_ORIGIN,
    N_PACO_PENDING,
    N_PACO_PREDICATE,
    N_PACO_SOURCE_DOCUMENT,
    N_PACO_STATUS,
    N_PACO_SUBJECT,
    N_PACO_TEXT_SPAN,
    N_PACO_TEXT_SPAN_END,
    N_PACO_TEXT_SPAN_START,
    N_PROV_ACTIVITY,
    N_PROV_AGENT,
    N_PROV_ASSOCIATED_WITH,
    N_PROV_DERIVED_FROM,
    N_PROV_ENTITY,
    N_PROV_GENERATED,
    N_PROV_GENERATED_BY,
    N_PROV_INFORMED_BY,
    N_PROV_SOFTWARE_AGENT,
    N_PROV_USED,
    N_RDF_TYPE,
    N_SCHEMA_NAME,
    N_XSD_DATETIME,
    N_XSD_FLOAT,
    N_XSD_INTEGER,
    N_XSD_STRING,
    PACO_CURRENT,
    PACO_OBJECT,
    PACO_PREDICATE,
    PACO_SUBJECT,
    create_source_document_entity,
)


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


def accept_statement(stmt_id: str, curator_id: str, workspace_id: str) -> None:
    graph = curation_graph(workspace_id)
    accepted_graph = data_graph(workspace_id)

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

    new_statement = NamedNode(accepted_statement_id)
    accepting_activity = NamedNode(accepting_activity_id)
    curator = NamedNode(curator_id)

    triples = [
        Triple(accepting_activity, N_RDF_TYPE, N_PACO_ACCEPTING_ACTIVITY),
        Triple(accepting_activity, N_RDF_TYPE, N_PROV_ACTIVITY),
        Triple(curator, N_RDF_TYPE, N_PACO_CURATOR),
        Triple(curator, N_RDF_TYPE, N_PROV_AGENT),
        Triple(accepting_activity, N_PROV_ASSOCIATED_WITH, curator),
        Triple(accepting_activity, N_PROV_USED, NamedNode(stmt_id)),
        Triple(
            accepting_activity,
            N_PACO_ACCEPTED_AT,
            Literal(accepted_at, datatype=N_XSD_DATETIME),
        ),
        Triple(new_statement, N_RDF_TYPE, N_PACO_CANDIDATE),
        Triple(new_statement, N_RDF_TYPE, N_PROV_ENTITY),
        Triple(new_statement, N_PACO_SUBJECT, NamedNode(old_subject)),
        Triple(new_statement, N_PACO_PREDICATE, NamedNode(old_predicate)),
        Triple(new_statement, N_PACO_OBJECT, NamedNode(old_object)),
        Triple(new_statement, N_PACO_STATUS, N_PACO_ACCEPTED),
        Triple(new_statement, N_PACO_CURRENT, Literal(True)),
        Triple(
            new_statement,
            N_PACO_CREATED_AT,
            Literal(created_at, datatype=N_XSD_DATETIME),
        ),
        Triple(new_statement, N_PACO_ORIGIN, curator),
        Triple(new_statement, N_PROV_GENERATED_BY, accepting_activity),
        Triple(new_statement, N_PROV_DERIVED_FROM, NamedNode(stmt_id)),
    ]

    triples_text = serialize(triples, format=RdfFormat.N_TRIPLES).decode("utf-8")

    sparql_update(f"""
        INSERT DATA {{
            GRAPH <{graph}> {{
                {triples_text}
            }}
        }}
    """)

    sparql_update(f"""
        INSERT DATA {{
            GRAPH <{accepted_graph}> {{
                <{old_subject}> <{old_predicate}> <{old_object}> .
            }}
        }}
    """)


def reject_statement(stmt_id: str, curator_id: str, workspace_id: str) -> None:
    pass


def write_alignment_results(
    alignments: list[tuple[str, str, float]],
    workspace_id: str,
    run_id: str | None = None,
    document_id: str | None = None,
) -> None:
    """Writes owl:sameAs CandidateStatements for proposed entity alignments."""
    if not alignments:
        return

    run_key = run_id or "unknown-run"
    doc_key = document_id or "unknown-document"
    now = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")

    alignment_activity = NamedNode(
        f"https://example.org/runs/{run_key}/documents/{doc_key}/activities/alignment"
    )
    extraction_activity = NamedNode(
        f"https://example.org/runs/{run_key}/documents/{doc_key}/activities/extraction"
    )

    triples = [
        Triple(N_PACO_ENTITY_ALIGNMENT, N_RDF_TYPE, N_PROV_SOFTWARE_AGENT),
        Triple(N_PACO_ENTITY_ALIGNMENT, N_SCHEMA_NAME, Literal("entity-alignment")),
        Triple(alignment_activity, N_RDF_TYPE, N_PACO_ALIGNMENT_ACTIVITY),
        Triple(alignment_activity, N_RDF_TYPE, N_PROV_ACTIVITY),
        Triple(alignment_activity, N_PROV_ASSOCIATED_WITH, N_PACO_ENTITY_ALIGNMENT),
        Triple(alignment_activity, N_PROV_INFORMED_BY, extraction_activity),
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
        candidate = NamedNode(
            f"https://example.org/workspaces/{workspace_id}/candidate-statements/{fingerprint}"
        )
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

    graph = curation_graph(workspace_id)
    triples_text = serialize(triples, format=RdfFormat.N_TRIPLES).decode("utf-8")
    sparql_update(f"INSERT DATA {{ GRAPH <{graph}> {{\n{triples_text}\n}} }}")
