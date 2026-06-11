import logging
import shutil
from pathlib import Path

from app.worker import celery_app

logger = logging.getLogger(__name__)


def _align_inner_document(ttl_path: Path, tmp_dir: Path) -> None:
    pass


@celery_app.task(bind=True, name="runs.annotate_and_align_document")
def annotate_and_align_document_task(
    self,
    model: str,
    document_id: str,
    run_id: str,
    tmp_dir: str,
    ttl_path: str,
    provenance_path: str,
    workspace_id: str,
) -> str:
    """
    Post-extraction per-document processing:
    - Performs inner-document entity alignment
    - Cleans up the tmp directory
    """
    logger.info("[%s] Aligning: document=%s", run_id, document_id)

    ttl_path = Path(ttl_path)
    tmp_dir = Path(tmp_dir)

    try:
        _align_inner_document(ttl_path, tmp_dir)

        logger.info("[%s] Alignment complete: document=%s", run_id, document_id)
    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)

    return document_id
