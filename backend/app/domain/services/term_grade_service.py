"""Bulk term finalisation per course (FR-4.32).

Recomputes each enrolled student's weighted term average + letter grade for a
(course, class, academic_year, quarter) and writes a TermGrade row. Existing
live rows for the same key are superseded (non-destructive).
"""

from __future__ import annotations

import uuid
from datetime import UTC
from datetime import datetime as dt

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.domain.models.exam import (
    ClassMember,
    ExamAttempt,
    ExamBank,
    ExamDispensation,
    ExamTest,
    SchoolClass,
    TermGrade,
    TestAssignment,
)
from app.domain.services import grade_calc


async def finalize_term(
    db: AsyncSession,
    *,
    org_id: uuid.UUID,
    course_code: str,
    class_id: uuid.UUID,
    academic_year: str,
    quarter: str,
) -> dict:
    """Finalise term grades for a course+class+year+quarter.

    422 if any submitted attempt for the in-scope tests is not validated.
    """
    now = dt.now(tz=UTC)

    # Tests in this course (org-scoped) that are assigned to this class+quarter.
    asgn_result = await db.execute(
        select(TestAssignment)
        .options(selectinload(TestAssignment.test).selectinload(ExamTest.bank))
        .join(ExamTest, TestAssignment.test_id == ExamTest.id)
        .join(ExamBank, ExamTest.bank_id == ExamBank.id)
        .join(SchoolClass, TestAssignment.class_id == SchoolClass.id)
        .where(
            TestAssignment.class_id == class_id,
            TestAssignment.quarter == quarter,
            ExamBank.org_id == org_id,
            ExamBank.course_code == course_code,
            SchoolClass.academic_year == academic_year,
        )
    )
    assignments = list(asgn_result.scalars().all())
    tests = {a.test.id: a.test for a in assignments}
    closes_by_test = {a.test_id: a.closes_at for a in assignments}
    test_ids = list(tests.keys())

    # Enrolled students.
    member_result = await db.execute(
        select(ClassMember.user_id).where(ClassMember.class_id == class_id)
    )
    student_ids = list(member_result.scalars().all())

    if not test_ids or not student_ids:
        return {"finalized_count": 0, "errors": []}

    # All submitted attempts for these tests.
    attempt_result = await db.execute(
        select(ExamAttempt).where(
            ExamAttempt.test_id.in_(test_ids),
            ExamAttempt.mcq_answers.isnot(None),
        )
    )
    attempts = list(attempt_result.scalars().all())

    # Guard: every submitted attempt must be validated.
    unvalidated = [str(a.id) for a in attempts if a.validation_status != "validated"]
    if unvalidated:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={"unvalidated_attempt_ids": unvalidated},
        )

    attempts_by_student: dict[uuid.UUID, dict[uuid.UUID, ExamAttempt]] = {}
    for a in attempts:
        attempts_by_student.setdefault(a.user_id, {})[a.test_id] = a

    # Dispensations for these tests.
    disp_result = await db.execute(
        select(ExamDispensation.student_id, ExamDispensation.test_id).where(
            ExamDispensation.test_id.in_(test_ids)
        )
    )
    dispensed_pairs = {(s, t) for s, t in disp_result.all()}

    finalized = 0
    errors: list[dict] = []
    for student_id in student_ids:
        student_attempts = attempts_by_student.get(student_id, {})
        grades = []
        for test_id, test in tests.items():
            feedback_available = grade_calc.compute_feedback_available(
                show_feedback=bool(test.show_feedback),
                closes_ats=[closes_by_test.get(test_id)],
                now=now,
            )
            attempt = student_attempts.get(test_id)
            grades.append(
                grade_calc.ExamGrade(
                    score=attempt.total_score if attempt else None,
                    weight=test.exam_weight,
                    submitted=attempt is not None,
                    dispensed=(student_id, test_id) in dispensed_pairs,
                    feedback_available=feedback_available,
                )
            )

        weighted_avg = grade_calc.weighted_average(grades)
        grade_letter = await grade_calc.resolve_letter_grade(db, org_id=org_id, score=weighted_avg)

        # Idempotent supersede: point any live row at the new authoritative one.
        existing_result = await db.execute(
            select(TermGrade).where(
                TermGrade.student_id == student_id,
                TermGrade.course_code == course_code,
                TermGrade.class_id == class_id,
                TermGrade.academic_year == academic_year,
                TermGrade.quarter == quarter,
                TermGrade.superseded_by.is_(None),
            )
        )
        live_rows = list(existing_result.scalars().all())

        new_grade = TermGrade(
            org_id=org_id,
            student_id=student_id,
            course_code=course_code,
            class_id=class_id,
            academic_year=academic_year,
            quarter=quarter,
            weighted_avg=weighted_avg,
            grade_letter=grade_letter,
        )
        db.add(new_grade)
        await db.flush()
        for row in live_rows:
            row.superseded_by = new_grade.id
        finalized += 1

    await db.commit()
    return {"finalized_count": finalized, "errors": errors}
