"""Hybrid HTML fetching: curl_cffi first, Playwright as a JS fallback.

Design for a 2 GB RAM VPS:

- curl_cffi with impersonate="chrome" sends a TLS/HTTP2 fingerprint that
  looks like a real Chrome — cheap, fast, no browser process. It is the
  primary path for every fetch.
- Some sites respond with a JS challenge (Cloudflare "Just a moment...",
  "Enable JavaScript and cookies to continue") that no static client can
  pass. For those — and only those — we fall back to a headless Chromium
  via Playwright. Any other curl_cffi error (404/500, DNS failure, timeout)
  is a permanent or transient failure of the site, not a sign that JS is
  needed: launching Chromium for it would burn ~300-500 MB RSS on a
  2 GB VPS on every check cycle. Chromium is launched per URL, used, and
  closed immediately; never kept running.
- Playwright is an optional dependency: if it (or its browser binaries)
  is not installed, the fallback raises, which the pipeline logs and
  treats like a fetch failure. The curl_cffi path works without it.
"""

import asyncio
import logging

import curl_cffi

logger = logging.getLogger(__name__)

TIMEOUT_SECONDS = 10.0
PLAYWRIGHT_TIMEOUT_SECONDS = 30.0
MAX_ATTEMPTS = 2  # initial attempt + 1 retry, curl_cffi path only
RETRY_DELAY_SECONDS = 2.0

# Realistic browser UA: some sites (news.ycombinator.com among them)
# reject or throttle requests from unknown bot-like agents.
# (curl_cffi with impersonate="chrome" already sends a matching Chrome UA
# and TLS fingerprint; this constant stays for tests and diagnostics.)
USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
)

# Markers of a JS challenge page: the static fetch "succeeded" (HTTP 200)
# but returned a stub that only runs JavaScript.
CHALLENGE_MARKERS = (
    "Just a moment...",
    "cf-challenge",
    "Enable JavaScript and cookies to continue",
    "Enable JavaScript",
)


def _is_js_challenge(html: str) -> bool:
    """Heuristic: does this HTML look like a Cloudflare/JS challenge page?"""
    return any(marker in html for marker in CHALLENGE_MARKERS)


# --- transport indirection for tests ---
# respx (the httpx mocking library used in tests) cannot intercept
# curl_cffi, so tests monkeypatch these two hooks to fake the transports.


async def _curl_cffi_fetch(url: str) -> str:
    """Primary path: curl_cffi with a Chrome TLS fingerprint.

    Retries once on transport errors. Raises on HTTP error statuses
    (after retries) or when the response is a JS challenge stub.
    """
    from curl_cffi.requests import AsyncSession

    last_error: Exception | None = None
    async with AsyncSession(
        impersonate="chrome", timeout=TIMEOUT_SECONDS
    ) as session:
        for attempt in range(1, MAX_ATTEMPTS + 1):
            try:
                response = await session.get(url)
                response.raise_for_status()
                text = response.text
                if _is_js_challenge(text):
                    # Not retried: a challenge is a property of the site,
                    # not a transient failure. Caller decides on fallback.
                    raise ChallengeDetected(url)
                return text
            except ChallengeDetected:
                raise
            except Exception as e:
                last_error = e
                logger.warning(
                    "curl_cffi attempt %d/%d failed for %s: %r",
                    attempt,
                    MAX_ATTEMPTS,
                    url,
                    e,
                )
                if attempt < MAX_ATTEMPTS:
                    await asyncio.sleep(RETRY_DELAY_SECONDS)
    assert last_error is not None
    raise last_error


class ChallengeDetected(Exception):
    """The site returned a JS challenge stub instead of content."""

    def __init__(self, url: str):
        super().__init__(f"JS challenge detected at {url}")
        self.url = url


async def _playwright_fetch(url: str) -> str:
    """Fallback path: render the page in headless Chromium."""
    try:
        from playwright.async_api import async_playwright
    except ImportError as e:
        raise RuntimeError(
            "Playwright is not installed; cannot render JS-heavy pages. "
            'Install with: pip install -e ".[browser]" && playwright install chromium'
        ) from e

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        try:
            page = await browser.new_page()
            await page.goto(url, timeout=PLAYWRIGHT_TIMEOUT_SECONDS)
            # Give SPA-style sites a moment to finish rendering; networkidle
            # can hang on pages with long-polling, so domcontentloaded plus
            # a small settle delay is the safer choice.
            await page.wait_for_load_state("domcontentloaded")
            await page.wait_for_timeout(1000)
            return await page.content()
        finally:
            await browser.close()


async def fetch_html(url: str) -> str:
    """Fetch a page's HTML.

    1. curl_cffi (fast, Chrome fingerprint). A JS challenge stub is not
       accepted as content.
    2. Playwright headless Chromium — only on ChallengeDetected. Other
       curl_cffi errors (HTTP status, DNS, timeout) propagate: retrying
       them in Chromium would just launch a heavy browser to fail again,
       and on a 2 GB VPS that is an OOM risk, not a recovery.

    Raises the curl_cffi error if the primary path fails, the Playwright
    error if the fallback fails.
    """
    try:
        html = await _curl_cffi_fetch(url)
        return html
    except ChallengeDetected:
        logger.info("JS challenge at %s, falling back to Playwright", url)

    html = await _playwright_fetch(url)
    return html


__all__ = ["fetch_html", "ChallengeDetected", "_is_js_challenge"]
