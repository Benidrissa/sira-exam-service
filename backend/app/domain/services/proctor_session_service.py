"""Proctoring session service — token issuance, heartbeat, alerts (E2-2)."""

from __future__ import annotations

import hashlib
import secrets
import uuid
from datetime import UTC, datetime

import structlog
from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.models.proctor import (
    EventSeverity,
    ExamSession,
    ProctorAlert,
    ProctorEvent,
    SessionStatus,
)

logger = structlog.get_logger(__name__)

# ---------------------------------------------------------------------------
# Alert thresholds — (count_threshold, alert_severity, message_template)
# ---------------------------------------------------------------------------

ALERT_THRESHOLDS: dict[str, tuple[int, EventSeverity, str]] = {
    # fmt: off
    "tab_switch":                 (3,  EventSeverity.medium,   "Tab switch threshold reached ({count}x)"),  # noqa: E501
    "window_blur":                (5,  EventSeverity.low,      "Window focus lost threshold reached ({count}x)"),  # noqa: E501
    "fullscreen_exit":            (2,  EventSeverity.medium,   "Fullscreen exited {count}x during exam"),  # noqa: E501
    "clipboard_access":           (3,  EventSeverity.medium,   "Clipboard access threshold reached ({count}x)"),  # noqa: E501
    "keyboard_shortcut_blocked": (10,  EventSeverity.low,      "Keyboard shortcuts blocked {count}x"),  # noqa: E501
    "screen_capture_attempt":     (1,  EventSeverity.critical, "Screen capture attempted"),
    "devtools_opened":            (1,  EventSeverity.high,     "DevTools opened during exam"),
    "browser_extension_detected": (1,  EventSeverity.high,     "Browser extension detected"),
    "copy_paste_blocked":         (5,  EventSeverity.low,      "Copy/paste blocked {count}x"),
    "context_menu_blocked":      (10,  EventSeverity.info,     "Context menu blocked {count}x"),
    "extended_display_detected":  (1,  EventSeverity.medium,   "Extended display detected"),
    # fmt: on
}


# ---------------------------------------------------------------------------
# Token helpers
# ---------------------------------------------------------------------------


def _hash_token(raw_token: str) -> str:
    return hashlib.sha256(raw_token.encode()).hexdigest()


# ---------------------------------------------------------------------------
# Public service functions
# ---------------------------------------------------------------------------


async def issue_session_token(
    db: AsyncSession,
    *,
    attempt_id: uuid.UUID,
    user_id: uuid.UUID,
    org_id: uuid.UUID,
) -> tuple[ExamSession, str]:
    """Create a new ExamSession and return (session, raw_token).

    The raw token is returned exactly once — the client must store it.
    Raises HTTP 409 if an active session already exists for this attempt.
    """
    # Guard: no duplicate active session
    existing = await db.scalar(
        select(ExamSession).where(
            ExamSession.attempt_id == attempt_id,
            ExamSession.status == SessionStatus.active,
        )
    )
    if existing is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="An active proctoring session already exists for this attempt.",
        )

    raw_token = secrets.token_urlsafe(32)
    token_hash = _hash_token(raw_token)

    session = ExamSession(
        id=uuid.uuid4(),
        attempt_id=attempt_id,
        user_id=user_id,
        org_id=org_id,
        session_token_hash=token_hash,
        status=SessionStatus.active,
    )
    db.add(session)
    await db.commit()
    await db.refresh(session)

    logger.info("session_token_issued", session_id=str(session.id), attempt_id=str(attempt_id))
    return session, raw_token


async def verify_session_token(
    db: AsyncSession,
    *,
    raw_token: str,
) -> ExamSession | None:
    """Return the ExamSession matching the raw token, or None."""
    token_hash = _hash_token(raw_token)
    result: ExamSession | None = await db.scalar(
        select(ExamSession).where(ExamSession.session_token_hash == token_hash)
    )
    return result


async def record_heartbeat(
    db: AsyncSession,
    *,
    session_id: uuid.UUID,
) -> ExamSession:
    """Update last_heartbeat_at and reset consecutive_missed_heartbeats."""
    session = await _get_active_session(db, session_id)
    session.last_heartbeat_at = datetime.now(tz=UTC)
    session.consecutive_missed_heartbeats = 0
    await db.commit()
    await db.refresh(session)
    return session


async def terminate_session(
    db: AsyncSession,
    *,
    session_id: uuid.UUID,
    reason: str,
) -> ExamSession:
    """Terminate an active session."""
    session = await _get_active_session(db, session_id)
    session.status = SessionStatus.terminated
    session.ended_at = datetime.now(tz=UTC)
    session.termination_reason = reason
    await db.commit()
    await db.refresh(session)
    logger.info("session_terminated", session_id=str(session_id), reason=reason)
    return session


async def create_alert(
    db: AsyncSession,
    *,
    session_id: uuid.UUID,
    severity: EventSeverity,
    message: str,
    event_id: uuid.UUID | None = None,
) -> ProctorAlert:
    """Create a ProctorAlert for the proctor dashboard."""
    alert = ProctorAlert(
        id=uuid.uuid4(),
        session_id=session_id,
        event_id=event_id,
        severity=severity,
        message=message,
    )
    db.add(alert)
    await db.commit()
    await db.refresh(alert)
    return alert


async def record_event(
    db: AsyncSession,
    *,
    session_id: uuid.UUID,
    event_type: str,
    severity: EventSeverity,
    payload: dict | None = None,
    occurred_at: datetime | None = None,
) -> tuple[ProctorEvent, ProctorAlert | None]:
    """Persist a lockdown integrity event and conditionally raise an alert (FR-3.3)."""
    from sqlalchemy import func

    event = ProctorEvent(
        id=uuid.uuid4(),
        session_id=session_id,
        event_type=event_type,
        severity=severity,
        payload=payload,
        occurred_at=occurred_at or datetime.now(UTC),
    )
    db.add(event)
    await db.commit()
    await db.refresh(event)

    alert: ProctorAlert | None = None
    if event_type in ALERT_THRESHOLDS:
        threshold, alert_sev, msg_template = ALERT_THRESHOLDS[event_type]
        count = await db.scalar(
            select(func.count(ProctorEvent.id)).where(
                ProctorEvent.session_id == session_id,
                ProctorEvent.event_type == event_type,
            )
        ) or 1
        if count >= threshold and (count == threshold or count % threshold == 0):
            alert = await create_alert(
                db,
                session_id=session_id,
                severity=alert_sev,
                message=msg_template.format(count=count),
            )

    logger.info("event_recorded", session_id=str(session_id), event_type=event_type)
    return event, alert


# ---------------------------------------------------------------------------
# Private helpers
# ---------------------------------------------------------------------------


async def _get_active_session(db: AsyncSession, session_id: uuid.UUID) -> ExamSession:
    session = await db.get(ExamSession, session_id)
    if session is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Proctoring session not found.",
        )
    if session.status != SessionStatus.active:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Session is not active (status={session.status}).",
        )
    return session
