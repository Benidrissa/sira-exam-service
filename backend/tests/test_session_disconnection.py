"""Tests for E3-4 — session disconnection model: grace period + NetworkGap audit table."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# ---------------------------------------------------------------------------
# Test 1 — Three missed heartbeats transitions session to 'disconnected'
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_three_missed_heartbeats_sets_disconnected() -> None:
    """Active session with 2 prior misses → status becomes disconnected on the 3rd miss."""
    from app.domain.models.proctor import ExamSession, SessionStatus
    from app.tasks.proctor_tasks import _check_heartbeat_async

    session_id = uuid.uuid4()
    session = MagicMock(spec=ExamSession)
    session.id = session_id
    session.status = SessionStatus.active
    session.consecutive_missed_heartbeats = 2  # one more will hit threshold=3
    session.disconnected_at = None
    session.last_heartbeat_at = datetime.now(UTC) - timedelta(seconds=120)

    # Mock db.execute — first call returns active sessions, second returns disconnected sessions
    mock_active_scalars = MagicMock()
    mock_active_scalars.scalars.return_value.all.return_value = [session]

    mock_disconnected_scalars = MagicMock()
    mock_disconnected_scalars.scalars.return_value.all.return_value = []

    # For Branch B's NetworkGap query — not used in this test but must not crash
    mock_gap_scalars = MagicMock()
    mock_gap_scalars.scalars.return_value.first.return_value = None

    mock_db = AsyncMock()
    mock_db.execute = AsyncMock(
        side_effect=[mock_active_scalars, mock_disconnected_scalars]
    )
    mock_db.add = MagicMock()
    mock_db.commit = AsyncMock()
    mock_db.__aenter__ = AsyncMock(return_value=mock_db)
    mock_db.__aexit__ = AsyncMock(return_value=False)

    mock_redis = MagicMock()
    mock_redis.exists.return_value = False
    mock_redis.setex = MagicMock()
    mock_redis.publish = MagicMock()
    mock_redis.close = MagicMock()

    mock_settings = MagicMock()
    mock_settings.redis_url = "redis://localhost:6379/0"
    mock_settings.heartbeat_disconnected_threshold = 3
    mock_settings.session_reconnect_grace_period_seconds = 120

    with (
        patch("app.core.database.celery_db", return_value=mock_db),
        patch("redis.from_url", return_value=mock_redis),
        patch("app.tasks.proctor_tasks.settings", mock_settings),
    ):
        result = await _check_heartbeat_async()

    assert session.status == SessionStatus.disconnected
    assert session.disconnected_at is not None
    assert result["flagged"] == 1


# ---------------------------------------------------------------------------
# Test 2 — Grace period expired → session transitions to 'expired'
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_grace_period_expired_sets_expired() -> None:
    """Disconnected session older than grace period → status becomes expired."""
    from app.domain.models.proctor import ExamSession, SessionStatus
    from app.tasks.proctor_tasks import _check_heartbeat_async

    session_id = uuid.uuid4()
    session = MagicMock(spec=ExamSession)
    session.id = session_id
    session.status = SessionStatus.disconnected
    session.consecutive_missed_heartbeats = 3
    session.disconnected_at = datetime.now(UTC) - timedelta(seconds=200)  # past 120s grace
    session.last_heartbeat_at = datetime.now(UTC) - timedelta(seconds=250)

    # Mock active sessions result (empty) and disconnected sessions result (one session)
    mock_active_scalars = MagicMock()
    mock_active_scalars.scalars.return_value.all.return_value = []

    mock_disconnected_scalars = MagicMock()
    mock_disconnected_scalars.scalars.return_value.all.return_value = [session]

    # Branch B queries NetworkGap to close open gap
    mock_gap_scalars = MagicMock()
    mock_gap_scalars.scalars.return_value.first.return_value = None  # no open gap to close

    mock_db = AsyncMock()
    mock_db.execute = AsyncMock(
        side_effect=[mock_active_scalars, mock_disconnected_scalars, mock_gap_scalars]
    )
    mock_db.add = MagicMock()
    mock_db.commit = AsyncMock()
    mock_db.__aenter__ = AsyncMock(return_value=mock_db)
    mock_db.__aexit__ = AsyncMock(return_value=False)

    mock_redis = MagicMock()
    mock_redis.exists.return_value = False
    mock_redis.setex = MagicMock()
    mock_redis.publish = MagicMock()
    mock_redis.close = MagicMock()

    mock_settings = MagicMock()
    mock_settings.redis_url = "redis://localhost:6379/0"
    mock_settings.heartbeat_disconnected_threshold = 3
    mock_settings.session_reconnect_grace_period_seconds = 120

    with (
        patch("app.core.database.celery_db", return_value=mock_db),
        patch("redis.from_url", return_value=mock_redis),
        patch("app.tasks.proctor_tasks.settings", mock_settings),
    ):
        result = await _check_heartbeat_async()

    assert session.status == SessionStatus.expired
    assert session.termination_reason == "reconnect_grace_period_expired"
    assert session.ended_at is not None
    assert result["expired"] == 1


# ---------------------------------------------------------------------------
# Test 3 — New config settings have correct default values
# ---------------------------------------------------------------------------


def test_new_config_settings_have_correct_defaults() -> None:
    """Both new disconnection settings have correct default values."""
    from app.core.config import Settings

    s = Settings()
    assert s.heartbeat_disconnected_threshold == 3
    assert s.session_reconnect_grace_period_seconds == 120
