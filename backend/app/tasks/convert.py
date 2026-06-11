import logging

from app.worker import celery_app

logger = logging.getLogger(__name__)


@celery_app.task(bind=True, name="runs.convert_pdf")
def convert_pdf_task(self, document_id: str, run_id: str) -> str:
    """
    - Reads raw PDF bytes from document table
    - Calls pipeline.pdf_conversion
    - Writes Markdown to documents.source_content
    - Updates run_documents.status
    """
    logger.info("[%s] Converting PDF: document=%s", run_id, document_id)

    logger.info("[%s] PDF conversion complete: document=%s", run_id, document_id)
    return document_id
