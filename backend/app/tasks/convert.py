import asyncio
import logging
from pathlib import Path
from uuid import UUID

from app.core.database import TaskSessionLocal as AsyncSessionLocal
from app.pipeline.convert import pdf_to_markdown
from app.repositories.document import DocumentRepository
from app.repositories.run import RunRepository
from app.worker import celery_app

logger = logging.getLogger(__name__)

TMP_BASE = Path("/tmp/ontocurate")


@celery_app.task(bind=True, name="runs.convert_pdf")
def convert_pdf_task(self, document_id: str, run_id: str) -> str:
    """
    - Reads raw PDF bytes from document table
    - Converts PDF to Markdown
    - Writes Markdown to `Document.source_content`
    - Updates run_documents.status
    """
    logger.info("[%s] Converting PDF: document=%s", run_id, document_id)

    tmp_dir = TMP_BASE / self.request.id
    tmp_dir.mkdir(parents=True, exist_ok=True)

    async def process() -> str:
        run_uuid = UUID(run_id)
        document_uuid = UUID(document_id)

        async with AsyncSessionLocal() as session:
            # set status to converting
            await RunRepository(session).update_document_status(
                run_uuid, document_uuid, "converting", celery_task_id=self.request.id
            )

        try:
            async with AsyncSessionLocal() as session:
                doc = await DocumentRepository(session).get_by_id(document_uuid)
                if doc is None:
                    raise ValueError(f"Document {document_id} not found")
                if doc.raw_bytes is None:
                    raise ValueError(f"Document {document_id} has no PDF bytes")

                markdown = pdf_to_markdown(doc.raw_bytes, filename=doc.filename)
                # save the markdown to the document
                await DocumentRepository(session).set_source_content(
                    document_uuid, markdown
                )

            # set status back to queued so the next task (extract) sets extracting
            async with AsyncSessionLocal() as session:
                await RunRepository(session).update_document_status(
                    run_uuid, document_uuid, "queued", task_name="Extracting"
                )

            return document_id

        except Exception:
            async with AsyncSessionLocal() as session:
                await RunRepository(session).update_document_status(
                    run_uuid, document_uuid, "failed"
                )
            logger.exception(
                "[%s] PDF conversion failed: document=%s", run_id, document_id
            )
            raise

    document_id = asyncio.run(process())
    logger.info("[%s] PDF conversion complete: document=%s", run_id, document_id)
    return document_id
