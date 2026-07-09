import uuid
from unittest.mock import patch


def unique_email(label: str) -> str:
    return f"{label}-{uuid.uuid4().hex[:8]}@example.com"


async def test_register_sets_cookie_and_creates_user(client):
    email = unique_email("register")
    resp = await client.post(
        "/auth/register",
        json={"username": None, "email": email, "password": "password123"},
    )
    assert resp.status_code == 200
    assert "access_token" in resp.cookies
    assert resp.json()["email"] == email


async def test_register_duplicate_email_fails(client):
    email = unique_email("dup")
    body = {"username": None, "email": email, "password": "password123"}
    assert (await client.post("/auth/register", json=body)).status_code == 200
    resp = await client.post("/auth/register", json=body)
    assert resp.status_code == 400


async def test_me_requires_auth(client):
    resp = await client.get("/auth/me")
    assert resp.status_code == 401


async def test_me_returns_current_user_after_register(client):
    email = unique_email("me")
    await client.post(
        "/auth/register",
        json={"username": None, "email": email, "password": "password123"},
    )
    resp = await client.get("/auth/me")
    assert resp.status_code == 200
    assert resp.json()["email"] == email


async def test_login_success(client):
    email = unique_email("login")
    password = "test123"
    await client.post(
        "/auth/register", json={"username": None, "email": email, "password": password}
    )
    await client.post("/auth/logout")

    resp = await client.post(
        "/auth/login", json={"login_name": email, "password": password}
    )
    assert resp.status_code == 200
    assert (await client.get("/auth/me")).status_code == 200


async def test_login_wrong_password_fails(client):
    email = unique_email("badpw")
    await client.post(
        "/auth/register",
        json={"username": None, "email": email, "password": "correctpassword"},
    )
    resp = await client.post(
        "/auth/login", json={"login_name": email, "password": "wrongpassword"}
    )
    assert resp.status_code == 401


async def test_login_unknown_user_fails(client):
    resp = await client.post(
        "/auth/login",
        json={"login_name": unique_email("nobody"), "password": "whatever123"},
    )
    assert resp.status_code == 401


async def test_logout_clears_session(client):
    email = unique_email("logout")
    await client.post(
        "/auth/register",
        json={"username": None, "email": email, "password": "password123"},
    )
    assert (await client.get("/auth/me")).status_code == 200

    resp = await client.post("/auth/logout")
    assert resp.status_code == 200
    assert (await client.get("/auth/me")).status_code == 401


async def test_delete_account_removes_session(client):
    email = unique_email("delete")
    await client.post(
        "/auth/register",
        json={"username": None, "email": email, "password": "password123"},
    )
    resp = await client.delete("/auth/me")
    assert resp.status_code == 200
    assert (await client.get("/auth/me")).status_code == 401


async def test_google_auth_creates_and_logs_in_user(client):
    email = unique_email("google")
    fake_payload = {
        "email": email,
        "name": "Google Test User",
        "picture": "https://example.com/pic.png",
        "sub": "google-sub-" + uuid.uuid4().hex[:8],
    }
    with patch(
        "app.routes.auth.id_token.verify_oauth2_token", return_value=fake_payload
    ):
        resp = await client.post("/auth/google", json={"credential": "fake-credential"})

    assert resp.status_code == 200
    assert resp.json()["email"] == email
    assert "access_token" in resp.cookies
    assert (await client.get("/auth/me")).status_code == 200


async def test_google_auth_rejects_invalid_token(client):
    with patch(
        "app.routes.auth.id_token.verify_oauth2_token",
        side_effect=ValueError("invalid token"),
    ):
        resp = await client.post(
            "/auth/google", json={"credential": "not-a-real-token"}
        )
    assert resp.status_code == 401


async def test_protected_route_requires_auth(client):
    resp = await client.get(f"/extraction/{uuid.uuid4()}")
    assert resp.status_code == 401
