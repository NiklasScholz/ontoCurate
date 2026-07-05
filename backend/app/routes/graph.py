from uuid import UUID

from fastapi import APIRouter

from app.routes.documents import order_statements
from app.schemas.statement import EntityNeighborhoodResponse, StatementResponse
from app.store.client import curation_graph, sparql_select
from app.store.utils import (
    PACO_ALIGNMENT_ACTIVITY,
    PACO_CANDIDATE,
    PACO_CURRENT,
    PROV_GENERATED_BY,
    RDF_TYPE,
)

router = APIRouter(prefix="/graph", tags=["graph"])


@router.get("/{workspace_id}/deduplication", response_model=list[StatementResponse])
async def get_deduplication(workspace_id: UUID):
    """
    Gets all of the owl:sameAs statements that span across documents.
    """

    graph = curation_graph(str(workspace_id))

    payload = sparql_select(f"""
        SELECT ?s ?p ?o WHERE {{
            GRAPH <{graph}> {{
                ?s ?p ?o .
                ?s <{RDF_TYPE}> <{PACO_CANDIDATE}> .
                ?s <{PACO_CURRENT}> true .
                ?s <{PROV_GENERATED_BY}> ?e .
                ?e <{RDF_TYPE}> <{PACO_ALIGNMENT_ACTIVITY}> .
            }}
        }}
        ORDER BY ?s ?p ?o
    """)

    rows = [
        (b["s"]["value"], b["p"]["value"], b["o"]["value"])
        for b in payload.get("results", {}).get("bindings", [])
    ]

    return order_statements(rows)


@router.get(
    "/{workspace_id}/neighborhood/{entity_id}",
    response_model=EntityNeighborhoodResponse,
)
async def get_neighborhood():
    """
    Gets the local neighborhood of a statement.
    """
    return EntityNeighborhoodResponse(incoming=[], outgoing=[])
