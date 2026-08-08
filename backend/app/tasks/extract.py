import asyncio
import logging
from pathlib import Path
from uuid import UUID

from app.core.config import settings
from app.core.database import TaskSessionLocal as AsyncSessionLocal
from app.pipeline.confidence_annotation import annotate_confidence
from app.pipeline.extraction import extract_document
from app.repositories.document import DocumentRepository
from app.repositories.run import RunRepository
from app.repositories.workspace import WorkspaceRepository
from app.store.writer import write_candidate_statements_from_ttl
from app.worker import celery_app

logger = logging.getLogger(__name__)

TMP_BASE = Path("/tmp/ontocurate")


@celery_app.task(bind=True, name="runs.extract_document")
def extract_document_task(self, document_id: str, run_id: str) -> str:
    """
    Extracts RDF triples from a document using OntoGPT
    - Reads document source content from database
    - Calls app.pipeline.extraction.extract_document
    - Chains align_document_task for per-document post-processing
    """
    logger.info("[%s] Extracting: document=%s", run_id, document_id)

    tmp_dir = TMP_BASE / self.request.id
    tmp_dir.mkdir(parents=True, exist_ok=True)

    skipped = (None, document_id, run_id, None, None, None, None)

    async def process() -> tuple[Path, str, str, str] | None:
        run_uuid = UUID(run_id)
        document_uuid = UUID(document_id)

        try:
            async with AsyncSessionLocal() as session:
                existing = await RunRepository(session).get_task(
                    run_uuid, document_uuid
                )
                if existing is not None and existing.status == "Failed":
                    logger.info(
                        "[%s] Skipping extraction, upstream stage failed: document=%s",
                        run_id,
                        document_id,
                    )
                    return None

                await RunRepository(session).update_document_status(
                    run_uuid,
                    document_uuid,
                    "Running",
                    celery_task_id=self.request.id,
                    task_name="Extraction",
                )

                doc = await DocumentRepository(session).get_by_id(document_uuid)
                if doc is None:
                    raise ValueError(f"Document {document_id} not found")
                workspace = await WorkspaceRepository(session).get_by_id(
                    doc.workspace_id
                )
                run = await RunRepository(session).get_by_id(run_uuid)

            schema_path = workspace.schema_path
            model = (run.model if run else None) or settings.default_model

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
                max_text_length=settings.max_text_length,
                max_output_tokens=settings.max_output_tokens,
                temperature=settings.extraction_temperature,
            )

            provenance_path = annotate_confidence(
                md_file,
                ttl_path,
                tmp_dir,
                config_path=Path(workspace.provenance_config_path),
            )
            await asyncio.to_thread(
                write_candidate_statements_from_ttl,
                run_id,
                document_id,
                ttl_path,
                str(doc.workspace_id),
                provenance_path,
                model=model,
            )

            async with AsyncSessionLocal() as session:
                await RunRepository(session).update_document_status(
                    run_uuid,
                    document_uuid,
                    "Queued",
                    task_name="Inner Document Alignment",
                )

            logger.info("[%s] Extraction complete: document=%s", run_id, document_id)
            return ttl_path, provenance_path, str(doc.workspace_id), model

        except Exception:
            async with AsyncSessionLocal() as session:
                await RunRepository(session).update_document_status(
                    run_uuid, document_uuid, "Failed"
                )
            logger.exception("[%s] Extraction failed: document=%s", run_id, document_id)
            return None

    result = asyncio.run(process())
    if result is None:
        return skipped

    ttl_path, provenance_path, workspace_id, model = result
    return (
        model,
        document_id,
        run_id,
        str(tmp_dir),
        str(ttl_path),
        str(provenance_path),
        workspace_id,
    )
