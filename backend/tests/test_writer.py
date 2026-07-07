import json
import uuid

import pytest

from app.store.client import curation_graph, sparql_select
from app.store.writer import write_candidate_statements_from_ttl

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
            "span_text": "o",
            "confidence": 0.95,
            "triple_type": "literal",
        }
    ],
}


def gen_workspace_id():
    return f"test-ws-{uuid.uuid4().hex[:8]}"


def test_write_candidate_statements_from_ttl(tmp_path):
    """Tests if candidate staements is inserted correctly"""
    ttl_file = tmp_path / "sample.ttl"
    ttl_file.write_text(TTL_TEXT, encoding="utf-8")
    workspace_id = gen_workspace_id()

    write_candidate_statements_from_ttl("run-1", "doc-1", ttl_file, workspace_id)

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
    """Tests if provenance annotation works"""
    ttl_file = tmp_path / "sample.ttl"
    ttl_file.write_text(TTL_TEXT, encoding="utf-8")
    prov_file = tmp_path / "provenance.json"
    prov_file.write_text(json.dumps(PROVENANCE), encoding="utf-8")
    workspace_id = gen_workspace_id()

    write_candidate_statements_from_ttl(
        "run-1", "doc-1", ttl_file, workspace_id, provenance_path=prov_file
    )

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
    assert bindings[0]["spanText"]["value"] == "o"
    assert int(bindings[0]["spanStart"]["value"]) == 10
    assert int(bindings[0]["spanEnd"]["value"]) == 11


def test_write_candidate_statements_without_provenance_has_no_confidence(tmp_path):
    """Tests if candidate statements are inserted without provenance."""
    ttl_file = tmp_path / "sample.ttl"
    ttl_file.write_text(TTL_TEXT, encoding="utf-8")
    workspace_id = gen_workspace_id()

    write_candidate_statements_from_ttl("run-1", "doc-1", ttl_file, workspace_id)

    sparql = f"""
PREFIX paco: <https://example.org/provenance-and-curation-ontology/>
SELECT ?s WHERE {{
  GRAPH <{curation_graph(workspace_id)}> {{
    ?s a paco:CandidateStatement .
    FILTER EXISTS {{ ?s paco:confidence ?c }}
  }}
}}
    """
    result = sparql_select(sparql)

    bindings = result.get("results", {}).get("bindings", [])
    assert len(bindings) == 0
