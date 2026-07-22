"""Helpers for integration tests"""

import json
import uuid
from pathlib import Path

from app.store.client import curation_graph, sparql_select
from app.store.writer import pred_local_name, write_candidate_statements_from_ttl


def gen_workspace_id(prefix: str = "test-ws") -> str:
    return f"{prefix}-{uuid.uuid4().hex[:8]}"


def unique_email(label: str) -> str:
    return f"{label}-{uuid.uuid4().hex[:8]}@rwth-aachen.de"


async def register_user(client, label: str) -> tuple[str, str, str]:
    """Registers a user and returns (user_id, email, access_token)"""
    email = unique_email(label)
    resp = await client.post(
        "/auth/register",
        json={"username": None, "email": email, "password": "password123"},
    )
    body = resp.json()
    return body["id"], email, resp.cookies["access_token"]


def as_user(client, token: str) -> None:
    client.cookies.set("access_token", token)


async def create_workspace(client, schema_name: str = "scholarySchema") -> str:
    resp = await client.post(
        "/workspaces/",
        json={"name": f"ws-{uuid.uuid4().hex[:8]}", "schema_name": schema_name},
    )
    return resp.json()["id"]


async def add_member(client, workspace_id: str, email: str, role: str) -> None:
    resp = await client.post(
        f"/workspaces/{workspace_id}/members",
        json={"user_info": email, "role": role},
    )
    assert resp.status_code == 201


def add_candidate_statements(
    tmp_path: Path,
    workspace_id: str,
    ttl_text: str,
    provenance: dict | None = None,
    document_id: str = "doc-1",
    run_id: str = "run-1",
) -> None:
    """Writes ttl_text (and optional provenance) to tmp_path and inserts the
    resulting candidate statements into the curation graph store for workspace_id."""
    ttl_file = tmp_path / f"{document_id}.ttl"
    ttl_file.write_text(ttl_text, encoding="utf-8")

    prov_file = None
    if provenance is not None:
        prov_file = tmp_path / f"{document_id}_provenance.json"
        prov_file.write_text(json.dumps(provenance), encoding="utf-8")

    write_candidate_statements_from_ttl(
        run_id, document_id, ttl_file, workspace_id, provenance_path=prov_file
    )


def find_candidate_id(
    workspace_id: str,
    predicate: str,
    subject: str | None = None,
    object_value: str | None = None,
) -> str:
    subject_triple = f"?s paco:subject <{subject}> .\n    " if subject else ""
    object_triple = f'?s paco:object "{object_value}" .\n    ' if object_value else ""
    sparql = f"""
        PREFIX paco: <https://example.org/provenance-and-curation-ontology/>
        SELECT ?s WHERE {{
        GRAPH <{curation_graph(workspace_id)}> {{
            ?s a paco:CandidateStatement ;
            paco:predicate <{predicate}> .
            {subject_triple}{object_triple}}}
        }}
    """
    result = sparql_select(sparql)
    bindings = result.get("results", {}).get("bindings", [])
    filters = f"predicate {predicate}"
    if subject:
        filters += f", subject {subject}"
    if object_value:
        filters += f", object {object_value}"
    assert bindings, f"No candidate statement found for {filters}"
    assert (
        len(bindings) == 1
    ), f"Expected exactly one candidate statement for {filters}, found {len(bindings)}"
    return bindings[0]["s"]["value"]


def sparql_count(query: str) -> int:
    bindings = sparql_select(query)["results"]["bindings"]
    return int(bindings[0]["count"]["value"])


def activity_count(workspace_id: str, activity_class: str) -> int:
    sparql = f"""
        PREFIX paco: <https://example.org/provenance-and-curation-ontology/>
        SELECT (COUNT(*) AS ?count) WHERE {{
            GRAPH <{curation_graph(workspace_id)}> {{
                ?a a paco:{activity_class} .
            }}
        }}
    """
    return sparql_count(sparql)


def add_statements(
    tmp_path: Path,
    workspace_id: str,
    triples: list[tuple[str, str, str]],
    document_id: str = "doc-1",
    run_id: str = "run-1",
    confidence: float = 0.9,
) -> dict[str, str]:
    """Add one candidate statement per (subject, predicate, object_value) triple
    and return {predicate: statement_id}. Attaches confidence annotation as well"""
    ttl_text = "\n".join(f'<{s}> <{p}> "{o}" .' for s, p, o in triples)
    provenance = {
        "annotations": [
            {
                "subject": s,
                "predicate": pred_local_name(p),
                "value": o,
                "span_start": 0,
                "span_end": len(o),
                "span_text": o,
                "confidence": confidence,
                "triple_type": "literal",
            }
            for s, p, o in triples
        ]
    }
    add_candidate_statements(
        tmp_path,
        workspace_id,
        ttl_text,
        provenance,
        document_id=document_id,
        run_id=run_id,
    )
    return {
        predicate: find_candidate_id(workspace_id, predicate)
        for _, predicate, _ in triples
    }


def add_statement(
    tmp_path: Path,
    workspace_id: str,
    subject: str,
    predicate: str,
    object_value: str,
    document_id: str = "doc-1",
    run_id: str = "run-1",
) -> str:
    """Adds a single candidate statement and returns its statement id."""
    return add_statements(
        tmp_path,
        workspace_id,
        [(subject, predicate, object_value)],
        document_id=document_id,
        run_id=run_id,
    )[predicate]


async def setup_workspace_with_statement(
    client,
    tmp_path,
    subject: str = "http://example.org/s",
    predicate: str = "http://example.org/p",
    object_value: str = "o",
) -> tuple[str, str, str]:
    """Registers an owner, creates a workspace, and adds one candidate statement
    in it. Returns (workspace_id, statement_id, owner_token)."""
    _, _, owner_token = await register_user(client, "owner")
    as_user(client, owner_token)
    workspace_id = await create_workspace(client)
    stmt_id = add_statement(tmp_path, workspace_id, subject, predicate, object_value)
    return workspace_id, stmt_id, owner_token
