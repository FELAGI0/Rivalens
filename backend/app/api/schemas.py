"""Pydantic schemas for the /api/v1 API."""

from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class CompetitorCreate(BaseModel):
    name: str
    url: str


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
