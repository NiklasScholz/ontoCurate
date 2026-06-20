"""Tests for app.pipeline.utils.turtle_utils"""

from rdflib import Graph as RdflibGraph

from app.pipeline.utils.turtle_utils import (
    build_type_index,
    collect_entity_triples,
    collect_literal_triples,
    collect_rdf_type_triples,
    load_entity_information,
    local_name,
)


class TestCollectRdfTypeTriples:
    def make_graph(self, ttl: str):
        g = RdflibGraph()
        g.parse(data=ttl, format="turtle")
        return g

    def test_returns_subject_and_full_type_uri(self):
        g = self.make_graph("""
            @prefix ex: <http://example.org/> .
            @prefix rdf: <http://www.w3.org/1999/02/22-rdf-syntax-ns#> .
            ex:paper1 rdf:type ex:Paper .
        """)
        result = collect_rdf_type_triples(g)
        assert len(result) == 1
        subject, type_uri = result[0]
        assert subject == "http://example.org/paper1"
        assert type_uri == "http://example.org/Paper"

    def test_multiple_types_for_same_subject(self):
        g = self.make_graph("""
            @prefix ex: <http://example.org/> .
            @prefix rdf: <http://www.w3.org/1999/02/22-rdf-syntax-ns#> .
            ex:paper1 rdf:type ex:Paper ;
                      rdf:type ex:Entity .
        """)
        result = collect_rdf_type_triples(g)
        assert len(result) == 2
        subjects = {s for s, _ in result}
        types = {t for _, t in result}
        assert subjects == {"http://example.org/paper1"}
        assert "http://example.org/Paper" in types
        assert "http://example.org/Entity" in types

    def test_multiple_subjects(self):
        g = self.make_graph("""
            @prefix ex: <http://example.org/> .
            @prefix rdf: <http://www.w3.org/1999/02/22-rdf-syntax-ns#> .
            ex:paper1 rdf:type ex:Paper .
            ex:author1 rdf:type ex:Person .
        """)
        result = collect_rdf_type_triples(g)
        assert len(result) == 2

    def test_no_type_triples_returns_empty(self):
        g = self.make_graph("""
            @prefix ex: <http://example.org/> .
            ex:paper1 ex:title "Some Title" .
        """)
        result = collect_rdf_type_triples(g)
        assert result == []


class TestLocalName:
    def test_hash_uri_returns_fragment(self):
        assert local_name("http://www.w3.org/2000/01/rdf-schema#label") == "label"

    def test_slash_uri_returns_last_segment(self):
        assert local_name("http://example.org/ontology/Paper") == "Paper"

    def test_non_http_uri_returned_as_is(self):
        assert local_name("someLocalName") == "someLocalName"

    def test_none_returns_none(self):
        assert local_name(None) is None


class TestCollectLiteralTriples:
    def make_graph(self, ttl: str):
        g = RdflibGraph()
        g.parse(data=ttl, format="turtle")
        return g

    def test_returns_subject_predicate_value(self):
        g = self.make_graph("""
            @prefix ex: <http://example.org/> .
            ex:paper1 ex:title "Entity Alignment for Knowledge Graphs";
            ex:abstract "A survey paper." .
        """)
        result = collect_literal_triples(g)
        assert len(result) == 2
        subject, predicate, value = result[0]
        assert subject == "http://example.org/paper1"
        assert predicate == "title" or predicate == "abstract"
        assert value == "Entity Alignment for Knowledge Graphs"
        subject, predicate, value = result[1]
        assert subject == "http://example.org/paper1"
        assert predicate == "abstract" or predicate == "title"
        assert value == "A survey paper."

    def test_skips_non_literal_objects(self):
        g = self.make_graph("""
            @prefix ex: <http://example.org/> .
            ex:paper1 ex:author ex:author1 .
        """)
        result = collect_literal_triples(g)
        assert result == []


class TestCollectEntityTriples:
    def make_graph(self, ttl: str):
        g = RdflibGraph()
        g.parse(data=ttl, format="turtle")
        return g

    def test_returns_subject_predicate_object(self):
        g = self.make_graph("""
            @prefix ex: <http://example.org/> .
            @prefix rdf: <http://www.w3.org/1999/02/22-rdf-syntax-ns#> .
            ex:paper1 rdf:type ex:Paper;
                ex:author ex:author1 ;
                ex:author ex:author2 .
        """)
        result = collect_entity_triples(g)
        assert (
            len(result) == 2
        ), f"Expected 2 entity triples, got {len(result)}. Check that rdf:type is excluded."
        subject, predicate, obj = result[0]
        assert subject == "http://example.org/paper1"
        assert predicate == "author"
        assert (
            obj == "http://example.org/author1" or obj == "http://example.org/author2"
        )
        subject, predicate, obj = result[1]
        assert subject == "http://example.org/paper1"
        assert predicate == "author"
        assert (
            obj == "http://example.org/author2" or obj == "http://example.org/author1"
        )

    def test_skips_literal_objects(self):
        g = self.make_graph("""
            @prefix ex: <http://example.org/> .
            ex:paper1 ex:title "Knowledge Graphs" .
        """)
        result = collect_entity_triples(g)
        assert result == []


class TestBuildTypeIndex:
    def make_graph(self, ttl: str):
        g = RdflibGraph()
        g.parse(data=ttl, format="turtle")
        return g

    def test_multiple_types_for_same_subject(self):
        g = self.make_graph("""
            @prefix ex: <http://example.org/> .
            @prefix rdf: <http://www.w3.org/1999/02/22-rdf-syntax-ns#> .
            ex:paper1 rdf:type ex:Paper ;
                      rdf:type ex:AcademicArticle .
        """)
        index = build_type_index(g)
        assert index["http://example.org/paper1"] == {"Paper", "AcademicArticle"}

    def test_multiple_subjects(self):
        g = self.make_graph("""
            @prefix ex: <http://example.org/> .
            @prefix rdf: <http://www.w3.org/1999/02/22-rdf-syntax-ns#> .
            ex:paper1 rdf:type ex:Paper .
            ex:author1 rdf:type ex:Person .
        """)
        index = build_type_index(g)
        assert "http://example.org/paper1" in index
        assert "http://example.org/author1" in index

    def test_non_type_triples_are_excluded(self):
        g = self.make_graph("""
            @prefix ex: <http://example.org/> .
            ex:paper1 ex:title "Knowledge Graphs" .
        """)
        assert build_type_index(g) == {}


class TestLoadEntityInformation:
    TTL = """\
@prefix ex: <http://example.org/> .
@prefix rdf: <http://www.w3.org/1999/02/22-rdf-syntax-ns#> .

ex:paper1 rdf:type ex:AcademicArticle ;
          ex:title "Knowledge Graph Entity Alignment" ;
          ex:author ex:author1 .

ex:author1 rdf:type ex:Person ;
           ex:name "Alice Smith" .
"""

    def test_entity_has_required_keys(self, tmp_path):
        ttl_path = tmp_path / "test.ttl"
        ttl_path.write_text(self.TTL, encoding="utf-8")
        result = load_entity_information(ttl_path)
        for entity in result:
            assert "uri" in entity
            assert "types" in entity
            assert "literals" in entity
            assert "relations_out" in entity
            assert "relations_in" in entity

    def test_entity_load_is_correct(self, tmp_path):
        ttl_path = tmp_path / "test.ttl"
        ttl_path.write_text(self.TTL, encoding="utf-8")
        result = load_entity_information(ttl_path)
        paper = next(e for e in result if e["uri"] == "http://example.org/paper1")
        assert "title" in paper["literals"]
        assert paper["literals"]["title"] == ["Knowledge Graph Entity Alignment"]
        assert "AcademicArticle" in paper["types"]
        assert "author" in paper["relations_out"]
        assert "http://example.org/author1" in paper["relations_out"]["author"]

        author = next(e for e in result if e["uri"] == "http://example.org/author1")
        assert "author" in author["relations_in"]
        assert "http://example.org/paper1" in author["relations_in"]["author"]
