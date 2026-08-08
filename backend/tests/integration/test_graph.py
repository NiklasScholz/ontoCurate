import json

from rdflib import Graph
from test_utils import (
    add_candidate_statements,
    add_member,
    add_statement,
    as_user,
    create_workspace,
    find_candidate_id,
    register_user,
    setup_workspace_with_statement,
)

from app.store.utils import OWL_SAME_AS
from app.store.writer import write_alignment_results, write_lookup_results


class TestDeduplicationCount:
    async def test_counts_pending_and_total(self, client, tmp_path):
        workspace_id, _, owner_token = await setup_workspace_with_statement(
            client, tmp_path
        )
        as_user(client, owner_token)
        write_lookup_results(
            [("http://example.org/a", "http://example.org/b", 0.9)],
            workspace_id,
            document_ids=["doc-1"],
        )
        write_alignment_results(
            [("http://example.org/c", "http://example.org/d", 0.8)],
            workspace_id,
            document_ids=["doc-1"],
        )

        resp = await client.get(f"/graph/{workspace_id}/deduplication/count")
        assert resp.status_code == 200
        body = resp.json()
        assert body["total_count"] == 2
        assert body["pending_count"] == 2

    async def test_accepted_pair_not_counted_as_pending(self, client, tmp_path):
        workspace_id, _, owner_token = await setup_workspace_with_statement(
            client, tmp_path
        )
        as_user(client, owner_token)
        write_lookup_results(
            [("http://example.org/a", "http://example.org/b", 0.9)],
            workspace_id,
            document_ids=["doc-1"],
        )
        stmt_id = find_candidate_id(
            workspace_id, OWL_SAME_AS, subject="http://example.org/a"
        )
        accept_resp = await client.post(
            f"/statements/{workspace_id}/accept", params={"statement_id": stmt_id}
        )
        assert accept_resp.status_code == 200

        resp = await client.get(f"/graph/{workspace_id}/deduplication/count")
        body = resp.json()
        assert body["total_count"] == 1
        assert body["pending_count"] == 0

    async def test_non_member_forbidden(self, client, tmp_path):
        workspace_id, _, _ = await setup_workspace_with_statement(client, tmp_path)
        _, _, outsider_token = await register_user(client, "outsider")
        as_user(client, outsider_token)
        resp = await client.get(f"/graph/{workspace_id}/deduplication/count")
        assert resp.status_code == 403


class TestDeduplicationList:
    async def test_returns_lookup_and_alignment_pairs(self, client, tmp_path):
        workspace_id, _, owner_token = await setup_workspace_with_statement(
            client, tmp_path
        )
        as_user(client, owner_token)
        write_lookup_results(
            [("http://example.org/a", "http://example.org/b", 0.9)],
            workspace_id,
            document_ids=["doc-1"],
        )

        resp = await client.get(f"/graph/{workspace_id}/deduplication")
        assert resp.status_code == 200
        rows = resp.json()
        assert len(rows) == 1
        assert rows[0]["current"]["subject"] == "http://example.org/a"
        assert rows[0]["current"]["predicate"] == OWL_SAME_AS
        assert rows[0]["current"]["object"] == "http://example.org/b"


class TestEntityNeighborhood:
    async def test_returns_incoming_and_outgoing_edges(self, client, tmp_path):
        _, _, owner_token = await register_user(client, "owner")
        as_user(client, owner_token)
        workspace_id = await create_workspace(client)
        add_candidate_statements(
            tmp_path,
            workspace_id,
            "<http://example.org/s> <http://example.org/p> <http://example.org/o> .",
        )

        resp = await client.get(
            f"/graph/{workspace_id}/neighborhood",
            params={"entity_id": "http://example.org/s"},
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["incoming"] == []
        assert len(body["outgoing"]) == 1
        assert body["outgoing"][0]["predicate"] == "http://example.org/p"
        assert body["outgoing"][0]["object"] == "http://example.org/o"

        resp = await client.get(
            f"/graph/{workspace_id}/neighborhood",
            params={"entity_id": "http://example.org/o"},
        )
        body = resp.json()
        assert len(body["incoming"]) == 1
        assert body["incoming"][0]["predicate"] == "http://example.org/p"
        assert body["incoming"][0]["subject"] == "http://example.org/s"
        assert body["outgoing"] == []

    async def test_literal_object_returns_empty_neighborhood(self, client, tmp_path):
        workspace_id, _, owner_token = await setup_workspace_with_statement(
            client, tmp_path
        )
        as_user(client, owner_token)
        resp = await client.get(
            f"/graph/{workspace_id}/neighborhood",
            params={"entity_id": "o"},
        )
        assert resp.status_code == 200
        assert resp.json() == {"incoming": [], "outgoing": []}

    async def test_non_member_forbidden(self, client, tmp_path):
        workspace_id, _, _ = await setup_workspace_with_statement(client, tmp_path)
        _, _, outsider_token = await register_user(client, "outsider")
        as_user(client, outsider_token)
        resp = await client.get(
            f"/graph/{workspace_id}/neighborhood",
            params={"entity_id": "http://example.org/s"},
        )
        assert resp.status_code == 403


class TestDeduplicationExport:
    async def setup_workspace_with_aligned_statement(
        self, client, tmp_path, owner_token
    ):
        as_user(client, owner_token)
        workspace_id = await create_workspace(client)
        prior_stmt = add_statement(
            tmp_path,
            workspace_id,
            "http://example.org/prior_a2c3c4",
            "http://example.org/name",
            "Alice",
        )
        accept_resp = await client.post(
            f"/statements/{workspace_id}/accept",
            params={"statement_id": prior_stmt},
        )
        assert accept_resp.status_code == 200
        write_alignment_results(
            [
                (
                    "http://example.org/prior_a2c3c4",
                    "http://example.org/current_a1b2c3",
                    0.95,
                )
            ],
            workspace_id,
            document_ids=["doc-1"],
        )
        alignment_stmt = find_candidate_id(
            workspace_id, OWL_SAME_AS, subject="http://example.org/current_a1b2c3"
        )
        accept_alignment_resp = await client.post(
            f"/statements/{workspace_id}/accept",
            params={"statement_id": alignment_stmt},
        )
        assert accept_alignment_resp.status_code == 200
        return workspace_id

    async def test_owner_can_export_merges_aligned_entities(self, client, tmp_path):
        _, _, owner_token = await register_user(client, "owner")
        workspace_id = await self.setup_workspace_with_aligned_statement(
            client, tmp_path, owner_token
        )

        resp = await client.get(f"/graph/{workspace_id}/deduplication/export")
        assert resp.status_code == 200
        assert resp.headers["content-type"].startswith("text/turtle")
        content_disposition = resp.headers["content-disposition"]
        assert content_disposition.startswith('attachment; filename="')
        assert content_disposition.endswith('_deduplicated.ttl"')
        assert "Alice" in resp.text
        graph = Graph()
        graph.parse(data=resp.text, format="turtle")
        subjects = {str(s) for s in graph.subjects()}
        assert subjects == {"http://example.org/current"}

    async def test_export_jsonld_format(self, client, tmp_path):
        _, _, owner_token = await register_user(client, "owner")
        workspace_id = await self.setup_workspace_with_aligned_statement(
            client, tmp_path, owner_token
        )
        resp = await client.get(
            f"/graph/{workspace_id}/deduplication/export",
            params={"format": "json-ld"},
        )
        assert resp.status_code == 200
        assert resp.headers["content-type"].startswith("application/ld+json")
        body = json.loads(resp.text)
        entries = body if isinstance(body, list) else [body]
        assert any(
            entry.get("@id") == "http://example.org/current" for entry in entries
        )

    async def test_editor_can_export(self, client, tmp_path):
        _, _, owner_token = await register_user(client, "owner")
        workspace_id = await self.setup_workspace_with_aligned_statement(
            client, tmp_path, owner_token
        )
        _, editor_email, editor_token = await register_user(client, "editor")
        as_user(client, owner_token)
        await add_member(client, workspace_id, editor_email, "editor")
        as_user(client, editor_token)
        resp = await client.get(f"/graph/{workspace_id}/deduplication/export")
        assert resp.status_code == 200

    async def test_non_member_cannot_export(self, client, tmp_path):
        _, _, owner_token = await register_user(client, "owner")
        workspace_id = await self.setup_workspace_with_aligned_statement(
            client, tmp_path, owner_token
        )
        _, _, outsider_token = await register_user(client, "outsider")
        as_user(client, outsider_token)
        resp = await client.get(f"/graph/{workspace_id}/deduplication/export")
        assert resp.status_code == 403
