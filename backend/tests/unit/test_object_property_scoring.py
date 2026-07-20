"""Tests for app.pipeline.metrics.object_property_scoring"""

import pytest

from app.pipeline.metrics.object_property_scoring import (
    apply_object_property_outlier_penalty,
    score_average_entity_confidence,
    score_average_target_entity_confidence,
    score_section_containment,
    score_spatial_cooccurrence,
)


class TestObjectPropertyScoring:
    def build_literal_by_subject_dict(
        self, subject: str, confidences_and_spans: list[tuple[float, int]]
    ) -> dict:
        """Build literal_by_subject dict with explicit with dumy span ends"""
        return {
            subject: [
                {
                    "subject": subject,
                    "predicate": "title",
                    "object": "v",
                    "span_start": pos,
                    "span_end": pos + 5,
                    "confidence": conf,
                    "triple_type": "literal",
                }
                for conf, pos in confidences_and_spans
            ]
        }

    def build_simple_literal_by_subject_dict(
        self, subject: str, confidences: list[float]
    ) -> dict:
        return self.build_literal_by_subject_dict(
            subject, [(c, i * 100) for i, c in enumerate(confidences)]
        )

    def test_target_avg_returns_average_of_target_literals(self):
        literal_subject_dict = self.build_simple_literal_by_subject_dict(
            "ent:A", [0.8, 0.6]
        )
        assert score_average_target_entity_confidence(
            "ent:A", literal_subject_dict
        ) == pytest.approx(0.7)

    def test_target_avg_single_literal(self):
        literal_subject_dict = self.build_simple_literal_by_subject_dict("ent:A", [0.5])
        assert score_average_target_entity_confidence(
            "ent:A", literal_subject_dict
        ) == pytest.approx(0.5)

    def test_target_avg_returns_none_when_target_missing(self):
        assert score_average_target_entity_confidence("ent:missing", {}) is None

    def test_avg_entity_confidence_averages_both_sides(self):
        literal_subject_dict = self.build_simple_literal_by_subject_dict(
            "ent:A", [1.0]
        ) | self.build_simple_literal_by_subject_dict("ent:B", [0.5])
        assert score_average_entity_confidence(
            "ent:A", "ent:B", literal_subject_dict
        ) == pytest.approx(0.75)

    def test_avg_entity_confidence_uses_only_target_when_source_missing(self):
        literal_subject_dict = self.build_simple_literal_by_subject_dict("ent:B", [0.6])
        assert score_average_entity_confidence(
            "ent:missing", "ent:B", literal_subject_dict
        ) == pytest.approx(0.6)

    def test_avg_entity_confidence_returns_none_when_both_missing(self):
        assert score_average_entity_confidence("s", "o", {}) is None

    def test_cooccurrence_higher_penalty_lowers_confidence(self):
        literal_subject_dict = {
            "subj:A": [
                {
                    "span_start": 0,
                    "span_end": 5,
                    "confidence": 1.0,
                    "triple_type": "literal",
                }
            ],
            "obj:B": [
                {
                    "span_start": 9000,
                    "span_end": 9005,
                    "confidence": 1.0,
                    "triple_type": "literal",
                }
            ],
        }
        conf_low, _ = score_spatial_cooccurrence(
            "subj:A", "obj:B", literal_subject_dict, 10000, 0.5, 0.0
        )
        conf_high, _ = score_spatial_cooccurrence(
            "subj:A", "obj:B", literal_subject_dict, 10000, 2.0, 0.0
        )
        assert conf_high < conf_low
        assert conf_low < 0.6
        assert conf_high < 0.01

    def test_cooccurrence_zero_penalty_returns_full_avg_confidence(self):
        literal_subject_dict = {
            "subj:A": [
                {
                    "span_start": 0,
                    "span_end": 5,
                    "confidence": 1.0,
                    "triple_type": "literal",
                }
            ],
            "obj:B": [
                {
                    "span_start": 9000,
                    "span_end": 9005,
                    "confidence": 1.0,
                    "triple_type": "literal",
                }
            ],
        }
        conf, _ = score_spatial_cooccurrence(
            "subj:A", "obj:B", literal_subject_dict, 10000, 0.0, 0.0
        )
        assert conf == pytest.approx(1.0)

    def test_cooccurrence_min_factor_confidence(self):
        literal_subject_dict = {
            "subj:A": [
                {
                    "span_start": 0,
                    "span_end": 5,
                    "confidence": 1.0,
                    "triple_type": "literal",
                }
            ],
            "obj:B": [
                {
                    "span_start": 9999,
                    "span_end": 10000,
                    "confidence": 1.0,
                    "triple_type": "literal",
                }
            ],
        }
        conf, _ = score_spatial_cooccurrence(
            "subj:A", "obj:B", literal_subject_dict, 10000, 100.0, 0.5
        )
        assert conf == pytest.approx(0.5)

    def test_section_containment_no_penalty_when_target_in_section(self):
        source = (
            "## Introduction\n\n. Some content bla bli blub\n\n## Conclusion\n\nfoo"
        )
        target_pos = source.index("content")
        literal_subject_dict = {
            "subj:A": [
                {
                    "span_start": 0,
                    "span_end": 5,
                    "confidence": 1.0,
                    "triple_type": "literal",
                }
            ],
            "obj:B": [
                {
                    "span_start": target_pos,
                    "span_end": target_pos + 6,
                    "confidence": 1.0,
                    "triple_type": "literal",
                }
            ],
        }
        result = score_section_containment(
            "subj:A",
            "obj:B",
            literal_subject_dict,
            source,
            ["Introduction"],
            0.8,
            0.0,
            0.3,
        )
        assert result == pytest.approx(1.0)

    def test_section_containment_applies_penalty_when_target_outside_section(self):
        source = "## Introduction\n\nIntro text\n\n## Results\n\n" + "x" * 500
        results_pos = source.index("## Results")
        target_pos = results_pos + len("## Results\n\n") + 100
        literal_subject_dict = {
            "subj:A": [
                {
                    "span_start": 0,
                    "span_end": 5,
                    "confidence": 1.0,
                    "triple_type": "literal",
                }
            ],
            "obj:B": [
                {
                    "span_start": target_pos,
                    "span_end": target_pos + 5,
                    "confidence": 1.0,
                    "triple_type": "literal",
                }
            ],
        }
        result = score_section_containment(
            "subj:A",
            "obj:B",
            literal_subject_dict,
            source,
            ["Introduction"],
            0.8,
            0.0,
            0.0,
        )
        assert result < 0.9

    def test_section_containment_returns_avg_confidence_when_no_section_was_found(self):
        source = "Some document without any matching section headings " + "x" * 100
        literal_subject_dict = {
            "subj:A": [
                {
                    "span_start": 0,
                    "span_end": 5,
                    "confidence": 1.0,
                    "triple_type": "literal",
                }
            ],
            "obj:B": [
                {
                    "span_start": 50,
                    "span_end": 55,
                    "confidence": 0.8,
                    "triple_type": "literal",
                }
            ],
        }
        result = score_section_containment(
            "subj:A",
            "obj:B",
            literal_subject_dict,
            source,
            ["NonExistentSection"],
            0.8,
            0.0,
            0.3,
        )
        assert result == pytest.approx(0.9)

    def test_outlier_object_property_is_penalized(self):
        anns = [
            {
                "subject": "s",
                "predicate": "hasAuthor",
                "object": f"o{i}",
                "confidence": 1.0,
                "triple_type": "object_property",
                "target_median": float(pos),
            }
            for i, pos in enumerate([100, 110, 9000])
        ]
        apply_object_property_outlier_penalty(
            anns,
            doc_length=10000,
            outlier_penalty=1.0,
            min_outlier_factor=0.0,
            outlier_predicates={"hasAuthor"},
        )
        outlier = next(a for a in anns if a["target_median"] == 9000.0)
        cluster = [a for a in anns if a["target_median"] != 9000.0]
        assert outlier["confidence"] < 1.0
        for a in cluster:
            assert a["confidence"] == pytest.approx(1.0, abs=0.1)

    def test_outlier_penalty_skipped_without_predicate(self):
        anns = [
            {
                "subject": "s",
                "predicate": "p",
                "object": "o1",
                "confidence": 1.0,
                "triple_type": "object_property",
                "target_median": 100.0,
            },
            {
                "subject": "s",
                "predicate": "p",
                "object": "o2",
                "confidence": 1.0,
                "triple_type": "object_property",
                "target_median": 9000.0,
            },
        ]
        apply_object_property_outlier_penalty(
            anns, 10000, 1.0, 0.0, outlier_predicates=set()
        )
        for a in anns:
            assert a["confidence"] == 1.0

    def test_outlier_min_penalty(self):
        anns = [
            {
                "subject": "s",
                "predicate": "p",
                "object": f"o{i}",
                "confidence": 1.0,
                "triple_type": "object_property",
                "target_median": float(pos),
            }
            for i, pos in enumerate([0, 10000])
        ]
        apply_object_property_outlier_penalty(
            anns, 10000, 100.0, 0.5, outlier_predicates={"p"}
        )
        for a in anns:
            assert a["confidence"] == pytest.approx(0.5)
