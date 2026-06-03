"""Student term-score aggregation per course (FR-4.27).

Builds, for the requesting student, one group per
(course_code, course_name, class_id, class_name, academic_year, quarter)
containing every exam assigned to the student's classes, with the student's
score, dispensation, and feedback availability, plus the weighted average and
letter grade.
"""

from __future__ import annotations

import uuid
from datetime import UTC
from datetime import datetime as dt

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.domain.models.exam import (
    ClassMember,
    ExamAttempt,
    ExamBank,
    ExamDispensation,
    ExamTest,
    TestAssignment,
)
from app.domain.services import grade_calc


async def get_student_course_summary(
    db: AsyncSession, *, user_id: uuid.UUID, org_id: uuid.UUID
) -> list[dict]:
    """Return the student's per-course/term grade groups."""
    now = dt.now(tz=UTC)

    member_result = await db.execute(
        select(ClassMember.class_id).where(ClassMember.user_id == user_id)
    )
    class_ids = list(member_result.scalars().all())
    if not class_ids:
        return []

    asgn_result = await db.execute(
        select(TestAssignment)
        .options(
            selectinload(TestAssignment.school_class),
            selectinload(TestAssignment.test).selectinload(ExamTest.bank),
        )
        .join(ExamTest, TestAssignment.test_id == ExamTest.id)
        .join(ExamBank, ExamTest.bank_id == ExamBank.id)
        .where(TestAssignment.class_id.in_(class_ids), ExamBank.org_id == org_id)
    )
    assignments = list(asgn_result.scalars().all())
    if not assignments:
        return []

    test_ids = [a.test_id for a in assignments]

    attempt_result = await db.execute(
        select(ExamAttempt).where(
            ExamAttempt.user_id == user_id,
            ExamAttempt.test_id.in_(test_ids),
            ExamAttempt.mcq_answers.isnot(None),
        )
    )
    attempts = {a.test_id: a for a in attempt_result.scalars().all()}

    disp_result = await db.execute(
        select(ExamDispensation.test_id).where(
            ExamDispensation.student_id == user_id,
            ExamDispensation.test_id.in_(test_ids),
        )
    )
    dispensed_test_ids = set(disp_result.scalars().all())

    # group_key -> {meta, exams: [ExamGrade], rows: [dict]}
    groups: dict[tuple, dict] = {}

    for asgn in assignments:
        test = asgn.test
        bank = test.bank
        # FR-4.27: legacy attempts/tests without a course_code are excluded.
        if bank.course_code is None:
            continue

        sc = asgn.school_class
        key = (
            bank.course_code,
            bank.course_name,
            asgn.class_id,
            sc.name,
            sc.academic_year,
            asgn.quarter,
        )

        feedback_available = grade_calc.compute_feedback_available(
            show_feedback=bool(test.show_feedback),
            closes_ats=[asgn.closes_at],
            now=now,
        )
        attempt = attempts.get(test.id)
        submitted = attempt is not None
        dispensed = test.id in dispensed_test_ids
        reveal = submitted and feedback_available and not dispensed
        score = attempt.total_score if reveal else None
        passed = attempt.passed if reveal else None

        grp = groups.setdefault(
            key,
            {
                "course_code": bank.course_code,
                "course_name": bank.course_name,
                "class_id": asgn.class_id,
                "class_name": sc.name,
                "academic_year": sc.academic_year,
                "quarter": asgn.quarter,
                "class_archived_at": sc.archived_at,
                "exams": [],
                "_grades": [],
            },
        )
        grp["exams"].append(
            {
                "test_id": test.id,
                "test_title": test.title,
                "exam_weight": test.exam_weight,
                "score": score,
                "passed": passed,
                "dispensed": dispensed,
                "feedback_available": feedback_available,
                "attempt_id": attempt.id if submitted else None,
            }
        )
        grp["_grades"].append(
            grade_calc.ExamGrade(
                score=attempt.total_score if submitted else None,
                weight=test.exam_weight,
                submitted=submitted,
                dispensed=dispensed,
                feedback_available=feedback_available,
            )
        )

    result: list[dict] = []
    for grp in groups.values():
        grades = grp.pop("_grades")
        weighted_avg = grade_calc.weighted_average(grades)
        grp["weighted_avg"] = weighted_avg
        grp["grade_letter"] = await grade_calc.resolve_letter_grade(
            db, org_id=org_id, score=weighted_avg
        )
        result.append(grp)

    return result
