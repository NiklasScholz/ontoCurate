from pathlib import Path

import pytest

from app.pipeline.entity_alignment import (
    candidate_filtering,
    generate_candidate_pairs,
    load_alignment_config,
    resolve_type_config,
    similarity_computation,
    validate_weights,
)
from app.pipeline.utils.turtle_utils import load_entity_information

ALIGNMENT_CONFIG_PATH = (
    Path(__file__).parent.parent / "config" / "scholarySchema" / "alignment_config.yaml"
)
CONFIG = load_alignment_config(ALIGNMENT_CONFIG_PATH)
PERSON_CFG = resolve_type_config(CONFIG, "Person")


def gen_entity(uri: str, type_: str, **literals) -> dict:
    # Helper to generate entity information (usually done in pipeline)
    return {
        "uri": uri,
        "types": [type_],
        "literals": {k: [v] for k, v in literals.items()},
        "relations_out": {},
    }


class TestGenerateCandidatePairs:
    def test_shared_doi(self):
        """Shared doi forces hard decisions"""
        a = gen_entity("ex:A", "AcademicArticle", doi="10.1234/abc")
        b = gen_entity("ex:B", "AcademicArticle", doi="10.1234/abc")
        c = gen_entity("ex:C", "AcademicArticle", doi="10.1234/xyz")

        pairs = generate_candidate_pairs([a, b, c], CONFIG)
        uris = {frozenset({p[0]["uri"], p[1]["uri"]}) for p in pairs}

        assert frozenset({"ex:A", "ex:B"}) in uris
        assert frozenset({"ex:A", "ex:C"}) not in uris

    def test_type_buckets(self):
        a = gen_entity("ex:A", "Person", name="Max")
        b = gen_entity("ex:B", "Person", name="Bob")
        c = gen_entity("ex:C", "Organization", name="RWTH Aachen")

        pairs = generate_candidate_pairs([a, b, c], CONFIG)
        uris = {frozenset({p[0]["uri"], p[1]["uri"]}) for p in pairs}

        assert frozenset({"ex:A", "ex:B"}) in uris
        assert frozenset({"ex:A", "ex:C"}) not in uris
        assert frozenset({"ex:B", "ex:C"}) not in uris


class TestEntityLoadingFromTTL:
    def test_load_entities_from_ttl(self, tmp_path):
        ttl_text = """
            @prefix ex: <http://example.org/> .
            @prefix rdf: <http://www.w3.org/1999/02/22-rdf-syntax-ns#> .

            ex:A rdf:type ex:Person .
            ex:A ex:knows ex:B .
            ex:A ex:knows ex:B .
            ex:A ex:name "Alice" .

            ex:B rdf:type ex:Person .
            ex:B ex:name "Bob" .
        """
        ttl_path = tmp_path / "test.ttl"
        ttl_path.write_text(ttl_text)
        entities = load_entity_information(ttl_path)
        by_uri = {e["uri"]: e for e in entities}
        assert all("Person" in e["types"] for e in entities)
        assert len(entities) == 2
        assert by_uri["http://example.org/A"]["literals"]["name"] == ["Alice"]
        assert by_uri["http://example.org/B"]["literals"]["name"] == ["Bob"]
        assert by_uri["http://example.org/A"]["relations_out"]["knows"] == [
            "http://example.org/B"
        ]
        assert by_uri["http://example.org/B"]["relations_out"] == {}
        assert by_uri["http://example.org/B"]["relations_in"] == {
            "knows": ["http://example.org/A"]
        }


class TestValidateWeights:
    def test_person_weights_valid(self):
        validate_weights(PERSON_CFG["weights"], "Person")

    def test_empty_weights_ok(self):
        validate_weights({}, "test")

    def test_invalid_weights(self):
        with pytest.raises(ValueError):
            validate_weights(
                {"syntactic": 0.5, "semantic": 0.5, "structural": 0.5}, "test"
            )


class TestResolveTypeConfig:
    def test_read_person_config_values(self):
        cfg = resolve_type_config(CONFIG, "Person")
        assert cfg["threshold"] > 0.9
        assert cfg["expand_initials"] is True
        assert "familyName" in cfg["comparison_predicates"]


class TestSimilarityComputation:
    def test_high_similarity_pair(self):
        a = gen_entity("ex:A", "Person", familyName="Smith", name="Alice")
        b = gen_entity("ex:B", "Person", familyName="Smith", name="Alice ")
        results = similarity_computation([(a, b)], CONFIG)
        assert results[0][2] >= PERSON_CFG["threshold"]

    def test_low_similarity_pair(self):
        a = gen_entity("ex:A", "Person", familyName="Mustermann", name="Max")
        b = gen_entity("ex:B", "Person", familyName="John", name="Doe")
        results = similarity_computation([(a, b)], CONFIG)
        assert results[0][2] < PERSON_CFG["threshold"]
        assert results[0][0]["uri"] == "ex:A"
        assert results[0][1]["uri"] == "ex:B"


class TestCandidateFiltering:
    def test_above_threshold_kept(self):
        a = gen_entity("ex:A", "Person", name="Alice")
        b = gen_entity("ex:B", "Person", name="Alice")
        assert len(candidate_filtering([(a, b, 0.99)], CONFIG)) == 1

    def test_below_threshold_dropped(self):
        a = gen_entity("ex:A", "Person", name="Alice")
        b = gen_entity("ex:B", "Person", name="Bob")
        assert len(candidate_filtering([(a, b, 0.2)], CONFIG)) == 0

    def test_exact_person_threshold_kept(self):
        a = gen_entity("ex:A", "Person", name="Alice")
        b = gen_entity("ex:B", "Person", name="Alice")
        assert len(candidate_filtering([(a, b, PERSON_CFG["threshold"])], CONFIG)) == 1
