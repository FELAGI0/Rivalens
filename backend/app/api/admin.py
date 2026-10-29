"""Admin endpoints: manual triggers (no auth until CP5)."""

from fastapi import APIRouter

from app.scheduler import run_all_competitors

router = APIRouter(prefix="/admin", tags=["admin"])


@router.post("/run-all")
async def trigger_run_all() -> dict:
    """Run a check cycle for all active competitors right now."""
    return await run_all_competitors()
