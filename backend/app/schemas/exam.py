"""Pydantic request/response schemas for the exam service."""

from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from app.domain.models.exam import BankStatus

# ---------------------------------------------------------------------------
# ExamBank
# ---------------------------------------------------------------------------


class ExamBankCreate(BaseModel):
    title_fr: str = Field(..., min_length=1, max_length=500)
    title_en: str | None = None
    subject: str | None = None
    language: str = "fr"
    passing_score: float = Field(80.0, ge=0.0, le=100.0)


class ExamBankUpdate(BaseModel):
    title_fr: str | None = Field(None, min_length=1, max_length=500)
    title_en: str | None = None
    subject: str | None = None
    language: str | None = None
    passing_score: float | None = Field(None, ge=0.0, le=100.0)
    status: BankStatus | None = None


class ExamBankResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    org_id: uuid.UUID
    created_by: uuid.UUID
    title_fr: str
    title_en: str | None
    subject: str | None
    language: str
    passing_score: float
    status: BankStatus
    generation_task_id: str | None
    generation_error: str | None
    created_at: datetime
    updated_at: datetime
