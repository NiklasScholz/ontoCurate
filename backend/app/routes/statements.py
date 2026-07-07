from uuid import UUID

from fastapi import APIRouter, Depends

from app.deps import get_current_user, require_role
from app.schemas.statement import StatementPatchBody, StatementResponse

router = APIRouter(
    prefix="/statements", tags=["statements"], dependencies=[Depends(get_current_user)]
)


@router.post(
    "/{workspace_id}/{statement_id}/accept",
    response_model=StatementResponse,
    dependencies=[Depends(require_role("owner", "editor"))],
)
async def accept_statement(workspace_id: UUID, statement_id: str):
    """
    Accepts a statement. Returns the new CandidateStatement.
    """
    # TODO


@router.post(
    "/{workspace_id}/{statement_id}/reject",
    response_model=StatementResponse,
    dependencies=[Depends(require_role("owner", "editor"))],
)
async def reject_statement(workspace_id: UUID, statement_id: str):
    """
    Rejects a statement. Returns the new CandidateStatement.
    """
    # TODO


@router.post(
    "/{workspace_id}/{statement_id}/reset",
    response_model=StatementResponse,
    dependencies=[Depends(require_role("owner", "editor"))],
)
async def reset_statement(workspace_id: UUID, statement_id: str):
    """
    Rolls back a statement to its original version, and set it to neither accepted nor rejected.
    Returns the new CandidateStatement.
    """


@router.patch(
    "/{workspace_id}/{statement_id}",
    response_model=StatementResponse,
    dependencies=[Depends(require_role("owner", "editor"))],
)
async def edit_statement(body: StatementPatchBody):
    """
    Modifies the fields of a triple. Returns the new CandidateStatement.
    """
