"""Scheduler tests: run_all_competitors over active/inactive/failing competitors."""

import httpx
import pytest
import respx
from sqlalchemy import select

from app.auth.security import create_access_token
from app.models import Competitor, Page, PageKind, PageSnapshot, User
from app.scheduler import run_all_competitors

HTML_A = """
<html><head><title>A</title></head>
<body><h1>A</h1><p>990 ₽</p></body></html>
"""
HTML_B = """
<html><head><title>B</title></head>
<body><h1>B</h1><p>490 ₽</p></body></html>
"""

URL_A = "https://comp-a.example.com/"
URL_B = "https://comp-b.example.com/"
URL_C = "https://comp-c.example.com/"


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


def _make_competitor(db, name: str, url: str, active: bool = True) -> Competitor:
    user = db.scalars(select(User).limit(1)).first()
    if user is None:
        user = User(
            email=f"{name.lower()}@example.com",
            password_hash="not-a-real-hash",
        )
        db.add(user)
        db.flush()
    comp = Competitor(user_id=user.id, name=name, url=url, active=active)
    db.add(comp)
    db.flush()
    db.add(Page(competitor_id=comp.id, url=url, kind=PageKind.LANDING))
    db.commit()
    return comp


# run_all_competitors uses its own SessionLocal, not the test session.
# Point it at the same connection so rows created inside the test
# transaction are visible and everything rolls back afterwards.
@pytest.fixture
def session_factory_override(db, monkeypatch):
    from sqlalchemy.orm import Session

    connection = db.get_bind()
    factory = lambda: Session(  # noqa: E731 — minimal local override
        bind=connection, expire_on_commit=False
    )
    monkeypatch.setattr("app.db.session.SessionLocal", factory)
    return factory


async def test_run_all_empty(session_factory_override, fake_fetch) -> None:
    result = await run_all_competitors()

    assert result["checked"] == 0
    assert result["failed"] == 0
    assert result["results"] == []


async def test_run_all_two_competitors(
    db, session_factory_override, monkeypatch, fake_fetch
) -> None:
    _mock_llm_success(monkeypatch)
    comp_a = _make_competitor(db, "Comp A", URL_A)
    comp_b = _make_competitor(db, "Comp B", URL_B)

    fake_fetch.route(URL_A, html=HTML_A)
    fake_fetch.route(URL_B, html=HTML_B)

    result = await run_all_competitors()

    assert result["checked"] == 2
    assert result["failed"] == 0

    for entry in result["results"]:
        assert entry["result"]["snapshots_created"] == 1

    snapshots = db.scalars(select(PageSnapshot)).all()
    assert len(snapshots) == 2

    checked_ids = {entry["competitor_id"] for entry in result["results"]}
    assert checked_ids == {str(comp_a.id), str(comp_b.id)}


async def test_run_all_one_fails(
    db, session_factory_override, monkeypatch, fake_fetch
) -> None:
    _mock_llm_success(monkeypatch)
    comp_a = _make_competitor(db, "Comp A", URL_A)
    comp_b = _make_competitor(db, "Comp B", URL_B)

    fake_fetch.route(URL_A, html="", status=500)
    fake_fetch.route(URL_B, html=HTML_B)

    result = await run_all_competitors()

    # Per-page fetch errors are logged inside run_competitor_check and do not
    # raise, so a 500 on one page yields snapshots_created=0 for that
    # competitor — not a failure. Competitor B is still checked.
    assert result["failed"] == 0
    assert result["checked"] == 2

    by_id = {entry["competitor_id"]: entry for entry in result["results"]}
    assert by_id[str(comp_a.id)]["result"]["snapshots_created"] == 0
    assert by_id[str(comp_b.id)]["result"]["snapshots_created"] == 1


async def test_run_all_inactive_skipped(
    db, session_factory_override, monkeypatch, fake_fetch
) -> None:
    _mock_llm_success(monkeypatch)
    comp_active = _make_competitor(db, "Comp Active", URL_A)
    _make_competitor(db, "Comp Inactive", URL_C, active=False)

    fake_fetch.route(URL_A, html=HTML_A)
    # No route for URL_C: if the inactive competitor were fetched,
    # fake_fetch would raise on the unrouted URL and the test would fail.

    result = await run_all_competitors()

    assert result["checked"] == 1
    assert result["failed"] == 0
    assert len(result["results"]) == 1
    assert result["results"][0]["competitor_id"] == str(comp_active.id)


# --- admin/run-all auth (endpoint tests, need the ASGI client) ---

import httpx as _httpx

from app.db.session import get_session as _get_session
from app.main import app as _app
from tests.conftest import TEST_PASSWORD as _TEST_PASSWORD, make_user as _make_user


@pytest.fixture
async def api_client(db):
    _app.dependency_overrides[_get_session] = lambda: db
    transport = _httpx.ASGITransport(app=_app)
    async with _httpx.AsyncClient(
        transport=transport, base_url="http://testserver"
    ) as async_client:
        yield async_client
    _app.dependency_overrides.pop(_get_session, None)


async def test_run_all_requires_auth(api_client, db) -> None:
    response = await api_client.post("/api/v1/admin/run-all")
    assert response.status_code == 401


@respx.mock
async def test_run_all_with_auth(api_client, db, session_factory_override) -> None:
    user = _make_user(db, "admin-trigger@example.com", _TEST_PASSWORD)
    headers = {"Authorization": f"Bearer {create_access_token(str(user.id))}"}

    response = await api_client.post("/api/v1/admin/run-all", headers=headers)
    assert response.status_code == 200
    body = response.json()
    assert body["checked"] == 0
    assert body["failed"] == 0
