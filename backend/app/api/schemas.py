"""Pydantic schemas for the /api/v1 API."""

from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.fetcher.guard import MAX_URL_LENGTH, check_url_scheme_and_host


class CompetitorCreate(BaseModel):
    # Length caps: unbounded fields are a trivial resource-exhaustion
    # vector (huge names/URLs stored and logged on every check cycle).
    name: str = Field(min_length=1, max_length=200)
    url: str = Field(min_length=1, max_length=MAX_URL_LENGTH)

    @field_validator("url")
    @classmethod
    def url_is_safe(cls, value: str) -> str:
        """Only safe absolute http(s) URLs reach the fetcher.

        Free-text input like "конкурент.ру" or "test" would otherwise be
        stored as-is and retried by the pipeline forever (and a bogus URL
        used to be the one case that launched Playwright). The same guard
        rejects loopback/private/reserved hosts — the SSRF surface.

        Raises UnsafeURLError (a ValueError subclass) -> FastAPI 422.
        """
        check_url_scheme_and_host(value)
        return value


class CompetitorOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    name: str
    url: str
    active: bool
    created_at: datetime


class PageOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    url: str
    kind: str
    active: bool


class InsightOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    period_start: datetime
    period_end: datetime
    summary: str
    created_at: datetime


class ChangeOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    kind: str
    payload: dict[str, Any]
    detected_at: datetime


class CheckResult(BaseModel):
    snapshots_created: int
    changes_created: int
    insight_id: UUID | None
    checked_at: datetime
    pages_checked: int
    pages_failed: int = 0
    next_check_at: datetime | None = None
    is_first_check: bool


class CompetitorDetail(BaseModel):
    competitor: CompetitorOut
    pages: list[PageOut]
    insights: list[InsightOut]
    total_checks: int
    last_checked_at: datetime | None = None
    next_check_at: datetime | None = None


class PricePoint(BaseModel):
    date: str
    prices: list[str]


class PriceChange(BaseModel):
    date: str
    from_: str = Field(alias="from")
    to: str
    kind: str

    model_config = ConfigDict(populate_by_name=True)


class PriceHistory(BaseModel):
    points: list[PricePoint]
    changes: list[PriceChange]
