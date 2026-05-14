"""Celery proctoring tasks — E2-5.

Tasks:
    analyze_snapshot  — Claude Vision violation detection
    check_heartbeat   — periodic heartbeat watchdog (Celery beat, every 30 s)
    finalize_session  — mark session completed/terminated
"""

from __future__ import annotations

import asyncio
import base64
import json
import uuid as _uuid_module
from datetime import UTC, datetime, timedelta

import structlog

from app.core.config import settings
from app.tasks.celery_app import celery_app

logger = structlog.get_logger(__name__)


# ---------------------------------------------------------------------------
# Task: analyze_snapshot
# ---------------------------------------------------------------------------


@celery_app.task(name="tasks.analyze_snapshot", bind=True, max_retries=2)
def analyze_snapshot(self, snapshot_id: str) -> dict:  # type: ignore[type-arg]
    """Download snapshot from MinIO, send to Claude Vision, flag violations."""
    try:
        return asyncio.run(_analyze_snapshot_async(snapshot_id))
    except Exception as exc:
        raise self.retry(exc=exc, countdown=30) from exc


async def _analyze_snapshot_async(snapshot_id: str) -> dict:  # type: ignore[type-arg]
    from anthropic import Anthropic

    from app.core.database import AsyncSessionLocal
    from app.domain.models.proctor import (  # type: ignore[attr-defined]
        EventSeverity,
        ProctorAlert,
        ProctorEvent,
        ProctorSnapshot,
        SnapshotAnalysis,
    )

    async with AsyncSessionLocal() as db:
        snap = await db.get(ProctorSnapshot, _uuid_module.UUID(snapshot_id))
        if not snap:
            logger.warning("analyze_snapshot_not_found", snapshot_id=snapshot_id)
            return {"error": "snapshot not found"}

        snap.analysis_status = SnapshotAnalysis.analyzing
        await db.commit()
        await db.refresh(snap)

        # Download image from MinIO
        from app.infrastructure.storage import get_exam_storage

        storage = get_exam_storage()
        image_bytes = await storage.download(snap.storage_key)
        image_b64 = base64.b64encode(image_bytes).decode()

        # Claude Vision — forced tool use
        client = Anthropic(api_key=settings.exam_anthropic_api_key or None)
        tool_def = {
            "name": "report_proctoring_analysis",
            "description": "Report the result of proctoring image analysis",
            "input_schema": {
                "type": "object",
                "properties": {
                    "violation_detected": {"type": "boolean"},
                    "violation_type": {
                        "type": "string",
                        "enum": [
                            "none",
                            "multiple_people",
                            "no_face",
                            "looking_away",
                            "phone_detected",
                            "another_screen",
                            "other",
                        ],
                    },
                    "confidence": {"type": "number", "minimum": 0, "maximum": 1},
                    "description": {"type": "string"},
                },
                "required": ["violation_detected", "violation_type", "confidence", "description"],
            },
        }

        response = client.messages.create(
            model=settings.anthropic_model,
            max_tokens=256,
            tools=[tool_def],  # type: ignore[list-item]
            tool_choice={"type": "tool", "name": "report_proctoring_analysis"},
            messages=[
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "image",
                            "source": {
                                "type": "base64",
                                "media_type": "image/jpeg",
                                "data": image_b64,
                            },
                        },
                        {
                            "type": "text",
                            "text": (
                                "Analyze this exam proctoring snapshot. "
                                "Check for: multiple people in frame, no face visible, "
                                "student looking away from screen (>2 seconds), "
                                "phone or another screen visible. Report findings."
                            ),
                        },
                    ],
                }
            ],
        )

        result: dict = response.content[0].input  # type: ignore[union-attr]

        snap.analysis_status = (
            SnapshotAnalysis.flagged if result["violation_detected"] else SnapshotAnalysis.clean
        )
        snap.violation_detected = result["violation_detected"]
        snap.violation_type = result["violation_type"]
        snap.confidence = result["confidence"]
        snap.analysis_result = result
        await db.commit()

        if result["violation_detected"] and result["confidence"] >= 0.7:
            severity = (
                EventSeverity.high if result["confidence"] >= 0.85 else EventSeverity.medium
            )
            event = ProctorEvent(
                id=_uuid_module.uuid4(),
                session_id=snap.session_id,
                event_type="violation_detected",
                severity=severity,
                payload=result,
            )
            db.add(event)
            alert = ProctorAlert(
                id=_uuid_module.uuid4(),
                session_id=snap.session_id,
                severity=severity,
                message=(
                    f"Violation detected: {result['violation_type']} "
                    f"(confidence: {result['confidence']:.0%})"
                ),
            )
            db.add(alert)
            await db.commit()
            await db.refresh(alert)

            # Publish to Redis for WebSocket fanout (sync redis for Celery worker)
            import redis as sync_redis

            r = sync_redis.from_url(settings.redis_url)
            r.publish(
                f"proctor:session:{snap.session_id}",
                json.dumps(
                    {
                        "type": "violation",
                        "session_id": str(snap.session_id),
                        "alert": {
                            "id": str(alert.id),
                            "severity": severity.value,
                            "message": alert.message,
                        },
                    }
                ),
            )
            r.close()

            logger.info(
                "snapshot_violation_flagged",
                snapshot_id=snapshot_id,
                violation_type=result["violation_type"],
                confidence=result["confidence"],
            )

        return result


# ---------------------------------------------------------------------------
# Task: check_heartbeat  (Celery beat — every 30 s)
# ---------------------------------------------------------------------------


@celery_app.task(name="tasks.check_heartbeat")
def check_heartbeat() -> dict:  # type: ignore[type-arg]
    """Flag sessions that missed 2+ consecutive heartbeats; expire at 5 misses."""
    return asyncio.run(_check_heartbeat_async())


async def _check_heartbeat_async() -> dict:  # type: ignore[type-arg]
    from sqlalchemy import select

    from app.core.database import AsyncSessionLocal
    from app.domain.models.proctor import (  # type: ignore[attr-defined]
        EventSeverity,
        ExamSession,
        ProctorAlert,
        ProctorEvent,
        SessionStatus,
    )

    threshold = datetime.now(UTC) - timedelta(seconds=75)  # 2.5 × heartbeat interval

    async with AsyncSessionLocal() as db:
        result = await db.execute(
            select(ExamSession).where(
                ExamSession.status == SessionStatus.active,
                ExamSession.last_heartbeat_at < threshold,
            )
        )
        sessions = result.scalars().all()

        flagged = 0
        for session in sessions:
            session.consecutive_missed_heartbeats = (
                session.consecutive_missed_heartbeats or 0
            ) + 1

            missed = session.consecutive_missed_heartbeats
            severity = EventSeverity.high if missed >= 3 else EventSeverity.medium

            event = ProctorEvent(
                id=_uuid_module.uuid4(),
                session_id=session.id,
                event_type="heartbeat_missed",
                severity=severity,
                payload={"count": missed},
            )
            db.add(event)

            if missed >= 5:
                session.status = SessionStatus.expired
                session.ended_at = datetime.now(UTC)
                session.termination_reason = "heartbeat_timeout"

                alert = ProctorAlert(
                    id=_uuid_module.uuid4(),
                    session_id=session.id,
                    severity=EventSeverity.critical,
                    message=(
                        f"Session auto-expired: {missed} consecutive missed heartbeats"
                    ),
                )
                db.add(alert)

                # Notify proctor via Redis
                import redis as sync_redis

                r = sync_redis.from_url(settings.redis_url)
                r.publish(
                    f"proctor:session:{session.id}",
                    json.dumps(
                        {
                            "type": "session_expired",
                            "session_id": str(session.id),
                            "reason": "heartbeat_timeout",
                            "missed_count": missed,
                        }
                    ),
                )
                r.close()

            flagged += 1

        await db.commit()
        logger.info("heartbeat_check_done", checked=len(sessions), flagged=flagged)
        return {"checked": len(sessions), "flagged": flagged}


# ---------------------------------------------------------------------------
# Task: finalize_session
# ---------------------------------------------------------------------------


@celery_app.task(name="tasks.finalize_session")
def finalize_session(session_id: str, reason: str = "exam_submitted") -> dict:  # type: ignore[type-arg]
    """Mark an active session as completed and record end time."""
    return asyncio.run(_finalize_session_async(session_id, reason))


async def _finalize_session_async(session_id: str, reason: str) -> dict:  # type: ignore[type-arg]
    from app.core.database import AsyncSessionLocal
    from app.domain.models.proctor import ExamSession, SessionStatus  # type: ignore[attr-defined]

    async with AsyncSessionLocal() as db:
        session = await db.get(ExamSession, _uuid_module.UUID(session_id))
        if session and session.status == SessionStatus.active:
            session.status = SessionStatus.completed
            session.ended_at = datetime.now(UTC)
            session.termination_reason = reason
            await db.commit()
            logger.info("session_finalized", session_id=session_id, reason=reason)
        else:
            logger.warning(
                "finalize_session_skipped",
                session_id=session_id,
                status=str(session.status) if session else "not_found",
            )

    return {"session_id": session_id, "finalized": True, "reason": reason}
