import asyncio
import logging
import re
import tempfile
from pathlib import Path
from uuid import UUID

from app.core.database import AsyncSessionLocal
from app.repositories.document import DocumentRepository
from app.repositories.run import RunRepository
from app.worker import celery_app

logger = logging.getLogger(__name__)


def clean_markdown(
    md_text: str,
    remove_placeholders: bool = True,
    remove_picture_text: bool = True,
    remove_figure_captions: bool = False,
    remove_table_captions: bool = False,
    normalize_whitespace: bool = True,
) -> str:
    if remove_placeholders:
        md_text = re.sub(r"\*\*==> picture.*?<==\*\*", "", md_text, flags=re.DOTALL)

    if remove_picture_text:
        md_text = re.sub(
            r"\*\*----- Start of picture text -----\*\*<br>.*?\*\*----- End of picture text -----\*\*<br>",
            "",
            md_text,
            flags=re.DOTALL,
        )

    if remove_figure_captions:
        md_text = re.sub(r"Figure\s+\d+[:.].*", "", md_text)

    if remove_table_captions:
        md_text = re.sub(r"Table\s+\d+[:.].*", "", md_text)

    if normalize_whitespace:
        md_text = re.sub(r"\n{3,}", "\n\n", md_text)
        md_text = re.sub(r"[ \t]{2,}", " ", md_text)

    return md_text


def pdf_to_markdown(raw_bytes: bytes, filename: str | None = None) -> str:
    """Convert PDF bytes to cleaned Markdown using pymupdf4llm.

    Raises ImportError if the dependency is missing.
    """
    try:
        import pymupdf4llm
    except ImportError as exc:
        raise ImportError("pymupdf4llm is required for PDF conversion.") from exc

    with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as tmp_pdf:
        tmp_pdf.write(raw_bytes)
        tmp_pdf.flush()
        tmp_path = tmp_pdf.name

    try:
        pages = pymupdf4llm.to_markdown(tmp_path, page_chunks=True)
        full_md = ""
        for i, page in enumerate(pages):
            page_text = page.get("text", "") if isinstance(page, dict) else ""
            full_md += f"\n\n**==> PAGE NUMBER {i + 1}: <==**\n\n"
            cleaned_text = clean_markdown(page_text)
            full_md += cleaned_text
        return full_md.strip()
    finally:
        try:
            Path(tmp_path).unlink(missing_ok=True)
        except Exception:
            logger.warning("Failed to remove temporary PDF file: %s", tmp_path)


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
                    run_uuid, document_uuid, "queued"
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
