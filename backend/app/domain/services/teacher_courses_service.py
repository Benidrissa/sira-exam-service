"""Teacher course portfolio dashboard (FR-4.30).

Aggregates a teacher's own exam banks into course cards keyed by
(course_code, course_name, academic_year), where academic_year is derived from
the classes the banks' tests are assigned to. Banks without a course_code are
grouped under "Uncategorised".
"""

from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.domain.models.exam import (
    ClassMember,
    ExamAttempt,
    ExamBank,
    ExamTest,
    TestAssignment,
    TestStatus,
)

UNCATEGORISED = "Uncategorised"


async def list_teacher_courses(
    db: AsyncSession,
    *,
    user_id: uuid.UUID,
    org_id: uuid.UUID,
    academic_year: str | None = None,
    quarter: str | None = None,
) -> list[dict]:
    """Return course cards for the teacher's own banks."""
    bank_result = await db.execute(
        select(ExamBank).where(ExamBank.created_by == user_id, ExamBank.org_id == org_id)
    )
    banks = {b.id: b for b in bank_result.scalars().all()}
    if not banks:
        return []

    test_result = await db.execute(select(ExamTest).where(ExamTest.bank_id.in_(list(banks.keys()))))
    tests = list(test_result.scalars().all())
    if not tests:
        return []
    tests_by_id = {t.id: t for t in tests}
    test_ids = list(tests_by_id.keys())

    asgn_result = await db.execute(
        select(TestAssignment)
        .options(selectinload(TestAssignment.school_class))
        .where(TestAssignment.test_id.in_(test_ids))
    )
    assignments = list(asgn_result.scalars().all())
    if quarter is not None:
        assignments = [a for a in assignments if a.quarter.value == quarter]
    if academic_year is not None:
        assignments = [a for a in assignments if a.school_class.academic_year == academic_year]

    # validated attempts for avg_score
    attempt_result = await db.execute(
        select(ExamAttempt).where(
            ExamAttempt.test_id.in_(test_ids),
            ExamAttempt.validation_status == "validated",
        )
    )
    attempts = list(attempt_result.scalars().all())

    # members per class for student_count
    class_ids = {a.class_id for a in assignments}
    members_by_class: dict[uuid.UUID, set[uuid.UUID]] = {}
    if class_ids:
        member_result = await db.execute(
            select(ClassMember).where(ClassMember.class_id.in_(list(class_ids)))
        )
        for m in member_result.scalars().all():
            members_by_class.setdefault(m.class_id, set()).add(m.user_id)

    # group_key (code, name, academic_year) -> aggregate
    groups: dict[tuple, dict] = {}

    def _key(bank: ExamBank, year: str | None) -> tuple:
        return (bank.course_code or UNCATEGORISED, bank.course_name, year)

    # Seed groups from assignments (gives academic_year + classes)
    for asgn in assignments:
        test = tests_by_id.get(asgn.test_id)
        if test is None:
            continue
        bank = banks[test.bank_id]
        key = _key(bank, asgn.school_class.academic_year)
        grp = groups.setdefault(key, _new_group(key))
        grp["_class_ids"].add(asgn.class_id)
        grp["_test_ids"].add(test.id)

    # Banks with no (filtered) assignments still surface as a course card,
    # unless a year/quarter filter is active (then they're out of scope).
    if academic_year is None and quarter is None:
        assigned_bank_ids = {
            tests_by_id[a.test_id].bank_id for a in assignments if a.test_id in tests_by_id
        }
        for bank in banks.values():
            if bank.id in assigned_bank_ids:
                continue
            key = _key(bank, None)
            groups.setdefault(key, _new_group(key))

    # Finalise counts
    scores_by_test: dict[uuid.UUID, list[float]] = {}
    for at in attempts:
        if at.total_score is not None:
            scores_by_test.setdefault(at.test_id, []).append(at.total_score)

    result: list[dict] = []
    for key, grp in groups.items():
        class_set = grp.pop("_class_ids")
        # include all published tests of the banks behind this course/year
        course_test_ids = {
            t.id
            for t in tests
            if (banks[t.bank_id].course_code or UNCATEGORISED, banks[t.bank_id].course_name)
            == (key[0], key[1])
        }
        published = [
            tests_by_id[tid]
            for tid in course_test_ids
            if tests_by_id[tid].status == TestStatus.published
        ]
        all_scores = [s for tid in course_test_ids for s in scores_by_test.get(tid, [])]

        students: set[uuid.UUID] = set()
        for cid in class_set:
            students |= members_by_class.get(cid, set())

        grp["class_count"] = len(class_set)
        grp["student_count"] = len(students)
        grp["test_count"] = len(published)
        grp["avg_score"] = (sum(all_scores) / len(all_scores)) if all_scores else None
        grp.pop("_test_ids", None)
        result.append(grp)

    return result


def _new_group(key: tuple) -> dict:
    return {
        "course_code": key[0],
        "course_name": key[1],
        "academic_year": key[2],
        "_class_ids": set(),
        "_test_ids": set(),
    }
