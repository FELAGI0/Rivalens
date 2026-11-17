"""Diff of extracted entities between two snapshots."""

from typing import Any


def _product_key(product: dict) -> str:
    """Stable identity of a catalog product across two snapshots.

    URL is the most reliable key (product pages move in the grid and
    titles get minor text changes); title is the fallback for pages that
    render cards without links.
    """
    url = str(product.get("url") or "").strip()
    if url:
        return f"url:{url}"
    return f"title:{product.get('title') or ''}"


def diff_products(a: dict, b: dict) -> list[dict]:
    """Compare product lists of two snapshots; return product-level changes.

    Kinds: product_added, product_removed, product_price_changed. Ordered
    so that price changes come first (the most actionable signal).
    """
    old_products = a.get("products") or []
    new_products = b.get("products") or []

    old_by_key = {_product_key(p): p for p in old_products}
    new_by_key = {_product_key(p): p for p in new_products}

    price_changes: list[dict[str, Any]] = []
    removed: list[dict[str, Any]] = []
    added: list[dict[str, Any]] = []

    for key, product in new_by_key.items():
        old = old_by_key.get(key)
        title = product.get("title") or ""
        if old is None:
            added.append(
                {
                    "kind": "product_added",
                    "payload": {
                        "title": title,
                        "price": product.get("price") or "",
                        "url": product.get("url") or "",
                    },
                }
            )
            continue
        old_price = old.get("price") or ""
        new_price = product.get("price") or ""
        if old_price != new_price:
            price_changes.append(
                {
                    "kind": "product_price_changed",
                    "payload": {
                        "title": title,
                        "from": old_price,
                        "to": new_price,
                        "url": product.get("url") or "",
                    },
                }
            )

    for key, product in old_by_key.items():
        if key in new_by_key:
            continue
        removed.append(
            {
                "kind": "product_removed",
                "payload": {
                    "title": product.get("title") or "",
                    "price": product.get("price") or "",
                    "url": product.get("url") or "",
                },
            }
        )

    return price_changes + added + removed


def diff_entities(a: dict, b: dict) -> list[dict]:
    """Compare old (a) and new (b) entities; return a flat list of changes.

    Each change is {"kind": str, "payload": dict}. Empty list if identical.

    Catalog pages (both sides extracted products) are compared per
    product. The page-level price set is skipped there: a category page
    has hundreds of prices, so set-diffing them yields noise like
    "+127 000, -105 360" with no product attached.
    """
    changes: list[dict[str, Any]] = []

    if a.get("title") != b.get("title"):
        changes.append(
            {"kind": "title", "payload": {"from": a.get("title"), "to": b.get("title")}}
        )

    old_headings = set(a.get("headings") or [])
    new_headings = set(b.get("headings") or [])
    for text in sorted(new_headings - old_headings):
        changes.append({"kind": "heading_added", "payload": {"text": text}})
    for text in sorted(old_headings - new_headings):
        changes.append({"kind": "heading_removed", "payload": {"text": text}})

    old_links = {link["href"]: link for link in (a.get("links") or [])}
    new_links = {link["href"]: link for link in (b.get("links") or [])}
    for href in sorted(new_links.keys() - old_links.keys()):
        changes.append(
            {"kind": "link_added", "payload": {"href": href, "text": new_links[href]["text"]}}
        )
    for href in sorted(old_links.keys() - new_links.keys()):
        changes.append(
            {"kind": "link_removed", "payload": {"href": href, "text": old_links[href]["text"]}}
        )

    if (a.get("products") or []) or (b.get("products") or []):
        changes.extend(diff_products(a, b))
    else:
        old_prices = set(a.get("prices") or [])
        new_prices = set(b.get("prices") or [])
        for value in sorted(new_prices - old_prices):
            changes.append({"kind": "price_added", "payload": {"value": value}})
        for value in sorted(old_prices - new_prices):
            changes.append({"kind": "price_removed", "payload": {"value": value}})

    return changes
