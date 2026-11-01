"""Billing tests: plan info, free-plan limit, plan upgrade."""

import httpx
import pytest

from app.db.session import get_session
from app.main import app
from tests.conftest import make_user


@pytest.fixture
async def client(db):
    app.dependency_overrides[get_session] = lambda: db
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(
        transport=transport, base_url="http://testserver"
    ) as async_client:
        yield async_client
    app.dependency_overrides.pop(get_session, None)


async def _auth_header(db, user) -> str:
    from app.auth.security import create_access_token

    return f"Bearer {create_access_token(str(user.id))}"


async def _add_competitor(client, headers, name: str, url: str) -> httpx.Response:
    return await client.post(
        "/api/v1/competitors",
        json={"name": name, "url": url},
        headers=headers,
    )


async def test_plan_default_free(client, db) -> None:
    user = make_user(db, "free@example.com")
    headers = {"Authorization": await _auth_header(db, user)}

    response = await client.get("/api/v1/billing/plan", headers=headers)
    assert response.status_code == 200
    body = response.json()
    assert body["plan"] == "free"
    assert body["competitors_limit"] == 1
    assert body["competitors_used"] == 0


async def test_free_limit_blocks_second(client, db) -> None:
    user = make_user(db, "free-limit@example.com")
    headers = {"Authorization": await _auth_header(db, user)}

    response = await _add_competitor(
        client, headers, "First", "https://first.example.com"
    )
    assert response.status_code == 201

    response = await _add_competitor(
        client, headers, "Second", "https://second.example.com"
    )
    assert response.status_code == 402


async def test_upgrade_unlocks(client, db) -> None:
    user = make_user(db, "upgrade@example.com")
    headers = {"Authorization": await _auth_header(db, user)}

    first = await _add_competitor(
        client, headers, "First", "https://first.example.com"
    )
    assert first.status_code == 201

    # Upgrade to pro before adding the second competitor.
    response = await client.post(
        "/api/v1/billing/plan", json={"plan": "pro"}, headers=headers
    )
    assert response.status_code == 200
    assert response.json()["plan"] == "pro"
    assert response.json()["competitors_limit"] == 10

    second = await _add_competitor(
        client, headers, "Second", "https://second.example.com"
    )
    assert second.status_code == 201


async def test_get_plan_shows_used(client, db) -> None:
    user = make_user(db, "used@example.com")
    headers = {"Authorization": await _auth_header(db, user)}

    response = await _add_competitor(
        client, headers, "Only one", "https://only.example.com"
    )
    assert response.status_code == 201

    response = await client.get("/api/v1/billing/plan", headers=headers)
    assert response.status_code == 200
    assert response.json()["competitors_used"] == 1
