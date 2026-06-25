from fastapi import APIRouter

from app.schemas.statement import EntityNeighborhoodResponse, StatementResponse

router = APIRouter(prefix="/graph", tags=["graph"])


@router.get("/{workspace_id}/deduplication", response_model=list[StatementResponse])
async def get_deduplication():
    """
    Gets all of the owl:sameAs statements that span across documents.
    """
    return []


@router.get(
    "/{workspace_id}/neighborhood/{entity_id}",
    response_model=EntityNeighborhoodResponse,
)
async def get_neighborhood():
    """
    Gets the local neighborhood of a statement.
    """
    return EntityNeighborhoodResponse(incoming=[], outgoing=[])
