"""Billing endpoints: plan info and (stub) plan change."""

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.auth.deps import get_current_user
from app.billing.limits import PLAN_LIMITS, competitor_count, plan_name
from app.db.session import get_session
from app.models import User

router = APIRouter(prefix="/billing", tags=["billing"])

VALID_PLANS = ("free", "pro", "business")


class PlanOut(BaseModel):
    plan: str
    competitors_used: int
    competitors_limit: int | None


class PlanChangeIn(BaseModel):
    plan: str


@router.get("/plan", response_model=PlanOut)
def get_plan(
    db: Session = Depends(get_session), user: User = Depends(get_current_user)
) -> PlanOut:
    return PlanOut(
        plan=plan_name(user.plan),
        competitors_used=competitor_count(db, user),
        competitors_limit=PLAN_LIMITS.get(plan_name(user.plan)),
    )


@router.post("/plan", response_model=PlanOut)
def change_plan(
    payload: PlanChangeIn,
    db: Session = Depends(get_session),
    user: User = Depends(get_current_user),
) -> PlanOut:
    """Stub: switch plan without payment. Real billing lands later."""
    if payload.plan not in VALID_PLANS:
        raise HTTPException(status_code=422, detail="unknown plan")

    user.plan = payload.plan
    db.add(user)
    db.commit()
    db.refresh(user)

    return PlanOut(
        plan=plan_name(user.plan),
        competitors_used=competitor_count(db, user),
        competitors_limit=PLAN_LIMITS.get(plan_name(user.plan)),
    )
