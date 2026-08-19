import logging
from pathlib import Path

import yaml

from app.pipeline.entity_alignment import precompute_embeddings, resolve_type_config
from app.pipeline.lookup_clients.orcid_client import query_orcid_for_entities
from app.pipeline.lookup_clients.wikidata_client import query_wikidata_for_entities
from app.pipeline.metrics.similarity_metrics import combined_similarity
from app.store.writer import write_lookup_results

logger = logging.getLogger(__name__)


def load_lookup_config(config_path: Path) -> dict:
    """Load the lookup YAML configuration."""
    with open(config_path, encoding="utf-8") as file:
        return yaml.safe_load(file) or {}


def derive_lookup_literals(entities: list[dict], lookup_file_config: dict) -> None:
    """
    Adds literals derived from the graph neigborhood to narrow down external lookups.
    Configured through `literal_derivation` in lookup_config.yaml, keyed by entity type.
    Config structure:
    `as`: the literal name to write the derived value to
    `from_literal`: the literal name to take the URI/value from
    `from_relation_in`: the relation name to follow in reverse (e.g. ":author" to find a paper this Person is listed as an author of)
    `from_relation_out`: the relation name to follow forward (e.g. ":affiliation" to find an Organization this Person is associated with)
    `relation_literal`: the literal name to take the URI/value from on the related entity
    """
    derivation_rules = lookup_file_config.get("literal_derivation", {})
    if not derivation_rules:
        return
    entities_by_uri = {entity["uri"]: entity for entity in entities}

    for entity in entities:
        entity_type = entity["types"][0] if entity.get("types") else None
        rules = derivation_rules.get(entity_type)
        if not rules:
            continue
        literals = entity.get("literals", {})
        for rule in rules:
            target = rule["as"]
            if "from_literal" in rule:
                # derive lookup identifier (e.g., orcid) from a literal on the entity itself
                derived = [
                    value.rsplit("/", 1)[-1]
                    for value in literals.get(rule["from_literal"], [])
                ]
            else:
                # Walk backwards/forward to find related literal required for querying the external service
                relation_in = rule.get("from_relation_in")
                if relation_in:
                    related_uris = entity.get("relations_in", {}).get(relation_in, [])
                else:
                    related_uris = entity.get("relations_out", {}).get(
                        rule["from_relation_out"], []
                    )

                derived = [
                    value
                    for related_uri in related_uris
                    for value in entities_by_uri.get(related_uri, {})
                    .get("literals", {})
                    .get(rule["relation_literal"], [])
                ]
            if derived:
                literals[target] = list(dict.fromkeys(derived))
        entity["literals"] = literals


def build_lookup_config(
    lookup_file_config: dict,
    source_key: str,
) -> dict:
    """
    Builds the scoring config for lookup.
    """
    source_config = lookup_file_config.get(source_key, {})
    return {
        "settings": source_config.get("settings", {}),
        "entity_types": {
            entity_type: type_cfg.get("scoring", {})
            for entity_type, type_cfg in source_config.get("entity_types", {}).items()
        },
    }


def score_and_write_results(
    source: str,
    candidates_map: dict[str, list[dict]],
    entities_by_uri: dict[str, dict],
    lookup_config: dict,
    workspace_id: str,
    run_id: str,
    document_ids: list[str],
) -> list[tuple[str, str, float, str | None]]:
    """
    Score one lookup source's candidates against local entities and write matches above threshold to oxigraph.
    Reuses the similarity scoring logic from entity alignment, but with its own weights and thresholds.
    """
    candidate_pairs = [
        (entities_by_uri[local_uri], candidate)
        for local_uri, candidates in candidates_map.items()
        if local_uri in entities_by_uri
        for candidate in candidates
    ]
    embedding_lookup = precompute_embeddings(candidate_pairs, lookup_config)
    logger.info(
        "[%s] Prepared %d %s candidate pair(s) and %d embedding text(s)",
        run_id,
        len(candidate_pairs),
        source,
        len(embedding_lookup),
    )
    lookup_results: list[tuple[str, str, float, str | None]] = []
    for local_uri, candidates in candidates_map.items():
        local_entity = entities_by_uri.get(local_uri)
        if not local_entity:
            continue
        entity_type = (
            local_entity["types"][0] if local_entity.get("types") else "default"
        )
        type_cfg = resolve_type_config(lookup_config, entity_type)
        raw_type_cfg = lookup_config.get("entity_types", {}).get(entity_type, {})
        unresolved_orcid_penalty = raw_type_cfg.get("unresolved_orcid_penalty", 0.0)
        fuzzy_match_penalty = raw_type_cfg.get("fuzzy_match_penalty", 0.0)

        for candidate in candidates:
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

            if candidate.get("orcid_unresolved"):  # penalty for unresolved orcid
                score *= 1.0 - unresolved_orcid_penalty

            if score >= type_cfg["threshold"]:
                if candidate.get(
                    "fuzzy_match"
                ):  # penalty afterwards so it does not affect score thresholding
                    score *= 1.0 - fuzzy_match_penalty
                related_orcid = (candidate.get("literals", {}).get("orcid") or [None])[
                    0
                ]
                lookup_results.append(
                    (local_uri, candidate["uri"], score, related_orcid)
                )
                logger.debug(
                    "[%s] %s lookup result(s): %s -> %s (score: %.3f)",
                    run_id,
                    source,
                    local_uri,
                    candidate["uri"],
                    score,
                )
    if not lookup_results:
        logger.info("[%s] No %s lookup result(s) above threshold", run_id, source)
        return []

    logger.info(
        "[%s] Writing %d %s lookup result(s) to oxigraph",
        run_id,
        len(lookup_results),
        source,
    )
    # Write results to oxigraph
    write_lookup_results(
        [
            (local_uri, candidate_uri, score)
            for local_uri, candidate_uri, score, _ in lookup_results
        ],
        workspace_id,
        source=source,
        run_id=run_id,
        document_ids=document_ids,
    )
    return lookup_results


def run_entity_lookup(
    entities: list[dict],
    lookup_file_config: dict,
    workspace_id: str,
    run_id: str,
    document_ids: list[str],
) -> int:
    """
    Run the full entity lookup pipeline for a set of entities.
    First queries ORCID if configured, then wikidata.
    Returns the total number of results written to the KG across all sources.
    """
    derive_lookup_literals(
        entities, lookup_file_config
    )  # add additional relevant information to entities from neighborhood
    entities_by_uri = {entity["uri"]: entity for entity in entities}
    total_results = 0

    wikidata_config = lookup_file_config.get("wikidata_lookup", {})
    wikidata_settings = wikidata_config.get("settings", {})
    wikidata_entity_types = wikidata_config.get("entity_types", {})

    orcid_config = lookup_file_config.get("orcid_lookup", {})
    orcid_settings = orcid_config.get("settings", {})
    orcid_entity_types = orcid_config.get("entity_types", {})

    # ORCID lookup (Recommendation to only query ORCID if additional institution or publication information is available, so it does not yield ambiguous matches)
    if orcid_entity_types:
        logger.info(
            "[%s] Querying ORCID with limit=%d, delay=%.2fs...",
            run_id,
            orcid_settings.get("candidate_limit", 5),
            orcid_settings.get("request_delay_seconds", 0.1),
        )
        orcid_candidates_map = query_orcid_for_entities(
            entities,
            limit=orcid_settings.get("candidate_limit", 5),
            request_delay_seconds=orcid_settings.get("request_delay_seconds", 0.1),
            entity_type_configs=orcid_entity_types,
            field_names=orcid_settings.get("field_names", {}),
        )

        # Score and write results for ORCID candidates, if found
        if orcid_candidates_map:
            logger.info(
                "[%s] Found ORCID candidates for %d entities",
                run_id,
                len(orcid_candidates_map),
            )
            orcid_lookup_config = build_lookup_config(
                lookup_file_config,
                "orcid_lookup",
            )
            orcid_results = score_and_write_results(
                "orcid",
                orcid_candidates_map,
                entities_by_uri,
                orcid_lookup_config,
                workspace_id,
                run_id,
                document_ids,
            )
            total_results += len(orcid_results)

            # Puts each found ORCID into the corresponding entity's literal, so wikidata can attempt to narrow down its candidates based on that ORCID.
            for local_uri, _, _, possible_orcid in orcid_results:
                if not possible_orcid:
                    continue
                local_entity = entities_by_uri.get(local_uri)
                if not local_entity:
                    continue
                literals = local_entity.setdefault("literals", {})
                literals["orcid"] = list(
                    dict.fromkeys(literals.get("orcid", []) + [possible_orcid])
                )
        else:
            logger.info("[%s] No ORCID candidates found", run_id)

    # Wikidata lookup
    logger.info(
        "[%s] Querying Wikidata with limit=%d, language=%s, delay=%.2fs...",
        run_id,
        wikidata_settings.get("candidate_limit", 5),
        wikidata_settings.get("language", "en"),
        wikidata_settings.get("request_delay_seconds", 0.1),
    )
    wikidata_candidates_map = query_wikidata_for_entities(
        entities,
        limit=wikidata_settings.get("candidate_limit", 5),
        language=wikidata_settings.get("language", "en"),
        request_delay_seconds=wikidata_settings.get("request_delay_seconds", 0.1),
        entity_type_configs=wikidata_entity_types,
    )

    if wikidata_candidates_map:
        logger.info(
            "[%s] Found Wikidata candidates for %d entities",
            run_id,
            len(wikidata_candidates_map),
        )
        wikidata_lookup_config = build_lookup_config(
            lookup_file_config,
            "wikidata_lookup",
        )
        wikidata_results = score_and_write_results(
            "wikidata",
            wikidata_candidates_map,
            entities_by_uri,
            wikidata_lookup_config,
            workspace_id,
            run_id,
            document_ids,
        )
        total_results += len(wikidata_results)
    else:
        logger.info("[%s] No Wikidata candidates found", run_id)

    return total_results
