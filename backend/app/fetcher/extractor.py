"""Extraction of structured entities from raw HTML."""

import re

from bs4 import BeautifulSoup

PRICE_RE = re.compile(r"\d[\d\s]*[₽$€]")


def extract_entities(html: str) -> dict:
    """Parse HTML and return exactly four keys: title, headings, links, prices."""
    soup = BeautifulSoup(html, "lxml")

    title_tag = soup.find("title")
    title = title_tag.get_text(strip=True) if title_tag else ""

    headings = [
        h.get_text(strip=True)
        for h in soup.find_all(["h1", "h2"])
        if h.get_text(strip=True)
    ]

    links = [
        {"href": a["href"], "text": a.get_text(strip=True)}
        for a in soup.find_all("a", href=True)
        if a.get_text(strip=True)
    ]

    text = soup.get_text(" ")
    prices = [m.group(0).strip() for m in PRICE_RE.finditer(text)]

    return {
        "title": title,
        "headings": headings,
        "links": links,
        "prices": prices,
    }
