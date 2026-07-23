import hashlib
import time
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, File, Query, Request, UploadFile
from pydantic import BaseModel, WithJsonSchema
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_session
from app.core.exceptions import BadRequestException, NotFoundException
from app.core.limiter import limiter
from app.deps import get_current_user, require_role
from app.models.user import User
from app.repositories.document import DocumentRepository
from app.repositories.run import RunRepository
from app.repositories.workspace import WorkspaceRepository
from app.schemas.run import RunDetailResponse
from app.store.client import curation_graph, sparql_select
from app.store.utils import *
from app.tasks import build_pipeline

router = APIRouter(
    prefix="/extraction", tags=["extraction"], dependencies=[Depends(get_current_user)]
)


def candidate_records_from_rows(rows: list[tuple[str, str, str]]) -> list[dict]:
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
                "confidence": first(PACO_CONFIDENCE),
                "text_span": first(PACO_TEXT_SPAN),
                "text_span_start": first(PACO_TEXT_SPAN_START),
                "text_span_end": first(PACO_TEXT_SPAN_END),
            }
        )

    return records


def derive_run_status(task_statuses: list[str]) -> str:
    """Compute overall run status from individual task statuses."""
    status = {"extracting", "converting", "aligning", "waiting"}
    if not task_statuses:
        return "queued"
    if any(s in status for s in task_statuses):
        return "running"
    if any(s == "failed" for s in task_statuses):
        return "failed"
    if all(s == "done" for s in task_statuses):
        return "completed"
    return "queued"


UploadFileType = Annotated[
    UploadFile, WithJsonSchema({"type": "string", "format": "binary"})
]  # fixes OpenAPI schema on swagger page


class GetRunsResponse(BaseModel):
    id: UUID
    run_id: UUID
    document_id: UUID | None
    status: str
    task_name: str


@router.get("/{workspace_id}", status_code=200, response_model=list[GetRunsResponse])
async def get_runs(workspace_id: UUID, session: AsyncSession = Depends(get_session)):
    run_repo = RunRepository(session)
    return await run_repo.list(workspace_id)


@router.post(
    "/", status_code=202, dependencies=[Depends(require_role("owner", "editor"))]
)
@limiter.limit("5/hour")
async def create_documents(
    request: Request,
    files: list[UploadFileType] = File(...),
    workspace_id: UUID = Query(...),
    session: AsyncSession = Depends(get_session),
    current_user: User = Depends(get_current_user),
):
    run_repo = RunRepository(session)
    doc_repo = DocumentRepository(session)
    workspace_repo = WorkspaceRepository(session)
    workspace = await workspace_repo.get_by_id(workspace_id)
    if not workspace:
        raise NotFoundException(f"Workspace {workspace_id} not found")
    model = "gpt-oss-120b"

    # Create hashes to ensure files have not been uploaded yet
    file_payloads = []
    for file in files:
        filename = file.filename or str(time.time())
        content = await file.read()
        content_hash = hashlib.sha256(content).hexdigest()

        existing = await doc_repo.get_by_hash(workspace_id, content_hash)
        if existing:
            raise BadRequestException(
                f"'{filename}' has already been uploaded to this workspace"
            )
        file_payloads.append((filename, content, content_hash))
    run = await run_repo.create(
        workspace_id=workspace_id, triggered_by=current_user.id, model=model
    )
    documents = []
    for filename, content, content_hash in file_payloads:
        if filename.lower().endswith(".pdf"):
            # pass raw bytes for PDFs
            doc = await doc_repo.create_pdf(
                workspace_id=workspace_id,
                filename=filename,
                raw_bytes=content,
                content_hash=content_hash,
            )
            await run_repo.add_task(run.id, doc.id, task_name="Markdown Conversion")
        elif filename.lower().endswith(".md") or filename.lower().endswith(".txt"):
            # UploadFile.read() returns bytes -> decode to text for source_content
            text = content.decode("utf-8", errors="replace")
            doc = await doc_repo.create_markdown(
                workspace_id=workspace_id,
                filename=filename,
                source_content=text,
                content_hash=content_hash,
            )
            await run_repo.add_task(run.id, doc.id, task_name="Extracting")
        else:
            raise BadRequestException(f"Unsupported file type: {filename}")
        documents.append({"document_id": str(doc.id), "file_type": doc.file_type})
    build_pipeline(documents, model, str(run.id), str(workspace_id)).delay()
    return {"run_id": run.id, "status": "queued"}


@router.get(
    "/{run_id}",
    response_model=RunDetailResponse,
    dependencies=[Depends(require_role("owner", "editor"))],
)
async def get_run(run_id: UUID, session: AsyncSession = Depends(get_session)):
    run_repo = RunRepository(session)
    run = await run_repo.get_by_id(run_id)
    if run is None:
        raise NotFoundException(f"Run {run_id} not found")
    tasks = await run_repo.get_tasks_by_run(run_id)
    return RunDetailResponse(
        id=run.id,
        status=derive_run_status([t.status for t in tasks]),
        model=run.model,
        created_at=run.created_at,
        updated_at=run.updated_at,
        documents=[
            {
                "document_id": t.document_id,
                "status": t.status,
                "task_name": t.task_name,
                "celery_task_id": t.celery_task_id,
            }
            for t in tasks
        ],
    )


@router.get("/{run_id}/statements")
async def get_run_statements(
    run_id: UUID, session: AsyncSession = Depends(get_session)
):
    run_repo = RunRepository(session)
    run = await run_repo.get_by_id(run_id)
    if run is None:
        return {"run_id": run_id, "statements": []}

    graph = curation_graph(str(run.workspace_id))

    payload = sparql_select(f"""
        SELECT ?s ?p ?o WHERE {{
            GRAPH <{graph}> {{ ?s ?p ?o }}
        }}
        ORDER BY ?s ?p ?o
    """)

    rows = [
        (b["s"]["value"], b["p"]["value"], b["o"]["value"])
        for b in payload.get("results", {}).get("bindings", [])
    ]

    return {
        "run_id": run_id,
        "workspace_id": run.workspace_id,
        "graph": graph,
        "statements": candidate_records_from_rows(rows),
    }


@router.post(
    "/{run_id}/statements/bulk_accept",
    status_code=202,
    dependencies=[Depends(require_role("owner", "editor"))],
)
async def bulk_accept_statements():
    pass


@router.get("/{run_id}/alignments")
async def get_run_alignments(
    run_id: UUID, session: AsyncSession = Depends(get_session)
):
    """Return all owl:sameAs CandidateStatements produced by inner-document alignment for a run."""
    run_repo = RunRepository(session)
    run = await run_repo.get_by_id(run_id)
    if run is None:
        raise NotFoundException(f"Run {run_id} not found")

    graph = curation_graph(str(run.workspace_id))
    paco = PACO
    owl_same_as = "http://www.w3.org/2002/07/owl#sameAs"

    payload = sparql_select(f"""
        SELECT ?stmt ?duplicate ?canonical ?confidence ?status WHERE {{
            GRAPH <{graph}> {{
                ?stmt <{paco}predicate> <{owl_same_as}> ;
                      <{paco}subject>   ?duplicate ;
                      <{paco}object>    ?canonical ;
                      <{paco}curationStatus> ?status .
                OPTIONAL {{ ?stmt <{paco}confidence> ?confidence . }}
            }}
        }}
        ORDER BY ?canonical ?duplicate
    """)

    alignments = [
        {
            "statement_id": b["stmt"]["value"],
            "duplicate": b["duplicate"]["value"],
            "canonical": b["canonical"]["value"],
            "confidence": (
                float(b["confidence"]["value"]) if "confidence" in b else None
            ),
            "status": b["status"]["value"].split("/")[-1],
        }
        for b in payload.get("results", {}).get("bindings", [])
    ]

    return {
        "run_id": run_id,
        "workspace_id": run.workspace_id,
        "count": len(alignments),
        "alignments": alignments,
    }


@router.get("/{run_id}/entities")
async def get_run_entities():
    pass


@router.get("/{run_id}/entities/{entity_uri:path}/statements")
async def get_run_entity_statements():
    pass
