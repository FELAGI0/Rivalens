"""SSRF guard tests: schema-level rejection, fetch-time resolution, rate limits."""

import asyncio
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
        # IPv4-in-IPv6 wrappers must not slip past the literal check
        "http://[::ffff:127.0.0.1]/",
        "http://[::ffff:169.254.169.254]/",
        "http://[::ffff:10.0.0.5]/",
        # 6to4/teredo embedding private IPv4
        "http://[2002:a00:1::]/",  # 6to4 of 10.0.0.1
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
        "http://[2606:2800:220:1:248:1893:25c8:1946]/",  # public IPv6
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

def _fake_getaddrinfo(*addrs: str):
    def fake(hostname, port, family=0, type=0, proto=0, flags=0):
        out = []
        for addr in addrs:
            family = socket.AF_INET6 if ":" in addr else socket.AF_INET
            out.append((family, type, proto, "", (addr, port)))
        return out

    return fake


async def test_resolve_to_private_rejected() -> None:
    with patch(
        "app.fetcher.guard.socket.getaddrinfo",
        side_effect=_fake_getaddrinfo("127.0.0.1"),
    ):
        with pytest.raises(UnsafeURLError, match="blocked"):
            await resolve_and_check_host("rebind.example.com")


async def test_resolve_to_mapped_ipv6_rejected() -> None:
    """::ffff:10.0.0.5 carries a private IPv4 — blocked after unwrap."""
    with patch(
        "app.fetcher.guard.socket.getaddrinfo",
        side_effect=_fake_getaddrinfo("::ffff:10.0.0.5"),
    ):
        with pytest.raises(UnsafeURLError, match="blocked"):
            await resolve_and_check_host("mapped.example.com")


async def test_resolve_to_public_passes() -> None:
    with patch(
        "app.fetcher.guard.socket.getaddrinfo",
        side_effect=_fake_getaddrinfo("93.184.216.34"),
    ):
        ips = await resolve_and_check_host("example.com")
    assert ips == ["93.184.216.34"]


async def test_resolve_mixed_public_and_private_rejected() -> None:
    # DNS rebinding shape: one public + one private address.
    with patch(
        "app.fetcher.guard.socket.getaddrinfo",
        side_effect=_fake_getaddrinfo("93.184.216.34", "10.1.2.3"),
    ):
        with pytest.raises(UnsafeURLError, match="blocked"):
            await resolve_and_check_host("example.com")


async def test_resolve_failure_raises_unsafe() -> None:
    with patch(
        "app.fetcher.guard.socket.getaddrinfo",
        side_effect=socket.gaierror("no such host"),
    ):
        with pytest.raises(UnsafeURLError, match="cannot resolve"):
            await resolve_and_check_host("nonexistent.example.com")


async def test_resolve_timeout_raises_unsafe() -> None:
    """A resolver that never answers fails fast, not hanging the loop."""
    import asyncio as asyncio_mod

    def never_answer(*args, **kwargs):
        import time

        time.sleep(10)  # getaddrinfo runs in an executor thread

    with patch(
        "app.fetcher.guard.socket.getaddrinfo", side_effect=never_answer
    ):
        with pytest.raises(UnsafeURLError, match="timed out"):
            await resolve_and_check_host("slow-dns.example.com", timeout=0.1)


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


# --- admin run-all rate limiting ---

async def test_run_all_cooldown(db, monkeypatch) -> None:
    """Second immediate POST /admin/run-all is a 429; first is 200."""
    import httpx

    import app.api.admin as admin_mod
    from app.db.session import get_session
    from app.main import app
    from app.auth.security import create_access_token

    from tests.conftest import make_user

    user = make_user(db, "run-all@example.com")
    token = create_access_token(str(user.id))
    headers = {"Authorization": f"Bearer {token}"}

    # run_all_competitors would hit the DB+network — stub it out.
    calls: list[int] = []

    async def fake_run_all() -> dict:
        calls.append(1)
        return {"checked": 0, "failed": 0, "results": []}

    monkeypatch.setattr(admin_mod, "run_all_competitors", fake_run_all)
    # Reset the cooldown gate so the test is hermetic.
    monkeypatch.setattr(admin_mod, "_last_run_all_at", 0.0)

    app.dependency_overrides[get_session] = lambda: db
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(
        transport=transport, base_url="http://testserver"
    ) as client:
        first = await client.post("/api/v1/admin/run-all", headers=headers)
        assert first.status_code == 200
        assert calls == [1]

        second = await client.post("/api/v1/admin/run-all", headers=headers)
        assert second.status_code == 429
        # The second call must not have started another run.
        assert calls == [1]
    app.dependency_overrides.pop(get_session, None)


async def test_run_all_requires_auth(db) -> None:
    import httpx

    from app.db.session import get_session
    from app.main import app

    app.dependency_overrides[get_session] = lambda: db
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(
        transport=transport, base_url="http://testserver"
    ) as client:
        response = await client.post("/api/v1/admin/run-all")
        assert response.status_code == 401
    app.dependency_overrides.pop(get_session, None)


# --- pipeline busy timeout ---

async def test_check_busy_error_on_queue_timeout(db, monkeypatch) -> None:
    """When both pipeline slots are held, a queued check fails fast with
    CheckBusyError instead of waiting forever."""
    import asyncio

    from app.pipeline import (
        CheckBusyError,
        CHECK_QUEUE_TIMEOUT_SECONDS,
        _check_semaphore,
        run_competitor_check,
    )

    async def hold_slot():
        async with _check_semaphore:
            await asyncio.sleep(CHECK_QUEUE_TIMEOUT_SECONDS + 5)

    # Occupy all slots.
    holder = asyncio.create_task(hold_slot())
    holder2 = asyncio.create_task(hold_slot())
    await asyncio.sleep(0)  # let the holders grab the semaphore
    try:
        monkeypatch.setattr(
            "app.pipeline.CHECK_QUEUE_TIMEOUT_SECONDS", 0.1
        )
        with pytest.raises(CheckBusyError):
            await run_competitor_check(
                "00000000-0000-0000-0000-000000000000", db
            )
    finally:
        holder.cancel()
        holder2.cancel()
        try:
            await holder
            await holder2
        except asyncio.CancelledError:
            pass



