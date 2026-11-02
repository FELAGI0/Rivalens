"""Scheduled competitor checks via APScheduler (AsyncIOScheduler)."""

import logging
from datetime import UTC, datetime, timedelta

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger

logger = logging.getLogger(__name__)

_scheduler: AsyncIOScheduler | None = None


async def run_all_competitors() -> dict:
    """Run a check for every active competitor.

    A per-competitor error is logged and counted; the rest continue.
    """
    from sqlalchemy import select

    from app.db.session import SessionLocal
    from app.models import Competitor
    from app.pipeline import run_competitor_check

    db = SessionLocal()
    checked = 0
    failed = 0
    results: list[dict] = []
    try:
        competitors = db.scalars(
            select(Competitor).where(Competitor.active.is_(True))
        ).all()
        for comp in competitors:
            try:
                result = await run_competitor_check(comp.id, db)
                checked += 1
                results.append({"competitor_id": str(comp.id), "result": result})
            except Exception as e:
                logger.warning("check failed for %s: %s", comp.id, e)
                failed += 1
                results.append({"competitor_id": str(comp.id), "error": str(e)})
    finally:
        db.close()
    return {"checked": checked, "failed": failed, "results": results}


async def send_weekly_digests() -> dict:
    """Send one digest email per user with this week's insights.

    Groups insights of the last 7 days by competitor (one item per
    competitor, newest insight per group), skips users with nothing.
    Email errors are swallowed by send_digest_email; a per-user DB
    failure is logged and counted, the rest continue.
    """
    from sqlalchemy import select

    from app.db.session import SessionLocal
    from app.models import Competitor, Insight, User
    from app.notifications import send_digest_email

    db = SessionLocal()
    sent = 0
    skipped = 0
    try:
        week_ago = datetime.now(UTC) - timedelta(days=7)
        users = db.scalars(select(User)).all()
        for user in users:
            try:
                rows = db.execute(
                    select(Insight, Competitor)
                    .join(
                        Competitor, Insight.competitor_id == Competitor.id
                    )
                    .where(
                        Insight.created_at >= week_ago,
                        Competitor.user_id == user.id,
                    )
                    .order_by(Insight.created_at.desc())
                ).all()

                # One digest item per competitor: the newest insight wins.
                seen: set = set()
                items: list[dict] = []
                for insight, comp in rows:
                    if comp.id in seen:
                        continue
                    seen.add(comp.id)
                    items.append(
                        {
                            "competitor_name": comp.name,
                            "summary": insight.summary,
                            "competitor_id": str(comp.id),
                        }
                    )

                if not items:
                    skipped += 1
                    continue

                await send_digest_email(user.email, items)
                sent += 1
            except Exception as e:
                logger.warning(
                    "digest failed for user %s: %r", user.id, e
                )
                skipped += 1
    finally:
        db.close()
    return {"sent": sent, "skipped": skipped}


def start_scheduler() -> None:
    """Start the AsyncIOScheduler: every N hours, first run in 1 minute."""
    global _scheduler
    if _scheduler is not None:
        return

    from app.config import settings

    scheduler = AsyncIOScheduler()
    scheduler.add_job(
        run_all_competitors,
        trigger=IntervalTrigger(hours=settings.check_interval_hours),
        id="run_all_competitors",
        next_run_time=datetime.now(UTC) + timedelta(minutes=1),
        replace_existing=True,
    )
    scheduler.add_job(
        send_weekly_digests,
        trigger=CronTrigger(
            day_of_week=settings.digest_day,
            hour=settings.digest_hour,
        ),
        id="weekly_digest",
        replace_existing=True,
    )
    scheduler.start()
    _scheduler = scheduler
    logger.info(
        "scheduler started, interval=%dh, digest day=%d hour=%d",
        settings.check_interval_hours,
        settings.digest_day,
        settings.digest_hour,
    )


def stop_scheduler() -> None:
    global _scheduler
    if _scheduler is not None:
        _scheduler.shutdown(wait=False)
        _scheduler = None
        logger.info("scheduler stopped")
