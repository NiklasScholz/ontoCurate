import uuid

from test_utils import add_member, as_user, create_workspace, register_user


class TestWorkspaceCreation:
    async def test_unknown_schema_name_returns_400(self, client):
        _, _, owner_token = await register_user(client, "owner")
        as_user(client, owner_token)
        resp = await client.post(
            "/workspaces/",
            json={"name": "my workspace", "schema_name": "not-a-real-schema"},
        )
        assert resp.status_code == 400


class TestWorkspaces:
    async def test_owner_sees_created_workspace(self, client):
        _, _, owner_token = await register_user(client, "owner")
        as_user(client, owner_token)
        workspace_id = await create_workspace(client)
        resp = await client.get("/workspaces/")
        assert resp.status_code == 200
        by_id = {w["id"]: w for w in resp.json()}
        assert by_id[workspace_id]["role"] == "owner"
        resp = await client.get(f"/workspaces/{workspace_id}")
        assert resp.status_code == 200
        assert resp.json()["role"] == "owner"

    async def test_non_member_does_not_see_workspace(self, client):
        _, _, owner_token = await register_user(client, "owner")
        as_user(client, owner_token)
        workspace_id = await create_workspace(client)
        _, _, non_member_token = await register_user(client, "non-member")
        as_user(client, non_member_token)
        resp = await client.get("/workspaces/")
        ids = {w["id"] for w in resp.json()}
        assert workspace_id not in ids
        resp = await client.get(f"/workspaces/{workspace_id}")
        assert resp.status_code == 403

    async def test_owner_can_delete(self, client):
        _, _, owner_token = await register_user(client, "owner")
        as_user(client, owner_token)
        workspace_id = await create_workspace(client)
        resp = await client.delete(f"/workspaces/{workspace_id}")
        assert resp.status_code == 204
        resp = await client.get(f"/workspaces/{workspace_id}")
        assert resp.status_code == 404
        resp = await client.get("/workspaces/")
        assert workspace_id not in {w["id"] for w in resp.json()}

    async def test_editor_cannot_delete(self, client):
        _, _, owner_token = await register_user(client, "owner")
        as_user(client, owner_token)
        workspace_id = await create_workspace(client)
        _, editor_email, editor_token = await register_user(client, "editor")
        await add_member(client, workspace_id, editor_email, "editor")
        as_user(client, editor_token)
        resp = await client.delete(f"/workspaces/{workspace_id}")
        assert resp.status_code == 403

    async def test_non_member_cannot_delete(self, client):
        _, _, owner_token = await register_user(client, "owner")
        as_user(client, owner_token)
        workspace_id = await create_workspace(client)
        _, _, non_member_token = await register_user(client, "no member")
        as_user(client, non_member_token)
        resp = await client.delete(f"/workspaces/{workspace_id}")
        assert resp.status_code == 403


class TestWorkspaceMembers:
    async def test_owner_can_list_members(self, client):
        _, owner_email, owner_token = await register_user(client, "owner")
        as_user(client, owner_token)
        workspace_id = await create_workspace(client)
        _, editor_email, _ = await register_user(client, "editor")
        await add_member(client, workspace_id, editor_email, "editor")
        resp = await client.get(f"/workspaces/{workspace_id}/members")
        assert resp.status_code == 200
        emails = {m["email"] for m in resp.json()}
        assert emails == {owner_email, editor_email}

    async def test_editor_cannot_list_members(self, client):
        _, _, owner_token = await register_user(client, "owner")
        as_user(client, owner_token)
        workspace_id = await create_workspace(client)
        _, editor_email, editor_token = await register_user(client, "editor")
        await add_member(client, workspace_id, editor_email, "editor")
        as_user(client, editor_token)
        resp = await client.get(f"/workspaces/{workspace_id}/members")
        assert resp.status_code == 403

    async def test_adding_unknown_user(self, client):
        _, _, owner_token = await register_user(client, "owner")
        as_user(client, owner_token)
        workspace_id = await create_workspace(client)
        resp = await client.post(
            f"/workspaces/{workspace_id}/members",
            json={"user_info": "nonexistant@rwth-aachen.de", "role": "editor"},
        )
        assert resp.status_code == 400

    async def test_adding_existing_member(self, client):
        _, _, owner_token = await register_user(client, "owner")
        as_user(client, owner_token)
        workspace_id = await create_workspace(client)
        _, editor_email, _ = await register_user(client, "editor")
        await add_member(client, workspace_id, editor_email, "editor")
        # try adding member again
        resp = await client.post(
            f"/workspaces/{workspace_id}/members",
            json={"user_info": editor_email, "role": "editor"},
        )
        assert resp.status_code == 409

    async def test_editor_cannot_add_member(self, client):
        _, _, owner_token = await register_user(client, "owner")
        as_user(client, owner_token)
        workspace_id = await create_workspace(client)
        _, editor_email, editor_token = await register_user(client, "editor")
        await add_member(client, workspace_id, editor_email, "editor")
        _, non_member_email, _ = await register_user(client, "no member")
        as_user(client, editor_token)
        resp = await client.post(
            f"/workspaces/{workspace_id}/members",
            json={"user_info": non_member_email, "role": "editor"},
        )
        assert resp.status_code == 403

    async def test_owner_can_remove_editor(self, client):
        _, _, owner_token = await register_user(client, "owner")
        as_user(client, owner_token)
        workspace_id = await create_workspace(client)
        editor_id, editor_email, _ = await register_user(client, "editor")
        await add_member(client, workspace_id, editor_email, "editor")
        resp = await client.delete(f"/workspaces/{workspace_id}/members/{editor_id}")
        assert resp.status_code == 204
        resp = await client.get(f"/workspaces/{workspace_id}/members")
        emails = {member["email"] for member in resp.json()}
        assert editor_email not in emails

    async def test_cannot_remove_last_owner(self, client):
        owner_id, _, owner_token = await register_user(client, "owner")
        as_user(client, owner_token)
        workspace_id = await create_workspace(client)
        resp = await client.delete(f"/workspaces/{workspace_id}/members/{owner_id}")
        assert resp.status_code == 400

    async def test_remove_owner_when_another_exists(self, client):
        owner_id, _, owner_token = await register_user(client, "owner")
        as_user(client, owner_token)
        workspace_id = await create_workspace(client)
        _, second_owner_email, second_owner_token = await register_user(
            client, "owner2"
        )
        await add_member(client, workspace_id, second_owner_email, "owner")
        resp = await client.delete(f"/workspaces/{workspace_id}/members/{owner_id}")
        assert resp.status_code == 204
        as_user(client, second_owner_token)
        resp = await client.get(f"/workspaces/{workspace_id}/members")
        emails = {member["email"] for member in resp.json()}
        assert second_owner_email in emails
        assert len(emails) == 1

    async def test_editor_cannot_remove_member(self, client):
        _, _, owner_token = await register_user(client, "owner")
        as_user(client, owner_token)
        workspace_id = await create_workspace(client)
        editor_id, editor_email, editor_token = await register_user(client, "editor")
        await add_member(client, workspace_id, editor_email, "editor")
        as_user(client, editor_token)
        resp = await client.delete(f"/workspaces/{workspace_id}/members/{editor_id}")
        assert resp.status_code == 403

    async def test_remove_as_non_member_and_nonexistent_member(self, client):
        _, _, owner_token = await register_user(client, "owner")
        as_user(client, owner_token)
        workspace_id = await create_workspace(client)
        resp = await client.delete(f"/workspaces/{workspace_id}/members/{uuid.uuid4()}")
        assert resp.status_code == 404
        editor_id, _, editor_token = await register_user(client, "editor")
        as_user(client, editor_token)
        _, _, non_member_token = await register_user(client, "non-member")
        as_user(client, non_member_token)
        resp = await client.delete(f"/workspaces/{workspace_id}/members/{editor_id}")
        assert resp.status_code == 403
