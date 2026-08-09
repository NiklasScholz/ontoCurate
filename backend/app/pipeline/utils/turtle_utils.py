from collections import defaultdict
from pathlib import Path

from rdflib import Graph, Literal, URIRef
from rdflib.namespace import OWL, RDF


def sparql_binding_to_term(binding: dict) -> URIRef | Literal:
    """Convert a SPARQL JSON result binding into the matching rdflib term."""
    if binding["type"] == "uri":
        return URIRef(binding["value"])
    return Literal(
        binding["value"],
        datatype=binding.get("datatype"),
        lang=binding.get("xml:lang"),
    )


def local_name(uri) -> str | None:
    """Extract the local name from a URI (i.e., strips the prefix)."""
    if uri is None:
        return None
    s = str(uri)
    if not s.startswith("http"):
        return s
    return s.split("#")[-1].split("/")[-1]


def load_entity_information(
    source: Path | Graph, exclude_owlSameAs: bool = True
) -> list[dict]:
    """Loads all named entities and their properties from a ttl file or an
    already-parsed rdflib Graph.

    Returns list of entity dicts:
        {
            "uri":           str,
            "types":         list[str],
            "literals":      dict[str, list[str]],
            "relations_out": dict[str, list[str]],
            "relations_in":  dict[str, list[str]],
        }
    """
    if isinstance(source, Graph):
        g = source
    else:
        g = Graph()
        g.parse(source, format="turtle")

    out_edges: dict = defaultdict(list)  # s -> [(p, o)]
    in_edges: dict = defaultdict(list)  # o -> [(s, p)]
    types: dict = defaultdict(set)
    literals: dict = defaultdict(lambda: defaultdict(list))

    all_entities: set = set()
    for s, p, o in g:
        all_entities.add(s)
        if p == RDF.type:
            types[s].add(o)
            continue
        if exclude_owlSameAs and p == OWL.sameAs:
            continue
        if isinstance(o, Literal):
            literals[s][local_name(p)].append(str(o))
        else:
            out_edges[s].append((p, o))
            in_edges[o].append((s, p))

    all_entities.update(types.keys())

    entities = []
    for e in all_entities:
        rel_out: dict = defaultdict(list)
        for p, o in out_edges.get(e, []):
            rel_out[local_name(p)].append(str(o))

        rel_in: dict = defaultdict(list)
        for s, p in in_edges.get(e, []):
            rel_in[local_name(p)].append(str(s))

        entities.append(
            {
                "uri": str(e),
                "types": sorted(local_name(t) for t in types.get(e, [])),
                "literals": dict(literals.get(e, {})),
                "relations_out": dict(rel_out),
                "relations_in": dict(rel_in),
            }
        )

    return entities


def collect_literal_triples(
    graph: Graph, uri_as_literal_predicates: frozenset[str] = frozenset()
) -> list[tuple[str, str, str]]:
    """Return (subject_uri, predicate_local_name, object_value) for every literal
    triple and URIRef objects matching literal predicates."""
    rows = []
    for s, p, o in graph:
        if not isinstance(s, URIRef):
            continue
        if p == RDF.type:
            continue
        if isinstance(o, Literal):
            rows.append((str(s), local_name(p), str(o)))
        elif isinstance(o, URIRef) and local_name(p) in uri_as_literal_predicates:
            rows.append((str(s), local_name(p), str(o)))
    return rows


def collect_entity_triples(
    graph: Graph, exclude_predicates: frozenset[str] = frozenset()
) -> list[tuple[str, str, str]]:
    """Return (subject_uri, predicate_local_name, object_uri) for every
    object property triple; skips blank nodes, rdf:type, and any predicate in
    `exclude_predicates` used for literal scoring instead."""
    rows = []
    for s, p, o in graph:
        if not isinstance(s, URIRef) or not isinstance(o, URIRef):
            continue
        if p == RDF.type:
            continue
        name = local_name(p)
        if name in exclude_predicates:
            continue
        rows.append((str(s), name, str(o)))
    return rows


def collect_rdf_type_triples(graph: Graph) -> list[tuple[str, str]]:
    """Return (subject_uri, full_type_uri) for every rdf:type triple."""
    rows = []
    for s, p, o in graph:
        if p == RDF.type and isinstance(s, URIRef) and isinstance(o, URIRef):
            rows.append((str(s), str(o)))
    return rows


def build_type_index(graph: Graph) -> dict[str, set[str]]:
    """Return {subject_uri: {type_local_name, ...}} from rdf:type triples."""
    index: dict[str, set[str]] = {}
    for s, p, o in graph:
        if p == RDF.type and isinstance(s, URIRef) and isinstance(o, URIRef):
            index.setdefault(str(s), set()).add(local_name(o))
    return index
