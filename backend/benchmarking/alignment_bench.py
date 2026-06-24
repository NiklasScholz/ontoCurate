from pathlib import Path

from app.pipeline.entity_alignment import (
    generate_candidate_pairs,
    load_alignment_config,
    resolve_type_config,
    similarity_computation,
)
from app.pipeline.utils.turtle_utils import load_entity_information, local_name


def label(entity: dict, comparison_predicates: list[str]):
    for key in comparison_predicates:
        vals = [v for v in entity["literals"].get(key, []) if v.strip()]
        if vals:
            return vals[0]
    return local_name(entity["uri"])


def pairs_to_rows(
    scored: list[tuple[dict, dict, float]],
    config: dict,
    alignment_type: str,
):
    rows = []
    for a, b, score in scored:
        entity_type = a["types"][0] if a["types"] else "unknown"
        type_cfg = resolve_type_config(config, entity_type)
        threshold = type_cfg["threshold"]
        above = score >= threshold
        if not above:  # we do not include pairs below threshold
            continue
        rows.append(
            {
                "alignment_type": alignment_type,
                "entity_type": entity_type,
                "entity_a_uri": local_name(a["uri"]),
                "entity_a_label": label(a, type_cfg["comparison_predicates"]),
                "entity_a_document": a.get("source_document", ""),
                "entity_b_uri": local_name(b["uri"]),
                "entity_b_label": label(b, type_cfg["comparison_predicates"]),
                "entity_b_document": b.get("source_document", ""),
                "alignment_confidence_score": round(score, 4),
                "threshold_set_by_config": threshold,
            }
        )
    return rows


def run_alignment_bench(
    ttl_paths: list[Path],
    config_path: Path,
):
    config = load_alignment_config(config_path)
    all_rows = []

    for ttl_path in ttl_paths:
        print(f"Running inner document alignment for {ttl_path.name}...")
        entities = load_entity_information(ttl_path)
        for e in entities:
            e["source_document"] = ttl_path.stem
        candidates = generate_candidate_pairs(entities, config)
        scored = similarity_computation(candidates, config)
        all_rows.extend(pairs_to_rows(scored, config, "inner"))

    if len(ttl_paths) > 1:
        print("Running cross-document alignment...")
        all_entities = []
        for ttl_path in ttl_paths:
            for entity in load_entity_information(ttl_path):
                entity["source_document"] = ttl_path.stem
                all_entities.append(entity)

        cross_candidates = [
            (a, b)
            for a, b in generate_candidate_pairs(all_entities, config)
            if a.get("source_document") != b.get("source_document")
        ]
        scored = similarity_computation(cross_candidates, config)
        all_rows.extend(pairs_to_rows(scored, config, "cross"))

    return all_rows
