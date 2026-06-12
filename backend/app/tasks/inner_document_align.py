import logging
import shutil
from pathlib import Path

from app.pipeline.entity_alignment import run_inner_document_alignment
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

    logger.info("[%s] Aligning: document=%s", run_id, document_id)

    ttl_path = Path(ttl_path)
    tmp_dir = Path(tmp_dir)

    try:
        run_inner_document_alignment(ttl_path, workspace_id, run_id, document_id)

        # Stage the TTL so cross-document alignment can read it after all docs complete.
        working_dir = TMP_BASE / run_id
        working_dir.mkdir(parents=True, exist_ok=True)
        shutil.copy2(ttl_path, working_dir / f"{document_id}.ttl")

        logger.info("[%s] Alignment complete: document=%s", run_id, document_id)
    except Exception:
        logger.exception("[%s] Alignment failed: document=%s", run_id, document_id)
        raise
    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)

    return document_id
