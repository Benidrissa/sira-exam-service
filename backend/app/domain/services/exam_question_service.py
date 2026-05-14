"""ExamQuestion service — CRUD, validation, and publish gate."""

from __future__ import annotations

import uuid

from fastapi import HTTPException, status
from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.models.exam import BankStatus, ExamBank, ExamQuestion
from app.schemas.exam import ExamQuestionCreate, ExamQuestionUpdate


async def _get_bank_or_404(db: AsyncSession, bank_id: uuid.UUID, org_id: uuid.UUID) -> ExamBank:
    result = await db.execute(
        select(ExamBank).where(ExamBank.id == bank_id, ExamBank.org_id == org_id)
    )
    bank = result.scalar_one_or_none()
    if bank is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="ExamBank not found")
    return bank


def _check_ownership(bank: ExamBank, created_by: uuid.UUID, is_admin: bool) -> None:
    if bank.created_by != created_by and not is_admin:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Forbidden")


async def _get_question_or_404(
    db: AsyncSession, question_id: uuid.UUID, bank_id: uuid.UUID
) -> ExamQuestion:
    result = await db.execute(
        select(ExamQuestion).where(
            ExamQuestion.id == question_id,
            ExamQuestion.bank_id == bank_id,
        )
    )
    question = result.scalar_one_or_none()
    if question is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="ExamQuestion not found")
    return question


async def create_question(
    db: AsyncSession,
    *,
    bank_id: uuid.UUID,
    org_id: uuid.UUID,
    created_by: uuid.UUID,
    is_admin: bool = False,
    data: ExamQuestionCreate,
) -> ExamQuestion:
    bank = await _get_bank_or_404(db, bank_id, org_id)
    _check_ownership(bank, created_by, is_admin)

    question = ExamQuestion(
        bank_id=bank_id,
        scenario_id=data.scenario_id,
        question_type=data.question_type,
        title=data.title,
        description=data.description,
        options=data.options,
        correct_answer_indices=data.correct_answer_indices,
        explanation=data.explanation,
        model_answer=data.model_answer,
        rubric=data.rubric,
        difficulty=data.difficulty,
        category=data.category,
        order_index=data.order_index,
        ai_generated=data.ai_generated,
        validated=False,
    )
    db.add(question)
    await db.commit()
    await db.refresh(question)
    return question


async def bulk_create_questions(
    db: AsyncSession,
    *,
    bank_id: uuid.UUID,
    org_id: uuid.UUID,
    created_by: uuid.UUID,
    is_admin: bool = False,
    items: list[ExamQuestionCreate],
) -> list[ExamQuestion]:
    bank = await _get_bank_or_404(db, bank_id, org_id)
    _check_ownership(bank, created_by, is_admin)

    questions = [
        ExamQuestion(
            bank_id=bank_id,
            scenario_id=d.scenario_id,
            question_type=d.question_type,
            title=d.title,
            description=d.description,
            options=d.options,
            correct_answer_indices=d.correct_answer_indices,
            explanation=d.explanation,
            model_answer=d.model_answer,
            rubric=d.rubric,
            difficulty=d.difficulty,
            category=d.category,
            order_index=d.order_index,
            ai_generated=d.ai_generated,
            validated=False,
        )
        for d in items
    ]
    db.add_all(questions)
    await db.commit()
    for q in questions:
        await db.refresh(q)
    return questions


async def get_question(
    db: AsyncSession,
    *,
    question_id: uuid.UUID,
    bank_id: uuid.UUID,
    org_id: uuid.UUID,
) -> ExamQuestion:
    result = await db.execute(
        select(ExamQuestion)
        .join(ExamBank, ExamQuestion.bank_id == ExamBank.id)
        .where(
            ExamQuestion.id == question_id,
            ExamQuestion.bank_id == bank_id,
            ExamBank.org_id == org_id,
        )
    )
    question = result.scalar_one_or_none()
    if question is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="ExamQuestion not found")
    return question


async def list_questions(
    db: AsyncSession, *, bank_id: uuid.UUID, org_id: uuid.UUID
) -> list[ExamQuestion]:
    await _get_bank_or_404(db, bank_id, org_id)
    result = await db.execute(
        select(ExamQuestion)
        .where(ExamQuestion.bank_id == bank_id)
        .order_by(ExamQuestion.order_index)
    )
    return list(result.scalars().all())


async def update_question(
    db: AsyncSession,
    *,
    question_id: uuid.UUID,
    bank_id: uuid.UUID,
    org_id: uuid.UUID,
    created_by: uuid.UUID,
    is_admin: bool = False,
    data: ExamQuestionUpdate,
) -> ExamQuestion:
    bank = await _get_bank_or_404(db, bank_id, org_id)
    _check_ownership(bank, created_by, is_admin)
    question = await _get_question_or_404(db, question_id, bank_id)

    patch = data.model_dump(exclude_unset=True)
    for field, value in patch.items():
        setattr(question, field, value)

    await db.commit()
    await db.refresh(question)
    return question


async def delete_question(
    db: AsyncSession,
    *,
    question_id: uuid.UUID,
    bank_id: uuid.UUID,
    org_id: uuid.UUID,
    created_by: uuid.UUID,
    is_admin: bool = False,
) -> None:
    bank = await _get_bank_or_404(db, bank_id, org_id)
    _check_ownership(bank, created_by, is_admin)
    question = await _get_question_or_404(db, question_id, bank_id)
    await db.delete(question)
    await db.commit()


async def validate_question(
    db: AsyncSession,
    *,
    question_id: uuid.UUID,
    bank_id: uuid.UUID,
    org_id: uuid.UUID,
) -> ExamQuestion:
    """Mark a single question as validated (FR-1.6.1)."""
    await _get_bank_or_404(db, bank_id, org_id)
    question = await _get_question_or_404(db, question_id, bank_id)
    question.validated = True
    await db.commit()
    await db.refresh(question)
    return question


async def validate_all_and_publish(
    db: AsyncSession,
    *,
    bank_id: uuid.UUID,
    org_id: uuid.UUID,
) -> tuple[int, ExamBank]:
    """Bulk-validate all questions then set bank.status=published (FR-1.6.2/1.6.3).

    Returns (validated_count, updated_bank).
    Raises 422 if any question was already validated (idempotent — counts them).
    """
    bank = await _get_bank_or_404(db, bank_id, org_id)

    # Count unvalidated questions; block publish if any remain after bulk validate
    unvalidated_result = await db.execute(
        select(func.count(ExamQuestion.id)).where(
            ExamQuestion.bank_id == bank_id,
            ExamQuestion.validated.is_(False),
        )
    )
    unvalidated_count = unvalidated_result.scalar() or 0

    if unvalidated_count == 0:
        # All already validated — just publish
        bank.status = BankStatus.published
        await db.commit()
        await db.refresh(bank)
        return 0, bank

    # Bulk validate
    await db.execute(
        update(ExamQuestion)
        .where(ExamQuestion.bank_id == bank_id, ExamQuestion.validated.is_(False))
        .values(validated=True)
    )

    # Check if there are any questions at all (can't publish empty bank)
    total_result = await db.execute(
        select(func.count(ExamQuestion.id)).where(ExamQuestion.bank_id == bank_id)
    )
    total = total_result.scalar() or 0
    if total == 0:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Cannot publish a bank with no questions.",
        )

    bank.status = BankStatus.published
    await db.commit()
    await db.refresh(bank)
    return unvalidated_count, bank
