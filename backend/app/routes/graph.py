import re
from uuid import UUID

from fastapi import APIRouter, Depends

from app.deps import get_current_user, require_role
from app.routes.documents import order_statements, zip_current_originals
from app.schemas.statement import (
    CurrentAndOriginalStatement,
    EntityNeighborhoodResponse,
    IncomingEdge,
    OutgoingEdge,
)
from app.store.client import curation_graph, sparql_select
from app.store.utils import (
    PACO_ALIGNMENT_ACTIVITY,
    PACO_CANDIDATE,
    PACO_CURRENT,
    PACO_LOOKUP_ACTIVITY,
    PACO_OBJECT,
    PACO_PREDICATE,
    PACO_SUBJECT,
    PROV_DERIVED_FROM,
    PROV_GENERATED_BY,
    RDF_TYPE,
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

    payload = sparql_select(f"""
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
    """)

    rows = [
        (b["s"]["value"], b["p"]["value"], b["o"]["value"], b["os"]["value"])
        for b in payload.get("results", {}).get("bindings", [])
    ]

    originals_payload = sparql_select(f"""
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
    """)

    originals_rows = [
        (b["s"]["value"], b["p"]["value"], b["o"]["value"], b["s"]["value"])
        for b in originals_payload.get("results", {}).get("bindings", [])
    ]

    statements = zip_current_originals(
        order_statements(rows), order_statements(originals_rows)
    )
    statements.sort(key=lambda s: s.current.subject)
    return statements


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

    incoming_payload = sparql_select(f"""
        SELECT ?s ?p WHERE {{
            GRAPH <{graph}> {{
                ?r <{PACO_SUBJECT}> ?s .
                ?r <{PACO_PREDICATE}> ?p .
                ?r <{PACO_OBJECT}> <{entity_id}> .
                ?r <{RDF_TYPE}> <{PACO_CANDIDATE}> .
                ?r <{PACO_CURRENT}> true .
            }}
        }}
        ORDER BY ?p ?s
    """)

    outgoing_payload = sparql_select(f"""
        SELECT ?p ?o WHERE {{
            GRAPH <{graph}> {{
                ?r <{PACO_SUBJECT}> <{entity_id}> .
                ?r <{PACO_PREDICATE}> ?p .
                ?r <{PACO_OBJECT}> ?o .
                ?r <{RDF_TYPE}> <{PACO_CANDIDATE}> .
                ?r <{PACO_CURRENT}> true .
            }}
        }}
        ORDER BY ?p ?o
    """)

    return EntityNeighborhoodResponse(
        incoming=[
            IncomingEdge(predicate=b["p"]["value"], subject=b["s"]["value"])
            for b in incoming_payload.get("results", {}).get("bindings", [])
        ],
        outgoing=[
            OutgoingEdge(predicate=b["p"]["value"], object=b["o"]["value"])
            for b in outgoing_payload.get("results", {}).get("bindings", [])
        ],
    )
