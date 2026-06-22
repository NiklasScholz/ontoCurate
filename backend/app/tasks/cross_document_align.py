import asyncio
import logging
import shutil
from pathlib import Path
from uuid import UUID

from app.core.database import TaskSessionLocal as AsyncSessionLocal
from app.pipeline.entity_alignment import run_cross_document_alignment
from app.repositories.run import RunRepository
from app.repositories.workspace import WorkspaceRepository
from app.worker import celery_app

logger = logging.getLogger(__name__)

TMP_BASE = Path("/tmp/ontocurate")


@celery_app.task(bind=True, name="runs.align_cross_document")
def align_cross_document_task(self, workspace_id: str, run_id: str) -> str:
    """Calls cross_document alignment"""
    logger.info(
        "[%s] Starting cross-document alignment: workspace=%s", run_id, workspace_id
    )

    async def run() -> None:
        async def update_all(status: str, task_name: str | None = None) -> None:
            async with AsyncSessionLocal() as session:
                tasks = await RunRepository(session).get_tasks_by_run(UUID(run_id))
            for t in tasks:
                async with AsyncSessionLocal() as session:
                    await RunRepository(session).update_document_status(
                        UUID(run_id), t.document_id, status, task_name=task_name
                    )

        await update_all("started", task_name="Cross-Document Alignment")
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
        finally:
            shutil.rmtree(TMP_BASE / run_id, ignore_errors=True)

    asyncio.run(run())
    return workspace_id
