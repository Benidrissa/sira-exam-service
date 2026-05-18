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
    snapshot_interval_ms: int = 10_000


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
    # E3-9: Edge AI optional fields (backward-compatible, old clients omit these)
    frame_sha256: str | None = None
    edge_verdict: str | None = None
    edge_confidence: float | None = None
    edge_model_version: str | None = None
    is_offline_frame: bool = False
    captured_at: datetime | None = None
    edge_processed: bool = False


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


# ---------------------------------------------------------------------------
# E3-5: Reconnect + offline sync
# ---------------------------------------------------------------------------


class HeartbeatResumeRequest(BaseModel):
    answer_drafts: dict[str, object] | None = None


class HeartbeatResumeResponse(BaseModel):
    ok: bool = True
    session_id: uuid.UUID
    reconnected_at: datetime
    next_heartbeat_in: int = 30


class OfflineFrameUploadUrlItem(BaseModel):
    snapshot_id: uuid.UUID
    taken_at: datetime


class OfflineFrameUploadUrlRequest(BaseModel):
    frames: list[OfflineFrameUploadUrlItem]


class OfflineFrameUploadUrlResponseItem(BaseModel):
    snapshot_id: uuid.UUID
    upload_url: str
    storage_key: str


class OfflineFrameUploadUrlResponse(BaseModel):
    urls: list[OfflineFrameUploadUrlResponseItem]


class OfflineFrameRecordedItem(BaseModel):
    snapshot_id: uuid.UUID
    frame_seq: int = 0
    edge_classification: str = "unknown"
    taken_at: datetime | None = None


class OfflineFrameBatchRecordedRequest(BaseModel):
    frames: list[OfflineFrameRecordedItem]


class OfflineFrameBatchRecordedResponse(BaseModel):
    accepted: int
    snapshot_ids: list[uuid.UUID]


# ---------------------------------------------------------------------------
# E3-10: VLM config + edge result storage
# ---------------------------------------------------------------------------


class VLMModelInfo(BaseModel):
    name: str
    url: str
    sha256: str = ""


class VLMConfigResponse(BaseModel):
    model_version: str
    cdn_base: str
    tier1_models: list[VLMModelInfo] = []
    tier2_model: VLMModelInfo | None = None
    mandatory_sample_rate: float = 0.10


class EdgeResultRequest(BaseModel):
    snapshot_id: uuid.UUID
    captured_at: datetime
    edge_decision: str  # "clean" | "flagged" | "uncertain" | "error"
    edge_confidence: float
    edge_inference_ms: int
    model_version: str
    violation_type: str = "none"



# ---------------------------------------------------------------------------
# E3-15: Identity verification schemas
# ---------------------------------------------------------------------------

class IdentitySelfieUploadUrlResponse(BaseModel):
    upload_url: str
    storage_key: str


class IdentitySelfieRecordedRequest(BaseModel):
    storage_key: str


class IdentityStatusResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    session_id: uuid.UUID
    identity_verified: bool
    identity_status: str | None
    identity_verified_at: datetime | None
