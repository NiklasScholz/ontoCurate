import pytest


def test_write_candidate_statements_from_ttl(tmp_path, monkeypatch):
    """Test that TTL produced by the writer is imported into the workspace
    curation graph.
    """
    ttl_text = """
    @prefix ex: <http://example.org/> .
    ex:s ex:p "o" .
    """

    ttl_file = tmp_path / "sample.ttl"
    ttl_file.write_text(ttl_text, encoding="utf-8")

    from backend.app.store.client import curation_graph, sparql_select
    from backend.app.store.writer import write_candidate_statements_from_ttl

    workspace_id = "test-ws"

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
    try:
        result = sparql_select(sparql)
    except Exception as exc:
        pytest.skip(f"Oxigraph HTTP endpoint is unavailable for the test run: {exc}")

    bindings = result.get("results", {}).get("bindings", [])
    assert len(bindings) == 1
    assert bindings[0]["subject"]["value"] == "http://example.org/s"
    assert bindings[0]["predicate"]["value"] == "http://example.org/p"
    assert bindings[0]["object"]["value"] == "o"
