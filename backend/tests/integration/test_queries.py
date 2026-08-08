import uuid

import pytest
from test_utils import (
    add_candidate_statements,
    add_statement,
    find_candidate_id,
    gen_workspace_id,
)

from app.schemas.statement import StatementEdit
from app.store.client import curation_graph
from app.store.queries import (
    export_deduplicated_graph,
    get_accepted_alignment_pairs,
    get_current_candidate_statement,
    get_existing_alignment_pairs,
    get_prior_entities,
)
from app.store.utils import SCHEMA_NAME
from app.store.writer import (
    accept_statement,
    edit_statement,
    reject_statement,
    write_alignment_results,
    write_lookup_results,
)

TTL_TEXT = """
@prefix ex: <http://example.org/> .
@prefix rdf: <http://www.w3.org/1999/02/22-rdf-syntax-ns#> .
@prefix owl: <http://www.w3.org/2002/07/owl#> .

ex:maxMustermann rdf:type ex:Person .
ex:maxMustermann ex:name "Max Mustermann" .
ex:maxMustermann owl:sameAs ex:maxMustermann2 .
"""

PROVENANCE = {
    "annotations": [
        {
            "subject": "http://example.org/maxMustermann",
            "predicate": "type",
            "value": "http://example.org/Person",
            "confidence": 1.0,
            "triple_type": "entity_type",
        },
        {
            "subject": "http://example.org/maxMustermann",
            "predicate": "name",
            "value": "Max Mustermann",
            "span_start": 0,
            "span_end": 15,
            "span_text": "Max Mustermann",
            "confidence": 1.0,
            "triple_type": "literal",
        },
    ]
}


def add_entity_to_rdf_store(tmp_path, workspace_id: str, document_id: str = "doc-1"):
    add_candidate_statements(
        tmp_path, workspace_id, TTL_TEXT, PROVENANCE, document_id=document_id
    )


class TestGetPriorEntities:
    def test_returns_prior_entities(self, tmp_path):
        workspace_id = gen_workspace_id()
        add_entity_to_rdf_store(tmp_path, workspace_id, document_id="doc-1")
        entities = get_prior_entities(workspace_id, exclude_document_ids=[])

        by_uri = {e["uri"]: e for e in entities}
        entity = by_uri["http://example.org/maxMustermann"]
        assert entity["is_prior"] is True
        assert entity["source_document"] == "doc-1"
        assert "Person" in entity["types"]
        assert entity["literals"]["name"] == ["Max Mustermann"]

    def test_excludes_given_document_ids(self, tmp_path):
        workspace_id = gen_workspace_id()
        add_entity_to_rdf_store(tmp_path, workspace_id, document_id="doc-1")
        entities = get_prior_entities(workspace_id, exclude_document_ids=["doc-1"])
        assert entities == []

    def test_excludes_owl_same_as_from_entity_content(self, tmp_path):
        workspace_id = gen_workspace_id()
        add_entity_to_rdf_store(tmp_path, workspace_id, document_id="doc-1")
        entities = get_prior_entities(workspace_id, exclude_document_ids=[])
        by_uri = {e["uri"]: e for e in entities}
        entity = by_uri["http://example.org/maxMustermann"]
        assert "sameAs" not in entity.get("relations_out", {})

    def test_excludes_rejected_statements(self, tmp_path):
        workspace_id = gen_workspace_id()
        add_entity_to_rdf_store(tmp_path, workspace_id, document_id="doc-1")
        name_stmt_id = find_candidate_id(workspace_id, "http://example.org/name")
        reject_statement(name_stmt_id, uuid.uuid4(), workspace_id)
        entities = get_prior_entities(workspace_id, exclude_document_ids=[])
        by_uri = {e["uri"]: e for e in entities}
        entity = by_uri["http://example.org/maxMustermann"]
        assert "name" not in entity.get("literals", {})


class TestGetAlignmentPairs:
    def test_returns_written_alignment_pair(self, tmp_path):
        workspace_id = gen_workspace_id()
        write_alignment_results(
            [("http://example.org/a", "http://example.org/b", 1.0)],
            workspace_id,
            "run-1",
            ["doc-1", "doc-2"],
        )
        pairs = get_existing_alignment_pairs(workspace_id)
        assert frozenset({"http://example.org/a", "http://example.org/b"}) in pairs

    def test_returns_rejected_alignment_pair(self, tmp_path):
        workspace_id = gen_workspace_id()
        write_alignment_results(
            [("http://example.org/a", "http://example.org/b", 1.0)],
            workspace_id,
            "run-1",
            ["doc-1", "doc-2"],
        )
        same_as_stmt_id = find_candidate_id(
            workspace_id, "http://www.w3.org/2002/07/owl#sameAs"
        )
        reject_statement(same_as_stmt_id, uuid.uuid4(), workspace_id)
        pairs = get_existing_alignment_pairs(workspace_id)
        assert frozenset({"http://example.org/a", "http://example.org/b"}) in pairs


class TestGetCurrentCandidateStatement:
    def test_walks_multi_hop_revision_chain(self, tmp_path):
        workspace_id = gen_workspace_id()
        graph = curation_graph(workspace_id)
        original_id = add_statement(
            tmp_path,
            workspace_id,
            "http://example.org/s",
            "http://example.org/p",
            "v1",
        )
        first_edit_id = edit_statement(
            original_id,
            uuid.uuid4(),
            workspace_id,
            StatementEdit(object_value="v2"),
        )
        second_edit_id = edit_statement(
            first_edit_id,
            uuid.uuid4(),
            workspace_id,
            StatementEdit(object_value="v3"),
        )

        assert get_current_candidate_statement(original_id, graph) == second_edit_id
        assert get_current_candidate_statement(first_edit_id, graph) == second_edit_id

    def test_unknown_statement_excpt(self, tmp_path):
        workspace_id = gen_workspace_id()
        graph = curation_graph(workspace_id)

        with pytest.raises(ValueError, match="No current CandidateStatement found"):
            get_current_candidate_statement("http://example.org/does-not-exist", graph)


class TestGetAcceptedAlignmentPairs:
    def test_returns_accepted_alignment_pair(self, tmp_path):
        workspace_id = gen_workspace_id()
        write_alignment_results(
            [("http://example.org/a", "http://example.org/b", 0.9)],
            workspace_id,
            "run-1",
            ["doc-1", "doc-2"],
        )
        same_as_stmt_id = find_candidate_id(
            workspace_id, "http://www.w3.org/2002/07/owl#sameAs"
        )
        accept_statement(same_as_stmt_id, uuid.uuid4(), workspace_id)
        pairs = get_accepted_alignment_pairs(workspace_id)
        assert {frozenset(p) for p in pairs} == {
            frozenset({"http://example.org/a", "http://example.org/b"})
        }

    def test_excludes_pending_alignment_pair(self, tmp_path):
        workspace_id = gen_workspace_id()
        write_alignment_results(
            [("http://example.org/a", "http://example.org/b", 0.9)],
            workspace_id,
            "run-1",
            ["doc-1", "doc-2"],
        )
        assert get_accepted_alignment_pairs(workspace_id) == set()

    def test_excludes_lookup_pairs(self, tmp_path):
        workspace_id = gen_workspace_id()
        write_lookup_results(
            [("http://example.org/a", "http://www.wikidata.org/entity/Q1", 0.9)],
            workspace_id,
            "run-1",
            ["doc-1"],
        )
        same_as_stmt_id = find_candidate_id(
            workspace_id, "http://www.w3.org/2002/07/owl#sameAs"
        )
        accept_statement(same_as_stmt_id, uuid.uuid4(), workspace_id)
        assert get_accepted_alignment_pairs(workspace_id) == set()


class TestExportDeduplicatedGraph:
    def accept_triple(
        self,
        tmp_path,
        workspace_id: str,
        subject: str,
        label: str,
        document_id: str = "doc-1",
    ) -> None:
        ttl_text = f'<{subject}> <{SCHEMA_NAME}> "{label}" .'
        add_candidate_statements(
            tmp_path, workspace_id, ttl_text, document_id=document_id
        )
        stmt_id = find_candidate_id(workspace_id, SCHEMA_NAME, subject=subject)
        accept_statement(stmt_id, uuid.uuid4(), workspace_id)

    def test_merges_aligned_entities_and_keeps_all_labels(self, tmp_path):
        workspace_id = gen_workspace_id()
        self.accept_triple(
            tmp_path,
            workspace_id,
            "http://example.org/a",
            "RWTH Aachen",
            document_id="doc-a",
        )
        self.accept_triple(
            tmp_path,
            workspace_id,
            "http://example.org/b",
            "Rheinisch-Westfaelische Technische Hochschule Aachen",
            document_id="doc-b",
        )
        write_alignment_results(
            [("http://example.org/a", "http://example.org/b", 0.9)],
            workspace_id,
            "run-1",
            ["http://example.org/a", "http://example.org/b"],
        )
        same_as_stmt_id = find_candidate_id(
            workspace_id, "http://www.w3.org/2002/07/owl#sameAs"
        )
        accept_statement(same_as_stmt_id, uuid.uuid4(), workspace_id)
        content = export_deduplicated_graph(workspace_id)

        assert "RWTH Aachen" in content
        assert "Rheinisch-Westfaelische Technische Hochschule Aachen" in content
        assert ("example.org/a" in content) != ("example.org/b" in content)
        assert "sameAs" not in content

    def test_strips_fallback_hash_from_merged_canonical_id(self, tmp_path):
        workspace_id = gen_workspace_id()
        self.accept_triple(
            tmp_path,
            workspace_id,
            "http://example.org/RWTHAachen_a1b2c3",
            "RWTH Aachen",
            document_id="doc-a",
        )
        self.accept_triple(
            tmp_path,
            workspace_id,
            "http://example.org/RWTH_9f9f9f",
            "Rheinisch-Westfaelische Technische Hochschule Aachen",
            document_id="doc-b",
        )
        write_alignment_results(
            [
                (
                    "http://example.org/RWTHAachen_a1b2c3",
                    "http://example.org/RWTH_9f9f9f",
                    0.9,
                )
            ],
            workspace_id,
            "run-1",
            ["http://example.org/RWTHAachen_a1b2c3", "http://example.org/RWTH_9f9f9f"],
        )
        same_as_stmt_id = find_candidate_id(
            workspace_id, "http://www.w3.org/2002/07/owl#sameAs"
        )
        accept_statement(same_as_stmt_id, uuid.uuid4(), workspace_id)
        content = export_deduplicated_graph(workspace_id)
        assert "example.org/RWTHAachen_a1b2c3" not in content
        assert "example.org/RWTH_9f9f9f" not in content
        assert ("example.org/RWTHAachen>" in content) != (
            "example.org/RWTH>" in content
        )

    def test_strips_fallback_hash_from_unmerged_entity(self, tmp_path):
        workspace_id = gen_workspace_id()
        self.accept_triple(
            tmp_path,
            workspace_id,
            "http://example.org/RWTHAachen_a1b2c3",
            "RWTH Aachen",
        )
        content = export_deduplicated_graph(workspace_id)
        assert "example.org/RWTHAachen>" in content
        assert "example.org/RWTHAachen_a1b2c3" not in content

    def test_keeps_hash_when_stripping_would_collide(self, tmp_path):
        workspace_id = gen_workspace_id()
        self.accept_triple(
            tmp_path,
            workspace_id,
            "http://example.org/RWTHAachen_a1b2c3",
            "RWTH Aachen",
            document_id="doc-a",
        )
        self.accept_triple(
            tmp_path,
            workspace_id,
            "http://example.org/RWTHAachen_d4e5f6",
            "Some other RWTHAachen-named entity",
            document_id="doc-b",
        )
        content = export_deduplicated_graph(workspace_id)
        assert "example.org/RWTHAachen_a1b2c3" in content
        assert "example.org/RWTHAachen_d4e5f6" in content
        assert "example.org/RWTHAachen>" not in content
