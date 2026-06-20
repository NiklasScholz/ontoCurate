"""Tests for app.pipeline.confidence_annotation.annotate_confidence"""

import json

import pytest

from app.pipeline.confidence_annotation import annotate_confidence

SOURCE_TEXT = """\
# Example paper
## Abstract

This is the abstract of the paper. It summarizes the main contributions and findings.

## Authors

Alice Smith, alice@example.org
Bob Jones, bob@example.org

## References

1. Doe, J. et al. Cited Paper. Journal of Citations (2022).
"""

TTL_CONTENT = """\
@prefix ex: <http://example.org/> .
@prefix rdf: <http://www.w3.org/1999/02/22-rdf-syntax-ns#> .

ex:paper1 rdf:type ex:AcademicArticle ;
          ex:title_paper "Example paper" ;
          ex:abstract "This is the abstract of the paper. It summarizes the main contributions and findings." .

ex:author1 rdf:type ex:Person ;
           ex:name "Alice Smith" ;
           ex:email "alice@example.org" .

ex:author2 rdf:type ex:Person ;
           ex:name "Bob Jones" ;
           ex:email "bob@example.org" .

ex:paper1 ex:author ex:author1 .
ex:paper1 ex:author ex:author2 .
"""


@pytest.fixture
def annotation_outputs(tmp_path):
    source_path = tmp_path / "paper.txt"
    ttl_path = tmp_path / "paper_extraction.ttl"
    output_dir = tmp_path / "out"

    source_path.write_text(SOURCE_TEXT, encoding="utf-8")
    ttl_path.write_text(TTL_CONTENT, encoding="utf-8")

    out_path = annotate_confidence(source_path, ttl_path, output_dir)
    with open(out_path, encoding="utf-8") as f:
        data = json.load(f)
    return data


class TestAnnotateConfidenceLiteralAnnotations:
    def test_produces_literal_provenance_output(self, annotation_outputs):
        literals = [
            a
            for a in annotation_outputs["annotations"]
            if a["triple_type"] == "literal"
        ]
        assert len(literals) > 0

    def test_literal_annotation_has_required_fields(self, annotation_outputs):
        literals = [
            a
            for a in annotation_outputs["annotations"]
            if a["triple_type"] == "literal"
        ]
        for ann in literals:
            assert "subject" in ann
            assert "predicate" in ann
            assert "value" in ann
            assert "span_start" in ann
            assert "span_end" in ann
            assert "span_text" in ann
            assert "confidence" in ann
            assert "in_window" in ann

    def test_literal_span_text_matches_source_slice(self, annotation_outputs):
        literals = [
            a
            for a in annotation_outputs["annotations"]
            if a["triple_type"] == "literal"
        ]
        for ann in literals:
            sliced = SOURCE_TEXT[ann["span_start"] : ann["span_end"]]
            assert sliced == ann["span_text"]

    def test_confidence_in_range(self, annotation_outputs):
        for ann in annotation_outputs["annotations"]:
            assert 0.0 <= ann["confidence"] <= 1.0

    def test_title_matched_with_high_confidence(self, annotation_outputs):
        title_anns = [
            a
            for a in annotation_outputs["annotations"]
            if a.get("triple_type") == "literal" and a.get("predicate") == "title_paper"
        ]
        assert len(title_anns) >= 1
        assert title_anns[0]["confidence"] >= 0.9


class TestAnnotateConfidenceEntityTypeAnnotations:
    def test_produces_entity_type_annotations(self, annotation_outputs):
        entity_anns = [
            a
            for a in annotation_outputs["annotations"]
            if a["triple_type"] == "entity_type"
        ]
        assert len(entity_anns) > 0

    def test_entity_type_annotation_has_no_span_fields(self, annotation_outputs):
        entity_anns = [
            a
            for a in annotation_outputs["annotations"]
            if a["triple_type"] == "entity_type"
        ]
        for ann in entity_anns:
            assert "span_start" not in ann
            assert "span_end" not in ann
            assert "span_text" not in ann

    def test_entity_type_confidence_is_average_of_its_literals(
        self, annotation_outputs
    ):
        anns = annotation_outputs["annotations"]
        entity_anns = [a for a in anns if a["triple_type"] == "entity_type"]
        literal_anns = [a for a in anns if a["triple_type"] == "literal"]

        for entity_ann in entity_anns:
            subject = entity_ann["subject"]
            subject_literals = [a for a in literal_anns if a["subject"] == subject]
            if not subject_literals:
                continue
            expected_avg = round(
                sum(a["confidence"] for a in subject_literals) / len(subject_literals),
                4,
            )
            assert entity_ann["confidence"] == pytest.approx(expected_avg, abs=1e-4)


class TestAnnotateConfidenceObjectPropertyAnnotations:
    def test_produces_object_property_annotations(self, annotation_outputs):
        obj_anns = [
            a
            for a in annotation_outputs["annotations"]
            if a["triple_type"] == "object_property"
        ]
        assert len(obj_anns) > 0

    def test_object_property_annotation_has_required_fields(self, annotation_outputs):
        obj_anns = [
            a
            for a in annotation_outputs["annotations"]
            if a["triple_type"] == "object_property"
        ]
        for ann in obj_anns:
            assert "subject" in ann
            assert "predicate" in ann
            assert "object" in ann
            assert "confidence" in ann
            assert "scoring_strategy" in ann

    def test_internal_outlier_fields_are_stripped(self, annotation_outputs):
        for ann in annotation_outputs["annotations"]:
            assert "apply_outlier_penalty" not in ann
            assert "target_median" not in ann
