"""Scheduled competitor checks via APScheduler (AsyncIOScheduler)."""

import logging
from datetime import UTC, datetime, timedelta

from apscheduler.schedulers.asyncio import AsyncIOScheduler
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
    scheduler.start()
    _scheduler = scheduler
    logger.info(
        "scheduler started, interval=%dh", settings.check_interval_hours
    )


def stop_scheduler() -> None:
    global _scheduler
    if _scheduler is not None:
        _scheduler.shutdown(wait=False)
        _scheduler = None
        logger.info("scheduler stopped")
