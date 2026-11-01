"""Pipeline tests: fetch -> extract -> diff -> LLM summary, on real Postgres.

Network transport is faked via the `fake_fetch` fixture (conftest.py):
fetch_html is now hybrid curl_cffi + Playwright, and respx can only
intercept httpx, so HTTP-level mocks live in the fixture instead.
"""

import pytest
from sqlalchemy import select

from app.fetcher.client import ChallengeDetected, _is_js_challenge
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


def _make_competitor_with_page(db) -> Page:
    return _make_competitor_with_page_at(db, PAGE_URL)


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


async def test_fetch_creates_snapshot(db, fake_fetch) -> None:
    page = _make_competitor_with_page(db)
    fake_fetch.route(PAGE_URL, html=HTML_V1)

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


async def test_diff_detects_price_change(db, fake_fetch, monkeypatch) -> None:
    page = _make_competitor_with_page(db)
    _mock_llm_success(monkeypatch)

    fake_fetch.route(PAGE_URL, html=HTML_V1)
    first = await run_competitor_check(page.competitor_id, db)
    assert first["changes_created"] == 0

    fake_fetch.route(PAGE_URL, html=HTML_V2)
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


async def test_pipeline_end_to_end(db, fake_fetch, monkeypatch) -> None:
    page = _make_competitor_with_page(db)
    _mock_llm_success(monkeypatch)

    fake_fetch.route(PAGE_URL, html=HTML_V1)
    await run_competitor_check(page.competitor_id, db)

    fake_fetch.route(PAGE_URL, html=HTML_V2)
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


async def test_llm_error_does_not_break_pipeline(db, fake_fetch, monkeypatch) -> None:
    page = _make_competitor_with_page(db)
    _mock_llm_error(monkeypatch)

    fake_fetch.route(PAGE_URL, html=HTML_V1)
    await run_competitor_check(page.competitor_id, db)

    fake_fetch.route(PAGE_URL, html=HTML_V2)
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


async def test_empty_html_creates_snapshot(db, fake_fetch) -> None:
    """Edge case: empty page still produces a valid snapshot with empty entities."""
    page = _make_competitor_with_page(db)
    fake_fetch.route(PAGE_URL, html="")

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


# --- HN-style parsing (real-world messy markup) ---

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


async def test_fetch_hn_real(db, fake_fetch) -> None:
    """HN-style markup extracts title, headings and links correctly."""
    entities = extract_entities(HN_HTML)
    assert entities["title"] == "Hacker News"
    assert entities["headings"] == []  # HN markup has no h1/h2
    hrefs = [link["href"] for link in entities["links"]]
    assert "https://example-ycombinator-com-2.example.com" in hrefs
    assert "vote?for=1" in hrefs
    assert entities["prices"] == []

    # And through the fetch layer: a routed 200 yields the same HTML.
    fake_fetch.route(HN_URL, html=HN_HTML)
    from app.fetcher.client import fetch_html

    html = await fetch_html(HN_URL)
    assert html == HN_HTML
    assert extract_entities(html)["title"] == "Hacker News"


# --- hybrid fetcher: challenge detection and Playwright fallback ---

CF_CHALLENGE_HTML = """
<html><head><title>Just a moment...</title></head>
<body>Enable JavaScript and cookies to continue</body></html>
"""


def test_is_js_challenge() -> None:
    assert _is_js_challenge(CF_CHALLENGE_HTML) is True
    assert _is_js_challenge("Just a moment...") is True
    assert _is_js_challenge("<html>normal page</html>") is False
    assert _is_js_challenge("") is False


async def test_challenge_falls_back_to_playwright(db, fake_fetch) -> None:
    """A CF challenge stub makes fetch_html fall back to Playwright."""
    from app.fetcher.client import fetch_html

    fake_fetch.route(HN_URL, challenge=True)
    fake_fetch.playwright_html = HN_HTML

    html = await fetch_html(HN_URL)

    assert html == HN_HTML
    assert fake_fetch.playwright_calls == [HN_URL]


async def test_pipeline_uses_playwright_snapshot(db, fake_fetch, monkeypatch) -> None:
    """End-to-end: a challenge site still gets a snapshot via Playwright."""
    _mock_llm_success(monkeypatch)

    user = User(email="challenge@example.com", password_hash="not-a-real-hash")
    db.add(user)
    db.flush()
    competitor = Competitor(
        user_id=user.id,
        name="Challenged",
        url="https://challenged.example.com",
    )
    db.add(competitor)
    db.flush()
    page = Page(
        competitor_id=competitor.id,
        url="https://challenged.example.com/",
        kind=PageKind.LANDING,
    )
    db.add(page)
    db.commit()

    fake_fetch.route("https://challenged.example.com/", challenge=True)
    fake_fetch.playwright_html = HTML_V1

    result = await run_competitor_check(competitor.id, db)

    assert result["snapshots_created"] == 1
    assert fake_fetch.playwright_calls == ["https://challenged.example.com/"]
    snapshots = db.scalars(
        select(PageSnapshot).where(PageSnapshot.page_id == page.id)
    ).all()
    assert len(snapshots) == 1
    assert snapshots[0].entities["title"] == "Competitor A — Pricing"


async def test_playwright_not_installed_raises(db, monkeypatch) -> None:
    """Without Playwright the fallback raises a clear error (pipeline logs it)."""
    import sys

    # No fake_fetch here: we call the real _playwright_fetch directly and
    # only simulate the missing playwright package.
    from app.fetcher import client as client_mod

    monkeypatch.setitem(sys.modules, "playwright", None)
    monkeypatch.setitem(sys.modules, "playwright.async_api", None)

    with pytest.raises(RuntimeError, match="not installed"):
        await client_mod._playwright_fetch(HN_URL)


@pytest.mark.integration
async def test_pipeline_with_real_fetch(db) -> None:
    """Integration: a live fetch of https://example.com (no mock).

    Skipped when the network is unavailable (sandboxed CI, offline dev).
    """
    import httpx

    try:
        response = await httpx.AsyncClient(
            timeout=10.0,
            headers={"User-Agent": "Rivalens-test"},
            follow_redirects=True,
        ).get("https://example.com")
        response.raise_for_status()
    except httpx.HTTPError:
        pytest.skip("no network access to https://example.com")

    page = _make_competitor_with_page_at(db, "https://example.com")
    result = await run_competitor_check(page.competitor_id, db)

    assert result["snapshots_created"] == 1
    snapshots = db.scalars(
        select(PageSnapshot).where(PageSnapshot.page_id == page.id)
    ).all()
    assert len(snapshots) == 1
    assert snapshots[0].entities["title"] == "Example Domain"
