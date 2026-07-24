from enum import Enum

import httpx
from rdflib import Graph, Namespace

from app.core.config import settings


class ExportFormat(str, Enum):
    turtle = "turtle"
    json_ld = "json-ld"


EXPORT_FORMAT_MEDIA_TYPES: dict[ExportFormat, tuple[str, str]] = {
    ExportFormat.turtle: ("text/turtle", "ttl"),
    ExportFormat.json_ld: ("application/ld+json", "jsonld"),
}


def sparql_select(query: str, restrict_to_graph: str | None = None) -> dict:
    """Execute a SPARQL SELECT/ASK query and return parsed JSON results.

    If restrict_to_graph is given, the query's dataset is pinned to that single
    named graph via the SPARQL 1.1 protocol's default-graph-uri/named-graph-uri
    parameters. This is enforced by Oxigraph itself: an explicit `GRAPH <iri>`
    clause in the query text for any other graph matches nothing, and `GRAPH ?g`
    can only ever bind to the permitted graph. Callers passing untrusted,
    user-supplied queries must always set this.
    """
    params = (
        {
            "default-graph-uri": restrict_to_graph,
            "named-graph-uri": restrict_to_graph,
        }
        if restrict_to_graph is not None
        else {}
    )
    response = httpx.post(
        f"{settings.oxigraph_url}/query",
        params=params,
        content=query.encode(),
        headers={
            "Content-Type": "application/sparql-query",
            "Accept": "application/sparql-results+json",
        },
        timeout=30.0,
    )
    response.raise_for_status()
    return response.json()


def sparql_update(query: str) -> None:
    """Execute a SPARQL UPDATE query (INSERT DATA, DELETE DATA, DROP, etc.)."""
    response = httpx.post(
        f"{settings.oxigraph_url}/update",
        content=query.encode(),
        headers={"Content-Type": "application/sparql-update"},
        timeout=120.0,
    )
    response.raise_for_status()


def curation_graph(workspace_id: str) -> str:
    """Named graph IRI for all CandidateStatements in a workspace."""
    return f"https://ontocurate.org/workspaces/{workspace_id}/graphs/provenance"


def data_graph(workspace_id: str) -> str:
    """Named graph IRI for accepted triples only."""
    return f"https://ontocurate.org/workspaces/{workspace_id}/graphs/data"


def sparql_construct(query: str) -> str:
    """Execute a SPARQL CONSTRUCT query and return the result as Turtle text."""
    response = httpx.post(
        f"{settings.oxigraph_url}/query",
        content=query.encode(),
        headers={
            "Content-Type": "application/sparql-query",
            "Accept": "text/turtle",
        },
        timeout=30.0,
    )
    response.raise_for_status()
    return response.text


def serialize_export(
    turtle_text: str, format: ExportFormat, prefixes: dict[str, str]
) -> str:
    """Re-serialize CONSTRUCT-query Turtle output in the requested export
    format, abbreviating URIs to CURIEs wherever a namespace in `prefixes` is
    known. Turtle output gets standard @prefix declarations; JSON-LD gets an
    explicit @context for compaction -- Oxigraph's own serializers do neither
    (they always emit full URIs, regardless of PREFIX declarations in the
    query), so this step has to happen after the fact, on our side."""
    # A prefix name can only ever point to one namespace at a time. If two
    # different registered namespaces would need the same prefix (e.g. two
    # entries in `prefixes` disagreeing on what "schema" expands to), the
    # first one wins -- prefixes is already ordered longest-namespace-first --
    # and the other is left as a full URI. Both output formats resolve the
    # same way so a given export is internally consistent.
    bound: dict[str, str] = {}
    for namespace, prefix in prefixes.items():
        bound.setdefault(prefix, namespace)

    graph = Graph()
    graph.parse(data=turtle_text, format="turtle")
    for prefix, namespace in bound.items():
        # rdflib's Graph() ships with dozens of built-in namespace bindings
        # of its own (schema, foaf, dcterms, prov, ...), sometimes under a
        # different URI variant than ours (e.g. it defaults "schema" to
        # "https://schema.org/"). replace=True forces our choice to win
        # regardless of what rdflib already had bound to that prefix name.
        graph.bind(prefix, Namespace(namespace), override=True, replace=True)

    if format == ExportFormat.json_ld:
        return graph.serialize(format="json-ld", context=bound, indent=2)
    return graph.serialize(format="turtle")


def export_graph(graph_iri: str, format: ExportFormat, prefixes: dict[str, str]) -> str:
    """Return all triples in a named graph, serialized in the given format
    with URIs abbreviated per `prefixes`."""
    ttl = sparql_construct(
        f"CONSTRUCT {{ ?s ?p ?o }} WHERE {{ GRAPH <{graph_iri}> {{ ?s ?p ?o }} }}"
    )
    return serialize_export(ttl, format, prefixes)


def drop_workspace_graphs(workspace_id: str) -> None:
    """Remove all graphs for a workspace. Called when a workspace is deleted."""
    sparql_update(f"""
        DROP SILENT GRAPH <{curation_graph(workspace_id)}> ;
        DROP SILENT GRAPH <{data_graph(workspace_id)}>
    """)
