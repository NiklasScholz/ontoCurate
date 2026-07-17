from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_session
from app.core.exceptions import NotFoundException
from app.deps import get_current_user, require_role
from app.models.user import User
from app.repositories.workspace import WorkspaceRepository
from app.schemas.statement import StatementEdit, StatementIdResponse, StatementResponse
from app.store.client import curation_graph
from app.store.queries import get_current_candidate_statement
from app.store.writer import (
    accept_statement,
    edit_statement,
    load_candidate_statement,
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
    response_model=StatementIdResponse,
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
    workspace_repo = WorkspaceRepository(session)

    workspace = await workspace_repo.get_by_id(workspace_id)
    if workspace is None:
        raise NotFoundException(f"Workspace {workspace_id} not found")

    try:
        return StatementIdResponse(
            id=accept_statement(
                stmt_id=statement_id,
                triggered_by=current_user.id,
                workspace_id=str(workspace.id),
            )
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.post(
    "/{workspace_id}/reject",
    status_code=200,
    dependencies=[Depends(require_role("owner", "editor"))],
    response_model=StatementIdResponse,
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
    workspace_repo = WorkspaceRepository(session)

    workspace = await workspace_repo.get_by_id(workspace_id)
    if workspace is None:
        raise NotFoundException(f"Workspace {workspace_id} not found")

    try:
        return StatementIdResponse(
            id=reject_statement(
                stmt_id=statement_id,
                triggered_by=current_user.id,
                workspace_id=str(workspace.id),
            )
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.patch(
    "/{workspace_id}/edit",
    status_code=200,
    dependencies=[Depends(require_role("owner", "editor"))],
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
    workspace_repo = WorkspaceRepository(session)

    workspace = await workspace_repo.get_by_id(workspace_id)
    if workspace is None:
        raise NotFoundException(f"Workspace {workspace_id} not found")

    try:
        return StatementIdResponse(
            id=edit_statement(
                stmt_id=statement_id,
                triggered_by=current_user.id,
                workspace_id=str(workspace.id),
                edit=edit,
            )
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.post(
    "/{workspace_id}/reset",
    response_model=StatementResponse,
    dependencies=[Depends(require_role("owner", "editor"))],
)
async def reset_statement_endpoint(
    workspace_id: UUID,
    statement_id: str,
    session: AsyncSession = Depends(get_session),
    current_user: User = Depends(get_current_user),
):
    """
    Rolls back a statement to its original version, and set it to reset.
    Returns the new CandidateStatement.
    """
    workspace_repo = WorkspaceRepository(session)

    workspace = await workspace_repo.get_by_id(workspace_id)
    if workspace is None:
        raise NotFoundException(f"Workspace {workspace_id} not found")

    try:
        return reset_statement(
            stmt_id=statement_id,
            triggered_by=current_user.id,
            workspace_id=str(workspace.id),
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.get(
    "/{workspace_id}/statements/{statement_id:path}/current",
    response_model=StatementResponse,
)
async def get_current_statement_endpoint(
    workspace_id: UUID, statement_id: str, session: AsyncSession = Depends(get_session)
):
    workspace_repo = WorkspaceRepository(session)

    workspace = await workspace_repo.get_by_id(workspace_id)
    if workspace is None:
        raise NotFoundException(f"Workspace {workspace_id} not found")

    graph = curation_graph(str(workspace_id))

    try:
        current_statement_id = get_current_candidate_statement(
            stmt_id=statement_id,
            graph=graph,
        )

        statement = load_candidate_statement(
            stmt_id=current_statement_id,
            graph=graph,
        )

        object_node = statement["object_node"]

        object_value = object_node.value

        return StatementResponse(
            id=current_statement_id,
            subject=statement["subject"],
            predicate=statement["predicate"],
            object=object_value,
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
