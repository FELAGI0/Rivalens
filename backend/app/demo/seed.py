"""Demo competitor seeded for every new user.

A brand-new account with an empty list is the worst first impression:
the user sees a blank screen and no idea of what the product does.
Instead, registration plants one pre-filled demo competitor with two
snapshots, three changes and a finished insight — so the first visit
already shows the whole pipeline's output.
"""

import logging
from datetime import UTC, datetime, timedelta
from uuid import UUID

from sqlalchemy.orm import Session

from app.fetcher.hasher import hash_html
from app.models import (
    Change,
    Competitor,
    Insight,
    Page,
    PageKind,
    PageSnapshot,
)

logger = logging.getLogger(__name__)

DEMO_COMPETITOR_NAME = "Демо: Habr"
DEMO_COMPETITOR_URL = "https://habr.com/ru/"

DEMO_SUMMARY = (
    "На главной Habr ротация ленты: ушли статьи про AI-генерацию "
    "ассетов, вместо них вышли тексты про SEO под нейросети и "
    "«Энтропию индустрии». Смещение интереса аудитории — от научпопа "
    "к AI-SEO/LLM-видимости."
)

DEMO_OLD_ENTITIES = {
    "title": "Хабр",
    "headings": ["Старое"],
    "links": [{"href": "/a", "text": "Старое"}],
    "prices": [],
}

DEMO_NEW_ENTITIES = {
    "title": "Хабр",
    "headings": ["Новое"],
    "links": [{"href": "/b", "text": "Новое"}],
    "prices": [],
}


def seed_demo_for_user(user_id: UUID, db: Session) -> None:
    """Create the demo competitor with a ready-made history.

    Called right after registration. Must never break registration:
    the caller wraps this in try/except.
    """
    now = datetime.now(UTC)

    competitor = Competitor(
        user_id=user_id,
        name=DEMO_COMPETITOR_NAME,
        url=DEMO_COMPETITOR_URL,
    )
    db.add(competitor)
    db.flush()

    page = Page(
        competitor_id=competitor.id,
        url=DEMO_COMPETITOR_URL,
        kind=PageKind.LANDING,
    )
    db.add(page)
    db.flush()

    old_snap = PageSnapshot(
        page_id=page.id,
        fetched_at=now - timedelta(hours=1),
        content_hash=hash_html("demo-old"),
        entities=DEMO_OLD_ENTITIES,
    )
    new_snap = PageSnapshot(
        page_id=page.id,
        fetched_at=now,
        content_hash=hash_html("demo-new"),
        entities=DEMO_NEW_ENTITIES,
    )
    db.add(old_snap)
    db.add(new_snap)
    db.flush()

    changes = [
        Change(
            page_id=page.id,
            from_snapshot_id=old_snap.id,
            to_snapshot_id=new_snap.id,
            kind="heading_added",
            payload={"text": "Новое"},
            detected_at=now,
        ),
        Change(
            page_id=page.id,
            from_snapshot_id=old_snap.id,
            to_snapshot_id=new_snap.id,
            kind="link_added",
            payload={"href": "/b", "text": "Новое"},
            detected_at=now,
        ),
        Change(
            page_id=page.id,
            from_snapshot_id=old_snap.id,
            to_snapshot_id=new_snap.id,
            kind="link_removed",
            payload={"href": "/a", "text": "Старое"},
            detected_at=now,
        ),
    ]
    for change in changes:
        db.add(change)
    db.flush()

    insight = Insight(
        competitor_id=competitor.id,
        period_start=old_snap.fetched_at,
        period_end=new_snap.fetched_at,
        summary=DEMO_SUMMARY,
        change_ids=[str(c.id) for c in changes],
        created_at=now,
    )
    db.add(insight)

    # Commit is the caller's business (register commits).
    logger.info("demo competitor seeded for user %s", user_id)
