from datetime import datetime, timezone
from hashlib import sha256
from pathlib import Path
from typing import Union

from app.store.client import curation_graph, sparql_update


def write_candidate_statements(statements: list[dict], workspace_id: str) -> None:
    """Write structured candidate statements (JSON-like) into the curation graph.

    This is a placeholder helper for future structured writes. For now it
    simply returns without action.
    """
    return None


def _build_candidate_statement_triples(
    *,
    parsed_quads,
    workspace_id: str,
    run_id: str | None,
    document_id: str | None,
):
    from pyoxigraph import Literal, NamedNode, Triple

    paco = "https://example.org/provenance-and-curation-ontology/"
    prov = "http://www.w3.org/ns/prov#"
    rdf = "http://www.w3.org/1999/02/22-rdf-syntax-ns#"
    xsd = "http://www.w3.org/2001/XMLSchema#"

    now = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    run_key = run_id or "unknown-run"
    document_key = document_id or "unknown-document"
    workspace_key = workspace_id or "unknown-workspace"

    source_document = NamedNode(
        f"https://ontocurate.org/workspaces/{workspace_key}/documents/{document_key}"
    )
    extraction_activity = NamedNode(
        f"https://ontocurate.org/runs/{run_key}/documents/{document_key}/activities/extraction"
    )
    ontogpt_agent = NamedNode(f"{paco}ontogpt")
    candidate_class = NamedNode(f"{paco}CandidateStatement")
    source_document_class = NamedNode(f"{paco}SourceDocument")
    extraction_class = NamedNode(f"{paco}ExtractionActivity")
    prov_entity = NamedNode(f"{prov}Entity")
    prov_activity = NamedNode(f"{prov}Activity")
    rdf_type = NamedNode(f"{rdf}type")
    prov_used = NamedNode(f"{prov}used")
    prov_generated_by = NamedNode(f"{prov}wasGeneratedBy")
    prov_associated_with = NamedNode(f"{prov}wasAssociatedWith")
    prov_derived_from = NamedNode(f"{prov}wasDerivedFrom")
    paco_subject = NamedNode(f"{paco}subject")
    paco_predicate = NamedNode(f"{paco}predicate")
    paco_object = NamedNode(f"{paco}object")
    paco_origin = NamedNode(f"{paco}origin")
    paco_status = NamedNode(f"{paco}curationStatus")
    paco_pending = NamedNode(f"{paco}pending")
    paco_created_at = NamedNode(f"{paco}createdAt")
    paco_extracted_at = NamedNode(f"{paco}extractedAt")
    paco_current = NamedNode(f"{paco}isCurrentVersion")

    triples = [
        Triple(source_document, rdf_type, source_document_class),
        Triple(source_document, rdf_type, prov_entity),
        Triple(extraction_activity, rdf_type, extraction_class),
        Triple(extraction_activity, rdf_type, prov_activity),
        Triple(extraction_activity, prov_used, source_document),
        Triple(extraction_activity, prov_associated_with, ontogpt_agent),
        Triple(extraction_activity, paco_extracted_at, Literal(now, datatype=NamedNode(f"{xsd}dateTime"))),
    ]

    for index, quad in enumerate(parsed_quads):
        fingerprint = sha256(
            f"{workspace_key}|{run_key}|{document_key}|{index}|{quad.subject}|{quad.predicate}|{quad.object}".encode(
                "utf-8"
            )
        ).hexdigest()[:24]
        candidate = NamedNode(
            f"https://ontocurate.org/workspaces/{workspace_key}/candidate-statements/{fingerprint}"
        )
        triples.extend(
            [
                Triple(candidate, rdf_type, candidate_class),
                Triple(candidate, rdf_type, prov_entity),
                Triple(candidate, paco_subject, quad.subject),
                Triple(candidate, paco_predicate, quad.predicate),
                Triple(candidate, paco_object, quad.object),
                Triple(candidate, paco_origin, ontogpt_agent),
                Triple(candidate, paco_status, paco_pending),
                Triple(candidate, paco_created_at, Literal(now, datatype=NamedNode(f"{xsd}dateTime"))),
                Triple(candidate, paco_current, Literal(True)),
                Triple(candidate, prov_generated_by, extraction_activity),
                Triple(candidate, prov_derived_from, source_document),
            ]
        )

    return triples


def write_candidate_statements_from_ttl(
    run_id: Union[str, None], document_id: Union[str, None], ttl_path: Union[str, Path], workspace_id: str
) -> None:
    """Load Turtle file into the workspace curation graph.

    - `ttl_path` may be a Path or string path to a Turtle file produced by
      the extraction pipeline.
    - Writes all triples into the named curation graph for the workspace.
    """
    graph = curation_graph(workspace_id)
    ttl_text = Path(ttl_path).read_text(encoding="utf-8")

    try:
        from pyoxigraph import RdfFormat, parse, serialize
    except Exception as exc:
        raise RuntimeError(f"pyoxigraph parsing is unavailable; cannot import candidate statements: {exc}")

    try:
        parsed_quads = list(parse(input=ttl_text, format=RdfFormat.TURTLE))
    except Exception as exc:
        raise RuntimeError(f"Failed to parse Turtle for candidate-statement import: {exc}")

    triples = _build_candidate_statement_triples(
        parsed_quads=parsed_quads,
        workspace_id=workspace_id,
        run_id=run_id,
        document_id=document_id,
    )

    triples_text = serialize(triples, format=RdfFormat.N_TRIPLES).decode("utf-8")
    sparql_update(f"INSERT DATA {{ GRAPH <{graph}> {{\n{triples_text}\n}} }}")


def accept_statement(stmt_id: str, curator_id: str, workspace_id: str) -> None:
    pass


def reject_statement(stmt_id: str, curator_id: str, workspace_id: str) -> None:
    pass
