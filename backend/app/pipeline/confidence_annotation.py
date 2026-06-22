"""Per-document confidence annotation.
See .docs/technical-logic-document/0001-extraction-confidence-score-logic.md for detailed description of the logic and rules used.
"""

from __future__ import annotations

import json
from pathlib import Path

import yaml
from rdflib import Graph

from app.pipeline.metrics.datatype_property_scoring import (
    apply_entity_outlier_penalty,
    find_span,
)
from app.pipeline.metrics.object_property_scoring import annotate_object_properties
from app.pipeline.utils.turtle_utils import (
    build_type_index,
    collect_literal_triples,
    collect_rdf_type_triples,
)


# Load Config
def load_config(
    config_path: Path,
) -> tuple[dict, float, float, float, float, float, list[str], dict]:
    raw = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    s = raw.get("settings", {})
    dp = raw.get("datatype_properties", {})
    windows = dp.get("windows", {})
    penalty = float(s.get("out_of_window_penalty", 0.8))
    win_distance_penalty = float(s.get("win_distance_penalty", 0.0))
    min_penalty_factor = float(s.get("min_penalty_factor", 0.3))
    outlier_penalty = float(dp.get("outlier_penalty", 1.0))
    min_outlier_factor = float(dp.get("min_outlier_factor", 0.2))
    outlier_pentalty_entities = list(dp.get("outlier_pentalty_entities", []))
    obj_prop_config = raw.get("object_properties", {})
    return (
        windows,
        penalty,
        win_distance_penalty,
        min_penalty_factor,
        outlier_penalty,
        min_outlier_factor,
        outlier_pentalty_entities,
        obj_prop_config,
    )


# Entry Point
def annotate_confidence(
    source_path: Path,
    ttl_path: Path,
    output_dir: Path,
    *,
    config_path: Path,
) -> Path:
    """Annotate every literal triple in ttl_path with a source span and
    confidence score, writing xx_provenance.json to output_dir.
    Uses config from {config_path}
    """
    (
        windows_config,
        out_of_window_penalty,
        win_distance_penalty,
        min_penalty_factor,
        outlier_penalty,
        min_outlier_factor,
        outlier_pentalty_entities,
        obj_prop_config,
    ) = load_config(config_path)

    source = source_path.read_text(encoding="utf-8")
    graph = Graph()
    graph.parse(str(ttl_path))
    type_index = build_type_index(graph)

    # Data Properties
    annotations = []

    for subject_uri, predicate_label, obj_value in collect_literal_triples(graph):
        result = find_span(
            source,
            obj_value,
            predicate_label,
            windows_config,
            out_of_window_penalty,
            win_distance_penalty=win_distance_penalty,
            min_penalty_factor=min_penalty_factor,
        )
        if result is None:
            continue
        span_start, span_end, confidence, in_window = result
        annotations.append(
            {
                "subject": subject_uri,
                "predicate": predicate_label,
                "value": obj_value,
                "span_start": span_start,
                "span_end": span_end,
                "span_text": source[span_start:span_end],
                "confidence": round(confidence, 4),
                "triple_type": "literal",
            }
        )

    # Penalize Outlier Triples for configured entities
    apply_entity_outlier_penalty(
        annotations,
        len(source),
        outlier_penalty,
        min_outlier_factor,
        outlier_pentalty_entities,
        type_index,
    )

    # Entity type annotations: average confidence of datatype properties per subject
    literal_by_subject = {}
    for ann in annotations:
        if ann.get("triple_type") == "literal":
            if ann["subject"] not in literal_by_subject:
                literal_by_subject[ann["subject"]] = []
            literal_by_subject[ann["subject"]].append(ann)

    for subject_uri, type_uri in collect_rdf_type_triples(graph):
        group = literal_by_subject.get(subject_uri)
        if not group:
            continue
        avg_confidence = round(sum(a["confidence"] for a in group) / len(group), 4)
        annotations.append(
            {
                "subject": subject_uri,
                "predicate": "type",
                "value": type_uri,
                "confidence": avg_confidence,
                "triple_type": "entity_type",
            }
        )

    # Object Property Confidence
    if obj_prop_config:
        annotate_object_properties(
            annotations,
            graph,
            source,
            literal_by_subject,
            obj_prop_config,
            out_of_window_penalty,
            win_distance_penalty,
            min_penalty_factor,
            doc_length=len(source),
        )

    output_dir.mkdir(parents=True, exist_ok=True)
    stem = ttl_path.stem.replace("_extraction", "")
    out_path = output_dir / f"{stem}_provenance.json"
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(
            {"source_document": str(source_path), "annotations": annotations},
            f,
            indent=2,
            ensure_ascii=False,
        )

    return out_path
