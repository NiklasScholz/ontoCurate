from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse, StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_session
from app.core.exceptions import NotFoundException
from app.repositories.document import DocumentRepository
from app.schemas.document import DocumentDetailResponse, DocumentResponse
from app.schemas.statement import StatementResponse
from app.store.client import curation_graph, sparql_select
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
)

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
        extracted_triples=0,
        pending_triples=0,
        markdown=str(doc.source_content),
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
    # TODO: Cancel all running tasks related to this document
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
    # TODO: Restrict to given document, order statements

    document = await DocumentRepository(session).get_by_id(document_id)
    if document is None:
        raise HTTPException(status_code=404, detail="Document not found")
    workspace_id = document.workspace_id

    graph = curation_graph(str(workspace_id))

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

    grouped: dict[str, dict[str, list[str]]] = {}
    for subject, predicate, obj in rows:
        grouped.setdefault(subject, {}).setdefault(predicate, []).append(obj)

    records: list[StatementResponse] = []
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
            StatementResponse(
                id=subject,
                subject=required(PACO_SUBJECT),
                predicate=required(PACO_PREDICATE),
                object=required(PACO_OBJECT),
                origin=required(PACO_ORIGIN),
                curation_status=required(PACO_STATUS),
                created_at=required(PACO_CREATED_AT),
                # generated_by=first(PROV_GENERATED_BY),
                # derived_from=first(PROV_DERIVED_FROM),
                confidence=confidence,
                text_span_start=start,
                text_span_end=end,
            )
        )

    return records


@router.get("/{document_id}/export/provenance.ttl")
async def export_document_ttl(document_id: str, response_class=FileResponse):
    # TODO
    pass
