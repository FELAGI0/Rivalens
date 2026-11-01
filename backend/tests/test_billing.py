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
    assert body["competitors_limit"] == 2
    assert body["competitors_used"] == 0


async def test_free_limit_blocks_third(client, db) -> None:
    """free=2: two competitors fit, the third is blocked with 402."""
    user = make_user(db, "free-limit@example.com")
    headers = {"Authorization": await _auth_header(db, user)}

    for name, host in (
        ("First", "first.example.com"),
        ("Second", "second.example.com"),
    ):
        response = await _add_competitor(
            client, headers, name, f"https://{host}"
        )
        assert response.status_code == 201

    response = await _add_competitor(
        client, headers, "Third", "https://third.example.com"
    )
    assert response.status_code == 402
    assert "Pro" in response.json()["detail"]


async def test_upgrade_unlocks(client, db) -> None:
    user = make_user(db, "upgrade@example.com")
    headers = {"Authorization": await _auth_header(db, user)}

    first = await _add_competitor(
        client, headers, "First", "https://first.example.com"
    )
    assert first.status_code == 201

    # Upgrade to pro, then fill past the free limit of 2.
    response = await client.post(
        "/api/v1/billing/plan", json={"plan": "pro"}, headers=headers
    )
    assert response.status_code == 200
    assert response.json()["plan"] == "pro"
    assert response.json()["competitors_limit"] == 10

    for name, host in (
        ("Second", "second.example.com"),
        ("Third", "third.example.com"),
        ("Fourth", "fourth.example.com"),
    ):
        response = await _add_competitor(
            client, headers, name, f"https://{host}"
        )
        assert response.status_code == 201


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


async def test_free_limit_two(client, db) -> None:
    """Free plan now fits 2 competitors; the third is a 402."""
    user = make_user(db, "free-two@example.com")
    headers = {"Authorization": await _auth_header(db, user)}

    first = await _add_competitor(
        client, headers, "First", "https://first.example.com"
    )
    assert first.status_code == 201

    second = await _add_competitor(
        client, headers, "Second", "https://second.example.com"
    )
    assert second.status_code == 201

    third = await _add_competitor(
        client, headers, "Third", "https://third.example.com"
    )
    assert third.status_code == 402
    assert "Pro" in third.json()["detail"]
