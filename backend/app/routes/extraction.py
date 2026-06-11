from uuid import UUID

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_session
from app.repositories.run import RunRepository
from app.store.writer import accept_statement, reject_statement

router = APIRouter(prefix="/extraction", tags=["extraction"])


@router.post("/", status_code=202)
async def create_run():
    pass


@router.get("/{run_id}")
async def get_run():
    pass


@router.get("/{run_id}/statements")
async def get_run_statements():
    pass


@router.post("/{run_id}/statements/bulk_accept", status_code=202)
async def bulk_accept_statements():
    pass


@router.post("/{run_id}/statements/{statement_id:path}/accept", status_code=200)
async def accept_statement_endpoint(
    run_id: UUID, statement_id: str, session: AsyncSession = Depends(get_session)
):
    run_repo = RunRepository(session)

    run = await run_repo.get_by_id(run_id)
    if run is None:
        return {"run_id": run_id, "error": "Run not found"}

    curator_id = "https://example.org/users/todo"

    accept_statement(
        stmt_id=statement_id,
        curator_id=curator_id,
        workspace_id=str(run.workspace_id),
    )

    return {
        "run_id": run_id,
        "workspace_id": run.workspace_id,
        "statement_id": statement_id,
        "status": "accepted",
    }


@router.post("/{run_id}/statements/{statement_id:path}/reject", status_code=200)
async def reject_statement():
    pass


@router.patch("/{run_id}/statements/{statement_id:path}", status_code=200)
async def edit_statement():
    pass


@router.get("/{run_id}/entities")
async def get_run_entities():
    pass


@router.get("/{run_id}/entities/{entity_uri:path}/statements")
async def get_run_entity_statements():
    pass
