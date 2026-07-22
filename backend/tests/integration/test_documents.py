import uuid

from test_utils import (
    add_candidate_statements,
    add_member,
    as_user,
    create_workspace,
    register_user,
    sparql_count,
)

from app.store.client import curation_graph
from app.store.utils import PACO_PENDING

TTL_TEXT = """
@prefix ex: <http://example.org/> .
ex:s ex:p "o" .
"""


async def create_workspace_with_document(client, owner_token):
    as_user(client, owner_token)
    workspace_id = await create_workspace(client)
    await client.post(
        "/extraction/",
        params={"workspace_id": workspace_id},
        files=[("files", ("doc.md", b"# hello world", "text/markdown"))],
    )
    resp = await client.get("/documents/", params={"workspace_id": workspace_id})
    document_id = resp.json()[0]["id"]
    return workspace_id, document_id


async def create_workspace_with_pdf_document(client, owner_token):
    as_user(client, owner_token)
    workspace_id = await create_workspace(client)
    await client.post(
        "/extraction/",
        params={"workspace_id": workspace_id},
        files=[("files", ("doc.pdf", b"%PDF-1.4 fake pdf bytes", "application/pdf"))],
    )
    resp = await client.get("/documents/", params={"workspace_id": workspace_id})
    document_id = resp.json()[0]["id"]
    return workspace_id, document_id


class TestDocumentDelete:

    async def test_editor_cannot_delete_document(self, client):
        _, owner_email, owner_token = await register_user(client, "owner")
        _, editor_email, editor_token = await register_user(client, "editor")
        as_user(client, owner_token)
        workspace_id, document_id = await create_workspace_with_document(
            client, owner_token
        )
        await add_member(client, workspace_id, editor_email, "editor")
        as_user(client, editor_token)
        resp = await client.delete(f"/documents/{document_id}")
        assert resp.status_code == 403

    async def test_non_member_cannot_delete_document(self, client):
        _, _, owner_token = await register_user(client, "owner")
        _, _, outsider_token = await register_user(client, "outsider")
        _, document_id = await create_workspace_with_document(client, owner_token)
        as_user(client, outsider_token)
        resp = await client.delete(f"/documents/{document_id}")
        assert resp.status_code == 403

    async def test_owner_can_delete_document(self, client):
        _, _, owner_token = await register_user(client, "owner")
        workspace_id, document_id = await create_workspace_with_document(
            client, owner_token
        )
        as_user(client, owner_token)
        resp = await client.delete(f"/documents/{document_id}")
        assert resp.status_code == 204
        resp = await client.get("/documents/", params={"workspace_id": workspace_id})
        assert resp.json() == []

    async def test_non_member_cannot_list_documents(self, client):
        _, _, owner_token = await register_user(client, "owner")
        _, _, non_member_token = await register_user(client, "non_member")
        workspace_id, _ = await create_workspace_with_document(client, owner_token)
        as_user(client, non_member_token)
        resp = await client.get("/documents/", params={"workspace_id": workspace_id})
        assert resp.status_code == 403

    async def test_non_member_cannot_get_document(self, client):
        _, _, owner_token = await register_user(client, "owner")
        _, _, non_member_token = await register_user(client, "non_member")
        _, document_id = await create_workspace_with_document(client, owner_token)
        as_user(client, non_member_token)
        resp = await client.get(f"/documents/{document_id}")
        assert resp.status_code == 403

    async def test_delete_removes_statements_from_oxigraph(self, client, tmp_path):
        _, _, owner_token = await register_user(client, "owner")
        workspace_id, document_id = await create_workspace_with_document(
            client, owner_token
        )
        add_candidate_statements(
            tmp_path, workspace_id, TTL_TEXT, document_id=document_id
        )

        count_sparql = f"""
            PREFIX paco: <https://example.org/provenance-and-curation-ontology/>
            SELECT (COUNT(*) AS ?count) WHERE {{
                GRAPH <{curation_graph(workspace_id)}> {{
                    ?cs a paco:CandidateStatement .
                }}
            }}
        """
        assert sparql_count(count_sparql) == 1
        as_user(client, owner_token)
        resp = await client.delete(f"/documents/{document_id}")
        assert resp.status_code == 204
        assert sparql_count(count_sparql) == 0

    async def test_get_document_unknown_not_found(self, client):
        _, _, owner_token = await register_user(client, "owner")
        as_user(client, owner_token)
        resp = await client.get(f"/documents/{uuid.uuid4()}")
        assert resp.status_code == 404

    async def test_delete_document_unknown_not_found(self, client):
        _, _, owner_token = await register_user(client, "owner")
        as_user(client, owner_token)
        resp = await client.delete(f"/documents/{uuid.uuid4()}")
        assert resp.status_code == 404


class TestDocumentMarkdown:
    async def test_can_download_markdown(self, client):
        _, _, owner_token = await register_user(client, "owner")
        _, document_id = await create_workspace_with_document(client, owner_token)
        as_user(client, owner_token)
        resp = await client.get(f"/documents/{document_id}/markdown")
        assert resp.status_code == 200
        assert resp.text == "# hello world"

    async def test_non_member_cannot_download_markdown(self, client):
        _, _, owner_token = await register_user(client, "owner")
        _, _, non_member_token = await register_user(client, "non_member")
        _, document_id = await create_workspace_with_document(client, owner_token)
        as_user(client, non_member_token)
        resp = await client.get(f"/documents/{document_id}/markdown")
        assert resp.status_code == 403

    async def test_still_processing_returns_202(self, client):
        _, _, owner_token = await register_user(client, "owner")
        _, document_id = await create_workspace_with_pdf_document(client, owner_token)
        as_user(client, owner_token)
        resp = await client.get(f"/documents/{document_id}/markdown")
        assert resp.status_code == 202


class TestDocumentPdf:
    async def test_owner_can_download_pdf(self, client):
        _, _, owner_token = await register_user(client, "owner")
        _, document_id = await create_workspace_with_pdf_document(client, owner_token)
        as_user(client, owner_token)
        resp = await client.get(f"/documents/{document_id}/pdf")
        assert resp.status_code == 200
        assert resp.content == b"%PDF-1.4 fake pdf bytes"

    async def test_non_member_cannot_download_pdf(self, client):
        _, _, owner_token = await register_user(client, "owner")
        _, _, non_member_token = await register_user(client, "non_member")
        _, document_id = await create_workspace_with_pdf_document(client, owner_token)
        as_user(client, non_member_token)
        resp = await client.get(f"/documents/{document_id}/pdf")
        assert resp.status_code == 403

    async def test_unknown_document(self, client):
        _, _, owner_token = await register_user(client, "owner")
        as_user(client, owner_token)
        resp = await client.get(f"/documents/{uuid.uuid4()}/pdf")
        assert resp.status_code == 404

    async def test_not_available_for_markdown_document(self, client):
        """A markdown document has no raw_bytes, so its /pdf endpoint has
        nothing to serve."""
        _, _, owner_token = await register_user(client, "owner")
        _, document_id = await create_workspace_with_document(client, owner_token)
        as_user(client, owner_token)
        resp = await client.get(f"/documents/{document_id}/pdf")
        assert resp.status_code == 400


class TestDocumentStatements:
    async def test_owner_can_get_document_statements(self, client, tmp_path):
        _, _, owner_token = await register_user(client, "owner")
        workspace_id, document_id = await create_workspace_with_document(
            client, owner_token
        )
        add_candidate_statements(
            tmp_path, workspace_id, TTL_TEXT, document_id=document_id
        )
        as_user(client, owner_token)

        resp = await client.get(f"/documents/{document_id}/statements")
        assert resp.status_code == 200
        statements = resp.json()
        assert len(statements) == 1
        assert statements[0]["subject"] == "http://example.org/s"
        assert statements[0]["predicate"] == "http://example.org/p"
        assert statements[0]["object"] == "o"
        assert statements[0]["curation_status"] == PACO_PENDING

    async def test_non_member_cannot_get_document_statements(self, client):
        _, _, owner_token = await register_user(client, "owner")
        _, _, non_member_token = await register_user(client, "non_member")
        _, document_id = await create_workspace_with_document(client, owner_token)
        as_user(client, non_member_token)
        resp = await client.get(f"/documents/{document_id}/statements")
        assert resp.status_code == 403

    async def test_unknown_document_returns_404(self, client):
        _, _, owner_token = await register_user(client, "owner")
        as_user(client, owner_token)
        resp = await client.get(f"/documents/{uuid.uuid4()}/statements")
        assert resp.status_code == 404
