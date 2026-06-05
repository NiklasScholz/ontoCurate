import httpx

from app.core.config import settings


def sparql_select(query: str) -> dict:
    """Execute a SPARQL SELECT/ASK/CONSTRUCT query and return parsed JSON results."""
    response = httpx.post(
        f"{settings.oxigraph_url}/query",
        content=query.encode(),
        headers={
            "Content-Type": "application/sparql-query",
            "Accept": "application/sparql-results+json",
        },
    )
    response.raise_for_status()
    return response.json()


def sparql_update(query: str) -> None:
    """Execute a SPARQL UPDATE query (INSERT DATA, DELETE DATA, DROP, etc.)."""
    response = httpx.post(
        f"{settings.oxigraph_url}/update",
        content=query.encode(),
        headers={"Content-Type": "application/sparql-update"},
    )
    response.raise_for_status()


def curation_graph(workspace_id: str) -> str:
    """Named graph IRI for all CandidateStatements in a workspace."""
    return f"https://ontocurate.org/workspaces/{workspace_id}/graphs/provenance"


def data_graph(workspace_id: str) -> str:
    """Named graph IRI for accepted triples only."""
    return f"https://ontocurate.org/workspaces/{workspace_id}/graphs/data"


def drop_workspace_graphs(workspace_id: str) -> None:
    """Remove all graphs for a workspace. Called when a workspace is deleted."""
    sparql_update(f"""
        DROP SILENT GRAPH <{curation_graph(workspace_id)}> ;
        DROP SILENT GRAPH <{data_graph(workspace_id)}>
    """)
