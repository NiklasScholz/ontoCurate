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
from app.store.client import (
    EXPORT_FORMAT_MEDIA_TYPES,
    ExportFormat,
    curation_graph,
    sparql_select,
)
from app.store.queries import export_deduplicated_graph
from app.store.utils import (
    PACO_ALIGNMENT_ACTIVITY,
    PACO_CANDIDATE,
    PACO_CURRENT,
    PACO_LOOKUP_ACTIVITY,
    PACO_OBJECT,
    PACO_PENDING,
    PACO_PREDICATE,
    PACO_STATUS,
    PACO_SUBJECT,
    PROV_DERIVED_FROM,
    PROV_GENERATED_BY,
    RDF_TYPE,
    build_prefix_map,
)

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

    graph = curation_graph(str(workspace_id))

    payload = await asyncio.to_thread(
        sparql_select,
        f"""
        SELECT ?s ?p ?o ?os WHERE {{
            GRAPH <{graph}> {{
                ?s ?p ?o .
                ?s <{RDF_TYPE}> <{PACO_CANDIDATE}> .
                ?s <{PACO_CURRENT}> true .
                ?s <{PROV_DERIVED_FROM}>* ?os .
                ?os <{PROV_GENERATED_BY}> ?e .
                ?e <{RDF_TYPE}> ?activity .

                VALUES ?activity_type {{
                <{PACO_ALIGNMENT_ACTIVITY}>
                <{PACO_LOOKUP_ACTIVITY}>
            }}

            ?e <{RDF_TYPE}> ?activity_type .
            }}
        }}
        ORDER BY ?s ?p ?o
        """,
    )

    rows = [
        (b["s"]["value"], b["p"]["value"], b["o"]["value"], b["os"]["value"])
        for b in payload.get("results", {}).get("bindings", [])
    ]

    originals_payload = await asyncio.to_thread(
        sparql_select,
        f"""
        SELECT ?s ?p ?o WHERE {{
            GRAPH <{graph}> {{
                ?s ?p ?o .
                ?s <{RDF_TYPE}> <{PACO_CANDIDATE}> .
                ?s <{PROV_GENERATED_BY}> ?e .
                ?e <{RDF_TYPE}> ?activity .

                VALUES ?activity_type {{
                <{PACO_ALIGNMENT_ACTIVITY}>
                <{PACO_LOOKUP_ACTIVITY}>
            }}

            ?e <{RDF_TYPE}> ?activity_type .
            }}
        }}
        ORDER BY ?s ?p ?o
        """,
    )

    originals_rows = [
        (b["s"]["value"], b["p"]["value"], b["o"]["value"], b["s"]["value"])
        for b in originals_payload.get("results", {}).get("bindings", [])
    ]

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

    graph = curation_graph(str(workspace_id))

    def count_query(pending_only: bool) -> str:
        return f"""
        SELECT (COUNT(DISTINCT ?s) AS ?count) WHERE {{
            GRAPH <{graph}> {{
                ?s <{RDF_TYPE}> <{PACO_CANDIDATE}> .
                ?s <{PACO_CURRENT}> true .
                ?s <{PROV_DERIVED_FROM}>* ?os .
                ?os <{PROV_GENERATED_BY}> ?e .

                VALUES ?activity_type {{
                <{PACO_ALIGNMENT_ACTIVITY}>
                <{PACO_LOOKUP_ACTIVITY}>
            }}

            ?e <{RDF_TYPE}> ?activity_type .
            {f"?s <{PACO_STATUS}> <{PACO_PENDING}> ." if pending_only else ""}
            }}
        }}
        """

    def run_count(pending_only: bool) -> int:
        payload = sparql_select(count_query(pending_only))
        bindings = payload.get("results", {}).get("bindings", [])
        return int(bindings[0]["count"]["value"]) if bindings else 0

    total_count, pending_count = await asyncio.gather(
        asyncio.to_thread(run_count, False),
        asyncio.to_thread(run_count, True),
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
    return Response(
        content=content,
        media_type=media_type,
        headers={
            "Content-Disposition": f'attachment; filename="deduplicated.{extension}"'
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

    graph = curation_graph(str(workspace_id))

    # literal objects should not return any neighborhood, as they are no entities and are solely derived for the subject entity
    if not is_iri(entity_id):
        return EntityNeighborhoodResponse(incoming=[], outgoing=[])

    incoming_payload = await asyncio.to_thread(
        sparql_select,
        f"""
        SELECT ?s ?p ?status WHERE {{
            GRAPH <{graph}> {{
                ?r <{PACO_SUBJECT}> ?s .
                ?r <{PACO_PREDICATE}> ?p .
                ?r <{PACO_OBJECT}> <{entity_id}> .
                ?r <{RDF_TYPE}> <{PACO_CANDIDATE}> .
                ?r <{PACO_CURRENT}> true .
                ?r <{PACO_STATUS}> ?status .
            }}
        }}
        ORDER BY ?p ?s
        """,
    )

    outgoing_payload = await asyncio.to_thread(
        sparql_select,
        f"""
        SELECT ?p ?o ?status WHERE {{
            GRAPH <{graph}> {{
                ?r <{PACO_SUBJECT}> <{entity_id}> .
                ?r <{PACO_PREDICATE}> ?p .
                ?r <{PACO_OBJECT}> ?o .
                ?r <{RDF_TYPE}> <{PACO_CANDIDATE}> .
                ?r <{PACO_CURRENT}> true .
                ?r <{PACO_STATUS}> ?status .
            }}
        }}
        ORDER BY ?p ?o
        """,
    )

    return EntityNeighborhoodResponse(
        incoming=[
            IncomingEdge(
                predicate=b["p"]["value"],
                subject=b["s"]["value"],
                status=b["status"]["value"],
            )
            for b in incoming_payload.get("results", {}).get("bindings", [])
        ],
        outgoing=[
            OutgoingEdge(
                predicate=b["p"]["value"],
                object=b["o"]["value"],
                status=b["status"]["value"],
            )
            for b in outgoing_payload.get("results", {}).get("bindings", [])
        ],
    )
