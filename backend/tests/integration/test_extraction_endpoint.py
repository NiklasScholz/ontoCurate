from test_utils import add_member, as_user, create_workspace, register_user


async def test_owner_can_upload_markdown(client):
    _, _, owner_token = await register_user(client, "owner")
    as_user(client, owner_token)
    workspace_id = await create_workspace(client)
    resp = await client.post(
        "/extraction/",
        params={"workspace_id": workspace_id},
        files=[("files", ("doc.md", b"# hello world", "text/markdown"))],
    )
    assert resp.status_code == 202
    body = resp.json()
    assert body["status"] == "queued"
    assert "run_id" in body

    docs_resp = await client.get("/documents/", params={"workspace_id": workspace_id})
    assert docs_resp.status_code == 200
    docs = docs_resp.json()
    assert len(docs) == 1
    assert docs[0]["filename"] == "doc.md"
    assert docs[0]["file_type"] == "markdown"


async def test_owner_can_upload_pdf(client):
    _, _, owner_token = await register_user(client, "owner")
    as_user(client, owner_token)
    workspace_id = await create_workspace(client)
    resp = await client.post(
        "/extraction/",
        params={"workspace_id": workspace_id},
        files=[("files", ("doc.pdf", b"PDF bytes", "application/pdf"))],
    )
    assert resp.status_code == 202

    docs_resp = await client.get("/documents/", params={"workspace_id": workspace_id})
    docs = docs_resp.json()
    assert len(docs) == 1
    assert docs[0]["file_type"] == "pdf"


async def test_editor_can_upload(client):
    _, _, owner_token = await register_user(client, "owner")
    as_user(client, owner_token)
    workspace_id = await create_workspace(client)
    _, editor_email, editor_token = await register_user(client, "editor")
    await add_member(client, workspace_id, editor_email, "editor")
    as_user(client, editor_token)
    resp = await client.post(
        "/extraction/",
        params={"workspace_id": workspace_id},
        files=[("files", ("doc.md", b"# hello world", "text/markdown"))],
    )
    assert resp.status_code == 202


async def test_non_member_cannot_upload(client):
    _, _, owner_token = await register_user(client, "owner")
    as_user(client, owner_token)
    workspace_id = await create_workspace(client)
    _, _, non_member_token = await register_user(client, "no member")
    as_user(client, non_member_token)
    resp = await client.post(
        "/extraction/",
        params={"workspace_id": workspace_id},
        files=[("files", ("doc.md", b"# hello world", "text/markdown"))],
    )
    assert resp.status_code == 403


async def test_uploading_duplicate_file_fails(client):
    _, _, owner_token = await register_user(client, "owner")
    as_user(client, owner_token)
    workspace_id = await create_workspace(client)
    files = [("files", ("doc.md", b"# hello world", "text/markdown"))]
    resp = await client.post(
        "/extraction/", params={"workspace_id": workspace_id}, files=files
    )
    assert resp.status_code == 202
    resp = await client.post(
        "/extraction/", params={"workspace_id": workspace_id}, files=files
    )
    assert resp.status_code == 400


async def test_unsupported_file_type_fails(client):
    _, _, owner_token = await register_user(client, "owner")
    as_user(client, owner_token)
    workspace_id = await create_workspace(client)
    resp = await client.post(
        "/extraction/",
        params={"workspace_id": workspace_id},
        files=[("files", ("doc.exe", b"binary of exe", "application/octet-stream"))],
    )
    assert resp.status_code == 400
