"""ExamAttempt service — start, submit, and MCQ scoring (FR-1.7)."""

from __future__ import annotations

import random
import uuid
from datetime import UTC
from datetime import datetime as dt

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.domain.models.exam import (
    ClassMember,
    DissertationAnswer,
    DissertationStatus,
    ExamAttempt,
    ExamBank,
    ExamQuestion,
    ExamTest,
    QuestionType,
    TestStatus,
)
from app.domain.services.dispensation_service import get_active_dispensation


async def start_attempt(
    db: AsyncSession,
    *,
    test_id: uuid.UUID,
    user_id: uuid.UUID,
    org_id: uuid.UUID,
) -> ExamAttempt:
    """Draw questions and create an ExamAttempt (FR-1.7.1).

    Raises:
        HTTPException(404): test not found or wrong org
        HTTPException(422): test not published or bank not published
        HTTPException(403): test window not open, or student not enrolled
    """
    result = await db.execute(
        select(ExamTest)
        .join(ExamBank, ExamTest.bank_id == ExamBank.id)
        .where(ExamTest.id == test_id, ExamBank.org_id == org_id)
        .options(selectinload(ExamTest.assignments))
    )
    test = result.scalar_one_or_none()
    if test is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="ExamTest not found")
    if test.status != TestStatus.published:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="ExamTest is not published.",
        )

    # Scheduling + class membership gate (only if test has assignments)
    if test.assignments:
        # FR-4.29: an active, non-expired dispensation bypasses the window + enrolment gate.
        dispensation = await get_active_dispensation(db, test_id=test_id, student_id=user_id)
        if dispensation is None:
            now = dt.now(tz=UTC)
            valid_assignment = next(
                (a for a in test.assignments if a.released_at <= now <= a.closes_at),
                None,
            )
            if valid_assignment is None:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN, detail="Test window not open"
                )
            enrolled = await db.scalar(
                select(ClassMember).where(
                    ClassMember.class_id == valid_assignment.class_id,
                    ClassMember.user_id == user_id,
                )
            )
            if enrolled is None:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="Not enrolled in any class for this test",
                )

    # Guard: student may not start a second attempt once one is submitted (FR-1.7 AC4)
    existing = await db.execute(
        select(ExamAttempt).where(
            ExamAttempt.test_id == test_id,
            ExamAttempt.user_id == user_id,
            ExamAttempt.mcq_answers.isnot(None),
        )
    )
    if existing.scalar_one_or_none() is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Attempt already submitted.",
        )

    # Fetch all validated questions in the bank
    q_result = await db.execute(
        select(ExamQuestion).where(
            ExamQuestion.bank_id == test.bank_id,
            ExamQuestion.validated.is_(True),
        )
    )
    all_questions = q_result.scalars().all()
    if not all_questions:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Bank has no validated questions.",
        )

    # Sample and optionally shuffle
    question_ids = [q.id for q in all_questions]
    if test.question_count and len(question_ids) > test.question_count:
        question_ids = random.sample(question_ids, k=test.question_count)
    if test.shuffle_questions:
        random.shuffle(question_ids)

    attempt = ExamAttempt(
        test_id=test_id,
        user_id=user_id,
        anon_id=uuid.uuid4(),
        question_ids=[str(qid) for qid in question_ids],
    )
    db.add(attempt)
    await db.commit()
    await db.refresh(attempt)

    # Return attempt + metadata needed by the frontend player
    drawn = {str(q.id): q for q in all_questions}
    ordered_questions = [drawn[str(qid)] for qid in question_ids if str(qid) in drawn]
    return attempt, test, ordered_questions


async def submit_attempt(
    db: AsyncSession,
    *,
    attempt_id: uuid.UUID,
    user_id: uuid.UUID,
    mcq_answers: dict[str, list[int]],
    dissertation_answers: dict[str, str],
    time_taken_sec: int | None,
) -> ExamAttempt:
    """Score MCQ answers, create DissertationAnswer rows, enqueue grading (FR-1.7.2).

    Raises:
        HTTPException(404): attempt not found
        HTTPException(409): attempt already submitted
        HTTPException(403): wrong user
    """
    attempt = await db.get(ExamAttempt, attempt_id)
    if attempt is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="ExamAttempt not found")
    if attempt.user_id != user_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Forbidden")
    if attempt.mcq_answers is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Attempt already submitted.",
        )

    # Load questions
    question_ids = [uuid.UUID(qid) for qid in (attempt.question_ids or [])]
    q_result = await db.execute(select(ExamQuestion).where(ExamQuestion.id.in_(question_ids)))
    questions = {str(q.id): q for q in q_result.scalars().all()}

    # Score MCQ (FR-1.7.3)
    mcq_total = 0
    mcq_earned = 0
    for qid, q in questions.items():
        if q.question_type != QuestionType.mcq:
            continue
        mcq_total += 1
        submitted = set(mcq_answers.get(qid, []))
        correct = set(q.correct_answer_indices or [])
        if submitted == correct:
            mcq_earned += 1

    mcq_score = (mcq_earned / mcq_total * 100.0) if mcq_total else 0.0

    # Persist MCQ results
    attempt.mcq_answers = mcq_answers
    attempt.mcq_score = mcq_score
    attempt.total_score = mcq_score
    attempt.time_taken_sec = time_taken_sec

    # Fetch test + bank for pass/fail threshold
    test = await db.get(ExamTest, attempt.test_id)
    if test:
        bank = await db.get(ExamBank, test.bank_id)
        if bank:
            attempt.passed = mcq_score >= bank.passing_score

    await db.flush()

    # Create DissertationAnswer rows (FR-1.7.2 + FR-1.8.1)
    from app.tasks.dissertation_grading import ai_correct_dissertation_task

    for qid_str, answer_text in dissertation_answers.items():
        if not answer_text.strip():
            continue
        da = DissertationAnswer(
            attempt_id=attempt_id,
            question_id=uuid.UUID(qid_str),
            answer_text=answer_text,
            status=DissertationStatus.pending,
        )
        db.add(da)
        await db.flush()
        ai_correct_dissertation_task.delay(str(da.id))

    await db.commit()
    await db.refresh(attempt)
    return attempt
