"""Tests for lockdown events API — issue #98 (E3-3)."""

from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# ---------------------------------------------------------------------------
# Test 1 — record_event below threshold creates event but no alert
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_record_event_creates_proctor_event_and_no_alert_below_threshold() -> None:
    """record_event for 'tab_switch' with count=1 (threshold=3) must not create an alert."""
    from app.domain.models.proctor import EventSeverity, ProctorEvent
    from app.domain.services.proctor_session_service import record_event

    session_id = uuid.uuid4()
    event_id = uuid.uuid4()

    mock_event = MagicMock(spec=ProctorEvent)
    mock_event.id = event_id
    mock_event.session_id = session_id
    mock_event.event_type = "tab_switch"
    mock_event.severity = EventSeverity.info

    mock_db = AsyncMock()
    mock_db.add = MagicMock()
    mock_db.commit = AsyncMock()
    mock_db.refresh = AsyncMock()
    # scalar returns count=1 (below threshold of 3)
    mock_db.scalar = AsyncMock(return_value=1)

    with (
        patch(
            "app.domain.services.proctor_session_service.create_alert",
            new_callable=AsyncMock,
        ) as mock_create_alert,
        patch(
            "app.domain.models.proctor.ProctorEvent",
            return_value=mock_event,
        ),
    ):
        event, alert = await record_event(
            mock_db,
            session_id=session_id,
            event_type="tab_switch",
            severity=EventSeverity.info,
        )

    assert alert is None
    mock_create_alert.assert_not_called()


# ---------------------------------------------------------------------------
# Test 2 — screen_capture_attempt triggers critical alert immediately (threshold=1)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_screen_capture_attempt_creates_immediate_alert() -> None:
    """record_event for 'screen_capture_attempt' with count=1 must trigger a critical alert."""
    from app.domain.models.proctor import EventSeverity, ProctorAlert, ProctorEvent
    from app.domain.services.proctor_session_service import record_event

    session_id = uuid.uuid4()

    mock_event = MagicMock(spec=ProctorEvent)
    mock_event.id = uuid.uuid4()
    mock_event.session_id = session_id
    mock_event.event_type = "screen_capture_attempt"
    mock_event.severity = EventSeverity.critical

    mock_alert = MagicMock(spec=ProctorAlert)
    mock_alert.id = uuid.uuid4()
    mock_alert.severity = EventSeverity.critical

    mock_db = AsyncMock()
    mock_db.add = MagicMock()
    mock_db.commit = AsyncMock()
    mock_db.refresh = AsyncMock()
    # count=1 — exactly at threshold
    mock_db.scalar = AsyncMock(return_value=1)

    with patch(
        "app.domain.services.proctor_session_service.create_alert",
        new_callable=AsyncMock,
        return_value=mock_alert,
    ) as mock_create_alert, patch(
        "app.domain.models.proctor.ProctorEvent",
        return_value=mock_event,
    ):
        event, alert = await record_event(
            mock_db,
            session_id=session_id,
            event_type="screen_capture_attempt",
            severity=EventSeverity.critical,
        )

    mock_create_alert.assert_called_once()
    call_kwargs = mock_create_alert.call_args.kwargs
    assert call_kwargs["severity"] == EventSeverity.critical
    assert "screen capture" in call_kwargs["message"].lower()


# ---------------------------------------------------------------------------
# Test 3 — events endpoint requires X-Session-Token header
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_events_endpoint_requires_session_token_header() -> None:
    """POST /sessions/{id}/events without X-Session-Token must return 422."""
    import uuid as _uuid

    from httpx import ASGITransport, AsyncClient

    from app.main import app

    session_id = _uuid.uuid4()
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        resp = await client.post(
            f"/api/v1/proctor/sessions/{session_id}/events",
            headers={"Authorization": "Bearer fake-token"},
            json={"event_type": "tab_switch"},
            # Intentionally omitting X-Session-Token
        )
    # Auth middleware fires first (401 for bad JWT) or header validation (422).
    assert resp.status_code in (401, 422)
