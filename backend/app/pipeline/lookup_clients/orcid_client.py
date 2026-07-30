import logging
import time

import httpx

from app.pipeline.lookup_clients.lookup_utils import (
    has_sufficient_data,
    resolve_rule_value_sets,
)

logger = logging.getLogger(__name__)

ORCID_SEARCH_API = "https://pub.orcid.org/v3.0/expanded-search/"
ORCID_RECORD_API = "https://pub.orcid.org/v3.0"


def create_orcid_client() -> httpx.Client:
    """Create an HTTP client for the ORCID public API."""
    return httpx.Client(
        headers={"Accept": "application/json"},
        timeout=httpx.Timeout(10.0),
        follow_redirects=True,
    )


def search_orcid(query: str, limit: int = 5) -> list[dict]:
    """
    Search the ORCID public API for researcher records matching the query.

    Args:
        query: ORCID query string (e.g. 'given-names:"Alice" AND
            family-name:"Smith"')
        limit: Maximum number of results to return

    Returns:
        List of ORCID candidate dicts with keys:
        - uri: Full ORCID URI (e.g. https://orcid.org/0000-0001-2345-6789)
        - orcid_id: Bare ORCID iD
        - given_names, family_names, credit_name: str
        - other_names: list[str]
        - institution_names: list[str] (affiliations, if available)
    """
    if not query or not query.strip():
        return []

    params = {"q": query.strip(), "start": 0, "rows": limit}

    try:
        with create_orcid_client() as client:
            response = client.get(ORCID_SEARCH_API, params=params)
            response.raise_for_status()
            data = response.json()
    except httpx.HTTPStatusError as exc:
        logger.error(
            "ORCID returned HTTP %s for query %r: %s",
            exc.response.status_code,
            query,
            exc.response.text[:500],
        )
        return []
    except httpx.RequestError as exc:
        logger.error("Network error while searching ORCID for %r: %s", query, exc)
        return []

    results = []
    for item in data.get("expanded-result") or []:
        orcid_id = item.get("orcid-id")
        if not orcid_id:
            continue
        results.append(
            {
                "uri": f"https://orcid.org/{orcid_id}",
                "orcid_id": orcid_id,
                "given_names": item.get("given-names", "") or "",
                "family_names": item.get("family-names", "") or "",
                "credit_name": item.get("credit-name", "") or "",
                "other_names": [n for n in item.get("other-name") or [] if n],
                "institution_names": [
                    n for n in item.get("institution-name") or [] if n
                ],
            }
        )
    return results


def fetch_orcid_record(orcid_id: str) -> dict | None:
    """
    Fetch a single ORCID person record by ID. Used to verify that extracted ORCID actually exists.
    """
    if not orcid_id or not orcid_id.strip():
        return None

    url = f"{ORCID_RECORD_API}/{orcid_id.strip()}/person"
    try:
        with create_orcid_client() as client:
            response = client.get(url)
            response.raise_for_status()
            data = response.json()
    except httpx.HTTPStatusError as exc:
        if exc.response.status_code == 404:
            logger.info("ORCID ID %s does not resolve to a record", orcid_id)
        else:
            logger.error(
                "ORCID returned HTTP %s for ID %r: %s",
                exc.response.status_code,
                orcid_id,
                exc.response.text[:500],
            )
        return None
    except httpx.RequestError as exc:
        logger.error("Network error while fetching ORCID ID %r: %s", orcid_id, exc)
        return None

    name = data.get("name") or {}
    other_names = (data.get("other-names") or {}).get("other-name") or []
    return {
        "orcid_id": orcid_id.strip(),
        "given_names": (name.get("given-names") or {}).get("value", "") or "",
        "family_names": (name.get("family-name") or {}).get("value", "") or "",
        "credit_name": (name.get("credit-name") or {}).get("value", "") or "",
        "other_names": [n.get("content", "") for n in other_names if n.get("content")],
    }


def _build_candidate_literals(result: dict) -> dict[str, list[str]]:
    """Build the literals used to compare an ORCID candidate."""
    given_name = result.get("given_names", "")
    family_name = result.get("family_names", "")
    credit_name = result.get("credit_name", "")

    names = [n for n in [credit_name, f"{given_name} {family_name}".strip()] if n]
    names.extend(result.get("other_names", []))
    literals = {
        "name": list(dict.fromkeys(names)),
        "orcid": [result["orcid_id"]],
    }

    if given_name:
        literals["givenName"] = [given_name]
    if family_name:
        literals["familyName"] = [family_name]

    institution_names = result.get("institution_names", [])
    if institution_names:
        literals["affiliation"] = institution_names

    return literals


def _result_to_candidate(result: dict) -> dict:
    """Turn a raw ORCID result (search hit or fetched record) into a candidate dict."""
    return {
        "uri": f"https://orcid.org/{result['orcid_id']}",
        "orcid_id": result["orcid_id"],
        "label": result.get("credit_name")
        or f"{result.get('given_names', '')} {result.get('family_names', '')}".strip(),
        "description": "",
        "literals": _build_candidate_literals(result),
        "source": "orcid",
        "relations_out": {},
        "relations_in": {},
    }


def _search_orcid_candidates(
    entity: dict,
    limit: int,
    request_delay_seconds: float,
    type_config: dict | None,
    field_names: dict[str, str],
) -> list[dict]:
    """ORCID API search based on entity data without known id"""
    type_config = type_config or {}
    literals = entity.get("literals", {})

    candidates = []
    seen_uris = set()
    seen_queries = set()

    for rule in type_config.get("search_queries", []):
        for value_set in resolve_rule_value_sets(literals, rule):
            query = " AND ".join(
                f'{field_names.get(predicate, predicate)}:"{value}"'
                for predicate, value in value_set.items()
            ).strip()

            if not query or query in seen_queries:
                continue

            seen_queries.add(query)

            for result in search_orcid(query, limit=limit):
                candidate = _result_to_candidate(result)
                if candidate["uri"] in seen_uris:
                    continue
                seen_uris.add(candidate["uri"])
                candidates.append(candidate)

            if request_delay_seconds > 0:
                time.sleep(request_delay_seconds)

    return candidates[:limit]


def generate_orcid_candidates(
    entity: dict,
    limit: int = 5,
    request_delay_seconds: float = 0.1,
    type_config: dict | None = None,
    field_names: dict[str, str] | None = None,
) -> list[dict]:
    """
    Generate ORCID candidates for a local entity. If entity carries ORCID from source text, verifies that id resolves to real record.
    If not, flags candidate, so confidence score can be reduced.
    Otherwise, it falls backs to orcid api search.
    """
    known_orcid_ids = entity.get("literals", {}).get("orcid", [])
    field_names = field_names or {}

    if known_orcid_ids:
        candidates = []
        for orcid_id in known_orcid_ids[:limit]:
            record = fetch_orcid_record(orcid_id)
            if record is not None:
                candidates.append(_result_to_candidate(record))
            if request_delay_seconds > 0:
                time.sleep(request_delay_seconds)
        if candidates:
            return candidates

        fallback_candidates = _search_orcid_candidates(
            entity, limit, request_delay_seconds, type_config, field_names
        )
        for candidate in fallback_candidates:
            candidate["orcid_unresolved"] = True
        return fallback_candidates

    return _search_orcid_candidates(
        entity, limit, request_delay_seconds, type_config, field_names
    )


def query_orcid_for_entities(
    entities: list[dict],
    limit: int = 5,
    request_delay_seconds: float = 0.1,
    entity_type_configs: dict | None = None,
    field_names: dict[str, str] | None = None,
) -> dict[str, list[dict]]:
    """
    Return ORCID candidates grouped by local entity URI.
    Known ORCIDs are verified through ORCID record API, while others are searched through search API.
    Candidates require at least one of the literals specified in `require_any_of` declared in the lookup config.
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
                "Skipping ORCID lookup for unconfigured entity type %s",
                entity_type,
            )
            continue
        if not literals.get("orcid") and not has_sufficient_data(literals, type_config):
            logger.debug(
                "Skipping ORCID lookup for %s: none of %s available to disambiguate",
                uri,
                type_config.get("require_any_of"),
            )
            continue
        candidates = generate_orcid_candidates(
            entity,
            limit=limit,
            request_delay_seconds=request_delay_seconds,
            type_config=type_config,
            field_names=field_names,
        )
        if candidates:
            results[uri] = candidates

    logger.info(
        "Generated ORCID candidates for %d of %d local entities",
        len(results),
        len(entities),
    )

    return results
