import asyncio
import logging
from pathlib import Path
from uuid import UUID

from app.core.database import TaskSessionLocal as AsyncSessionLocal
from app.pipeline.entity_alignment import load_alignment_config
from app.pipeline.metrics.similarity_metrics import combined_similarity
from app.pipeline.utils.turtle_utils import load_entity_information
from app.pipeline.wikidata_client import query_wikidata_for_entities
from app.repositories.run import RunRepository
from app.repositories.workspace import WorkspaceRepository
from app.store.writer import write_alignment_results
from app.worker import celery_app

logger = logging.getLogger(__name__)

TMP_BASE = Path("/tmp/ontocurate")


@celery_app.task(bind=True, name="runs.lookup_wikidata")
def lookup_wikidata_task(self, workspace_id: str, run_id: str) -> str:
    """
    Wikidata Entity Lookup
    - Loads merged TTL from cross-document alignment
    - Queries Wikidata for candidate entities
    - Scores candidates against local entities using similarity metrics
    - Writes owl:sameAs alignments to oxigraph
    """
    logger.info("[%s] Starting Wikidata lookup: workspace=%s", run_id, workspace_id)

    async def run() -> None:
        async def update_all(status: str, task_name: str | None = None) -> None:
            """Update status for all documents in the run."""
            async with AsyncSessionLocal() as session:
                tasks = await RunRepository(session).get_tasks_by_run(UUID(run_id))
            for t in tasks:
                async with AsyncSessionLocal() as session:
                    await RunRepository(session).update_document_status(
                        UUID(run_id), t.document_id, status, task_name=task_name
                    )

        await update_all("aligning", task_name="Wikidata Lookup")
        try:
            # Load workspace config
            async with AsyncSessionLocal() as session:
                workspace = await WorkspaceRepository(session).get_by_id(
                    UUID(workspace_id)
                )

            working_dir = TMP_BASE / run_id
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
                    await update_all("done", task_name="Wikidata Lookup")
                    return
                for ttl_path in ttl_files:
                    entities.extend(load_entity_information(ttl_path))

            if not entities:
                logger.info("[%s] No entities found in merged TTL", run_id)
                await update_all("done", task_name="Wikidata Lookup")
                return

            logger.info(
                "[%s] Loaded %d entities from merged TTL", run_id, len(entities)
            )

            # Query Wikidata for candidates
            logger.info("[%s] Querying Wikidata for candidates...", run_id)
            wikidata_candidates_map = await asyncio.to_thread(
                query_wikidata_for_entities, entities, limit=5
            )

            if not wikidata_candidates_map:
                logger.info("[%s] No Wikidata candidates found", run_id)
                await update_all("done", task_name="Wikidata Lookup")
                return

            logger.info(
                "[%s] Found Wikidata candidates for %d entities",
                run_id,
                len(wikidata_candidates_map),
            )

            # Load alignment config for scoring
            config_path = workspace.alignment_config_path
            config = load_alignment_config(Path(config_path))

            # Score local entities against Wikidata candidates
            alignments = []
            for local_uri, wikidata_candidates in wikidata_candidates_map.items():
                # Find the local entity
                local_entity = next(
                    (e for e in entities if e["uri"] == local_uri), None
                )
                if not local_entity:
                    continue

                entity_type = (
                    local_entity["types"][0] if local_entity.get("types") else "default"
                )

                # Score each candidate
                for candidate in wikidata_candidates:
                    from app.pipeline.entity_alignment import resolve_type_config

                    type_cfg = resolve_type_config(config, entity_type)
                    score = combined_similarity(
                        local_entity,
                        candidate,
                        weights=type_cfg["weights"],
                        comparison_predicates=type_cfg["comparison_predicates"],
                        expand_initials=type_cfg["expand_initials"],
                        threshold=type_cfg["threshold"],
                        semantic_text_predicates=type_cfg["semantic_text_predicates"],
                        sparsity_penalty=type_cfg["sparsity_penalty"],
                        sparsity_max_fields=type_cfg["sparsity_max_fields"],
                        hard_match_predicates=type_cfg["hard_match_predicates"],
                    )

                    if score >= type_cfg["threshold"]:
                        alignments.append(
                            (local_uri, candidate["uri"], score, None, "wikidata")
                        )
                        logger.info(
                            "[%s] Wikidata alignment: %s -> %s (score: %.3f)",
                            run_id,
                            local_uri,
                            candidate["uri"],
                            score,
                        )

            if not alignments:
                logger.info("[%s] No Wikidata alignments above threshold", run_id)
                await update_all("done", task_name="Wikidata Lookup")
                return

            logger.info(
                "[%s] Writing %d Wikidata alignment(s) to oxigraph",
                run_id,
                len(alignments),
            )

            # Write alignments to oxigraph
            triples = [(uri_a, uri_b, score) for uri_a, uri_b, score, *_ in alignments]
            write_alignment_results(triples, workspace_id, run_id, document_ids=None)

            # append sameAs triples to merged.ttl if needed
            write_same_as_triples(merged_ttl, triples, merged_ttl)

            await update_all("done", task_name="Wikidata Lookup")
            logger.info("[%s] Wikidata lookup complete", run_id)

        except Exception:
            await update_all("failed")
            logger.exception("[%s] Wikidata lookup failed", run_id)
            raise
        finally:
            # Clean up temporary files after lookup completes
            import shutil

            shutil.rmtree(working_dir, ignore_errors=True)
            logger.debug("[%s] Cleaned up working directory", run_id)

    asyncio.run(run())
    return workspace_id
