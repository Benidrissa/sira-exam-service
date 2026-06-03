"""Unit tests for bulk term finalization (FR-4.32) — service layer."""

from __future__ import annotations

import uuid
from datetime import UTC, timedelta
from datetime import datetime as dt
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import HTTPException

from app.domain.models.exam import (
    ExamAttempt,
    ExamTest,
    Quarter,
    TermGrade,
    TestAssignment,
)
from app.domain.services import term_grade_service as svc

ORG = uuid.UUID("aaaaaaaa-0000-0000-0000-000000000001")
STUDENT = uuid.UUID("11111111-0000-0000-0000-000000000001")
CLASS_ID = uuid.UUID("dddddddd-0000-0000-0000-000000000009")
PAST = dt.now(tz=UTC) - timedelta(days=1)


def _test(weight: float) -> ExamTest:
    t = ExamTest(id=uuid.uuid4(), bank_id=uuid.uuid4(), title="T", exam_weight=weight)
    t.show_feedback = False
    return t


def _assignment(test: ExamTest) -> TestAssignment:
    a = TestAssignment(id=uuid.uuid4(), test_id=test.id, class_id=CLASS_ID, quarter=Quarter.q1)
    a.closes_at = PAST
    a.test = test
    return a


def _attempt(test_id: uuid.UUID, score: float, status: str = "validated") -> ExamAttempt:
    return ExamAttempt(
        id=uuid.uuid4(),
        test_id=test_id,
        user_id=STUDENT,
        total_score=score,
        passed=score >= 60,
        validation_status=status,
    )


def _scalars(items: list) -> MagicMock:
    r = MagicMock()
    r.scalars.return_value.all.return_value = items
    return r


def _rows(items: list) -> MagicMock:
    r = MagicMock()
    r.all.return_value = items
    return r


def _db(side_effect: list) -> MagicMock:
    db = MagicMock()
    db.execute = AsyncMock(side_effect=side_effect)
    db.commit = AsyncMock()
    added: list = []
    db.add = lambda obj: added.append(obj)

    async def _flush() -> None:
        if added and getattr(added[-1], "id", None) is None:
            added[-1].id = uuid.uuid4()

    db.flush = AsyncMock(side_effect=_flush)
    db._added = added
    return db


async def test_finalize_success_one_student() -> None:
    t1 = _test(30)
    t2 = _test(70)
    db = _db(
        [
            _scalars([_assignment(t1), _assignment(t2)]),  # assignments
            _scalars([STUDENT]),  # members
            _scalars([_attempt(t1.id, 80), _attempt(t2.id, 60)]),  # attempts (validated)
            _rows([]),  # dispensations
            _scalars([]),  # resolve_letter_grade -> get_scale (default)
            _scalars([]),  # existing live TermGrade (none)
        ]
    )

    result = await svc.finalize_term(
        db,
        org_id=ORG,
        course_code="CS101",
        class_id=CLASS_ID,
        academic_year="2025-2026",
        quarter="q1",
    )
    assert result["finalized_count"] == 1
    assert result["errors"] == []
    new_grade = db._added[-1]
    assert isinstance(new_grade, TermGrade)
    assert new_grade.weighted_avg == 66.0
    assert new_grade.grade_letter == "D"
    db.commit.assert_awaited_once()


async def test_finalize_blocks_on_unvalidated_attempt() -> None:
    t1 = _test(50)
    bad = _attempt(t1.id, 80, status="pending")
    db = _db(
        [
            _scalars([_assignment(t1)]),
            _scalars([STUDENT]),
            _scalars([bad]),  # an unvalidated attempt
        ]
    )

    with pytest.raises(HTTPException) as exc:
        await svc.finalize_term(
            db,
            org_id=ORG,
            course_code="CS101",
            class_id=CLASS_ID,
            academic_year="2025-2026",
            quarter="q1",
        )
    assert exc.value.status_code == 422
    assert str(bad.id) in exc.value.detail["unvalidated_attempt_ids"]


async def test_refinalize_supersedes_live_row() -> None:
    t1 = _test(100)
    old = TermGrade(
        id=uuid.uuid4(),
        org_id=ORG,
        student_id=STUDENT,
        course_code="CS101",
        class_id=CLASS_ID,
        academic_year="2025-2026",
        quarter=Quarter.q1,
    )
    old.superseded_by = None

    db = _db(
        [
            _scalars([_assignment(t1)]),
            _scalars([STUDENT]),
            _scalars([_attempt(t1.id, 90)]),
            _rows([]),  # dispensations
            _scalars([]),  # get_scale
            _scalars([old]),  # existing live row
        ]
    )

    result = await svc.finalize_term(
        db,
        org_id=ORG,
        course_code="CS101",
        class_id=CLASS_ID,
        academic_year="2025-2026",
        quarter="q1",
    )
    assert result["finalized_count"] == 1
    new_grade = db._added[-1]
    assert old.superseded_by == new_grade.id  # old row points at the new one


async def test_only_dispensed_student_gets_null_average() -> None:
    t1 = _test(50)
    db = _db(
        [
            _scalars([_assignment(t1)]),
            _scalars([STUDENT]),
            _scalars([]),  # no submitted attempts
            _rows([(STUDENT, t1.id)]),  # student dispensed from the only exam
            _scalars([]),  # get_scale (score None -> not actually queried, but harmless)
            _scalars([]),  # existing
        ]
    )

    result = await svc.finalize_term(
        db,
        org_id=ORG,
        course_code="CS101",
        class_id=CLASS_ID,
        academic_year="2025-2026",
        quarter="q1",
    )
    new_grade = db._added[-1]
    assert new_grade.weighted_avg is None
    assert new_grade.grade_letter is None
    assert result["finalized_count"] == 1
