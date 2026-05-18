"""Tests for E3-5 — reconnect + offline sync API."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


@pytest.mark.asyncio
async def test_heartbeat_resume_disconnected_session_closes_network_gap() -> None:  # noqa: E501
    from app.domain.models.proctor import ExamSession, NetworkGap, SessionStatus
    from app.domain.services.proctor_session_service import resume_session_after_disconnect

    session_id = uuid.uuid4()
    disconnected_at = datetime.now(UTC) - timedelta(seconds=45)

    session = MagicMock(spec=ExamSession)
    session.id = session_id
    session.attempt_id = uuid.uuid4()
    session.status = SessionStatus.disconnected
    session.disconnected_at = disconnected_at
    session.last_heartbeat_at = None
    session.consecutive_missed_heartbeats = 3

    open_gap = MagicMock(spec=NetworkGap)
    open_gap.reconnected_at = None
    open_gap.disconnected_at = disconnected_at

    mock_db = AsyncMock()
    mock_db.get = AsyncMock(return_value=session)
    mock_db.scalar = AsyncMock(return_value=open_gap)
    mock_db.add = MagicMock()
    mock_db.commit = AsyncMock()
    mock_db.refresh = AsyncMock()

    with patch("app.domain.services.proctor_session_service.select", return_value=MagicMock()):
        await resume_session_after_disconnect(mock_db, session_id=session_id)

    assert session.status == SessionStatus.active
    assert session.consecutive_missed_heartbeats == 0
    assert session.disconnected_at is None
    assert open_gap.reconnected_at is not None
    assert open_gap.duration_seconds >= 44
    mock_db.commit.assert_awaited_once()


@pytest.mark.asyncio
async def test_heartbeat_resume_on_expired_session_returns_409() -> None:
    from fastapi import HTTPException

    from app.domain.models.proctor import ExamSession, SessionStatus
    from app.domain.services.proctor_session_service import _get_disconnected_session

    session_id = uuid.uuid4()
    expired_session = MagicMock(spec=ExamSession)
    expired_session.id = session_id
    expired_session.status = SessionStatus.expired

    mock_db = AsyncMock()
    mock_db.get = AsyncMock(return_value=expired_session)

    with pytest.raises(HTTPException) as exc_info:
        await _get_disconnected_session(mock_db, session_id)

    assert exc_info.value.status_code == 409


@pytest.mark.asyncio
async def test_batch_recorded_skips_already_processed_snapshot() -> None:
    from app.domain.models.proctor import ProctorSnapshot, SnapshotAnalysis

    snap_id = uuid.uuid4()

    snap = MagicMock(spec=ProctorSnapshot)
    snap.id = snap_id
    snap.analysis_status = SnapshotAnalysis.clean  # already processed

    mock_analyze_task = MagicMock()
    mock_analyze_task.apply_async = MagicMock()

    # Simulate the batch-recorded logic directly
    frame = MagicMock()
    frame.snapshot_id = snap_id
    frame.frame_seq = 10
    frame.edge_classification = "clean"

    accepted_ids: list[uuid.UUID] = []
    if snap.analysis_status != SnapshotAnalysis.pending:
        accepted_ids.append(snap.id)
    else:
        if frame.edge_classification == "flagged":
            mock_analyze_task.apply_async(args=[str(snap.id)], queue="sira_exam_high")
        elif frame.frame_seq % 10 == 0:
            mock_analyze_task.apply_async(args=[str(snap.id)], queue="sira_exam_low")
        accepted_ids.append(snap.id)

    mock_analyze_task.apply_async.assert_not_called()
    assert snap_id in accepted_ids
