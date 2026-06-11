import asyncio
import logging
from pathlib import Path
from uuid import UUID

from app.core.config import settings
from app.core.database import AsyncSessionLocal
from app.pipeline.confidence_annotation import annotate_confidence
from app.pipeline.extraction import extract_document
from app.repositories.document import DocumentRepository
from app.repositories.run import RunRepository
from app.store.writer import write_candidate_statements_from_ttl
from app.worker import celery_app

logger = logging.getLogger(__name__)

DEFAULT_SCHEMA = (
    Path(__file__).parent.parent.parent / "config" / "schemas" / "scholarly_schema.yaml"
)
TMP_BASE = Path("/tmp/ontocurate")


@celery_app.task(bind=True, name="runs.extract_document")
def extract_document_task(self, document_id: str, run_id: str) -> str:
    """
    Extracts RDF triples from a document using OntoGPT
    - Reads document source content from database
    - Calls app.pipeline.extraction.extract_document
    - Chains annotate_and_align_document_task for per-document post-processing
    - Updates task status to "extracting" -> "done" or "failed"
    """
    logger.info("[%s] Extracting: document=%s", run_id, document_id)

    tmp_dir = TMP_BASE / self.request.id
    tmp_dir.mkdir(parents=True, exist_ok=True)

    async def process() -> tuple[Path, str]:
        run_uuid = UUID(run_id)
        document_uuid = UUID(document_id)

        async with AsyncSessionLocal() as session:
            await RunRepository(session).update_document_status(
                run_uuid, document_uuid, "extracting", celery_task_id=self.request.id
            )

        async with AsyncSessionLocal() as session:
            doc = await DocumentRepository(session).get_by_id(document_uuid)
            run = await RunRepository(session).get_by_id(run_uuid)

        try:
            schema_path = (
                Path(run.schema_path) if run and run.schema_path else DEFAULT_SCHEMA
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

            provenance_path = annotate_confidence(
                md_file, ttl_path, tmp_dir, schema_path=schema_path
            )
            write_candidate_statements_from_ttl(
                run_id,
                document_id,
                ttl_path,
                str(doc.workspace_id),
                provenance_path,
                model=model,
            )

            async with AsyncSessionLocal() as session:
                await RunRepository(session).update_document_status(
                    run_uuid, document_uuid, "done"
                )

            logger.info("[%s] Extraction complete: document=%s", run_id, document_id)
            return ttl_path, provenance_path, str(doc.workspace_id), model

        except Exception:
            async with AsyncSessionLocal() as session:
                await RunRepository(session).update_document_status(
                    run_uuid, document_uuid, "failed"
                )
            logger.exception("[%s] Extraction failed: document=%s", run_id, document_id)
            raise

    ttl_path, provenance_path, workspace_id, model = asyncio.run(process())

    return (
        model,
        document_id,
        run_id,
        str(tmp_dir),
        str(ttl_path),
        str(provenance_path),
        workspace_id,
    )
