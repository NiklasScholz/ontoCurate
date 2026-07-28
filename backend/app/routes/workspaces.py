import asyncio
from pathlib import Path
from typing import Literal
from uuid import UUID

import httpx
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse, Response
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_session
from app.core.exceptions import (
    BadRequestException,
    ConflictException,
    ForbiddenException,
    NotFoundException,
)
from app.deps import get_current_user, require_role
from app.models.user import User
from app.repositories.document import DocumentRepository
from app.repositories.run import RunRepository
from app.repositories.user import UserRepository
from app.repositories.workspace import WorkspaceMemberRepository, WorkspaceRepository
from app.schemas.query import QueryResultResponse
from app.schemas.user import UserResponse
from app.schemas.workspace import (
    AddMemberRequest,
    MemberResponse,
    WorkspaceCreate,
    WorkspaceQueryRequest,
    WorkspaceResponse,
)
from app.store.client import (
    EXPORT_FORMAT_MEDIA_TYPES,
    ExportFormat,
    curation_graph,
    data_graph,
    drop_workspace_graphs,
    export_graph,
    sparql_select,
)
from app.store.utils import (
    CURATION_ONLY_PREFIXES,
    build_prefix_map,
    extract_query_prefixes,
    format_sparql_response,
    shorten_sparql_results,
)
from app.store.writer import upsert_curator

router = APIRouter(
    prefix="/workspaces", tags=["workspaces"], dependencies=[Depends(get_current_user)]
)


def _schema_repo_path(schema_path: str) -> str:
    """Path to the workspace's LinkML schema file, relative to the repository root."""
    schema_name = Path(schema_path).parent.name
    return f"backend/config/{schema_name}/extraction_schema.yaml"


@router.get("/", response_model=list[WorkspaceResponse])
async def list_workspaces(
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    workspaces = await WorkspaceRepository(session).get_all_by_user(current_user.id)
    return [
        WorkspaceResponse(
            id=ws.id,
            name=ws.name,
            role=role,
            schema_repo_path=_schema_repo_path(ws.schema_path),
        )
        for ws, role in workspaces
    ]


@router.post("/", response_model=WorkspaceResponse, status_code=201)
async def create_workspace(
    data: WorkspaceCreate,
    session: AsyncSession = Depends(get_session),
    user: User = Depends(get_current_user),
):
    """Creates workspace with schema path assuming the schema path exists (and was selected through the schema endpoint). We expect schemas to follow the format: extraction_schema.yaml, alignment_config.yaml and provenance_config.yaml within the schema path folder."""
    base = Path(__file__).parent.parent.parent / "config" / data.schema_name
    schema_path = str(base / "extraction_schema.yaml")
    provenance_path = str(base / "provenance_config.yaml")
    alignment_config_path = str(base / "alignment_config.yaml")
    if (
        not Path(schema_path).exists()
        or not Path(provenance_path).exists()
        or not Path(alignment_config_path).exists()
    ):
        raise BadRequestException(f"Schema '{data.schema_name}' does not exist")

    workspace = await WorkspaceRepository(session).create(
        data.name,
        schema_path,
        alignment_config_path=alignment_config_path,
        provenance_config_path=provenance_path,
    )
    if not workspace:
        raise BadRequestException("Failed to create workspace")
    workspace_mem = await WorkspaceMemberRepository(session).add_member(
        workspace.id, user.id, "owner"
    )
    if not workspace_mem:
        raise BadRequestException("Failed to add user as workspace member")
    await asyncio.to_thread(
        upsert_curator, str(workspace.id), user.id, user.name, user.email, user.username
    )
    return WorkspaceResponse(
        id=workspace.id,
        name=workspace.name,
        role="owner",
        schema_repo_path=_schema_repo_path(workspace.schema_path),
    )


@router.get(
    "/{workspace_id}",
    response_model=WorkspaceResponse,
    dependencies=[Depends(require_role("owner", "editor"))],
)
async def get_workspace(
    workspace_id: UUID,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    workspace = await WorkspaceRepository(session).get_by_id(workspace_id)
    role = await WorkspaceMemberRepository(session).get_role(
        workspace_id, current_user.id
    )
    return WorkspaceResponse(
        id=workspace.id,
        name=workspace.name,
        role=role,
        schema_repo_path=_schema_repo_path(workspace.schema_path),
    )


@router.get(
    "/{workspace_id}/prefixes",
    dependencies=[Depends(require_role("owner", "editor"))],
)
async def get_workspace_prefixes(
    workspace_id: UUID,
    graph: Literal["data", "curation"] = "data",
    session: AsyncSession = Depends(get_session),
) -> dict[str, str]:
    """Returns the prefix map of the workspace (including fixed and schema-specific
    prefixes), scoped to the given graph. Used to fill in prefixes for query view."""
    workspace = await WorkspaceRepository(session).get_by_id(workspace_id)
    prefixes = build_prefix_map(workspace.schema_path if workspace else None)
    return {
        prefix: namespace
        for namespace, prefix in prefixes.items()
        # linkml is not useful in our use cases
        if prefix != "linkml"
        and (graph == "curation" or prefix not in CURATION_ONLY_PREFIXES)
    }


@router.get(
    "/{workspace_id}/export/provenance",
    dependencies=[Depends(require_role("owner"))],
    response_class=FileResponse,
)
async def export_provenance_graph(
    workspace_id: str,
    format: ExportFormat = ExportFormat.turtle,
    session: AsyncSession = Depends(get_session),
):
    media_type, extension = EXPORT_FORMAT_MEDIA_TYPES[format]
    workspace = await WorkspaceRepository(session).get_by_id(workspace_id)
    prefixes = build_prefix_map(workspace.schema_path if workspace else None)
    content = await asyncio.to_thread(
        export_graph, curation_graph(workspace_id), format, prefixes
    )
    return Response(
        content=content,
        media_type=media_type,
        headers={
            "Content-Disposition": f'attachment; filename="provenance.{extension}"'
        },
    )


@router.get(
    "/{workspace_id}/export/data",
    dependencies=[Depends(require_role("owner", "editor"))],
    response_class=FileResponse,
)
async def export_data_graph(
    workspace_id: str,
    format: ExportFormat = ExportFormat.turtle,
    session: AsyncSession = Depends(get_session),
):
    media_type, extension = EXPORT_FORMAT_MEDIA_TYPES[format]
    workspace = await WorkspaceRepository(session).get_by_id(workspace_id)
    prefixes = build_prefix_map(workspace.schema_path if workspace else None)
    content = await asyncio.to_thread(
        export_graph, data_graph(workspace_id), format, prefixes
    )
    return Response(
        content=content,
        media_type=media_type,
        headers={"Content-Disposition": f'attachment; filename="data.{extension}"'},
    )


@router.post(
    "/{workspace_id}/query",
    response_model=QueryResultResponse,
    dependencies=[Depends(require_role("owner", "editor"))],
)
async def query_workspace_graph(
    workspace_id: UUID,
    body: WorkspaceQueryRequest,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    """
    Runs a user-supplied SPARQL SELECT/ASK query against one of the workspace's
    graphs. Owners may query either the data or curation graph; editors are
    always restricted to the data graph regardless of what they request.

    The query's dataset is pinned to that single graph at the Oxigraph protocol
    level, so an explicit GRAPH clause in the submitted query cannot be used to
    read triples outside of it.
    """
    role = await WorkspaceMemberRepository(session).get_role(
        workspace_id, current_user.id
    )
    if role is None:
        raise ForbiddenException(f"You do not have access to workspace {workspace_id}")

    graph = body.graph if role == "owner" else "data"
    graph_iri = (
        curation_graph(str(workspace_id))
        if graph == "curation"
        else data_graph(str(workspace_id))
    )

    try:
        payload = await asyncio.to_thread(
            sparql_select, body.query, restrict_to_graph=graph_iri
        )
    except httpx.TimeoutException as exc:
        raise HTTPException(status_code=504, detail="Query timed out") from exc
    except httpx.HTTPStatusError as exc:
        raise HTTPException(status_code=422, detail=exc.response.text) from exc

    workspace = await WorkspaceRepository(session).get_by_id(workspace_id)
    prefixes = build_prefix_map(workspace.schema_path if workspace else None)
    prefixes = {**prefixes, **extract_query_prefixes(body.query)}
    prefixes = dict(sorted(prefixes.items(), key=lambda item: -len(item[0])))
    formatted = format_sparql_response(shorten_sparql_results(payload, prefixes))
    if isinstance(formatted, bool):
        return QueryResultResponse(boolean=formatted)
    return QueryResultResponse(**formatted)


@router.delete(
    "/{workspace_id}", status_code=204, dependencies=[Depends(require_role("owner"))]
)
async def delete_workspace(
    workspace_id: UUID,
    session: AsyncSession = Depends(get_session),
):
    await asyncio.to_thread(drop_workspace_graphs, str(workspace_id))
    await RunRepository(session).delete_all_for_workspace(workspace_id)
    await DocumentRepository(session).delete_all_for_workspace(workspace_id)
    await WorkspaceRepository(session).delete(workspace_id)


@router.get(
    "/{workspace_id}/members",
    response_model=list[MemberResponse],
    dependencies=[Depends(require_role("owner"))],
)
async def list_workspace_members(
    workspace_id: UUID,
    session: AsyncSession = Depends(get_session),
):
    members = await WorkspaceMemberRepository(session).list_members_with_users(
        workspace_id
    )
    return [
        MemberResponse(
            id=user.id,
            email=user.email,
            name=user.name,
            picture=user.picture,
            role=member.role,
        )
        for member, user in members
    ]


@router.post(
    "/{workspace_id}/members",
    response_model=UserResponse,
    status_code=201,
    dependencies=[Depends(require_role("owner"))],
)
async def add_workspace_member(
    workspace_id: UUID,
    body: AddMemberRequest,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    user_repo = UserRepository(session)
    user = await user_repo.get_by_email(
        body.user_info
    ) or await user_repo.get_by_username(body.user_info)
    if not user:
        raise BadRequestException(f"User '{body.user_info}' does not exist")

    workspace_repo = WorkspaceMemberRepository(session)
    if await workspace_repo.get_role(workspace_id, user.id) is not None:
        raise ConflictException(
            f"User '{body.user_info}' is already a member of this workspace"
        )

    await workspace_repo.add_member(workspace_id, user.id, body.role)
    await asyncio.to_thread(
        upsert_curator, str(workspace_id), user.id, user.name, user.email, user.username
    )
    return user


@router.delete(
    "/{workspace_id}/members/{user_id}",
    status_code=204,
    dependencies=[Depends(require_role("owner"))],
)
async def remove_workspace_member(
    workspace_id: UUID,
    user_id: UUID,
    session: AsyncSession = Depends(get_session),
):
    member_repo = WorkspaceMemberRepository(session)
    role = await member_repo.get_role(workspace_id, user_id)
    if role is None:
        raise NotFoundException("Member not found in workspace")

    if role == "owner":
        members = await member_repo.list_members(workspace_id)
        owner_count = sum(1 for m in members if m.role == "owner")
        if owner_count <= 1:
            raise BadRequestException("Cannot remove the last owner of a workspace")

    await member_repo.remove_member(workspace_id, user_id)
