"""REST API for competitors: per-user CRUD + manual check + insights/changes."""

from datetime import UTC, datetime, timedelta
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.api.schemas import (
    ChangeOut,
    CheckResult,
    CompetitorCreate,
    CompetitorDetail,
    CompetitorOut,
    InsightOut,
    PageOut,
    PriceChange,
    PriceHistory,
    PricePoint,
)
from app.auth.deps import get_current_user
from app.billing.limits import can_add_competitor, competitor_count, plan_name
from app.db.session import get_session
from app.models import Change, Competitor, Insight, Page, PageKind, PageSnapshot, User
from app.pipeline import run_competitor_check

router = APIRouter(prefix="/competitors")


def _own_competitor_or_404(
    db: Session, competitor_id: UUID, user: User
) -> Competitor:
    competitor = db.get(Competitor, competitor_id)
    if competitor is None or competitor.user_id != user.id:
        # 404 (not 403) to not leak other users' competitor ids
        raise HTTPException(status_code=404, detail="competitor not found")
    return competitor


def _next_check_at() -> datetime | None:
    """When the scheduler's run_all_competitors job fires next, if alive."""
    try:
        from app.scheduler import _scheduler

        if _scheduler is None:
            return None
        job = _scheduler.get_job("run_all_competitors")
        if job is None or job.next_run_time is None:
            return None
        return job.next_run_time
    except Exception:
        # The API must not fail because the scheduler is misbehaving.
        return None


def _snapshot_count(db: Session, competitor_id: UUID) -> int:
    return (
        db.scalar(
            select(func.count())
            .select_from(PageSnapshot)
            .join(Page, PageSnapshot.page_id == Page.id)
            .where(Page.competitor_id == competitor_id)
        )
        or 0
    )


def _last_checked_at(
    db: Session, competitor_id: UUID
) -> datetime | None:
    return db.scalar(
        select(func.max(PageSnapshot.fetched_at))
        .join(Page, PageSnapshot.page_id == Page.id)
        .where(Page.competitor_id == competitor_id)
    )


@router.post("", response_model=CompetitorOut, status_code=201)
def create_competitor(
    payload: CompetitorCreate,
    db: Session = Depends(get_session),
    user: User = Depends(get_current_user),
) -> Competitor:
    if not can_add_competitor(db, user):
        raise HTTPException(
            status_code=402,
            detail=(
                "Лимит Free — 2 конкурента. Перейдите на Pro, "
                "чтобы добавить больше."
            ),
        )

    existing = db.scalars(
        select(Competitor).where(
            Competitor.user_id == user.id, Competitor.name == payload.name
        )
    ).first()
    if existing is not None:
        raise HTTPException(status_code=409, detail="competitor already exists")

    competitor = Competitor(user_id=user.id, name=payload.name, url=payload.url)
    db.add(competitor)
    db.flush()

    # Auto-attach a default landing page so the pipeline works right away.
    if not db.scalars(
        select(Page).where(Page.competitor_id == competitor.id)
    ).first():
        db.add(
            Page(
                competitor_id=competitor.id,
                url=payload.url,
                kind=PageKind.LANDING,
            )
        )

    db.commit()
    db.refresh(competitor)
    return competitor


@router.get("", response_model=list[CompetitorOut])
def list_competitors(
    db: Session = Depends(get_session), user: User = Depends(get_current_user)
) -> list[Competitor]:
    return list(
        db.scalars(select(Competitor).where(Competitor.user_id == user.id)).all()
    )


@router.get("/plan/usage")
def get_plan_usage(
    db: Session = Depends(get_session), user: User = Depends(get_current_user)
) -> dict:
    from app.billing.limits import PLAN_LIMITS

    return {
        "plan": plan_name(user.plan),
        "competitors_used": competitor_count(db, user),
        "competitors_limit": PLAN_LIMITS.get(plan_name(user.plan)),
    }


@router.get("/{competitor_id}", response_model=CompetitorDetail)
def get_competitor(
    competitor_id: UUID,
    db: Session = Depends(get_session),
    user: User = Depends(get_current_user),
) -> CompetitorDetail:
    competitor = _own_competitor_or_404(db, competitor_id, user)

    pages = list(
        db.scalars(
            select(Page)
            .where(Page.competitor_id == competitor_id)
            .order_by(Page.created_at)
        ).all()
    )
    insights = list(
        db.scalars(
            select(Insight)
            .where(Insight.competitor_id == competitor_id)
            .order_by(Insight.created_at.desc())
        ).all()
    )
    return CompetitorDetail(
        competitor=CompetitorOut.model_validate(competitor),
        pages=[PageOut.model_validate(p) for p in pages],
        insights=[InsightOut.model_validate(i) for i in insights],
        total_checks=_snapshot_count(db, competitor_id),
        last_checked_at=_last_checked_at(db, competitor_id),
        next_check_at=_next_check_at(),
    )


@router.delete("/{competitor_id}", status_code=204)
def delete_competitor(
    competitor_id: UUID,
    db: Session = Depends(get_session),
    user: User = Depends(get_current_user),
) -> None:
    """Delete a competitor; pages, snapshots, changes and insights go too.

    Cascades are declared both at DB level (ondelete=CASCADE on every FK
    down the chain) and ORM level (delete-orphan relationships).
    """
    competitor = _own_competitor_or_404(db, competitor_id, user)
    db.delete(competitor)
    db.commit()


@router.post("/{competitor_id}/check", response_model=CheckResult)
async def check_competitor(
    competitor_id: UUID,
    db: Session = Depends(get_session),
    user: User = Depends(get_current_user),
) -> dict:
    _own_competitor_or_404(db, competitor_id, user)

    pages_checked = (
        db.scalar(
            select(func.count())
            .select_from(Page)
            .where(
                Page.competitor_id == competitor_id,
                Page.active.is_(True),
            )
        )
        or 0
    )

    result = await run_competitor_check(competitor_id, db)

    # First check = exactly one snapshot exists after this run: nothing
    # to diff against yet, the next run will produce changes.
    result["pages_checked"] = pages_checked
    result["is_first_check"] = _snapshot_count(db, competitor_id) <= 1
    result["next_check_at"] = _next_check_at()
    return result


@router.get("/{competitor_id}/insights", response_model=list[InsightOut])
def list_insights(
    competitor_id: UUID,
    db: Session = Depends(get_session),
    user: User = Depends(get_current_user),
) -> list[Insight]:
    _own_competitor_or_404(db, competitor_id, user)
    return list(
        db.scalars(
            select(Insight)
            .where(Insight.competitor_id == competitor_id)
            .order_by(Insight.created_at.desc())
        ).all()
    )


@router.get("/{competitor_id}/changes", response_model=list[ChangeOut])
def list_changes(
    competitor_id: UUID,
    limit: int = 50,
    db: Session = Depends(get_session),
    user: User = Depends(get_current_user),
) -> list[Change]:
    _own_competitor_or_404(db, competitor_id, user)
    return list(
        db.scalars(
            select(Change)
            .join(Page, Change.page_id == Page.id)
            .where(Page.competitor_id == competitor_id)
            .order_by(Change.detected_at.desc())
            .limit(limit)
        ).all()
    )


@router.get("/{competitor_id}/price-history", response_model=PriceHistory)
def get_price_history(
    competitor_id: UUID,
    days: int = Query(default=30, ge=1, le=365),
    db: Session = Depends(get_session),
    user: User = Depends(get_current_user),
) -> PriceHistory:
    """Prices per day for the last N days + price changes in the period.

    Points: one per day that has snapshots; prices come from the last
    snapshot of each page on that day (later snapshots win). Changes:
    price_added / price_removed rows with value mapped to from/to.
    """
    _own_competitor_or_404(db, competitor_id, user)
    since = datetime.now(UTC) - timedelta(days=days)

    snapshots = db.scalars(
        select(PageSnapshot)
        .join(Page, PageSnapshot.page_id == Page.id)
        .where(Page.competitor_id == competitor_id, PageSnapshot.fetched_at >= since)
        .order_by(PageSnapshot.fetched_at.asc())
    ).all()

    # day -> page_id -> last snapshot of that page on that day
    last_per_day: dict[str, dict[UUID, PageSnapshot]] = {}
    for snap in snapshots:
        day = snap.fetched_at.strftime("%Y-%m-%d")
        last_per_day.setdefault(day, {})[snap.page_id] = snap

    points = [
        PricePoint(
            date=day,
            prices=sorted(
                {
                    price
                    for snap in pages.values()
                    for price in (snap.entities.get("prices") or [])
                }
            ),
        )
        for day, pages in sorted(last_per_day.items())
    ]

    change_rows = db.scalars(
        select(Change)
        .join(Page, Change.page_id == Page.id)
        .where(
            Page.competitor_id == competitor_id,
            Change.kind.in_(("price_added", "price_removed")),
            Change.detected_at >= since,
        )
        .order_by(Change.detected_at.desc())
    ).all()

    changes = []
    for row in change_rows:
        value = str(row.payload.get("value") or "")
        if row.kind == "price_added":
            from_value, to_value = "", value
        else:
            from_value, to_value = value, ""
        changes.append(
            PriceChange(
                date=row.detected_at.strftime("%Y-%m-%d"),
                from_=from_value,
                to=to_value,
                kind=row.kind,
            )
        )

    return PriceHistory(points=points, changes=changes)
