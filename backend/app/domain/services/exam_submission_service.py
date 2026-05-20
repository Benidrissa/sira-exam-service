"""Teacher submission review + student attempt history service (FR-4.7–FR-4.13)."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.domain.models.exam import (
    DissertationAnswer,
    DissertationStatus,
    ExamAttempt,
    ExamBank,
    ExamQuestion,
    ExamTest,
    QuestionType,
)

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
    """
    await _get_test_with_org_guard(db, test_id=test_id, org_id=org_id)

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

    summaries = []
    for attempt in attempts:
        counts = _dissertation_counts(attempt.dissertation_answers)

        summaries.append(
            {
                "attempt_id": attempt.id,
                "user_id": attempt.user_id,
                "attempted_at": attempt.attempted_at,
                "time_taken_sec": attempt.time_taken_sec,
                "mcq_score": attempt.mcq_score,
                "total_score": attempt.total_score,
                "passed": attempt.passed,
                "validation_status": attempt.validation_status,
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
        "user_id": attempt.user_id,
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
    """List all submitted attempts for the student, scoped to their org."""
    result = await db.execute(
        select(ExamAttempt, ExamTest)
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

    return [
        {
            "attempt_id": attempt.id,
            "test_id": attempt.test_id,
            "test_title": test.title,
            "attempted_at": attempt.attempted_at,
            "total_score": attempt.total_score,
            "passed": attempt.passed,
            "validation_status": attempt.validation_status,
        }
        for attempt, test in rows
    ]


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

    # Feedback gate: show_feedback OR closed assignment
    feedback_available = bool(test.show_feedback)
    if not feedback_available:
        # Check if any assignment's closes_at has passed
        from app.domain.models.exam import TestAssignment

        asgn_result = await db.execute(
            select(TestAssignment).where(TestAssignment.test_id == test.id)
        )
        assignments = list(asgn_result.scalars().all())
        now = datetime.now(tz=UTC)
        if any(a.closes_at is not None and a.closes_at.astimezone(UTC) < now for a in assignments):
            feedback_available = True

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
