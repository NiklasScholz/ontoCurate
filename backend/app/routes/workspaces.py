from uuid import UUID

from fastapi import APIRouter, Depends
from fastapi.responses import FileResponse, Response
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_session
from app.repositories.workspace import WorkspaceRepository
from app.schemas.workspace import WorkspaceCreate, WorkspaceResponse
from app.store.client import curation_graph, export_graph_ttl

router = APIRouter(prefix="/workspaces", tags=["workspaces"])


@router.get("/", response_model=list[WorkspaceResponse])
async def list_workspaces(
    session: AsyncSession = Depends(get_session),
):
    return await WorkspaceRepository(session).get_all()


@router.post("/", response_model=WorkspaceResponse, status_code=201)
async def create_workspace(
    data: WorkspaceCreate,
    session: AsyncSession = Depends(get_session),
):
    return await WorkspaceRepository(session).create(
        data.name,
        data.schema_path,
        data.alignment_config_path,
        data.provenance_config_path,
    )


@router.get("/{workspace_id}", response_model=WorkspaceResponse)
async def get_workspace(
    workspace_id: UUID,
    session: AsyncSession = Depends(get_session),
):
    return await WorkspaceRepository(session).get_by_id(workspace_id)


@router.get("/{workspace_id}/export/provenance.ttl", response_class=FileResponse)
async def export_provenance_graph(workspace_id: str):
    ttl = export_graph_ttl(curation_graph(workspace_id))
    return Response(
        content=ttl,
        media_type="text/turtle",
        headers={"Content-Disposition": f'attachment; filename="provenance.ttl"'},
    )


@router.delete("/{workspace_id}", status_code=204)
async def delete_workspace(
    workspace_id: UUID,
    session: AsyncSession = Depends(get_session),
):
    await WorkspaceRepository(session).delete(workspace_id)
