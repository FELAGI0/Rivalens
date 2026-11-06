"""End-to-end competitor check pipeline: fetch -> extract -> diff -> summarize."""

import asyncio
import logging
from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.diff import diff_entities
from app.fetcher import extract_entities, fetch_html, hash_html
from app.llm import summarize
from app.models import Change, Competitor, Insight, PageSnapshot, Page, User
from app.notifications import send_insight_email

logger = logging.getLogger(__name__)

# Global concurrency cap: on a 1-CPU VPS a burst of manual checks (or
# manual checks racing the scheduler) would otherwise run N pipelines in
# parallel — N LLM calls, N SMTP sends, and worst of all several
# Playwright Chromium launches at once (300-500 MB RSS each on a 2 GB
# box). Extra runs wait their turn instead of piling on.
MAX_CONCURRENT_CHECKS = 2

# How long a manual check may wait for a semaphore slot before giving
# up. The caller (an HTTP request holding a pooled DB session) must not
# queue indefinitely behind two slow cycles (LLM 60s + SMTP 20s each).
CHECK_QUEUE_TIMEOUT_SECONDS = 30.0

_check_semaphore = asyncio.Semaphore(MAX_CONCURRENT_CHECKS)


class CheckBusyError(Exception):
    """All pipeline slots are busy; the caller should retry later."""


def _pg_advisory_lock_key(competitor_id: UUID | str) -> int:
    """Stable 63-bit int for pg_advisory_xact_lock from the competitor UUID."""
    value = competitor_id.int if isinstance(competitor_id, UUID) else UUID(competitor_id).int
    return value >> 65


async def run_competitor_check(competitor_id: UUID, db: Session) -> dict:
    """Run one check cycle for all active pages of a competitor.

    Returns counts of created rows, the insight id (None if skipped) and
    the number of pages whose fetch failed. Never raises on per-page
    fetch errors or LLM errors.

    Concurrency: the whole cycle runs under a per-competitor advisory
    lock, so a manual "Check now" cannot race the scheduled run and diff
    against the same previous snapshot twice (duplicate changes,
    insights and emails). Globally, at most MAX_CONCURRENT_CHECKS cycles
    run at once (the semaphore is shared across the process); a caller
    waiting longer than CHECK_QUEUE_TIMEOUT_SECONDS gets CheckBusyError.
    The scheduler path catches it like any per-competitor error.
    """
    try:
        async with asyncio.timeout(CHECK_QUEUE_TIMEOUT_SECONDS):
            async with _check_semaphore:
                return await _run_competitor_check_locked(competitor_id, db)
    except TimeoutError as e:
        raise CheckBusyError(
            f"check queue busy for competitor {competitor_id}"
        ) from e


async def _run_competitor_check_locked(competitor_id: UUID, db: Session) -> dict:
    # The lock is tied to the current transaction: it is taken on the
    # session's current transaction and released at commit/rollback, i.e.
    # exactly at the end of this cycle.
    db.execute(func.pg_advisory_xact_lock(_pg_advisory_lock_key(competitor_id)))

    competitor = db.get(Competitor, competitor_id)
    if competitor is None:
        raise LookupError(f"competitor {competitor_id} not found")

    pages = db.scalars(
        select(Page).where(Page.competitor_id == competitor_id, Page.active.is_(True))
    ).all()

    snapshots_created = 0
    changes_created = 0
    pages_failed = 0
    all_changes: list[dict] = []
    new_changes: list[Change] = []
    new_snapshot_times: list[datetime] = []

    for page in pages:
        try:
            html = await fetch_html(page.url)
        except Exception as e:
            # Full exception type + message: on the VPS the plain %s form
            # logged just "httpx.ConnectError" with no details, which made
            # diagnosing the HN fetch failures impossible.
            logger.warning(
                "fetch failed for page %s (%s): %r", page.id, page.url, e
            )
            pages_failed += 1
            continue

        logger.info(
            "extract: page %s fetched %d bytes", page.id, len(html)
        )

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
        logger.info(
            "snapshot: page %s -> snapshot %s (%d headings, %d links, %d prices, hash=%s)",
            page.id,
            new_snap.id,
            len(entities["headings"]),
            len(entities["links"]),
            len(entities["prices"]),
            new_snap.content_hash[:12],
        )

        if prev is not None:
            page_changes = diff_entities(prev.entities, entities)
            logger.info(
                "diff: page %s %s -> %s: %d changes",
                page.id,
                prev.id,
                new_snap.id,
                len(page_changes),
            )
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

    # Commit snapshots + changes BEFORE the slow parts (LLM up to 60s,
    # SMTP up to 20s): no transaction/connection is pinned during them,
    # and a failed LLM call can no longer lose the data. The advisory
    # lock is released here — another check for this competitor (manual
    # or scheduled) may start from this point, but it will see the new
    # snapshots as "previous" and diff correctly.
    db.commit()

    insight_id: UUID | None = None
    summary: str = ""
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
            db.commit()
            insight_id = insight.id
            logger.info(
                "llm: competitor %s -> insight %s (%d changes summarized)",
                competitor.id,
                insight_id,
                len(all_changes),
            )
        except Exception as e:
            # Snapshots + changes are already committed above; a failing
            # LLM must never lose them.
            db.rollback()
            logger.warning("LLM summarization failed: %r", e)

    # Email notification on a new insight. Separated from the LLM block:
    # email errors are caught inside send_insight_email and must never
    # affect the pipeline result.
    if insight_id is not None:
        from app.config import settings

        if settings.email_mode == "instant":
            try:
                user = db.get(User, competitor.user_id)
                if user is not None and user.email:
                    await send_insight_email(
                        to_email=user.email,
                        competitor_name=competitor.name,
                        summary=summary,
                        competitor_id=str(competitor.id),
                    )
            except Exception as e:
                logger.warning("email notification failed: %r", e)
        else:
            # digest mode: the insight is already in the DB; the weekly
            # digest job (scheduler) collects it and emails on Monday.
            logger.info(
                "digest mode: insight %s queued for weekly digest", insight_id
            )
    else:
        logger.info(
            "llm: competitor %s skipped, no changes", competitor.id
        )

    return {
        "snapshots_created": snapshots_created,
        "changes_created": changes_created,
        "pages_failed": pages_failed,
        "insight_id": str(insight_id) if insight_id else None,
        "checked_at": datetime.now(UTC).isoformat(),
    }
