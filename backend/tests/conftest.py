"""Shared fixtures: real Postgres in a container + migrations applied."""

import os
import subprocess
import sys
from collections.abc import Generator
from pathlib import Path

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from testcontainers.community.postgres import PostgresContainer

POSTGRES_IMAGE = "postgres:16-alpine"

# backend/ — the directory containing alembic.ini
BACKEND_DIR = Path(__file__).resolve().parent.parent

# app.config creates Settings() at import time; tests need env vars set
# before any app module is imported. Values are placeholders — real
# DATABASE_URL comes from the container, LLM calls are mocked in tests.
os.environ.setdefault("DATABASE_URL", "postgresql+psycopg://placeholder@localhost:5432/placeholder")
os.environ.setdefault("AI_BASE_URL", "https://llm.example.com/v1")
os.environ.setdefault("AI_API_KEY", "sk-test")
os.environ.setdefault("AI_MODEL", "test-model")
os.environ.setdefault("AI_PROVIDER", "openai")
os.environ.setdefault("JWT_SECRET", "test-secret")
# Many tests POST /check several times in a row; the manual-check
# cooldown (anti cost-DoS) would 429 them. Off in tests.
os.environ.setdefault("MANUAL_CHECK_COOLDOWN_SECONDS", "0")


@pytest.fixture(scope="session")
def database_url() -> Generator[str, None, None]:
    """Start a throwaway Postgres container; yield its connection URL."""
    with PostgresContainer(POSTGRES_IMAGE) as postgres:
        # testcontainers returns a psycopg2-style URL; use psycopg (v3) driver.
        yield postgres.get_connection_url().replace(
            "postgresql+psycopg2://", "postgresql+psycopg://"
        )


@pytest.fixture(scope="session")
def migrated_engine(database_url: str):
    """Engine against the container with all migrations applied via alembic."""
    subprocess.run(
        [sys.executable, "-m", "alembic", "upgrade", "head"],
        check=True,
        cwd=BACKEND_DIR,
        env={**os.environ, "DATABASE_URL": database_url},
    )
    engine = create_engine(database_url)
    yield engine
    engine.dispose()


@pytest.fixture
def db(migrated_engine) -> Generator[Session, None, None]:
    """Per-test session; each test runs inside a transaction that is rolled back."""
    connection = migrated_engine.connect()
    transaction = connection.begin()
    session = Session(bind=connection, expire_on_commit=False)

    yield session

    session.close()
    transaction.rollback()
    connection.close()


# --- fetch transport mock ---
# fetch_html's primary path is curl_cffi, which respx cannot intercept.
# Tests that need to control what fetch_html returns monkeypatch the
# transport hook in app.fetcher.client instead. This fixture applies a
# no-op default so an unmocked URL fails loudly instead of hitting the
# real network.

@pytest.fixture
def fake_fetch(monkeypatch):
    """Patch app.fetcher.client.fetch_html with a controllable fake.

    Usage:
        fake_fetch.route("https://x/", html="<html>…</html>")
        fake_fetch.route("https://y/", status=500)      # HTTP error
        fake_fetch.route("https://z/", error=httpx.ConnectError("…"))
        fake_fetch.route("https://c/", challenge=True)  # CF stub -> playwright
        fake_fetch.playwright_html = "<html>rendered</html>"  # what PW returns

    Unrouted URLs raise AssertionError (no accidental real network).
    """
    import httpx

    import app.fetcher.client as client_mod

    routes: dict = {}

    class _FakeFetch:
        playwright_html: str | None = None
        playwright_calls: list[str] = []
        calls: list[str] = []

        def route(
            self,
            url: str,
            html: str = "",
            status: int = 200,
            error: Exception | None = None,
            challenge: bool = False,
        ) -> None:
            routes[url] = {
                "html": html,
                "status": status,
                "error": error,
                "challenge": challenge,
            }

    fake = _FakeFetch()

    async def fake_curl_cffi(url: str) -> str:
        fake.calls.append(url)
        route = routes.get(url)
        if route is None:
            raise AssertionError(
                f"fetch_html called with unrouted URL {url!r} — tests must "
                "not hit the real network"
            )
        if route["error"] is not None:
            raise route["error"]
        if route["status"] >= 400:
            raise httpx.HTTPStatusError(
                f"HTTP {route['status']}",
                request=httpx.Request("GET", url),
                response=httpx.Response(route["status"]),
            )
        if route["challenge"]:
            raise client_mod.ChallengeDetected(url)
        return route["html"]

    async def fake_playwright(url: str) -> str:
        fake.playwright_calls.append(url)
        if fake.playwright_html is None:
            raise RuntimeError("playwright fallback not expected in this test")
        return fake.playwright_html

    # Patch the transports, not fetch_html itself: the real fetch_html
    # orchestration (challenge -> fallback) is exactly what these tests
    # exercise. The SSRF guard resolves real DNS — unroutable test URLs
    # (https://…example.com) would fail it — so the guard is stubbed to
    # a check against the same route table: an unrouted URL still fails
    # loudly, a routed one passes.
    def fake_guard(url: str) -> None:
        if url not in routes:
            raise AssertionError(
                f"fetch_html called with unrouted URL {url!r} — tests must "
                "not hit the real network"
            )

    monkeypatch.setattr(client_mod, "_curl_cffi_fetch", fake_curl_cffi)
    monkeypatch.setattr(client_mod, "_playwright_fetch", fake_playwright)
    monkeypatch.setattr(client_mod, "_guard_url", fake_guard)

    return fake


# --- auth helpers shared by API tests ---

TEST_PASSWORD = "test-password-123"


def make_user(db, email: str, password: str = TEST_PASSWORD):
    """Insert a user with a real password hash; commit so it is visible
    to sessions outside the test transaction (auth endpoints)."""
    from app.auth.security import hash_password
    from app.models import User

    user = User(email=email, password_hash=hash_password(password))
    db.add(user)
    db.commit()
    return user


def auth_header(db, user) -> str:
    """Authorization header value for the given user."""
    from app.auth.security import create_access_token

    return f"Bearer {create_access_token(str(user.id))}"
