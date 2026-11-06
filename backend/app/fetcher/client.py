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
from urllib.parse import urlsplit

import curl_cffi

from app.fetcher.guard import UnsafeURLError, resolve_and_check_host

logger = logging.getLogger(__name__)

TIMEOUT_SECONDS = 10.0
PLAYWRIGHT_TIMEOUT_SECONDS = 30.0
MAX_ATTEMPTS = 2  # initial attempt + 1 retry, curl_cffi path only
RETRY_DELAY_SECONDS = 2.0
MAX_REDIRECTS = 5  # each hop re-checked through the SSRF guard

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


def _pinned_ips_to_resolve_list(hostname: str, port: int, ips: list[str]) -> list[str]:
    """curl_cffi `dns=` (CURLOPT_RESOLVE) pin format: host:port:ip entries."""
    return [f"{hostname}:{port}:{ip}" for ip in ips]


async def _guard_url(url: str) -> list[str]:
    """Resolve the host and reject private/reserved targets (SSRF).

    Returns validated IP strings for the caller to pin the request to.
    Runs on every fetch, right before the request goes out — and the
    connection is forced to use the validated address (curl: dns= pin),
    closing the TOCTOU gap where libcurl would re-resolve on its own.
    """
    hostname = urlsplit(url).hostname
    if not hostname:
        raise UnsafeURLError(f"no hostname in {url!r}")
    return await resolve_and_check_host(hostname)


async def _curl_cffi_fetch(url: str) -> str:
    """Primary path: curl_cffi with a Chrome TLS fingerprint.

    Retries once on transport errors. Raises on HTTP error statuses
    (after retries) or when the response is a JS challenge stub.
    Redirects are followed manually (MAX_REDIRECTS): automatic following
    would let a public URL 302 into a private one, bypassing the guard.
    Each hop is resolved and checked before it is requested.
    """
    from curl_cffi.requests import AsyncSession

    last_error: Exception | None = None
    current_url = url
    redirects_taken = 0
    async with AsyncSession(
        impersonate="chrome", timeout=TIMEOUT_SECONDS
    ) as session:
        for attempt in range(1, MAX_ATTEMPTS + 1):
            try:
                pinned_ips = await _guard_url(current_url)
                parts = urlsplit(current_url)
                # CURLOPT_RESOLVE: force the connection to the validated
                # address — libcurl must not re-resolve (DNS rebinding
                # between our check and its connect would be the TOCTOU).
                dns_pins = _pinned_ips_to_resolve_list(
                    parts.hostname,
                    parts.port
                    or (443 if parts.scheme == "https" else 80),
                    pinned_ips,
                )
                response = await session.get(
                    current_url, allow_redirects=False, dns=dns_pins
                )
                if response.status_code in (301, 302, 303, 307, 308) and (
                    response.headers.get("location")
                ):
                    if redirects_taken >= MAX_REDIRECTS:
                        raise UnsafeURLError("too many redirects")
                    redirects_taken += 1
                    current_url = _resolve_redirect(
                        current_url, response.headers["location"]
                    )
                    continue
                response.raise_for_status()
                text = response.text
                if _is_js_challenge(text):
                    # Not retried: a challenge is a property of the site,
                    # not a transient failure. Caller decides on fallback.
                    raise ChallengeDetected(url)
                return text
            except (ChallengeDetected, UnsafeURLError):
                raise
            except Exception as e:
                last_error = e
                logger.warning(
                    "curl_cffi attempt %d/%d failed for %s: %r",
                    attempt,
                    MAX_ATTEMPTS,
                    current_url,
                    e,
                )
                if attempt < MAX_ATTEMPTS:
                    await asyncio.sleep(RETRY_DELAY_SECONDS)
    assert last_error is not None
    raise last_error


def _resolve_redirect(base_url: str, location: str) -> str:
    """Join a redirect target against the current URL, keeping it http(s)."""
    from urllib.parse import urljoin

    target = urljoin(base_url, location)
    parts = urlsplit(target)
    if parts.scheme not in ("http", "https"):
        # scheme smuggling via a redirect is refused outright
        raise UnsafeURLError(f"redirect to non-http scheme {parts.scheme!r}")
    return target


class ChallengeDetected(Exception):
    """The site returned a JS challenge stub instead of content."""

    def __init__(self, url: str):
        super().__init__(f"JS challenge detected at {url}")
        self.url = url


async def _playwright_fetch(url: str) -> str:
    """Fallback path: render the page in headless Chromium.

    The URL's host is guard-resolved before goto, and every subrequest
    is intercepted and checked. Residual risk: page.goto itself is
    resolved by Chromium, not pinned to our validated IP — a perfectly
    timed rebinding could still slip the main document through. Full
    mitigation is a network-level egress policy on the VPS; this code
    layer makes the attack window milliseconds instead of hours.
    """
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

            # SSRF guard for the browser too: any subrequest the page
            # makes to a private/reserved host is aborted before it
            # leaves the process (covers meta refresh, fetch() in page
            # scripts, redirect chains Chromium would follow itself).
            # Resolution results are cached per-page: one page can fire
            # dozens of same-host subrequests, and each guard call
            # resolves DNS — a per-host cache avoids the lookup storm.
            _resolved_cache: dict[str, UnsafeURLError | None] = {}

            async def _abort_unsafe(route):
                req = route.request
                host = urlsplit(req.url).hostname
                try:
                    if host:
                        if host in _resolved_cache:
                            cached = _resolved_cache[host]
                            if cached is not None:
                                raise cached
                            await route.continue_()
                            return
                        await resolve_and_check_host(host)
                        _resolved_cache[host] = None
                    await route.continue_()
                except UnsafeURLError as e:
                    if host not in _resolved_cache:
                        _resolved_cache[host] = e
                    logger.warning("playwright blocked unsafe request: %r", e)
                    await route.abort()

            await page.route("**/*", _abort_unsafe)

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

    Raises UnsafeURLError if the URL (or any redirect hop) targets a
    private/reserved network — that is not retried anywhere.
    """
    try:
        html = await _curl_cffi_fetch(url)
        return html
    except ChallengeDetected:
        logger.info("JS challenge at %s, falling back to Playwright", url)

    await _guard_url(url)
    html = await _playwright_fetch(url)
    return html


__all__ = ["fetch_html", "ChallengeDetected", "_is_js_challenge"]
