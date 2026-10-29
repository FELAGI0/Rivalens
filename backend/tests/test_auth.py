"""Auth tests: register/login/me, required auth, per-user isolation."""

import httpx
import pytest

from app.db.session import get_session
from app.main import app
from tests.conftest import TEST_PASSWORD, make_user


@pytest.fixture
async def client(db):
    app.dependency_overrides[get_session] = lambda: db
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(
        transport=transport, base_url="http://testserver"
    ) as async_client:
        yield async_client
    app.dependency_overrides.pop(get_session, None)


async def test_register_login_me(client, db) -> None:
    response = await client.post(
        "/api/v1/auth/register",
        json={"email": "auth@example.com", "password": TEST_PASSWORD},
    )
    assert response.status_code == 201
    registered = response.json()
    assert registered["email"] == "auth@example.com"
    assert registered["plan"] == "free"

    response = await client.post(
        "/api/v1/auth/login",
        json={"email": "auth@example.com", "password": TEST_PASSWORD},
    )
    assert response.status_code == 200
    token = response.json()["access_token"]
    assert token

    response = await client.get(
        "/api/v1/auth/me", headers={"Authorization": f"Bearer {token}"}
    )
    assert response.status_code == 200
    me = response.json()
    assert me["email"] == "auth@example.com"
    assert me["id"] == registered["id"]


async def test_login_wrong_password(client, db) -> None:
    make_user(db, "wrongpw@example.com", TEST_PASSWORD)

    response = await client.post(
        "/api/v1/auth/login",
        json={"email": "wrongpw@example.com", "password": "wrong"},
    )
    assert response.status_code == 401


async def test_register_duplicate_email(client, db) -> None:
    make_user(db, "dup@example.com", TEST_PASSWORD)

    response = await client.post(
        "/api/v1/auth/register",
        json={"email": "dup@example.com", "password": TEST_PASSWORD},
    )
    assert response.status_code == 409


async def test_require_auth(client, db) -> None:
    # No token at all.
    response = await client.get("/api/v1/competitors")
    assert response.status_code == 401

    # Garbage token.
    response = await client.get(
        "/api/v1/competitors", headers={"Authorization": "Bearer nonsense"}
    )
    assert response.status_code == 401

    # /health stays public.
    response = await client.get("/health")
    assert response.status_code == 200


async def test_isolate_between_users(client, db) -> None:
    from app.auth.security import create_access_token

    user_a = make_user(db, "user-a@example.com")
    user_b = make_user(db, "user-b@example.com")

    headers_a = {"Authorization": f"Bearer {create_access_token(str(user_a.id))}"}
    headers_b = {"Authorization": f"Bearer {create_access_token(str(user_b.id))}"}

    # User A creates a competitor.
    response = await client.post(
        "/api/v1/competitors",
        json={"name": "A's competitor", "url": "https://a.example.com"},
        headers=headers_a,
    )
    assert response.status_code == 201
    competitor_id = response.json()["id"]

    # User B does not see it in the list.
    response = await client.get("/api/v1/competitors", headers=headers_b)
    assert response.status_code == 200
    assert response.json() == []

    # User B gets 404 (not 403) for A's competitor detail.
    for path in (
        f"/api/v1/competitors/{competitor_id}",
        f"/api/v1/competitors/{competitor_id}/insights",
        f"/api/v1/competitors/{competitor_id}/changes",
    ):
        response = await client.get(path, headers=headers_b)
        assert response.status_code == 404, path

    # And cannot check it.
    response = await client.post(
        f"/api/v1/competitors/{competitor_id}/check", headers=headers_b
    )
    assert response.status_code == 404

    # User A still sees it.
    response = await client.get(
        f"/api/v1/competitors/{competitor_id}", headers=headers_a
    )
    assert response.status_code == 200
    assert response.json()["competitor"]["name"] == "A's competitor"
