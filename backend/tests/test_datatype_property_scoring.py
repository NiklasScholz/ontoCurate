"""Unit tests for app.pipeline.metrics.datatype_property_scoring"""

import pytest

from app.pipeline.metrics.datatype_property_scoring import (
    apply_entity_outlier_penalty,
    find_span,
    find_span_in,
    relocate_ambiguous_spans,
    try_abbreviation_match,
)


def type_index(*pairs: tuple[str, str]) -> dict[str, set[str]]:
    """Build a minimal type_index from (subject_uri, type_local_name) pairs."""
    index: dict[str, set[str]] = {}
    for subject, type_name in pairs:
        if subject not in index:
            index[subject] = set()
        index[subject].add(type_name)
    return index


# Exact Match Tests
class TestExactMatch:
    def test_exact_match_confidence_is_1(self):
        source = "The title of the paper is Deep Learning"
        start, end, conf = find_span_in(source, "Deep Learning", 0)
        assert conf == 1.0
        assert start == 26
        assert end == 39

    def test_exact_match_correct_span(self):
        source = "The title of the paper is Deep Learning"
        start, end, conf = find_span_in(source, "Deep Learning", 0)
        assert source[start:end] == "Deep Learning"
        assert conf == 1.0

    def test_exact_match_with_offset(self):
        # test that offset is correctly applied for window settings
        source = "prefix Test Paper suffix"
        offset = 7
        assert source[offset:] == "Test Paper suffix"
        start, end, conf = find_span_in(source[offset:], "Test Paper", offset)
        assert conf == 1.0
        assert start == 7
        assert end == 17
        assert source[start:end] == "Test Paper"

    def test_multiline_value_matches_with_exact(self):
        # double-space in both source and value
        source = "Authors: Niklas  Scholz and Max Mustermann"
        value = "Niklas  Scholz"
        start, end, conf = find_span_in(source, value, 0)
        assert conf == 1.0
        assert source[start:end] == "Niklas  Scholz"

    def test_exact_match_in_window(self):
        # minimal window config for testing
        windows = {
            "title_paper": {"strategy": "head", "chars": 400},
            "abstract": {"strategy": "section", "heading": "Abstract"},
        }

        oow_penalty = 0.8
        distance_penalty = 0.0
        min_penalty = 0.3

        source = "Title: Knowledge Graph Construction with LLMs " + " x" * 1000
        result = find_span(
            source,
            "Knowledge Graph Construction with LLMs",
            "title_paper",
            windows,
            oow_penalty,
            win_distance_penalty=distance_penalty,
            min_penalty_factor=min_penalty,
        )
        start, end, conf, in_window = result
        assert source[start:end] == "Knowledge Graph Construction with LLMs"
        assert conf == 1.0
        assert in_window is True


# Test Case Insensitive Match
class TestCaseInsensitiveMatch:
    def test_uppercase_source_lowercase_value(self):
        source = "title: KG CONSTRUCTION WITH LLMS."
        start, end, conf = find_span_in(source, "kg construction with llms", 0)
        assert conf == 0.95
        assert source[start:end].lower() == "kg construction with llms"
        assert end - start == len("kg construction with llms")

    def test_lowercase_source_uppercase_value(self):
        source = "Scholz, N. et al. partnering with AI for knowledge graph construction"
        start, end, conf = find_span_in(
            source, "partnering with AI for KNOWLEDGE GRAPH Construction", 0
        )
        assert conf == 0.95
        assert (
            source[start:end].lower()
            == "partnering with ai for knowledge graph construction"
        )
        assert end - start == len("partnering with AI for KNOWLEDGE GRAPH Construction")
        start, end, conf = find_span_in(source, "Scholz et al.", 0)
        assert conf != 0.95


# White Space Normalisation Tests
class TestWhitespaceNormalisedMatch:
    def test_extra_whitespace_in_source(self):
        # source has words split by newlines/spaces
        source = "Title: Knowledge \n Graph \n Constr\nuction wi th L L Ms"
        value = "Knowledge Graph Construction with LLMs"
        start, end, conf = find_span_in(source, value, 0)
        assert conf == 0.9
        assert source[start:end] == "Knowledge \n Graph \n Constr\nuction wi th L L Ms"

    def test_extra_whitespace_in_value(self):
        # source has single space, value has double space (through noise or formatting)
        source = "Title: Knowledge Graph Basics"
        value = "Knowledge  Graph  Basics"
        _, _, conf = find_span_in(source, value, 0)
        assert conf == 0.9

    def test_whitespace_normalised_case_insensitive(self):
        # norm match is always case-insensitive
        source = "Title: knowledge  \n graph  \n embed\ndin g s"
        value = "Knowledge       Graph   Embeddings"
        _, _, conf = find_span_in(source, value, 0)
        assert conf == 0.9


# Fuzzy Match Tests
class TestFuzzyMatch:
    def test_fuzzy_match_below_1(self):
        source = "The paper discusses knowledg graph embdinng techniques."
        result = find_span_in(source, "knowledge graph embedding", 0)
        assert result is not None
        _, _, conf = result
        assert conf < 1.0
        assert conf > 0.8

    def test_no_match_below_min_score_returns_none(
        self,
    ):  # configured 0.5 match at least
        source = "Completely unrelated content here."
        result = find_span_in(source, "lorem ipsum dipsum chitsum lipsum", 0)
        assert result is None

    def test_find_abbrevation_in_large_source(self):
        source = "x" * 500 + " KG Graph " + "x" * 500
        result = find_span_in(source, "Knowledge Graph", 0)
        start, end, conf = result
        assert conf >= 0.5
        assert source[start:end] == "KG Graph"

    def test_empty_value_returns_none(self):
        assert find_span_in("some text", "", 0) is None

    def test_whitespace_only_value_returns_none(self):
        assert find_span_in("some text", "   ", 0) is None

    def test_year_only_date_matches_exactly_in_reference(self):
        source = (
            "4. Denny, P., et al.: Generative AI for education (GAIED): advances, "
            "opportunities, and challenges. CoRR abs/2402.01580 (2024)\n"
            "8. Lee, S., Song, K.S.: Teachers and students perceptions of AI-generated "
            "concept explanations. Comput. Educ. Artif. Intell. 7, 100283 (2024)"
        )
        result = find_span_in(source, "2024", 0)
        assert result is not None
        start, end, conf = result
        assert conf == 1.0
        assert source[start:end] == "2024"
        assert source[start:end] != "2402.01580"

    def test_journal_abbreviated_name_is_matched(self):
        source = (
            "Nicol, D.J., Macfarlane-Dick, D.: Formative assessment and "
            "self-regulated learning: a model and seven principles of good "
            "feedback practice. Stud. High. Educ. 31 (2), 199-218 (2006)"
        )
        result = find_span_in(source, "Studies in Higher Education", 0)
        assert result is not None, (
            "Expected a match for 'Studies in Higher Education' against its "
            "abbreviation 'Stud. High. Educ.' but got None"
        )
        start, end, conf = result
        matched = source[start:end]
        assert "Stud" in matched, f"Unexpected match span: {repr(matched)}"


# Abbreviation Match Tests
class TestAbbreviationMatch:
    def test_acronym_with_expanded_trailing_word(self):
        source = "xyz" * 500 + " KG Graph " + "zyx" * 500
        start, end = try_abbreviation_match(source, "Knowledge Graph")
        assert "KG Graph" == source[start:end]


# Test for Penalties
class TestOutOfWindowPenalty:
    windows = {
        "title_paper": {"strategy": "head", "chars": 400},
        "abstract": {"strategy": "section", "heading": "Abstract"},
    }
    oow_penalty = 0.8
    distance_penalty = 0.0
    min_penalty = 0.0

    def find(self, source, value, predicate):
        return find_span(
            source,
            value,
            predicate,
            self.windows,
            self.oow_penalty,
            win_distance_penalty=self.distance_penalty,
            min_penalty_factor=self.min_penalty,
        )

    def test_in_window_no_penalty(self):
        source = "# Knowledge Graph Entity Alignment Methods: A Survey " + "x" * 5000
        result = self.find(
            source, "Knowledge Graph Entity Alignment Methods: A Survey", "title_paper"
        )
        assert result is not None
        start, end, conf, in_window = result
        assert in_window is True
        assert conf == 1.0
        assert source[start:end] == "Knowledge Graph Entity Alignment Methods: A Survey"

    def test_out_of_window_penalty_applied(self):
        # title_paper window is first 400 chars; value appears after char 400
        source = (
            "x" * 450
            + "Title: Knowledge Graph Entity Alignment Methods: A Survey "
            + "x" * 50
        )
        result = self.find(
            source, "Knowledge Graph Entity Alignment Methods: A Survey", "title_paper"
        )
        assert result is not None
        start, end, conf, in_window = result
        assert in_window is False
        assert conf < 1.0
        assert source[start:end] == "Knowledge Graph Entity Alignment Methods: A Survey"

    def test_out_of_window_confidence_is_scaled_by_penalty(self):
        source = (
            "x" * 450 + " Knowledge Graph Entity Alignment Methods: Survey " + "x" * 50
        )
        result = self.find(
            source, "KG Entity Alignment Methods: A Survey", "title_paper"
        )
        start, end, conf, _ = result
        assert conf == pytest.approx(0.70, abs=1e-1)
        expected_start = source.index("Knowledge Graph")
        assert abs(start - expected_start) <= 10
        assert "Entity Alignment" in source[start:end]

    def test_unknown_predicate_uses_full_strategy(self):
        # unknown predicates default to no penalty
        source = "x" * 500 + " Some value " + "x" * 50
        result = self.find(source, "Some value", "unknown_predicate")
        assert result is not None
        start, end, conf, in_window = result
        assert in_window is True
        assert conf == 1.0
        assert source[start:end] == "Some value"


# Test WindowDistance Penalties
class TestDistanceDecay:
    windows = {
        "title_paper": {"strategy": "head", "chars": 400},
        "abstract": {"strategy": "section", "heading": "Abstract"},
    }
    oow_penalty = 0.8

    def find_with_decay(self, source, value, predicate, decay, min_penalty=0.0):
        return find_span(
            source,
            value,
            predicate,
            self.windows,
            self.oow_penalty,
            win_distance_penalty=decay,
            min_penalty_factor=min_penalty,
        )

    def test_decay_zero_gives_flat_penalty(self):
        source = "x" * 450 + " Target " + "x" * 500
        r = self.find_with_decay(source, "Target", "title_paper", decay=0.0)
        start, end, conf, _ = r
        assert conf == pytest.approx(0.8, abs=1e-4)
        assert source[start:end] == "Target"

    def test_higher_decay_lowers_confidence_further(self):
        source = "x" * 450 + " Target " + "x" * 500
        r_low = self.find_with_decay(source, "Target", "title_paper", decay=0.5)
        r_high = self.find_with_decay(source, "Target", "title_paper", decay=2.0)
        start_low, end_low, conf_low, _ = r_low
        start_high, end_high, conf_high, _ = r_high
        assert conf_high < conf_low
        assert source[start_low:end_low] == "Target"
        assert source[start_high:end_high] == "Target"

    def test_decay_whitespace(self):
        source = "x" * 450 + " Targ et " + "x" * 500
        r_low = self.find_with_decay(source, "Target", "title_paper", decay=0.5)
        r_high = self.find_with_decay(source, "Target", "title_paper", decay=2.0)
        start_low, end_low, conf_low, _ = r_low
        start_high, end_high, conf_high, _ = r_high
        assert conf_high < conf_low
        assert source[start_low:end_low] == "Targ et"
        assert source[start_high:end_high] == "Targ et"


class TestEntityOutlierPenalty:
    def ann(self, subject, span_start, confidence=1.0):
        # helper holding all candidate statements for an entity (including their span_start)
        return {
            "subject": subject,
            "predicate": "some_pred",
            "value": "val",
            "span_start": span_start,
            "span_end": span_start + 10,
            "confidence": confidence,
            "triple_type": "literal",
        }

    def test_outlier_is_penalised(self):
        idx = type_index(("ent:A", "Person"))
        anns = [
            self.ann("ent:A", 100),
            self.ann("ent:A", 120),
            self.ann("ent:A", 110),
            self.ann("ent:A", 9000),  # outlier
        ]
        apply_entity_outlier_penalty(
            anns,
            doc_length=10000,
            outlier_penalty=1.0,
            min_outlier_factor=0.0,
            entity_types=["Person"],
            type_index=idx,
        )
        outlier = next(a for a in anns if a["span_start"] == 9000)
        assert outlier["confidence"] < 1.0
        assert outlier["confidence"] == pytest.approx(0.1, abs=0.05)

    def test_nopenalty_cluster(self):
        idx = type_index(("ent:A", "Person"))
        anns = [
            self.ann("ent:A", 100),
            self.ann("ent:A", 110),
            self.ann("ent:A", 120),
        ]
        apply_entity_outlier_penalty(
            anns,
            doc_length=10000,
            outlier_penalty=1.0,
            min_outlier_factor=0.0,
            entity_types=["Person"],
            type_index=idx,
        )
        for a in anns:
            assert a["confidence"] == pytest.approx(1.0, abs=0.05)

    def test_singleannotation_not_penalised(self):
        idx = type_index(("ent:A", "Person"))
        anns = [self.ann("ent:A", 5000)]
        apply_entity_outlier_penalty(
            anns,
            doc_length=10000,
            outlier_penalty=1.0,
            min_outlier_factor=0.0,
            entity_types=["Person"],
            type_index=idx,
        )
        assert anns[0]["confidence"] == 1.0

    def test_outlier_penalty_zero_disables_penalty(self):
        idx = type_index(("ent:A", "Person"))
        anns = [self.ann("ent:A", 100), self.ann("ent:A", 9000)]
        apply_entity_outlier_penalty(
            anns,
            doc_length=10000,
            outlier_penalty=0.0,
            min_outlier_factor=0.0,
            entity_types=["Person"],
            type_index=idx,
        )
        for a in anns:
            assert a["confidence"] == 1.0

    def test_min_outlier_penalty(self):
        idx = type_index(("ent:A", "Person"))
        anns = [self.ann("ent:A", 0), self.ann("ent:A", 10000)]
        apply_entity_outlier_penalty(
            anns,
            doc_length=10000,
            outlier_penalty=10.0,
            min_outlier_factor=0.5,
            entity_types=["Person"],
            type_index=idx,
        )
        for a in anns:
            assert a["confidence"] == 0.5

    def test_not_specified_entity_not_penalised(self):
        idx = type_index(("ent:A", "Proceedings"))  # Not part of entity_types filter
        anns = [self.ann("ent:A", 100), self.ann("ent:A", 9000)]
        apply_entity_outlier_penalty(
            anns,
            doc_length=10000,
            outlier_penalty=1.0,
            min_outlier_factor=0.0,
            entity_types=["Person"],
            type_index=idx,
        )
        for a in anns:
            assert a["confidence"] == 1.0

    def test_empty_entity_types(self):
        """No Entity Filter applies to no subject"""
        idx = type_index(("ent:A", "Proceedings"))
        anns = [self.ann("ent:A", 100), self.ann("ent:A", 9000)]
        apply_entity_outlier_penalty(
            anns,
            doc_length=10000,
            outlier_penalty=1.0,
            min_outlier_factor=0.0,
            entity_types=[],
            type_index=idx,
        )
        outlier = next(a for a in anns if a["span_start"] == 9000)
        assert outlier["confidence"] == 1.0

    def test_notype_index_applies_to_all(self):
        """No type_index does not apply anything"""
        anns = [self.ann("ent:A", 100), self.ann("ent:A", 9000)]
        apply_entity_outlier_penalty(
            anns,
            doc_length=10000,
            outlier_penalty=1.0,
            min_outlier_factor=0.0,
            entity_types=["Person"],
            type_index=None,
        )
        outlier = next(a for a in anns if a["span_start"] == 9000)
        assert outlier["confidence"] == 1.0

    def test_outlier_penalty_independent_betweeen_entities(self):
        idx = type_index(("ent:A", "Person"), ("ent:B", "Person"))
        anns = [
            self.ann("ent:A", 100),
            self.ann("ent:A", 9000),
            self.ann("ent:B", 100),
            self.ann("ent:B", 105),
        ]
        apply_entity_outlier_penalty(
            anns,
            doc_length=10000,
            outlier_penalty=1.0,
            min_outlier_factor=0.0,
            entity_types=["Person"],
            type_index=idx,
        )
        a_outlier = next(
            a for a in anns if a["subject"] == "ent:A" and a["span_start"] == 9000
        )
        banns = [a for a in anns if a["subject"] == "ent:B"]
        assert a_outlier["confidence"] < 1.0
        for a in banns:
            assert a["confidence"] == pytest.approx(1.0, abs=1e-1)


class TestRelocateAmbiguousSpans:
    def ann(self, subject: str, predicate: str, value: str, span_start: int) -> dict:
        return {
            "subject": subject,
            "predicate": predicate,
            "value": value,
            "span_start": span_start,
            "span_end": span_start + len(value),
            "span_text": value,
            "confidence": 1.0,
            "triple_type": "literal",
        }

    def test_year_relocated_to_nearest_entity_occurrence(self):
        # "2025" appears at position 0 (paper header) and again near position 76
        # (next to the cited paper's title at position 55).
        # The function should move the span from 0 to 76.
        title = "Title of cited paper"
        source = "2025 " + " " * 50 + title + " 2025"
        title_pos = 55
        year_pos_near_title = title_pos + len(title) + 1  # 76

        subject = "ex:CitedPaper"
        annotations = [
            self.ann(subject, "datePublished", "2025", 0),
            self.ann(subject, "title", title, title_pos),
        ]
        relocate_ambiguous_spans(
            annotations,
            source,
            len(source),
            entity_types=["AcademicArticle"],
            type_index={subject: {"AcademicArticle"}},
        )

        date_ann = next(a for a in annotations if a["predicate"] == "datePublished")
        assert date_ann["span_start"] == year_pos_near_title
        assert date_ann["span_text"] == "2025"

    def test_no_relocation_when_single_occurrence(self):
        title = "Title of cited paper"
        source = "Some unrelated header. " + " " * 50 + title + " 2025"
        year_pos = len(source) - 4

        subject = "ex:CitedPaper"
        annotations = [
            self.ann(subject, "datePublished", "2025", year_pos),
            self.ann(subject, "title", title, len(source) - 4 - len(title) - 1),
        ]
        relocate_ambiguous_spans(
            annotations,
            source,
            len(source),
            entity_types=["AcademicArticle"],
            type_index={subject: {"AcademicArticle"}},
        )

        date_ann = next(a for a in annotations if a["predicate"] == "datePublished")
        assert date_ann["span_start"] == year_pos
