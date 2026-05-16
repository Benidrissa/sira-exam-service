"""Pydantic V2 schemas for proctoring endpoints (E2-2, E2-4, E3-3)."""

from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict

from app.domain.models.proctor import EventSeverity, SessionStatus, SnapshotAnalysis

# ---------------------------------------------------------------------------
# Session
# ---------------------------------------------------------------------------


class StartSessionRequest(BaseModel):
    attempt_id: uuid.UUID


class StartSessionResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    session_id: uuid.UUID
    session_token: str
    expires_in: int = 7200  # seconds


class HeartbeatResponse(BaseModel):
    ok: bool = True
    next_heartbeat_in: int = 30  # seconds


class ConsentRequest(BaseModel):
    consent_given: bool


class ConsentResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    session_id: uuid.UUID
    consent_given: bool
    consent_given_at: datetime | None


# ---------------------------------------------------------------------------
# Snapshot
# ---------------------------------------------------------------------------


class SnapshotUploadUrlResponse(BaseModel):
    upload_url: str
    storage_key: str


class SnapshotRecordedRequest(BaseModel):
    snapshot_id: uuid.UUID
    storage_key: str


class SnapshotRecordedResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    session_id: uuid.UUID
    storage_key: str
    taken_at: datetime
    analysis_status: SnapshotAnalysis


# ---------------------------------------------------------------------------
# Reference frame
# ---------------------------------------------------------------------------


class ReferenceFrameUploadUrlResponse(BaseModel):
    upload_url: str


class ReferenceFrameRecordedRequest(BaseModel):
    storage_key: str


class ReferenceFrameRecordedResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    session_id: uuid.UUID
    reference_frame_key: str


# ---------------------------------------------------------------------------
# Terminate session
# ---------------------------------------------------------------------------


class TerminateSessionRequest(BaseModel):
    reason: str


# ---------------------------------------------------------------------------
# Session summary (read model)
# ---------------------------------------------------------------------------


class ExamSessionResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    attempt_id: uuid.UUID
    user_id: uuid.UUID
    org_id: uuid.UUID
    status: SessionStatus
    lockdown_mode: bool
    phase: str
    started_at: datetime
    ended_at: datetime | None
    last_heartbeat_at: datetime | None
    consecutive_missed_heartbeats: int
    consent_given: bool
    consent_given_at: datetime | None
    reference_frame_key: str | None
    termination_reason: str | None


# ---------------------------------------------------------------------------
# Lockdown events (E3-3)
# ---------------------------------------------------------------------------


class ProctoringEventRequest(BaseModel):
    event_type: str
    severity: EventSeverity = EventSeverity.info
    payload: dict[str, object] | None = None
    occurred_at: datetime | None = None


class ProctoringEventResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    session_id: uuid.UUID
    event_type: str
    severity: EventSeverity
    payload: dict[str, object] | None = None
    occurred_at: datetime


class ProctoringEventBatchRequest(BaseModel):
    events: list[ProctoringEventRequest]


class ProctoringEventBatchResponse(BaseModel):
    recorded: int
    event_ids: list[uuid.UUID]
