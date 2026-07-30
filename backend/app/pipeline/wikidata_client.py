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

    return details.get("labels", {}).get(language, {}).get("value", "").strip()


def _build_queries_from_rule(
    literals: dict[str, list[str]],
    rule: dict,
) -> list[str]:
    """Build Wikidata search queries from one configured rule."""
    predicates = rule.get("predicates", [])

    if not predicates:
        return []

    require_all = rule.get("require_all", False)
    join_with = rule.get("join_with", " ")
    max_queries = rule.get("max_queries", 1)

    value_lists = [
        [
            value.strip()
            for value in literals.get(predicate, [])
            if value and value.strip()
        ]
        for predicate in predicates
    ]

    if require_all and any(not values for values in value_lists):
        fallback_predicates = rule.get("fallback_predicates", [])

        if not fallback_predicates:
            return []

        fallback_rule = {
            "predicates": fallback_predicates,
            "require_all": True,
            "join_with": join_with,
            "max_queries": max_queries,
        }

        return _build_queries_from_rule(
            literals,
            fallback_rule,
        )

    # One predicate: each literal value becomes its own query.
    if len(predicates) == 1:
        return value_lists[0][:max_queries]

    # Multiple predicates: combine the first value of each predicate.
    parts = [values[0] for values in value_lists if values]

    if not parts:
        return []

    return [join_with.join(parts)]


def _build_search_queries(
    entity: dict,
    type_config: dict | None = None,
) -> list[str]:
    """Build unique Wikidata search queries for a local entity."""
    literals = entity.get("literals", {})
    type_config = type_config or {}
    configured_rules = type_config.get("search_queries", [])

    queries: list[str] = []

    for rule in configured_rules:
        queries.extend(
            _build_queries_from_rule(
                literals,
                rule,
            )
        )

    unique_queries = list(
        dict.fromkeys(query.strip() for query in queries if query and query.strip())
    )

    logger.debug(
        "Built configured Wikidata search queries: %s",
        unique_queries,
    )

    return unique_queries


def _extract_candidate_values(
    source_config: dict,
    result: dict,
    details: dict,
    language: str,
) -> list[str]:
    """Extract candidate literal values from one configured Wikidata source."""
    source = source_config.get("source")

    if source == "label":
        values = [result.get("label", "")]

    elif source == "aliases":
        aliases = details.get("aliases", {}).get(language, [])

        values = [
            alias.get("value", "") for alias in aliases if isinstance(alias, dict)
        ]

    elif source == "string_claims":
        property_id = source_config.get("property")

        if not property_id:
            raise ValueError("Candidate source 'string_claims' requires a property")

        values = claim_string_values(
            details,
            property_id,
        )

    elif source == "item_claim_labels":
        property_id = source_config.get("property")

        if not property_id:
            raise ValueError("Candidate source 'item_claim_labels' requires a property")

        entity_ids = claim_entity_ids(
            details,
            property_id,
        )

        values = [fetch_label(entity_id, language) for entity_id in entity_ids]

    else:
        raise ValueError(f"Unknown candidate literal source: {source!r}")

    return list(
        dict.fromkeys(
            value.strip()
            for value in values
            if isinstance(value, str) and value.strip()
        )
    )


def _build_candidate_literals(
    result: dict,
    details: dict,
    type_config: dict,
    language: str,
) -> dict[str, list[str]]:
    """Build candidate literals according to the entity-type configuration."""
    literals: dict[str, list[str]] = {}

    candidate_literal_config = type_config.get(
        "candidate_literals",
        {},
    )

    for local_predicate, source_configs in candidate_literal_config.items():
        values: list[str] = []

        for source_config in source_configs:
            values.extend(
                _extract_candidate_values(
                    source_config,
                    result,
                    details,
                    language,
                )
            )

        unique_values = list(dict.fromkeys(values))

        if unique_values:
            literals[local_predicate] = unique_values

    return literals


def generate_wikidata_candidates(
    entity: dict,
    limit: int = 5,
    language: str = "en",
    request_delay_seconds: float = 0.1,
    type_config: dict | None = None,
) -> list[dict]:
    """Generate Wikidata candidates for a local entity."""
    type_config = type_config or {}

    entity_types = entity.get("types", [])
    entity_type = entity_types[0] if entity_types else None

    candidates: list[dict] = []
    seen_uris: set[str] = set()

    search_queries = _build_search_queries(
        entity,
        type_config=type_config,
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

            candidate_literals = _build_candidate_literals(
                result,
                details,
                type_config,
                language=language,
            )

            candidate = {
                "uri": candidate_uri,
                "wikidata_id": result["wikidata_id"],
                "label": result["label"],
                "description": result["description"],
                "literals": candidate_literals,
                "source": "wikidata",
                "relations_out": {},
                "relations_in": {},
            }

            logger.debug(
                "Built Wikidata candidate literals for type %s and entity %s: %s",
                entity_type,
                result["wikidata_id"],
                candidate_literals,
            )

            candidates.append(candidate)

        if request_delay_seconds > 0:
            time.sleep(request_delay_seconds)

    return candidates[:limit]


def query_wikidata_for_entities(
    entities: list[dict],
    limit: int = 5,
    language: str = "en",
    request_delay_seconds: float = 0.1,
    entity_type_configs: dict | None = None,
) -> dict[str, list[dict]]:
    """Return Wikidata candidates grouped by local entity URI."""
    results = {}
    entity_type_configs = entity_type_configs or {}

    for entity in entities:
        uri = entity.get("uri")

        if not uri or not entity.get("literals"):
            continue

        entity_types = entity.get("types", [])
        entity_type = entity_types[0] if entity_types else None
        type_config = entity_type_configs.get(entity_type)

        if not type_config:
            logger.debug(
                "Skipping Wikidata lookup for unconfigured entity type %s",
                entity_type,
            )
            continue

        candidates = generate_wikidata_candidates(
            entity,
            limit=limit,
            language=language,
            request_delay_seconds=request_delay_seconds,
            type_config=type_config,
        )

        if candidates:
            results[uri] = candidates

    logger.info(
        "Generated Wikidata candidates for %d of %d local entities",
        len(results),
        len(entities),
    )

    return results
