from test_utils import add_member, as_user, create_workspace, register_user


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


async def test_editor_cannot_delete_document(client):
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


async def test_non_member_cannot_delete_document(client):
    _, _, owner_token = await register_user(client, "owner")
    _, _, outsider_token = await register_user(client, "outsider")
    _, document_id = await create_workspace_with_document(client, owner_token)
    as_user(client, outsider_token)
    resp = await client.delete(f"/documents/{document_id}")
    assert resp.status_code == 403


async def test_owner_can_delete_document(client):
    _, _, owner_token = await register_user(client, "owner")
    workspace_id, document_id = await create_workspace_with_document(
        client, owner_token
    )
    as_user(client, owner_token)
    resp = await client.delete(f"/documents/{document_id}")
    assert resp.status_code == 204
    resp = await client.get("/documents/", params={"workspace_id": workspace_id})
    assert resp.json() == []
