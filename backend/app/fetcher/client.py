"""HTTP fetching of competitor pages (static HTML only)."""

import httpx

TIMEOUT_SECONDS = 10.0
USER_AGENT = "Rivalens/0.1"


async def fetch_html(url: str) -> str:
    """Fetch a page and return its HTML; raise on HTTP errors."""
    async with httpx.AsyncClient(
        timeout=TIMEOUT_SECONDS,
        headers={"User-Agent": USER_AGENT},
        follow_redirects=True,
    ) as client:
        response = await client.get(url)
        response.raise_for_status()
        return response.text
