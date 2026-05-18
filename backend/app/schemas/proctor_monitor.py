"""Pydantic V2 schemas for the proctor monitor API — E2-6, E3-8."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict

# ---------------------------------------------------------------------------
# Network gap (offline interval) schema — E3-8
# ---------------------------------------------------------------------------


class NetworkGapSchema(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    session_id: uuid.UUID
    disconnected_at: datetime
    reconnected_at: datetime | None = None
    duration_seconds: int | None = None
    missed_heartbeat_count: int = 0
    auto_expired: bool = False


# ---------------------------------------------------------------------------
# Alert schemas
# ---------------------------------------------------------------------------


class ProctorAlertSchema(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    session_id: uuid.UUID
    severity: str
    message: str
    acknowledged: bool
    acknowledged_by: uuid.UUID | None = None
    acknowledged_at: datetime | None = None
    created_at: datetime


class AcknowledgeAlertRequest(BaseModel):
    acknowledged_by: uuid.UUID


# ---------------------------------------------------------------------------
# Event schemas
# ---------------------------------------------------------------------------


class ProctorEventSchema(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    session_id: uuid.UUID
    event_type: str
    severity: str
    payload: dict[str, Any] | None = None
    created_at: datetime


# ---------------------------------------------------------------------------
# Snapshot schemas
# ---------------------------------------------------------------------------


class ProctorSnapshotSchema(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    session_id: uuid.UUID
    storage_key: str
    analysis_status: str
    violation_detected: bool | None = None
    violation_type: str | None = None
    confidence: float | None = None
    created_at: datetime
    # Enriched at response time — not from DB
    download_url: str | None = None
    # E3-14: Edge AI transparency fields
    edge_verdict: str | None = None
    edge_confidence: float | None = None
    is_offline_frame: bool = False
    integrity_check_passed: bool | None = None


# ---------------------------------------------------------------------------
# Session list (summary)
# ---------------------------------------------------------------------------


class SessionSummarySchema(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    org_id: uuid.UUID
    user_id: uuid.UUID
    exam_attempt_id: uuid.UUID | None = None
    status: str
    started_at: datetime
    ended_at: datetime | None = None
    last_heartbeat_at: datetime | None = None
    consecutive_missed_heartbeats: int
    termination_reason: str | None = None
    # Offline state — E3-8
    disconnected_at: datetime | None = None
    total_offline_duration_s: int | None = None
    offline_event_count: int = 0
    # Enriched at response time
    unacked_alert_count: int = 0
    latest_snapshot_url: str | None = None
    # E3-14: Edge AI coverage
    edge_coverage_pct: float | None = None


# ---------------------------------------------------------------------------
# Session detail (full timeline)
# ---------------------------------------------------------------------------


class SessionDetailSchema(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    org_id: uuid.UUID
    user_id: uuid.UUID
    exam_attempt_id: uuid.UUID | None = None
    status: str
    started_at: datetime
    ended_at: datetime | None = None
    last_heartbeat_at: datetime | None = None
    consecutive_missed_heartbeats: int
    termination_reason: str | None = None
    unacked_alerts: list[ProctorAlertSchema] = []
    recent_events: list[ProctorEventSchema] = []
    recent_snapshots: list[ProctorSnapshotSchema] = []
    network_gaps: list[NetworkGapSchema] = []
    # E3-14: Edge AI coverage
    edge_coverage_pct: float | None = None


# ---------------------------------------------------------------------------
# Terminate session
# ---------------------------------------------------------------------------


class TerminateSessionRequest(BaseModel):
    reason: str = "proctor_terminated"


class TerminateSessionResponse(BaseModel):
    session_id: uuid.UUID
    status: str
    ended_at: datetime
