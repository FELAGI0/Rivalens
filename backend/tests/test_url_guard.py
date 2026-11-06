"""SSRF guard tests: schema-level rejection and fetch-time resolution."""

import ipaddress
import socket
from unittest.mock import patch

import pytest

from app.fetcher.guard import (
    UnsafeURLError,
    check_url_scheme_and_host,
    resolve_and_check_host,
)


# --- schema-level (CompetitorCreate) ---

@pytest.mark.parametrize(
    "url",
    [
        "http://127.0.0.1/",
        "http://localhost/",
        "https://10.0.0.1/pricing",
        "https://192.168.1.1/",
        "http://169.254.169.254/latest/meta-data",  # cloud metadata
        "http://[::1]/",
        "https://example.com:8080/",  # bad port
        "ftp://example.com/",
        "not a url",
    ],
)
def test_unsafe_urls_rejected_at_schema(url: str) -> None:
    with pytest.raises(ValueError):
        check_url_scheme_and_host(url)


@pytest.mark.parametrize(
    "url",
    [
        "https://example.com/",
        "http://example.com/pricing",
        "https://example.com:443/",
        "http://example.com:80/",
    ],
)
def test_safe_urls_pass_schema(url: str) -> None:
    check_url_scheme_and_host(url)


def test_url_length_cap() -> None:
    long_url = "https://example.com/" + "a" * 2100
    with pytest.raises(ValueError, match="too long"):
        check_url_scheme_and_host(long_url)


def test_localhost_subdomain_rejected() -> None:
    with pytest.raises(ValueError):
        check_url_scheme_and_host("https://api.localhost/")


# --- fetch-time (resolve and check every address) ---

def test_resolve_to_private_rejected() -> None:
    # "0x7f.1" style / non-dotted-quad literal IP forms resolve
    # differently per OS; patch getaddrinfo to be deterministic.
    with patch(
        "app.fetcher.guard.socket.getaddrinfo",
        return_value=[
            (socket.AF_INET, socket.SOCK_STREAM, 6, "", ("127.0.0.1", 0))
        ],
    ):
        with pytest.raises(UnsafeURLError, match="blocked"):
            resolve_and_check_host("rebind.example.com")


def test_resolve_to_public_passes() -> None:
    with patch(
        "app.fetcher.guard.socket.getaddrinfo",
        return_value=[
            (socket.AF_INET, socket.SOCK_STREAM, 6, "", ("93.184.216.34", 0))
        ],
    ):
        resolve_and_check_host("example.com")


def test_resolve_mixed_public_and_private_rejected() -> None:
    # DNS rebinding shape: one public + one private address.
    with patch(
        "app.fetcher.guard.socket.getaddrinfo",
        return_value=[
            (socket.AF_INET, socket.SOCK_STREAM, 6, "", ("93.184.216.34", 0)),
            (socket.AF_INET, socket.SOCK_STREAM, 6, "", ("10.1.2.3", 0)),
        ],
    ):
        with pytest.raises(UnsafeURLError, match="blocked"):
            resolve_and_check_host("example.com")


def test_resolve_failure_raises_unsafe() -> None:
    import socket as socket_mod

    with patch(
        "app.fetcher.guard.socket.getaddrinfo",
        side_effect=socket_mod.gaierror("no such host"),
    ):
        with pytest.raises(UnsafeURLError, match="cannot resolve"):
            resolve_and_check_host("nonexistent.example.com")


def test_api_level_rejection() -> None:
    """CompetitorCreate turns UnsafeURLError into a 422 via ValueError."""
    from pydantic import ValidationError

    from app.api.schemas import CompetitorCreate

    with pytest.raises(ValidationError):
        CompetitorCreate(name="X", url="http://169.254.169.254/metadata")

    # The good path still works.
    model = CompetitorCreate(name="X", url="https://example.com/")
    assert model.url == "https://example.com/"


def test_name_length_cap() -> None:
    from pydantic import ValidationError

    from app.api.schemas import CompetitorCreate

    with pytest.raises(ValidationError):
        CompetitorCreate(name="X" * 201, url="https://example.com/")

    with pytest.raises(ValidationError):
        CompetitorCreate(name="", url="https://example.com/")
