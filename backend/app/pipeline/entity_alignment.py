import logging
from collections import defaultdict
from pathlib import Path

import yaml
from rdflib import Graph, URIRef
from rdflib.namespace import OWL

from app.pipeline.metrics.similarity_metrics import (
    combined_similarity,
    get_embeddings_batch,
    semantic_text_pair,
)
from app.pipeline.utils.turtle_utils import load_entity_information
from app.store.queries import get_existing_alignment_pairs, get_prior_entities
from app.store.writer import write_alignment_results

logger = logging.getLogger(__name__)


def validate_weights(weights: dict, label: str) -> None:
    """Raise Exception if values do not sum to approximately 1.0."""
    if not weights:
        return
    total = sum(weights.values())
    if abs(total - 1.0) > 1e-6:
        raise ValueError(f"Weights in '{label}' must sum to 1.0, got {total:.6f}")


def load_alignment_config(
    config_path: Path,
) -> dict:
    """
    Loads and validates the alignment yaml config.
    Returns settings dict.
    """
    with open(config_path) as f:
        config = yaml.safe_load(f)

    settings = config.get("settings", {})
    validate_weights(settings.get("default_weights", {}), "settings.default_weights")
    for type_name, type_cfg in config.get("entity_types", {}).items():
        if "weights" in type_cfg:
            validate_weights(type_cfg["weights"], f"entity_types.{type_name}.weights")
    return config


def resolve_type_config(config: dict, entity_type: str) -> dict:
    """Return relevant parts of config for an entity type."""
    settings = config.get("settings", {})
    overrides = config.get("entity_types", {}).get(entity_type, {})

    return {
        "threshold": overrides.get(
            "threshold",
            settings.get("default_threshold", 0.8),
        ),
        "weights": overrides.get(
            "weights",
            settings.get(
                "default_weights",
                {"syntactic": 0.5, "semantic": 0.35, "structural": 0.15},
            ),
        ),
        "comparison_predicates": overrides.get(
            "comparison_predicates",
            settings.get("default_comparison_predicates", ["name"]),
        ),
        "semantic_text_predicates": overrides.get(
            "semantic_text_predicates",
            settings.get("default_semantic_text_predicates", ["name"]),
        ),
        "expand_initials": overrides.get(
            "expand_initials",
            settings.get("default_expand_initials", False),
        ),
        "sparsity_penalty": overrides.get(
            "sparsity_penalty",
            settings.get("default_sparsity_penalty", 1.0),
        ),
        "sparsity_max_fields": overrides.get(
            "sparsity_max_fields",
            settings.get("default_sparsity_max_fields", 1),
        ),
        "hard_match_predicates": overrides.get(
            "hard_match_predicates",
            settings.get("default_hard_match_predicates", None),
        ),
    }


def generate_candidate_pairs(
    entities: list[dict],
    config: dict,
) -> list[tuple[dict, dict]]:
    """
    Produce candidate pairs for alignment by grouping entities of the same type.
    Buckets entities by their type and applies strict-identifier blocking rules
    - If any strict-identifier value is shared between the two entities pair is always kept
    - If both entities have values for the same strict-identifier field and those
      values do not overlap -> pair is always dropped
    - everything beyond this is passed to scoring
    """

    global_unique_keys = set(config.get("settings", {}).get("unique_keys", []))

    buckets: dict[str, list[dict]] = defaultdict(list)
    for entity in entities:
        if entity["types"]:
            buckets[entity["types"][0]].append(entity)
    seen = set()
    pairs = []
    for type_name, bucket in buckets.items():
        if len(bucket) < 2:
            continue

        type_unique_keys = set(
            config.get("entity_types", {}).get(type_name, {}).get("unique_keys", [])
        )
        hard_id_fields = global_unique_keys | type_unique_keys
        # Generate all pairs within the bucket and apply strict-identifier rules
        for i, a in enumerate(bucket):
            for b in bucket[i + 1 :]:
                if a["uri"] == b["uri"]:
                    # avoids self-pairs
                    continue

                pair_id = frozenset({a["uri"], b["uri"]})
                if pair_id in seen:
                    continue

                hard_match = False
                hard_conflict = False
                for field in hard_id_fields:
                    av = {v for v in a["literals"].get(field, []) if v.strip()}
                    bv = {v for v in b["literals"].get(field, []) if v.strip()}
                    if av and bv:
                        if av & bv:
                            hard_match = True
                            break
                        else:
                            hard_conflict = True
                if hard_conflict and not hard_match:
                    continue
                seen.add(pair_id)
                pairs.append((a, b))
    return pairs


def precompute_embeddings(
    candidates: list[tuple[dict, dict]],
    config: dict,
) -> dict[str, list[float]]:
    """
    Precomputes embeddings for all candidate pairs where semantic similarity
    is enabled and returns a lookup dict {text: embedding}.
    Entity Embedding is computed on a joint string of all literals appearing in both entities.
    """
    texts = set()
    for a, b in candidates:
        type_cfg = resolve_type_config(config, a["types"][0])
        if type_cfg["weights"].get("semantic", 0.0) <= 0:
            continue
        pair_texts = semantic_text_pair(a, b, type_cfg["semantic_text_predicates"])
        if pair_texts:
            texts.update(pair_texts)
    if not texts:
        return {}
    return get_embeddings_batch(list(texts))


def similarity_computation(
    candidates: list[tuple[dict, dict]],
    config: dict,
) -> list[tuple[dict, dict, float]]:
    """
    Compute a combined similarity score for every candidate pair with given config.
    Skips metrics with configured weight 0.0
    """
    embedding_lookup = precompute_embeddings(candidates, config)

    results: list[tuple[dict, dict, float]] = []
    for a, b in candidates:
        type_cfg = resolve_type_config(config, a["types"][0])
        score = combined_similarity(
            a,
            b,
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
        results.append((a, b, score))
    return results


def candidate_filtering(
    candidates: list[tuple[dict, dict, float]],
    config: dict,
) -> list[tuple[dict, dict, float]]:
    """Discards candidate pairs whose similarity score falls below threshold"""
    return [
        (a, b, score)
        for a, b, score in candidates
        if score >= resolve_type_config(config, a["types"][0])["threshold"]
    ]


def score_and_filter(
    candidates: list[tuple[dict, dict]],
    config: dict,
) -> list[tuple[str, str, float, str | None, str | None]]:
    """Score candidates and return only pairs above threshold as (uri_a, uri_b, score, src_doc_a, src_doc_b)."""
    scored = similarity_computation(candidates, config)
    filtered = candidate_filtering(scored, config)
    return [
        (a["uri"], b["uri"], score, a.get("source_document"), b.get("source_document"))
        for a, b, score in filtered
    ]


def write_same_as_triples(
    ttl_path: Path,
    alignments: list[tuple[str, str, float]],
    output_path: Path,
) -> Path:
    """Append owl:sameAs triples to a Turtle file for each aligned pair (so it can be used in further processes without accessing oxigraph)"""
    g = Graph()
    g.parse(ttl_path, format="turtle")
    for uri_a, uri_b, score in alignments:
        g.add((URIRef(uri_a), OWL.sameAs, URIRef(uri_b)))
    g.serialize(destination=output_path, format="turtle")
    return output_path


def run_inner_document_alignment(
    ttl_path: Path,
    workspace_id: str,
    run_id: str,
    config_path: Path,
    document_id: str | None = None,
) -> Path:
    """
    Inner document alignment.
    Writes its results back into its ttl, as well as to oxigraph
    """
    config = load_alignment_config(config_path)
    entities = load_entity_information(ttl_path)
    if not entities:
        return ttl_path
    candidates = generate_candidate_pairs(entities, config)
    if not candidates:
        logger.info("[%s] No candidate pairs found, skipping alignment", run_id)
        return ttl_path
    alignments = score_and_filter(candidates, config)
    if not alignments:
        logger.info("[%s] No pairs above threshold, skipping alignment", run_id)
        return ttl_path

    logger.info("[%s] Writing %d owl:sameAs triple(s)", run_id, len(alignments))
    # Write results to local ttl and oxigraph
    triples = [(uri_a, uri_b, score) for uri_a, uri_b, score, *_ in alignments]
    write_same_as_triples(ttl_path, triples, ttl_path)
    write_alignment_results(
        triples, workspace_id, run_id, [document_id] if document_id else None
    )
    return ttl_path


def run_cross_document_alignment(
    working_dir: Path,
    workspace_id: str,
    run_id: str,
    config_path: Path,
) -> None:
    """
    Cross document entity alignment loading all per-document aligned ttls and performing entity alignment between them again.
    Additionally, it checks for entities from previous runs and aligns them with the current run.
    """
    # merged.ttl is output of this function and will be used by further tasks
    ttl_files = [p for p in working_dir.glob("*.ttl") if p.name != "merged.ttl"]

    entities = []
    for ttl_path in ttl_files:
        for entity in load_entity_information(ttl_path):
            entity["source_document"] = ttl_path.stem
            entity["is_prior"] = False
            entities.append(entity)
    # Get entities from prior runs (excluding current run documents)
    prior_entities = get_prior_entities(
        workspace_id, exclude_document_ids=[p.stem for p in ttl_files]
    )
    entities.extend(prior_entities)

    config = load_alignment_config(config_path)
    candidates = [
        (a, b)
        for a, b in generate_candidate_pairs(entities, config)
        if not (
            a.get("is_prior") and b.get("is_prior")
        )  # exclude pairs of entities that are both from prior runs
        and a.get("source_document")
        != b.get(
            "source_document"
        )  # exclude pairs of the same document running in inner-document alignment
    ]

    # Resolve existing alignment pairs to avoid duplicates
    alignments = score_and_filter(candidates, config)
    existing_pairs = get_existing_alignment_pairs(workspace_id)
    alignments = [
        (uri_a, uri_b, score, src_a, src_b)
        for uri_a, uri_b, score, src_a, src_b in alignments
        if frozenset({uri_a, uri_b}) not in existing_pairs
    ]

    if not alignments:
        return

    logger.info(
        "[%s] Cross-document: writing %d owl:sameAs triple(s)",
        run_id,
        len(alignments),
    )

    # Merge all per-document TTLs into a single graph and append sameAs triples
    triples = [(uri_a, uri_b, score) for uri_a, uri_b, score, *_ in alignments]
    merged_graph = Graph()
    for ttl_path in ttl_files:
        merged_graph.parse(ttl_path, format="turtle")
    for uri_a, uri_b, score in triples:
        merged_graph.add((URIRef(uri_a), OWL.sameAs, URIRef(uri_b)))
    merged_path = working_dir / "merged.ttl"
    merged_graph.serialize(destination=merged_path, format="turtle")

    # Write alignment results to oxigraph
    grouped = defaultdict(list)
    for uri_a, uri_b, score, src_a, src_b in alignments:
        key = tuple(sorted([src_a or "unknown", src_b or "unknown"]))
        grouped[key].append((uri_a, uri_b, score))

    for (doc_a, doc_b), pairs in grouped.items():
        write_alignment_results(pairs, workspace_id, run_id, [doc_a, doc_b])
