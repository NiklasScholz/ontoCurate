from test_utils import (
    add_member,
    as_user,
    register_user,
    setup_workspace_with_statement,
)

from app.store.client import data_graph
from app.store.utils import PACO


class TestQueryEndpoint:
    async def test_editor_can_query_data_graph(self, client, tmp_path):
        workspace_id, stmt_id, owner_token = await setup_workspace_with_statement(
            client, tmp_path
        )
        as_user(client, owner_token)
        await client.post(
            f"/statements/{workspace_id}/accept", params={"statement_id": stmt_id}
        )

        _, editor_email, editor_token = await register_user(client, "editor")
        as_user(client, owner_token)
        await add_member(client, workspace_id, editor_email, "editor")
        as_user(client, editor_token)

        resp = await client.post(
            f"/workspaces/{workspace_id}/query",
            json={"query": "SELECT * WHERE { ?s ?p ?o }"},
        )
        assert resp.status_code == 200
        body = resp.json()
        assert sorted(body["variables"]) == ["o", "p", "s"]
        assert len(body["rows"]) == 1
        assert body["rows"][0]["s"]["value"] == "http://example.org/s"

    async def test_non_member_cannot_query(self, client, tmp_path):
        workspace_id, _, _ = await setup_workspace_with_statement(client, tmp_path)
        _, _, outsider_token = await register_user(client, "outsider")
        as_user(client, outsider_token)
        resp = await client.post(
            f"/workspaces/{workspace_id}/query",
            json={"query": "SELECT * WHERE { ?s ?p ?o }"},
        )
        assert resp.status_code == 403

    async def test_ask_query_returns_boolean(self, client, tmp_path):
        workspace_id, stmt_id, owner_token = await setup_workspace_with_statement(
            client, tmp_path
        )
        as_user(client, owner_token)
        await client.post(
            f"/statements/{workspace_id}/accept", params={"statement_id": stmt_id}
        )

        resp = await client.post(
            f"/workspaces/{workspace_id}/query",
            json={"query": "ASK WHERE { ?s ?p ?o }"},
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["boolean"] is True
        assert body["rows"] == []

        resp = await client.post(
            f"/workspaces/{workspace_id}/query",
            json={"query": "ASK WHERE { <http://example.org/nope> ?p ?o }"},
        )
        assert resp.status_code == 200
        assert resp.json()["boolean"] is False

    async def test_editor_curation_request_forwards_to_data_graph(
        self, client, tmp_path
    ):
        workspace_id, _, owner_token = await setup_workspace_with_statement(
            client, tmp_path
        )
        _, editor_email, editor_token = await register_user(client, "editor")
        as_user(client, owner_token)
        await add_member(client, workspace_id, editor_email, "editor")
        as_user(client, editor_token)
        resp = await client.post(
            f"/workspaces/{workspace_id}/query",
            json={"query": "SELECT * WHERE { ?s ?p ?o }", "graph": "curation"},
        )
        assert resp.status_code == 200
        assert resp.json()["rows"] == []

    async def test_owner_can_query_curation_graph(self, client, tmp_path):
        workspace_id, stmt_id, owner_token = await setup_workspace_with_statement(
            client, tmp_path
        )
        as_user(client, owner_token)
        await client.post(
            f"/statements/{workspace_id}/accept", params={"statement_id": stmt_id}
        )
        resp = await client.post(
            f"/workspaces/{workspace_id}/query",
            json={
                "query": (
                    f"PREFIX paco: <{PACO}>"
                    " SELECT ?origin WHERE { ?s paco:origin ?origin }"
                ),
                "graph": "curation",
            },
        )
        assert resp.status_code == 200
        body = resp.json()
        assert len(body["rows"]) >= 1

    async def test_query_handles_prefixes(self, client, tmp_path):
        workspace_id, _, owner_token = await setup_workspace_with_statement(
            client, tmp_path
        )
        as_user(client, owner_token)

        resp = await client.post(
            f"/workspaces/{workspace_id}/query",
            json={
                "query": (
                    f"PREFIX paco: <{PACO}>"
                    " SELECT ?status WHERE { ?s paco:curationStatus ?status } LIMIT 1"
                ),
                "graph": "curation",
            },
        )
        assert resp.status_code == 200
        body = resp.json()
        assert len(body["rows"]) >= 1
        assert body["rows"][0]["status"]["value"].startswith("paco:")

    async def test_query_uses_client_prefixes(self, client, tmp_path):
        workspace_id, _, owner_token = await setup_workspace_with_statement(
            client, tmp_path
        )
        as_user(client, owner_token)
        resp = await client.post(
            f"/workspaces/{workspace_id}/query",
            json={
                "query": (
                    f"PREFIX myp: <{PACO}>"
                    " SELECT ?status WHERE { ?s myp:curationStatus ?status } LIMIT 1"
                ),
                "graph": "curation",
            },
        )
        assert resp.status_code == 200
        body = resp.json()
        assert len(body["rows"]) >= 1
        assert body["rows"][0]["status"]["value"].startswith("myp:")

    async def test_query_cannot_reach_other_workspace_graph(self, client, tmp_path):
        workspace_a, _, owner_a_token = await setup_workspace_with_statement(
            client, tmp_path
        )
        as_user(client, owner_a_token)
        workspace_b, stmt_b, owner_b_token = await setup_workspace_with_statement(
            client,
            tmp_path,
            subject="http://example.org/s2",
            predicate="http://example.org/p2",
            object_value="o2",
        )
        as_user(client, owner_b_token)
        await client.post(
            f"/statements/{workspace_b}/accept", params={"statement_id": stmt_b}
        )
        as_user(client, owner_a_token)
        other_graph = data_graph(workspace_b)
        resp = await client.post(
            f"/workspaces/{workspace_a}/query",
            json={
                "query": f"SELECT * WHERE {{ GRAPH <{other_graph}> {{ ?s ?p ?o }} }}"
            },
        )
        assert resp.status_code == 200
        assert resp.json()["rows"] == []

    async def test_invalid_query_returns_error(self, client, tmp_path):
        workspace_id, _, owner_token = await setup_workspace_with_statement(
            client, tmp_path
        )
        as_user(client, owner_token)
        resp = await client.post(
            f"/workspaces/{workspace_id}/query",
            json={"query": "SELECT * WHERE { ?s ?p"},
        )
        assert resp.status_code == 422
        assert resp.json()["detail"]
