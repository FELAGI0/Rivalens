"""Tests for ORM models: relations, defaults, cascade deletes. Real Postgres."""

from datetime import UTC, datetime

from sqlalchemy import select

from app.models import Change, Competitor, Insight, Page, PageKind, PageSnapshot, User


def _make_user(db, email="user@example.com") -> User:
    user = User(email=email)
    db.add(user)
    db.flush()
    return user


def _make_competitor(db, user: User, name="Competitor A") -> Competitor:
    competitor = Competitor(user_id=user.id, name=name, url="https://example.com")
    db.add(competitor)
    db.flush()
    return competitor


def _make_page(db, competitor: Competitor, url="https://example.com/pricing") -> Page:
    page = Page(
        competitor_id=competitor.id,
        url=url,
        kind=PageKind.PRICE,
    )
    db.add(page)
    db.flush()
    return page


def test_user_competitor_page_relations(db) -> None:
    user = _make_user(db)
    competitor = _make_competitor(db, user)
    page = _make_page(db, competitor)

    db.flush()

    loaded_user = db.get(User, user.id)
    assert loaded_user is not None
    assert loaded_user.plan == "free"
    assert [c.name for c in loaded_user.competitors] == ["Competitor A"]

    assert competitor.user_id == user.id
    assert page.competitor_id == competitor.id
    assert competitor.pages[0].id == page.id

    # Defaults are server-side; after flush they are materialized.
    assert user.created_at is not None
    assert competitor.active is True
    assert page.active is True


def test_snapshot_and_change(db) -> None:
    user = _make_user(db)
    competitor = _make_competitor(db, user)
    page = _make_page(db, competitor)

    old_snapshot = PageSnapshot(
        page_id=page.id,
        content_hash="hash-1",
        entities={"prices": {"basic": 100}},
    )
    new_snapshot = PageSnapshot(
        page_id=page.id,
        content_hash="hash-2",
        entities={"prices": {"basic": 120}},
    )
    db.add_all([old_snapshot, new_snapshot])
    db.flush()

    change = Change(
        page_id=page.id,
        from_snapshot_id=old_snapshot.id,
        to_snapshot_id=new_snapshot.id,
        kind="price",
        payload={"field": "basic", "old": 100, "new": 120},
    )
    db.add(change)
    db.flush()

    assert change.id is not None
    assert change.from_snapshot_id == old_snapshot.id
    assert change.to_snapshot_id == new_snapshot.id
    assert change.detected_at is not None
    assert old_snapshot.entities == {"prices": {"basic": 100}}

    snapshots = db.scalars(
        select(PageSnapshot).where(PageSnapshot.page_id == page.id)
    ).all()
    assert {s.content_hash for s in snapshots} == {"hash-1", "hash-2"}


def test_insight(db) -> None:
    user = _make_user(db)
    competitor = _make_competitor(db, user)

    insight = Insight(
        competitor_id=competitor.id,
        period_start=datetime(2025, 10, 1, tzinfo=UTC),
        period_end=datetime(2025, 10, 7, tzinfo=UTC),
        summary="Competitor raised prices across the board.",
        change_ids=[],
    )
    db.add(insight)
    db.flush()

    assert insight.id is not None
    assert insight.change_ids == []
    assert insight.created_at is not None


def test_unique_page_url_per_competitor(db) -> None:
    import pytest
    from sqlalchemy.exc import IntegrityError

    user = _make_user(db)
    competitor = _make_competitor(db, user)
    _make_page(db, competitor, url="https://example.com/pricing")

    duplicate = Page(
        competitor_id=competitor.id,
        url="https://example.com/pricing",
        kind=PageKind.PRICE,
    )
    db.add(duplicate)

    with pytest.raises(IntegrityError):
        db.flush()


def test_delete_user_cascades_to_everything(db) -> None:
    user = _make_user(db)
    competitor = _make_competitor(db, user)
    page = _make_page(db, competitor)

    snapshot = PageSnapshot(page_id=page.id, content_hash="hash-1")
    db.add(snapshot)
    db.flush()

    change = Change(
        page_id=page.id,
        to_snapshot_id=snapshot.id,
        kind="price",
        payload={"field": "basic"},
    )
    db.add(change)
    db.flush()

    insight = Insight(
        competitor_id=competitor.id,
        period_start=datetime(2025, 10, 1, tzinfo=UTC),
        period_end=datetime(2025, 10, 7, tzinfo=UTC),
        summary="summary",
    )
    db.add(insight)
    db.flush()

    change_id = change.id
    snapshot_id = snapshot.id
    competitor_id = competitor.id
    page_id = page.id
    insight_id = insight.id

    db.delete(user)
    db.flush()

    # Rows are deleted in the DB by FK CASCADE, but objects of this session
    # may still sit in the identity map. Expire everything so that db.get()
    # below re-reads from the database instead of serving stale objects.
    db.expire_all()

    assert db.get(User, user.id) is None
    assert db.get(Competitor, competitor_id) is None
    assert db.get(Page, page_id) is None
    assert db.get(PageSnapshot, snapshot_id) is None
    assert db.get(Change, change_id) is None
    assert db.get(Insight, insight_id) is None
