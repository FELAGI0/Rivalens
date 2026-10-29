"""API tests: competitors CRUD + check + insights, via ASGITransport."""

import httpx
import pytest
import respx

from app.db.session import get_session
from app.main import app

HTML_V1 = """
<html>
  <head><title>Competitor A — Pricing</title></head>
  <body>
    <h1>Pricing</h1>
    <p>Basic plan costs 990 ₽ per month.</p>
  </body>
</html>
"""

HTML_V2 = HTML_V1.replace("990", "1490")

PAGE_URL = "https://competitor-api.example.com/"


class _FakeMessage:
    def __init__(self, content: str):
        self.content = content


class _FakeChoice:
    def __init__(self, content: str):
        self.message = _FakeMessage(content)


class _FakeResponse:
    def __init__(self, content: str):
        self.choices = [_FakeChoice(content)]


def _mock_llm_success(monkeypatch, text: str = "test summary") -> None:
    async def fake_create(self, *args, **kwargs):
        return _FakeResponse(text)

    monkeypatch.setattr(
        "openai.resources.chat.completions.AsyncCompletions.create", fake_create
    )


@pytest.fixture
async def client(db):
    # Route FastAPI's session dependency to the test session bound to
    # the transaction-wrapped connection of the container database.
    app.dependency_overrides[get_session] = lambda: db
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(
        transport=transport, base_url="http://testserver"
    ) as async_client:
        yield async_client
    app.dependency_overrides.pop(get_session, None)


@pytest.fixture
def auth(client, db):
    """A registered user + Authorization header, applied to the client."""
    from tests.conftest import TEST_PASSWORD, make_user

    user = make_user(db, "api-test@example.com", TEST_PASSWORD)
    client.headers["Authorization"] = f"Bearer-test-not-needed"
    # Token created directly (not via /login) to keep tests hermetic.
    from app.auth.security import create_access_token

    token = create_access_token(str(user.id))
    client.headers["Authorization"] = f"Bearer {token}"
    return user


def _create_competitor(client) -> httpx.Response:
    return client.post(
        "/api/v1/competitors",
        json={"name": "Competitor A", "url": PAGE_URL},
    )


async def test_create_competitor(client, db, auth) -> None:
    response = await _create_competitor(client)
    assert response.status_code == 201

    body = response.json()
    assert body["name"] == "Competitor A"
    assert body["url"] == PAGE_URL
    assert body["active"] is True

    # A default landing page is auto-attached.
    detail = (await client.get(f"/api/v1/competitors/{body['id']}")).json()
    assert len(detail["pages"]) == 1
    assert detail["pages"][0]["kind"] == "landing"
    assert detail["pages"][0]["url"] == PAGE_URL


async def test_list_competitors(client, db, auth) -> None:
    await _create_competitor(client)
    await client.post(
        "/api/v1/competitors",
        json={"name": "Competitor B", "url": "https://b.example.com"},
    )

    response = await client.get("/api/v1/competitors")
    assert response.status_code == 200
    assert len(response.json()) == 2


async def test_get_competitor_detail_404(client, db, auth) -> None:
    response = await client.get("/api/v1/competitors/00000000-0000-0000-0000-000000000000")
    assert response.status_code == 404


@respx.mock
async def test_check_endpoint(client, db, auth, monkeypatch) -> None:
    _mock_llm_success(monkeypatch)
    created = (await _create_competitor(client)).json()

    respx.get(PAGE_URL).mock(return_value=httpx.Response(200, text=HTML_V1))
    response = await client.post(f"/api/v1/competitors/{created['id']}/check")
    assert response.status_code == 200
    assert response.json()["snapshots_created"] >= 1

    # Second run with changed content -> changes + insight.
    respx.get(PAGE_URL).mock(return_value=httpx.Response(200, text=HTML_V2))
    response = await client.post(f"/api/v1/competitors/{created['id']}/check")
    body = response.json()
    assert body["snapshots_created"] >= 1
    assert body["changes_created"] >= 1


@respx.mock
async def test_insights_endpoint(client, db, auth, monkeypatch) -> None:
    _mock_llm_success(monkeypatch)
    created = (await _create_competitor(client)).json()

    respx.get(PAGE_URL).mock(return_value=httpx.Response(200, text=HTML_V1))
    await client.post(f"/api/v1/competitors/{created['id']}/check")
    respx.get(PAGE_URL).mock(return_value=httpx.Response(200, text=HTML_V2))
    await client.post(f"/api/v1/competitors/{created['id']}/check")

    response = await client.get(f"/api/v1/competitors/{created['id']}/insights")
    assert response.status_code == 200
    insights = response.json()
    assert len(insights) >= 1
    assert insights[0]["summary"] == "test summary"
