"""Competitor deletion tests: cascade, ownership 404, auth."""

import httpx
import pytest
from sqlalchemy import select

from app.db.session import get_session
from app.main import app
from app.models import Change, Competitor, Insight, Page, PageSnapshot
from tests.conftest import make_user


@pytest.fixture
async def client(db):
    app.dependency_overrides[get_session] = lambda: db
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(
        transport=transport, base_url="http://testserver"
    ) as async_client:
        yield async_client
    app.dependency_overrides.pop(get_session, None)


async def _auth_header(db, user) -> str:
    from app.auth.security import create_access_token

    return f"Bearer {create_access_token(str(user.id))}"


async def _add_competitor(client, headers, name: str, url: str) -> httpx.Response:
    return await client.post(
        "/api/v1/competitors",
        json={"name": name, "url": url},
        headers=headers,
    )


def _populate_competitor(db, competitor: Competitor) -> None:
    """Give the competitor's existing landing page snapshots, changes, insights.

    POST /competitors already auto-creates the landing page — reuse it,
    the (competitor_id, url) pair is unique.
    """
    from datetime import datetime, timedelta, timezone

    page = db.scalars(
        select(Page).where(Page.competitor_id == competitor.id)
    ).one()
    now = datetime.now(timezone.utc)

    old_snap = PageSnapshot(
        page_id=page.id,
        fetched_at=now - timedelta(hours=1),
        content_hash="aaaa",
        entities={"title": "old"},
    )
    new_snap = PageSnapshot(
        page_id=page.id,
        fetched_at=now,
        content_hash="bbbb",
        entities={"title": "new"},
    )
    db.add_all([old_snap, new_snap])
    db.flush()

    change = Change(
        kind="title",
        payload={"from": "old", "to": "new"},
        page_id=page.id,
        from_snapshot_id=old_snap.id,
        to_snapshot_id=new_snap.id,
        detected_at=now,
    )
    db.add(change)

    insight = Insight(
        competitor_id=competitor.id,
        period_start=old_snap.fetched_at,
        period_end=new_snap.fetched_at,
        summary="summary text",
        change_ids=[str(change.id)],
    )
    db.add(insight)
    db.commit()


async def test_delete_competitor(client, db) -> None:
    """DELETE -> 204; competitor, pages, insights gone."""
    user = make_user(db, "del-owner@example.com")
    headers = {"Authorization": await _auth_header(db, user)}

    created = await _add_competitor(
        client, headers, "HN", "https://news.ycombinator.com"
    )
    assert created.status_code == 201
    competitor_id = created.json()["id"]

    competitor = db.get(Competitor, competitor_id)
    _populate_competitor(db, competitor)

    response = await client.delete(
        f"/api/v1/competitors/{competitor_id}", headers=headers
    )
    assert response.status_code == 204

    assert db.get(Competitor, competitor_id) is None
    assert (
        db.scalars(
            select(Page).where(Page.competitor_id == competitor_id)
        ).all()
        == []
    )
    assert (
        db.scalars(
            select(Insight).where(Insight.competitor_id == competitor_id)
        ).all()
        == []
    )


async def test_delete_competitor_cascades_children(client, db) -> None:
    """Snapshots/changes go with the page; insight with the competitor."""
    from sqlalchemy import func

    user = make_user(db, "del-cascade@example.com")
    headers = {"Authorization": await _auth_header(db, user)}

    created = await _add_competitor(
        client, headers, "Casc", "https://casc.example.com"
    )
    competitor_id = created.json()["id"]
    competitor = db.get(Competitor, competitor_id)
    _populate_competitor(db, competitor)

    # Children exist before the delete.
    assert (
        db.scalar(
            select(func.count()).select_from(Page).where(
                Page.competitor_id == competitor_id
            )
        )
        == 1
    )
    assert (
        db.scalar(
            select(func.count()).select_from(PageSnapshot)
        )
        == 2
    )
    assert db.scalar(select(func.count()).select_from(Change)) == 1
    assert (
        db.scalar(
            select(func.count()).select_from(Insight).where(
                Insight.competitor_id == competitor_id
            )
        )
        == 1
    )

    response = await client.delete(
        f"/api/v1/competitors/{competitor_id}", headers=headers
    )
    assert response.status_code == 204

    assert db.scalar(select(func.count()).select_from(PageSnapshot)) == 0
    assert db.scalar(select(func.count()).select_from(Change)) == 0
    assert db.scalar(select(func.count()).select_from(Insight)) == 0


async def test_delete_competitor_404(client, db) -> None:
    """Another user's competitor or a missing id: 404, nothing deleted."""
    owner = make_user(db, "del-owner2@example.com")
    intruder = make_user(db, "del-intruder@example.com")

    created = await _add_competitor(
        client,
        {"Authorization": await _auth_header(db, owner)},
        "Foreign",
        "https://foreign.example.com",
    )
    competitor_id = created.json()["id"]

    # Intruder tries the owner's competitor.
    response = await client.delete(
        f"/api/v1/competitors/{competitor_id}",
        headers={"Authorization": await _auth_header(db, intruder)},
    )
    assert response.status_code == 404
    assert db.get(Competitor, competitor_id) is not None

    # Missing id entirely.
    import uuid as uuid_mod

    response = await client.delete(
        f"/api/v1/competitors/{uuid_mod.uuid4()}",
        headers={"Authorization": await _auth_header(db, intruder)},
    )
    assert response.status_code == 404


async def test_delete_competitor_requires_auth(client, db) -> None:
    import uuid as uuid_mod

    response = await client.delete(
        f"/api/v1/competitors/{uuid_mod.uuid4()}"
    )
    assert response.status_code == 401
