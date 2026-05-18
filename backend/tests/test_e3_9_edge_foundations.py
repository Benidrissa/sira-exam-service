"""Tests for E3-9 — Edge AI server foundations: SHA-256 integrity, backward compat."""

from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


@pytest.mark.asyncio
async def test_sha256_mismatch_creates_integrity_failure_event_and_skips_claude() -> None:
    from app.domain.models.proctor import ProctorSnapshot, SnapshotAnalysis
    from app.tasks.proctor_tasks import _analyze_snapshot_async

    snap_id = uuid.uuid4()
    session_id = uuid.uuid4()
    real_bytes = b"real image bytes"
    stored_sha256 = "a" * 64  # wrong hash

    snap = MagicMock(spec=ProctorSnapshot)
    snap.id = snap_id
    snap.session_id = session_id
    snap.storage_key = f"snapshots/{session_id}/{snap_id}.jpg"
    snap.analysis_status = SnapshotAnalysis.pending
    snap.frame_sha256 = stored_sha256

    mock_db = AsyncMock()
    mock_db.get = AsyncMock(return_value=snap)
    mock_db.add = MagicMock()
    mock_db.commit = AsyncMock()
    mock_db.refresh = AsyncMock()
    mock_db.__aenter__ = AsyncMock(return_value=mock_db)
    mock_db.__aexit__ = AsyncMock(return_value=False)

    mock_storage = MagicMock()
    mock_storage.download = AsyncMock(return_value=real_bytes)

    mock_anthropic_cls = MagicMock()

    with (
        patch("app.tasks.proctor_tasks.settings") as mock_settings,
        patch("app.core.database.celery_db", return_value=mock_db),
        patch("app.infrastructure.storage.get_exam_storage", return_value=mock_storage),
        patch("anthropic.Anthropic", mock_anthropic_cls),
    ):
        mock_settings.enable_proctor_vision = True
        mock_settings.exam_anthropic_api_key = "test-key"
        mock_settings.anthropic_model = "claude-sonnet-4-6"
        result = await _analyze_snapshot_async(str(snap_id))

    assert result.get("error") == "integrity_check_failed"
    assert snap.integrity_check_passed is False
    assert snap.integrity_failure_reason == "sha256_mismatch"
    assert snap.analysis_status == SnapshotAnalysis.error
    mock_anthropic_cls.assert_not_called()


def test_snapshot_recorded_request_accepts_old_client_without_edge_fields() -> None:
    from app.schemas.proctor import SnapshotRecordedRequest

    snap_id = uuid.uuid4()
    storage_key = f"snapshots/{uuid.uuid4()}/{snap_id}.jpg"
    req = SnapshotRecordedRequest(snapshot_id=snap_id, storage_key=storage_key)
    assert req.frame_sha256 is None
    assert req.edge_verdict is None
    assert req.is_offline_frame is False
    assert req.edge_processed is False


def test_snapshot_recorded_request_accepts_new_edge_fields() -> None:
    from app.schemas.proctor import SnapshotRecordedRequest

    snap_id = uuid.uuid4()
    req = SnapshotRecordedRequest(
        snapshot_id=snap_id,
        storage_key=f"snapshots/x/{snap_id}.jpg",
        frame_sha256="deadbeef" * 8,
        edge_verdict="clean",
        edge_confidence=0.92,
        edge_model_version="v1.0",
        is_offline_frame=True,
        edge_processed=True,
    )
    assert req.frame_sha256 == "deadbeef" * 8
    assert req.edge_verdict == "clean"
    assert req.is_offline_frame is True
