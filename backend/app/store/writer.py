import json
from datetime import datetime, timezone
from hashlib import sha256
from pathlib import Path
from typing import Union

from app.store.client import curation_graph, sparql_update


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
        (ann["subject"], ann["predicate"], ann["value"]): ann
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
    from pyoxigraph import Literal, NamedNode, Triple

    paco = "https://example.org/provenance-and-curation-ontology/"
    prov = "http://www.w3.org/ns/prov#"
    rdf = "http://www.w3.org/1999/02/22-rdf-syntax-ns#"
    xsd = "http://www.w3.org/2001/XMLSchema#"
    schema = "https://schema.org/"

    now = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    run_key = run_id or "unknown-run"
    document_key = (
        document_id or "unknown-document"
    )  # Currently only link to sql db entry, consider adding full document entity later
    workspace_key = workspace_id or "unknown-workspace"

    # Define general nodes
    rdf_type = NamedNode(f"{rdf}type")
    schema_name = NamedNode(f"{schema}name")
    # Define ontogpt agent
    ontogpt_agent = NamedNode(f"{paco}ontogpt-{model}")
    ontogpt_agent_name = Literal(f"{model}")
    prov_agent = NamedNode(f"{prov}SoftwareAgent")

    # Define source document
    source_document = NamedNode(
        f"https://example.org/workspaces/{workspace_key}/documents/{document_key}"
    )
    source_document_class = NamedNode(f"{paco}SourceDocument")
    prov_entity = NamedNode(f"{prov}Entity")

    # Define Candidate Statement
    candidate_class = NamedNode(f"{paco}CandidateStatement")
    paco_subject = NamedNode(f"{paco}subject")
    paco_predicate = NamedNode(f"{paco}predicate")
    paco_object = NamedNode(f"{paco}object")
    paco_origin = NamedNode(f"{paco}origin")
    paco_status = NamedNode(f"{paco}curationStatus")
    paco_text_span = NamedNode(f"{paco}textSpan")
    paco_text_span_start = NamedNode(f"{paco}textSpanStart")
    paco_text_span_end = NamedNode(f"{paco}textSpanEnd")
    paco_confidence = NamedNode(f"{paco}confidence")
    paco_pending = NamedNode(f"{paco}pending")
    paco_created_at = NamedNode(f"{paco}createdAt")
    paco_current = NamedNode(f"{paco}isCurrentVersion")

    # Define Extraction Activity
    extraction_activity = NamedNode(
        f"https://example.org/runs/{run_key}/documents/{document_key}/activities/extraction"
    )
    extraction_class = NamedNode(f"{paco}ExtractionActivity")
    prov_activity = NamedNode(f"{prov}Activity")
    prov_used = NamedNode(f"{prov}used")
    prov_generated = NamedNode(f"{prov}generated")
    prov_was_generated_by = NamedNode(f"{prov}wasGeneratedBy")
    prov_associated_with = NamedNode(f"{prov}wasAssociatedWith")
    prov_derived_from = NamedNode(f"{prov}wasDerivedFrom")
    paco_extracted_at = NamedNode(f"{paco}extractedAt")

    triples = [
        Triple(ontogpt_agent, rdf_type, prov_agent),
        Triple(ontogpt_agent, schema_name, ontogpt_agent_name),
        Triple(source_document, rdf_type, source_document_class),
        Triple(source_document, rdf_type, prov_entity),
        Triple(extraction_activity, rdf_type, extraction_class),
        Triple(extraction_activity, rdf_type, prov_activity),
        Triple(extraction_activity, prov_used, source_document),
        Triple(extraction_activity, prov_associated_with, ontogpt_agent),
        Triple(
            extraction_activity,
            paco_extracted_at,
            Literal(now, datatype=NamedNode(f"{xsd}dateTime")),
        ),
    ]

    index_lookup = provenance_index or {}
    rdf_type_uri = f"{rdf}type"

    for index, quad in enumerate(parsed_quads):
        if quad.predicate.value == rdf_type_uri:
            key = (
                quad.subject.value,
                "type",
                quad.object.value,
            )
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
            Triple(candidate, rdf_type, candidate_class),
            Triple(candidate, rdf_type, prov_entity),
            Triple(candidate, paco_subject, quad.subject),
            Triple(candidate, paco_predicate, quad.predicate),
            Triple(candidate, paco_object, quad.object),
            Triple(candidate, paco_origin, ontogpt_agent),
            Triple(candidate, paco_status, paco_pending),
            Triple(
                candidate,
                paco_created_at,
                Literal(now, datatype=NamedNode(f"{xsd}dateTime")),
            ),
            Triple(candidate, paco_current, Literal(True)),
            Triple(extraction_activity, prov_generated, candidate),
            Triple(candidate, prov_was_generated_by, extraction_activity),
            Triple(candidate, prov_derived_from, source_document),
        ]

        # Attach provenance annotation
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
                    paco_confidence,
                    Literal(str(ann["confidence"]), datatype=NamedNode(f"{xsd}float")),
                )
            )
            if isinstance(quad.object, Literal):
                candidate_triples.extend(
                    [
                        Triple(
                            candidate,
                            paco_text_span,
                            Literal(
                                ann["span_text"], datatype=NamedNode(f"{xsd}string")
                            ),
                        ),
                        Triple(
                            candidate,
                            paco_text_span_start,
                            Literal(
                                str(ann["span_start"]),
                                datatype=NamedNode(f"{xsd}integer"),
                            ),
                        ),
                        Triple(
                            candidate,
                            paco_text_span_end,
                            Literal(
                                str(ann["span_end"]),
                                datatype=NamedNode(f"{xsd}integer"),
                            ),
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
        from pyoxigraph import RdfFormat, parse, serialize
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
    pass


def reject_statement(stmt_id: str, curator_id: str, workspace_id: str) -> None:
    pass
