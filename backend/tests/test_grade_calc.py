"""Unit tests for the shared grade-calc helpers (FR-4.27/4.31/4.32)."""

from __future__ import annotations

import uuid
from datetime import UTC, timedelta
from datetime import datetime as dt
from unittest.mock import AsyncMock, MagicMock

from app.domain.services import grade_calc
from app.domain.services.grade_calc import ExamGrade

ORG = uuid.UUID("aaaaaaaa-0000-0000-0000-000000000001")


# --- compute_feedback_available --------------------------------------------


def test_feedback_available_when_show_feedback() -> None:
    assert grade_calc.compute_feedback_available(show_feedback=True, closes_ats=[None]) is True


def test_feedback_available_when_window_closed() -> None:
    past = dt.now(tz=UTC) - timedelta(hours=1)
    assert grade_calc.compute_feedback_available(show_feedback=False, closes_ats=[past]) is True


def test_feedback_unavailable_when_open_and_no_flag() -> None:
    future = dt.now(tz=UTC) + timedelta(hours=1)
    assert grade_calc.compute_feedback_available(show_feedback=False, closes_ats=[future]) is False


def test_feedback_unavailable_when_no_assignments() -> None:
    assert grade_calc.compute_feedback_available(show_feedback=False, closes_ats=[]) is False


# --- weighted_average -------------------------------------------------------


def _g(score, weight, *, submitted=True, dispensed=False, feedback=True) -> ExamGrade:
    return ExamGrade(
        score=score,
        weight=weight,
        submitted=submitted,
        dispensed=dispensed,
        feedback_available=feedback,
    )


def test_weighted_average_basic() -> None:
    # AC1: weights 30 & 70, scores 80 & 60 -> 66.0
    avg = grade_calc.weighted_average([_g(80, 30), _g(60, 70)])
    assert avg == 66.0


def test_weighted_average_excludes_dispensed() -> None:
    # AC2: adding a dispensed exam does not change the average
    avg = grade_calc.weighted_average([_g(80, 30), _g(60, 70), _g(0, 40, dispensed=True)])
    assert avg == 66.0


def test_weighted_average_excludes_unsubmitted() -> None:
    avg = grade_calc.weighted_average([_g(80, 30), _g(60, 70), _g(None, 50, submitted=False)])
    assert avg == 66.0


def test_weighted_average_excludes_feedback_unavailable() -> None:
    # AC3: a feedback-locked exam is excluded from the average
    avg = grade_calc.weighted_average([_g(80, 30), _g(60, 70), _g(100, 50, feedback=False)])
    assert avg == 66.0


def test_weighted_average_none_when_no_contributors() -> None:
    assert grade_calc.weighted_average([_g(None, 30, submitted=False)]) is None
    assert grade_calc.weighted_average([]) is None


def test_weighted_average_zero_denominator_is_none_not_zero() -> None:
    assert grade_calc.weighted_average([_g(90, 0)]) is None


# --- resolve_letter_grade ---------------------------------------------------


async def test_resolve_letter_grade_uses_org_scale() -> None:
    db = MagicMock()
    result = MagicMock()
    result.scalars.return_value.all.return_value = []  # -> default scale
    db.execute = AsyncMock(return_value=result)

    assert await grade_calc.resolve_letter_grade(db, org_id=ORG, score=85) == "B"
    assert await grade_calc.resolve_letter_grade(db, org_id=ORG, score=None) is None
