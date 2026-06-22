import logging
import os
import re
import time

import httpx
from rapidfuzz import fuzz
from sklearn.metrics.pairwise import cosine_similarity


def normalize_tokens(s: str) -> str:
    """Sort tokens alphabetically after stripping punctuation and lowercasing.
    Sorting is used so e.g. name order is always the same and matches get higher conf scores
    """
    tokens = sorted(re.sub(r"[^\w]", " ", s.lower()).split())
    return " ".join(tokens)


def fuzz_score(a: str, b: str) -> float:
    """Ratio fuzzy matching score on normalized words"""
    return fuzz.ratio(normalize_tokens(a), normalize_tokens(b)) / 100.0


def initial_expanded_score(a: str, b: str) -> float:
    """Like fuzz_score but treats single-character tokens as initials. (Helps match J. Doe with John Doe with higher confidence)"""
    base = fuzz_score(a, b)
    if base >= 0.96:
        return base

    def _tokens(s: str) -> list[str]:
        """Returns sorted lowercase tokens by length and treats non word characters as seperators."""
        return sorted(re.sub(r"[^\w]", " ", s.lower()).split(), key=len, reverse=True)

    tokens_a, tokens_b = _tokens(a), _tokens(b)
    if not tokens_a or not tokens_b:
        return base

    def _has_full_given(tokens: list[str]) -> bool:
        return any(len(t) > 1 for t in tokens[1:])

    if not (
        _has_full_given(tokens_a) or _has_full_given(tokens_b)
    ):  # only initials are available and no token with more than 1 char --> not informative
        return base

    shorter, longer = (
        (tokens_a, tokens_b) if len(tokens_a) <= len(tokens_b) else (tokens_b, tokens_a)
    )
    multi_shorter = [
        t for t in shorter if len(t) > 1
    ]  # picks all non-initial tokens from the shorter list as anchors
    if not multi_shorter:  # no initial token available
        return base
    anchor = multi_shorter[
        0
    ]  # picks the longest non-initial token (for persons typically surname)
    anchor_idx = next(
        (i for i, lt in enumerate(longer) if lt == anchor), None
    )  # requires exact match for the anchor
    if anchor_idx is None:
        return base

    used = {anchor_idx}
    for (
        tok
    ) in (
        shorter
    ):  # for every other token look for matching token in longer list (either exact match, or single character matching first character of target)
        if tok == anchor:
            continue
        match = next(
            (
                i
                for i, lt in enumerate(longer)
                if i not in used
                and (
                    lt == tok
                    or (len(lt) == 1 and tok.startswith(lt))
                    or (len(tok) == 1 and lt.startswith(tok))
                )
            ),
            None,
        )
        if match is None:
            return base
        used.add(match)
    return 1.0


def syntactic_similarity(
    entity1: dict,
    entity2: dict,
    comparison_predicates: list[str],
    expand_initials: bool = False,
) -> float:
    """Compute similarity based on string surface forms of entity property values.

    For each field of comparison_predicates returns the average syntactic similarity score
    If expand_initials is True, single-character tokens are treated as initials and match any token with the same prefix, boosting scores for abbreviated names.
    Otherwise, fuzz ratio score on normalised names is used.
    """
    score_fn = initial_expanded_score if expand_initials else fuzz_score

    field_scores = []
    for key in comparison_predicates:
        vals_a = [v for v in entity1["literals"].get(key, []) if v.strip()]
        vals_b = [v for v in entity2["literals"].get(key, []) if v.strip()]
        if not vals_a or not vals_b:
            continue
        best = max(score_fn(a, b) for a in vals_a for b in vals_b)
        field_scores.append(best)

    return sum(field_scores) / len(field_scores) if field_scores else 0.0


def get_embedding(text: str) -> list[float]:
    """Get embedding from OPENAI_API_BASE."""

    api_base = os.getenv("OPENAI_API_BASE", "https://chat.kiconnect.nrw/api/v1")
    api_key = os.getenv("OPENAI_API_KEY")
    endpoint = f"{api_base}/embeddings"
    if not api_key:
        logging.error("OPENAI_API_KEY not set in environment")
        return []
    model = os.getenv("EMBEDDING_MODEL", "qwen3-embedding-8b")
    payload = {
        "input": text,
        "model": model,
    }

    headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
    last_exception = None
    for attempt in range(3):
        try:
            with httpx.Client(timeout=30.0) as client:
                response = client.post(endpoint, json=payload, headers=headers)
                response.raise_for_status()
                data = response.json()
                return data["data"][0]["embedding"]
        except (httpx.ConnectError, httpx.ReadError, httpx.TimeoutException) as e:
            last_exception = e
            time.sleep(2**attempt)
        except Exception as e:
            logging.error(f"Failed to get embedding for text: {e}")
            return []
    logging.error(f"Failed to get embedding after 3 attempts: {last_exception}")
    return []


def semantic_similarity(
    entity1: dict,
    entity2: dict,
    semantic_text_predicates: list[str] | None = None,
) -> float:
    """Computes semantic similarity using embeddings from KI Connect NRW
    Uses text values from specified semantic_text_predicates (if both entities contain it)
    """
    predicates = semantic_text_predicates or ["name"]

    # Only include values for predicates present in both entities
    parts1, parts2 = [], []
    for field in predicates:
        vals1 = [v for v in entity1["literals"].get(field, []) if v.strip()]
        vals2 = [v for v in entity2["literals"].get(field, []) if v.strip()]
        if vals1 and vals2:
            parts1.extend(vals1)
            parts2.extend(vals2)

    if not parts1 or not parts2:
        return 0.0

    emb1 = get_embedding(" ".join(parts1))
    emb2 = get_embedding(" ".join(parts2))

    if not emb1 or not emb2:
        return 0.0

    return float(cosine_similarity([emb1], [emb2])[0][0])


def structural_similarity(entity1: dict, entity2: dict) -> float:
    """Compute structural similarity based on predicate containment.
    Returns default=0.4 if no literals are available
    """
    default = 0.4
    literals_a = set(entity1.get("literals", {}).keys())
    literals_b = set(entity2.get("literals", {}).keys())
    if not literals_a or not literals_b:
        return default
    overlap = len(literals_a & literals_b)
    return max(default, overlap / min(len(literals_a), len(literals_b)))


def combined_similarity(
    entity1: dict,
    entity2: dict,
    weights: dict[str, float] | None = None,
    comparison_predicates: list[str] | None = None,
    expand_initials: bool = False,
    threshold: float = 0.8,
    semantic_text_predicates: list[str] | None = None,
) -> float:
    """Aggregates syntactic, semantic and structural similarity according to config"""
    w = weights or {"syntactic": 0.5, "semantic": 0.35, "structural": 0.15}
    keys = comparison_predicates or ["name"]

    score = 0.0

    w_structural = w.get("structural", 0.0)
    if w_structural > 0:
        score += w_structural * structural_similarity(entity1, entity2)

    w_syntactic = w.get("syntactic", 0.0)
    if w_syntactic > 0:
        score += w_syntactic * syntactic_similarity(
            entity1, entity2, keys, expand_initials
        )

    w_semantic = w.get("semantic", 0.0)
    if w_semantic > 0:
        if (
            score + w_semantic < 0.65
        ):  # skip expensive semantic similarity if structural and syntactic similarity are already very low (configurable threshold)
            return score
        score += w_semantic * semantic_similarity(
            entity1, entity2, semantic_text_predicates
        )
    return score
