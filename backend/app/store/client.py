from pyoxigraph import NamedNode, Store

_store: Store | None = None


def get_store() -> Store:
    """
    Return the Oxigraph Store.
    """
    global _store
    if _store is None:
        import os

        from app.core.config import settings

        os.makedirs(settings.oxigraph_data_path, exist_ok=True)
        _store = Store(settings.oxigraph_data_path)
    return _store


def curation_graph(workspace_id: str) -> NamedNode:
    """Named provenance graph in a workspace"""
    return NamedNode(
        f"https://ontocurate.org/workspaces/{workspace_id}/graphs/provenance"
    )


def data_graph(workspace_id: str) -> NamedNode:
    """Named graph for accepted triples only"""
    return NamedNode(f"https://ontocurate.org/workspaces/{workspace_id}/graphs/data")


def drop_workspace_graphs(workspace_id: str) -> None:
    """Remove all graphs for a workspace"""
    store = get_store()
    store.remove_graph(curation_graph(workspace_id))
    store.remove_graph(data_graph(workspace_id))
