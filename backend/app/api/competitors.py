"""REST API for competitors: CRUD + manual check + insights/changes."""

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
from app.db.session import get_session
from app.models import Change, Competitor, Insight, Page, PageKind, User
from app.pipeline import run_competitor_check

router = APIRouter(prefix="/competitors")

DEFAULT_USER_EMAIL = "demo@rivalens.local"


def get_default_user(db: Session) -> User:
    """Single implicit user (CP3): the first row, created on demand."""
    user = db.scalars(select(User).limit(1)).first()
    if user is None:
        user = User(email=DEFAULT_USER_EMAIL, plan="free")
        db.add(user)
        db.commit()
    return user


def _get_competitor_or_404(db: Session, competitor_id: UUID) -> Competitor:
    competitor = db.get(Competitor, competitor_id)
    if competitor is None:
        raise HTTPException(status_code=404, detail="competitor not found")
    return competitor


@router.post("", response_model=CompetitorOut, status_code=201)
def create_competitor(
    payload: CompetitorCreate, db: Session = Depends(get_session)
) -> Competitor:
    user = get_default_user(db)

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
        page = Page(
            competitor_id=competitor.id,
            url=payload.url,
            kind=PageKind.LANDING,
        )
        db.add(page)

    db.commit()
    db.refresh(competitor)
    return competitor


@router.get("", response_model=list[CompetitorOut])
def list_competitors(db: Session = Depends(get_session)) -> list[Competitor]:
    return list(db.scalars(select(Competitor)).all())


@router.get("/{competitor_id}", response_model=CompetitorDetail)
def get_competitor(
    competitor_id: UUID, db: Session = Depends(get_session)
) -> CompetitorDetail:
    competitor = _get_competitor_or_404(db, competitor_id)

    pages = list(
        db.scalars(
            select(Page).where(Page.competitor_id == competitor_id).order_by(Page.created_at)
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
    competitor_id: UUID, db: Session = Depends(get_session)
) -> dict:
    _get_competitor_or_404(db, competitor_id)

    result = await run_competitor_check(competitor_id, db)
    return result


@router.get("/{competitor_id}/insights", response_model=list[InsightOut])
def list_insights(
    competitor_id: UUID, db: Session = Depends(get_session)
) -> list[Insight]:
    _get_competitor_or_404(db, competitor_id)
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
) -> list[Change]:
    _get_competitor_or_404(db, competitor_id)
    return list(
        db.scalars(
            select(Change)
            .join(Page, Change.page_id == Page.id)
            .where(Page.competitor_id == competitor_id)
            .order_by(Change.detected_at.desc())
            .limit(limit)
        ).all()
    )
