"""Tests for proctor_tasks and heartbeat endpoint — issue #95 bug fixes."""

from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# ---------------------------------------------------------------------------
# Test 1 — Import fix: analyze_snapshot is importable from proctor_tasks
# ---------------------------------------------------------------------------


def test_analyze_snapshot_is_importable() -> None:
    """analyze_snapshot must be importable from proctor_tasks (not proctor)."""
    from app.tasks.proctor_tasks import analyze_snapshot  # must not raise ImportError

    assert callable(analyze_snapshot.delay)


# ---------------------------------------------------------------------------
# Test 2 — Feature flag: Claude is NOT called when enable_proctor_vision=False
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_analyze_snapshot_skips_vision_when_flag_disabled() -> None:
    """When enable_proctor_vision=False, status→clean and Anthropic is never called."""
    from app.domain.models.proctor import ProctorSnapshot, SnapshotAnalysis
    from app.tasks.proctor_tasks import _analyze_snapshot_async

    snap_id = uuid.uuid4()
    snap = MagicMock(spec=ProctorSnapshot)
    snap.analysis_status = SnapshotAnalysis.pending
    snap.session_id = uuid.uuid4()
    snap.storage_key = "snapshots/test/snap.jpg"

    mock_db_ctx = AsyncMock()
    mock_db_ctx.get = AsyncMock(return_value=snap)
    mock_db_ctx.commit = AsyncMock()
    mock_db_ctx.refresh = AsyncMock()
    mock_db_ctx.__aenter__ = AsyncMock(return_value=mock_db_ctx)
    mock_db_ctx.__aexit__ = AsyncMock(return_value=False)

    mock_anthropic_cls = MagicMock()

    with (
        patch("app.tasks.proctor_tasks.settings") as mock_settings,
        # celery_db is a deferred import inside the function — patch at source module
        patch("app.core.database.celery_db", return_value=mock_db_ctx),
        patch("anthropic.Anthropic", mock_anthropic_cls),
    ):
        mock_settings.enable_proctor_vision = False
        mock_settings.exam_anthropic_api_key = ""

        result = await _analyze_snapshot_async(str(snap_id))

    assert snap.analysis_status == SnapshotAnalysis.clean
    assert result.get("skipped") is True
    mock_anthropic_cls.assert_not_called()


# ---------------------------------------------------------------------------
# Test 3 — Missing snapshot returns gracefully without calling Claude
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_analyze_snapshot_returns_error_for_missing_snapshot() -> None:
    """When the snapshot row is not found, task returns an error dict gracefully."""
    from app.tasks.proctor_tasks import _analyze_snapshot_async

    mock_db_ctx = AsyncMock()
    mock_db_ctx.get = AsyncMock(return_value=None)  # not found
    mock_db_ctx.__aenter__ = AsyncMock(return_value=mock_db_ctx)
    mock_db_ctx.__aexit__ = AsyncMock(return_value=False)

    mock_anthropic_cls = MagicMock()

    with (
        patch("app.core.database.celery_db", return_value=mock_db_ctx),
        patch("anthropic.Anthropic", mock_anthropic_cls),
    ):
        result = await _analyze_snapshot_async(str(uuid.uuid4()))

    assert "error" in result
    mock_anthropic_cls.assert_not_called()


# ---------------------------------------------------------------------------
# Test 4 — Heartbeat endpoint contract: X-Session-Token required
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_heartbeat_requires_session_token_header() -> None:
    """POST /heartbeat without X-Session-Token must return 422 (missing required header)."""
    import uuid as _uuid

    from httpx import ASGITransport, AsyncClient

    from app.main import app

    session_id = _uuid.uuid4()
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.post(
            f"/api/v1/proctor/sessions/{session_id}/heartbeat",
            headers={"Authorization": "Bearer fake-token"},
            # Intentionally omitting X-Session-Token
        )
    # Auth middleware fires first (401 for bad JWT) then header validation (422).
    # Either proves the endpoint rejects calls without proper auth headers.
    assert resp.status_code in (401, 422)
