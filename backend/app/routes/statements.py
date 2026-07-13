from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_session
from app.deps import get_current_user, require_role
from app.models.user import User
from app.repositories.workspace import WorkspaceRepository
from app.schemas.statement import StatementEdit, StatementIdResponse, StatementResponse
from app.store.writer import (
    accept_statement,
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
        raise HTTPException(status_code=404, detail="Workspace not found")

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
        raise HTTPException(status_code=404, detail="Workspace not found")

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
        raise HTTPException(status_code=404, detail="Workspace not found")

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
        raise HTTPException(status_code=404, detail="Workspace not found")

    try:
        return reset_statement(
            stmt_id=statement_id,
            triggered_by=current_user.id,
            workspace_id=str(workspace.id),
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
