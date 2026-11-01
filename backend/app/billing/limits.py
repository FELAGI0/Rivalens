"""Plan limits: how many competitors each plan allows."""

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Competitor, User, UserPlan

# None = unlimited
# free=2: one slot for the demo competitor is not enough to feel the
# product — the user must be able to add a real one without upgrading.
PLAN_LIMITS: dict[str, int | None] = {
    "free": 2,
    "pro": 10,
    "business": None,
}


def plan_name(plan: str | UserPlan) -> str:
    """Normalize a plan to its plain string name.

    User.plan is a String column, but a freshly constructed User carries
    the UserPlan enum default, and str(UserPlan.FREE) is "UserPlan.FREE"
    — which would miss PLAN_LIMITS and read as unlimited. Always go
    through .value for enums.
    """
    if isinstance(plan, UserPlan):
        return plan.value
    return str(plan)


def competitor_count(db: Session, user: User) -> int:
    return len(
        db.scalars(
            select(Competitor.id).where(Competitor.user_id == user.id)
        ).all()
    )


def can_add_competitor(db: Session, user: User) -> bool:
    limit = PLAN_LIMITS.get(plan_name(user.plan))
    if limit is None:
        return True
    return competitor_count(db, user) < limit
