from uuid import UUID

from fastapi import APIRouter, Depends
from fastapi.responses import FileResponse, StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_session
from app.core.exceptions import NotFoundException
from app.repositories.document import DocumentRepository
from app.schemas.document import DocumentResponse
from app.schemas.statement import StatementResponse

router = APIRouter(prefix="/documents", tags=["documents"])


@router.get("/", response_model=list[DocumentResponse])
async def list_documents(
    workspace_id: UUID, session: AsyncSession = Depends(get_session)
):
    return [
        # TODO: Return extracted/pending triples
        DocumentResponse(
            id=doc.id,
            filename=doc.filename,
            file_type=doc.file_type,
            title=doc.title,
            extracted_triples=0,
            pending_triples=0,
        )
        for doc in await DocumentRepository(session).list_by_workspace(workspace_id)
    ]


@router.get("/{document_id}", response_model=DocumentResponse)
async def get_document(document_id: UUID, session: AsyncSession = Depends(get_session)):
    doc = await DocumentRepository(session).get_by_id(document_id)
    if not doc:
        raise NotFoundException(f"Document {document_id} not found")
    return DocumentResponse(
        # TODO: Return extracted/pending triples
        id=doc.id,
        filename=doc.filename,
        file_type=doc.file_type,
        title=doc.title,
        extracted_triples=0,
        pending_triples=0,
    )


@router.get("/{document_id}/markdown", response_class=FileResponse)
async def get_document_markdown(document_id: UUID):
    # TODO
    return StreamingResponse(
        iter(["The content of the document"]),
        media_type="text/markdown",
        headers={"Content-Disposition": f"attachment; filename={document_id}.md"},
    )


@router.get("/{document_id}/pdf", response_class=FileResponse)
async def get_document_pdf(document_id: UUID):
    # TODO
    return StreamingResponse(
        iter(["The content of the document"]),
        media_type="application/pdf",
        headers={"Content-Disposition": f"attachment; filename={document_id}.pdf"},
    )


@router.delete("/{document_id}", status_code=204)
async def delete_document(
    document_id: UUID, session: AsyncSession = Depends(get_session)
):
    await DocumentRepository(session).delete(document_id)


@router.get("/{document_id}/statements", response_model=list[StatementResponse])
async def get_document_statements(
    document_id: UUID, session: AsyncSession = Depends(get_session)
):
    """
    Returns all statements associated entirely with the given document.

    The order of statements is as follows (coarsest to finest grouping):
    - Data type properties are listed before object properties.
    - Finally, sort triples lexicographically.

    owl:sameAs triples that connect entities from different documents are not listed.

    Pagination could be added in the future if performance is bad.
    """
    # TODO
    return []


@router.get("/{document_id}/export/provenance.ttl")
async def export_document_ttl(document_id: str, response_class=FileResponse):
    # TODO
    pass
