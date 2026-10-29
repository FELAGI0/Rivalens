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
