"""Score complaint service — file, list, and resolve (FR-4.15–FR-4.16)."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.models.exam import (
    ComplaintStatus,
    DissertationAnswer,
    DissertationStatus,
    ExamAttempt,
    ExamBank,
    ExamTest,
    ReviewAuditLog,
    ScoreComplaint,
)

# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


async def _get_attempt_with_user_guard(
    db: AsyncSession,
    *,
    attempt_id: uuid.UUID,
    user_id: uuid.UUID,
    org_id: uuid.UUID,
) -> ExamAttempt:
    """Fetch attempt scoped to org, then enforce user ownership (403)."""
    result = await db.execute(
        select(ExamAttempt)
        .join(ExamTest, ExamAttempt.test_id == ExamTest.id)
        .join(ExamBank, ExamTest.bank_id == ExamBank.id)
        .where(ExamAttempt.id == attempt_id, ExamBank.org_id == org_id)
    )
    attempt = result.scalar_one_or_none()
    if attempt is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="ExamAttempt not found")
    if attempt.user_id != user_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Forbidden")
    return attempt


# ---------------------------------------------------------------------------
# FR-4.15: File complaint
# ---------------------------------------------------------------------------


async def file_complaint(
    db: AsyncSession,
    *,
    attempt_id: uuid.UUID,
    user_id: uuid.UUID,
    org_id: uuid.UUID,
    question_id: uuid.UUID | None,
    reason: str,
) -> ScoreComplaint:
    """File a score complaint.

    Guards:
    - attempt.user_id == user_id (403)
    - attempt must be submitted — mcq_answers IS NOT NULL (422)
    - reason >= 20 chars enforced by schema
    - UniqueConstraint violation → 409
    """
    attempt = await _get_attempt_with_user_guard(
        db, attempt_id=attempt_id, user_id=user_id, org_id=org_id
    )

    if attempt.mcq_answers is None:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Attempt has not been submitted yet.",
        )

    complaint = ScoreComplaint(
        attempt_id=attempt_id,
        question_id=question_id,
        filed_by=user_id,
        reason=reason,
        status=ComplaintStatus.pending,
    )
    db.add(complaint)
    try:
        await db.commit()
    except IntegrityError:
        await db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="A complaint for this attempt/question already exists.",
        )
    await db.refresh(complaint)
    return complaint


# ---------------------------------------------------------------------------
# FR-4.15: List attempt complaints (student)
# ---------------------------------------------------------------------------


async def list_attempt_complaints(
    db: AsyncSession,
    *,
    attempt_id: uuid.UUID,
    user_id: uuid.UUID,
    org_id: uuid.UUID,
) -> list[ScoreComplaint]:
    """Student's own complaints for the attempt.

    Guard: attempt.user_id == user_id (403).
    """
    await _get_attempt_with_user_guard(db, attempt_id=attempt_id, user_id=user_id, org_id=org_id)

    result = await db.execute(
        select(ScoreComplaint)
        .where(ScoreComplaint.attempt_id == attempt_id)
        .order_by(ScoreComplaint.created_at.desc())
    )
    return list(result.scalars().all())


# ---------------------------------------------------------------------------
# FR-4.16: List test complaints (teacher)
# ---------------------------------------------------------------------------


async def list_test_complaints(
    db: AsyncSession,
    *,
    test_id: uuid.UUID,
    org_id: uuid.UUID,
) -> list[ScoreComplaint]:
    """All complaints for a test (teacher view).

    Joins: ScoreComplaint → ExamAttempt → ExamTest → ExamBank (org check).
    """
    # Verify test belongs to this org
    test_result = await db.execute(
        select(ExamTest)
        .join(ExamBank, ExamTest.bank_id == ExamBank.id)
        .where(ExamTest.id == test_id, ExamBank.org_id == org_id)
    )
    if test_result.scalar_one_or_none() is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="ExamTest not found")

    result = await db.execute(
        select(ScoreComplaint)
        .join(ExamAttempt, ScoreComplaint.attempt_id == ExamAttempt.id)
        .where(ExamAttempt.test_id == test_id)
        .order_by(ScoreComplaint.created_at.desc())
    )
    return list(result.scalars().all())


# ---------------------------------------------------------------------------
# FR-4.16: Resolve complaint (teacher)
# ---------------------------------------------------------------------------


async def resolve_complaint(
    db: AsyncSession,
    *,
    complaint_id: uuid.UUID,
    org_id: uuid.UUID,
    resolved_by: uuid.UUID,
    status: ComplaintStatus,
    review_note: str | None,
    score_override: float | None,
) -> ScoreComplaint:
    """Resolve a score complaint.

    Guards:
    - complaint must be 'pending' (409 if already resolved)
    - if status='rejected': review_note required
    - test.bank.org_id == org_id (404)
    If approved and score_override:
    - if question_id not None: update DissertationAnswer.human_score, recompute total + passed
    - if question_id is None: update attempt.total_score directly, recompute passed
    """
    # Load complaint with org guard via join chain
    result = await db.execute(
        select(ScoreComplaint)
        .join(ExamAttempt, ScoreComplaint.attempt_id == ExamAttempt.id)
        .join(ExamTest, ExamAttempt.test_id == ExamTest.id)
        .join(ExamBank, ExamTest.bank_id == ExamBank.id)
        .where(ScoreComplaint.id == complaint_id, ExamBank.org_id == org_id)
    )
    complaint = result.scalar_one_or_none()
    if complaint is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="ScoreComplaint not found"
        )

    if complaint.status != ComplaintStatus.pending:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Complaint already resolved (status={complaint.status}).",
        )

    if status == ComplaintStatus.rejected and not review_note:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="review_note is required when rejecting a complaint.",
        )

    # Apply score override if approved
    if status == ComplaintStatus.approved and score_override is not None:
        attempt = await db.get(ExamAttempt, complaint.attempt_id)
        if attempt is not None:
            if complaint.question_id is not None:
                # Update the matching DissertationAnswer
                da_result = await db.execute(
                    select(DissertationAnswer).where(
                        DissertationAnswer.attempt_id == complaint.attempt_id,
                        DissertationAnswer.question_id == complaint.question_id,
                    )
                )
                da = da_result.scalar_one_or_none()
                if da is not None:
                    da.human_score = score_override
                    da.status = DissertationStatus.human_reviewed
                    da.human_scored_by = resolved_by
                    da.human_scored_at = datetime.now(tz=UTC)
                    await db.flush()

                # score_override is the new total_score for this attempt.
                # Updating a single dissertation answer doesn't determine a valid
                # total on its own (rubric units vs percentage units differ).
                # Treat score_override as the authoritative new total, consistent
                # with the batch_validate override path.
                attempt.total_score = score_override
            else:
                # Direct override of total_score
                attempt.total_score = score_override

            # Recompute passed
            test = await db.get(ExamTest, attempt.test_id)
            if test:
                bank = await db.get(ExamBank, test.bank_id)
                if bank and attempt.total_score is not None:
                    attempt.passed = attempt.total_score >= bank.passing_score

    # Resolve the complaint
    complaint.status = status
    complaint.reviewed_by = resolved_by
    complaint.review_note = review_note
    complaint.score_override = score_override
    complaint.reviewed_at = datetime.now(tz=UTC)

    # Write audit log when a score override is applied (FR-4.21.3)
    if status == ComplaintStatus.approved and score_override is not None:
        attempt_for_audit = await db.get(ExamAttempt, complaint.attempt_id)
        if attempt_for_audit is not None:
            # Load org_id via bank
            test_for_audit = await db.get(ExamTest, attempt_for_audit.test_id)
            bank_for_audit = (
                await db.get(ExamBank, test_for_audit.bank_id) if test_for_audit else None
            )
            if bank_for_audit is not None and complaint.question_id is not None:
                    # Dissertation-level override: record against the DissertationAnswer
                    da_result = await db.execute(
                        select(DissertationAnswer).where(
                            DissertationAnswer.attempt_id == complaint.attempt_id,
                            DissertationAnswer.question_id == complaint.question_id,
                        )
                    )
                    da_for_audit = da_result.scalar_one_or_none()
                    if da_for_audit is not None:
                        audit_entry = ReviewAuditLog(
                            answer_id=da_for_audit.id,
                            attempt_id=complaint.attempt_id,
                            test_id=attempt_for_audit.test_id,
                            org_id=bank_for_audit.org_id,
                            actor_id=resolved_by,
                            actor_role="teacher",
                            action="complaint_resolved",
                            old_values={"human_score": da_for_audit.human_score},
                            new_values={
                                "human_score": score_override,
                                "complaint_id": str(complaint.id),
                                "review_note": review_note,
                            },
                        )
                        db.add(audit_entry)

    await db.commit()
    await db.refresh(complaint)
    return complaint
