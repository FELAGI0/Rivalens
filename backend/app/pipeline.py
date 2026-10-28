"""End-to-end competitor check pipeline: fetch -> extract -> diff -> summarize."""

import logging
from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.diff import diff_entities
from app.fetcher import extract_entities, fetch_html, hash_html
from app.llm import summarize
from app.models import Change, Competitor, Insight, PageSnapshot, Page

logger = logging.getLogger(__name__)


async def run_competitor_check(competitor_id: UUID, db: Session) -> dict:
    """Run one check cycle for all active pages of a competitor.

    Returns counts of created rows and the insight id (None if skipped).
    Never raises on per-page fetch errors or LLM errors.
    """
    competitor = db.get(Competitor, competitor_id)
    if competitor is None:
        raise LookupError(f"competitor {competitor_id} not found")

    pages = db.scalars(
        select(Page).where(Page.competitor_id == competitor_id, Page.active.is_(True))
    ).all()

    snapshots_created = 0
    changes_created = 0
    all_changes: list[dict] = []
    new_changes: list[Change] = []
    new_snapshot_times: list[datetime] = []

    for page in pages:
        try:
            html = await fetch_html(page.url)
        except Exception as e:
            logger.warning("fetch failed for page %s (%s): %s", page.id, page.url, e)
            continue

        # Latest snapshot BEFORE this check — queried before inserting the
        # new one, so equal fetched_at values (server now() is per-transaction)
        # cannot make the new snapshot its own "previous".
        prev = db.scalars(
            select(PageSnapshot)
            .where(PageSnapshot.page_id == page.id)
            .order_by(PageSnapshot.fetched_at.desc(), PageSnapshot.id.desc())
            .limit(1)
        ).first()

        entities = extract_entities(html)
        new_snap = PageSnapshot(
            page_id=page.id,
            content_hash=hash_html(html),
            entities=entities,
        )
        db.add(new_snap)
        db.flush()
        snapshots_created += 1
        new_snapshot_times.append(new_snap.fetched_at)

        if prev is not None:
            page_changes = diff_entities(prev.entities, entities)
            for d in page_changes:
                change = Change(
                    page_id=page.id,
                    from_snapshot_id=prev.id,
                    to_snapshot_id=new_snap.id,
                    kind=d["kind"],
                    payload=d["payload"],
                )
                db.add(change)
                changes_created += 1
                all_changes.append(d)
                new_changes.append(change)
                db.flush()

    insight_id: UUID | None = None
    if all_changes:
        try:
            summary = await summarize(all_changes, competitor.name)
            insight = Insight(
                competitor_id=competitor.id,
                period_start=min(new_snapshot_times),
                period_end=max(new_snapshot_times),
                summary=summary,
                change_ids=[str(c.id) for c in new_changes],
            )
            db.add(insight)
            db.flush()
            insight_id = insight.id
        except Exception as e:
            logger.warning("LLM summarization failed: %s", e)

    db.commit()

    return {
        "snapshots_created": snapshots_created,
        "changes_created": changes_created,
        "insight_id": str(insight_id) if insight_id else None,
        "checked_at": datetime.now(UTC).isoformat(),
    }
