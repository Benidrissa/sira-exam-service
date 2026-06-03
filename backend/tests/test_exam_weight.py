"""Unit tests for exam_weight / coefficient per test (FR-4.26) — schema layer.

These validate the Pydantic contract for the exam_weight field on the test
create/update/response schemas plus the read-row schemas. No database needed.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from app.schemas.exam import (
    AttemptSubmissionSummary,
    ExamTestCreate,
    ExamTestResponse,
    ExamTestUpdate,
    StudentAttemptHistoryItem,
)


def test_create_defaults_weight_to_one() -> None:
    """AC3: omitting exam_weight on create defaults to 1.0."""
    test = ExamTestCreate(title="Midterm")
    assert test.exam_weight == 1.0


def test_create_accepts_weight_in_range() -> None:
    """AC1: a valid weight is stored on the model."""
    test = ExamTestCreate(title="Midterm", exam_weight=30)
    assert test.exam_weight == 30


@pytest.mark.parametrize("weight", [0.0, 100.0])
def test_create_accepts_boundaries(weight: float) -> None:
    assert ExamTestCreate(title="x", exam_weight=weight).exam_weight == weight


@pytest.mark.parametrize("weight", [-0.1, 100.1, 110])
def test_create_rejects_out_of_range(weight: float) -> None:
    """AC4: exam_weight outside 0-100 is a validation error (→ 422)."""
    with pytest.raises(ValidationError):
        ExamTestCreate(title="x", exam_weight=weight)


def test_update_accepts_partial_weight() -> None:
    """AC2: PATCH may set exam_weight on its own."""
    upd = ExamTestUpdate(exam_weight=70)
    assert upd.exam_weight == 70
    # exclude_none keeps only the supplied field (mirrors update_exam_test)
    assert upd.model_dump(exclude_none=True) == {"exam_weight": 70.0}


def test_update_rejects_out_of_range() -> None:
    with pytest.raises(ValidationError):
        ExamTestUpdate(exam_weight=110)


def test_update_weight_is_optional() -> None:
    assert ExamTestUpdate(title="renamed").exam_weight is None


def test_response_exposes_weight() -> None:
    """ExamTestResponse surfaces exam_weight back to the client."""
    now = datetime.now(UTC)
    payload = {
        "id": uuid.uuid4(),
        "bank_id": uuid.uuid4(),
        "created_by": uuid.uuid4(),
        "title": "Final",
        "mode": "exam",
        "question_count": 10,
        "shuffle_questions": True,
        "time_limit_minutes": 60,
        "show_feedback": False,
        "mcq_weight": 1.0,
        "dissertation_weight": 1.0,
        "exam_weight": 70.0,
        "status": "published",
        "anonymous_grading": False,
        "created_at": now,
        "updated_at": now,
    }
    resp = ExamTestResponse(**payload)
    assert resp.exam_weight == 70.0


def test_submission_summary_carries_weight() -> None:
    """AC5: teacher submission rows include exam_weight."""
    row = AttemptSubmissionSummary(
        attempt_id=uuid.uuid4(),
        user_id=uuid.uuid4(),
        attempted_at=datetime.now(UTC),
        time_taken_sec=120,
        mcq_score=80.0,
        total_score=80.0,
        passed=True,
        validation_status="validated",
        exam_weight=30.0,
        pending_count=0,
        ai_scored_count=0,
        human_reviewed_count=0,
    )
    assert row.exam_weight == 30.0


def test_student_history_carries_weight() -> None:
    """AC5: student history rows include exam_weight."""
    row = StudentAttemptHistoryItem(
        attempt_id=uuid.uuid4(),
        test_id=uuid.uuid4(),
        test_title="Midterm",
        attempted_at=datetime.now(UTC),
        total_score=60.0,
        passed=True,
        validation_status="validated",
        exam_weight=70.0,
    )
    assert row.exam_weight == 70.0
