from enum import Enum

import httpx

from app.core.config import settings


class ExportFormat(str, Enum):
    turtle = "turtle"
    json_ld = "json-ld"


EXPORT_FORMAT_MEDIA_TYPES: dict[ExportFormat, tuple[str, str]] = {
    ExportFormat.turtle: ("text/turtle", "ttl"),
    ExportFormat.json_ld: ("application/ld+json", "jsonld"),
}


def sparql_select(query: str) -> dict:
    """Execute a SPARQL SELECT/ASK/CONSTRUCT query and return parsed JSON results."""
    response = httpx.post(
        f"{settings.oxigraph_url}/query",
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


def sparql_construct_ttl(query: str, format: ExportFormat = ExportFormat.turtle) -> str:
    """Execute a SPARQL CONSTRUCT query and return the result serialized in the given format."""
    media_type, _ = EXPORT_FORMAT_MEDIA_TYPES[format]
    response = httpx.post(
        f"{settings.oxigraph_url}/query",
        content=query.encode(),
        headers={
            "Content-Type": "application/sparql-query",
            "Accept": media_type,
        },
        timeout=30.0,
    )
    response.raise_for_status()
    return response.text


def export_graph_ttl(graph_iri: str, format: ExportFormat = ExportFormat.turtle) -> str:
    """Return all triples in a named graph, serialized in the given format."""
    return sparql_construct_ttl(
        f"CONSTRUCT {{ ?s ?p ?o }} WHERE {{ GRAPH <{graph_iri}> {{ ?s ?p ?o }} }}",
        format,
    )


def drop_workspace_graphs(workspace_id: str) -> None:
    """Remove all graphs for a workspace. Called when a workspace is deleted."""
    sparql_update(f"""
        DROP SILENT GRAPH <{curation_graph(workspace_id)}> ;
        DROP SILENT GRAPH <{data_graph(workspace_id)}>
    """)
