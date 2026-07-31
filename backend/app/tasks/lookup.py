import asyncio
import logging
import shutil
from pathlib import Path
from uuid import UUID

from app.core.database import TaskSessionLocal as AsyncSessionLocal
from app.pipeline.lookup import load_lookup_config, run_entity_lookup
from app.pipeline.utils.turtle_utils import load_entity_information
from app.repositories.run import RunRepository
from app.repositories.workspace import WorkspaceRepository
from app.worker import celery_app

logger = logging.getLogger(__name__)

TMP_BASE = Path("/tmp/ontocurate")


@celery_app.task(bind=True, name="runs.lookup_wikidata")
def lookup_wikidata_task(self, workspace_id: str, run_id: str) -> str:
    """
    Entity Lookup
    - Loads merged TTL from cross-document alignment
    - uses app.pipeline.lookup.run_entity_lookup to query lookup services for candidate entities, scores them, and writes proposed
      owl:sameAs links to Oxigraph
    """
    logger.info("[%s] Starting entity lookup: workspace=%s", run_id, workspace_id)

    async def run() -> None:
        async def update_all(status: str, task_name: str | None = None) -> None:
            """Update status for all documents in the run."""
            async with AsyncSessionLocal() as session:
                tasks = await RunRepository(session).get_tasks_by_run(UUID(run_id))
            for t in tasks:
                if t.status == "Failed":
                    # Skip updating failed tasks
                    continue
                async with AsyncSessionLocal() as session:
                    await RunRepository(session).update_document_status(
                        UUID(run_id), t.document_id, status, task_name=task_name
                    )

        await update_all("Running", task_name="External Lookup")
        working_dir = TMP_BASE / run_id
        try:
            async with AsyncSessionLocal() as session:
                tasks = await RunRepository(session).get_tasks_by_run(UUID(run_id))

            document_ids = [str(task.document_id) for task in tasks]

            # Load workspace config
            async with AsyncSessionLocal() as session:
                workspace = await WorkspaceRepository(session).get_by_id(
                    UUID(workspace_id)
                )

            lookup_file_config = load_lookup_config(Path(workspace.lookup_config_path))

            merged_ttl = working_dir / "merged.ttl"

            # Load entities from merged TTL if it exists, otherwise load from per-doc TTLs
            entities = []
            if merged_ttl.exists():
                logger.info("[%s] Loading entities from merged.ttl", run_id)
                entities = load_entity_information(merged_ttl)
            else:
                logger.info(
                    "[%s] No merged.ttl found, loading from per-document TTLs", run_id
                )
                ttl_files = list(working_dir.glob("*.ttl"))
                if not ttl_files:
                    logger.info("[%s] No TTL files found in working directory", run_id)
                    await update_all("Done", task_name="External Lookup")
                    return
                for ttl_path in ttl_files:
                    entities.extend(load_entity_information(ttl_path))

            if not entities:
                logger.info("[%s] No entities found in merged TTL", run_id)
                await update_all("Done", task_name="Lookup")
                return

            logger.info(
                "[%s] Loaded %d entities for entity lookup",
                run_id,
                len(entities),
            )

            total_results = await asyncio.to_thread(
                run_entity_lookup,
                entities,
                lookup_file_config,
                workspace_id,
                run_id,
                document_ids,
            )

            if not total_results:
                logger.info("[%s] No entity lookup result(s) above threshold", run_id)

            await update_all("Done", task_name="Lookup")
            logger.info(
                "[%s] Entity lookup complete: %d result(s) written",
                run_id,
                total_results,
            )

        except Exception:
            await update_all("Failed", task_name="Lookup")
            logger.exception("[%s] Entity lookup failed", run_id)
            raise
        finally:
            shutil.rmtree(working_dir, ignore_errors=True)
            logger.debug("[%s] Cleaned up working directory", run_id)

    asyncio.run(run())
    return workspace_id
