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
    ):  # only initials are available and no token with more than 1 char
        # If both sides have single-char given-name tokens that differ, it's an explicit
        # conflict and return a near-zero score
        initials_a = {t for t in tokens_a if len(t) == 1}
        initials_b = {t for t in tokens_b if len(t) == 1}
        if initials_a and initials_b and initials_a.isdisjoint(initials_b):
            return 0.05
        return base

    shorter, longer = (
        (tokens_a, tokens_b) if len(tokens_a) <= len(tokens_b) else (tokens_b, tokens_a)
    )
    multi_shorter = [
        t for t in shorter if len(t) > 1
    ]  # picks all non-initial tokens from the shorter list as anchors
    if not multi_shorter:  # no initial token available
        return base
    # Pick the first multi-char token that also appears in the longer list.
    longer_set = set(longer)
    anchor = next((t for t in multi_shorter if t in longer_set), multi_shorter[0])
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
            # explicit initial conflict yields low score
            if len(tok) == 1 and any(
                len(longer[i]) == 1 and i not in used for i in range(len(longer))
            ):
                return 0.05
            return base
        used.add(match)
    return 1.0


def syntactic_similarity(
    entity1: dict,
    entity2: dict,
    comparison_predicates: list[str],
    expand_initials: bool = False,
    sparsity_penalty: float = 1.0,
    sparsity_max_fields: int = 1,
) -> float:
    """Compute similarity based on string surface forms of entity property values.

    For each field of comparison_predicates returns the average syntactic similarity score
    If expand_initials is True, single-character tokens are treated as initials and match any token with the same prefix, boosting scores for abbreviated names.
    Otherwise, fuzz ratio score on normalised names is used.
    sparsity_penalty is applied when the number of matched fields is <= sparsity_max_fields
    (and at least one more predicate was configured)
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

    if not field_scores:
        return 0.0

    avg = sum(field_scores) / len(field_scores)
    if (
        sparsity_penalty < 1.0
        and len(field_scores) <= sparsity_max_fields
        and len(comparison_predicates) > sparsity_max_fields
    ):
        avg *= sparsity_penalty
    return avg


def get_embeddings_batch(
    texts: list[str], batch_size: int = 100, retries: int = 3
) -> dict[str, list[float]]:
    """Get embeddings for {batch_size} texts from configured OpenAI endpoint.
    Duplicate texts are only sent once.  Returns dictionary of form {text: embedding}
    On failures of API call it retries with exponential backoff up to {retries} times.
    Missing embeddings or text after retries are silently omitted for the stake of usability.
    """
    api_base = os.getenv("OPENAI_API_BASE", "https://chat.kiconnect.nrw/api/v1")
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        raise RuntimeError("OPENAI_API_KEY not set in environment")
    model = os.getenv("EMBEDDING_MODEL", "qwen3-embedding-8b")
    endpoint = f"{api_base}/embeddings"
    headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}

    unique_texts = list(dict.fromkeys(texts))  # de-dupe, keep order
    result = {}

    for i in range(0, len(unique_texts), batch_size):
        batch = unique_texts[i : i + batch_size]
        payload = {"input": batch, "model": model}

        data = None
        last_exception = None
        for attempt in range(retries):
            try:
                with httpx.Client(timeout=120.0) as client:
                    response = client.post(endpoint, json=payload, headers=headers)
                    response.raise_for_status()
                    data = response.json()
                break
            except httpx.HTTPStatusError as e:
                last_exception = e
                if e.response.status_code == 429 or e.response.status_code >= 500:
                    time.sleep(2**attempt)
                    continue
                logging.error(f"Failed to get embeddings: {e}")
                break
            except (httpx.ConnectError, httpx.ReadError, httpx.TimeoutException) as e:
                last_exception = e
                time.sleep(2**attempt)
            except Exception as e:
                logging.error(f"Failed to get embeddings: {e}")
                break
        else:
            logging.error(
                f"Failed to get embeddings after {retries} attempts: {last_exception}"
            )

        if data is None:
            continue
        for idx, item in enumerate(data["data"]):
            result[batch[item.get("index", idx)]] = item["embedding"]

    return result


def semantic_text_pair(
    entity1: dict, entity2: dict, predicates: list[str]
) -> tuple[str, str] | None:
    """Builds the joined embedding-input text for both entities from fields
    present on both sides or
    None if no shared field has a value on both entities."""
    parts1, parts2 = [], []
    for field in predicates:
        vals1 = [v for v in entity1["literals"].get(field, []) if v.strip()]
        vals2 = [v for v in entity2["literals"].get(field, []) if v.strip()]
        if vals1 and vals2:
            parts1.extend(vals1)
            parts2.extend(vals2)
    if not parts1 or not parts2:
        return None
    return " ".join(parts1), " ".join(parts2)


def semantic_similarity(
    entity1: dict,
    entity2: dict,
    semantic_text_predicates: list[str] | None = None,
    embedding_lookup: dict[str, list[float]] | None = None,
) -> float:
    """Computes semantic similarity using embeddings from configured OpenAI endpoint
    Uses text values from specified semantic_text_predicates (if both entities contain it).
    Embeddings are looked up from {embedding_lookup} (built from precomputaiton)
    """
    predicates = semantic_text_predicates or ["name"]
    pair_texts = semantic_text_pair(entity1, entity2, predicates)
    if pair_texts is None:
        return 0.0
    text1, text2 = pair_texts

    lookup = embedding_lookup or {}
    emb1 = lookup.get(text1)
    emb2 = lookup.get(text2)

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
    sparsity_penalty: float = 1.0,
    sparsity_max_fields: int = 1,
    hard_match_predicates: dict[str, float] | None = None,
    embedding_lookup: dict[str, list[float]] | None = None,
) -> float:
    """Aggregates syntactic, semantic and structural similarity according to config"""
    w = weights or {"syntactic": 0.5, "semantic": 0.35, "structural": 0.15}
    keys = comparison_predicates or ["name"]

    if hard_match_predicates:
        score_fn = initial_expanded_score if expand_initials else fuzz_score
        for key, min_score in hard_match_predicates.items():
            vals_a = [v for v in entity1["literals"].get(key, []) if v.strip()]
            vals_b = [v for v in entity2["literals"].get(key, []) if v.strip()]
            if vals_a and vals_b:
                best = max(score_fn(a, b) for a in vals_a for b in vals_b)
                if best < min_score:
                    return 0.0

    score = 0.0

    w_structural = w.get("structural", 0.0)
    if w_structural > 0:
        score += w_structural * structural_similarity(entity1, entity2)

    w_syntactic = w.get("syntactic", 0.0)
    if w_syntactic > 0:
        score += w_syntactic * syntactic_similarity(
            entity1,
            entity2,
            keys,
            expand_initials,
            sparsity_penalty,
            sparsity_max_fields,
        )

    w_semantic = w.get("semantic", 0.0)
    if w_semantic > 0:
        score += w_semantic * semantic_similarity(
            entity1, entity2, semantic_text_predicates, embedding_lookup
        )

    return score
