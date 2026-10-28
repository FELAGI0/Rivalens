"""Shared fixtures: real Postgres in a container + migrations applied."""

import os
import subprocess
from collections.abc import Generator
from pathlib import Path

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from testcontainers.community.postgres import PostgresContainer

POSTGRES_IMAGE = "postgres:16-alpine"

# backend/ — the directory containing alembic.ini
BACKEND_DIR = Path(__file__).resolve().parent.parent


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
        ["alembic", "upgrade", "head"],
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
