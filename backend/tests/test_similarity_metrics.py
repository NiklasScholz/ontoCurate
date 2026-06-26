"""Tests for similarity_metrics.py"""

import os
from pathlib import Path

import pytest

from app.pipeline.entity_alignment import load_alignment_config, resolve_type_config
from app.pipeline.metrics.similarity_metrics import (
    combined_similarity,
    fuzz_score,
    initial_expanded_score,
    semantic_similarity,
    structural_similarity,
    syntactic_similarity,
)

ALIGNMENT_CONFIG_PATH = (
    Path(__file__).parent.parent / "config" / "schemas" / "alignment_config.yaml"
)
# load current config of scholarly use case
CONFIG = load_alignment_config(ALIGNMENT_CONFIG_PATH)
PERSON_CFG = resolve_type_config(CONFIG, "Person")
CONF_CFG = resolve_type_config(CONFIG, "Conference")
STRUCT_MIN = 0.4


def entity(uri: str, **literals) -> dict:
    """Helper to create entity information dicts (generated in pipeline usually)"""
    return {
        "uri": uri,
        "literals": {k: [v] for k, v in literals.items()},
        "relations_out": {},
    }


class TestFuzzScore:
    def test_low(self):
        assert fuzz_score("hello", "world") < 0.4

    def test_mid(self):
        score = fuzz_score("John Smith", "John Doe")
        assert 0.4 <= score < 0.7

    def test_high(self):
        assert fuzz_score("Alice Smith", "Alice Smith") == 1.0

    def test_different_word_order(self):
        assert fuzz_score("Smith Alice", "Alice Smith") == 1.0


class TestInitialExpandedScore:
    def test_low(self):
        assert initial_expanded_score("John Doe", "Alice Smith") < 0.5

    def test_mid(self):
        score = initial_expanded_score("Max Mustermann", "Max Bauer")
        assert 0.4 <= score < 0.75

    def test_high_full_match(self):
        assert initial_expanded_score("Alice Smith", "Alice Smith") == 1.0

    def test_initial_matches_full_name(self):
        assert initial_expanded_score("A. Smith", "Alice Smith") == 1.0

    def test_initial_mismatch(self):
        assert initial_expanded_score("B. Smith", "Alice Smith") < 0.75


class TestSyntacticSimilarity:
    KEYS = PERSON_CFG["comparison_predicates"]  # comaprison predicates for persons

    def test_low(self):
        e1 = entity("ex:A", familyName="Scholz", name="Niklas")
        e2 = entity("ex:B", familyName="Mustermann", name="Max")
        assert syntactic_similarity(e1, e2, self.KEYS) < 0.4

    def test_mid(self):
        e1 = entity("ex:A", familyName="Smith", name="John")
        e2 = entity("ex:B", familyName="Smith", name="Alice")
        score = syntactic_similarity(e1, e2, self.KEYS)
        assert 0.4 <= score < 0.75

    def test_high(self):
        e1 = entity("ex:A", familyName="Smith", name="Alice", email="alice@mail.com")
        e2 = entity("ex:B", familyName="Smith", name="Alice", email="alice@mail.com")
        assert syntactic_similarity(e1, e2, self.KEYS) == 1.0

    def test_missing_key_skipped(self):
        e1 = entity("ex:A", name="Alice", email="alice@mail.com")
        e2 = entity("ex:B", name="Alice")
        assert syntactic_similarity(e1, e2, self.KEYS) == 1.0


class TestStructuralSimilarity:
    def test_disjoint_predicates(self):
        # expects minimum struct similarity when no predicate is shared
        e1 = entity("ex:A", name="AIED")
        e2 = entity("ex:B", location="Berlin")
        assert structural_similarity(e1, e2) == STRUCT_MIN

    def test_mid(self):
        e1 = entity("ex:A", name="AIED", location="Tokyo")
        e2 = entity("ex:B", name="ECTEL", issn="1234")
        score = structural_similarity(e1, e2)
        assert STRUCT_MIN <= score < 0.9

    def test_high(self):
        e1 = entity("ex:A", name="AIED", location="Tokyo")
        e2 = entity("ex:B", name="ECTEL", location="Berlin")
        assert (
            structural_similarity(e1, e2) == 1.0
        )  # will need to be dragged down by other scores

    def test_no_predicates(self):
        assert structural_similarity(entity("ex:A"), entity("ex:B")) == STRUCT_MIN

    def test_sparse_data(self):
        e1 = entity("ex:A", name="AIED")
        e2 = entity("ex:B", name="ECTEL", location="Berlin", issn="1234")
        assert structural_similarity(e1, e2) == 1.0


needs_api_key = pytest.mark.skipif(
    not os.getenv("OPENAI_API_KEY"),
    reason="OPENAI_API_KEY not set; skipping embedding tests",
)


class TestSemanticSimilarity:
    FIELDS = CONF_CFG["semantic_text_predicates"]

    def test_no_shared_predicates_returns_zero(self):
        # if no predicates are shared then embedding does not make sense to use (return 0.0)
        e1 = entity("ex:A", name="AIED")
        e2 = entity("ex:B", location="Tokyo")
        assert semantic_similarity(e1, e2, self.FIELDS) == 0.0

    def test_api_unreachable_returns_zero(self):
        # invalid API base is treated as 0.0
        orig = os.environ.get("OPENAI_API_BASE")
        os.environ["OPENAI_API_BASE"] = "http://localhost:19999"
        try:
            e1 = entity("ex:A", name="AIED")
            e2 = entity("ex:B", name="ECTEL")
            assert semantic_similarity(e1, e2, self.FIELDS) == 0.0
        finally:
            if orig is None:
                os.environ.pop("OPENAI_API_BASE", None)
            else:
                os.environ["OPENAI_API_BASE"] = orig


class TestSemanticSimilarityQuality:
    """Live tests to use locally for embeddings quality"""

    FIELDS = CONF_CFG["semantic_text_predicates"]

    @needs_api_key
    def test_low_unrelated_conferences(self):
        e1 = entity("ex:A", name="AIED")
        e2 = entity("ex:B", name="ECTEL")
        score = semantic_similarity(e1, e2, self.FIELDS)
        assert (
            score < 0.75
        ), f"Expected low similarity for unrelated conferences, got {score}"

    @needs_api_key
    def test_mid_related_venues(self):
        e1 = entity("ex:A", name="International Conference on AI")
        e2 = entity("ex:B", name="International Workshop on AI")
        score = semantic_similarity(e1, e2, self.FIELDS)
        assert (
            0.5 <= score < 0.95
        ), f"Expected mid similarity for related venues, got {score}"

    @needs_api_key
    def test_high_abbreviation_vs_full_name(self):
        e1 = entity("ex:A", name="AIED")
        e2 = entity("ex:B", name="Artificial Intelligence in Education")
        score = semantic_similarity(e1, e2, self.FIELDS)
        assert (
            score > 0.8
        ), f"Expected high similarity for abbreviation vs full name, got {score}"


class TestCombinedSimilarity:
    W = PERSON_CFG["weights"]
    KEYS = PERSON_CFG["comparison_predicates"]
    EXPAND = PERSON_CFG["expand_initials"]

    def test_low(self):
        e1 = entity("ex:A", familyName="Mustermann", name="Max")
        e2 = entity("ex:B", familyName="Doe", name="John")
        score = combined_similarity(
            e1,
            e2,
            weights=self.W,
            comparison_predicates=self.KEYS,
            expand_initials=self.EXPAND,
        )
        assert score < 0.5

    def test_mid(self):
        e1 = entity("ex:A", familyName="Smith", name="John")
        e2 = entity("ex:B", familyName="Smith", name="Alice")
        score = combined_similarity(
            e1,
            e2,
            weights=self.W,
            comparison_predicates=self.KEYS,
            expand_initials=self.EXPAND,
        )
        assert 0.4 <= score < 0.75

    def test_high(self):
        e1 = entity("ex:A", familyName="Smith", name="Alice Smith")
        e2 = entity("ex:B", familyName="Smithe", name="Alice")
        score = combined_similarity(
            e1,
            e2,
            weights=self.W,
            comparison_predicates=self.KEYS,
            expand_initials=self.EXPAND,
        )
        assert score >= PERSON_CFG["threshold"]

    @needs_api_key
    def test_with_semantic_low(self):
        e1 = entity("ex:A", name="NeurIPS")
        e2 = entity("ex:B", name="ICLR")
        score = combined_similarity(
            e1,
            e2,
            weights=CONF_CFG["weights"],
            comparison_predicates=CONF_CFG["comparison_predicates"],
            semantic_text_predicates=CONF_CFG["semantic_text_predicates"],
        )
        assert (
            score < CONF_CFG["threshold"]
        ), f"Expected low similarity with semantic similarity, got {score}"

    @needs_api_key
    def test_with_semantic_high(self):
        e1 = entity(
            "ex:A", name="Artificial Intelligence In Education", location="Tokyo"
        )
        e2 = entity("ex:B", name="AIED", location="Tokyo")
        score = combined_similarity(
            e1,
            e2,
            weights=CONF_CFG["weights"],
            comparison_predicates=CONF_CFG["comparison_predicates"],
            semantic_text_predicates=CONF_CFG["semantic_text_predicates"],
        )
        assert (
            score >= CONF_CFG["threshold"]
        ), f"Expected high similarity with semantic similarity, got {score}"

    def test_zhang_zhuang_blocked(self):
        e1 = entity("ex:A", familyName="Zhang", name="Y. Zhang")
        e2 = entity("ex:B", familyName="Zhuang", name="Y. Zhuang")
        score = combined_similarity(
            e1,
            e2,
            weights=PERSON_CFG["weights"],
            comparison_predicates=PERSON_CFG["comparison_predicates"],
            expand_initials=PERSON_CFG["expand_initials"],
            hard_match_predicates=PERSON_CFG["hard_match_predicates"],
        )
        assert score == 0.0
