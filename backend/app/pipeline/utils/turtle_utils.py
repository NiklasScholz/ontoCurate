from collections import defaultdict
from pathlib import Path

from rdflib import Graph, Literal
from rdflib.namespace import OWL, RDF


def get_local_name(uri) -> str:
    """Extract the local name from a URI (e.g. "http://example.com/Person" -> "Person")."""
    uri = str(uri)
    if "#" in uri:
        return uri.rsplit("#", 1)[1]
    return uri.rsplit("/", 1)[1]


def load_entity_information(
    ttl_path: Path, exclude_owlSameAs: bool = True
) -> list[dict]:
    """Loads  all named entities and their properties from a ttl

    Returns list of entity dicts:
        {
            "uri":           str,
            "types":         list[str],
            "literals":      dict[str, list[str]],
            "relations_out": dict[str, list[str]],
            "relations_in":  dict[str, list[str]],
        }
    """
    g = Graph()
    g.parse(ttl_path, format="turtle")

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
            literals[s][get_local_name(p)].append(str(o))
        else:
            out_edges[s].append((p, o))
            in_edges[o].append((s, p))

    all_entities.update(types.keys())

    entities = []
    for e in all_entities:
        rel_out: dict = defaultdict(list)
        for p, o in out_edges.get(e, []):
            rel_out[get_local_name(p)].append(str(o))

        rel_in: dict = defaultdict(list)
        for s, p in in_edges.get(e, []):
            rel_in[get_local_name(p)].append(str(s))

        entities.append(
            {
                "uri": str(e),
                "types": sorted(get_local_name(t) for t in types.get(e, [])),
                "literals": dict(literals.get(e, {})),
                "relations_out": dict(rel_out),
                "relations_in": dict(rel_in),
            }
        )

    return entities
