import logging
import shutil
from pathlib import Path

from app.pipeline.entity_alignment import run_cross_document_alignment
from app.worker import celery_app

logger = logging.getLogger(__name__)

TMP_BASE = Path("/tmp/ontocurate")


@celery_app.task(bind=True, name="runs.align_cross_document")
def align_cross_document_task(self, workspace_id: str, run_id: str) -> str:
    """Calls cross_document alignment"""
    logger.info(
        "[%s] Starting cross-document alignment: workspace=%s", run_id, workspace_id
    )
    try:
        run_cross_document_alignment(TMP_BASE / run_id, workspace_id, run_id)
        logger.info("[%s] Cross-document alignment complete", run_id)
    finally:
        shutil.rmtree(TMP_BASE / run_id, ignore_errors=True)  # clean up staged TTLs
    return workspace_id
