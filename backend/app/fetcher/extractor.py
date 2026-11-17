"""Extraction of structured entities from raw HTML."""

import json
import re

from bs4 import BeautifulSoup

PRICE_RE = re.compile(r"\d[\d\s]*[₽$€]")

# Selectors tried in order for card-based catalog pages. The first one
# yielding at least CARD_THRESHOLD cards is treated as the product grid.
CARD_SELECTORS = (
    "article.product",
    "div.product-card",
    "li.product",
    "div[class*='product']",
    "div[class*='card']",
)

# Fewer matched cards than this is not a catalog: a product page often has
# a single "product" wrapper, and treating it as a catalog would lose the
# page-level price diff that already works.
CARD_THRESHOLD = 3

# Card title/price/link sub-selectors.
CARD_TITLE_SELECTORS = "h2, h3, h4, [class*='title'], [class*='name']"
CARD_PRICE_SELECTORS = ("[class*='price']", ".price")

MAX_PRODUCTS = 50
MAX_PRODUCT_TITLE = 200


def _jsonld_price(data: dict) -> str:
    """Price text from a Schema.org Product node's offers."""
    offers = data.get("offers")
    if isinstance(offers, list):
        offers = offers[0] if offers else None
    if not isinstance(offers, dict):
        return ""
    price = offers.get("price")
    if price is None:
        price = offers.get("lowPrice")
    if price is None:
        return ""
    currency = offers.get("priceCurrency") or ""
    symbols = {"RUB": "₽", "USD": "$", "EUR": "€"}
    symbol = symbols.get(str(currency).upper(), "")
    return f"{price} {symbol}".strip() if symbol else str(price)


def _jsonld_products(soup: BeautifulSoup) -> list[dict]:
    products: list[dict] = []

    def add(node: object) -> None:
        if not isinstance(node, dict):
            return
        node_type = node.get("@type")
        types = node_type if isinstance(node_type, list) else [node_type]
        if "Product" not in types:
            return
        products.append(
            {
                "title": str(node.get("name") or "").strip()[:MAX_PRODUCT_TITLE],
                "price": _jsonld_price(node),
                "url": str(node.get("url") or ""),
            }
        )

    for script in soup.find_all("script", type="application/ld+json"):
        raw = script.string
        if not raw:
            continue
        try:
            data = json.loads(raw)
        except (ValueError, TypeError):
            # Malformed third-party JSON-LD must never break extraction.
            continue
        if isinstance(data, list):
            for item in data:
                add(item)
        elif isinstance(data, dict):
            if isinstance(data.get("@graph"), list):
                for item in data["@graph"]:
                    add(item)
            else:
                add(data)

    seen: set[str] = set()
    unique: list[dict] = []
    for product in products:
        if not product["title"]:
            continue
        key = f"{product['url']}|{product['title']}"
        if key in seen:
            continue
        seen.add(key)
        unique.append(product)
    return unique


def _card_products(soup: BeautifulSoup) -> list[dict]:
    from bs4 import Tag

    for selector in CARD_SELECTORS:
        cards = soup.select(selector)
        if len(cards) < CARD_THRESHOLD:
            continue

        products: list[dict] = []
        for card in cards:
            title_el = card.select_one(CARD_TITLE_SELECTORS)
            if not isinstance(title_el, Tag):
                continue
            price_el = None
            for price_selector in CARD_PRICE_SELECTORS:
                price_el = card.select_one(price_selector)
                if price_el is not None:
                    break
            if price_el is None:
                continue
            price_match = PRICE_RE.search(price_el.get_text(" "))
            link_el = card.select_one("a[href]")
            products.append(
                {
                    "title": title_el.get_text(strip=True)[:MAX_PRODUCT_TITLE],
                    "price": price_match.group(0) if price_match else "",
                    "url": (
                        str(link_el.get("href"))
                        if isinstance(link_el, Tag) and link_el.get("href")
                        else ""
                    ),
                }
            )
        if len(products) >= CARD_THRESHOLD:
            return products

    return []


def _extract_products(soup: BeautifulSoup) -> list[dict]:
    """Catalog products: JSON-LD Product first, card heuristics as fallback."""
    products = _jsonld_products(soup)
    if not products:
        products = _card_products(soup)
    return products[:MAX_PRODUCTS]


def extract_entities(html: str) -> dict:
    """Parse HTML into title, headings, links, prices and products.

    `prices` stays page-level (every price found on the page) for
    single-product pages; `products` is the per-item view for catalog
    pages, where a page-level price set would produce meaningless diffs.
    """
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
        "products": _extract_products(soup),
    }
