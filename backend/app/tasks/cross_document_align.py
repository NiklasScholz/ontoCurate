import asyncio
import logging
from pathlib import Path
from uuid import UUID

from redis.exceptions import LockError

from app.core.database import TaskSessionLocal as AsyncSessionLocal
from app.core.locks import workspace_alignment_lock
from app.pipeline.entity_alignment import run_cross_document_alignment
from app.repositories.run import RunRepository
from app.repositories.workspace import WorkspaceRepository
from app.worker import celery_app

logger = logging.getLogger(__name__)

TMP_BASE = Path("/tmp/ontocurate")
LOCK_RETRY_DELAY_SECONDS = 5


@celery_app.task(bind=True, name="runs.align_cross_document", max_retries=None)
def align_cross_document_task(self, workspace_id: str, run_id: str) -> str:
    """Calls cross_document alignment.
    Only one cross-document may run per workspace at a time. Automatically retry after configured delay if another alignment is in process.
    """
    logger.info(
        "[%s] Starting cross-document alignment: workspace=%s", run_id, workspace_id
    )

    lock = workspace_alignment_lock(workspace_id)
    if not lock.acquire(blocking=False):
        logger.info(
            "[%s] Cross-document alignment busy for workspace=%s, retrying",
            run_id,
            workspace_id,
        )
        raise self.retry(countdown=LOCK_RETRY_DELAY_SECONDS)

    async def run() -> None:
        async def update_all(status: str, task_name: str | None = None) -> None:
            async with AsyncSessionLocal() as session:
                tasks = await RunRepository(session).get_tasks_by_run(UUID(run_id))
            for t in tasks:
                async with AsyncSessionLocal() as session:
                    await RunRepository(session).update_document_status(
                        UUID(run_id), t.document_id, status, task_name=task_name
                    )

        await update_all("aligning", task_name="Cross-Document Alignment")
        try:
            async with AsyncSessionLocal() as session:
                workspace = await WorkspaceRepository(session).get_by_id(
                    UUID(workspace_id)
                )

            config_path = workspace.alignment_config_path
            await asyncio.to_thread(
                run_cross_document_alignment,
                TMP_BASE / run_id,
                workspace_id,
                run_id,
                config_path,
            )
            await update_all("done", task_name="Cross-Document Alignment")

            logger.info("[%s] Cross-document alignment complete", run_id)
        except Exception:
            await update_all("failed")
            logger.exception("[%s] Cross-document alignment failed", run_id)
            raise

    try:
        asyncio.run(run())
    finally:
        try:
            lock.release()
        except LockError:
            logger.warning(
                "[%s] Cross-document alignment lock for workspace=%s already"
                " expired before release",
                run_id,
                workspace_id,
            )

    return workspace_id
