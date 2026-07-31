import asyncio
import logging
import shutil
from pathlib import Path
from uuid import UUID

from app.core.database import TaskSessionLocal as AsyncSessionLocal
from app.pipeline.entity_alignment import run_inner_document_alignment
from app.repositories.run import RunRepository
from app.repositories.workspace import WorkspaceRepository
from app.worker import celery_app

logger = logging.getLogger(__name__)


TMP_BASE = Path("/tmp/ontocurate")


@celery_app.task(bind=True, name="runs.align_document")
def align_document_task(self, extract_result: tuple) -> str:
    """
    Per-Document Entity Alignment Postprocessing
    """
    model, document_id, run_id, tmp_dir, ttl_path, provenance_path, workspace_id = (
        extract_result
    )

    if ttl_path is None:
        # Skip document failed in the extraction stage
        logger.info(
            "[%s] Skipping alignment, previous stage failed: document=%s",
            run_id,
            document_id,
        )
        return document_id

    logger.info("[%s] Aligning: document=%s", run_id, document_id)

    ttl_path = Path(ttl_path)
    tmp_dir = Path(tmp_dir)

    async def run() -> None:
        async def update_status(status: str, task_name: str | None = None) -> None:
            async with AsyncSessionLocal() as session:
                await RunRepository(session).update_document_status(
                    UUID(run_id), UUID(document_id), status, task_name=task_name
                )

        await update_status("Running", task_name="Inner Document Alignment")
        try:
            async with AsyncSessionLocal() as session:
                workspace = await WorkspaceRepository(session).get_by_id(
                    UUID(workspace_id)
                )

            config_path = workspace.alignment_config_path
            await asyncio.to_thread(
                run_inner_document_alignment,
                ttl_path,
                workspace_id,
                run_id,
                config_path,
                document_id,
            )

            working_dir = TMP_BASE / run_id
            working_dir.mkdir(parents=True, exist_ok=True)
            shutil.copy2(ttl_path, working_dir / f"{document_id}.ttl")

            async with AsyncSessionLocal() as session:
                tasks = await RunRepository(session).get_tasks_by_run(UUID(run_id))

            other_tasks = [t for t in tasks if str(t.document_id) != document_id]
            all_others_finished = all(
                t.status in {"Waiting", "Done", "Failed"} for t in other_tasks
            )
            if all_others_finished:
                await update_status("Queued", task_name="Cross-Document Alignment")
            else:
                await update_status("Waiting", task_name="Cross-Document Alignment")
            logger.info("[%s] Alignment complete: document=%s", run_id, document_id)
        except Exception:
            await update_status("Failed")
            logger.exception("[%s] Alignment failed: document=%s", run_id, document_id)
        finally:
            shutil.rmtree(tmp_dir, ignore_errors=True)

    asyncio.run(run())
    return document_id
