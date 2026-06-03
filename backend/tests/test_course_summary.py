"""Unit tests for student term-score aggregation (FR-4.27) — service layer."""

from __future__ import annotations

import uuid
from datetime import UTC, timedelta
from datetime import datetime as dt
from unittest.mock import AsyncMock, MagicMock

from app.domain.models.exam import (
    ExamAttempt,
    ExamBank,
    ExamTest,
    Quarter,
    SchoolClass,
    TestAssignment,
)
from app.domain.services import course_summary_service as svc

ORG = uuid.UUID("aaaaaaaa-0000-0000-0000-000000000001")
STUDENT = uuid.UUID("11111111-0000-0000-0000-000000000001")
CLASS_ID = uuid.UUID("dddddddd-0000-0000-0000-000000000009")

PAST = dt.now(tz=UTC) - timedelta(days=1)
FUTURE = dt.now(tz=UTC) + timedelta(days=1)


def _bank(course_code: str | None) -> ExamBank:
    return ExamBank(
        id=uuid.uuid4(),
        org_id=ORG,
        course_code=course_code,
        course_name="Algorithms" if course_code else None,
        title_fr="B",
        language="fr",
        passing_score=60.0,
    )


def _test(bank: ExamBank, *, weight: float, show_feedback: bool = False) -> ExamTest:
    t = ExamTest(id=uuid.uuid4(), bank_id=bank.id, title="Exam", exam_weight=weight)
    t.show_feedback = show_feedback
    t.bank = bank
    return t


def _assignment(test: ExamTest, *, closes_at: dt) -> TestAssignment:
    a = TestAssignment(
        id=uuid.uuid4(),
        test_id=test.id,
        class_id=CLASS_ID,
        quarter=Quarter.q1,
        closes_at=closes_at,
    )
    a.test = test
    a.school_class = SchoolClass(id=CLASS_ID, org_id=ORG, name="CS-1", academic_year="2025-2026")
    a.school_class.archived_at = None
    return a


def _attempt(test_id: uuid.UUID, *, score: float) -> ExamAttempt:
    return ExamAttempt(
        id=uuid.uuid4(),
        test_id=test_id,
        user_id=STUDENT,
        total_score=score,
        passed=score >= 60,
    )


def _scalars(items: list) -> MagicMock:
    r = MagicMock()
    r.scalars.return_value.all.return_value = items
    return r


def _db(side_effect: list) -> MagicMock:
    db = MagicMock()
    db.execute = AsyncMock(side_effect=side_effect)
    return db


async def test_empty_when_no_class_membership() -> None:
    db = _db([_scalars([])])  # no ClassMember rows
    assert await svc.get_student_course_summary(db, user_id=STUDENT, org_id=ORG) == []


async def test_weighted_average_two_closed_exams() -> None:
    bank = _bank("CS101")
    t1 = _test(bank, weight=30)
    t2 = _test(bank, weight=70)
    a1 = _assignment(t1, closes_at=PAST)  # closed -> feedback available
    a2 = _assignment(t2, closes_at=PAST)
    at1 = _attempt(t1.id, score=80)
    at2 = _attempt(t2.id, score=60)

    db = _db(
        [
            _scalars([CLASS_ID]),  # ClassMember.class_id
            _scalars([a1, a2]),  # assignments
            _scalars([at1, at2]),  # attempts
            _scalars([]),  # dispensations
            _scalars([]),  # resolve_letter_grade -> get_scale (default)
        ]
    )

    groups = await svc.get_student_course_summary(db, user_id=STUDENT, org_id=ORG)
    assert len(groups) == 1
    g = groups[0]
    assert g["weighted_avg"] == 66.0
    assert g["grade_letter"] == "D"  # default scale: 60-69 -> D
    assert len(g["exams"]) == 2


async def test_dispensed_exam_excluded_from_average() -> None:
    bank = _bank("CS101")
    t1 = _test(bank, weight=30)
    t2 = _test(bank, weight=70)
    t3 = _test(bank, weight=40)
    a1 = _assignment(t1, closes_at=PAST)
    a2 = _assignment(t2, closes_at=PAST)
    a3 = _assignment(t3, closes_at=PAST)

    db = _db(
        [
            _scalars([CLASS_ID]),
            _scalars([a1, a2, a3]),
            _scalars([_attempt(t1.id, score=80), _attempt(t2.id, score=60)]),
            _scalars([t3.id]),  # t3 dispensed (no attempt)
            _scalars([]),  # default scale
        ]
    )

    groups = await svc.get_student_course_summary(db, user_id=STUDENT, org_id=ORG)
    g = groups[0]
    assert g["weighted_avg"] == 66.0  # unchanged
    exam3 = next(e for e in g["exams"] if e["test_id"] == t3.id)
    assert exam3["dispensed"] is True
    assert exam3["score"] is None


async def test_feedback_locked_exam_score_hidden_and_excluded() -> None:
    bank = _bank("CS101")
    t1 = _test(bank, weight=50)
    t2 = _test(bank, weight=50)
    a1 = _assignment(t1, closes_at=PAST)  # available
    a2 = _assignment(t2, closes_at=FUTURE)  # still open -> locked

    db = _db(
        [
            _scalars([CLASS_ID]),
            _scalars([a1, a2]),
            _scalars([_attempt(t1.id, score=90), _attempt(t2.id, score=40)]),
            _scalars([]),
            _scalars([]),
        ]
    )

    groups = await svc.get_student_course_summary(db, user_id=STUDENT, org_id=ORG)
    g = groups[0]
    locked = next(e for e in g["exams"] if e["test_id"] == t2.id)
    assert locked["feedback_available"] is False
    assert locked["score"] is None
    # only t1 (90) contributes
    assert g["weighted_avg"] == 90.0


async def test_legacy_course_code_none_excluded() -> None:
    bank = _bank(None)  # legacy, no course_code
    t1 = _test(bank, weight=50)
    a1 = _assignment(t1, closes_at=PAST)

    db = _db(
        [
            _scalars([CLASS_ID]),
            _scalars([a1]),
            _scalars([_attempt(t1.id, score=80)]),
            _scalars([]),
        ]
    )

    groups = await svc.get_student_course_summary(db, user_id=STUDENT, org_id=ORG)
    assert groups == []
