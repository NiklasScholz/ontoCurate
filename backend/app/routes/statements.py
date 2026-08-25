import asyncio
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from pyoxigraph import NamedNode
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_session
from app.core.exceptions import NotFoundException
from app.deps import get_current_user, require_role
from app.models.user import User
from app.repositories.workspace import WorkspaceRepository
from app.schemas.statement import StatementEdit, StatementResponse
from app.store.client import curation_graph
from app.store.queries import (
    get_current_candidate_statement,
    load_candidate_statement,
    load_candidate_statements_bulk,
)
from app.store.writer import (
    accept_statement,
    accept_statements_bulk,
    edit_statement,
    reject_statement,
    reset_statement,
)

router = APIRouter(
    prefix="/statements", tags=["statements"], dependencies=[Depends(get_current_user)]
)


@router.post(
    "/{workspace_id}/accept",
    status_code=200,
    dependencies=[Depends(require_role("owner", "editor"))],
    response_model=StatementResponse,
)
async def accept_statement_endpoint(
    workspace_id: UUID,
    statement_id: str,
    session: AsyncSession = Depends(get_session),
    current_user: User = Depends(get_current_user),
):
    """
    Accepts a statement. Returns the new CandidateStatement.
    """
    try:
        await asyncio.to_thread(
            accept_statement,
            stmt_id=statement_id,
            triggered_by=current_user.id,
            workspace_id=str(workspace_id),
        )
        return await get_current_statement_endpoint(workspace_id, statement_id, session)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.post(
    "/{workspace_id}/reject",
    status_code=200,
    dependencies=[Depends(require_role("owner", "editor"))],
    response_model=StatementResponse,
)
async def reject_statement_endpoint(
    workspace_id: UUID,
    statement_id: str,
    session: AsyncSession = Depends(get_session),
    current_user: User = Depends(get_current_user),
):
    """
    Rejects a statement. Returns the new CandidateStatement.
    """
    try:
        await asyncio.to_thread(
            reject_statement,
            stmt_id=statement_id,
            triggered_by=current_user.id,
            workspace_id=str(workspace_id),
        )
        return await get_current_statement_endpoint(workspace_id, statement_id, session)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.patch(
    "/{workspace_id}/edit",
    status_code=200,
    dependencies=[Depends(require_role("owner", "editor"))],
    response_model=StatementResponse,
)
async def edit_statement_endpoint(
    workspace_id: UUID,
    statement_id: str,
    edit: StatementEdit,
    session: AsyncSession = Depends(get_session),
    current_user: User = Depends(get_current_user),
):
    """
    Modifies the fields of a triple. Returns the new CandidateStatement.
    """
    try:
        await asyncio.to_thread(
            edit_statement,
            stmt_id=statement_id,
            triggered_by=current_user.id,
            workspace_id=str(workspace_id),
            edit=edit,
        )
        return await get_current_statement_endpoint(workspace_id, statement_id, session)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.post(
    "/{workspace_id}/reset",
    status_code=200,
    dependencies=[Depends(require_role("owner", "editor"))],
    response_model=StatementResponse,
)
async def reset_statement_endpoint(
    workspace_id: UUID,
    statement_id: str,
    current_user: User = Depends(get_current_user),
):
    """
    Rolls back a statement to its original version, and set it to reset.
    Returns the new CandidateStatement.
    """
    try:
        return await asyncio.to_thread(
            reset_statement,
            stmt_id=statement_id,
            triggered_by=current_user.id,
            workspace_id=str(workspace_id),
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.post(
    "/{workspace_id}/bulk_accept",
    status_code=200,
    dependencies=[Depends(require_role("owner", "editor"))],
    response_model=list[StatementResponse],
)
async def bulk_accept(
    workspace_id: UUID,
    statement_ids: list[str],
    current_user: User = Depends(get_current_user),
):
    """
    Accepts multiple statements in bulk. Returns the new CandidateStatements.
    """
    if not statement_ids:
        return []

    graph = curation_graph(str(workspace_id))

    try:
        new_ids = await asyncio.to_thread(
            accept_statements_bulk,
            stmt_ids=statement_ids,
            triggered_by=current_user.id,
            workspace_id=str(workspace_id),
        )
        accepted = await asyncio.to_thread(
            load_candidate_statements_bulk,
            stmt_ids=list(new_ids.values()),
            graph=graph,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    result = []
    for statement_id in statement_ids:
        new_id = new_ids[statement_id]
        statement = accepted[new_id]
        result.append(
            StatementResponse(
                id=new_id,
                subject=statement["subject"],
                predicate=statement["predicate"],
                object=statement["object_node"].value,
                object_is_uri=isinstance(statement["object_node"], NamedNode),
                origin=statement["origin"],
                curation_status=statement["status"],
                created_at=statement["created_at"],
                confidence=statement["confidence_score"],
                text_span_start=statement["text_span_start"],
                text_span_end=statement["text_span_end"],
            )
        )
    return result


@router.get(
    "/{workspace_id}/statements/{statement_id:path}/current",
    response_model=StatementResponse,
    dependencies=[Depends(require_role("owner", "editor"))],
)
async def get_current_statement_endpoint(
    workspace_id: UUID, statement_id: str, session: AsyncSession = Depends(get_session)
):
    """Retrieves the current version of a statement. Also used as a shared helper for other endpoints that modify statements."""
    workspace_repo = WorkspaceRepository(session)
    workspace = await workspace_repo.get_by_id(workspace_id)
    if workspace is None:
        raise NotFoundException(f"Workspace {workspace_id} not found")

    graph = curation_graph(str(workspace_id))
    try:
        current_statement_id = await asyncio.to_thread(
            get_current_candidate_statement,
            stmt_id=statement_id,
            graph=graph,
        )

        statement = await asyncio.to_thread(
            load_candidate_statement,
            stmt_id=current_statement_id,
            graph=graph,
        )

        return StatementResponse(
            id=current_statement_id,
            subject=statement["subject"],
            predicate=statement["predicate"],
            object=statement["object_node"].value,
            object_is_uri=isinstance(statement["object_node"], NamedNode),
            origin=statement["origin"],
            curation_status=statement["status"],
            created_at=statement["created_at"],
            confidence=statement["confidence_score"],
            text_span_start=statement["text_span_start"],
            text_span_end=statement["text_span_end"],
        )

    except ValueError as exc:
        raise HTTPException(
            status_code=404,
            detail=str(exc),
        ) from exc
