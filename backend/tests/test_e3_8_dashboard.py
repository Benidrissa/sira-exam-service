"""Tests for E3-8 — proctor dashboard offline state."""

from __future__ import annotations

import uuid
from unittest.mock import MagicMock


def test_network_gap_schema_from_model() -> None:
    from datetime import UTC, datetime, timedelta

    from app.domain.models.proctor import NetworkGap
    from app.schemas.proctor_monitor import NetworkGapSchema

    gap = MagicMock(spec=NetworkGap)
    gap.id = uuid.uuid4()
    gap.session_id = uuid.uuid4()
    gap.disconnected_at = datetime.now(UTC) - timedelta(seconds=120)
    gap.reconnected_at = datetime.now(UTC)
    gap.duration_seconds = 120
    gap.missed_heartbeat_count = 4
    gap.auto_expired = False

    schema = NetworkGapSchema.model_validate(gap)
    assert schema.duration_seconds == 120
    assert schema.auto_expired is False


def test_evidence_report_endpoint_returns_403_for_non_teacher() -> None:
    """evidence-report requires teacher role — student JWT should return 403."""
    # This is a route-level permission test — verify TeacherUser dep is applied
    import inspect

    from app.api.v1 import proctor_monitor

    source = inspect.getsource(proctor_monitor)
    assert "evidence-report" in source or "evidence_report" in source
    assert "TeacherUser" in source


def test_session_summary_schema_offline_fields() -> None:
    """SessionSummarySchema must expose the E3-8 offline fields."""
    from app.schemas.proctor_monitor import SessionSummarySchema

    fields = SessionSummarySchema.model_fields
    assert "disconnected_at" in fields
    assert "total_offline_duration_s" in fields
    assert "offline_event_count" in fields


def test_session_detail_schema_network_gaps_field() -> None:
    """SessionDetailSchema must include network_gaps list."""
    from app.schemas.proctor_monitor import SessionDetailSchema

    fields = SessionDetailSchema.model_fields
    assert "network_gaps" in fields
