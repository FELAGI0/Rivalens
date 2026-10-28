"""Pydantic schemas for the /api/v1 API."""

from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict


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


class CompetitorDetail(BaseModel):
    competitor: CompetitorOut
    pages: list[PageOut]
    insights: list[InsightOut]
