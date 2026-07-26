import hashlib
import time
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, File, Query, Request, UploadFile
from pydantic import BaseModel, WithJsonSchema
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_session
from app.core.exceptions import (
    BadRequestException,
    ForbiddenException,
    NotFoundException,
)
from app.core.limiter import limiter
from app.deps import get_current_user, require_role
from app.models.user import User
from app.repositories.document import DocumentRepository
from app.repositories.run import RunRepository
from app.repositories.workspace import WorkspaceMemberRepository, WorkspaceRepository
from app.store.writer import delete_document_data
from app.tasks import build_pipeline, build_retry_pipeline

router = APIRouter(
    prefix="/extraction", tags=["extraction"], dependencies=[Depends(get_current_user)]
)


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
            await run_repo.add_task(run.id, doc.id, task_name="Conversion")
        elif filename.lower().endswith(".md") or filename.lower().endswith(".txt"):
            # UploadFile.read() returns bytes -> decode to text for source_content
            text = content.decode("utf-8", errors="replace")
            doc = await doc_repo.create_markdown(
                workspace_id=workspace_id,
                filename=filename,
                source_content=text,
                content_hash=content_hash,
            )
            await run_repo.add_task(run.id, doc.id, task_name="Extraction")
        else:
            raise BadRequestException(f"Unsupported file type: {filename}")
        documents.append({"document_id": str(doc.id), "file_type": doc.file_type})
    build_pipeline(documents, model, str(run.id), str(workspace_id)).delay()
    return {"run_id": run.id, "status": "queued"}


@router.post(
    "/{run_id}/documents/{document_id}/retry",
    status_code=202,
)
async def retry_document(
    run_id: UUID,
    document_id: UUID,
    session: AsyncSession = Depends(get_session),
    current_user: User = Depends(get_current_user),
):
    run_repo = RunRepository(session)
    run = await run_repo.get_by_id(run_id)
    if run is None:
        raise NotFoundException(f"Run {run_id} not found")
    role = await WorkspaceMemberRepository(session).get_role(
        run.workspace_id, current_user.id
    )
    if role not in ("owner", "editor"):
        raise ForbiddenException(
            "You do not have permission to resubmit this document for extraction."
        )

    task = await run_repo.get_task(run.id, document_id)
    if task is None:
        raise NotFoundException(f"Document {document_id} not found in run {run.id}")
    if task.status != "Failed":
        raise BadRequestException(f"Document {document_id} is not in a failed state")

    doc = await DocumentRepository(session).get_by_id(document_id)
    if doc is None:
        raise NotFoundException(f"Document {document_id} not found")

    # remove all triples associated with this document (i.e. extraction triples if failed during alignment for example)
    delete_document_data(str(run.workspace_id), str(document_id))

    task_name = "Conversion" if doc.file_type == "pdf" else "Extraction"
    await run_repo.reset_document_for_retry(run.id, document_id, task_name)

    build_retry_pipeline(
        str(document_id), doc.file_type, str(run.id), str(run.workspace_id)
    ).delay()
    return {"status": "queued"}
