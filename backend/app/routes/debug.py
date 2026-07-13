import uuid

from celery.result import AsyncResult
from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_session
from app.deps import get_current_user
from app.models.workspace import Workspace
from app.repositories.run import RunRepository
from app.repositories.workspace import WorkspaceRepository
from app.store.client import curation_graph, sparql_select, sparql_update
from app.tasks.test import ping_task, slow_task

router = APIRouter(prefix="/debug", tags=["debug"])


@router.post("/ping")
async def trigger_ping(message: str = "pong"):
    """Enqueues a ping task and return the task id and queued status."""
    result = ping_task.delay(message)
    return {"task_id": result.id, "status": "queued"}


@router.post("/slow")
async def trigger_slow(seconds: int = 5):
    """Enqueues a task that sleep for N secodns"""
    result = slow_task.delay(seconds)
    return {"task_id": result.id, "status": "queued"}


@router.get("/task/{task_id}")
async def get_task_status(task_id: str):
    """Poll celery task status"""
    result = AsyncResult(task_id)
    return {
        "task_id": task_id,
        "status": result.status,
        "result": result.result if result.ready() else None,
    }


@router.get("/db")
async def check_db(session: AsyncSession = Depends(get_session)):
    """
    Verifies database connection by writing a row to Workspace table, retrieving it and deleting it again.
    """
    workspace = Workspace(name="testing purposes")
    session.add(workspace)
    await session.flush()

    fetched = await session.get(Workspace, workspace.id)
    await session.delete(fetched)
    await session.commit()

    return {
        "database": "ok",
        "write_read": {"id": str(workspace.id), "name": workspace.name},
    }


@router.get("/oxigraph")
async def check_oxigraph():
    """
    Verifies the triple store connection, write, and query are all working.
    """
    graph = "https://ontocurate.org/debug"
    subject = "https://ontocurate.org/debug/subject"
    predicate = "https://ontocurate.org/debug/predicate"

    sparql_update(f"""
        INSERT DATA {{
            GRAPH <{graph}> {{
                <{subject}> <{predicate}> "hello world" .
            }}
        }}
    """)

    result = sparql_select(f"""
        SELECT ?o WHERE {{
            GRAPH <{graph}> {{ <{subject}> <{predicate}> ?o }}
        }}
    """)

    sparql_update(f"DROP SILENT GRAPH <{graph}>")

    bindings = result.get("results", {}).get("bindings", [])
    if not bindings:
        return {"oxigraph": "error", "detail": "triple not found after write"}

    return {
        "oxigraph": "ok",
        "write_read": bindings[0]["o"]["value"],
    }


@router.post("/seed-statement/{workspace_id}", status_code=201)
async def seed_statement_for_testing(
    workspace_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
    user=Depends(get_current_user),
):
    workspace_repo = WorkspaceRepository(session)
    run_repo = RunRepository(session)

    workspace = await workspace_repo.get_by_id(workspace_id)
    if workspace is None:
        workspace = await workspace_repo.create_with_id(
            name="Test Workspace",
            workspace_id=workspace_id,
            schema_path="test-schema-path",
            alignment_config_path="test-alignment-config-path",
            provenance_config_path="test-provenance-config-path",
        )

    run = await run_repo.create(
        workspace_id=workspace.id,
        triggered_by=user.id,
        model="test-model",
    )

    graph = curation_graph(str(workspace.id))

    statement_id = (
        f"https://example.org/workspaces/"
        f"{workspace_id}/candidate-statements/test-paper-author"
    )

    source_document_id = (
        f"https://example.org/workspaces/" f"{workspace_id}/source-documents/test-paper"
    )

    sparql_update(f"""
    INSERT DATA {{
        GRAPH <{graph}> {{
            <{source_document_id}> a <https://example.org/provenance-and-curation-ontology/SourceDocument> .
            <{statement_id}> a <https://example.org/provenance-and-curation-ontology/CandidateStatement> .
            <{statement_id}> a <http://www.w3.org/ns/prov#Entity> .
            <{statement_id}> <https://example.org/provenance-and-curation-ontology/subject> <https://example.org/entities/Paper_X> .
            <{statement_id}> <https://example.org/provenance-and-curation-ontology/predicate> <https://schema.org/author> .
            <{statement_id}> <https://example.org/provenance-and-curation-ontology/object> <https://example.org/entities/Author_Y> .
            <{statement_id}> <https://example.org/provenance-and-curation-ontology/curationStatus> <https://example.org/provenance-and-curation-ontology/pending> .
            <{statement_id}> <https://example.org/provenance-and-curation-ontology/isCurrentVersion> true .
            <{statement_id}> <https://example.org/provenance-and-curation-ontology/confidence> "0.85"^^<http://www.w3.org/2001/XMLSchema#decimal> .
            <{statement_id}> <http://www.w3.org/ns/prov#wasDerivedFrom> <{source_document_id}> .
            <{statement_id}> <https://example.org/provenance-and-curation-ontology/origin> <https://example.org/origins/test-origin> .
            <{statement_id}> <https://example.org/provenance-and-curation-ontology/createdAt> "2023-10-01T12:00:00Z"^^<http://www.w3.org/2001/XMLSchema#dateTime> .
        }}
    }}
    """)

    return {
        "workspace_id": workspace_id,
        "run_id": run.id,
        "statement_id": statement_id,
        "source_document_id": source_document_id,
        "status": "seeded",
        "next_step": (
            f"POST /extraction/{run.id}/statements/" f"{statement_id}/accept"
        ),
    }
