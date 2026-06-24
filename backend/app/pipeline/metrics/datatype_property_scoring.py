"""Datatype property (literal) confidence scoring.
Window resolution, span matching, outlier penalty for literal triples.
"""

from __future__ import annotations

import re
from collections import defaultdict

from rapidfuzz import fuzz

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


def build_norm_map(text: str, strip_markdown: bool = False) -> tuple[str, list[int]]:
    """Collapse whitespace runs to a single space, optionally stripping markdown inline
    markers (* _ ` and em/en dashes replaced with hyphen).
    Returns (norm_text, pos_map) where pos_map[i] is the original index of norm_text[i].
    """
    MD_CHARS = frozenset("*_`")
    EM_DASHES = frozenset("—–")
    norm_chars: list[str] = []
    pos_map: list[int] = []
    i = 0
    while i < len(text):
        ch = text[i]
        if ch.isspace():
            if norm_chars and norm_chars[-1] != " ":
                norm_chars.append(" ")
                pos_map.append(i)
            while i < len(text) and text[i].isspace():
                i += 1
        elif strip_markdown and ch in MD_CHARS:
            i += 1  # drop the character, don't include char in output
        elif strip_markdown and ch in EM_DASHES:
            norm_chars.append("-")
            pos_map.append(i)
            i += 1
        else:
            norm_chars.append(ch)
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


def find_span_in(
    text: str, value: str, offset: int, exact_only: bool = False
) -> tuple[int, int, float] | None:
    """Finds the best matching span of {value} in {text}, returning (start, end, confidence).
    Confidence is based on the type of match:
    - 1.0 exact match
    - 0.95 case-insensitive match
    - 0.9 Normalized Match (any whitespace noise in source or value, inter- or intra-word)
    - 0.0-0.94 partial match based on fuzzy string similarity (may yield higher scores than other matches)

    When exact_only=True, fuzzy and abbreviation fallbacks are skipped — useful for
    identifier predicates (issn, doi, …) where a fuzzy match against unrelated digit
    sequences would produce a misleading confidence score.
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

    # Markdown-stripped normalized match
    stripped_text, stripped_pos_map = build_norm_map(text, strip_markdown=True)
    stripped_value = build_norm_map(value, strip_markdown=True)[0]
    idx = stripped_text.lower().find(stripped_value.lower())
    if idx >= 0:
        orig_start = stripped_pos_map[idx]
        orig_end = (
            stripped_pos_map[
                min(idx + len(stripped_value) - 1, len(stripped_pos_map) - 1)
            ]
            + 1
        )
        return offset + orig_start, offset + orig_end, 0.88

    if exact_only:
        return None

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
    exact_only: bool = False,
) -> tuple[int, int, float, bool] | None:
    """Search for {value} in {source}, going through all declared windows first.
    The following rules are being used (highest confidence wins):
        - Any match found inside a declared window is returned with in_window=True.
        - If no declared window matched, the full document is searched with the
        out-of-window penalty (+ optional distance penalty from the nearest window).
        - If no declared windows exist the full document is searched with no penalty.

    When exact_only=True, fuzzy and abbreviation fallbacks are disabled in find_span_in.
    """
    windows = get_windows(source, predicate, windows_config)

    # Best match across all declared windows (in_window=True)
    best_in_window: tuple[int, int, float] | None = None
    for window_text, window_offset in windows:
        result = find_span_in(window_text, value, window_offset, exact_only=exact_only)
        if result is not None:
            if best_in_window is None or result[2] > best_in_window[2]:
                best_in_window = result

    # Full-document result (penalised when declared windows exist)
    full_result = find_span_in(source, value, 0, exact_only=exact_only)
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


ABBREV_RE = re.compile(
    r"\b\w{1,4}\.$"
)  # ensures punctuation in abbrevations (e.g. Prof.) is not confused with sentence punctuation


def split_sentences(text: str) -> list[tuple[int, str]]:
    pattern = re.compile(r"(?<=[.!?])\s+|(?:\n\s*\n)+")
    result: list[tuple[int, str]] = []
    last = 0
    for m in pattern.finditer(text):
        chunk = text[last : m.start()]
        stripped = chunk.strip()
        # Don't split after abbreviation tokens
        if stripped and ABBREV_RE.search(stripped):
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


def entity_median_span(literals: list[dict]) -> float | None:
    """Returns median span_start across a list of literal annotations."""
    positions = [a["span_start"] for a in literals if "span_start" in a]
    if not positions:
        return None
    return median_position(positions)


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
        median = entity_median_span(group)
        if median is None:
            continue
        for ann in group:
            normalized_difference = abs(ann["span_start"] - median) / doc_length
            factor = max(
                min_outlier_factor, 1.0 - outlier_penalty * normalized_difference
            )
            ann["confidence"] = round(ann["confidence"] * factor, 4)
