"""Admin endpoints: manual triggers, auth required."""

from fastapi import APIRouter, Depends

from app.auth.deps import get_current_user
from app.models import User
from app.scheduler import run_all_competitors

router = APIRouter(prefix="/admin", tags=["admin"])


@router.post("/run-all")
async def trigger_run_all(
    current_user: User = Depends(get_current_user),
) -> dict:
    """Run a check cycle for all active competitors right now.

    Any authenticated user may trigger it (MVP); a role check can be
    added later.
    """
    return await run_all_competitors()
