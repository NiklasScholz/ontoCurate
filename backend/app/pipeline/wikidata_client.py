"""Wikidata entity lookup and query module."""

import logging
import time
from functools import lru_cache

import httpx

from app.core.config import settings

logger = logging.getLogger(__name__)

# Wikidata API endpoints
WIKIDATA_SEARCH_API = "https://www.wikidata.org/w/api.php"
WIKIDATA_ENTITY_API = "https://www.wikidata.org/wiki/Special:EntityData"


def create_wikimedia_client() -> httpx.Client:
    """Create an HTTP client compliant with Wikimedia's User-Agent policy."""
    if not settings.wikimedia_user_agent:
        raise RuntimeError(
            "WIKIMEDIA_USER_AGENT must be configured with an application name, "
            "version, and contact information."
        )
    return httpx.Client(
        headers={
            "User-Agent": settings.wikimedia_user_agent,
            "Accept": "application/json",
        },
        timeout=httpx.Timeout(10.0),
        follow_redirects=True,
    )


def search_wikidata(
    query: str,
    limit: int = 5,
    language: str = "en",
) -> list[dict]:
    """
    Search Wikidata for entities matching the query string.

    Args:
        query: Search query string (e.g., name of person, organization)
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
        "language": language,
        "uselang": language,
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

            api_error = data.get("error")

            if api_error:
                logger.error(
                    "Wikidata API error for query %r: "
                    "code=%r info=%r retry_after=%r api_error_header=%r",
                    query,
                    api_error.get("code"),
                    api_error.get("info"),
                    response.headers.get("Retry-After"),
                    response.headers.get("MediaWiki-API-Error"),
                )
                return []

            search_items = data.get("search", [])

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

    for item in search_items:
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


def claim_entity_ids(details: dict, property_id: str) -> list[str]:
    """Extract Wikidata entity IDs from item-valued claims."""
    ids = []

    claims = details.get("properties", {}).get(property_id, [])

    for claim in claims:
        value = claim.get("mainsnak", {}).get("datavalue", {}).get("value")

        if isinstance(value, dict):
            qid = value.get("id")
            if qid:
                ids.append(qid)

    return ids


def claim_string_values(details: dict, property_id: str) -> list[str]:
    """Extract string values from Wikidata claims."""
    values = []

    claims = details.get("properties", {}).get(property_id, [])

    for claim in claims:
        value = claim.get("mainsnak", {}).get("datavalue", {}).get("value")

        if isinstance(value, str) and value.strip():
            values.append(value.strip())

    return values


@lru_cache(maxsize=512)
def fetch_label(
    wikidata_id: str,
    language: str = "en",
) -> str:
    """Fetch and cache a label of a Wikidata item."""
    details = fetch_wikidata_entity_details(wikidata_id)

    return (
        details.get("labels", {})
        .get(language, {})
        .get("value", "")
        .strip()
    )


def _build_search_queries(
    entity: dict,
    entity_type: str | None,
) -> list[str]:
    """Build unique Wikidata search queries for a local entity."""
    literals = entity.get("literals", {})
    queries: list[str] = []

    if entity_type == "Person":
        given_names = literals.get("givenName", [])
        family_names = literals.get("familyName", [])
        names = literals.get("name", [])

        if given_names and family_names:
            queries.append(f"{given_names[0]} {family_names[0]}")
        elif family_names:
            queries.append(family_names[0])

        queries.extend(names[:2])
    else:
        names = literals.get("name") or literals.get("title", [])
        queries.extend(names[:2])

    return list(
        dict.fromkeys(query.strip() for query in queries if query and query.strip())
    )


def _build_candidate_literals(
    result: dict,
    details: dict,
    entity_type: str | None,
    language: str = "en",
) -> dict[str, list[str]]:
    """Build the literals used to compare a Wikidata candidate."""
    label = result.get("label", "")

    literals: dict[str, list[str]] = {
        "name": [label],
    }

    if entity_type == "AcademicArticle":
        literals["title"] = [label]

    if entity_type == "Person":
        given_name_ids = claim_entity_ids(details, "P735")
        family_name_ids = claim_entity_ids(details, "P734")

        given_names = [
            fetch_label(qid, language)
            for qid in given_name_ids
        ]

        family_names = [
            fetch_label(qid, language)
            for qid in family_name_ids
        ]

        given_names = [value for value in given_names if value]
        family_names = [value for value in family_names if value]

        if given_names:
            literals["givenName"] = given_names

        if family_names:
            literals["familyName"] = family_names

        orcids = claim_string_values(details, "P496")

        if orcids:
            literals["orcid"] = orcids

    aliases = details.get("aliases", {}).get(language, [])
    alias_values = [
        alias.get("value", "") for alias in aliases if alias.get("value", "").strip()
    ]

    literals["name"].extend(alias_values)

    if entity_type == "AcademicArticle":
        literals["title"].extend(alias_values)

    return literals


def generate_wikidata_candidates(
    entity: dict,
    limit: int = 5,
    language: str = "en",
) -> list[dict]:
    """Generate Wikidata candidates for a local entity."""
    entity_types = entity.get("types", [])
    entity_type = entity_types[0] if entity_types else None

    candidates: list[dict] = []
    seen_uris: set[str] = set()

    search_queries = _build_search_queries(
        entity,
        entity_type,
    )

    for query in search_queries:
        search_results = search_wikidata(
            query,
            limit=limit,
            language=language,
        )

        for result in search_results:
            candidate_uri = result["uri"]

            if candidate_uri in seen_uris:
                continue

            seen_uris.add(candidate_uri)

            details = fetch_wikidata_entity_details(result["wikidata_id"])

            candidate = {
                "uri": candidate_uri,
                "wikidata_id": result["wikidata_id"],
                "label": result["label"],
                "description": result["description"],
                "literals": _build_candidate_literals(
                    result,
                    details,
                    entity_type,
                    language=language,
                ),
                "types": entity_types,
                "source": "wikidata",
                "relations_out": {},
                "relations_in": {},
            }

            candidates.append(candidate)

        time.sleep(0.1)

    return candidates[:limit]


def query_wikidata_for_entities(
    entities: list[dict],
    limit: int = 5,
    language: str = "en",
) -> dict[str, list[dict]]:
    """Return Wikidata candidates grouped by local entity URI."""
    results = {}

    for entity in entities:
        uri = entity.get("uri")

        if not uri or not entity.get("literals"):
            continue

        candidates = generate_wikidata_candidates(
            entity,
            limit=limit,
            language=language,
        )

        if candidates:
            results[uri] = candidates

    logger.info(
        "Generated Wikidata candidates for %d of %d local entities",
        len(results),
        len(entities),
    )

    return results
