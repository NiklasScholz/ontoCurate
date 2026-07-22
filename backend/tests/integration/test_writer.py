import uuid

import pytest
from test_utils import (
    activity_count,
    add_candidate_statements,
    find_candidate_id,
    gen_workspace_id,
    sparql_count,
)

from app.schemas.statement import StatementEdit
from app.store.client import curation_graph, data_graph, sparql_select
from app.store.utils import PACO_REJECTED, create_source_document_entity
from app.store.writer import (
    accept_statement,
    delete_document_data,
    edit_statement,
    load_candidate_statement,
    reject_statement,
    reset_statement,
    write_alignment_results,
)

TTL_TEXT = """
@prefix ex: <http://example.org/> .
ex:s ex:p "o" .
"""

PROVENANCE = {
    "source_document": "doc.md",
    "annotations": [
        {
            "subject": "http://example.org/s",
            "predicate": "p",
            "value": "o",
            "span_start": 10,
            "span_end": 11,
            "span_text": "o.",
            "confidence": 0.95,
            "triple_type": "literal",
        }
    ],
}


def test_write_candidate_statements_from_ttl(tmp_path):
    workspace_id = gen_workspace_id()
    add_candidate_statements(tmp_path, workspace_id, TTL_TEXT)

    sparql = f"""
        PREFIX paco: <https://example.org/provenance-and-curation-ontology/>
        PREFIX prov: <http://www.w3.org/ns/prov#>
        SELECT ?s ?subject ?predicate ?object ?generatedBy WHERE {{
        GRAPH <{curation_graph(workspace_id)}> {{
            ?s a paco:CandidateStatement ;
            paco:subject ?subject ;
            paco:predicate ?predicate ;
            paco:object ?object ;
            prov:wasGeneratedBy ?generatedBy .
        }}
        }}
    """
    result = sparql_select(sparql)

    bindings = result.get("results", {}).get("bindings", [])
    assert len(bindings) == 1
    assert bindings[0]["subject"]["value"] == "http://example.org/s"
    assert bindings[0]["predicate"]["value"] == "http://example.org/p"
    assert bindings[0]["object"]["value"] == "o"


def test_write_candidate_statements_with_provenance(tmp_path):
    workspace_id = gen_workspace_id()
    add_candidate_statements(tmp_path, workspace_id, TTL_TEXT, PROVENANCE)
    sparql = f"""
        PREFIX paco: <https://example.org/provenance-and-curation-ontology/>
        SELECT ?confidence ?spanText ?spanStart ?spanEnd WHERE {{
        GRAPH <{curation_graph(workspace_id)}> {{
            ?s a paco:CandidateStatement ;
            paco:confidence ?confidence ;
            paco:textSpan ?spanText ;
            paco:textSpanStart ?spanStart ;
            paco:textSpanEnd ?spanEnd .
        }}
        }}
    """
    result = sparql_select(sparql)

    bindings = result.get("results", {}).get("bindings", [])
    assert len(bindings) == 1
    assert float(bindings[0]["confidence"]["value"]) == pytest.approx(0.95)
    assert bindings[0]["spanText"]["value"] == "o."
    assert int(bindings[0]["spanStart"]["value"]) == 10
    assert int(bindings[0]["spanEnd"]["value"]) == 11


def test_accept_statement_preserves_object_datatype(tmp_path):
    workspace_id = gen_workspace_id()
    typed_ttl_text = """
        @prefix ex: <http://example.org/> .
        @prefix xsd: <http://www.w3.org/2001/XMLSchema#> .
        ex:conf ex:startDate "2024"^^xsd:gYear .
    """
    provenance = {
        "annotations": [
            {
                "subject": "http://example.org/conf",
                "predicate": "startDate",
                "value": "2024",
                "span_start": 0,
                "span_end": 4,
                "span_text": "2024",
                "confidence": 0.9,
                "triple_type": "literal",
            }
        ]
    }
    add_candidate_statements(tmp_path, workspace_id, typed_ttl_text, provenance)

    stmt_id = find_candidate_id(workspace_id, "http://example.org/startDate")
    accept_statement(stmt_id, uuid.uuid4(), workspace_id)
    sparql = f"""
        SELECT ?o WHERE {{
        GRAPH <{data_graph(workspace_id)}> {{
            <http://example.org/conf> <http://example.org/startDate> ?o .
        }}
        }}
    """
    bindings = sparql_select(sparql).get("results", {}).get("bindings", [])
    assert len(bindings) == 1
    assert bindings[0]["o"]["value"] == "2024"
    assert bindings[0]["o"]["datatype"] == "http://www.w3.org/2001/XMLSchema#gYear"


def count_candidate_statements_derived_from(workspace_id: str, document_id: str) -> int:
    """Count candidate statements that have a prov:wasDerivedFrom link to the given document."""
    source_document = create_source_document_entity(workspace_id, document_id).value
    sparql = f"""
PREFIX prov: <http://www.w3.org/ns/prov#>
SELECT (COUNT(DISTINCT ?cs) AS ?count) WHERE {{
  GRAPH <{curation_graph(workspace_id)}> {{
    ?cs prov:wasDerivedFrom <{source_document}> .
  }}
}}
    """
    return sparql_count(sparql)


def count_candidate_statement_chain(workspace_id: str, document_id: str) -> int:
    """Count every revision derived (transitively) from the document, i.e. the
    full edit/reject/accept/reset chain, not just the statement it produced first."""
    source_document = create_source_document_entity(workspace_id, document_id).value
    sparql = f"""
PREFIX prov: <http://www.w3.org/ns/prov#>
SELECT (COUNT(DISTINCT ?cs) AS ?count) WHERE {{
  GRAPH <{curation_graph(workspace_id)}> {{
    ?cs prov:wasDerivedFrom+ <{source_document}> .
  }}
}}
    """
    return sparql_count(sparql)


def count_source_document_triples(workspace_id: str, document_id: str) -> int:
    """Count triples in the curation graph for the given document (entity)"""
    source_document = create_source_document_entity(workspace_id, document_id).value
    sparql = f"""
        SELECT (COUNT(*) AS ?count) WHERE {{
        GRAPH <{curation_graph(workspace_id)}> {{
            <{source_document}> ?p ?o .
        }}
        }}
    """
    return sparql_count(sparql)


class TestDeleteDocumentData:
    def test_removes_stuff_from_curation_graph(self, tmp_path):
        workspace_id = gen_workspace_id()
        add_candidate_statements(tmp_path, workspace_id, TTL_TEXT)

        assert count_candidate_statements_derived_from(workspace_id, "doc-1") == 1
        assert count_source_document_triples(workspace_id, "doc-1") > 0
        assert activity_count(workspace_id, "ExtractionActivity") == 1

        delete_document_data(workspace_id, "doc-1")

        assert count_candidate_statements_derived_from(workspace_id, "doc-1") == 0
        assert count_source_document_triples(workspace_id, "doc-1") == 0
        assert activity_count(workspace_id, "ExtractionActivity") == 0

    def test_removes_accepted_triple_from_data_graph(self, tmp_path):
        workspace_id = gen_workspace_id()
        add_candidate_statements(tmp_path, workspace_id, TTL_TEXT, PROVENANCE)
        stmt_id = find_candidate_id(workspace_id, "http://example.org/p")
        accept_statement(stmt_id, uuid.uuid4(), workspace_id)

        data_sparql = f"""
            SELECT (COUNT(*) AS ?count) WHERE {{
            GRAPH <{data_graph(workspace_id)}> {{ <http://example.org/s> <http://example.org/p> "o" }}
            }}
        """
        assert sparql_count(data_sparql) == 1
        delete_document_data(workspace_id, "doc-1")
        assert sparql_count(data_sparql) == 0

        candidate_sparql = f"""
            PREFIX paco: <https://example.org/provenance-and-curation-ontology/>
            SELECT (COUNT(*) AS ?count) WHERE {{
            GRAPH <{curation_graph(workspace_id)}> {{
                ?cs a paco:CandidateStatement .
            }}
            }}
        """
        assert sparql_count(candidate_sparql) == 0

    def test_removes_edit_reject_accept(self, tmp_path):
        """Deleting a document should remove every revision and every kind of
        activity a statement went through, not just the final one."""
        workspace_id = gen_workspace_id()
        add_candidate_statements(tmp_path, workspace_id, TTL_TEXT, PROVENANCE)
        original_id = find_candidate_id(workspace_id, "http://example.org/p")

        edited_id = edit_statement(
            original_id,
            uuid.uuid4(),
            workspace_id,
            StatementEdit(object_value="edited-value"),
        )
        rejected_id = reject_statement(edited_id, uuid.uuid4(), workspace_id)
        accept_statement(rejected_id, uuid.uuid4(), workspace_id)

        data_sparql = f"""
SELECT (COUNT(*) AS ?count) WHERE {{
  GRAPH <{data_graph(workspace_id)}> {{ <http://example.org/s> <http://example.org/p> "edited-value" }}
}}
        """
        assert count_candidate_statement_chain(workspace_id, "doc-1") == 4
        assert activity_count(workspace_id, "EditingActivity") == 1
        assert activity_count(workspace_id, "RejectingActivity") == 1
        assert activity_count(workspace_id, "AcceptingActivity") == 1
        assert sparql_count(data_sparql) == 1
        assert count_source_document_triples(workspace_id, "doc-1") > 0

        delete_document_data(workspace_id, "doc-1")

        assert count_candidate_statement_chain(workspace_id, "doc-1") == 0
        assert activity_count(workspace_id, "EditingActivity") == 0
        assert activity_count(workspace_id, "RejectingActivity") == 0
        assert activity_count(workspace_id, "AcceptingActivity") == 0
        assert sparql_count(data_sparql) == 0
        assert count_source_document_triples(workspace_id, "doc-1") == 0

    def test_removes_alignment_activity_and_triple(self, tmp_path):
        workspace_id = gen_workspace_id()
        add_candidate_statements(tmp_path, workspace_id, TTL_TEXT, document_id="doc-1")
        add_candidate_statements(
            tmp_path,
            workspace_id,
            '@prefix ex: <http://example.org/> .\nex:s2 ex:p2 "o2" .\n',
            document_id="doc-2",
        )

        write_alignment_results(
            [("http://example.org/s", "http://example.org/s2", 0.95)],
            workspace_id,
            "run-1",
            ["doc-1", "doc-2"],
        )

        same_as_sparql = f"""
            PREFIX paco: <https://example.org/provenance-and-curation-ontology/>
            PREFIX owl: <http://www.w3.org/2002/07/owl#>
            SELECT (COUNT(*) AS ?count) WHERE {{
            GRAPH <{curation_graph(workspace_id)}> {{
                ?cs a paco:CandidateStatement ;
                    paco:predicate owl:sameAs ;
                    paco:subject <http://example.org/s2> ;
                    paco:object <http://example.org/s> .
            }}
            }}
        """
        assert activity_count(workspace_id, "AlignmentActivity") == 1
        assert sparql_count(same_as_sparql) == 1

        delete_document_data(workspace_id, "doc-1")

        assert activity_count(workspace_id, "AlignmentActivity") == 0
        assert sparql_count(same_as_sparql) == 0

    def test_leaves_only_deletes_for_specified_document(self, tmp_path):
        workspace_id = gen_workspace_id()
        add_candidate_statements(tmp_path, workspace_id, TTL_TEXT, document_id="doc-1")
        add_candidate_statements(
            tmp_path,
            workspace_id,
            '@prefix ex: <http://example.org/> .\nex:s2 ex:p2 "o2" .\n',
            document_id="doc-2",
        )
        delete_document_data(workspace_id, "doc-1")
        assert count_candidate_statements_derived_from(workspace_id, "doc-1") == 0
        assert count_candidate_statements_derived_from(workspace_id, "doc-2") == 1


class TestStatementStatusChange:
    def test_reject_writer(self, tmp_path):
        workspace_id = gen_workspace_id()
        add_candidate_statements(tmp_path, workspace_id, TTL_TEXT, PROVENANCE)
        stmt_id = find_candidate_id(workspace_id, "http://example.org/p")
        new_id = reject_statement(stmt_id, uuid.uuid4(), workspace_id)
        new_stmt = load_candidate_statement(new_id, curation_graph(workspace_id))
        assert new_stmt["status"] == PACO_REJECTED
        assert new_stmt["is_current"] == "true"
        old_stmt = load_candidate_statement(stmt_id, curation_graph(workspace_id))
        assert old_stmt["is_current"] == "false"

    def test_edit_subject_and_predicate(self, tmp_path):
        workspace_id = gen_workspace_id()
        add_candidate_statements(tmp_path, workspace_id, TTL_TEXT, PROVENANCE)
        stmt_id = find_candidate_id(workspace_id, "http://example.org/p")
        new_id = edit_statement(
            stmt_id,
            uuid.uuid4(),
            workspace_id,
            StatementEdit(
                subject="http://example.org/s2", predicate="http://example.org/p2"
            ),
        )
        new_stmt = load_candidate_statement(new_id, curation_graph(workspace_id))
        assert new_stmt["subject"] == "http://example.org/s2"
        assert new_stmt["predicate"] == "http://example.org/p2"


class TestResetStatement:
    def test_reset_after_reject_restores_original_version(self, tmp_path):
        workspace_id = gen_workspace_id()
        add_candidate_statements(tmp_path, workspace_id, TTL_TEXT, PROVENANCE)
        original_id = find_candidate_id(workspace_id, "http://example.org/p")

        rejected_id = reject_statement(original_id, uuid.uuid4(), workspace_id)
        response = reset_statement(rejected_id, uuid.uuid4(), workspace_id)

        assert response.subject == "http://example.org/s"
        assert response.object == "o"

        rejected_stmt = load_candidate_statement(
            rejected_id, curation_graph(workspace_id)
        )
        assert rejected_stmt["is_current"] == "false"
        assert count_candidate_statement_chain(workspace_id, "doc-1") == 3

    def test_reset_after_accept_removes_data_graph_triple(self, tmp_path):
        workspace_id = gen_workspace_id()
        add_candidate_statements(tmp_path, workspace_id, TTL_TEXT, PROVENANCE)
        original_id = find_candidate_id(workspace_id, "http://example.org/p")
        accepted_id = accept_statement(original_id, uuid.uuid4(), workspace_id)

        data_sparql = f"""
        SELECT (COUNT(*) AS ?count) WHERE {{
        GRAPH <{data_graph(workspace_id)}> {{ <http://example.org/s> <http://example.org/p> "o" }}
        }}
        """
        assert sparql_count(data_sparql) == 1
        assert count_candidate_statement_chain(workspace_id, "doc-1") == 2
        reset_statement(accepted_id, uuid.uuid4(), workspace_id)
        assert count_candidate_statement_chain(workspace_id, "doc-1") == 3
        assert sparql_count(data_sparql) == 0

    def test_reset_non_current_statement_excpt(self, tmp_path):
        workspace_id = gen_workspace_id()
        add_candidate_statements(tmp_path, workspace_id, TTL_TEXT, PROVENANCE)
        original_id = find_candidate_id(workspace_id, "http://example.org/p")
        reject_statement(original_id, uuid.uuid4(), workspace_id)

        with pytest.raises(ValueError, match="current statement version"):
            reset_statement(original_id, uuid.uuid4(), workspace_id)

    def test_reset_original_pending_statement_excpt(self, tmp_path):
        workspace_id = gen_workspace_id()
        add_candidate_statements(tmp_path, workspace_id, TTL_TEXT, PROVENANCE)
        original_id = find_candidate_id(workspace_id, "http://example.org/p")

        with pytest.raises(ValueError, match="already the current version"):
            reset_statement(original_id, uuid.uuid4(), workspace_id)
