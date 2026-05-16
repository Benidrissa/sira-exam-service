"""Tests for E3-1: Claude Vision prompt caching + adaptive snapshot_interval_ms."""

from __future__ import annotations


def test_proctoring_system_prompt_exceeds_cache_threshold() -> None:
    """PROCTORING_SYSTEM_PROMPT must be at least 4000 characters for >1024 token cache threshold."""
    from app.tasks.proctor_tasks import PROCTORING_SYSTEM_PROMPT

    assert len(PROCTORING_SYSTEM_PROMPT) >= 4000, (
        f"Prompt too short: {len(PROCTORING_SYSTEM_PROMPT)} chars"
    )


def test_snapshot_interval_ms_default_is_10000() -> None:
    """ExamSession.snapshot_interval_ms default must be 10000ms (10s)."""
    from app.domain.models.proctor import ExamSession

    col = ExamSession.__table__.c.get("snapshot_interval_ms")
    assert col is not None
    assert col.default.arg == 10_000 or str(col.server_default.arg) == "10000"
