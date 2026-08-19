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
    """
    Execute a SPARQL SELECT/ASK query and return parsed JSON results.
    If restrict_to_graph is given, the query is restricted to the provided named
    graph ensuring users cannot access unrestricted data.
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
    """
    Serialize CONSTRUCT-query Turtle output in the requested export
    format, abbreviating URIs to CURIEs wherever a namespace in `prefixes` is
    known. Necessary, as Oxigraph always emit full URIs, regardless of PREFIX
    declarations in the query), so this step has to happen after the fact, on our side.
    """
    bound = {}
    for namespace, prefix in prefixes.items():
        bound.setdefault(prefix, namespace)

    graph = Graph()
    graph.parse(data=turtle_text, format="turtle")
    for prefix, namespace in bound.items():
        graph.bind(prefix, Namespace(namespace), override=True, replace=True)

    if format == ExportFormat.json_ld:
        return graph.serialize(format="json-ld", context=bound, indent=2)
    return graph.serialize(format="turtle")


def export_graph(graph_iri: str, format: ExportFormat, prefixes: dict[str, str]) -> str:
    """
    Return all triples in a named graph, serialized in the given format
    with URIs abbreviated per `prefixes`.
    """
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
