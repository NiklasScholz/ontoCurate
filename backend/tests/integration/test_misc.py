import uuid

from test_utils import as_user, register_user, unique_email


class TestUserLookup:
    async def test_finds_user_by_email(self, client):
        _, _, requester_token = await register_user(client, "owner")
        _, target_email, _ = await register_user(client, "user-to-find")
        as_user(client, requester_token)

        resp = await client.get("/users/lookup", params={"user_info": target_email})
        assert resp.status_code == 200
        body = resp.json()
        assert body["email"] == target_email

    async def test_finds_user_by_username(self, client):
        _, _, requester_token = await register_user(client, "owner")
        username = f"target-{uuid.uuid4().hex[:8]}"
        register_resp = await client.post(
            "/auth/register",
            json={
                "username": username,
                "email": unique_email("target"),
                "password": "password123",
            },
        )
        assert register_resp.status_code == 200

        as_user(client, requester_token)
        resp = await client.get("/users/lookup", params={"user_info": username})
        assert resp.status_code == 200
        assert resp.json()["name"] == username

    async def test_unknown_user_returns_404(self, client):
        _, _, requester_token = await register_user(client, "owner")
        as_user(client, requester_token)

        resp = await client.get(
            "/users/lookup", params={"user_info": "nobody@rwth-aachen.de"}
        )
        assert resp.status_code == 404
