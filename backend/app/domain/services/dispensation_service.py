"""Exam dispensation / exemption service (FR-4.29).

A teacher or admin may exempt a student from a specific test. An active
(non-expired) dispensation bypasses the open-window + enrolment gate in
``start_attempt`` and excludes the exam from term aggregation.
"""

from __future__ import annotations

import uuid
from datetime import UTC
from datetime import datetime as dt

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.models.exam import (
    ClassMember,
    ExamAttempt,
    ExamBank,
    ExamDispensation,
    ExamTest,
)


async def _get_test_with_org_guard(
    db: AsyncSession, *, test_id: uuid.UUID, org_id: uuid.UUID
) -> ExamTest:
    result = await db.execute(
        select(ExamTest)
        .join(ExamBank, ExamTest.bank_id == ExamBank.id)
        .where(ExamTest.id == test_id, ExamBank.org_id == org_id)
    )
    test = result.scalar_one_or_none()
    if test is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="ExamTest not found")
    return test


async def create_dispensation(
    db: AsyncSession,
    *,
    org_id: uuid.UUID,
    granted_by: uuid.UUID,
    student_id: uuid.UUID,
    test_id: uuid.UUID,
    class_id: uuid.UUID,
    reason: str,
    expires_at: dt | None = None,
) -> ExamDispensation:
    """Grant a dispensation. 404 if test out of org; 422 if student not enrolled;
    409 if one already exists for (test, student)."""
    await _get_test_with_org_guard(db, test_id=test_id, org_id=org_id)

    enrolled = await db.scalar(
        select(ClassMember).where(
            ClassMember.class_id == class_id,
            ClassMember.user_id == student_id,
        )
    )
    if enrolled is None:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Student is not enrolled in the given class",
        )

    dispensation = ExamDispensation(
        org_id=org_id,
        student_id=student_id,
        test_id=test_id,
        class_id=class_id,
        reason=reason,
        granted_by=granted_by,
        expires_at=expires_at,
    )
    db.add(dispensation)
    try:
        await db.commit()
    except IntegrityError as exc:
        await db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="A dispensation already exists for this student and test",
        ) from exc
    await db.refresh(dispensation)
    return dispensation


async def delete_dispensation(
    db: AsyncSession, *, dispensation_id: uuid.UUID, org_id: uuid.UUID
) -> None:
    """Revoke a dispensation. 404 if not found in org; 409 if the student has
    already submitted an attempt for the test."""
    dispensation = await db.get(ExamDispensation, dispensation_id)
    if dispensation is None or dispensation.org_id != org_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Dispensation not found")

    submitted = await db.scalar(
        select(ExamAttempt).where(
            ExamAttempt.test_id == dispensation.test_id,
            ExamAttempt.user_id == dispensation.student_id,
            ExamAttempt.mcq_answers.isnot(None),
        )
    )
    if submitted is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Student has already submitted an attempt for this test",
        )

    await db.delete(dispensation)
    await db.commit()


async def list_test_dispensations(
    db: AsyncSession, *, test_id: uuid.UUID, org_id: uuid.UUID
) -> list[ExamDispensation]:
    """List all dispensations for a test (teacher/admin)."""
    await _get_test_with_org_guard(db, test_id=test_id, org_id=org_id)
    result = await db.execute(select(ExamDispensation).where(ExamDispensation.test_id == test_id))
    return list(result.scalars().all())


async def get_active_dispensation(
    db: AsyncSession,
    *,
    test_id: uuid.UUID,
    student_id: uuid.UUID,
    now: dt | None = None,
) -> ExamDispensation | None:
    """Return the student's active (non-expired) dispensation for a test, if any."""
    now = now or dt.now(tz=UTC)
    result = await db.execute(
        select(ExamDispensation).where(
            ExamDispensation.test_id == test_id,
            ExamDispensation.student_id == student_id,
        )
    )
    dispensation = result.scalar_one_or_none()
    if dispensation is None:
        return None
    if dispensation.expires_at is not None and dispensation.expires_at <= now:
        return None
    return dispensation
