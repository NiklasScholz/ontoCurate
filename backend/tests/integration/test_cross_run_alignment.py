from pathlib import Path

from test_utils import add_candidate_statements, gen_workspace_id, sparql_count

from app.pipeline.entity_alignment import run_cross_document_alignment
from app.store.client import curation_graph
from app.store.queries import get_existing_alignment_pairs
from app.store.writer import write_alignment_results

ALIGNMENT_CONFIG_PATH = (
    Path(__file__).parent.parent.parent
    / "config"
    / "scholarySchema"
    / "alignment_config.yaml"
)


def get_person_ttl(uri: str, family_name: str, name: str) -> str:
    return f"""
        @prefix ex: <http://example.org/> .
        @prefix rdf: <http://www.w3.org/1999/02/22-rdf-syntax-ns#> .
        <{uri}> rdf:type ex:Person .
        <{uri}> ex:familyName "{family_name}" .
        <{uri}> ex:name "{name}" .
    """


def get_person_provenance(uri: str) -> dict:
    return {
        "annotations": [
            {
                "subject": uri,
                "predicate": "type",
                "value": "http://example.org/Person",
                "confidence": 0.9,
                "triple_type": "entity_type",
            }
        ]
    }


class TestCrossRunAlignment:
    # Integration test checking that oxigraph is used correctly during entity alignment across runs
    def test_align_new_run_entity_to_prior_run_entity(self, tmp_path):
        workspace_id = gen_workspace_id()
        prior_uri = "http://example.org/prior-smith"
        current_uri = "http://example.org/current-smith"
        add_candidate_statements(
            tmp_path,
            workspace_id,
            get_person_ttl(prior_uri, "Smith", "Alice"),
            get_person_provenance(prior_uri),
            document_id="doc-prior",
        )

        working_dir = tmp_path / "work"
        working_dir.mkdir()
        (working_dir / "doc-current.ttl").write_text(
            get_person_ttl(current_uri, "Smith", "Alice "), encoding="utf-8"
        )
        run_cross_document_alignment(
            working_dir, workspace_id, "run-2", ALIGNMENT_CONFIG_PATH
        )
        pairs = get_existing_alignment_pairs(workspace_id)
        assert frozenset({prior_uri, current_uri}) in pairs

    def test_no_duplicate_pairs_after_multiple_runs(self, tmp_path):
        workspace_id = gen_workspace_id()
        prior_uri = "http://example.org/prior-smith"
        current_uri = "http://example.org/current-smith"

        add_candidate_statements(
            tmp_path,
            workspace_id,
            get_person_ttl(prior_uri, "Smith", "Alice"),
            get_person_provenance(prior_uri),
            document_id="doc-prior",
        )
        # add alignment result for prior and current entity from previous run
        write_alignment_results(
            [(prior_uri, current_uri, 0.95)],
            workspace_id,
            "run-0",
            ["doc-prior", "doc-current"],
        )
        # mock extraction output
        working_dir = tmp_path / "work"
        working_dir.mkdir()
        (working_dir / "doc-current.ttl").write_text(
            get_person_ttl(current_uri, "Smith", "Alice "), encoding="utf-8"
        )

        run_cross_document_alignment(
            working_dir, workspace_id, "run-2", ALIGNMENT_CONFIG_PATH
        )
        # check that only one same as triple is there
        sparql = f"""
            PREFIX paco: <https://example.org/provenance-and-curation-ontology/>
            PREFIX owl: <http://www.w3.org/2002/07/owl#>
            SELECT (COUNT(*) AS ?count) WHERE {{
            GRAPH <{curation_graph(workspace_id)}> {{
                ?s a paco:CandidateStatement ;
                paco:predicate owl:sameAs ;
                paco:subject ?sameEntity ;
                paco:object ?sameEntity2 .
                FILTER (
                (?sameEntity = <{prior_uri}> && ?sameEntity2 = <{current_uri}>) ||
                (?sameEntity = <{current_uri}> && ?sameEntity2 = <{prior_uri}>)
                )
            }}
            }}
        """
        assert sparql_count(sparql) == 1

    def test_no_two_prior_entities_compared(self, tmp_path):
        """Tests that we do not have too high runtime complexity because of unnecessary comparisons"""
        workspace_id = gen_workspace_id()
        prior_uri_a = "http://example.org/prior-a"
        prior_uri_b = "http://example.org/prior-b"
        for uri, doc_id in [(prior_uri_a, "doc-a"), (prior_uri_b, "doc-b")]:
            add_candidate_statements(
                tmp_path,
                workspace_id,
                get_person_ttl(uri, "Scholz", "Scholz Niklas"),
                get_person_provenance(uri),
                document_id=doc_id,
            )

        working_dir = tmp_path / "working_dir"
        working_dir.mkdir()
        (working_dir / "doc-current.ttl").write_text(
            get_person_ttl("http://example.org/current", "Scholz", "Scholz N."),
            encoding="utf-8",
        )
        run_cross_document_alignment(
            working_dir, workspace_id, "run-2", ALIGNMENT_CONFIG_PATH
        )
        pairs = get_existing_alignment_pairs(workspace_id)
        assert frozenset({prior_uri_a, prior_uri_b}) not in pairs
        assert frozenset({prior_uri_a, "http://example.org/current"}) in pairs
