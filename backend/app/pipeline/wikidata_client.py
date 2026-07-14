"""Wikidata entity lookup and query module."""

import logging
import os
import time
from typing import Optional

import httpx

logger = logging.getLogger(__name__)

# Mapping of our entity types to Wikidata entity classes (QIDs)
ENTITY_TYPE_TO_WIKIDATA_CLASS = {
    "Person": "Q5",  # human
    "Organization": "Q43229",  # organization
    "Conference": "Q2055880",  # conference
    "Workshop": "Q26106281",  # workshop
    "Journal": "Q5633421",  # academic journal
    "Proceedings": "Q1143604",  # academic publication
    "Series": "Q277759",  # book series
    "AcademicArticle": "Q13442814",  # scholarly article
}

# Wikidata API endpoints
WIKIDATA_SEARCH_API = "https://www.wikidata.org/w/api.php"
WIKIDATA_ENTITY_API = "https://www.wikidata.org/wiki/Special:EntityData"

WIKIMEDIA_USER_AGENT = os.getenv("WIKIMEDIA_USER_AGENT")

if not WIKIMEDIA_USER_AGENT:
    raise RuntimeError(
        "WIKIMEDIA_USER_AGENT must be configured with an application name, "
        "version, and contact information."
    )

if not WIKIMEDIA_USER_AGENT:
    raise RuntimeError(
        "WIKIMEDIA_USER_AGENT must be configured with an application name, "
        "version, and contact information."
    )


def create_wikimedia_client() -> httpx.Client:
    """Create an HTTP client compliant with Wikimedia's User-Agent policy."""
    return httpx.Client(
        headers={
            "User-Agent": WIKIMEDIA_USER_AGENT,
            "Accept": "application/json",
        },
        timeout=httpx.Timeout(10.0),
        follow_redirects=True,
    )


def search_wikidata(
    query: str,
    entity_type: Optional[str] = None,
    limit: int = 5,
) -> list[dict]:
    """
    Search Wikidata for entities matching the query string.

    Args:
        query: Search query string (e.g., name of person, organization)
        entity_type: Our entity type (e.g., "Person", "Organization") for type filtering
        limit: Maximum number of results to return

    Returns:
        List of Wikidata entity candidates as dicts with keys:
        - uri: Full Wikidata entity URI (e.g., http://www.wikidata.org/entity/Q123)
        - label: Entity label/name
        - description: Short description from Wikidata
        - wikidata_id: Wikidata QID (e.g., Q123)
    """
    if not query or not query.strip():
        return []

    params: dict[str, str | int] = {
        "action": "wbsearchentities",
        "search": query.strip(),
        "language": "en",
        "uselang": "en",
        "format": "json",
        "type": "item",
        "limit": limit,
        "maxlag": 5,
    }

    try:
        with create_wikimedia_client() as client:
            response = client.get(WIKIDATA_SEARCH_API, params=params)
            response.raise_for_status()
            data = response.json()

    except httpx.HTTPStatusError as exc:
        logger.error(
            "Wikidata returned HTTP %s for query %r: %s",
            exc.response.status_code,
            query,
            exc.response.text[:500],
        )
        return []

    except httpx.RequestError as exc:
        logger.error(
            "Network error while searching Wikidata for %r: %s",
            query,
            exc,
        )
        return []

    results = []

    for item in data.get("search", []):
        qid = item.get("id")
        if not qid:
            continue

        results.append(
            {
                "uri": f"https://www.wikidata.org/entity/{qid}",
                "label": item.get("label", ""),
                "description": item.get("description", ""),
                "wikidata_id": qid,
            }
        )

    return results


def fetch_wikidata_entity_details(wikidata_id: str) -> dict:
    """
    Fetch detailed properties of a Wikidata entity.

    Args:
        wikidata_id: Wikidata QID (e.g., "Q123")

    Returns:
        Dict with keys:
        - uri: Full entity URI
        - labels: Dict of language -> label
        - descriptions: Dict of language -> description
        - properties: Dict of property -> list of values/references
    """
    if not wikidata_id:
        return {}

    url = f"{WIKIDATA_ENTITY_API}/{wikidata_id}.json"

    try:
        with create_wikimedia_client() as client:
            response = client.get(url)
            response.raise_for_status()
            data = response.json()

    except httpx.HTTPStatusError as exc:
        logger.error(
            "Wikidata returned HTTP %s for entity %s: %s",
            exc.response.status_code,
            wikidata_id,
            exc.response.text[:500],
        )
        return {}

    except httpx.RequestError as exc:
        logger.error(
            "Network error while fetching Wikidata entity %s: %s",
            wikidata_id,
            exc,
        )
        return {}

    entity = data.get("entities", {}).get(wikidata_id, {})

    return {
        "uri": f"https://www.wikidata.org/entity/{wikidata_id}",
        "labels": entity.get("labels", {}),
        "descriptions": entity.get("descriptions", {}),
        "aliases": entity.get("aliases", {}),
        "properties": entity.get("claims", {}),
    }


def generate_wikidata_candidates(entity: dict, limit: int = 5) -> list[dict]:
    """
    Generate candidate Wikidata entities for alignment with a local entity.

    Args:
        entity: Local entity dict with keys:
            - types: list of entity types (e.g., ["Person"])
            - literals: dict of predicate -> list of string values
        limit: Max candidates per query

    Returns:
        List of Wikidata candidates formatted similarly to local entities:
        {
            "uri": "http://www.wikidata.org/entity/Q123",
            "wikidata_id": "Q123",
            "label": "...",
            "description": "...",
            "literals": {  # extracted from Wikidata properties
                "name": ["..."],
                "familyName": ["..."],
                ...
            }
        }
    """
    candidates = []

    # Use primary name/title for search
    entity_type = entity["types"][0] if entity.get("types") else None

    search_queries = []

    # Priority: familyName + givenName for Person, name for others
    if entity_type == "Person":
        family_names = entity.get("literals", {}).get("familyName", [])
        given_names = entity.get("literals", {}).get("givenName", [])
        names = entity.get("literals", {}).get("name", [])

        if family_names and given_names:
            search_queries.append(f"{given_names[0]} {family_names[0]}")
        elif family_names:
            search_queries.append(family_names[0])
        if names:
            search_queries.extend(names[:2])  # Try primary names too
    else:
        # For organizations, conferences, etc., use name/title
        names = entity.get("literals", {}).get("name", [])
        if not names:
            names = entity.get("literals", {}).get("title", [])
        search_queries.extend(names[:2])

    # Execute searches
    for query in search_queries:
        if not query or not query.strip():
            continue

        logger.info(f"Querying Wikidata: '{query}' (type: {entity_type})")

        wikidata_results = search_wikidata(query, entity_type=entity_type, limit=limit)

        for result in wikidata_results:
            # Avoid duplicates
            if any(c["uri"] == result["uri"] for c in candidates):
                continue

            # Fetch full details
            details = fetch_wikidata_entity_details(result["wikidata_id"])

            # Extract literals from Wikidata properties
            # For now, use label and description as basic literals
            candidate = {
                "uri": result["uri"],
                "wikidata_id": result["wikidata_id"],
                "label": result["label"],
                "description": result["description"],
                "literals": {
                    "name": [result["label"]],
                },
                "types": entity["types"],  # Use same types
                "source": "wikidata",
                "relations_out": {},
                "relations_in": {},
            }

            # Add aliases as alternative names
            if details.get("aliases"):
                aliases = details["aliases"].get("en", [])
                if aliases:
                    candidate["literals"]["name"].extend(
                        [a.get("value", "") for a in aliases]
                    )

            candidates.append(candidate)

        # Rate limiting: small delay between searches
        time.sleep(0.1)

    return candidates[:limit]


def query_wikidata_for_entities(
    entities: list[dict], limit: int = 5
) -> dict[str, list[dict]]:
    """
    Query Wikidata for candidates for each local entity.

    Args:
        entities: List of local entity dicts
        limit: Max candidates per entity

    Returns:
        Dict mapping entity URI -> list of Wikidata candidates
    """
    results = {}

    for entity in entities:
        uri = entity.get("uri")
        if not uri:
            continue

        # Skip if entity is too sparse (e.g., only has types, no name)
        if not entity.get("literals"):
            logger.debug(f"Skipping sparse entity {uri}")
            continue

        logger.info(f"Generating Wikidata candidates for {uri}")
        candidates = generate_wikidata_candidates(entity, limit=limit)

        if candidates:
            results[uri] = candidates
            logger.info(f"Found {len(candidates)} Wikidata candidate(s) for {uri}")
        else:
            logger.info(f"No Wikidata candidates found for {uri}")

    return results
