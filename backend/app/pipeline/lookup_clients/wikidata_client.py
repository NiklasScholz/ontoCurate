import logging
import re
import time
from functools import lru_cache

import httpx

from app.core.config import settings
from app.pipeline.lookup_clients.lookup_utils import (
    has_sufficient_data,
    resolve_rule_value_sets,
)

logger = logging.getLogger(__name__)

# Wikidata API endpoints
WIKIDATA_SEARCH_API = "https://www.wikidata.org/w/api.php"
WIKIDATA_ENTITY_API = "https://www.wikidata.org/wiki/Special:EntityData"
WIKIDATA_SPARQL_ENDPOINT = "https://query.wikidata.org/sparql"


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
        list of Wikidata entity candidates as dicts with keys uri, label,
        description, wikidata_id
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


def search_wikidata_by_orcid(orcid_id: str, language: str = "en") -> dict | None:
    """
    Look up the Wikidata entity with given ORCID iD (P496) via a
    direct SPARQL query, rather than a fuzzy label search.
    Returns None if no entity claims that ORCID.
    """
    orcid_regex = re.compile(r"^\d{4}-\d{4}-\d{4}-\d{3}[\dX]$")
    if not orcid_id or not orcid_regex.match(orcid_id.strip()):
        return None
    orcid_id = orcid_id.strip()
    query = f"""
        SELECT ?item ?itemLabel ?itemDescription WHERE {{
          ?item wdt:P496 "{orcid_id}".
          SERVICE wikibase:label {{ bd:serviceParam wikibase:language "{language}". }}
        }}
        LIMIT 1
    """
    try:
        with create_wikimedia_client() as client:
            response = client.get(
                WIKIDATA_SPARQL_ENDPOINT,
                params={"query": query, "format": "json"},
                headers={"Accept": "application/sparql-results+json"},
            )
            response.raise_for_status()
            data = response.json()
    except httpx.HTTPStatusError as exc:
        logger.error(
            "Wikidata SPARQL returned HTTP %s for ORCID %r: %s",
            exc.response.status_code,
            orcid_id,
            exc.response.text[:500],
        )
        return None
    except httpx.RequestError as exc:
        logger.error(
            "Network error while querying Wikidata SPARQL for ORCID %r: %s",
            orcid_id,
            exc,
        )
        return None

    bindings = data.get("results", {}).get("bindings", [])
    if not bindings:
        return None
    binding = bindings[0]
    item_uri = binding.get("item", {}).get("value")
    if not item_uri:
        return None
    wikidata_id = item_uri.rstrip("/").split("/")[-1]
    return {
        "uri": f"https://www.wikidata.org/entity/{wikidata_id}",
        "label": binding.get("itemLabel", {}).get("value", ""),
        "description": binding.get("itemDescription", {}).get("value", ""),
        "wikidata_id": wikidata_id,
    }


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


def _extract_candidate_values(
    source_config: dict,
    result: dict,
    details: dict,
    language: str,
) -> list[str]:
    """
    Extract candidate literal values from configured Wikidata source.
    Defined in config as candidate_literals rule mapping wikidata source type and property to local predicate.
    """
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
        values = []
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


def _passes_class_filter(details: dict, type_config: dict) -> bool:
    """
    Ensure entity is an instance of at least one of the configured classes, if any are set.
    Prevents fuzzy matches of conferences with the same name as a book or movie, for example.
    """
    instance_of = type_config.get("instance_of")
    if not instance_of:
        return True
    candidate_classes = claim_entity_ids(details, "P31")
    return any(qid in instance_of for qid in candidate_classes)


def _result_to_wikidata_candidate(
    result: dict,
    type_config: dict,
    language: str,
) -> dict | None:
    """
    Turn a raw Wikidata result (search or ORCID lookup) into
    a candidate dict, or None if it fails the configured class filter.
    """
    details = fetch_wikidata_entity_details(result["wikidata_id"])
    if not _passes_class_filter(details, type_config):
        logger.debug(
            "Rejecting Wikidata candidate %s: not an instance of %s",
            result["wikidata_id"],
            type_config.get("instance_of"),
        )
        return None

    candidate_literals = _build_candidate_literals(
        result,
        details,
        type_config,
        language=language,
    )
    return {
        "uri": result["uri"],
        "wikidata_id": result["wikidata_id"],
        "label": result["label"],
        "description": result["description"],
        "literals": candidate_literals,
        "source": "wikidata",
        "relations_out": {},
        "relations_in": {},
    }


def _search_wikidata_candidates(
    entity: dict,
    limit: int,
    language: str,
    request_delay_seconds: float,
    type_config: dict,
) -> list[dict]:
    """Fuzzy label-based Wikidata search through wikidata search api"""
    entity_types = entity.get("types", [])
    entity_type = entity_types[0] if entity_types else None
    candidates = []
    seen_uris = set()
    seen_queries = set()
    literals = entity.get("literals", {})

    for rule in type_config.get("search_queries", []):
        join_with = rule.get("join_with", " ")
        # resolve rule set for querying, but do not include optional predicates that are not expected to be present in the label of wikidata
        for value_set in resolve_rule_value_sets(
            literals, rule, include_optional=False
        ):
            query = join_with.join(value_set.values()).strip()
            if not query or query in seen_queries:
                continue
            seen_queries.add(query)
            search_results = search_wikidata(query, limit=limit, language=language)

            for result in search_results:
                if result["uri"] in seen_uris:
                    continue
                seen_uris.add(result["uri"])
                candidate = _result_to_wikidata_candidate(result, type_config, language)
                if candidate is None:
                    continue
                candidate["fuzzy_match"] = True
                logger.debug(
                    "Built Wikidata candidate literals for type %s and entity %s: %s",
                    entity_type,
                    result["wikidata_id"],
                    candidate["literals"],
                )
                candidates.append(candidate)

            if request_delay_seconds > 0:
                time.sleep(request_delay_seconds)
    return candidates[:limit]


def generate_wikidata_candidates(
    entity: dict,
    limit: int = 5,
    language: str = "en",
    request_delay_seconds: float = 0.1,
    type_config: dict | None = None,
) -> list[dict]:
    """
    Generate Wikidata candidates for a local entity. If entity carries orcid verify against wikidata P496 claim.
    If this fails, falls back to fuzzy label search with class filtering in wikidata entity search API.
    """
    type_config = type_config or {}
    known_orcid_ids = entity.get("literals", {}).get("orcid", [])
    # If entity has found ORCID verify against wikidata through SPARQL query
    if known_orcid_ids:
        candidates = []
        for orcid_id in known_orcid_ids[:limit]:
            result = search_wikidata_by_orcid(orcid_id, language=language)
            if result is not None:
                candidate = _result_to_wikidata_candidate(result, type_config, language)
                if candidate is not None:
                    candidates.append(candidate)
            if request_delay_seconds > 0:
                time.sleep(request_delay_seconds)
        if candidates:
            return candidates

        fallback_candidates = _search_wikidata_candidates(
            entity, limit, language, request_delay_seconds, type_config
        )
        for candidate in fallback_candidates:
            candidate["orcid_unresolved"] = True
        return fallback_candidates

    return _search_wikidata_candidates(
        entity, limit, language, request_delay_seconds, type_config
    )


def query_wikidata_for_entities(
    entities: list[dict],
    limit: int = 5,
    language: str = "en",
    request_delay_seconds: float = 0.1,
    entity_type_configs: dict | None = None,
) -> dict[str, list[dict]]:
    """
    Return Wikidata candidates grouped by local entity URI.
    """
    results = {}
    entity_type_configs = entity_type_configs or {}
    for entity in entities:
        uri = entity.get("uri")
        literals = entity.get("literals", {})
        if not uri or not literals:
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
        if not literals.get("orcid") and not has_sufficient_data(literals, type_config):
            logger.debug(
                "Skipping Wikidata lookup for %s: none of %s available to disambiguate",
                uri,
                type_config.get("require_any_of"),
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
