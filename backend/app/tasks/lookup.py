import asyncio
import logging
from copy import deepcopy
from pathlib import Path
from uuid import UUID

from app.core.database import TaskSessionLocal as AsyncSessionLocal
from app.pipeline.entity_alignment import (
    load_alignment_config,
    precompute_embeddings,
    resolve_type_config,
)
from app.pipeline.metrics.similarity_metrics import (
    combined_similarity,
    semantic_similarity,
    structural_similarity,
    syntactic_similarity,
)
from app.pipeline.utils.turtle_utils import load_entity_information
from app.pipeline.wikidata_client import query_wikidata_for_entities
from app.repositories.run import RunRepository
from app.repositories.workspace import WorkspaceRepository
from app.store.writer import write_lookup_results
from app.worker import celery_app

logger = logging.getLogger(__name__)

TMP_BASE = Path("/tmp/ontocurate")


def build_lookup_config(config: dict) -> dict:
    """
    Build the Wikidata lookup configuration by overlaying
    wikidata_lookup settings onto the normal alignment configuration.

    Entity types without lookup-specific overrides retain their
    normal alignment settings.
    """
    lookup_config = deepcopy(config)
    lookup_overrides = config.get("wikidata_lookup", {})

    lookup_config["settings"] = {
        **config.get("settings", {}),
        **lookup_overrides.get("settings", {}),
    }

    entity_types = deepcopy(config.get("entity_types", {}))

    for entity_type, override in lookup_overrides.get(
        "entity_types",
        {},
    ).items():
        entity_types[entity_type] = {
            **entity_types.get(entity_type, {}),
            **override,
        }

    lookup_config["entity_types"] = entity_types

    return lookup_config


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
            async with AsyncSessionLocal() as session:
                tasks = await RunRepository(session).get_tasks_by_run(UUID(run_id))

            document_ids = [str(task.document_id) for task in tasks]

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
            lookup_config = build_lookup_config(config)

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

                    type_cfg = resolve_type_config(lookup_config, entity_type)
                    weights = type_cfg["weights"]

                    syntactic_score = syntactic_similarity(
                        local_entity,
                        candidate,
                        comparison_predicates=type_cfg["comparison_predicates"],
                        expand_initials=type_cfg["expand_initials"],
                        sparsity_penalty=type_cfg["sparsity_penalty"],
                        sparsity_max_fields=type_cfg["sparsity_max_fields"],
                    )

                    semantic_score = semantic_similarity(
                        local_entity,
                        candidate,
                        semantic_text_predicates=type_cfg["semantic_text_predicates"],
                        embedding_lookup=embedding_lookup,
                    )

                    structural_score = structural_similarity(
                        local_entity,
                        candidate,
                    )

                    score = combined_similarity(
                        local_entity,
                        candidate,
                        weights=weights,
                        comparison_predicates=type_cfg["comparison_predicates"],
                        expand_initials=type_cfg["expand_initials"],
                        threshold=type_cfg["threshold"],
                        semantic_text_predicates=type_cfg["semantic_text_predicates"],
                        sparsity_penalty=type_cfg["sparsity_penalty"],
                        sparsity_max_fields=type_cfg["sparsity_max_fields"],
                        hard_match_predicates=type_cfg["hard_match_predicates"],
                        embedding_lookup=embedding_lookup,
                    )

                    weighted_syntactic = weights.get("syntactic", 0.0) * syntactic_score
                    weighted_semantic = weights.get("semantic", 0.0) * semantic_score
                    weighted_structural = (
                        weights.get("structural", 0.0) * structural_score
                    )

                    weighted_total = (
                        weighted_syntactic + weighted_semantic + weighted_structural
                    )

                    logged_predicates = list(
                        dict.fromkeys(
                            type_cfg["comparison_predicates"]
                            + type_cfg["semantic_text_predicates"]
                        )
                    )

                    local_values = {
                        predicate: local_entity.get("literals", {}).get(predicate, [])
                        for predicate in logged_predicates
                    }

                    candidate_values = {
                        predicate: candidate.get("literals", {}).get(predicate, [])
                        for predicate in logged_predicates
                    }

                    logger.info(
                        "[%s] Wikidata candidate score: "
                        "local=%s local_values=%r "
                        "candidate=%s qid=%s label=%r description=%r type=%s "
                        "syntactic=%.3f*%.2f=%.3f "
                        "semantic=%.3f*%.2f=%.3f "
                        "structural=%.3f*%.2f=%.3f "
                        "weighted_total=%.3f final_score=%.3f "
                        "threshold=%.3f accepted=%s "
                        "candidate_values=%r",
                        run_id,
                        local_uri,
                        local_values,
                        candidate["uri"],
                        candidate.get("wikidata_id"),
                        candidate.get("label"),
                        candidate.get("description"),
                        entity_type,
                        syntactic_score,
                        weights.get("syntactic", 0.0),
                        weighted_syntactic,
                        semantic_score,
                        weights.get("semantic", 0.0),
                        weighted_semantic,
                        structural_score,
                        weights.get("structural", 0.0),
                        weighted_structural,
                        weighted_total,
                        score,
                        type_cfg["threshold"],
                        score >= type_cfg["threshold"],
                        candidate_values,
                    )

                    if abs(weighted_total - score) > 1e-9:
                        logger.info(
                            "[%s] Candidate weighted total %.3f differs from final score %.3f; "
                            "a hard-match predicate may have rejected the candidate",
                            run_id,
                            weighted_total,
                            score,
                        )

                    if score >= type_cfg["threshold"]:
                        alignments.append(
                            (local_uri, candidate["uri"], score, None, "wikidata")
                        )
                        logger.info(
                            "[%s] Wikidata lookup result(s): %s -> %s (score: %.3f)",
                            run_id,
                            local_uri,
                            candidate["uri"],
                            score,
                        )

            if not alignments:
                logger.info("[%s] No Wikidata lookup result(s) above threshold", run_id)
                await update_all("done", task_name="Wikidata Lookup")
                return

            logger.info(
                "[%s] Writing %d Wikidata lookup result(s) to oxigraph",
                run_id,
                len(alignments),
            )

            # Write alignments to oxigraph
            lookup_results = [(local_uri, wikidata_uri, score) for local_uri, wikidata_uri, score, *_ in alignments]
            write_lookup_results(lookup_results, workspace_id, run_id, document_ids=document_ids)

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
