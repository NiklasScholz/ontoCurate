from celery.result import AsyncResult
from fastapi import APIRouter, Depends
from pyoxigraph import Literal, NamedNode, Quad
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_session
from app.models.workspace import Workspace
from app.store.client import get_store
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
    store = get_store()

    test_graph = NamedNode("https://ontocurate.org/debug")
    test_subject = NamedNode("https://ontocurate.org/debug/subject")
    test_predicate = NamedNode("https://ontocurate.org/debug/predicate")
    test_object = Literal("hello world")

    quad = Quad(test_subject, test_predicate, test_object, test_graph)
    store.add(quad)

    results = list(
        store.quads_for_pattern(test_subject, test_predicate, None, test_graph)
    )
    store.remove(quad)

    if not results:
        return {"oxigraph": "error", "detail": "triple not found after write"}

    return {
        "oxigraph": "ok",
        "write_read": str(results[0].object),
    }
