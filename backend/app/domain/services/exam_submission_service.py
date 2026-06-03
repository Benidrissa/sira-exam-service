"""Teacher submission review + student attempt history service (FR-4.7–FR-4.13)."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.domain.models.exam import (
    ClassMember,
    DissertationAnswer,
    DissertationStatus,
    ExamAccessGrant,
    ExamAttempt,
    ExamBank,
    ExamDispensation,
    ExamQuestion,
    ExamTest,
    QuestionType,
    ReviewAuditLog,
    TestAssignment,
)
from app.domain.services import grade_calc

# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


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


async def _get_attempt_with_org_guard(
    db: AsyncSession, *, attempt_id: uuid.UUID, org_id: uuid.UUID
) -> ExamAttempt:
    result = await db.execute(
        select(ExamAttempt)
        .join(ExamTest, ExamAttempt.test_id == ExamTest.id)
        .join(ExamBank, ExamTest.bank_id == ExamBank.id)
        .where(ExamAttempt.id == attempt_id, ExamBank.org_id == org_id)
    )
    attempt = result.scalar_one_or_none()
    if attempt is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="ExamAttempt not found")
    return attempt


def _dissertation_counts(
    dissertation_answers: list[DissertationAnswer],
) -> dict:
    pending = sum(1 for a in dissertation_answers if a.status == DissertationStatus.pending)
    ai_scored = sum(1 for a in dissertation_answers if a.status == DissertationStatus.ai_scored)
    human_reviewed = sum(
        1 for a in dissertation_answers if a.status == DissertationStatus.human_reviewed
    )
    return {
        "pending_count": pending,
        "ai_scored_count": ai_scored,
        "human_reviewed_count": human_reviewed,
    }


def _build_question_answer(
    question: ExamQuestion,
    mcq_answers: dict | None,
    dissertation_map: dict[str, DissertationAnswer],
    *,
    reveal_feedback: bool,
) -> dict:
    qid_str = str(question.id)
    submitted_mcq = (mcq_answers or {}).get(qid_str)
    is_mcq_correct: bool | None = None
    if question.question_type == QuestionType.mcq and submitted_mcq is not None:
        correct = set(question.correct_answer_indices or [])
        is_mcq_correct = set(submitted_mcq) == correct

    da: DissertationAnswer | None = dissertation_map.get(qid_str)

    return {
        "question_id": question.id,
        "question_type": question.question_type,
        "description": question.description,
        "options": question.options,
        "correct_answer_indices": question.correct_answer_indices if reveal_feedback else None,
        "explanation": question.explanation if reveal_feedback else None,
        "model_answer": question.model_answer if reveal_feedback else None,
        "mcq_answer_indices": submitted_mcq,
        "is_mcq_correct": is_mcq_correct,
        "dissertation_answer_text": da.answer_text if da else None,
        "ai_score": da.ai_score if da else None,
        "ai_feedback": da.ai_feedback if da else None,
        "human_score": da.human_score if da else None,
        "human_feedback": da.human_feedback if da else None,
    }


# ---------------------------------------------------------------------------
# FR-4.7: Teacher submission list
# ---------------------------------------------------------------------------


async def list_test_submissions(
    db: AsyncSession,
    *,
    test_id: uuid.UUID,
    org_id: uuid.UUID,
) -> list[dict]:
    """Return all submitted attempts for a test with per-status dissertation counts.

    Guard: test must belong to org_id (via bank.org_id). 404 otherwise.
    A 'submitted' attempt has mcq_answers IS NOT NULL.
    Each row is enriched with class + course info via TestAssignment → SchoolClass.
    """
    test = await _get_test_with_org_guard(db, test_id=test_id, org_id=org_id)

    # Load bank for course fields
    bank = await db.get(ExamBank, test.bank_id)

    result = await db.execute(
        select(ExamAttempt)
        .where(
            ExamAttempt.test_id == test_id,
            ExamAttempt.mcq_answers.isnot(None),
        )
        .options(selectinload(ExamAttempt.dissertation_answers))
        .order_by(ExamAttempt.attempted_at.desc())
    )
    attempts = list(result.scalars().all())

    # Load all assignments for this test to find class info per attempt
    asgn_result = await db.execute(
        select(TestAssignment)
        .options(selectinload(TestAssignment.school_class))
        .where(TestAssignment.test_id == test_id)
        .order_by(TestAssignment.released_at.desc())
    )
    assignments = list(asgn_result.scalars().all())

    # FR-4.29: which students are dispensed from this test (score hidden, flagged)
    disp_result = await db.execute(
        select(ExamDispensation.student_id).where(ExamDispensation.test_id == test_id)
    )
    dispensed_students = set(disp_result.scalars().all())

    summaries = []
    for attempt in attempts:
        counts = _dissertation_counts(attempt.dissertation_answers)
        is_dispensed = attempt.user_id in dispensed_students

        # Find the class for this specific attempt's student via ClassMember
        class_id: uuid.UUID | None = None
        class_name: str | None = None
        class_archived_at: datetime | None = None
        for asgn in assignments:
            member_result = await db.execute(
                select(ClassMember).where(
                    ClassMember.class_id == asgn.class_id,
                    ClassMember.user_id == attempt.user_id,
                )
            )
            if member_result.scalar_one_or_none() is not None:
                class_id = asgn.class_id
                class_name = asgn.school_class.name
                class_archived_at = asgn.school_class.archived_at
                break

        display_id = attempt.anon_id if test.anonymous_grading else attempt.user_id
        summaries.append(
            {
                "attempt_id": attempt.id,
                "user_id": display_id,
                "attempted_at": attempt.attempted_at,
                "time_taken_sec": attempt.time_taken_sec,
                "mcq_score": None if is_dispensed else attempt.mcq_score,
                "total_score": None if is_dispensed else attempt.total_score,
                "passed": attempt.passed,
                "validation_status": attempt.validation_status,
                "exam_weight": test.exam_weight,
                "dispensed": is_dispensed,
                "class_id": class_id,
                "class_name": class_name,
                "class_archived_at": class_archived_at,
                "course_code": bank.course_code if bank else None,
                "course_name": bank.course_name if bank else None,
                **counts,
            }
        )
    return summaries


# ---------------------------------------------------------------------------
# FR-4.8: Individual attempt full review (teacher)
# ---------------------------------------------------------------------------


async def get_attempt_full_review(
    db: AsyncSession,
    *,
    attempt_id: uuid.UUID,
    org_id: uuid.UUID,
) -> dict:
    """Full attempt + all Q+A pairs for teacher. Always includes correct answers.

    Guard: attempt.test.bank.org_id must equal org_id. 404 otherwise.
    """
    attempt = await _get_attempt_with_org_guard(db, attempt_id=attempt_id, org_id=org_id)

    # Load test to check anonymous_grading flag.
    # _get_attempt_with_org_guard already verified attempt→test→bank chain belongs to org,
    # so test being None here would be a data-integrity violation — raise rather than leak.
    test = await db.get(ExamTest, attempt.test_id)
    if test is None:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="ExamTest not found for this attempt — data inconsistency",
        )
    display_id = attempt.anon_id if test.anonymous_grading else attempt.user_id

    # Load all questions for this attempt
    question_ids = [uuid.UUID(qid) for qid in (attempt.question_ids or [])]
    q_result = await db.execute(select(ExamQuestion).where(ExamQuestion.id.in_(question_ids)))
    questions = {str(q.id): q for q in q_result.scalars().all()}

    # Load dissertation answers
    da_result = await db.execute(
        select(DissertationAnswer).where(DissertationAnswer.attempt_id == attempt_id)
    )
    dissertation_map = {str(da.question_id): da for da in da_result.scalars().all()}

    # Build ordered question list (teacher sees everything)
    q_list = []
    for qid_str in (str(qid) for qid in question_ids):
        q = questions.get(qid_str)
        if q is None:
            continue
        q_list.append(
            _build_question_answer(
                q,
                attempt.mcq_answers,
                dissertation_map,
                reveal_feedback=True,
            )
        )

    return {
        "attempt_id": attempt.id,
        "test_id": attempt.test_id,
        "user_id": display_id,
        "attempted_at": attempt.attempted_at,
        "mcq_score": attempt.mcq_score,
        "total_score": attempt.total_score,
        "passed": attempt.passed,
        "validation_status": attempt.validation_status,
        "questions": q_list,
    }


# ---------------------------------------------------------------------------
# FR-4.9: Validate attempt
# ---------------------------------------------------------------------------


async def validate_attempt(
    db: AsyncSession,
    *,
    attempt_id: uuid.UUID,
    org_id: uuid.UUID,
    validated_by: uuid.UUID,
) -> ExamAttempt:
    """Mark attempt as teacher-validated.

    Guard: all DissertationAnswer rows must be status=human_reviewed.
    If any are pending/ai_scored: raise HTTPException(422, detail={pending_answer_ids: [...]})
    Idempotent: if already validated, return 200.
    """
    attempt = await _get_attempt_with_org_guard(db, attempt_id=attempt_id, org_id=org_id)

    # Idempotent
    if attempt.validation_status == "validated":
        return attempt

    # Check all dissertations are human_reviewed
    da_result = await db.execute(
        select(DissertationAnswer).where(DissertationAnswer.attempt_id == attempt_id)
    )
    dissertation_answers = list(da_result.scalars().all())
    not_reviewed = [
        str(da.id) for da in dissertation_answers if da.status != DissertationStatus.human_reviewed
    ]
    if not_reviewed:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={"pending_answer_ids": not_reviewed},
        )

    attempt.validation_status = "validated"
    attempt.validated_by = validated_by
    attempt.validated_at = datetime.now(tz=UTC)
    await db.commit()
    await db.refresh(attempt)
    return attempt


# ---------------------------------------------------------------------------
# FR-4.10: Batch validate
# ---------------------------------------------------------------------------


async def batch_validate(
    db: AsyncSession,
    *,
    test_id: uuid.UUID,
    org_id: uuid.UUID,
    attempt_ids: list[uuid.UUID],
    override_score: float | None,
    validated_by: uuid.UUID,
) -> dict:
    """Validate multiple attempts (max 100).

    Guard: all attempt_ids must belong to test_id and same org.
    Partial success: collect errors, commit successes.
    Returns {validated_count: int, errors: [{attempt_id, reason}]}
    """
    test = await _get_test_with_org_guard(db, test_id=test_id, org_id=org_id)
    bank = await db.get(ExamBank, test.bank_id)

    validated_count = 0
    errors: list[dict] = []

    for attempt_id in attempt_ids:
        # Load attempt scoped to this test + org
        result = await db.execute(
            select(ExamAttempt).where(
                ExamAttempt.id == attempt_id,
                ExamAttempt.test_id == test_id,
            )
        )
        attempt = result.scalar_one_or_none()
        if attempt is None:
            errors.append(
                {"attempt_id": str(attempt_id), "reason": "Attempt not found in this test"}
            )
            continue

        if attempt.mcq_answers is None:
            errors.append({"attempt_id": str(attempt_id), "reason": "Attempt not yet submitted"})
            continue

        if override_score is not None:
            # Apply score override, recompute passed
            attempt.total_score = override_score
            if bank:
                attempt.passed = override_score >= bank.passing_score
        else:
            # Must have all dissertations human_reviewed
            da_result = await db.execute(
                select(DissertationAnswer).where(DissertationAnswer.attempt_id == attempt_id)
            )
            dissertation_answers = list(da_result.scalars().all())
            not_reviewed = [
                str(da.id)
                for da in dissertation_answers
                if da.status != DissertationStatus.human_reviewed
            ]
            if not_reviewed:
                errors.append(
                    {
                        "attempt_id": str(attempt_id),
                        "reason": f"Dissertations not fully reviewed: {not_reviewed}",
                    }
                )
                continue

        if attempt.validation_status != "validated":
            attempt.validation_status = "validated"
            attempt.validated_by = validated_by
            attempt.validated_at = datetime.now(tz=UTC)

        validated_count += 1

    await db.commit()
    return {"validated_count": validated_count, "errors": errors}


# ---------------------------------------------------------------------------
# FR-4.12: Student attempt history
# ---------------------------------------------------------------------------


async def list_student_history(
    db: AsyncSession,
    *,
    user_id: uuid.UUID,
    org_id: uuid.UUID,
) -> list[dict]:
    """List all submitted attempts for the student enriched with class + course info."""
    result = await db.execute(
        select(ExamAttempt, ExamTest, ExamBank)
        .join(ExamTest, ExamAttempt.test_id == ExamTest.id)
        .join(ExamBank, ExamTest.bank_id == ExamBank.id)
        .where(
            ExamAttempt.user_id == user_id,
            ExamAttempt.mcq_answers.isnot(None),
            ExamBank.org_id == org_id,
        )
        .order_by(ExamAttempt.attempted_at.desc())
    )
    rows = result.all()

    now = datetime.now(tz=UTC)

    items = []
    for attempt, test, bank in rows:
        # Find class for this attempt via TestAssignment + ClassMember
        asgn_result = await db.execute(
            select(TestAssignment)
            .options(selectinload(TestAssignment.school_class))
            .join(ClassMember, TestAssignment.class_id == ClassMember.class_id)
            .where(
                TestAssignment.test_id == attempt.test_id,
                ClassMember.user_id == user_id,
            )
            .order_by(TestAssignment.released_at.desc())
            .limit(1)
        )
        asgn = asgn_result.scalar_one_or_none()

        class_id: uuid.UUID | None = None
        class_name: str | None = None
        academic_year: str | None = None
        class_archived_at: datetime | None = None
        review_allowed = bool(test.show_feedback)

        if asgn is not None:
            class_id = asgn.class_id
            class_name = asgn.school_class.name
            academic_year = asgn.school_class.academic_year
            class_archived_at = asgn.school_class.archived_at
            if not review_allowed and asgn.closes_at.astimezone(UTC) < now:
                review_allowed = True

        # Check access grant if still not allowed — filter expiry at DB level
        if not review_allowed:
            from sqlalchemy import or_

            grant_result = await db.execute(
                select(ExamAccessGrant).where(
                    ExamAccessGrant.student_id == user_id,
                    ExamAccessGrant.org_id == org_id,
                    or_(
                        ExamAccessGrant.test_id == attempt.test_id,
                        ExamAccessGrant.bank_id == test.bank_id,
                    ),
                    or_(
                        ExamAccessGrant.expires_at.is_(None),
                        ExamAccessGrant.expires_at > now,
                    ),
                )
            )
            if grant_result.first() is not None:
                review_allowed = True

        items.append(
            {
                "attempt_id": attempt.id,
                "test_id": attempt.test_id,
                "test_title": test.title,
                "attempted_at": attempt.attempted_at,
                "total_score": attempt.total_score,
                "passed": attempt.passed,
                "validation_status": attempt.validation_status,
                "exam_weight": test.exam_weight,
                "class_id": class_id,
                "class_name": class_name,
                "academic_year": academic_year,
                "class_archived_at": class_archived_at,
                "course_code": bank.course_code,
                "course_name": bank.course_name,
                "review_allowed": review_allowed,
            }
        )
    return items


# ---------------------------------------------------------------------------
# FR-4.13: Student read-only attempt review
# ---------------------------------------------------------------------------


async def get_attempt_review(
    db: AsyncSession,
    *,
    attempt_id: uuid.UUID,
    user_id: uuid.UUID,
    org_id: uuid.UUID,
) -> dict:
    """Student's own read-only attempt review.

    Guard: attempt.user_id == user_id (403 otherwise).
    Feedback gate: correct_answer_indices, explanation, model_answer are revealed ONLY if:
      test.show_feedback=True OR (closes_at from TestAssignment is not None AND closes_at < now)
    """
    # Load attempt with org guard
    result = await db.execute(
        select(ExamAttempt, ExamTest, ExamBank)
        .join(ExamTest, ExamAttempt.test_id == ExamTest.id)
        .join(ExamBank, ExamTest.bank_id == ExamBank.id)
        .where(ExamAttempt.id == attempt_id, ExamBank.org_id == org_id)
    )
    row = result.first()
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="ExamAttempt not found")
    attempt, test, _bank = row

    if attempt.user_id != user_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Forbidden")

    # Feedback gate (FR-4.13): show_feedback OR a closed assignment window.
    asgn_result = await db.execute(
        select(TestAssignment.closes_at).where(TestAssignment.test_id == test.id)
    )
    feedback_available = grade_calc.compute_feedback_available(
        show_feedback=bool(test.show_feedback),
        closes_ats=list(asgn_result.scalars().all()),
    )

    # Load questions and dissertations
    question_ids = [uuid.UUID(qid) for qid in (attempt.question_ids or [])]
    q_result = await db.execute(select(ExamQuestion).where(ExamQuestion.id.in_(question_ids)))
    questions = {str(q.id): q for q in q_result.scalars().all()}

    da_result = await db.execute(
        select(DissertationAnswer).where(DissertationAnswer.attempt_id == attempt_id)
    )
    dissertation_map = {str(da.question_id): da for da in da_result.scalars().all()}

    q_list = []
    for qid_str in (str(qid) for qid in question_ids):
        q = questions.get(qid_str)
        if q is None:
            continue
        q_list.append(
            _build_question_answer(
                q,
                attempt.mcq_answers,
                dissertation_map,
                reveal_feedback=feedback_available,
            )
        )

    return {
        "attempt_id": attempt.id,
        "test_id": attempt.test_id,
        "attempted_at": attempt.attempted_at,
        "mcq_score": attempt.mcq_score,
        "total_score": attempt.total_score,
        "passed": attempt.passed,
        "validation_status": attempt.validation_status,
        "feedback_available": feedback_available,
        "questions": q_list,
    }


# ---------------------------------------------------------------------------
# FR-4.21: Review audit log
# ---------------------------------------------------------------------------


async def list_audit_logs(
    db: AsyncSession,
    *,
    test_id: uuid.UUID,
    org_id: uuid.UUID,
) -> list[ReviewAuditLog]:
    """Return all review audit log entries for a test, ordered newest-first."""
    await _get_test_with_org_guard(db, test_id=test_id, org_id=org_id)

    result = await db.execute(
        select(ReviewAuditLog)
        .where(ReviewAuditLog.test_id == test_id, ReviewAuditLog.org_id == org_id)
        .order_by(ReviewAuditLog.occurred_at.desc())
    )
    return list(result.scalars().all())


# ---------------------------------------------------------------------------
# FR-4.20: Exam access grants
# ---------------------------------------------------------------------------


async def create_access_grant(
    db: AsyncSession,
    *,
    org_id: uuid.UUID,
    granted_by: uuid.UUID,
    student_id: uuid.UUID,
    bank_id: uuid.UUID | None,
    test_id: uuid.UUID | None,
    expires_at: datetime | None,
) -> ExamAccessGrant:
    grant = ExamAccessGrant(
        bank_id=bank_id,
        test_id=test_id,
        student_id=student_id,
        granted_by=granted_by,
        org_id=org_id,
        expires_at=expires_at,
    )
    db.add(grant)
    await db.commit()
    await db.refresh(grant)
    return grant


async def revoke_access_grant(
    db: AsyncSession,
    *,
    grant_id: uuid.UUID,
    org_id: uuid.UUID,
) -> None:
    result = await db.execute(
        select(ExamAccessGrant).where(
            ExamAccessGrant.id == grant_id,
            ExamAccessGrant.org_id == org_id,
        )
    )
    grant = result.scalar_one_or_none()
    if grant is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Grant not found")
    await db.delete(grant)
    await db.commit()


async def list_access_grants(
    db: AsyncSession,
    *,
    org_id: uuid.UUID,
) -> list[ExamAccessGrant]:
    result = await db.execute(
        select(ExamAccessGrant)
        .where(ExamAccessGrant.org_id == org_id)
        .order_by(ExamAccessGrant.granted_at.desc())
    )
    return list(result.scalars().all())


# ---------------------------------------------------------------------------
# FR-4.24: Anonymous grading — de-anonymisation mapping
# ---------------------------------------------------------------------------


async def get_anon_mapping(
    db: AsyncSession,
    *,
    test_id: uuid.UUID,
    org_id: uuid.UUID,
) -> list[dict]:
    """Return [{anon_id, user_id}] for all submitted attempts.

    Guard (409): all submitted attempts must have validation_status=validated.
    Guard (404): test.anonymous_grading must be True.
    """
    from sqlalchemy import func as sqlfunc

    test = await _get_test_with_org_guard(db, test_id=test_id, org_id=org_id)
    if not test.anonymous_grading:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Anonymous grading is not enabled for this test",
        )

    unvalidated_count = await db.scalar(
        select(sqlfunc.count(ExamAttempt.id)).where(
            ExamAttempt.test_id == test_id,
            ExamAttempt.mcq_answers.isnot(None),
            ExamAttempt.validation_status != "validated",
        )
    )
    if unvalidated_count:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Scoring not complete — {unvalidated_count} unvalidated attempt(s) remain",
        )

    result = await db.execute(
        select(ExamAttempt.anon_id, ExamAttempt.user_id).where(
            ExamAttempt.test_id == test_id,
            ExamAttempt.mcq_answers.isnot(None),
        )
    )
    return [{"anon_id": row.anon_id, "user_id": row.user_id} for row in result.all()]
