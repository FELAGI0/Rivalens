"""HTTP fetching of competitor pages (static HTML only)."""

import asyncio
import logging

import httpx

logger = logging.getLogger(__name__)

TIMEOUT_SECONDS = 10.0
# Realistic browser User-Agent: some sites (news.ycombinator.com among
# them) reject or throttle requests from unknown bot-like agents.
USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
)
MAX_ATTEMPTS = 2  # initial attempt + 1 retry
RETRY_DELAY_SECONDS = 2.0


async def fetch_html(url: str) -> str:
    """Fetch a page and return its HTML.

    Retries once after RETRY_DELAY_SECONDS on transport errors
    (connect/timeout/read). HTTP error statuses (4xx/5xx) are not
    retried. Raises the last error if all attempts fail.
    """
    async with httpx.AsyncClient(
        timeout=TIMEOUT_SECONDS,
        headers={"User-Agent": USER_AGENT},
        follow_redirects=True,
    ) as client:
        last_error: httpx.RequestError | None = None
        for attempt in range(1, MAX_ATTEMPTS + 1):
            try:
                response = await client.get(url)
                response.raise_for_status()
                return response.text
            except httpx.RequestError as e:
                last_error = e
                logger.warning(
                    "fetch attempt %d/%d failed for %s: %r",
                    attempt,
                    MAX_ATTEMPTS,
                    url,
                    e,
                )
                if attempt < MAX_ATTEMPTS:
                    await asyncio.sleep(RETRY_DELAY_SECONDS)
        assert last_error is not None
        raise last_error
