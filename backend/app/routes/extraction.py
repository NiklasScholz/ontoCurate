from uuid import UUID

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_session
from app.repositories.run import RunRepository
from app.repositories.user import UserRepository
from app.repositories.workspace import WorkspaceRepository
from app.store.client import curation_graph, sparql_update
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

    triggered_by = None  # will be replaced by user

    # If no triggering user supplied, create a system user
    if triggered_by is None:
        user_repo = UserRepository(session)
        user = await user_repo.get_by_email("system@localhost")
        if user is None:
            user = await user_repo.create(email="system@localhost", password_encrypt="")
        triggered_by = user.id

    accept_statement(
        stmt_id=statement_id,
        triggered_by=triggered_by,
        workspace_id=str(run.workspace_id),
    )

    return {
        "run_id": run_id,
        "workspace_id": run.workspace_id,
        "statement_id": statement_id,
        "status": "accepted",
    }


@router.post("/{run_id}/statements/{statement_id:path}/reject", status_code=200)
async def reject_statement_endpoint(
    run_id: UUID, statement_id: str, session: AsyncSession = Depends(get_session)
):
    run_repo = RunRepository(session)

    run = await run_repo.get_by_id(run_id)
    if run is None:
        return {"run_id": run_id, "error": "Run not found"}

    triggered_by = None  # will be replaced by user

    # If no triggering user supplied, create a system user
    if triggered_by is None:
        user_repo = UserRepository(session)
        user = await user_repo.get_by_email("system@localhost")
        if user is None:
            user = await user_repo.create(email="system@localhost", password_encrypt="")
        triggered_by = user.id

    reject_statement(
        stmt_id=statement_id,
        triggered_by=triggered_by,
        workspace_id=str(run.workspace_id),
    )

    return {
        "run_id": run_id,
        "workspace_id": run.workspace_id,
        "statement_id": statement_id,
        "status": "rejected",
    }


@router.patch("/{run_id}/statements/{statement_id:path}", status_code=200)
async def edit_statement():
    pass


@router.get("/{run_id}/entities")
async def get_run_entities():
    pass


@router.get("/{run_id}/entities/{entity_uri:path}/statements")
async def get_run_entity_statements():
    pass


@router.post("/dev/seed-statement", status_code=201)
async def seed_statement_for_testing(
    session: AsyncSession = Depends(get_session),
):
    workspace_repo = WorkspaceRepository(session)
    run_repo = RunRepository(session)
    workspace = await workspace_repo.create(name="Test Workspace")
    workspace_id = workspace.id

    run = await run_repo.create(
        workspace_id=workspace_id,
        triggered_by=None,
        model="test-model",
    )

    graph = curation_graph(str(workspace_id))

    statement_id = (
        f"https://example.org/workspaces/"
        f"{workspace_id}/candidate-statements/test-paper-author"
    )

    sparql_update(
        f"""
    INSERT DATA {{
        GRAPH <{graph}> {{
            <{statement_id}> a <https://example.org/provenance-and-curation-ontology/CandidateStatement> .
            <{statement_id}> a <http://www.w3.org/ns/prov#Entity> .
            <{statement_id}> <https://example.org/provenance-and-curation-ontology/subject> <https://example.org/entities/Paper_X> .
            <{statement_id}> <https://example.org/provenance-and-curation-ontology/predicate> <https://schema.org/author> .
            <{statement_id}> <https://example.org/provenance-and-curation-ontology/object> <https://example.org/entities/Author_Y> .
            <{statement_id}> <https://example.org/provenance-and-curation-ontology/curationStatus> <https://example.org/provenance-and-curation-ontology/pending> .
            <{statement_id}> <https://example.org/provenance-and-curation-ontology/isCurrentVersion> true .
            <{statement_id}> <https://example.org/provenance-and-curation-ontology/confidence> "0.85"^^<http://www.w3.org/2001/XMLSchema#decimal> .
        }}
    }}
    """
    )

    return {
        "workspace_id": workspace_id,
        "run_id": run.id,
        "statement_id": statement_id,
        "status": "seeded",
        "next_step": (
            f"POST /extraction/{run.id}/statements/" f"{statement_id}/accept"
        ),
    }
