"""Pipeline tests: fetch -> extract -> diff -> LLM summary, on real Postgres."""

import httpx
import pytest
import respx
from sqlalchemy import select

from app.models import Change, Competitor, Insight, Page, PageKind, PageSnapshot, User
from app.pipeline import run_competitor_check

HTML_V1 = """
<html>
  <head><title>Competitor A — Pricing</title></head>
  <body>
    <h1>Pricing</h1>
    <h2>Basic</h2>
    <a href="/features">Features</a>
    <p>Basic plan costs 990 ₽ per month.</p>
  </body>
</html>
"""

HTML_V2 = """
<html>
  <head><title>Competitor A — Pricing</title></head>
  <body>
    <h1>Pricing</h1>
    <h2>Basic</h2>
    <h2>Enterprise</h2>
    <a href="/features">Features</a>
    <a href="/contacts">Contacts</a>
    <p>Basic plan costs 1490 ₽ per month.</p>
  </body>
</html>
"""

PAGE_URL = "https://competitor-a.example.com/pricing"


class _FakeMessage:
    def __init__(self, content: str):
        self.content = content


class _FakeChoice:
    def __init__(self, content: str):
        self.message = _FakeMessage(content)


class _FakeResponse:
    def __init__(self, content: str):
        self.choices = [_FakeChoice(content)]


def _make_competitor_with_page(db) -> Page:
    user = User(email="pipeline@example.com")
    db.add(user)
    db.flush()
    competitor = Competitor(
        user_id=user.id,
        name="Competitor A",
        url="https://competitor-a.example.com",
    )
    db.add(competitor)
    db.flush()
    page = Page(competitor_id=competitor.id, url=PAGE_URL, kind=PageKind.PRICE)
    db.add(page)
    db.commit()
    return page


def _mock_llm_success(monkeypatch, text: str = "test summary") -> None:
    async def fake_create(self, *args, **kwargs):
        return _FakeResponse(text)

    monkeypatch.setattr(
        "openai.resources.chat.completions.AsyncCompletions.create", fake_create
    )


def _mock_llm_error(monkeypatch) -> None:
    async def fake_create(self, *args, **kwargs):
        raise RuntimeError("LLM is down")

    monkeypatch.setattr(
        "openai.resources.chat.completions.AsyncCompletions.create", fake_create
    )


# The pipeline needs ai_* settings even when the LLM call is mocked.
@pytest.fixture(autouse=True)
def _ai_settings(monkeypatch):
    monkeypatch.setenv("AI_BASE_URL", "https://llm.example.com/v1")
    monkeypatch.setenv("AI_API_KEY", "sk-test")
    monkeypatch.setenv("AI_MODEL", "test-model")
    monkeypatch.setenv("AI_PROVIDER", "openai")


@respx.mock
async def test_fetch_creates_snapshot(db) -> None:
    page = _make_competitor_with_page(db)
    respx.get(PAGE_URL).mock(return_value=httpx.Response(200, text=HTML_V1))

    result = await run_competitor_check(page.competitor_id, db)

    assert result["snapshots_created"] == 1
    assert result["changes_created"] == 0
    assert result["insight_id"] is None

    snapshots = db.scalars(
        select(PageSnapshot).where(PageSnapshot.page_id == page.id)
    ).all()
    assert len(snapshots) == 1

    entities = snapshots[0].entities
    assert entities["title"] == "Competitor A — Pricing"
    assert "Pricing" in entities["headings"]
    assert "Basic" in entities["headings"]
    assert {"href": "/features", "text": "Features"} in entities["links"]
    assert "990 ₽" in entities["prices"]

    content_hash = snapshots[0].content_hash
    assert isinstance(content_hash, str)
    assert len(content_hash) == 64
    int(content_hash, 16)  # must be hex


@respx.mock
async def test_diff_detects_price_change(db, monkeypatch) -> None:
    page = _make_competitor_with_page(db)
    _mock_llm_success(monkeypatch)

    respx.get(PAGE_URL).mock(return_value=httpx.Response(200, text=HTML_V1))
    first = await run_competitor_check(page.competitor_id, db)
    assert first["changes_created"] == 0

    respx.get(PAGE_URL).mock(return_value=httpx.Response(200, text=HTML_V2))
    second = await run_competitor_check(page.competitor_id, db)

    assert second["snapshots_created"] == 1
    assert second["changes_created"] >= 1
    assert second["insight_id"] is not None

    kinds = db.scalars(select(Change.kind).where(Change.page_id == page.id)).all()
    assert "price_added" in kinds
    assert "price_removed" in kinds

    insight = db.scalars(
        select(Insight).where(Insight.competitor_id == page.competitor_id)
    ).all()
    assert len(insight) == 1


@respx.mock
async def test_pipeline_end_to_end(db, monkeypatch) -> None:
    page = _make_competitor_with_page(db)
    _mock_llm_success(monkeypatch)

    respx.get(PAGE_URL).mock(return_value=httpx.Response(200, text=HTML_V1))
    await run_competitor_check(page.competitor_id, db)

    respx.get(PAGE_URL).mock(return_value=httpx.Response(200, text=HTML_V2))
    result = await run_competitor_check(page.competitor_id, db)

    assert result["snapshots_created"] == 1
    assert result["changes_created"] >= 1
    assert result["insight_id"] is not None

    snapshots = db.scalars(
        select(PageSnapshot).where(PageSnapshot.page_id == page.id)
    ).all()
    assert len(snapshots) == 2

    changes = db.scalars(
        select(Change).where(Change.page_id == page.id)
    ).all()
    assert len(changes) >= 1

    insight = db.scalars(
        select(Insight).where(Insight.competitor_id == page.competitor_id)
    ).all()
    assert len(insight) == 1
    assert insight[0].summary == "test summary"
    assert insight[0].summary  # non-empty


@respx.mock
async def test_llm_error_does_not_break_pipeline(db, monkeypatch) -> None:
    page = _make_competitor_with_page(db)
    _mock_llm_error(monkeypatch)

    respx.get(PAGE_URL).mock(return_value=httpx.Response(200, text=HTML_V1))
    await run_competitor_check(page.competitor_id, db)

    respx.get(PAGE_URL).mock(return_value=httpx.Response(200, text=HTML_V2))
    result = await run_competitor_check(page.competitor_id, db)

    assert result["changes_created"] >= 1
    assert result["insight_id"] is None

    snapshots = db.scalars(
        select(PageSnapshot).where(PageSnapshot.page_id == page.id)
    ).all()
    assert len(snapshots) == 2

    changes = db.scalars(
        select(Change).where(Change.page_id == page.id)
    ).all()
    assert len(changes) >= 1

    insights = db.scalars(
        select(Insight).where(Insight.competitor_id == page.competitor_id)
    ).all()
    assert insights == []
