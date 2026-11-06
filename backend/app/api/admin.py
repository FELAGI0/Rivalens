"""Admin endpoints: manual triggers, auth required."""

import asyncio
import time

from fastapi import APIRouter, Depends, HTTPException

from app.auth.deps import get_current_user
from app.models import User
from app.scheduler import run_all_competitors

router = APIRouter(prefix="/admin", tags=["admin"])

# Rate limit for POST /admin/run-all: one run alls-check over every
# competitor (N fetches + N LLM calls + N emails), so an authenticated
# user hammering the endpoint is a cost/DoS vector. In-process timestamp
# gate — a restart resets it, which is acceptable for an MVP trigger.
_RUN_ALL_COOLDOWN_SECONDS = 600
_RUN_ALL_MIN_INTERVAL_SECONDS = 60

_run_all_lock = asyncio.Lock()
_last_run_all_at: float = 0.0


@router.post("/run-all")
async def trigger_run_all(
    current_user: User = Depends(get_current_user),
) -> dict:
    """Run a check cycle for all active competitors right now.

    Any authenticated user may trigger it (MVP); a role check can be
    added later. Rate-limited: not more than once per cooldown, and a
    run already in progress makes new calls wait (bounded) instead of
    piling up.
    """
    global _last_run_all_at

    # Bounded wait: if a run is in flight, wait for it (max a minute)
    # rather than starting a parallel duplicate cycle.
    try:
        async with asyncio.timeout(_RUN_ALL_MIN_INTERVAL_SECONDS):
            async with _run_all_lock:
                now = time.monotonic()
                since_last = now - _last_run_all_at
                if since_last < _RUN_ALL_COOLDOWN_SECONDS:
                    retry_in = int(_RUN_ALL_COOLDOWN_SECONDS - since_last)
                    raise HTTPException(
                        status_code=429,
                        detail=(
                            f"Полный прогон уже запускался недавно. "
                            f"Повторите через ~{retry_in // 60 + 1} мин."
                        ),
                    )
                _last_run_all_at = now
                return await run_all_competitors()
    except TimeoutError:
        raise HTTPException(
            status_code=503,
            detail="Прогон всё ещё выполняется, попробуйте позже.",
        )
