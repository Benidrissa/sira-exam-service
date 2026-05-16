"""Celery proctoring tasks — E2-5.

Tasks:
    analyze_snapshot  — Claude Vision violation detection
    check_heartbeat   — periodic heartbeat watchdog (Celery beat, every 30 s)
    finalize_session  — mark session completed/terminated
"""

from __future__ import annotations

import asyncio
import base64
import hashlib
import json
import uuid as _uuid_module
from datetime import UTC, datetime, timedelta

import structlog

from app.core.config import settings
from app.tasks.celery_app import celery_app

logger = structlog.get_logger(__name__)

PROCTORING_SYSTEM_PROMPT = """\
You are an automated online exam proctoring AI. Your sole job is to analyze \
a single webcam frame captured during a remotely proctored academic examination \
and report any integrity violations. You will always respond by calling the \
report_proctoring_analysis tool — never with free text.

VIOLATION TYPES — definitions and detection criteria:

1. none
   The student is alone, facing the camera, and no prohibited devices or \
persons are visible. Assign this when the frame is clean.

2. multiple_people
   Two or more distinct human faces or bodies are visible in the frame at the \
same time. A reflection or poster with a face does NOT count. Confidence should \
be high (>=0.85) only when at least two fully or partially visible faces are \
unambiguous. A fleeting shadow or heavily blurred background figure warrants \
lower confidence (0.5–0.7).

3. no_face
   No human face is detectable in the frame. This includes: the student has \
turned fully away, is absent from the seat, the camera is covered or pointed at \
the ceiling, or the image is too dark/blurry to make any determination. \
Distinguish from looking_away (face partially visible but gaze averted).

4. looking_away
   The student's face IS visible but gaze is directed significantly away from \
the primary screen — laterally more than approximately 30 degrees, or downward \
toward a concealed device. A brief glance does not automatically trigger this; \
the posture must suggest sustained off-screen attention. Do not flag if the \
student is reading a secondary monitor that is part of the legitimate exam \
setup and visible in the same frame.

5. phone_detected
   A mobile phone, smartphone, or tablet held in hand or placed on the desk \
is visible. Physical books and printed notes are NOT phone_detected. Smart \
watches are borderline — flag at confidence 0.6 or below unless the screen is \
clearly illuminated with messaging or search content.

6. another_screen
   A second monitor, laptop, or television displaying non-exam content is \
visible in the background or reflected in glasses or surfaces. The student's \
primary exam screen does NOT count. A dark or powered-off secondary monitor does \
NOT count.

7. other
   A clear integrity concern exists but does not fit the categories above. \
Use sparingly and provide a precise description field. Examples: student \
visibly reading from notes taped off-camera, earpiece visible, \
another person's hands visible on the keyboard.

CONFIDENCE SCALE:
0.0–0.39  : Possible or uncertain — do not flag as a violation in downstream \
logic unless operator threshold is very low.
0.40–0.59 : Likely — flag but treat as low-severity.
0.60–0.84 : Probable — flag as medium-severity.
0.85–1.00 : Certain — flag as high-severity; triggers immediate alert.

FRAME QUALITY NOTES:
If the image is completely black, white, or corrupted: set violation_detected=false, \
violation_type=none, confidence=0.0, description="Frame unreadable due to quality issue."
Do not speculate about events outside the frame. Only report what is visible.
Privacy: do not describe the student's appearance, race, or gender in the description \
field. Describe only the behavioral or object observation.

LIGHTING AND ENVIRONMENTAL FACTORS:
Poor lighting that obscures the face should be treated similarly to no_face if \
the student cannot be identified. Reflections from glasses are common — only flag \
another_screen if the reflected content is clearly readable or shows distinct \
screen elements. Background blur from webcam depth-of-field effects is normal and \
should not cause false positives for multiple_people.

TEMPORAL CONTEXT:
Each call receives a single static frame, not a video. You cannot infer duration \
from a single frame. Make your assessment based solely on what is visible in the \
current frame. Do not reference previous frames.

OUTPUT FORMAT enforced by tool schema:
Always call report_proctoring_analysis with all four required fields.
The description field must be one concise sentence of 25 words or fewer stating \
the specific observation that led to your conclusion.\
"""


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

    from app.core.database import celery_db
    from app.domain.models.proctor import (  # type: ignore[attr-defined]
        EventSeverity,
        ProctorAlert,
        ProctorEvent,
        ProctorSnapshot,
        SnapshotAnalysis,
    )

    async with celery_db() as db:
        snap = await db.get(ProctorSnapshot, _uuid_module.UUID(snapshot_id))
        if not snap:
            logger.warning("analyze_snapshot_not_found", snapshot_id=snapshot_id)
            return {"error": "snapshot not found"}

        snap.analysis_status = SnapshotAnalysis.analyzing
        await db.commit()
        await db.refresh(snap)

        if not settings.enable_proctor_vision:
            logger.info("proctor_vision_disabled", snapshot_id=snapshot_id)
            snap.analysis_status = SnapshotAnalysis.clean
            snap.analysis_result = {"skipped": True, "reason": "enable_proctor_vision=False"}
            await db.commit()
            return {"skipped": True}

        # Download image from MinIO
        from app.infrastructure.storage import get_exam_storage

        storage = get_exam_storage()
        image_bytes = await storage.download(snap.storage_key)
        image_b64 = base64.b64encode(image_bytes).decode()

        # E3-9: SHA-256 integrity check
        if snap.frame_sha256 is not None:
            actual_sha256 = hashlib.sha256(image_bytes).hexdigest()
            if actual_sha256 != snap.frame_sha256:
                logger.warning(
                    "snapshot_integrity_failure",
                    snapshot_id=snapshot_id,
                    expected=snap.frame_sha256,
                    actual=actual_sha256,
                )
                snap.integrity_check_passed = False
                snap.integrity_failure_reason = "sha256_mismatch"
                snap.analysis_status = SnapshotAnalysis.error
                event = ProctorEvent(
                    id=_uuid_module.uuid4(),
                    session_id=snap.session_id,
                    event_type="integrity_check_failed",
                    severity=EventSeverity.medium,
                    payload={
                        "expected_sha256": snap.frame_sha256,
                        "actual_sha256": actual_sha256,
                    },
                )
                db.add(event)
                await db.commit()
                return {"error": "integrity_check_failed", "snapshot_id": snapshot_id}
            snap.integrity_check_passed = True

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
            system=[
                {
                    "type": "text",
                    "text": PROCTORING_SYSTEM_PROMPT,
                    "cache_control": {"type": "ephemeral"},
                }
            ],
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
        logger.info(
            "claude_vision_usage",
            snapshot_id=snapshot_id,
            input_tokens=response.usage.input_tokens,
            cache_creation=getattr(response.usage, "cache_creation_input_tokens", 0),
            cache_read=getattr(response.usage, "cache_read_input_tokens", 0),
        )

        tool_block = response.content[0]
        assert tool_block.type == "tool_use", f"Expected tool_use, got {tool_block.type}"  # type: ignore[union-attr]
        result: dict = tool_block.input  # type: ignore[union-attr]

        snap.analysis_status = (
            SnapshotAnalysis.flagged if result["violation_detected"] else SnapshotAnalysis.clean
        )
        snap.violation_detected = result["violation_detected"]
        snap.violation_type = result["violation_type"]
        snap.confidence = result["confidence"]
        snap.analysis_result = result
        await db.commit()

        if result["violation_detected"] and result["confidence"] >= 0.7:
            severity = EventSeverity.high if result["confidence"] >= 0.85 else EventSeverity.medium
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
            import redis as sync_redis_lib

            r = sync_redis_lib.from_url(settings.redis_url)
            try:
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
            finally:
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
    import redis as sync_redis_lib
    from sqlalchemy import select

    from app.core.database import celery_db
    from app.domain.models.proctor import (  # type: ignore[attr-defined]
        EventSeverity,
        ExamSession,
        NetworkGap,
        ProctorAlert,
        ProctorEvent,
        SessionStatus,
    )

    heartbeat_threshold = datetime.now(UTC) - timedelta(seconds=75)  # 2.5 × heartbeat interval
    grace_cutoff = datetime.now(UTC) - timedelta(
        seconds=settings.session_reconnect_grace_period_seconds
    )

    async with celery_db() as db:
        # ------------------------------------------------------------------
        # Branch A — active sessions that missed a heartbeat
        # ------------------------------------------------------------------
        active_result = await db.execute(
            select(ExamSession).where(
                ExamSession.status == SessionStatus.active,
                ExamSession.last_heartbeat_at < heartbeat_threshold,
            )
        )
        active_sessions = active_result.scalars().all()

        # ------------------------------------------------------------------
        # Branch B — disconnected sessions past the reconnect grace period
        # ------------------------------------------------------------------
        disconnected_result = await db.execute(
            select(ExamSession).where(
                ExamSession.status == SessionStatus.disconnected,
                ExamSession.disconnected_at < grace_cutoff,
            )
        )
        disconnected_sessions = disconnected_result.scalars().all()

        flagged = 0
        expired = 0
        now = datetime.now(UTC)

        r = sync_redis_lib.from_url(settings.redis_url)
        try:
            # --- Branch A: active → disconnected at threshold misses ---
            for session in active_sessions:
                lock_key = f"exam:heartbeat_check:{session.id}"
                if r.exists(lock_key):
                    continue
                r.setex(lock_key, 60, "1")

                session.consecutive_missed_heartbeats = (
                    session.consecutive_missed_heartbeats or 0
                ) + 1
                missed = session.consecutive_missed_heartbeats

                if missed >= settings.heartbeat_disconnected_threshold:
                    session.status = SessionStatus.disconnected
                    session.disconnected_at = now

                    # Create NetworkGap to start tracking the interruption
                    gap = NetworkGap(
                        id=_uuid_module.uuid4(),
                        session_id=session.id,
                        disconnected_at=now,
                        missed_heartbeat_count=missed,
                        auto_expired=False,
                    )
                    db.add(gap)

                    event = ProctorEvent(
                        id=_uuid_module.uuid4(),
                        session_id=session.id,
                        event_type="network_interruption_suspected",
                        severity=EventSeverity.medium,
                        payload={"missed_count": missed},
                    )
                    db.add(event)

                    alert = ProctorAlert(
                        id=_uuid_module.uuid4(),
                        session_id=session.id,
                        severity=EventSeverity.medium,
                        message=(
                            f"Session disconnected: {missed} consecutive missed heartbeats. "
                            f"Grace period: {settings.session_reconnect_grace_period_seconds}s."
                        ),
                    )
                    db.add(alert)

                    r.publish(
                        f"proctor:session:{session.id}",
                        json.dumps(
                            {
                                "type": "session_disconnected",
                                "session_id": str(session.id),
                                "missed_count": missed,
                            }
                        ),
                    )
                else:
                    # Still below threshold — just log the miss
                    event = ProctorEvent(
                        id=_uuid_module.uuid4(),
                        session_id=session.id,
                        event_type="heartbeat_missed",
                        severity=EventSeverity.medium,
                        payload={"count": missed},
                    )
                    db.add(event)

                flagged += 1

            # --- Branch B: disconnected → expired after grace period ---
            for session in disconnected_sessions:
                lock_key = f"exam:grace_expired:{session.id}"
                if r.exists(lock_key):
                    continue
                r.setex(lock_key, 60, "1")

                session.status = SessionStatus.expired
                session.ended_at = now
                session.termination_reason = "reconnect_grace_period_expired"

                # Close the open NetworkGap for this session
                gap_result = await db.execute(
                    select(NetworkGap).where(
                        NetworkGap.session_id == session.id,
                        NetworkGap.reconnected_at.is_(None),
                    )
                )
                open_gap = gap_result.scalars().first()
                if open_gap and session.disconnected_at:
                    open_gap.reconnected_at = now
                    open_gap.auto_expired = True
                    open_gap.duration_seconds = int(
                        (now - session.disconnected_at).total_seconds()
                    )

                event = ProctorEvent(
                    id=_uuid_module.uuid4(),
                    session_id=session.id,
                    event_type="session_auto_expired",
                    severity=EventSeverity.critical,
                    payload={"reason": "reconnect_grace_period_expired"},
                )
                db.add(event)

                alert = ProctorAlert(
                    id=_uuid_module.uuid4(),
                    session_id=session.id,
                    severity=EventSeverity.critical,
                    message=(
                        "Session auto-expired: reconnect grace period exceeded "
                        f"({settings.session_reconnect_grace_period_seconds}s)."
                    ),
                )
                db.add(alert)

                r.publish(
                    f"proctor:session:{session.id}",
                    json.dumps(
                        {
                            "type": "session_expired",
                            "session_id": str(session.id),
                            "reason": "reconnect_grace_period_expired",
                        }
                    ),
                )

                expired += 1

        finally:
            r.close()

        await db.commit()
        logger.info(
            "heartbeat_check_done",
            active_checked=len(active_sessions),
            disconnected_checked=len(disconnected_sessions),
            flagged=flagged,
            expired=expired,
        )
        return {
            "checked": len(active_sessions),
            "flagged": flagged,
            "expired": expired,
        }


# ---------------------------------------------------------------------------
# Task: finalize_session
# ---------------------------------------------------------------------------


@celery_app.task(name="tasks.finalize_session")
def finalize_session(session_id: str, reason: str = "exam_submitted") -> dict:  # type: ignore[type-arg]
    """Mark an active session as completed and record end time."""
    return asyncio.run(_finalize_session_async(session_id, reason))


async def _finalize_session_async(session_id: str, reason: str) -> dict:  # type: ignore[type-arg]
    from app.core.database import celery_db
    from app.domain.models.proctor import ExamSession, SessionStatus  # type: ignore[attr-defined]

    async with celery_db() as db:
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
