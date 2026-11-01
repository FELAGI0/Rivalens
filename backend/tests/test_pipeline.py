"""Pipeline tests: fetch -> extract -> diff -> LLM summary, on real Postgres."""

import httpx
import pytest
import respx
from sqlalchemy import select

from app.fetcher.client import fetch_html
from app.fetcher.extractor import extract_entities
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
    return _make_competitor_with_page_at(db, PAGE_URL)


def _make_competitor_with_page_at(db, page_url: str) -> Page:
    user = User(email="pipeline@example.com", password_hash="not-a-real-hash")
    db.add(user)
    db.flush()
    competitor = Competitor(
        user_id=user.id,
        name="Competitor A",
        url="https://competitor-a.example.com",
    )
    db.add(competitor)
    db.flush()
    page = Page(competitor_id=competitor.id, url=page_url, kind=PageKind.PRICE)
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


@respx.mock
async def test_empty_html_creates_snapshot(db) -> None:
    """Edge case: empty page still produces a valid snapshot with empty entities."""
    page = _make_competitor_with_page(db)
    respx.get(PAGE_URL).mock(return_value=httpx.Response(200, text=""))

    result = await run_competitor_check(page.competitor_id, db)

    assert result["snapshots_created"] == 1
    assert result["changes_created"] == 0
    assert result["insight_id"] is None

    snapshots = db.scalars(
        select(PageSnapshot).where(PageSnapshot.page_id == page.id)
    ).all()
    assert len(snapshots) == 1
    assert snapshots[0].entities == {
        "title": "",
        "headings": [],
        "links": [],
        "prices": [],
    }


# A few lines of real news.ycombinator.com markup: exercises the parser
# on messy real-world HTML (custom tags, nested links, no prices).
HN_HTML = """
<html><head><title>Hacker News</title></head>
<body>
  <tr><td class="title"><a href="https://example-ycombinator-com-2.example.com" class="titlelink">Some YC story</a></td></tr>
  <tr><td class="subtext"><span class="score">321 points</span></td></tr>
  <tr><td valign="top" class="votelinks"><a id="up_1" href="vote?for=1">...</a></td></tr>
</body></html>
"""

HN_URL = "https://news.ycombinator.com/"


@respx.mock
async def test_fetch_hn_real(db) -> None:
    """HN-style markup extracts title, headings and links correctly."""
    entities = extract_entities(HN_HTML)
    assert entities["title"] == "Hacker News"
    assert entities["headings"] == []  # HN markup has no h1/h2
    hrefs = [link["href"] for link in entities["links"]]
    assert "https://example-ycombinator-com-2.example.com" in hrefs
    assert "vote?for=1" in hrefs
    assert entities["prices"] == []

    # And through the fetch layer: a mocked 200 yields the same HTML.
    respx.get(HN_URL).mock(return_value=httpx.Response(200, text=HN_HTML))
    html = await fetch_html(HN_URL)
    assert html == HN_HTML
    assert extract_entities(html)["title"] == "Hacker News"


@respx.mock
async def test_fetch_retries_on_network_error(db, monkeypatch) -> None:
    """Transport errors are retried once after a delay, then succeed."""
    # Zero the retry delay so the test is fast.
    monkeypatch.setattr("app.fetcher.client.RETRY_DELAY_SECONDS", 0.0)

    # Simulate one transport error, then success. respx side_effect list
    # is consumed per call.
    respx.get(HN_URL).mock(
        side_effect=[
            httpx.ConnectError("connection refused"),
            httpx.Response(200, text=HN_HTML),
        ]
    )

    html = await fetch_html(HN_URL)
    assert html == HN_HTML


@pytest.mark.integration
async def test_pipeline_with_real_fetch(db) -> None:
    """Integration: a live fetch of https://example.com (no mock).

    Skipped when the network is unavailable (sandboxed CI, offline dev).
    """
    try:
        response = await httpx.AsyncClient(
            timeout=10.0,
            headers={"User-Agent": "Rivalens-test"},
            follow_redirects=True,
        ).get("https://example.com")
        response.raise_for_status()
    except httpx.HTTPError:
        pytest.skip("no network access to https://example.com")

    page = _make_competitor_with_page_at(
        db, "https://example.com"
    )
    result = await run_competitor_check(page.competitor_id, db)

    assert result["snapshots_created"] == 1
    snapshots = db.scalars(
        select(PageSnapshot).where(PageSnapshot.page_id == page.id)
    ).all()
    assert len(snapshots) == 1
    assert snapshots[0].entities["title"] == "Example Domain"
