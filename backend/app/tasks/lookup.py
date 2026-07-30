import asyncio
import logging
import shutil
from copy import deepcopy
from pathlib import Path
from uuid import UUID

import yaml

from app.core.database import TaskSessionLocal as AsyncSessionLocal
from app.pipeline.entity_alignment import (
    load_alignment_config,
    precompute_embeddings,
    resolve_type_config,
)
from app.pipeline.metrics.similarity_metrics import combined_similarity
from app.pipeline.utils.turtle_utils import load_entity_information
from app.pipeline.wikidata_client import query_wikidata_for_entities
from app.repositories.run import RunRepository
from app.repositories.workspace import WorkspaceRepository
from app.store.writer import write_lookup_results
from app.worker import celery_app

logger = logging.getLogger(__name__)

TMP_BASE = Path("/tmp/ontocurate")


def load_lookup_config(config_path: Path) -> dict:
    """Load the lookup YAML configuration."""
    with open(config_path, encoding="utf-8") as file:
        return yaml.safe_load(file) or {}


def build_lookup_config(
    alignment_config: dict,
    lookup_file_config: dict,
) -> dict:
    """
    Build the effective scoring configuration for Wikidata lookup.

    The normal alignment configuration provides the defaults.
    The Wikidata lookup configuration provides lookup-specific overrides.
    """
    effective_config = deepcopy(alignment_config)

    wikidata_config = lookup_file_config.get(
        "wikidata_lookup",
        {},
    )

    entity_types = deepcopy(alignment_config.get("entity_types", {}))

    for entity_type, lookup_type_config in wikidata_config.get(
        "entity_types",
        {},
    ).items():
        scoring_overrides = lookup_type_config.get(
            "scoring",
            {},
        )

        if not scoring_overrides:
            continue

        entity_types[entity_type] = {
            **entity_types.get(entity_type, {}),
            **scoring_overrides,
        }

    effective_config["entity_types"] = entity_types

    return effective_config


@celery_app.task(bind=True, name="runs.lookup_wikidata")
def lookup_wikidata_task(self, workspace_id: str, run_id: str) -> str:
    """
    Wikidata Entity Lookup
    - Loads merged TTL from cross-document alignment
    - Queries Wikidata for candidate entities
    - Scores candidates against local entities using similarity metrics
    - Writes proposed Wikidata owl:sameAs links to Oxigraph
    """
    logger.info("[%s] Starting Wikidata lookup: workspace=%s", run_id, workspace_id)

    async def run() -> None:
        async def update_all(status: str, task_name: str | None = None) -> None:
            """Update status for all documents in the run."""
            async with AsyncSessionLocal() as session:
                tasks = await RunRepository(session).get_tasks_by_run(UUID(run_id))
            for t in tasks:
                if t.status == "Failed":
                    # Skip updating failed tasks
                    continue
                async with AsyncSessionLocal() as session:
                    await RunRepository(session).update_document_status(
                        UUID(run_id), t.document_id, status, task_name=task_name
                    )

        await update_all("Running", task_name="Wikidata Lookup")
        working_dir = TMP_BASE / run_id
        try:
            async with AsyncSessionLocal() as session:
                tasks = await RunRepository(session).get_tasks_by_run(UUID(run_id))

            document_ids = [str(task.document_id) for task in tasks]

            # Load workspace config
            async with AsyncSessionLocal() as session:
                workspace = await WorkspaceRepository(session).get_by_id(
                    UUID(workspace_id)
                )

            # Load alignment config for scoring
            alignment_config_path = Path(workspace.alignment_config_path)
            lookup_config_path = Path(workspace.lookup_config_path)

            alignment_config = load_alignment_config(alignment_config_path)
            lookup_file_config = load_lookup_config(lookup_config_path)

            lookup_config = build_lookup_config(
                alignment_config,
                lookup_file_config,
            )

            wikidata_config = lookup_file_config.get("wikidata_lookup", {})
            lookup_settings = wikidata_config.get("settings", {})
            lookup_entity_types = wikidata_config.get("entity_types", {})

            candidate_limit = lookup_settings.get(
                "candidate_limit",
                5,
            )

            language = lookup_settings.get(
                "language",
                "en",
            )

            request_delay_seconds = lookup_settings.get(
                "request_delay_seconds",
                0.1,
            )

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
                    await update_all("Done", task_name="Wikidata Lookup")
                    return
                for ttl_path in ttl_files:
                    entities.extend(load_entity_information(ttl_path))

            if not entities:
                logger.info("[%s] No entities found in merged TTL", run_id)
                await update_all("Done", task_name="Wikidata Lookup")
                return

            logger.info(
                "[%s] Loaded %d entities for Wikidata lookup",
                run_id,
                len(entities),
            )

            # Query Wikidata for candidates
            logger.info(
                "[%s] Querying Wikidata with limit=%d, language=%s, delay=%.2fs...",
                run_id,
                candidate_limit,
                language,
                request_delay_seconds,
            )
            wikidata_candidates_map = await asyncio.to_thread(
                query_wikidata_for_entities,
                entities,
                limit=candidate_limit,
                language=language,
                request_delay_seconds=request_delay_seconds,
                entity_type_configs=lookup_entity_types,
            )

            if not wikidata_candidates_map:
                logger.info("[%s] No Wikidata candidates found", run_id)
                await update_all("Done", task_name="Wikidata Lookup")
                return

            logger.info(
                "[%s] Found Wikidata candidates for %d entities",
                run_id,
                len(wikidata_candidates_map),
            )

            # Build all local-Wikidata candidate pairs so semantic embeddings can be computed in one batch.
            entities_by_uri = {entity["uri"]: entity for entity in entities}

            candidate_pairs = [
                (entities_by_uri[local_uri], candidate)
                for local_uri, candidates in wikidata_candidates_map.items()
                if local_uri in entities_by_uri
                for candidate in candidates
            ]

            embedding_lookup = await asyncio.to_thread(
                precompute_embeddings,
                candidate_pairs,
                lookup_config,
            )

            logger.info(
                "[%s] Prepared %d Wikidata candidate pair(s) and %d embedding text(s)",
                run_id,
                len(candidate_pairs),
                len(embedding_lookup),
            )

            # Score local entities against Wikidata candidates
            lookup_results: list[tuple[str, str, float]] = []
            for local_uri, wikidata_candidates in wikidata_candidates_map.items():
                # Find the local entity
                local_entity = entities_by_uri.get(local_uri)

                if not local_entity:
                    continue

                entity_type = (
                    local_entity["types"][0] if local_entity.get("types") else "default"
                )

                type_cfg = resolve_type_config(lookup_config, entity_type)

                # Score each candidate
                for candidate in wikidata_candidates:
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
                        embedding_lookup=embedding_lookup,
                    )

                    if score >= type_cfg["threshold"]:
                        lookup_results.append((local_uri, candidate["uri"], score))
                        logger.debug(
                            "[%s] Wikidata lookup result(s): %s -> %s (score: %.3f)",
                            run_id,
                            local_uri,
                            candidate["uri"],
                            score,
                        )

            if not lookup_results:
                logger.info("[%s] No Wikidata lookup result(s) above threshold", run_id)
                await update_all("Done", task_name="Wikidata Lookup")
                return

            logger.info(
                "[%s] Writing %d Wikidata lookup result(s) to oxigraph",
                run_id,
                len(lookup_results),
            )

            # Write lookup_results to oxigraph
            write_lookup_results(
                lookup_results, workspace_id, run_id, document_ids=document_ids
            )

            await update_all("Done", task_name="Wikidata Lookup")
            logger.info("[%s] Wikidata lookup complete", run_id)

        except Exception:
            await update_all("Failed")
            logger.exception("[%s] Wikidata lookup failed", run_id)
            raise
        finally:
            shutil.rmtree(working_dir, ignore_errors=True)
            logger.debug("[%s] Cleaned up working directory", run_id)

    asyncio.run(run())
    return workspace_id
