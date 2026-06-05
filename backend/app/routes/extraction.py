import time
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, File, Query, UploadFile
from pydantic import WithJsonSchema
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_session
from app.repositories.document import DocumentRepository
from app.repositories.run import RunRepository
from app.repositories.workspace import WorkspaceRepository
from app.store.client import curation_graph, sparql_select
from app.tasks import build_pipeline

router = APIRouter(prefix="/extraction", tags=["extraction"])

PACO = "https://example.org/provenance-and-curation-ontology/"
PROV = "http://www.w3.org/ns/prov#"
RDF = "http://www.w3.org/1999/02/22-rdf-syntax-ns#"
RDF_TYPE = f"{RDF}type"
PACO_CANDIDATE = f"{PACO}CandidateStatement"
PACO_SUBJECT = f"{PACO}subject"
PACO_PREDICATE = f"{PACO}predicate"
PACO_OBJECT = f"{PACO}object"
PACO_ORIGIN = f"{PACO}origin"
PACO_STATUS = f"{PACO}curationStatus"
PACO_CREATED_AT = f"{PACO}createdAt"
PACO_CURRENT = f"{PACO}isCurrentVersion"
PROV_GENERATED_BY = f"{PROV}wasGeneratedBy"
PROV_DERIVED_FROM = f"{PROV}wasDerivedFrom"


def _candidate_records_from_rows(rows: list[tuple[str, str, str]]) -> list[dict]:
    grouped: dict[str, dict[str, list[str]]] = {}
    for subject, predicate, obj in rows:
        grouped.setdefault(subject, {}).setdefault(predicate, []).append(obj)

    records: list[dict] = []
    for subject, props in grouped.items():
        if PACO_CANDIDATE not in props.get(RDF_TYPE, []):
            continue

        def first(key: str) -> str | None:
            values = props.get(key, [])
            return values[0] if values else None

        records.append(
            {
                "id": subject,
                "subject": first(PACO_SUBJECT),
                "predicate": first(PACO_PREDICATE),
                "object": first(PACO_OBJECT),
                "origin": first(PACO_ORIGIN),
                "curation_status": first(PACO_STATUS),
                "created_at": first(PACO_CREATED_AT),
                "is_current_version": first(PACO_CURRENT),
                "generated_by": first(PROV_GENERATED_BY),
                "derived_from": first(PROV_DERIVED_FROM),
            }
        )

    return records


UploadFileType = Annotated[
    UploadFile, WithJsonSchema({"type": "string", "format": "binary"})
]


@router.post("/", status_code=202)
async def create_documents(
    files: list[UploadFileType] = File(...),
    workspace_id: UUID = Query(...),
    session: AsyncSession = Depends(get_session),
):
    triggered_by = None  # will be replaced by user
    run_repo = RunRepository(session)
    doc_repo = DocumentRepository(session)
    workspace_repo = WorkspaceRepository(session)
    workspace = await workspace_repo.get_by_id(workspace_id)
    if not workspace:
        workspace = await workspace_repo.create_with_id(
            name="Default Workspace", workspace_id=workspace_id
        )
    model = "gpt-oss-120b"

    run = await run_repo.create(
        workspace_id=workspace_id, triggered_by=triggered_by, model=model
    )
    documents = []
    for file in files:
        filename = file.filename or str(time.time())
        content = await file.read()
        if filename.lower().endswith(".pdf"):
            # pass raw bytes for PDFs
            doc = await doc_repo.create_pdf(
                workspace_id=workspace_id, filename=filename, raw_bytes=content
            )
            await run_repo.add_task(run.id, doc.id, task_name="Markdown Conversion")
        else:
            # UploadFile.read() returns bytes -> decode to text for source_content
            text = content.decode("utf-8", errors="replace")
            doc = await doc_repo.create_markdown(
                workspace_id=workspace_id, filename=filename, source_content=text
            )
            await run_repo.add_task(run.id, doc.id, task_name="Extracting")
        documents.append({"document_id": str(doc.id), "file_type": doc.file_type})
    build_pipeline(documents, str(run.id)).delay()
    return {"run_id": run.id, "status": "queued"}


@router.get("/{run_id}")
async def get_run():
    pass


@router.get("/{run_id}/statements")
async def get_run_statements(
    run_id: UUID, session: AsyncSession = Depends(get_session)
):
    run_repo = RunRepository(session)
    run = await run_repo.get_by_id(run_id)
    if run is None:
        return {"run_id": run_id, "statements": []}

    graph = curation_graph(str(run.workspace_id))

    payload = sparql_select(
        f"""
        SELECT ?s ?p ?o WHERE {{
            GRAPH <{graph}> {{ ?s ?p ?o }}
        }}
        ORDER BY ?s ?p ?o
    """
    )

    rows = [
        (b["s"]["value"], b["p"]["value"], b["o"]["value"])
        for b in payload.get("results", {}).get("bindings", [])
    ]

    return {
        "run_id": run_id,
        "workspace_id": run.workspace_id,
        "graph": graph,
        "statements": _candidate_records_from_rows(rows),
    }


@router.post("/{run_id}/statements/bulk_accept", status_code=202)
async def bulk_accept_statements():
    pass


@router.post("/{run_id}/statements/{statement_id:path}/accept", status_code=200)
async def accept_statement():
    pass


@router.post("/{run_id}/statements/{statement_id:path}/reject", status_code=200)
async def reject_statement():
    pass


@router.patch("/{run_id}/statements/{statement_id:path}", status_code=200)
async def edit_statement():
    pass


@router.get("/{run_id}/entities")
async def get_run_entities():
    pass


@router.get("/{run_id}/entities/{entity_uri:path}/statements")
async def get_run_entity_statements():
    pass
