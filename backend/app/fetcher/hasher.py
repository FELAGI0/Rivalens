"""Content hashing for snapshots."""

import hashlib


def hash_html(html: str) -> str:
    """SHA-256 hexdigest of the raw HTML."""
    return hashlib.sha256(html.encode("utf-8")).hexdigest()
