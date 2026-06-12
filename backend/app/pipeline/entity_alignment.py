import logging
from collections import defaultdict
from pathlib import Path

import yaml
from rdflib import Graph, URIRef
from rdflib.namespace import OWL

from app.pipeline.metrics.similarity_metrics import combined_similarity
from app.pipeline.utils.turtle_utils import load_entity_information
from app.store.writer import write_alignment_results

logger = logging.getLogger(__name__)

# default config path
DEFAULT_CONFIG = (
    Path(__file__).parent.parent.parent / "config" / "schemas" / "alignment_config.yaml"
)


def validate_weights(weights: dict, label: str) -> None:
    """Raise Exception if values do not sum to approximately 1.0"""
    if not weights:
        return
    total = sum(weights.values())
    if abs(total - 1.0) > 1e-6:
        raise ValueError(f"Weights in '{label}' must sum to 1.0, got {total:.6f}")


def load_alignment_config(
    config_path: Path | None = None,
) -> dict:
    """Load and validate the alignment yaml config.
    Returns settings dict
    """
    with open(config_path or DEFAULT_CONFIG) as f:
        config = yaml.safe_load(f)

    settings = config.get("settings", {})

    validate_weights(settings.get("default_weights", {}), "settings.default_weights")

    for type_name, type_cfg in config.get("entity_types", {}).items():
        if "weights" in type_cfg:
            validate_weights(type_cfg["weights"], f"entity_types.{type_name}.weights")

    return config


def resolve_type_config(config: dict, entity_type: str) -> dict:
    """Return relevant parts of config for an entity type"""
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
        "comparison_keys": overrides.get(
            "comparison_keys",
            settings.get("default_comparison_keys", ["name"]),
        ),
        "semantic_text_fields": overrides.get(
            "semantic_text_fields",
            settings.get("default_semantic_text_fields", ["name"]),
        ),
        "expand_initials": overrides.get(
            "expand_initials",
            settings.get("default_expand_initials", False),
        ),
    }


def generate_candidate_pairs(
    entities: list[dict],
    config: dict,
) -> list[tuple[dict, dict]]:
    """Produce candidate pairs for alignment by grouping entities of the same type.
    Buckets entities by their type and applies strict-identifier blocking rules
    - If any strict-identifier value is shared between the two entities pair is always kept
    - If both entities have values for the same strict-identifier field and those
      values do not overlap -> pair is always dropped
    -everything else is passed to scoring
    """

    hard_id_fields = set(config.get("settings", {}).get("unique_keys", []))

    buckets: dict[str, list[dict]] = defaultdict(list)
    for entity in entities:
        if entity["types"]:
            buckets[entity["types"][0]].append(entity)

    seen = set()
    pairs = []

    for type_name, bucket in buckets.items():
        if len(bucket) < 2:
            continue

        for i, a in enumerate(bucket):
            for b in bucket[i + 1 :]:
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


def similarity_computation(
    candidates: list[tuple[dict, dict]],
    config: dict,
) -> list[tuple[dict, dict, float]]:
    """Compute a combined similarity score for every candidate pair.
    Skips metrics with configured weight 0.0
    """

    results: list[tuple[dict, dict, float]] = []
    for a, b in candidates:
        type_cfg = resolve_type_config(config, a["types"][0])
        score = combined_similarity(
            a,
            b,
            weights=type_cfg["weights"],
            comparison_keys=type_cfg["comparison_keys"],
            expand_initials=type_cfg["expand_initials"],
            threshold=type_cfg["threshold"],
            semantic_text_fields=type_cfg["semantic_text_fields"],
        )
        results.append((a, b, score))
    return results


def candidate_filtering(
    candidates: list[tuple[dict, dict, float]],
    config: dict,
) -> list[tuple[dict, dict, float]]:
    """Discars candidate pairs whose similarity score falls below threshold"""
    return [
        (a, b, score)
        for a, b, score in candidates
        if score >= resolve_type_config(config, a["types"][0])["threshold"]
    ]


def write_same_as_triples(
    ttl_path: Path,
    alignments: list[tuple[str, str, float]],
    output_path: Path,
) -> Path:
    """Append owl:sameAs triples to a Turtle file for each aligned pair (so it can be used in further processes without accessing oxigraph)"""

    g = Graph()
    g.parse(ttl_path, format="turtle")

    for uri_a, uri_b, _score in alignments:
        g.add((URIRef(uri_a), OWL.sameAs, URIRef(uri_b)))

    g.serialize(destination=output_path, format="turtle")
    return output_path


def run_inner_document_alignment(
    ttl_path: Path,
    workspace_id: str,
    run_id: str,
    document_id: str | None = None,
    config_path: Path | None = None,
) -> Path:
    """Inner document alignment. Writes its results back into its ttl, as well as to oxigraph"""

    config = load_alignment_config(config_path)
    entities = load_entity_information(ttl_path)

    if not entities:
        return ttl_path

    candidates = generate_candidate_pairs(entities, config)

    if not candidates:
        logger.info("[%s] No candidate pairs found, skipping alignment", run_id)
        return ttl_path

    scored = similarity_computation(candidates, config)
    filtered = candidate_filtering(scored, config)

    if not filtered:
        logger.info("[%s] No pairs above threshold, skipping alignment", run_id)
        return ttl_path

    alignments = [(a["uri"], b["uri"], score) for a, b, score in filtered]

    logger.info("[%s] Writing %d owl:sameAs triple(s)", run_id, len(alignments))
    write_same_as_triples(ttl_path, alignments, ttl_path)
    write_alignment_results(alignments, workspace_id, run_id, document_id)

    return ttl_path


def run_cross_document_alignment(
    working_dir: Path,
    workspace_id: str,
    run_id: str,
    config_path: Path | None = None,
) -> None:
    """
    Cross document entity alignment loading all per-document aligned ttls and performing entity alignment between them again
    """

    ttl_files = list(working_dir.glob("*.ttl"))

    entities = []
    for ttl_path in ttl_files:
        for entity in load_entity_information(ttl_path):
            entity["source_document"] = ttl_path.stem
            entities.append(entity)

    config = load_alignment_config(config_path)
    candidates = [
        (a, b)
        for a, b in generate_candidate_pairs(entities, config)
        if a.get("source_document") != b.get("source_document")
    ]

    scored = similarity_computation(candidates, config)
    filtered = candidate_filtering(scored, config)

    alignments = [(a["uri"], b["uri"], score) for a, b, score in filtered]
    if alignments:
        logger.info(
            "[%s] Cross-document: writing %d owl:sameAs triple(s)",
            run_id,
            len(alignments),
        )
        write_alignment_results(alignments, workspace_id, run_id)
