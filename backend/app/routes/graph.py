import asyncio
import re
from uuid import UUID

from fastapi import APIRouter, Depends
from fastapi.responses import FileResponse, Response
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_session
from app.deps import get_current_user, require_role
from app.repositories.workspace import WorkspaceRepository
from app.routes.documents import (
    order_statements,
    sort_by_relation_count,
    zip_current_originals,
)
from app.schemas.statement import (
    CurrentAndOriginalStatement,
    DeduplicationCountResponse,
    EntityNeighborhoodResponse,
    IncomingEdge,
    OutgoingEdge,
)
from app.store.client import EXPORT_FORMAT_MEDIA_TYPES, ExportFormat
from app.store.queries import (
    export_deduplicated_graph,
    get_deduplication_counts,
    get_deduplication_statement_rows,
    get_entity_neighborhood,
)
from app.store.utils import build_prefix_map

router = APIRouter(
    prefix="/graph", tags=["graph"], dependencies=[Depends(get_current_user)]
)


@router.get(
    "/{workspace_id}/deduplication",
    response_model=list[CurrentAndOriginalStatement],
    dependencies=[Depends(require_role("owner", "editor"))],
)
async def get_deduplication(workspace_id: UUID):
    """
    Gets all of the owl:sameAs statements that span across documents.
    """

    rows, originals_rows = await asyncio.to_thread(
        get_deduplication_statement_rows, str(workspace_id)
    )

    statements = zip_current_originals(
        order_statements(rows), order_statements(originals_rows)
    )
    return sort_by_relation_count(statements)


@router.get(
    "/{workspace_id}/deduplication/count",
    response_model=DeduplicationCountResponse,
    dependencies=[Depends(require_role("owner", "editor"))],
)
async def get_deduplication_count(workspace_id: UUID):
    """
    Counts owl:sameAs statements (from alignment/lookup): total and pending review.
    """

    total_count, pending_count = await asyncio.to_thread(
        get_deduplication_counts, str(workspace_id)
    )
    return DeduplicationCountResponse(
        total_count=total_count, pending_count=pending_count
    )


@router.get(
    "/{workspace_id}/deduplication/export",
    dependencies=[Depends(require_role("owner", "editor"))],
    response_class=FileResponse,
)
async def export_deduplication_graph(
    workspace_id: UUID,
    format: ExportFormat = ExportFormat.turtle,
    session: AsyncSession = Depends(get_session),
):
    """
    Exports the data graph by merging entities, that were accepted as aligned, onto a single URI.
    """
    media_type, extension = EXPORT_FORMAT_MEDIA_TYPES[format]
    workspace = await WorkspaceRepository(session).get_by_id(workspace_id)
    prefixes = build_prefix_map(workspace.schema_path if workspace else None)
    content = await asyncio.to_thread(
        export_deduplicated_graph, str(workspace_id), format, prefixes
    )
    # clean up file name to avoid invalid characters replacing with underscores.
    filename = (
        re.sub(
            r'[\\/:"*?<>|\r\n]+',
            "_",
            (workspace.name if workspace else "workspace").strip(),
        )
        or "workspace"
    )
    return Response(
        content=content,
        media_type=media_type,
        headers={
            "Content-Disposition": (
                f'attachment; filename="{filename}_deduplicated.{extension}"'
            )
        },
    )


@router.get(
    "/{workspace_id}/neighborhood",
    response_model=EntityNeighborhoodResponse,
    dependencies=[Depends(require_role("owner", "editor"))],
)
async def get_neighborhood(workspace_id: UUID, entity_id: str):
    """
    Gets the local neighborhood of a given entity.
    """
    # invalid characters for iri/uri
    iriref_invalid = re.compile(r'[\x00-\x20<>"{}|^`\\]')

    def is_iri(value: str) -> bool:
        """Returns true if given value is a valid IRI/URI, false otherwise."""
        return bool(
            re.match(r"^[a-zA-Z][a-zA-Z0-9+.-]*://", value)
        ) and not iriref_invalid.search(value)

    # literal objects should not return any neighborhood, as they are no entities and are solely derived for the subject entity
    if not is_iri(entity_id):
        return EntityNeighborhoodResponse(incoming=[], outgoing=[])

    incoming, outgoing = await asyncio.to_thread(
        get_entity_neighborhood, str(workspace_id), entity_id
    )

    return EntityNeighborhoodResponse(
        incoming=[
            IncomingEdge(predicate=predicate, subject=other, status=status)
            for predicate, other, status in incoming
        ],
        outgoing=[
            OutgoingEdge(predicate=predicate, object=other, status=status)
            for predicate, other, status in outgoing
        ],
    )
