"""Unit tests for the teacher course portfolio dashboard (FR-4.30)."""

from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, MagicMock

from app.domain.models.exam import (
    ClassMember,
    ExamAttempt,
    ExamBank,
    ExamTest,
    Quarter,
    SchoolClass,
    TestAssignment,
    TestStatus,
)
from app.domain.services import teacher_courses_service as svc

ORG = uuid.UUID("aaaaaaaa-0000-0000-0000-000000000001")
TEACHER = uuid.UUID("cccccccc-0000-0000-0000-000000000001")
CLASS_A = uuid.UUID("dddddddd-0000-0000-0000-00000000000a")
CLASS_B = uuid.UUID("dddddddd-0000-0000-0000-00000000000b")


def _bank(code: str | None, name: str | None) -> ExamBank:
    return ExamBank(
        id=uuid.uuid4(),
        org_id=ORG,
        created_by=TEACHER,
        course_code=code,
        course_name=name,
        title_fr="B",
        language="fr",
        passing_score=60.0,
    )


def _test(bank: ExamBank, *, status: TestStatus = TestStatus.published) -> ExamTest:
    t = ExamTest(id=uuid.uuid4(), bank_id=bank.id, title="T", exam_weight=1.0)
    t.status = status
    return t


def _assignment(test: ExamTest, class_id: uuid.UUID, year: str) -> TestAssignment:
    a = TestAssignment(id=uuid.uuid4(), test_id=test.id, class_id=class_id, quarter=Quarter.q1)
    a.school_class = SchoolClass(id=class_id, org_id=ORG, name="C", academic_year=year)
    return a


def _attempt(test_id: uuid.UUID, score: float, status: str = "validated") -> ExamAttempt:
    return ExamAttempt(
        id=uuid.uuid4(),
        test_id=test_id,
        user_id=uuid.uuid4(),
        total_score=score,
        validation_status=status,
    )


def _scalars(items: list) -> MagicMock:
    r = MagicMock()
    r.scalars.return_value.all.return_value = items
    return r


def _db(side_effect: list) -> MagicMock:
    db = MagicMock()
    db.execute = AsyncMock(side_effect=side_effect)
    return db


async def test_empty_when_no_banks() -> None:
    db = _db([_scalars([])])
    assert await svc.list_teacher_courses(db, user_id=TEACHER, org_id=ORG) == []


async def test_two_courses_three_classes() -> None:
    b1 = _bank("CS101", "Intro CS")
    b2 = _bank("CS201", "Data Structures")
    t1 = _test(b1)
    t2 = _test(b2)
    a1 = _assignment(t1, CLASS_A, "2025-2026")
    a2 = _assignment(t2, CLASS_A, "2025-2026")
    a3 = _assignment(t2, CLASS_B, "2025-2026")

    db = _db(
        [
            _scalars([b1, b2]),  # banks
            _scalars([t1, t2]),  # tests
            _scalars([a1, a2, a3]),  # assignments
            _scalars([_attempt(t1.id, 80)]),  # validated attempts
            _scalars([ClassMember(class_id=CLASS_A, user_id=uuid.uuid4())]),  # members
        ]
    )

    rows = await svc.list_teacher_courses(db, user_id=TEACHER, org_id=ORG)
    by_code = {r["course_code"]: r for r in rows}
    assert set(by_code) == {"CS101", "CS201"}
    assert by_code["CS201"]["class_count"] == 2  # CLASS_A + CLASS_B
    assert by_code["CS101"]["avg_score"] == 80.0


async def test_avg_score_none_without_validated_attempts() -> None:
    b1 = _bank("CS101", "Intro CS")
    t1 = _test(b1)
    a1 = _assignment(t1, CLASS_A, "2025-2026")

    db = _db(
        [
            _scalars([b1]),
            _scalars([t1]),
            _scalars([a1]),
            _scalars([]),  # no validated attempts
            _scalars([]),  # members
        ]
    )

    rows = await svc.list_teacher_courses(db, user_id=TEACHER, org_id=ORG)
    assert rows[0]["avg_score"] is None


async def test_uncategorised_bucket_for_null_course_code() -> None:
    b1 = _bank(None, None)
    t1 = _test(b1)
    a1 = _assignment(t1, CLASS_A, "2025-2026")

    db = _db(
        [
            _scalars([b1]),
            _scalars([t1]),
            _scalars([a1]),
            _scalars([]),
            _scalars([]),
        ]
    )

    rows = await svc.list_teacher_courses(db, user_id=TEACHER, org_id=ORG)
    assert rows[0]["course_code"] == "Uncategorised"


async def test_test_count_only_published() -> None:
    b1 = _bank("CS101", "Intro CS")
    t_pub = _test(b1, status=TestStatus.published)
    t_draft = _test(b1, status=TestStatus.draft)
    a1 = _assignment(t_pub, CLASS_A, "2025-2026")

    db = _db(
        [
            _scalars([b1]),
            _scalars([t_pub, t_draft]),
            _scalars([a1]),
            _scalars([]),
            _scalars([]),
        ]
    )

    rows = await svc.list_teacher_courses(db, user_id=TEACHER, org_id=ORG)
    assert rows[0]["test_count"] == 1  # only the published test
