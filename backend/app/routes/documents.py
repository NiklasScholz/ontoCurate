import asyncio
import re
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Response
from fastapi.responses import FileResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_session
from app.core.exceptions import (
    BadRequestException,
    ForbiddenException,
    NotFoundException,
)
from app.deps import get_current_user
from app.models.user import User
from app.repositories.document import DocumentRepository
from app.repositories.workspace import WorkspaceMemberRepository, WorkspaceRepository
from app.schemas.document import DocumentDetailResponse, DocumentResponse
from app.schemas.statement import (
    CurrentAndOriginalStatement,
    RelatedSpansResponse,
    StatementResponseWithOriginal,
)
from app.store.client import EXPORT_FORMAT_MEDIA_TYPES, ExportFormat, curation_graph
from app.store.queries import export_document_data as query_export_document_data
from app.store.queries import (
    export_document_provenance as query_export_document_provenance,
)
from app.store.queries import (
    get_document_statement_rows,
    get_related_spans,
    get_triple_counts_bulk,
)
from app.store.utils import (
    PACO_CANDIDATE,
    PACO_CONFIDENCE,
    PACO_CREATED_AT,
    PACO_CURRENT,
    PACO_OBJECT,
    PACO_ORIGIN,
    PACO_PREDICATE,
    PACO_STATUS,
    PACO_SUBJECT,
    PACO_TEXT_SPAN_END,
    PACO_TEXT_SPAN_START,
    RDF_TYPE,
    build_prefix_map,
    create_source_document_entity,
)
from app.store.writer import delete_document_data

router = APIRouter(
    prefix="/documents", tags=["documents"], dependencies=[Depends(get_current_user)]
)


@router.get("/", response_model=list[DocumentResponse])
async def list_documents(
    workspace_id: UUID,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    role = await WorkspaceMemberRepository(session).get_role(
        workspace_id, current_user.id
    )
    if not role:
        raise ForbiddenException(f"You do not have access to workspace {workspace_id}")

    docs = await DocumentRepository(session).list_by_workspace(workspace_id)

    counts = await asyncio.to_thread(
        get_triple_counts_bulk,
        document_ids=[str(doc.id) for doc in docs],
        workspace_id=str(workspace_id),
    )

    return [
        DocumentResponse(
            id=doc.id,
            filename=doc.filename,
            file_type=doc.file_type,
            title=doc.title,
            extracted_triples=counts[str(doc.id)][0],
            pending_triples=counts[str(doc.id)][1],
            created_at=doc.created_at,
        )
        for doc in docs
    ]


@router.get("/{document_id}", response_model=DocumentDetailResponse)
async def get_document(
    document_id: UUID,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    doc = await DocumentRepository(session).get_by_id(document_id)
    if not doc:
        raise NotFoundException(f"Document {document_id} not found")
    role = await WorkspaceMemberRepository(session).get_role(
        doc.workspace_id, current_user.id
    )
    if not role:
        raise ForbiddenException(f"You do not have access to document {document_id}")

    counts = await asyncio.to_thread(
        get_triple_counts_bulk,
        document_ids=[str(document_id)],
        workspace_id=str(doc.workspace_id),
    )
    extracted_triples, pending_triples = counts[str(document_id)]

    return DocumentDetailResponse(
        id=doc.id,
        filename=doc.filename,
        file_type=doc.file_type,
        title=doc.title,
        extracted_triples=extracted_triples,
        pending_triples=pending_triples,
        created_at=doc.created_at,
        markdown=str(doc.source_content),
    )


@router.get("/{document_id}/markdown")
async def get_document_markdown(
    document_id: UUID,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    doc = await DocumentRepository(session).get_by_id(document_id)
    if not doc:
        raise NotFoundException(f"Document {document_id} not found")
    if not doc.source_content:
        return Response(
            status_code=202,
            content="Markdown conversion is still in progress. Please try again later.",
        )
    role = await WorkspaceMemberRepository(session).get_role(
        doc.workspace_id, current_user.id
    )
    if not role:
        raise ForbiddenException(f"You do not have access to document {document_id}")

    markdown = doc.source_content
    return Response(
        content=markdown,
        media_type="text/markdown",
        headers={"Content-Disposition": f"attachment; filename={document_id}.md"},
    )


@router.get("/{document_id}/pdf")
async def get_document_pdf(
    document_id: UUID,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    doc = await DocumentRepository(session).get_by_id(document_id)
    if not doc:
        raise NotFoundException(f"Document {document_id} not found")
    role = await WorkspaceMemberRepository(session).get_role(
        doc.workspace_id, current_user.id
    )
    if not role:
        raise ForbiddenException(f"You do not have access to document {document_id}")
    if not doc.raw_bytes:
        raise BadRequestException(f"PDF for document {document_id} is not available")
    return Response(
        content=doc.raw_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": f"attachment; filename={document_id}.pdf"},
    )


@router.delete("/{document_id}", status_code=204)
async def delete_document(
    document_id: UUID,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    doc = await DocumentRepository(session).get_by_id(document_id)
    if not doc:
        raise NotFoundException(f"Document {document_id} not found")
    role = await WorkspaceMemberRepository(session).get_role(
        doc.workspace_id, current_user.id
    )
    if role != "owner":
        raise ForbiddenException(
            f"Only workspace owners can delete document {document_id}"
        )
    await asyncio.to_thread(
        delete_document_data, str(doc.workspace_id), str(document_id)
    )
    await DocumentRepository(session).delete(document_id)


@router.get(
    "/{document_id}/statements",
    response_model=list[CurrentAndOriginalStatement],
)
async def get_document_statements(
    document_id: UUID,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    """
    Returns all statements associated entirely with the given document.

    Statements are grouped by their (immutable) original subject, and subjects
    with more outgoing relations are listed first so main document occurs first making it more suitable for reviewing.

    owl:sameAs triples that connect entities from different documents are not listed.

    Pagination could be added in the future if performance is bad.
    """

    document = await DocumentRepository(session).get_by_id(document_id)
    if document is None:
        raise NotFoundException(f"Document {document_id} not found")
    workspace_id = document.workspace_id
    role = await WorkspaceMemberRepository(session).get_role(
        workspace_id, current_user.id
    )
    if not role:
        raise ForbiddenException(f"You do not have access to document {document_id}")

    rows, originals_rows = await asyncio.to_thread(
        get_document_statement_rows, str(workspace_id), str(document_id)
    )

    return sort_by_relation_count(
        zip_current_originals(order_statements(rows), order_statements(originals_rows, current_only=False))
    )


@router.get(
    "/{document_id}/related-spans",
    response_model=RelatedSpansResponse,
)
async def get_related_spans_endpoint(
    document_id: UUID,
    subject: str,
    object: str | None = None,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    """
    Returns the text spans of every literal associated with given entities in the given document.
    """
    document = await DocumentRepository(session).get_by_id(document_id)
    if document is None:
        raise NotFoundException(f"Document {document_id} not found")
    workspace_id = document.workspace_id
    role = await WorkspaceMemberRepository(session).get_role(
        workspace_id, current_user.id
    )
    if not role:
        raise ForbiddenException(f"You do not have access to document {document_id}")

    subject_spans, object_spans = await asyncio.to_thread(
        get_related_spans, str(workspace_id), str(document_id), subject, object
    )
    return RelatedSpansResponse(subject_spans=subject_spans, object_spans=object_spans)


def zip_current_originals(
    current: list[StatementResponseWithOriginal],
    original: list[StatementResponseWithOriginal],
) -> list[CurrentAndOriginalStatement]:
    originals_by_id = {stm.id: stm for stm in original}

    result = []
    for stm in current:
        result.append(
            CurrentAndOriginalStatement(
                current=stm,
                original=originals_by_id[stm.original],
            )
        )

    return result


def order_statements(
    rows: list[tuple[str, str, str, str, str]],
    current_only: bool = True,
) -> list[StatementResponseWithOriginal]:
    grouped: dict[str, dict[str, list[str]]] = {}
    originals: dict[str, str] = {}
    object_is_uri = {}
    for subject, predicate, obj, original, obj_type in rows:
        grouped.setdefault(subject, {}).setdefault(predicate, []).append(obj)
        originals[subject] = original
        if predicate == PACO_OBJECT:
            object_is_uri[subject] = obj_type == "uri"

    records: list[StatementResponseWithOriginal] = []
    for subject, props in grouped.items():
        if PACO_CANDIDATE not in props.get(RDF_TYPE, []):
            continue

        def first(key: str) -> str | None:
            values = props.get(key, [])
            return values[0] if values else None

        def required(key: str) -> str:
            value = first(key)
            if value is None:
                raise HTTPException(
                    status_code=500, detail=f"CandidateStatement lacks {key}"
                )
            return value

        if current_only and (
            first(PACO_CURRENT) is None or first(PACO_CURRENT) == "false"
        ):
            continue

        confidence_str = first(PACO_CONFIDENCE)
        confidence = None if confidence_str is None else float(confidence_str)

        start_str = first(PACO_TEXT_SPAN_START)
        start = None if start_str is None else int(start_str)
        end_str = first(PACO_TEXT_SPAN_END)
        end = None if end_str is None else int(end_str)

        records.append(
            StatementResponseWithOriginal(
                id=subject,
                subject=required(PACO_SUBJECT),
                predicate=required(PACO_PREDICATE),
                object=required(PACO_OBJECT),
                object_is_uri=object_is_uri.get(subject, False),
                origin=required(PACO_ORIGIN),
                curation_status=required(PACO_STATUS),
                created_at=required(PACO_CREATED_AT),
                confidence=confidence,
                text_span_start=start,
                text_span_end=end,
                original=originals[subject],
            )
        )

    return records


def sort_by_relation_count(
    statements: list[CurrentAndOriginalStatement],
) -> list[CurrentAndOriginalStatement]:
    """
    Orders statements by the outgoing relation count of their (immutable) original
    subject.
    Ties are broken by the original subject/predicate/object which stay stable.
    """
    counts = {}
    for stm in statements:
        counts[stm.original.subject] = counts.get(stm.original.subject, 0) + 1

    return sorted(
        statements,
        key=lambda stm: (
            -counts[stm.original.subject],
            stm.original.subject,
            stm.original.predicate,
            stm.original.object,
        ),
    )


async def _get_document_or_403(
    document_id: UUID,
    current_user: User,
    session: AsyncSession,
    roles: tuple[str, ...] | None = None,
):
    doc = await DocumentRepository(session).get_by_id(document_id)
    if not doc:
        raise NotFoundException(f"Document {document_id} not found")
    role = await WorkspaceMemberRepository(session).get_role(
        doc.workspace_id, current_user.id
    )
    if not role or (roles is not None and role not in roles):
        raise ForbiddenException(f"You do not have access to document {document_id}")
    return doc


@router.get("/{document_id}/export/provenance", response_class=FileResponse)
async def export_document_provenance(
    document_id: UUID,
    format: ExportFormat = ExportFormat.turtle,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    doc = await _get_document_or_403(
        document_id, current_user, session, roles=("owner",)
    )
    graph = curation_graph(str(doc.workspace_id))
    document_entity = create_source_document_entity(str(document_id)).value
    media_type, extension = EXPORT_FORMAT_MEDIA_TYPES[format]
    workspace = await WorkspaceRepository(session).get_by_id(doc.workspace_id)
    prefixes = build_prefix_map(workspace.schema_path if workspace else None)
    content = await asyncio.to_thread(
        query_export_document_provenance, graph, document_entity, format, prefixes
    )
    filename = (
        re.sub(
            r'[\\/:"*?<>|\r\n]+',
            "_",
            (workspace.name if workspace else "workspace").strip(),
        )
        or "workspace"
    )
    return Response(
        content=content,
        media_type=media_type,
        headers={
            "Content-Disposition": (
                f'attachment; filename="{filename}_provenance.{extension}"'
            )
        },
    )


@router.get("/{document_id}/export/data", response_class=FileResponse)
async def export_document_data(
    document_id: UUID,
    format: ExportFormat = ExportFormat.turtle,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    doc = await _get_document_or_403(document_id, current_user, session)
    graph = curation_graph(str(doc.workspace_id))
    document_entity = create_source_document_entity(str(document_id)).value
    media_type, extension = EXPORT_FORMAT_MEDIA_TYPES[format]
    workspace = await WorkspaceRepository(session).get_by_id(doc.workspace_id)
    prefixes = build_prefix_map(workspace.schema_path if workspace else None)
    content = await asyncio.to_thread(
        query_export_document_data, graph, document_entity, format, prefixes
    )
    filename = (
        re.sub(
            r'[\\/:"*?<>|\r\n]+',
            "_",
            (workspace.name if workspace else "workspace").strip(),
        )
        or "workspace"
    )
    return Response(
        content=content,
        media_type=media_type,
        headers={
            "Content-Disposition": f'attachment; filename="{filename}_data.{extension}"'
        },
    )
