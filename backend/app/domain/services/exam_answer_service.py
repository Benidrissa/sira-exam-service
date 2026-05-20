"""DissertationAnswer service — human scoring + review queue (FR-1.9)."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.models.exam import (
    DissertationAnswer,
    DissertationStatus,
    ExamAttempt,
    ExamBank,
    ExamQuestion,
    ExamTest,
)


def _max_rubric_points(rubric: list | None) -> float:
    if not rubric:
        return 100.0
    return sum(float(c.get("max_points", 0)) for c in rubric)


async def list_for_review(
    db: AsyncSession,
    *,
    test_id: uuid.UUID,
    org_id: uuid.UUID,
) -> list[DissertationAnswer]:
    """Return answers with status pending or ai_scored for a teacher's test (FR-1.9.1)."""
    # Verify test belongs to this org
    test_result = await db.execute(
        select(ExamTest)
        .join(ExamBank, ExamTest.bank_id == ExamBank.id)
        .where(ExamTest.id == test_id, ExamBank.org_id == org_id)
    )
    if test_result.scalar_one_or_none() is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="ExamTest not found")

    result = await db.execute(
        select(DissertationAnswer)
        .join(ExamAttempt, DissertationAnswer.attempt_id == ExamAttempt.id)
        .where(
            ExamAttempt.test_id == test_id,
            DissertationAnswer.status.in_(
                [
                    DissertationStatus.pending,
                    DissertationStatus.ai_scored,
                    DissertationStatus.human_reviewed,
                ]
            ),
        )
        .order_by(DissertationAnswer.attempt_id)
    )
    return list(result.scalars().all())


async def apply_human_score(
    db: AsyncSession,
    *,
    answer_id: uuid.UUID,
    org_id: uuid.UUID,
    graded_by: uuid.UUID,
    human_score: float,
    human_feedback: str,
    ai_score_override: float | None = None,
    ai_feedback_override: str | None = None,
) -> DissertationAnswer:
    """Apply teacher grade to a dissertation answer (FR-1.9.2).

    Validates score ≤ sum(rubric max_points); sets status=human_reviewed.
    """
    # Fetch answer + verify org ownership via attempt → test → bank
    result = await db.execute(
        select(DissertationAnswer)
        .join(ExamAttempt, DissertationAnswer.attempt_id == ExamAttempt.id)
        .join(ExamTest, ExamAttempt.test_id == ExamTest.id)
        .join(ExamBank, ExamTest.bank_id == ExamBank.id)
        .where(DissertationAnswer.id == answer_id, ExamBank.org_id == org_id)
    )
    answer = result.scalar_one_or_none()
    if answer is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="DissertationAnswer not found"
        )

    # Validate score bounds
    q_result = await db.execute(select(ExamQuestion).where(ExamQuestion.id == answer.question_id))
    question = q_result.scalar_one_or_none()
    max_pts = _max_rubric_points(question.rubric if question else None)
    if human_score > max_pts:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"human_score ({human_score}) exceeds rubric maximum ({max_pts}).",
        )

    answer.human_score = human_score
    answer.human_feedback = human_feedback
    answer.human_scored_by = graded_by
    answer.human_scored_at = datetime.now(tz=UTC)
    answer.status = DissertationStatus.human_reviewed
    if ai_score_override is not None:
        answer.ai_score = ai_score_override
    if ai_feedback_override is not None:
        answer.ai_feedback = ai_feedback_override
    await db.commit()
    await db.refresh(answer)
    return answer
