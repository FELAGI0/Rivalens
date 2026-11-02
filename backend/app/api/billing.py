"""Billing endpoints: plan info, YooKassa checkout and webhook."""

import logging

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.auth.deps import get_current_user
from app.billing.limits import (
    PLAN_LIMITS,
    PLAN_PRICES_RUB,
    competitor_count,
    plan_name,
)
from app.billing.yookassa import YooKassaError, create_payment, verify_payment
from app.db.session import get_session
from app.models import User

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/billing", tags=["billing"])

VALID_PLANS = ("free", "pro", "business")

# Plan hierarchy: index = tier. Downgrade/same via POST /billing/plan,
# upgrade only via checkout (payment).
PLAN_RANK = {"free": 0, "pro": 1, "business": 2}


class PlanOfferOut(BaseModel):
    name: str
    original_price: int
    discount_price: int
    limit: int | None


class PlanOut(BaseModel):
    plan: str
    competitors_used: int
    competitors_limit: int | None
    offers: list[PlanOfferOut] = []


class PlanChangeIn(BaseModel):
    plan: str


class CheckoutIn(BaseModel):
    plan: str


class CheckoutOut(BaseModel):
    confirmation_url: str


@router.get("/plan", response_model=PlanOut)
def get_plan(
    db: Session = Depends(get_session), user: User = Depends(get_current_user)
) -> PlanOut:
    offers = [
        PlanOfferOut(
            name=name,
            original_price=prices["original"],
            discount_price=prices["discount"],
            limit=PLAN_LIMITS.get(name),
        )
        for name, prices in PLAN_PRICES_RUB.items()
    ]
    return PlanOut(
        plan=plan_name(user.plan),
        competitors_used=competitor_count(db, user),
        competitors_limit=PLAN_LIMITS.get(plan_name(user.plan)),
        offers=offers,
    )


@router.post("/plan", response_model=PlanOut)
def change_plan(
    payload: PlanChangeIn,
    db: Session = Depends(get_session),
    user: User = Depends(get_current_user),
) -> PlanOut:
    """Downgrade or re-choose the current plan, free of charge.

    Upgrades go through checkout: POST /billing/plan with a HIGHER
    plan than the user's current one is a 422 — money must move via
    YooKassa before the tier goes up.
    """
    if payload.plan not in VALID_PLANS:
        raise HTTPException(status_code=422, detail="unknown plan")

    if PLAN_RANK[payload.plan] > PLAN_RANK[plan_name(user.plan)]:
        raise HTTPException(
            status_code=422, detail="use checkout for upgrade"
        )

    user.plan = payload.plan
    db.add(user)
    db.commit()
    db.refresh(user)

    return PlanOut(
        plan=plan_name(user.plan),
        competitors_used=competitor_count(db, user),
        competitors_limit=PLAN_LIMITS.get(plan_name(user.plan)),
    )


@router.post("/checkout", response_model=CheckoutOut)
async def checkout(
    payload: CheckoutIn,
    db: Session = Depends(get_session),
    user: User = Depends(get_current_user),
) -> CheckoutOut:
    """Create a YooKassa payment and return the redirect URL.

    The plan is NOT activated here — only after the payment.succeeded
    webhook confirms the money actually arrived.
    """
    if payload.plan not in PLAN_PRICES_RUB:
        raise HTTPException(status_code=422, detail="unknown plan")
    if payload.plan == plan_name(user.plan):
        raise HTTPException(status_code=422, detail="plan already active")

    try:
        result = await create_payment(
            str(user.id), payload.plan, PLAN_PRICES_RUB[payload.plan]["discount"]
        )
    except YooKassaError as e:
        # Payments are core but not critical: log, tell the user, stay up.
        logger.warning("checkout failed for user %s: %r", user.id, e)
        raise HTTPException(status_code=502, detail="payment unavailable")

    return CheckoutOut(confirmation_url=result["confirmation_url"])


@router.post("/webhook")
async def billing_webhook(
    body: dict, db: Session = Depends(get_session)
) -> dict:
    """YooKassa HTTP notification: activate the paid plan.

    No auth: YooKassa's servers call this endpoint. Notifications are
    NOT signed by YooKassa, so the payload alone is never trusted —
    the payment is re-fetched from the YooKassa API and only its
    status and metadata activate the plan.

    Returns 200 for anything ignored (otherwise YooKassa retries for
    24 hours) and 500 on transient verification errors (retry welcome).
    """
    event = body.get("event")
    if event != "payment.succeeded":
        logger.info("webhook ignored: event=%r", event)
        return {"status": "ok"}

    payment = body.get("object") or {}
    metadata = payment.get("metadata") or {}
    user_id = metadata.get("user_id")
    plan = metadata.get("plan")
    payment_id = payment.get("id")

    if not payment_id or not user_id or plan not in VALID_PLANS:
        logger.warning(
            "webhook succeeded event without usable metadata: %r",
            metadata,
        )
        return {"status": "ok"}

    # Verification: trust only the API, never the notification body.
    try:
        verified = await verify_payment(payment_id)
    except YooKassaError as e:
        # Transient API failure: 500 so YooKassa retries the webhook.
        logger.warning("webhook verification failed for %s: %r", payment_id, e)
        raise HTTPException(status_code=500, detail="verification failed")

    if verified.get("status") != "succeeded":
        logger.warning(
            "webhook: payment %s not succeeded (status=%r), skip",
            payment_id,
            verified.get("status"),
        )
        return {"status": "ok"}

    verified_metadata = verified.get("metadata") or {}
    if (
        verified_metadata.get("user_id") != user_id
        or verified_metadata.get("plan") != plan
    ):
        logger.warning(
            "webhook: metadata mismatch for payment %s, skip", payment_id
        )
        return {"status": "ok"}

    user = db.get(User, user_id)
    if user is None:
        logger.warning("webhook for unknown user %r", user_id)
        return {"status": "ok"}

    if plan_name(user.plan) == plan:
        # Idempotency: YooKassa redelivers notifications; the plan is
        # already active, nothing to do.
        logger.info("webhook idempotent replay for user %s", user_id)
        return {"status": "ok"}

    user.plan = plan
    db.add(user)
    db.commit()
    logger.info("user %s upgraded to %s via webhook", user_id, plan)

    return {"status": "ok"}
