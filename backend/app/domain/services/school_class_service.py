"""SchoolClass service — class roster management, enrollment, test scheduling (FR-4.1–FR-4.6)."""

from __future__ import annotations

import uuid
from datetime import UTC
from datetime import datetime as dt

from fastapi import HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

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

# ---------------------------------------------------------------------------
# SchoolClass CRUD
# ---------------------------------------------------------------------------


async def create_class(
    db: AsyncSession,
    *,
    org_id: uuid.UUID,
    created_by: uuid.UUID,
    name: str,
    academic_year: str,
) -> SchoolClass:
    school_class = SchoolClass(
        org_id=org_id,
        created_by=created_by,
        name=name,
        academic_year=academic_year,
    )
    db.add(school_class)
    try:
        await db.commit()
        await db.refresh(school_class)
    except IntegrityError:
        await db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Class '{name}' for year '{academic_year}' already exists in this org",
        )
    return school_class


async def list_classes(
    db: AsyncSession,
    *,
    org_id: uuid.UUID,
    academic_year: str | None = None,
) -> list[SchoolClass]:
    stmt = select(SchoolClass).where(SchoolClass.org_id == org_id)
    if academic_year is not None:
        stmt = stmt.where(SchoolClass.academic_year == academic_year)
    stmt = stmt.order_by(SchoolClass.created_at.desc())
    result = await db.execute(stmt)
    return list(result.scalars().all())


async def get_class(
    db: AsyncSession,
    *,
    class_id: uuid.UUID,
    org_id: uuid.UUID,
) -> SchoolClass:
    result = await db.execute(
        select(SchoolClass).where(SchoolClass.id == class_id, SchoolClass.org_id == org_id)
    )
    school_class = result.scalar_one_or_none()
    if school_class is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="SchoolClass not found")
    return school_class


async def update_class(
    db: AsyncSession,
    *,
    class_id: uuid.UUID,
    org_id: uuid.UUID,
    name: str | None = None,
    academic_year: str | None = None,
) -> SchoolClass:
    school_class = await get_class(db, class_id=class_id, org_id=org_id)
    if name is not None:
        school_class.name = name
    if academic_year is not None:
        school_class.academic_year = academic_year
    try:
        await db.commit()
        await db.refresh(school_class)
    except IntegrityError:
        await db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="A class with this name and academic year already exists in this org",
        )
    return school_class


async def delete_class(
    db: AsyncSession,
    *,
    class_id: uuid.UUID,
    org_id: uuid.UUID,
) -> None:
    school_class = await get_class(db, class_id=class_id, org_id=org_id)
    # 409 if class has members
    member_count = await db.scalar(
        select(func.count()).select_from(ClassMember).where(ClassMember.class_id == class_id)
    )
    if member_count:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Cannot delete a class that has enrolled members",
        )
    await db.delete(school_class)
    await db.commit()


# ---------------------------------------------------------------------------
# ClassMember enrollment
# ---------------------------------------------------------------------------


async def enroll_student(
    db: AsyncSession,
    *,
    class_id: uuid.UUID,
    org_id: uuid.UUID,
    user_id: uuid.UUID,
    added_by: uuid.UUID,
) -> ClassMember:
    # Verify class belongs to org (raises 404 if not)
    await get_class(db, class_id=class_id, org_id=org_id)

    member = ClassMember(
        class_id=class_id,
        user_id=user_id,
        added_by=added_by,
    )
    db.add(member)
    try:
        await db.commit()
        await db.refresh(member)
    except IntegrityError:
        await db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Student is already enrolled in this class",
        )
    return member


async def remove_member(
    db: AsyncSession,
    *,
    class_id: uuid.UUID,
    org_id: uuid.UUID,
    user_id: uuid.UUID,
) -> None:
    # Verify class belongs to org
    await get_class(db, class_id=class_id, org_id=org_id)

    result = await db.execute(
        select(ClassMember).where(
            ClassMember.class_id == class_id,
            ClassMember.user_id == user_id,
        )
    )
    member = result.scalar_one_or_none()
    if member is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Member not found")
    await db.delete(member)
    await db.commit()


async def list_members(
    db: AsyncSession,
    *,
    class_id: uuid.UUID,
    org_id: uuid.UUID,
) -> list[ClassMember]:
    # Verify class belongs to org
    await get_class(db, class_id=class_id, org_id=org_id)

    result = await db.execute(select(ClassMember).where(ClassMember.class_id == class_id))
    return list(result.scalars().all())


# ---------------------------------------------------------------------------
# TestAssignment scheduling
# ---------------------------------------------------------------------------


async def create_assignment(
    db: AsyncSession,
    *,
    test_id: uuid.UUID,
    class_id: uuid.UUID,
    org_id: uuid.UUID,
    released_at: dt,
    closes_at: dt,
    quarter: Quarter,
    assigned_by: uuid.UUID,
) -> TestAssignment:
    if closes_at <= released_at:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="closes_at must be after released_at",
        )

    # Verify test belongs to org (join through ExamBank)
    result = await db.execute(
        select(ExamTest)
        .join(ExamBank, ExamTest.bank_id == ExamBank.id)
        .where(ExamTest.id == test_id, ExamBank.org_id == org_id)
    )
    test = result.scalar_one_or_none()
    if test is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="ExamTest not found")
    if test.status != TestStatus.published:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Test must be published before it can be assigned",
        )

    # Verify class belongs to org
    await get_class(db, class_id=class_id, org_id=org_id)

    assignment = TestAssignment(
        test_id=test_id,
        class_id=class_id,
        released_at=released_at,
        closes_at=closes_at,
        quarter=quarter,
        assigned_by=assigned_by,
    )
    db.add(assignment)
    try:
        await db.commit()
        await db.refresh(assignment)
    except IntegrityError:
        await db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="This test is already assigned to this class",
        )
    return assignment


async def list_assignments(
    db: AsyncSession,
    *,
    test_id: uuid.UUID,
    org_id: uuid.UUID,
) -> list[TestAssignment]:
    # Verify test belongs to org
    result = await db.execute(
        select(ExamTest)
        .join(ExamBank, ExamTest.bank_id == ExamBank.id)
        .where(ExamTest.id == test_id, ExamBank.org_id == org_id)
    )
    if result.scalar_one_or_none() is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="ExamTest not found")

    result = await db.execute(select(TestAssignment).where(TestAssignment.test_id == test_id))
    return list(result.scalars().all())


async def update_assignment(
    db: AsyncSession,
    *,
    assignment_id: uuid.UUID,
    org_id: uuid.UUID,
    released_at: dt | None = None,
    closes_at: dt | None = None,
    quarter: Quarter | None = None,
) -> TestAssignment:
    result = await db.execute(
        select(TestAssignment)
        .join(ExamTest, TestAssignment.test_id == ExamTest.id)
        .join(ExamBank, ExamTest.bank_id == ExamBank.id)
        .where(TestAssignment.id == assignment_id, ExamBank.org_id == org_id)
    )
    assignment = result.scalar_one_or_none()
    if assignment is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="TestAssignment not found"
        )

    new_released_at = released_at if released_at is not None else assignment.released_at
    new_closes_at = closes_at if closes_at is not None else assignment.closes_at

    if new_closes_at <= new_released_at:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="closes_at must be after released_at",
        )

    if released_at is not None:
        assignment.released_at = released_at
    if closes_at is not None:
        assignment.closes_at = closes_at
    if quarter is not None:
        assignment.quarter = quarter

    await db.commit()
    await db.refresh(assignment)
    return assignment


async def delete_assignment(
    db: AsyncSession,
    *,
    assignment_id: uuid.UUID,
    org_id: uuid.UUID,
) -> None:
    result = await db.execute(
        select(TestAssignment)
        .join(ExamTest, TestAssignment.test_id == ExamTest.id)
        .join(ExamBank, ExamTest.bank_id == ExamBank.id)
        .where(TestAssignment.id == assignment_id, ExamBank.org_id == org_id)
    )
    assignment = result.scalar_one_or_none()
    if assignment is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="TestAssignment not found"
        )

    # 409 if any ExamAttempt exists for the test
    attempt_count = await db.scalar(
        select(func.count())
        .select_from(ExamAttempt)
        .where(ExamAttempt.test_id == assignment.test_id)
    )
    if attempt_count:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Cannot delete assignment: students have already attempted this test",
        )

    await db.delete(assignment)
    await db.commit()


# ---------------------------------------------------------------------------
# Student test discovery
# ---------------------------------------------------------------------------


async def get_student_available_tests(
    db: AsyncSession,
    *,
    user_id: uuid.UUID,
    org_id: uuid.UUID,
) -> list[dict]:
    """Return open-window tests for a student, with attempt status.

    Returns list of dicts with keys:
        test_id, test_title, bank_subject, released_at, closes_at,
        quarter, class_name, academic_year, has_attempted, attempt_id
    """
    now = dt.now(tz=UTC)

    # Find all ClassMember rows for this user
    member_result = await db.execute(select(ClassMember).where(ClassMember.user_id == user_id))
    members = member_result.scalars().all()
    if not members:
        return []

    class_ids = [m.class_id for m in members]

    # Find open TestAssignment rows for those classes
    assignment_result = await db.execute(
        select(TestAssignment)
        .options(selectinload(TestAssignment.school_class), selectinload(TestAssignment.test))
        .join(ExamTest, TestAssignment.test_id == ExamTest.id)
        .join(ExamBank, ExamTest.bank_id == ExamBank.id)
        .where(
            TestAssignment.class_id.in_(class_ids),
            TestAssignment.released_at <= now,
            TestAssignment.closes_at >= now,
            ExamBank.org_id == org_id,
        )
    )
    assignments = assignment_result.scalars().all()

    rows = []
    for a in assignments:
        # Check if the student has an attempt for this test
        attempt_result = await db.execute(
            select(ExamAttempt).where(
                ExamAttempt.test_id == a.test_id,
                ExamAttempt.user_id == user_id,
            )
        )
        attempt = attempt_result.scalar_one_or_none()

        # Load the bank for the subject
        bank_result = await db.execute(select(ExamBank).where(ExamBank.id == a.test.bank_id))
        bank = bank_result.scalar_one_or_none()

        rows.append(
            {
                "test_id": a.test_id,
                "test_title": a.test.title,
                "bank_subject": bank.subject if bank else None,
                "released_at": a.released_at,
                "closes_at": a.closes_at,
                "quarter": a.quarter,
                "class_name": a.school_class.name,
                "academic_year": a.school_class.academic_year,
                "has_attempted": attempt is not None,
                "attempt_id": attempt.id if attempt is not None else None,
            }
        )
    return rows
