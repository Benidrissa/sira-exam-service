"""Proctoring API — session management, heartbeat, snapshots, reference frames (E2-2, E2-4)."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from fastapi import APIRouter, Header, HTTPException, status
from sqlalchemy import select

from app.api.deps import DB, CurrentUser
from app.core.config import settings
from app.domain.models.proctor import ExamSession, ProctorSnapshot, SessionStatus
from app.domain.services import proctor_session_service
from app.infrastructure.exam_evidence import (
    get_identity_selfie_upload_url,
    get_offline_frame_upload_url,
    get_reference_frame_upload_url,
    get_snapshot_upload_url,
)
from app.schemas.proctor import (
    ConsentRequest,
    ConsentResponse,
    EdgeResultRequest,
    ExamSessionResponse,
    HeartbeatResponse,
    HeartbeatResumeRequest,
    HeartbeatResumeResponse,
    IdentitySelfieRecordedRequest,
    IdentitySelfieUploadUrlResponse,
    IdentityStatusResponse,
    OfflineFrameBatchRecordedRequest,
    OfflineFrameBatchRecordedResponse,
    OfflineFrameUploadUrlRequest,
    OfflineFrameUploadUrlResponse,
    OfflineFrameUploadUrlResponseItem,
    ProctoringEventBatchRequest,
    ProctoringEventBatchResponse,
    ProctoringEventRequest,
    ProctoringEventResponse,
    ReferenceFrameRecordedRequest,
    ReferenceFrameRecordedResponse,
    ReferenceFrameUploadUrlResponse,
    SnapshotRecordedRequest,
    SnapshotRecordedResponse,
    SnapshotUploadUrlResponse,
    StartSessionRequest,
    StartSessionResponse,
    TerminateSessionRequest,
    VLMConfigResponse,
    VLMModelInfo,
)
from app.tasks.proctor_tasks import analyze_snapshot, verify_identity

router = APIRouter(prefix="/proctor", tags=["proctor"])


# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------


def _uid(user: CurrentUser) -> uuid.UUID:
    return uuid.UUID(user.user_id)


def _org(user: CurrentUser) -> uuid.UUID:
    if not user.org_id:
        raise HTTPException(status_code=403, detail="Missing org_id in token")
    return uuid.UUID(user.org_id)


async def _get_session_or_404(db: DB, session_id: uuid.UUID, org_id: uuid.UUID) -> ExamSession:
    session = await db.scalar(
        select(ExamSession).where(
            ExamSession.id == session_id,
            ExamSession.org_id == org_id,
        )
    )
    if session is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Session not found.")
    return session


# ---------------------------------------------------------------------------
# E2-2: Session start
# ---------------------------------------------------------------------------


@router.post(
    "/sessions/start",
    response_model=StartSessionResponse,
    status_code=status.HTTP_201_CREATED,
)
async def start_session(
    body: StartSessionRequest,
    db: DB,
    user: CurrentUser,
) -> StartSessionResponse:
    """Issue a proctoring session token for an exam attempt (FR-2.2).

    The ``session_token`` is returned **once** — the client must persist it.
    """
    session, raw_token = await proctor_session_service.issue_session_token(
        db,
        attempt_id=body.attempt_id,
        user_id=_uid(user),
        org_id=_org(user),
    )
    return StartSessionResponse(
        session_id=session.id,
        session_token=raw_token,
        expires_in=7200,
        snapshot_interval_ms=session.snapshot_interval_ms,
    )


# ---------------------------------------------------------------------------
# E2-2: Heartbeat
# ---------------------------------------------------------------------------


@router.post("/sessions/{session_id}/heartbeat", response_model=HeartbeatResponse)
async def heartbeat(
    session_id: uuid.UUID,
    db: DB,
    user: CurrentUser,  # noqa: ARG001  — validates JWT + org
    x_session_token: str = Header(..., alias="X-Session-Token"),
) -> HeartbeatResponse:
    """Record a heartbeat; verifies the session token (FR-2.2).

    Pass the raw token in the ``X-Session-Token`` header.
    """
    matched = await proctor_session_service.verify_session_token(db, raw_token=x_session_token)
    if matched is None or matched.id != session_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired session token.",
        )
    if matched.status != SessionStatus.active:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Session is not active (status={matched.status}).",
        )
    await proctor_session_service.record_heartbeat(db, session_id=session_id)
    return HeartbeatResponse(ok=True, next_heartbeat_in=30)


# ---------------------------------------------------------------------------
# E2-2: Consent
# ---------------------------------------------------------------------------


@router.post("/sessions/{session_id}/consent", response_model=ConsentResponse)
async def record_consent(
    session_id: uuid.UUID,
    body: ConsentRequest,
    db: DB,
    user: CurrentUser,
) -> ConsentResponse:
    """Record student consent for proctoring (FR-2.10)."""
    session = await _get_session_or_404(db, session_id, _org(user))
    if session.user_id != _uid(user):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Forbidden.")
    session.consent_given = body.consent_given
    if body.consent_given:
        session.consent_given_at = datetime.now(tz=UTC)
    await db.commit()
    await db.refresh(session)
    return ConsentResponse(
        session_id=session.id,
        consent_given=session.consent_given,
        consent_given_at=session.consent_given_at,
    )


# ---------------------------------------------------------------------------
# E2-4: Snapshot — presigned upload URL
# ---------------------------------------------------------------------------


@router.get(
    "/sessions/{session_id}/snapshot-upload-url",
    response_model=SnapshotUploadUrlResponse,
)
async def snapshot_upload_url(
    session_id: uuid.UUID,
    db: DB,
    user: CurrentUser,
    snapshot_id: uuid.UUID,
) -> SnapshotUploadUrlResponse:
    """Return a presigned PUT URL for uploading a webcam snapshot (FR-2.7)."""
    session = await _get_session_or_404(db, session_id, _org(user))
    if session.user_id != _uid(user):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Forbidden.")
    key = f"snapshots/{session_id}/{snapshot_id}.jpg"
    url = await get_snapshot_upload_url(str(session_id), str(snapshot_id))
    return SnapshotUploadUrlResponse(upload_url=url, storage_key=key)


# ---------------------------------------------------------------------------
# E2-4: Snapshot — record after upload
# ---------------------------------------------------------------------------


@router.post(
    "/sessions/{session_id}/snapshot-recorded",
    response_model=SnapshotRecordedResponse,
    status_code=status.HTTP_201_CREATED,
)
async def snapshot_recorded(
    session_id: uuid.UUID,
    body: SnapshotRecordedRequest,
    db: DB,
    user: CurrentUser,
) -> SnapshotRecordedResponse:
    """Create a ProctorSnapshot row and enqueue AI analysis (FR-2.7)."""
    session = await _get_session_or_404(db, session_id, _org(user))
    if session.user_id != _uid(user):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Forbidden.")

    snapshot = ProctorSnapshot(
        id=body.snapshot_id,
        session_id=session_id,
        storage_key=body.storage_key,
        # E3-9: Edge AI metadata (all optional)
        frame_sha256=body.frame_sha256,
        edge_verdict=body.edge_verdict,
        edge_confidence=body.edge_confidence,
        edge_model_version=body.edge_model_version,
        is_offline_frame=body.is_offline_frame,
        captured_at=body.captured_at,
        edge_processed=body.edge_processed,
    )
    db.add(snapshot)
    await db.commit()
    await db.refresh(snapshot)

    # Dispatch Celery analysis task
    analyze_snapshot.delay(str(snapshot.id))

    return SnapshotRecordedResponse.model_validate(snapshot)


# ---------------------------------------------------------------------------
# E2-4: Reference frame — presigned upload URL
# ---------------------------------------------------------------------------


@router.get(
    "/sessions/{session_id}/reference-frame-upload-url",
    response_model=ReferenceFrameUploadUrlResponse,
)
async def reference_frame_upload_url(
    session_id: uuid.UUID,
    db: DB,
    user: CurrentUser,
) -> ReferenceFrameUploadUrlResponse:
    """Return a presigned PUT URL for uploading the student ID / reference photo."""
    session = await _get_session_or_404(db, session_id, _org(user))
    if session.user_id != _uid(user):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Forbidden.")
    url = await get_reference_frame_upload_url(str(session_id))
    return ReferenceFrameUploadUrlResponse(upload_url=url)


# ---------------------------------------------------------------------------
# E2-4: Reference frame — record after upload
# ---------------------------------------------------------------------------


@router.post(
    "/sessions/{session_id}/reference-frame-recorded",
    response_model=ReferenceFrameRecordedResponse,
)
async def reference_frame_recorded(
    session_id: uuid.UUID,
    body: ReferenceFrameRecordedRequest,
    db: DB,
    user: CurrentUser,
) -> ReferenceFrameRecordedResponse:
    """Store the MinIO key for the student's reference photo."""
    session = await _get_session_or_404(db, session_id, _org(user))
    if session.user_id != _uid(user):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Forbidden.")
    session.reference_frame_key = body.storage_key
    await db.commit()
    await db.refresh(session)
    return ReferenceFrameRecordedResponse(
        session_id=session.id,
        reference_frame_key=session.reference_frame_key or body.storage_key,
    )


# ---------------------------------------------------------------------------
# E3-15: Identity verification
# ---------------------------------------------------------------------------


@router.get("/sessions/{session_id}/identity/upload-url", response_model=IdentitySelfieUploadUrlResponse)
async def get_identity_selfie_upload_url_endpoint(
    session_id: uuid.UUID,
    db: DB,
    user: CurrentUser,
) -> IdentitySelfieUploadUrlResponse:
    """Return a presigned PUT URL for uploading the pre-exam identity selfie (FR-3.15)."""
    session = await _get_session_or_404(db, session_id, _org(user))
    if session.user_id != _uid(user):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Forbidden.")
    if session.identity_verified:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Identity already verified.")
    url, key = await get_identity_selfie_upload_url(str(session_id))
    return IdentitySelfieUploadUrlResponse(upload_url=url, storage_key=key)


@router.post(
    "/sessions/{session_id}/identity/recorded",
    response_model=IdentityStatusResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
async def identity_selfie_recorded(
    session_id: uuid.UUID,
    body: IdentitySelfieRecordedRequest,
    db: DB,
    user: CurrentUser,
) -> IdentityStatusResponse:
    """Record a selfie+ID upload and enqueue Claude Vision validation (FR-3.15)."""
    session = await _get_session_or_404(db, session_id, _org(user))
    if session.user_id != _uid(user):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Forbidden.")
    if session.identity_verified:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Identity already verified.")
    session.identity_selfie_key = body.storage_key
    session.identity_status = "pending"
    await db.commit()
    await db.refresh(session)
    verify_identity.delay(str(session_id))
    return IdentityStatusResponse(
        session_id=session.id,
        identity_verified=session.identity_verified,
        identity_status=session.identity_status,
        identity_verified_at=session.identity_verified_at,
    )


@router.get("/sessions/{session_id}/identity/status", response_model=IdentityStatusResponse)
async def get_identity_status(
    session_id: uuid.UUID,
    db: DB,
    user: CurrentUser,
) -> IdentityStatusResponse:
    """Poll identity verification result (FR-3.15)."""
    session = await _get_session_or_404(db, session_id, _org(user))
    return IdentityStatusResponse(
        session_id=session.id,
        identity_verified=session.identity_verified,
        identity_status=session.identity_status,
        identity_verified_at=session.identity_verified_at,
    )


# ---------------------------------------------------------------------------
# Read: session detail
# ---------------------------------------------------------------------------


@router.get("/sessions/{session_id}", response_model=ExamSessionResponse)
async def get_session(
    session_id: uuid.UUID,
    db: DB,
    user: CurrentUser,
) -> ExamSessionResponse:
    """Fetch session metadata (used by proctor dashboard)."""
    session = await db.scalar(
        select(ExamSession).where(
            ExamSession.id == session_id,
            ExamSession.org_id == _org(user),
        )
    )
    if session is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Session not found.")
    return ExamSessionResponse.model_validate(session)


# ---------------------------------------------------------------------------
# E2-2: Terminate session (teacher only)
# ---------------------------------------------------------------------------


@router.post("/sessions/{session_id}/terminate", response_model=ExamSessionResponse)
async def terminate_session(
    session_id: uuid.UUID,
    body: TerminateSessionRequest,
    user: CurrentUser,
    db: DB,
) -> ExamSessionResponse:
    """Terminate an active session (session owner or teacher, FR-2.2)."""
    session = await _get_session_or_404(db, session_id, _org(user))
    if not getattr(user, "is_teacher", False) and session.user_id != uuid.UUID(user.user_id):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Not authorised to terminate this session.",
        )
    updated = await proctor_session_service.terminate_session(
        db, session_id=session_id, reason=body.reason
    )
    return ExamSessionResponse.model_validate(updated)


# ---------------------------------------------------------------------------
# E3-3: Lockdown events — single
# ---------------------------------------------------------------------------


@router.post(
    "/sessions/{session_id}/events",
    response_model=ProctoringEventResponse,
    status_code=status.HTTP_201_CREATED,
)
async def record_session_event(
    session_id: uuid.UUID,
    body: ProctoringEventRequest,
    db: DB,
    user: CurrentUser,
    x_session_token: str = Header(..., alias="X-Session-Token"),
) -> ProctoringEventResponse:
    """Record a single lockdown integrity event (FR-3.3)."""
    matched = await proctor_session_service.verify_session_token(db, raw_token=x_session_token)
    if matched is None or matched.id != session_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired session token.",
        )
    session = await _get_session_or_404(db, session_id, _org(user))
    if session.status != SessionStatus.active:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Session is not active (status={session.status.value}).",
        )

    event, _ = await proctor_session_service.record_event(
        db,
        session_id=session_id,
        event_type=body.event_type,
        severity=body.severity,
        payload=body.payload,
        occurred_at=body.occurred_at,
    )
    return ProctoringEventResponse.model_validate(event)


# ---------------------------------------------------------------------------
# E3-3: Lockdown events — batch
# ---------------------------------------------------------------------------


@router.post(
    "/sessions/{session_id}/events/batch",
    response_model=ProctoringEventBatchResponse,
    status_code=status.HTTP_201_CREATED,
)
async def record_session_events_batch(
    session_id: uuid.UUID,
    body: ProctoringEventBatchRequest,
    db: DB,
    user: CurrentUser,
    x_session_token: str = Header(..., alias="X-Session-Token"),
) -> ProctoringEventBatchResponse:
    """Record a batch of lockdown integrity events — max 50 per call (FR-3.3)."""
    if len(body.events) > 50:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Batch may not exceed 50 events.",
        )
    matched = await proctor_session_service.verify_session_token(db, raw_token=x_session_token)
    if matched is None or matched.id != session_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired session token.",
        )
    session = await _get_session_or_404(db, session_id, _org(user))
    if session.status != SessionStatus.active:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Session is not active (status={session.status.value}).",
        )

    event_ids: list[uuid.UUID] = []
    for ev in body.events:
        event, _ = await proctor_session_service.record_event(
            db,
            session_id=session_id,
            event_type=ev.event_type,
            severity=ev.severity,
            payload=ev.payload,
            occurred_at=ev.occurred_at,
        )
        event_ids.append(event.id)

    return ProctoringEventBatchResponse(recorded=len(event_ids), event_ids=event_ids)


# ---------------------------------------------------------------------------
# E3-5: Reconnect after network interruption
# ---------------------------------------------------------------------------


@router.post("/sessions/{session_id}/heartbeat-resume", response_model=HeartbeatResumeResponse)
async def heartbeat_resume(
    session_id: uuid.UUID,
    body: HeartbeatResumeRequest,
    db: DB,
    user: CurrentUser,
    x_session_token: str = Header(..., alias="X-Session-Token"),
) -> HeartbeatResumeResponse:
    """Reconnect a disconnected proctoring session after network interruption (FR-3.5)."""
    matched = await proctor_session_service.verify_session_token(db, raw_token=x_session_token)
    if matched is None or matched.id != session_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired session token.",
        )
    session = await proctor_session_service.resume_session_after_disconnect(
        db,
        session_id=session_id,
        answer_drafts=body.answer_drafts,
    )
    return HeartbeatResumeResponse(
        ok=True,
        session_id=session.id,
        reconnected_at=session.last_heartbeat_at or datetime.now(UTC),
        next_heartbeat_in=30,
    )


@router.post(
    "/sessions/{session_id}/offline-frames/batch-upload-urls",
    response_model=OfflineFrameUploadUrlResponse,
)
async def offline_frames_batch_upload_urls(
    session_id: uuid.UUID,
    body: OfflineFrameUploadUrlRequest,
    db: DB,
    user: CurrentUser,
    x_session_token: str = Header(..., alias="X-Session-Token"),
) -> OfflineFrameUploadUrlResponse:
    """Pre-create ProctorSnapshot rows and return presigned PUT URLs for offline frames (FR-3.5)."""
    if len(body.frames) > 50:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Batch may not exceed 50 frames.",
        )
    matched = await proctor_session_service.verify_session_token(db, raw_token=x_session_token)
    if matched is None or matched.id != session_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired session token.",
        )
    session = await _get_session_or_404(db, session_id, _org(user))
    if session.status != SessionStatus.active:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Session is not active (status={session.status.value}).",
        )

    items: list[OfflineFrameUploadUrlResponseItem] = []
    for frame in body.frames:
        existing_snap = await db.get(ProctorSnapshot, frame.snapshot_id)
        if existing_snap is None:
            storage_key = f"snapshots/{session_id}/{frame.snapshot_id}.jpg"
            snap = ProctorSnapshot(
                id=frame.snapshot_id,
                session_id=session_id,
                storage_key=storage_key,
                taken_at=frame.taken_at,
            )
            db.add(snap)
        url, key = await get_offline_frame_upload_url(str(session_id), str(frame.snapshot_id))
        items.append(
            OfflineFrameUploadUrlResponseItem(
                snapshot_id=frame.snapshot_id,
                upload_url=url,
                storage_key=key,
            )
        )
    await db.commit()
    return OfflineFrameUploadUrlResponse(urls=items)


@router.post(
    "/sessions/{session_id}/offline-frames/batch-recorded",
    response_model=OfflineFrameBatchRecordedResponse,
)
async def offline_frames_batch_recorded(
    session_id: uuid.UUID,
    body: OfflineFrameBatchRecordedRequest,
    db: DB,
    user: CurrentUser,
    x_session_token: str = Header(..., alias="X-Session-Token"),
) -> OfflineFrameBatchRecordedResponse:
    """Confirm offline frames uploaded; dispatch analysis tasks (FR-3.5)."""
    matched = await proctor_session_service.verify_session_token(db, raw_token=x_session_token)
    if matched is None or matched.id != session_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired session token.",
        )

    from app.domain.models.proctor import SnapshotAnalysis

    accepted_ids: list[uuid.UUID] = []
    for frame in body.frames:
        snap = await db.get(ProctorSnapshot, frame.snapshot_id)
        if snap is None:
            continue
        if snap.analysis_status != SnapshotAnalysis.pending:
            accepted_ids.append(snap.id)
            continue
        if frame.edge_classification == "flagged":
            analyze_snapshot.apply_async(args=[str(snap.id)], queue="sira_exam_high")
        elif frame.frame_seq % 10 == 0:
            analyze_snapshot.apply_async(args=[str(snap.id)], queue="sira_exam_low")
        accepted_ids.append(snap.id)

    return OfflineFrameBatchRecordedResponse(accepted=len(accepted_ids), snapshot_ids=accepted_ids)


# ---------------------------------------------------------------------------
# E3-10: VLM config + edge result storage
# ---------------------------------------------------------------------------


@router.get("/vlm-config", response_model=VLMConfigResponse)
async def get_vlm_config(user: CurrentUser) -> VLMConfigResponse:
    """Return current edge AI model configuration (FR-3.10).

    Response is NOT cached (Cache-Control: no-store) so clients always get the latest version.
    """
    from fastapi.responses import JSONResponse

    tier1_models: list[VLMModelInfo] = []
    if settings.vlm_cdn_base:
        tier1_models = [
            VLMModelInfo(
                name="mediapipe-face-landmarker",
                url=f"{settings.vlm_cdn_base}/mediapipe-face-landmarker.task",
            ),
            VLMModelInfo(
                name="yolo-world-s-int8",
                url=f"{settings.vlm_cdn_base}/yolo-world-s-int8.onnx",
            ),
        ]
    response_data = VLMConfigResponse(
        model_version=settings.vlm_model_version or "v0.0.0",
        cdn_base=settings.vlm_cdn_base or "",
        tier1_models=tier1_models,
        mandatory_sample_rate=0.10,
    )
    return JSONResponse(
        content=response_data.model_dump(),
        headers={"Cache-Control": "no-store"},
    )


@router.post(
    "/sessions/{session_id}/edge-result",
    status_code=status.HTTP_201_CREATED,
)
async def record_edge_result(
    session_id: uuid.UUID,
    body: EdgeResultRequest,
    db: DB,
    user: CurrentUser,
    x_session_token: str = Header(..., alias="X-Session-Token"),
) -> dict:
    """Store edge AI verdict for a suppressed clean frame (no cloud analysis needed) (FR-3.10)."""
    matched = await proctor_session_service.verify_session_token(db, raw_token=x_session_token)
    if matched is None or matched.id != session_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired session token.",
        )
    session = await _get_session_or_404(db, session_id, _org(user))
    if session.status != SessionStatus.active:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Session is not active (status={session.status.value}).",
        )

    # Create a ProctorSnapshot row with no storage_key (suppressed clean frame)
    from app.domain.models.proctor import SnapshotAnalysis

    snap = ProctorSnapshot(
        id=body.snapshot_id,
        session_id=session_id,
        storage_key="",  # empty — frame was not uploaded
        taken_at=body.captured_at,
        captured_at=body.captured_at,
        analysis_status=SnapshotAnalysis.clean,
        edge_verdict=body.edge_decision,
        edge_confidence=body.edge_confidence,
        edge_model_version=body.model_version,
        edge_processed=True,
        is_offline_frame=False,
    )
    db.add(snap)

    # Increment edge_clean_count in session edge_metadata
    current_meta = session.edge_metadata or {}
    current_meta["edge_clean_count"] = current_meta.get("edge_clean_count", 0) + 1
    session.edge_metadata = current_meta

    await db.commit()
    return {"ok": True, "snapshot_id": str(snap.id)}
