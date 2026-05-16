"""Proctor monitor API — E2-6. Implements FR-2.6 (proctor dashboard endpoints).

prefix: /api/v1/proctor/monitor
Auth: teacher JWT (require_teacher dep)
"""

from __future__ import annotations

import contextlib
import uuid
from datetime import UTC, datetime

from fastapi import APIRouter, HTTPException, Query, status
from sqlalchemy import func, select

from app.api.deps import DB, TeacherUser
from app.core.redis_client import get_redis
from app.infrastructure.storage import get_exam_storage
from app.schemas.proctor_monitor import (
    AcknowledgeAlertRequest,
    ProctorAlertSchema,
    SessionDetailSchema,
    SessionSummarySchema,
    TerminateSessionRequest,
    TerminateSessionResponse,
)

router = APIRouter(prefix="/proctor/monitor", tags=["proctor-monitor"])


# ---------------------------------------------------------------------------
# GET /sessions
# ---------------------------------------------------------------------------


@router.get("/sessions", response_model=list[SessionSummarySchema])
async def list_sessions(
    db: DB,
    user: TeacherUser,
    org_id: uuid.UUID | None = Query(default=None),
    session_status: str | None = Query(default=None, alias="status"),
) -> list[SessionSummarySchema]:
    """List exam sessions with unacked alert count and latest snapshot URL.

    Filters by org_id (required for non-admin) and optional status.
    """
    from sqlalchemy import select as sa_select

    from app.domain.models.proctor import (  # type: ignore[attr-defined]
        ExamSession,
        ProctorAlert,
        ProctorSnapshot,
    )

    # Non-admin teachers are scoped to their org
    effective_org: uuid.UUID | None = org_id
    if not user.is_admin:
        effective_org = uuid.UUID(user.org_id) if user.org_id else None

    # Correlated subquery: unacked alert count per session
    alert_count_sq = (
        sa_select(func.count(ProctorAlert.id))
        .where(ProctorAlert.session_id == ExamSession.id, ProctorAlert.acknowledged.is_(False))
        .correlate(ExamSession)
        .scalar_subquery()
    )

    # Correlated subquery: latest snapshot storage_key per session
    latest_snap_sq = (
        sa_select(ProctorSnapshot.storage_key)
        .where(ProctorSnapshot.session_id == ExamSession.id)
        .order_by(ProctorSnapshot.taken_at.desc())
        .limit(1)
        .correlate(ExamSession)
        .scalar_subquery()
    )

    stmt = select(
        ExamSession,
        alert_count_sq.label("unacked_count"),
        latest_snap_sq.label("latest_snap_key"),
    )
    if effective_org is not None:
        stmt = stmt.where(ExamSession.org_id == effective_org)
    if session_status is not None:
        stmt = stmt.where(ExamSession.status == session_status)
    stmt = stmt.order_by(ExamSession.started_at.desc()).limit(100)

    result = await db.execute(stmt)
    rows = result.all()

    storage = get_exam_storage()
    out: list[SessionSummarySchema] = []

    for sess, unacked_count, snap_key in rows:
        snap_url: str | None = None
        if snap_key:
            try:
                snap_url = await storage.presigned_get_url(snap_key)
            except Exception:  # noqa: BLE001
                snap_url = None

        schema = SessionSummarySchema.model_validate(sess)
        schema.unacked_alert_count = unacked_count or 0
        schema.latest_snapshot_url = snap_url
        out.append(schema)

    return out


# ---------------------------------------------------------------------------
# GET /sessions/{session_id}
# ---------------------------------------------------------------------------


@router.get("/sessions/{session_id}", response_model=SessionDetailSchema)
async def get_session_detail(
    session_id: uuid.UUID,
    db: DB,
    user: TeacherUser,
) -> SessionDetailSchema:
    """Full session detail: events timeline (last 50), unacked alerts, snapshots (last 10)."""
    from app.domain.models.proctor import (  # type: ignore[attr-defined]
        ExamSession,
        ProctorAlert,
        ProctorEvent,
        ProctorSnapshot,
    )

    session = await db.get(ExamSession, session_id)
    if not session:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Session not found")

    _assert_org_access(user, session.org_id)

    # Unacked alerts
    alert_result = await db.execute(
        select(ProctorAlert)
        .where(
            ProctorAlert.session_id == session_id,
            ProctorAlert.acknowledged.is_(False),
        )
        .order_by(ProctorAlert.created_at.desc())
    )
    unacked_alerts = alert_result.scalars().all()

    # Last 50 events
    event_result = await db.execute(
        select(ProctorEvent)
        .where(ProctorEvent.session_id == session_id)
        .order_by(ProctorEvent.created_at.desc())
        .limit(50)
    )
    events = event_result.scalars().all()

    # Last 10 snapshots with presigned URLs
    snap_result = await db.execute(
        select(ProctorSnapshot)
        .where(ProctorSnapshot.session_id == session_id)
        .order_by(ProctorSnapshot.taken_at.desc())
        .limit(10)
    )
    snaps = snap_result.scalars().all()

    storage = get_exam_storage()
    from app.schemas.proctor_monitor import ProctorSnapshotSchema

    snap_schemas: list[ProctorSnapshotSchema] = []
    for snap in snaps:
        s = ProctorSnapshotSchema.model_validate(snap)
        if snap.storage_key:
            with contextlib.suppress(Exception):
                s.download_url = await storage.presigned_get_url(snap.storage_key)
        snap_schemas.append(s)

    from app.schemas.proctor_monitor import ProctorAlertSchema, ProctorEventSchema

    detail = SessionDetailSchema.model_validate(session)
    detail.unacked_alerts = [ProctorAlertSchema.model_validate(a) for a in unacked_alerts]
    detail.recent_events = [ProctorEventSchema.model_validate(e) for e in events]
    detail.recent_snapshots = snap_schemas
    return detail


# ---------------------------------------------------------------------------
# PATCH /sessions/{session_id}/terminate
# ---------------------------------------------------------------------------


@router.patch("/sessions/{session_id}/terminate", response_model=TerminateSessionResponse)
async def terminate_session(
    session_id: uuid.UUID,
    data: TerminateSessionRequest,
    db: DB,
    user: TeacherUser,
) -> TerminateSessionResponse:
    """Forcibly terminate an active session and publish Redis event."""
    from app.domain.models.proctor import ExamSession, SessionStatus  # type: ignore[attr-defined]

    session = await db.get(ExamSession, session_id)
    if not session:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Session not found")

    _assert_org_access(user, session.org_id)

    if session.status not in (SessionStatus.active,):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Session is already {session.status.value}",
        )

    now = datetime.now(UTC)
    session.status = SessionStatus.terminated  # type: ignore[attr-defined]
    session.ended_at = now
    session.termination_reason = data.reason
    await db.commit()
    await db.refresh(session)

    # Publish termination event to Redis
    import json

    redis = await get_redis()
    await redis.publish(
        f"proctor:session:{session_id}",
        json.dumps(
            {
                "type": "session_terminated",
                "session_id": str(session_id),
                "reason": data.reason,
                "terminated_by": user.user_id,
            }
        ),
    )

    return TerminateSessionResponse(
        session_id=session_id,
        status=session.status.value,
        ended_at=now,
    )


# ---------------------------------------------------------------------------
# GET /sessions/{session_id}/alerts
# ---------------------------------------------------------------------------


@router.get("/sessions/{session_id}/alerts", response_model=list[ProctorAlertSchema])
async def list_session_alerts(
    session_id: uuid.UUID,
    db: DB,
    user: TeacherUser,
) -> list[ProctorAlertSchema]:
    """Return all ProctorAlerts for a session (newest first)."""
    from app.domain.models.proctor import ExamSession, ProctorAlert  # type: ignore[attr-defined]

    session = await db.get(ExamSession, session_id)
    if not session:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Session not found")

    _assert_org_access(user, session.org_id)

    result = await db.execute(
        select(ProctorAlert)
        .where(ProctorAlert.session_id == session_id)
        .order_by(ProctorAlert.created_at.desc())
    )
    alerts = result.scalars().all()
    return [ProctorAlertSchema.model_validate(a) for a in alerts]


# ---------------------------------------------------------------------------
# PATCH /alerts/{alert_id}/acknowledge
# ---------------------------------------------------------------------------


@router.patch("/alerts/{alert_id}/acknowledge", response_model=ProctorAlertSchema)
async def acknowledge_alert(
    alert_id: uuid.UUID,
    data: AcknowledgeAlertRequest,
    db: DB,
    user: TeacherUser,
) -> ProctorAlertSchema:
    """Mark a ProctorAlert as acknowledged."""
    from app.domain.models.proctor import ExamSession, ProctorAlert  # type: ignore[attr-defined]

    alert = await db.get(ProctorAlert, alert_id)
    if not alert:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Alert not found")

    # Check org access via parent session
    session = await db.get(ExamSession, alert.session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Alert or session not found")
    _assert_org_access(user, session.org_id)

    if not alert.acknowledged:
        alert.acknowledged = True
        alert.acknowledged_by = data.acknowledged_by
        alert.acknowledged_at = datetime.now(UTC)
        await db.commit()
        await db.refresh(alert)

    return ProctorAlertSchema.model_validate(alert)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _assert_org_access(user: TeacherUser, resource_org_id: uuid.UUID) -> None:  # type: ignore[valid-type]
    """Raise 403 if a non-admin teacher attempts cross-org access."""
    if user.is_admin:  # type: ignore[union-attr]
        return
    teacher_org = uuid.UUID(user.org_id) if user.org_id else None  # type: ignore[union-attr]
    if teacher_org != resource_org_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access denied: different organisation",
        )
