import asyncio
import logging
import shutil
from pathlib import Path
from uuid import UUID

from app.core.config import settings
from app.core.database import AsyncSessionLocal
from app.pipeline.extraction import extract_document
from app.repositories.document import DocumentRepository
from app.repositories.run import RunRepository
from app.worker import celery_app

logger = logging.getLogger(__name__)

_DEFAULT_SCHEMA = (
    Path(__file__).parent.parent.parent / "config" / "schemas" / "scholarly_schema.yaml"
)
_TMP_BASE = Path("/tmp/ontocurate")


@celery_app.task(bind=True, name="runs.extract_document")
def extract_document_task(self, document_id: str, run_id: str) -> str:
    """
    Extracts RDF triples from a document using OntoGPT
    - Reads document source content from database
    - Calls app.pipeline.extraction.extract_document
    - Writes candidate statements (Turtle) to the workspace curation graph
    - Updates task status to "extracting" -> "done" or "failed"
    - Temp Directory gets deleted after writing to database (possible to comment out for debugging)
    """
    logger.info("[%s] Extracting: document=%s", run_id, document_id)

    tmp_dir = _TMP_BASE / self.request.id
    tmp_dir.mkdir(parents=True, exist_ok=True)

    async def _process() -> None:
        run_uuid = UUID(run_id)
        document_uuid = UUID(document_id)

        async with AsyncSessionLocal() as session:
            await RunRepository(session).update_document_status(
                run_uuid, document_uuid, "extracting"
            )

        async with AsyncSessionLocal() as session:
            doc = await DocumentRepository(session).get_by_id(document_uuid)
            run = await RunRepository(session).get_by_id(run_uuid)

        try:
            schema_path = (
                Path(run.schema_path) if run and run.schema_path else _DEFAULT_SCHEMA
            )
            model = (run.model if run and run.model else None) or settings.default_model

            md_file = tmp_dir / f"{Path(doc.filename).stem}.md"
            md_file.write_text(doc.source_content, encoding="utf-8")

            _yaml_path, ttl_path = await asyncio.to_thread(
                extract_document,
                input_path=md_file,
                schema_path=schema_path,
                output_dir=tmp_dir,
                model=model,
                api_base=settings.openai_api_base,
                api_key=settings.openai_api_key,
            )

            # Persist candidate statements into the workspace curation graph
            try:
                from app.store.writer import write_candidate_statements_from_ttl

                write_candidate_statements_from_ttl(
                    str(run_id), str(document_id), ttl_path, str(doc.workspace_id)
                )
            except Exception:
                logger.exception("Failed to write candidate statements to store")

            async with AsyncSessionLocal() as session:
                await RunRepository(session).update_document_status(
                    run_uuid, document_uuid, "done"
                )

            logger.info("[%s] Extraction complete: document=%s", run_id, document_id)

        except Exception:
            async with AsyncSessionLocal() as session:
                await RunRepository(session).update_document_status(
                    run_uuid, document_uuid, "failed"
                )
            logger.exception("[%s] Extraction failed: document=%s", run_id, document_id)
            raise

    try:
        asyncio.run(_process())

    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)

    return document_id
