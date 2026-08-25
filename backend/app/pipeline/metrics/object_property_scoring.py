from collections import defaultdict

from rdflib import Graph

from app.pipeline.metrics.datatype_property_scoring import (
    entity_median_span,
    extract_section,
    median_position,
)
from app.pipeline.utils.turtle_utils import collect_entity_triples


def entity_avg_confidence(uri: str, literal_by_subject: dict) -> float | None:
    """Returns average confidence for all literals of a given entity."""
    lits = literal_by_subject.get(uri)
    if not lits:
        return None
    return round(sum(a["confidence"] for a in lits) / len(lits), 4)


def score_average_target_entity_confidence(
    object_uri: str, literal_by_subject: dict
) -> float | None:
    """Returns average literal confidence of the target entity."""
    return entity_avg_confidence(object_uri, literal_by_subject)


def score_average_entity_confidence(
    subject_uri: str, object_uri: str, literal_by_subject: dict
) -> float | None:
    """Returns average literal confidence across both source and target entities."""
    src = literal_by_subject.get(subject_uri) or []
    tgt = literal_by_subject.get(object_uri) or []
    all_literals = src + tgt
    if not all_literals:
        return None
    return round(sum(a["confidence"] for a in all_literals) / len(all_literals), 4)


def score_spatial_cooccurrence(
    subject_uri: str,
    object_uri: str,
    literal_by_subject: dict,
    doc_length: int,
    distance_penalty: float,
    min_factor: float,
) -> tuple[float, float | None] | None:
    """
    Calculates avg confidence of both entities scaled by distance between their spans
    and target median (for reuse during outlier penalisation).
    Useful for entities that should occur close to each other (e.g. Author and Organization)
    Returns (confidence, target_median_position) or None if target has no literals.
    """
    tgt_conf = entity_avg_confidence(object_uri, literal_by_subject)
    if tgt_conf is None:
        return None
    src_conf = entity_avg_confidence(subject_uri, literal_by_subject)
    base = (src_conf + tgt_conf) / 2 if src_conf is not None else tgt_conf
    subj_median = entity_median_span(literal_by_subject.get(subject_uri) or [])
    tgt_median = entity_median_span(literal_by_subject.get(object_uri) or [])
    if subj_median is None or tgt_median is None or doc_length == 0:
        return base, tgt_median
    distance = abs(subj_median - tgt_median)
    factor = max(min_factor, 1.0 - distance_penalty * distance / doc_length)
    return round(base * factor, 4), tgt_median


def find_entity_in_section(
    literal_annotations: list[dict],
    source: str,
    section_heading: str,
) -> float | None:
    """
    Search for any of the entitys literal values inside a named section.
    Used when scoring non-primary document entities that could also be primary-document entities but differentiate.
    Returns the absolute span_start position in the source document, or None.
    """
    result = extract_section(source, section_heading)
    if result is None:
        return None
    section_text, section_offset = result
    section_lower = section_text.lower()
    for ann in literal_annotations:
        value = str(ann.get("value", "")).strip()
        if not value:
            continue
        idx = section_lower.find(value.lower())
        if idx != -1:
            return float(section_offset + idx)
    return None


def score_entity_hierachy_aware_confidence(
    subject_uri: str,
    object_uri: str,
    literal_by_subject: dict,
    source: str,
    primary_entity_predicates: list[str],
    fallback_sections: list[str],
) -> tuple[float | None, float | None]:
    """
    Average-entity confidence that is aware of whether the subject is the primary entity.
    For non-primary entities, it checks for the object entity's literal values inside the configured fallback sections
    (to prevent outlier penalties when taking value from different window)
    Returns (confidence, tgt_median).
    """
    subj_lits = literal_by_subject.get(subject_uri, [])
    is_primary = any(a.get("predicate") in primary_entity_predicates for a in subj_lits)

    if is_primary:
        return (
            score_average_entity_confidence(
                subject_uri, object_uri, literal_by_subject
            ),
            None,
        )

    obj_lits = literal_by_subject.get(object_uri, [])
    tgt_median = None
    for heading in fallback_sections:
        pos = find_entity_in_section(obj_lits, source, heading)
        if pos is not None:
            tgt_median = pos
            break

    confidence = score_average_entity_confidence(
        subject_uri, object_uri, literal_by_subject
    )
    return confidence, tgt_median


def score_section_containment(
    subject_uri: str,
    object_uri: str,
    literal_by_subject: dict,
    source: str,
    sections: list[str],
    out_of_window_penalty: float,
    win_distance_penalty: float,
    min_penalty_factor: float,
) -> float | None:
    """
    Returns target avg literal confidence, penalized if the target entity
    median literal span does not fall inside any of the configured sections.
    (similiar to out-of-window penalty)
    """
    tgt_conf = entity_avg_confidence(object_uri, literal_by_subject)
    if tgt_conf is None:
        return None
    src_conf = entity_avg_confidence(subject_uri, literal_by_subject)
    base = (src_conf + tgt_conf) / 2 if src_conf is not None else tgt_conf
    tgt_median = entity_median_span(literal_by_subject.get(object_uri) or [])
    if tgt_median is None:
        return base

    section_ranges = []
    for heading in sections:  # extract all declared sections and their offsets
        result = extract_section(source, heading)
        if result is not None:
            sec_text, sec_offset = result
            section_ranges.append((sec_offset, sec_offset + len(sec_text)))

    if not section_ranges:
        return base

    for (
        sec_start,
        sec_end,
    ) in section_ranges:  # check if target median is contained in at least one section
        if sec_start <= tgt_median <= sec_end:
            return base

    min_distance = min(
        min(abs(tgt_median - s), abs(tgt_median - e)) for s, e in section_ranges
    )  # calculate distance to nearest section boundary for distance penalty
    rel = min_distance / len(source) if source else 0.0
    decay = max(min_penalty_factor, 1.0 - win_distance_penalty * rel)
    return round(base * out_of_window_penalty * decay, 4)


def apply_object_property_outlier_penalty(
    annotations: list[dict],
    doc_length: int,
    outlier_penalty: float,
    min_outlier_factor: float,
    outlier_predicates: set[str] | None = None,
) -> None:
    """
    Penalize object property annotations in the same (subject, predicate) group
    whose target entity's median span is a spatial outlier relative to the group.
    Useful when an author is hallucinated from another reference.
    Only applies to predicates listed in outlier_predicates.
    """
    if doc_length == 0 or outlier_penalty == 0.0:
        return
    if not outlier_predicates:
        return
    groups = defaultdict(list)
    for ann in annotations:
        if (
            ann.get("triple_type") == "object_property"
            and ann.get("predicate") in outlier_predicates
            and ann.get("target_median") is not None
        ):
            groups[(ann["subject"], ann["predicate"])].append(ann)
    for group in groups.values():
        if len(group) < 2:
            continue
        group_median = median_position([int(a["target_median"]) for a in group])
        for ann in group:
            diff = abs(ann["target_median"] - group_median)
            factor = max(min_outlier_factor, 1.0 - outlier_penalty * diff / doc_length)
            ann["confidence"] = round(ann["confidence"] * factor, 4)


def annotate_object_properties(
    annotations: list[dict],
    graph: Graph,
    source: str,
    literal_by_subject: dict,
    obj_prop_config: dict,
    out_of_window_penalty: float,
    win_distance_penalty: float,
    min_penalty_factor: float,
    doc_length: int,
    exclude_predicates: frozenset[str] = frozenset(),
) -> None:
    """
    Score all object property triples and append annotations in-place.
    Strategy is selected per predicate via obj_prop_config['predicates'][predicate]['strategy'].
    Our code currently supports the strategies:
    - average_target_entity_confidence: confidence is the average of all literal confidences of the target entity.
    - average_entity_confidence: confidence is the average of all literal confidences of both source and target entities.
    - spatial_cooccurrence: confidence is the average of source and target literal confidences, scaled by the distance between their median literal spans (closer = higher confidence).
    - section_containment: confidence is the average of source and target literal confidences, penalized if the target entity's median literal span does not fall inside any of the configured sections
    """
    default_strategy = obj_prop_config.get(
        "default_strategy", "average_target_entity_confidence"
    )
    coop_dist_penalty = float(obj_prop_config.get("cooccurrence_distance_penalty", 1.0))
    coop_min_factor = float(obj_prop_config.get("cooccurrence_min_factor", 0.3))
    coop_outlier_penalty = float(
        obj_prop_config.get("cooccurrence_outlier_penalty", 1.0)
    )
    coop_min_outlier_factor = float(
        obj_prop_config.get("cooccurrence_min_outlier_factor", 0.2)
    )
    predicate_cfgs: dict = obj_prop_config.get("predicates", {})

    outlier_predicates: set[str] = set()

    # Iterate over all triples that belong to entities
    for subject_uri, predicate, object_uri in collect_entity_triples(
        graph, exclude_predicates
    ):
        config = predicate_cfgs.get(predicate, {})  # get config for current predicate
        strategy = config.get("strategy", default_strategy)
        if config.get("apply_outlier_penalty", False):
            outlier_predicates.add(predicate)

        confidence = None
        tgt_median = None
        # If new strategies are added, they should be registered here as an entrypoint
        if strategy == "average_target_entity_confidence":
            confidence = score_average_target_entity_confidence(
                object_uri, literal_by_subject
            )
        elif strategy == "average_entity_confidence":
            primary_entity_preds = config.get("primary_entity_predicates", [])
            fallback_secs = config.get("fallback_sections", [])
            if primary_entity_preds:
                confidence, tgt_median = score_entity_hierachy_aware_confidence(
                    subject_uri,
                    object_uri,
                    literal_by_subject,
                    source,
                    primary_entity_preds,
                    fallback_secs,
                )
            else:
                confidence = score_average_entity_confidence(
                    subject_uri, object_uri, literal_by_subject
                )
        elif strategy == "spatial_cooccurrence":
            result = score_spatial_cooccurrence(
                subject_uri,
                object_uri,
                literal_by_subject,
                doc_length,
                coop_dist_penalty,
                coop_min_factor,
            )
            if result is not None:
                confidence, tgt_median = result
        elif strategy == "section_containment":
            sections = config.get("sections", [])
            confidence = score_section_containment(
                subject_uri,
                object_uri,
                literal_by_subject,
                source,
                sections,
                out_of_window_penalty,
                win_distance_penalty,
                min_penalty_factor,
            )

        if confidence is None:
            continue

        if config.get("apply_outlier_penalty", False) and tgt_median is None:
            tgt_median = entity_median_span(literal_by_subject.get(object_uri) or [])

        ann = {
            "subject": subject_uri,
            "predicate": predicate,
            "object": object_uri,
            "confidence": confidence,
            "triple_type": "object_property",
            "target_median": tgt_median,
        }
        annotations.append(ann)

    apply_object_property_outlier_penalty(
        annotations,
        doc_length,
        coop_outlier_penalty,
        coop_min_outlier_factor,
        outlier_predicates,
    )

    for ann in annotations:
        ann.pop("target_median", None)
