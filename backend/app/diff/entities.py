"""Diff of extracted entities between two snapshots."""

from typing import Any


def diff_entities(a: dict, b: dict) -> list[dict]:
    """Compare old (a) and new (b) entities; return a flat list of changes.

    Each change is {"kind": str, "payload": dict}. Empty list if identical.
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

    old_prices = set(a.get("prices") or [])
    new_prices = set(b.get("prices") or [])
    for value in sorted(new_prices - old_prices):
        changes.append({"kind": "price_added", "payload": {"value": value}})
    for value in sorted(old_prices - new_prices):
        changes.append({"kind": "price_removed", "payload": {"value": value}})

    return changes
