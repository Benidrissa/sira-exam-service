"""Epic 2 data models — proctoring session, snapshots, events, alerts."""

from __future__ import annotations

import enum
import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, Enum, Float, ForeignKey, Integer, Text, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base

# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------


class SessionStatus(str, enum.Enum):
    active = "active"
    disconnected = "disconnected"
    terminated = "terminated"
    expired = "expired"
    completed = "completed"


class SnapshotAnalysis(str, enum.Enum):
    pending = "pending"
    analyzing = "analyzing"
    clean = "clean"
    flagged = "flagged"
    error = "error"


class EventSeverity(str, enum.Enum):
    info = "info"
    low = "low"
    medium = "medium"
    high = "high"
    critical = "critical"


# ---------------------------------------------------------------------------
# Models
# ---------------------------------------------------------------------------


class ExamSession(Base):
    """Proctoring session — 1:1 with ExamAttempt."""

    __tablename__ = "exam_sessions"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    attempt_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("exam_attempts.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
        index=True,
    )
    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False, index=True)
    org_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False, index=True)
    session_token_hash: Mapped[str] = mapped_column(Text, nullable=False, unique=True)
    status: Mapped[SessionStatus] = mapped_column(
        Enum(SessionStatus, name="sessionstatus", create_type=False),
        nullable=False,
        default=SessionStatus.active,
    )
    lockdown_mode: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    phase: Mapped[str] = mapped_column(Text, nullable=False, default="remote")
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    ended_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_heartbeat_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    consecutive_missed_heartbeats: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    disconnected_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    snapshot_interval_ms: Mapped[int] = mapped_column(Integer, nullable=False, default=10_000)
    consent_given: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    consent_given_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    reference_frame_key: Mapped[str | None] = mapped_column(Text, nullable=True)
    termination_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    edge_metadata: Mapped[dict | None] = mapped_column(JSONB, nullable=True)

    # Relationships
    attempt: Mapped[ExamAttempt] = relationship(  # type: ignore[name-defined]  # noqa: F821
        "ExamAttempt", back_populates="session"
    )
    snapshots: Mapped[list[ProctorSnapshot]] = relationship(
        "ProctorSnapshot", back_populates="session", cascade="all, delete-orphan"
    )
    events: Mapped[list[ProctorEvent]] = relationship(
        "ProctorEvent", back_populates="session", cascade="all, delete-orphan"
    )
    alerts: Mapped[list[ProctorAlert]] = relationship(
        "ProctorAlert", back_populates="session", cascade="all, delete-orphan"
    )


class ProctorSnapshot(Base):
    """Webcam snapshot captured during a proctored session."""

    __tablename__ = "proctor_snapshots"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    session_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("exam_sessions.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    storage_key: Mapped[str] = mapped_column(Text, nullable=False)
    taken_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    analysis_status: Mapped[SnapshotAnalysis] = mapped_column(
        Enum(SnapshotAnalysis, name="snapshotanalysis", create_type=False),
        nullable=False,
        default=SnapshotAnalysis.pending,
    )
    analysis_result: Mapped[dict[str, object] | None] = mapped_column(JSONB, nullable=True)
    violation_detected: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    violation_type: Mapped[str | None] = mapped_column(Text, nullable=True)
    confidence: Mapped[float | None] = mapped_column(Float, nullable=True)

    # E3-9: Edge AI metadata
    frame_sha256: Mapped[str | None] = mapped_column(Text, nullable=True)
    edge_verdict: Mapped[str | None] = mapped_column(Text, nullable=True)
    edge_confidence: Mapped[float | None] = mapped_column(Float, nullable=True)
    edge_model_version: Mapped[str | None] = mapped_column(Text, nullable=True)
    is_offline_frame: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    captured_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    integrity_check_passed: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    integrity_failure_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    edge_processed: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    session: Mapped[ExamSession] = relationship("ExamSession", back_populates="snapshots")


class ProctorEvent(Base):
    """Audit log entry for a proctored session."""

    __tablename__ = "proctor_events"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    session_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("exam_sessions.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    event_type: Mapped[str] = mapped_column(Text, nullable=False)
    severity: Mapped[EventSeverity] = mapped_column(
        Enum(EventSeverity, name="eventseverity", create_type=False),
        nullable=False,
        default=EventSeverity.info,
    )
    payload: Mapped[dict[str, object] | None] = mapped_column(JSONB, nullable=True)
    occurred_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    session: Mapped[ExamSession] = relationship("ExamSession", back_populates="events")
    alerts: Mapped[list[ProctorAlert]] = relationship("ProctorAlert", back_populates="event")


class ProctorAlert(Base):
    """Unacknowledged alert for the proctor dashboard."""

    __tablename__ = "proctor_alerts"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    session_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("exam_sessions.id", ondelete="CASCADE"),
        nullable=False,
    )
    event_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("proctor_events.id", ondelete="SET NULL"),
        nullable=True,
    )
    severity: Mapped[EventSeverity] = mapped_column(
        Enum(EventSeverity, name="eventseverity", create_type=False),
        nullable=False,
        default=EventSeverity.info,
    )
    message: Mapped[str] = mapped_column(Text, nullable=False)
    acknowledged: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    acknowledged_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    acknowledged_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    session: Mapped[ExamSession] = relationship("ExamSession", back_populates="alerts")
    event: Mapped[ProctorEvent | None] = relationship("ProctorEvent", back_populates="alerts")


class NetworkGap(Base):
    """Forensic record of a connectivity interruption during a proctored session."""

    __tablename__ = "network_gaps"
    __table_args__ = {"schema": "exam_svc"}

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    session_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("exam_svc.exam_sessions.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    disconnected_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    reconnected_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    duration_seconds: Mapped[int | None] = mapped_column(Integer, nullable=True)
    missed_heartbeat_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    auto_expired: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
