import json

from test_utils import (
    add_member,
    add_statement,
    as_user,
    create_workspace,
    register_user,
    setup_workspace_with_statement,
)

from app.store.utils import PACO


async def create_workspace_with_document(client, owner_token) -> tuple[str, str]:
    as_user(client, owner_token)
    workspace_id = await create_workspace(client)
    resp = await client.post(
        "/extraction/",
        params={"workspace_id": workspace_id},
        files=[("files", ("doc.md", b"# hello world", "text/markdown"))],
    )
    assert resp.status_code < 400
    docs = await client.get("/documents/", params={"workspace_id": workspace_id})
    document_id = docs.json()[0]["id"]
    return workspace_id, document_id


async def add_document_to_workspace(client, workspace_id: str, filename: str) -> str:
    resp = await client.post(
        "/extraction/",
        params={"workspace_id": workspace_id},
        files=[("files", (filename, b"# hello again", "text/markdown"))],
    )
    assert resp.status_code < 400
    docs = await client.get("/documents/", params={"workspace_id": workspace_id})
    return next(d["id"] for d in docs.json() if d["filename"] == filename)


class TestWorkspaceExport:
    async def test_editor_can_export_data_graph_ttl(self, client, tmp_path):
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

        resp = await client.get(f"/workspaces/{workspace_id}/export/data")
        assert resp.status_code == 200
        assert '"o"' in resp.text
        assert resp.headers["content-type"].startswith("text/turtle")

    async def test_data_graph_export_jsonld(self, client, tmp_path):
        workspace_id, stmt_id, owner_token = await setup_workspace_with_statement(
            client, tmp_path
        )
        as_user(client, owner_token)
        await client.post(
            f"/statements/{workspace_id}/accept", params={"statement_id": stmt_id}
        )

        resp = await client.get(
            f"/workspaces/{workspace_id}/export/data", params={"format": "json-ld"}
        )
        assert resp.status_code == 200
        body = json.loads(resp.text)
        entries = body if isinstance(body, list) else [body]
        assert any(entry.get("@id") == "http://example.org/s" for entry in entries)

    async def test_owner_can_export_provenance_graph(self, client, tmp_path):
        workspace_id, stmt_id, owner_token = await setup_workspace_with_statement(
            client, tmp_path
        )
        as_user(client, owner_token)
        await client.post(
            f"/statements/{workspace_id}/accept", params={"statement_id": stmt_id}
        )

        resp = await client.get(f"/workspaces/{workspace_id}/export/provenance")
        assert resp.status_code == 200
        assert "paco:origin" in resp.text

    async def test_editor_forbidden_provenance_export(self, client, tmp_path):
        workspace_id, _, owner_token = await setup_workspace_with_statement(
            client, tmp_path
        )
        _, editor_email, editor_token = await register_user(client, "editor")
        as_user(client, owner_token)
        await add_member(client, workspace_id, editor_email, "editor")
        as_user(client, editor_token)

        resp = await client.get(f"/workspaces/{workspace_id}/export/provenance")
        assert resp.status_code == 403


class TestWorkspacePrefixes:
    async def test_returns_prefixes(self, client, tmp_path):
        workspace_id, _, owner_token = await setup_workspace_with_statement(
            client, tmp_path
        )
        as_user(client, owner_token)
        resp = await client.get(f"/workspaces/{workspace_id}/prefixes")
        assert resp.status_code == 200
        prefixes = resp.json()
        assert prefixes["paco"] == PACO
        assert "schema" in prefixes
        assert "smo" in prefixes
        assert "linkml" not in prefixes


class TestDocumentExport:
    async def test_data_export_document(self, client, tmp_path):
        _, _, owner_token = await register_user(client, "owner")
        workspace_id, doc_a = await create_workspace_with_document(client, owner_token)
        doc_b = await add_document_to_workspace(client, workspace_id, "doc-b.md")
        as_user(client, owner_token)
        stmt_a = add_statement(
            tmp_path,
            workspace_id,
            "http://example.org/a-subj",
            "http://example.org/a-pred",
            "a-obj",
            document_id=doc_a,
        )
        stmt_b = add_statement(
            tmp_path,
            workspace_id,
            "http://example.org/b-subj",
            "http://example.org/b-pred",
            "b-obj",
            document_id=doc_b,
            run_id="run-2",
        )
        await client.post(
            f"/statements/{workspace_id}/accept", params={"statement_id": stmt_a}
        )
        await client.post(
            f"/statements/{workspace_id}/accept", params={"statement_id": stmt_b}
        )
        resp_a = await client.get(f"/documents/{doc_a}/export/data")
        assert resp_a.status_code == 200
        assert "a-subj" in resp_a.text
        assert "b-subj" not in resp_a.text
        resp_b = await client.get(f"/documents/{doc_b}/export/data")
        assert resp_b.status_code == 200
        assert "b-subj" in resp_b.text
        assert "a-subj" not in resp_b.text

    async def test_provenance_export_owner_only_and_scoped(self, client, tmp_path):
        _, _, owner_token = await register_user(client, "owner")
        workspace_id, doc_a = await create_workspace_with_document(client, owner_token)
        doc_b = await add_document_to_workspace(client, workspace_id, "doc-b.md")
        as_user(client, owner_token)
        add_statement(
            tmp_path,
            workspace_id,
            "http://example.org/a-subj",
            "http://example.org/a-pred",
            "a-obj",
            document_id=doc_a,
        )
        add_statement(
            tmp_path,
            workspace_id,
            "http://example.org/b-subj",
            "http://example.org/b-pred",
            "b-obj",
            document_id=doc_b,
            run_id="run-2",
        )
        _, editor_email, editor_token = await register_user(client, "editor")
        as_user(client, owner_token)
        await add_member(client, workspace_id, editor_email, "editor")
        as_user(client, editor_token)
        forbidden = await client.get(f"/documents/{doc_a}/export/provenance")
        assert forbidden.status_code == 403
        as_user(client, owner_token)
        resp = await client.get(f"/documents/{doc_a}/export/provenance")
        assert resp.status_code == 200
        assert f"doc:{doc_a}" in resp.text
        assert f"doc:{doc_b}" not in resp.text
        assert "paco:origin" in resp.text
