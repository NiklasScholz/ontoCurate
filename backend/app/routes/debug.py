from celery.result import AsyncResult
from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_session
from app.models.workspace import Workspace
from app.store.client import sparql_select, sparql_update
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

    sparql_update(
        f"""
        INSERT DATA {{
            GRAPH <{graph}> {{
                <{subject}> <{predicate}> "hello world" .
            }}
        }}
    """
    )

    result = sparql_select(
        f"""
        SELECT ?o WHERE {{
            GRAPH <{graph}> {{ <{subject}> <{predicate}> ?o }}
        }}
    """
    )

    sparql_update(f"DROP SILENT GRAPH <{graph}>")

    bindings = result.get("results", {}).get("bindings", [])
    if not bindings:
        return {"oxigraph": "error", "detail": "triple not found after write"}

    return {
        "oxigraph": "ok",
        "write_read": bindings[0]["o"]["value"],
    }
