from fastapi import APIRouter, Depends
from fastapi.responses import Response
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_session
from app.repositories.workspace import WorkspaceRepository
from app.schemas.workspace import WorkspaceResponse
from app.store.client import curation_graph, export_graph_ttl

router = APIRouter(prefix="/workspaces", tags=["workspaces"])


@router.get("/", response_model=list[WorkspaceResponse])
async def list_workspaces(
    session: AsyncSession = Depends(get_session),
):
    return await WorkspaceRepository(session).get_all()


@router.post("/", response_model=WorkspaceResponse, status_code=201)
async def create_workspace():
    pass


@router.get("/{workspace_id}", response_model=WorkspaceResponse)
async def get_workspace():
    pass


@router.get("/{workspace_id}/export/provenance.ttl")
async def export_provenance_graph(workspace_id: str):
    ttl = export_graph_ttl(workspace_id, curation_graph(workspace_id))
    return Response(
        content=ttl,
        media_type="text/turtle",
        headers={"Content-Disposition": f'attachment; filename="provenance.ttl"'},
    )


@router.delete("/{workspace_id}", status_code=204)
async def delete_workspace():
    pass
