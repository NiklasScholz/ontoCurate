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
from app.repositories.workspace import WorkspaceMemberRepository
from app.schemas.document import DocumentDetailResponse, DocumentResponse
from app.schemas.statement import (
    CurrentAndOriginalStatement,
    StatementResponseWithOriginal,
)
from app.store.client import curation_graph, sparql_select
from app.store.utils import (
    PACO_CANDIDATE,
    PACO_CONFIDENCE,
    PACO_CREATED_AT,
    PACO_CURRENT,
    PACO_EXTRACTION_ACTIVITY,
    PACO_OBJECT,
    PACO_ORIGIN,
    PACO_PENDING,
    PACO_PREDICATE,
    PACO_STATUS,
    PACO_SUBJECT,
    PACO_TEXT_SPAN_END,
    PACO_TEXT_SPAN_START,
    PROV_DERIVED_FROM,
    PROV_GENERATED_BY,
    PROV_USED,
    RDF_TYPE,
    create_source_document_entity,
)

router = APIRouter(
    prefix="/documents", tags=["documents"], dependencies=[Depends(get_current_user)]
)


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
            extracted_triples=await get_triple_count(doc.id, session, False),
            pending_triples=await get_triple_count(doc.id, session, True),
        )
        for doc in await DocumentRepository(session).list_by_workspace(workspace_id)
    ]


@router.get("/{document_id}", response_model=DocumentDetailResponse)
async def get_document(document_id: UUID, session: AsyncSession = Depends(get_session)):
    doc = await DocumentRepository(session).get_by_id(document_id)
    if not doc:
        raise NotFoundException(f"Document {document_id} not found")
    return DocumentDetailResponse(
        id=doc.id,
        filename=doc.filename,
        file_type=doc.file_type,
        title=doc.title,
        extracted_triples=await get_triple_count(document_id, session, False),
        pending_triples=await get_triple_count(document_id, session, True),
        markdown=str(doc.source_content),
    )


async def get_triple_count(
    document_id: UUID, session: AsyncSession, pending_only: bool
):
    document = await DocumentRepository(session).get_by_id(document_id)
    if document is None:
        raise HTTPException(status_code=404, detail="Document not found")
    workspace_id = document.workspace_id

    graph = curation_graph(str(workspace_id))

    document_entity = create_source_document_entity(
        str(workspace_id), str(document_id)
    ).value

    payload = sparql_select(f"""
        SELECT (COUNT(*) AS ?count) WHERE {{
            GRAPH <{graph}> {{
                ?s <{RDF_TYPE}> <{PACO_CANDIDATE}> .
                ?s <{PACO_CURRENT}> true .
                ?s <{PROV_DERIVED_FROM}>* ?os .
                ?os <{PROV_GENERATED_BY}> ?e .
                ?e <{RDF_TYPE}> <{PACO_EXTRACTION_ACTIVITY}> .
                ?e <{PROV_USED}> <{document_entity}> .
                {f"?s <{PACO_STATUS}> <{PACO_PENDING}> ." if pending_only else ""}
            }}
        }}
        ORDER BY ?s ?p ?o
    """)

    rows = [b["count"]["value"] for b in payload.get("results", {}).get("bindings", [])]

    return rows[0]


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
    return FileResponse(
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
    if not role:
        raise ForbiddenException(f"You do not have access to document {document_id}")
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

    The order of statements is as follows (coarsest to finest grouping):
    - Data type properties are listed before object properties.
    - Finally, sort triples lexicographically.

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

    graph = curation_graph(str(workspace_id))

    document_entity = create_source_document_entity(
        str(workspace_id), str(document_id)
    ).value

    payload = sparql_select(f"""
        SELECT ?s ?p ?o ?os WHERE {{
            GRAPH <{graph}> {{
                ?s ?p ?o .
                ?s <{RDF_TYPE}> <{PACO_CANDIDATE}> .
                ?s <{PACO_CURRENT}> true .
                ?s <{PROV_DERIVED_FROM}>* ?os .
                ?os <{PROV_GENERATED_BY}> ?e .
                ?e <{RDF_TYPE}> <{PACO_EXTRACTION_ACTIVITY}> .
                ?e <{PROV_USED}> <{document_entity}> .
            }}
        }}
        ORDER BY ?s ?p ?o
    """)

    rows = [
        (b["s"]["value"], b["p"]["value"], b["o"]["value"], b["os"]["value"])
        for b in payload.get("results", {}).get("bindings", [])
    ]

    originals_payload = sparql_select(f"""
        SELECT ?s ?p ?o WHERE {{
            GRAPH <{graph}> {{
                ?s ?p ?o .
                ?s <{RDF_TYPE}> <{PACO_CANDIDATE}> .
                ?s <{PROV_GENERATED_BY}> ?e .
                ?e <{RDF_TYPE}> <{PACO_EXTRACTION_ACTIVITY}> .
                ?e <{PROV_USED}> <{document_entity}> .
            }}
        }}
        ORDER BY ?s ?p ?o
    """)

    originals_rows = [
        (b["s"]["value"], b["p"]["value"], b["o"]["value"], b["s"]["value"])
        for b in originals_payload.get("results", {}).get("bindings", [])
    ]

    return zip_current_originals(
        order_statements(rows), order_statements(originals_rows)
    )


def zip_current_originals(
    current: list[StatementResponseWithOriginal],
    original: list[StatementResponseWithOriginal],
) -> list[CurrentAndOriginalStatement]:
    result = []
    for stm in current:
        matches = [x for x in original if x.id == stm.original]
        result.append(
            CurrentAndOriginalStatement(
                current=stm, original=matches[0] if len(matches) >= 1 else stm
            )
        )
    return result


def order_statements(
    rows: list[tuple[str, str, str, str]],
) -> list[StatementResponseWithOriginal]:
    grouped: dict[str, dict[str, list[str]]] = {}
    originals: dict[str, str] = {}
    for subject, predicate, obj, original in rows:
        grouped.setdefault(subject, {}).setdefault(predicate, []).append(obj)
        originals[subject] = original

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

        if first(PACO_CURRENT) is None or first(PACO_CURRENT) == "false":
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
                origin=required(PACO_ORIGIN),
                curation_status=required(PACO_STATUS),
                created_at=required(PACO_CREATED_AT),
                confidence=confidence,
                text_span_start=start,
                text_span_end=end,
                original=originals[subject],
            )
        )

    # TODO: The sorting order must be stable. Since subject/predicate/object can be changed by the user, we currently can't really use them as the sort key!
    records.sort(key=lambda s: s.original)
    return records


@router.get("/{document_id}/export/provenance.ttl")
async def export_document_ttl(document_id: str, response_class=FileResponse):
    # TODO
    pass
