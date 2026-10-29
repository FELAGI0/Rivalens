"""REST API for competitors: per-user CRUD + manual check + insights/changes."""

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.schemas import (
    ChangeOut,
    CheckResult,
    CompetitorCreate,
    CompetitorDetail,
    CompetitorOut,
    InsightOut,
    PageOut,
)
from app.auth.deps import get_current_user
from app.db.session import get_session
from app.models import Change, Competitor, Insight, Page, PageKind, User
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


@router.post("", response_model=CompetitorOut, status_code=201)
def create_competitor(
    payload: CompetitorCreate,
    db: Session = Depends(get_session),
    user: User = Depends(get_current_user),
) -> Competitor:
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
    )


@router.post("/{competitor_id}/check", response_model=CheckResult)
async def check_competitor(
    competitor_id: UUID,
    db: Session = Depends(get_session),
    user: User = Depends(get_current_user),
) -> dict:
    _own_competitor_or_404(db, competitor_id, user)

    result = await run_competitor_check(competitor_id, db)
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
