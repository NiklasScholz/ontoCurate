"""Per-document confidence annotation.
See .docs/technical-logic-document/0001-extraction-confidence-score-logic.md for detailed description of the logic and rules used.
"""

from __future__ import annotations

import json
import re
from collections import defaultdict
from pathlib import Path

import yaml
from rapidfuzz import fuzz
from rdflib import Graph, Literal, URIRef
from rdflib.namespace import RDF

DEFAULT_CONFIG = (
    Path(__file__).parent.parent.parent
    / "config"
    / "schemas"
    / "provenance_config.yaml"
)

# Extract Windows

HEADING_RE = re.compile(r"^(#{1,6})\s+\**\s*(.+?)\s*\**\s*$", re.MULTILINE)


def extract_section(source: str, heading_name: str) -> tuple[str, int] | None:
    """Finds Sections by matching heading text (section strategy). Requires Markdown headings to work"""
    for m in HEADING_RE.finditer(source):
        if m.group(2).strip().lower() == heading_name.strip().lower():
            content_start = m.end()
            next_m = HEADING_RE.search(source, content_start)
            content_end = next_m.start() if next_m else len(source)
            return source[content_start:content_end], content_start
    return None


def resolve_window(source: str, entry: dict) -> tuple[str, int] | None:
    """Parses window by strategy provided in config."""
    strategy = entry.get(
        "strategy", "full"
    )  # full refers to full document, i.e. do nothing
    if strategy == "head":  # gets first n chars of the document
        chars = int(entry.get("chars", len(source)))
        return source[:chars], 0
    if strategy == "tail":  # gets last n chars of the document
        chars = int(entry.get("chars", len(source)))
        return source[-chars:], max(0, len(source) - chars)
    if strategy == "section":
        heading = entry.get("heading", "")
        result = extract_section(source, heading)
        return result  # full-document fallback if nothing is found
    return None


def get_windows(
    source: str, predicate: str, windows_config: dict
) -> list[tuple[str, int]]:
    """Retrieves windows for a given predicate based on the config.
    Multiple windows can be declared for a single predicate, then all are returned.
    """
    entry = windows_config.get(predicate)
    if entry is None:
        return []

    entries = entry if isinstance(entry, list) else [entry]
    windows = []
    for e in entries:
        resolved = resolve_window(source, e)
        if resolved is not None:
            windows.append(resolved)
    return windows


# Search Span Logic


def build_norm_map(text: str) -> tuple[str, list[int]]:
    """Collapse whitespace runs to a single space.
    Returns (norm_text, pos_map) where pos_map[i] is the original index of norm_text[i].
    """
    norm_chars: list[str] = []
    pos_map: list[int] = []
    i = 0
    while i < len(text):
        if text[i].isspace():
            if norm_chars and norm_chars[-1] != " ":
                norm_chars.append(" ")
                pos_map.append(i)
            while i < len(text) and text[i].isspace():
                i += 1
        else:
            norm_chars.append(text[i])
            pos_map.append(i)
            i += 1
    return "".join(norm_chars), pos_map


def build_intraword_pattern(value: str) -> str:
    """Build a regex that allows optional whitespace anywhere between characters
    within a token and between tokens.
    E.g. 'Know\nledge' in value matches 'Knowledge' in source
    """
    norm = re.sub(r"\s+", " ", value).strip()
    words = norm.split(" ")
    word_patterns = [r"\s*".join(re.escape(ch) for ch in word) for word in words]
    return r"\s*".join(word_patterns)


def try_abbreviation_match(text: str, value: str) -> tuple[int, int] | None:
    """Match value against text when it appears as an acronym, optionally followed by
    any of the expanded words.  E.g. 'KG Graph' is found for value 'Knowledge Graph'."""
    value_words = re.sub(r"\s+", " ", value).strip().split()
    if len(value_words) < 2:
        return None
    acronym = "".join(w[0] for w in value_words)
    m = re.search(r"(?<!\w)" + re.escape(acronym) + r"(?!\w)", text, re.IGNORECASE)
    if not m:
        return None
    pos = m.end()
    for word in value_words:
        wm = re.match(r"\s+" + re.escape(word), text[pos:], re.IGNORECASE)
        if wm:
            pos += wm.end()
    return m.start(), pos


def find_span_in(text: str, value: str, offset: int) -> tuple[int, int, float] | None:
    """Finds the best matching span of {value} in {text}, returning (start, end, confidence).
    Confidence is based on the type of match:
    - 1.0 exact match
    - 0.95 case-insensitive match
    - 0.9 Normalized Match (any whitespace noise in source or value, inter- or intra-word)
    - 0.0-0.94 partial match based on fuzzy string similarity (may yield higher scores than other matches)
    """
    if not value.strip():
        return None

    # Exact Match
    idx = text.find(value)
    if idx >= 0:
        return offset + idx, offset + idx + len(value), 1.0

    lower_text = text.lower()
    lower_value = value.lower()
    idx = lower_text.find(lower_value)
    if idx >= 0:  # case insensitive match
        return offset + idx, offset + idx + len(value), 0.95

    # Normalized match
    norm_text, pos_map = build_norm_map(text)
    norm_value = re.sub(r"\s+", " ", value).strip()
    idx = norm_text.lower().find(norm_value.lower())
    if idx >= 0:
        orig_start = pos_map[idx]
        orig_end = pos_map[idx + len(norm_value) - 1] + 1
        return offset + orig_start, offset + orig_end, 0.9
    pattern = build_intraword_pattern(value)
    m = re.search(pattern, text, re.IGNORECASE)
    if m:
        return offset + m.start(), offset + m.end(), 0.9

    # Abbreviation match
    abbrev = try_abbreviation_match(text, value)
    if abbrev:
        return offset + abbrev[0], offset + abbrev[1], 0.75

    sentences = split_sentences(text)
    if not sentences:
        return None

    # Fuzzy String Matching on Sentences within the text (Take ratio) -> ensures no highly confident matches because of words simply occuring in a window (e.g. Author of Paper2 for Paper3)
    best_score = 0.0
    best_sent_start = 0
    best_sent_text = ""
    for sent_start, sent_text in sentences:
        if len(sent_text) < max(
            len(value) * 0.5, 5
        ):  # ensures very short sentences don't get high scores just because of a few matching characters
            continue
        score = fuzz.partial_ratio(
            lower_value, sent_text.lower()
        )  # allows skipping characters
        if score > best_score:
            best_score = score
            best_sent_start = sent_start
            best_sent_text = sent_text
    min_score = 50
    if best_score < min_score:  # ensure that partial match exists
        return None

    local_start, local_end = best_window(
        best_sent_text, value, offset=best_sent_start
    )  # finds best matching sliding value (of target length )
    return offset + local_start, offset + local_end, best_score / 100.0


def find_span(
    source: str,
    value: str,
    predicate: str,
    windows_config: dict,
    out_of_window_penalty: float,
    win_distance_penalty: float = 0.0,
    min_penalty_factor: float = 0.3,
) -> tuple[int, int, float, bool] | None:
    """Search for {value} in {source}, going through all declared windows first.
    The following rules are being used (highest confidence wins):
        - Any match found inside a declared window is returned with in_window=True.
        - If no declared window matched, the full document is searched with the
        out-of-window penalty (+ optional distance penalty from the nearest window).
        - If no declared windows exist the full document is searched with no penalty.
    """
    windows = get_windows(source, predicate, windows_config)

    # Best match across all declared windows (in_window=True)
    best_in_window: tuple[int, int, float] | None = None
    for window_text, window_offset in windows:
        result = find_span_in(window_text, value, window_offset)
        if result is not None:
            if best_in_window is None or result[2] > best_in_window[2]:
                best_in_window = result

    # Full-document result (penalised when declared windows exist)
    full_result = find_span_in(source, value, 0)
    best_full: tuple[int, int, float, bool] | None = None
    if full_result is not None:
        start, end, conf = full_result
        if not windows:
            # No declared windows -> no penalty
            best_full = (start, end, conf, True)
        else:
            # find distance to nearest window
            nearest_window_end = (
                min(
                    win_off + len(win_txt)
                    for win_txt, win_off in windows
                    if start >= win_off + len(win_txt)
                )
                if any(start >= win_off + len(win_txt) for win_txt, win_off in windows)
                else (min(win_off + len(win_txt) for win_txt, win_off in windows))
            )  # checks if our match is after at least one window, if so calculates distance to nearest window end, otherwise distance to nearest window start
            distance = max(0, start - nearest_window_end)
            relative_distance = distance / len(source) if source else 0.0
            # apply distance penalty
            decay_factor = max(
                min_penalty_factor, 1.0 - win_distance_penalty * relative_distance
            )
            best_full = (
                start,
                end,
                round(conf * out_of_window_penalty * decay_factor, 4),
                False,
            )

    # Return whichever candidate has the higher confidence
    if best_in_window is not None and best_full is not None:
        if best_in_window[2] >= best_full[2]:
            return *best_in_window, True
        return best_full
    if best_in_window is not None:
        return *best_in_window, True
    return best_full


_ABBREV_RE = re.compile(r"\b\w{1,4}\.$")


def split_sentences(text: str) -> list[tuple[int, str]]:
    pattern = re.compile(r"(?<=[.!?])\s+|(?:\n\s*\n)+")
    result: list[tuple[int, str]] = []
    last = 0
    for m in pattern.finditer(text):
        chunk = text[last : m.start()]
        stripped = chunk.strip()
        # Don't split after abbreviation-like tokens
        if stripped and _ABBREV_RE.search(stripped):
            continue
        if stripped:
            leading = len(chunk) - len(chunk.lstrip())
            result.append((last + leading, stripped))
        last = m.end()
    tail = text[last:]
    stripped_tail = tail.strip()
    if stripped_tail:
        leading = len(tail) - len(tail.lstrip())
        result.append((last + leading, stripped_tail))
    return result


def best_window(sentence: str, value: str, offset: int = 0) -> tuple[int, int]:
    """Find the best matching window of {value} in {sentence} based on fuzzy matching, returning (start, end)."""
    val_len = len(value)
    sent_len = len(sentence)

    if val_len >= sent_len:
        return offset, offset + sent_len

    lower_val = value.lower()
    lower_sent = sentence.lower()
    best_score = -1
    best_i = 0
    for i in range(sent_len - val_len + 1):
        score = fuzz.ratio(lower_val, lower_sent[i : i + val_len])
        if score > best_score:
            best_score = score
            best_i = i

    return offset + best_i, offset + best_i + val_len


# Gather triples
def local_name(uri: URIRef) -> str:
    s = str(uri)
    return s.split("#")[-1].split("/")[-1]


def collect_literal_triples(graph: Graph) -> list[tuple[str, str, str]]:
    rows = []
    for s, p, o in graph:
        if not isinstance(s, URIRef) or not isinstance(o, Literal):
            continue
        if p == RDF.type:
            continue
        rows.append((str(s), local_name(p), str(o)))
    return rows


def collect_entity_triples(graph: Graph) -> list[tuple[str, str, str]]:
    """Return (subject_uri, predicate_local_name, object_uri) for every
    ObjectPropertytriple; skips blank nodes and rdf:type."""
    rows = []
    for s, p, o in graph:
        if not isinstance(s, URIRef) or not isinstance(o, URIRef):
            continue
        if p == RDF.type:
            continue
        rows.append((str(s), local_name(p), str(o)))
    return rows


def collect_rdf_type_triples(graph: Graph) -> list[tuple[str, str]]:
    """Return (subject_uri, full_type_uri) for every rdf:type triple."""
    rows = []
    for s, p, o in graph:
        if p == RDF.type and isinstance(s, URIRef) and isinstance(o, URIRef):
            rows.append((str(s), str(o)))
    return rows


def build_type_index(graph: Graph) -> dict[str, set[str]]:
    """Returns all types for each subject_uri (via rdf:type)"""
    index = {}
    for s, p, o in graph:
        if p == RDF.type and isinstance(s, URIRef) and isinstance(o, URIRef):
            if str(s) not in index:
                index[str(s)] = set()
            index[str(s)].add(local_name(o))
    return index


# Outlier Penalties
def median_position(positions: list[int]) -> float:
    sorted_pos = sorted(positions)
    n = len(sorted_pos)
    mid = n // 2
    return (
        (sorted_pos[mid - 1] + sorted_pos[mid]) / 2
        if n % 2 == 0
        else float(sorted_pos[mid])
    )


def apply_entity_outlier_penalty(
    annotations: list[dict],
    doc_length: int,
    outlier_penalty: float,
    min_outlier_factor: float,
    entity_types: list[str] | None = None,
    type_index: dict[str, set[str]] | None = None,
) -> None:
    """Adds a penalty to literal triples whose span is a spatial outlier in contrast to the other triples of the same entity.
    Intuition: If an entity has multiple literal annotations, we expect them to be mentioned in roughly the same area of the document (e.g. all affiliations of a paper are likely mentioned in the header). If one annotation is far away from the others, it's more likely to be a spurious match and should be penalized.

    Groups by subject URI, computes the median span_start of the group, then
    scales each annotation's confidence by:
        max(min_outlier_factor, 1 - outlier_penalty * |span_start - median| / doc_length)

    Only subjects with an rdf:type whose name is in entity_types are penalised.
    Skips entities with only one annotation.
    """
    if doc_length == 0 or outlier_penalty == 0.0:
        return

    def is_target_entity(subject_uri: str) -> bool:
        if not entity_types or type_index is None:
            return False  # no filter provided implies it should not be used at all
        subject_types = type_index.get(subject_uri, set())
        return bool(subject_types & set(entity_types))

    # Group by Subject URI (literal triples only, filtered by rdf:type)
    groups = defaultdict(list)
    for ann in annotations:
        if ann.get("triple_type") == "literal" and is_target_entity(ann["subject"]):
            groups[ann["subject"]].append(ann)

    # Apply Median Penalty
    for group in groups.values():
        if len(group) < 2:
            continue
        median = median_position([a["span_start"] for a in group])
        for ann in group:
            normalized_difference = abs(ann["span_start"] - median) / doc_length
            factor = max(
                min_outlier_factor, 1.0 - outlier_penalty * normalized_difference
            )
            ann["confidence"] = round(ann["confidence"] * factor, 4)


# Load Config
def load_config(
    config_path: Path,
) -> tuple[dict, float, float, float, float, float, list[str]]:
    raw = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    s = raw.get("settings", {})
    windows = raw.get("predicate_windows", {})
    penalty = float(s.get("out_of_window_penalty", 0.8))
    win_distance_penalty = float(s.get("win_distance_penalty", 0.0))
    min_penalty_factor = float(s.get("min_penalty_factor", 0.3))
    outlier_penalty = float(s.get("outlier_penalty", 1.0))
    min_outlier_factor = float(s.get("min_outlier_factor", 0.2))
    outlier_pentalty_entities = list(s.get("outlier_pentalty_entities", []))
    return (
        windows,
        penalty,
        win_distance_penalty,
        min_penalty_factor,
        outlier_penalty,
        min_outlier_factor,
        outlier_pentalty_entities,
    )


# Entry Point
def annotate_confidence(
    source_path: Path,
    ttl_path: Path,
    output_dir: Path,
    *,
    schema_path: Path | None = None,
    config_path: Path | None = None,
) -> Path:
    """Annotate every literal triple in ttl_path with a source span and
    confidence score, writing xx_provenance.json to output_dir.
    Uses config from {schema_path.parent}/provenance_config.yaml
    """
    if config_path is None:
        if schema_path is not None:
            candidate = Path(schema_path).parent / "provenance_config.yaml"
            config_path = candidate if candidate.exists() else DEFAULT_CONFIG
        else:
            config_path = DEFAULT_CONFIG

    (
        windows_config,
        out_of_window_penalty,
        win_distance_penalty,
        min_penalty_factor,
        outlier_penalty,
        min_outlier_factor,
        outlier_pentalty_entities,
    ) = load_config(config_path)

    source = source_path.read_text(encoding="utf-8")
    graph = Graph()
    graph.parse(str(ttl_path))
    type_index = build_type_index(graph)

    # Data Properties
    annotations: list[dict] = []

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
                "in_window": in_window,
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

    # ToDo: Object Property confidence score; Problems with rule-based and semantic approaches: structure between citations is obviously different; LLM hallucinations tend to produce semantic close things; Entity Literal confidence indicates nothing about this relation. We could assume none and those relations are verified by user always.

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
