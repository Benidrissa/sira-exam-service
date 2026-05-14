"""ExamScenario service — CRUD with org_id + ownership checks."""

from __future__ import annotations

import uuid

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.models.exam import ExamBank, ExamQuestion, ExamScenario
from app.schemas.exam import ExamScenarioCreate, ExamScenarioUpdate


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


async def create_scenario(
    db: AsyncSession,
    *,
    bank_id: uuid.UUID,
    org_id: uuid.UUID,
    created_by: uuid.UUID,
    is_admin: bool = False,
    data: ExamScenarioCreate,
) -> ExamScenario:
    bank = await _get_bank_or_404(db, bank_id, org_id)
    _check_ownership(bank, created_by, is_admin)

    scenario = ExamScenario(
        bank_id=bank_id,
        title=data.title,
        objective=data.objective,
        context_text=data.context_text,
        order_index=data.order_index,
    )
    db.add(scenario)
    await db.commit()
    await db.refresh(scenario)
    return scenario


async def get_scenario(
    db: AsyncSession,
    *,
    scenario_id: uuid.UUID,
    bank_id: uuid.UUID,
    org_id: uuid.UUID,
) -> ExamScenario:
    result = await db.execute(
        select(ExamScenario)
        .join(ExamBank, ExamScenario.bank_id == ExamBank.id)
        .where(
            ExamScenario.id == scenario_id,
            ExamScenario.bank_id == bank_id,
            ExamBank.org_id == org_id,
        )
    )
    scenario = result.scalar_one_or_none()
    if scenario is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="ExamScenario not found")
    return scenario


async def list_scenarios(
    db: AsyncSession, *, bank_id: uuid.UUID, org_id: uuid.UUID
) -> list[ExamScenario]:
    await _get_bank_or_404(db, bank_id, org_id)
    result = await db.execute(
        select(ExamScenario)
        .where(ExamScenario.bank_id == bank_id)
        .order_by(ExamScenario.order_index)
    )
    return list(result.scalars().all())


async def update_scenario(
    db: AsyncSession,
    *,
    scenario_id: uuid.UUID,
    bank_id: uuid.UUID,
    org_id: uuid.UUID,
    created_by: uuid.UUID,
    is_admin: bool = False,
    data: ExamScenarioUpdate,
) -> ExamScenario:
    bank = await _get_bank_or_404(db, bank_id, org_id)
    _check_ownership(bank, created_by, is_admin)
    scenario = await get_scenario(db, scenario_id=scenario_id, bank_id=bank_id, org_id=org_id)

    patch = data.model_dump(exclude_unset=True)
    for field, value in patch.items():
        setattr(scenario, field, value)

    await db.commit()
    await db.refresh(scenario)
    return scenario


async def delete_scenario(
    db: AsyncSession,
    *,
    scenario_id: uuid.UUID,
    bank_id: uuid.UUID,
    org_id: uuid.UUID,
    created_by: uuid.UUID,
    is_admin: bool = False,
) -> None:
    bank = await _get_bank_or_404(db, bank_id, org_id)
    _check_ownership(bank, created_by, is_admin)
    scenario = await get_scenario(db, scenario_id=scenario_id, bank_id=bank_id, org_id=org_id)

    # Block deletion if questions exist
    q_result = await db.execute(
        select(ExamQuestion).where(ExamQuestion.scenario_id == scenario_id).limit(1)
    )
    if q_result.scalar_one_or_none() is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Cannot delete scenario with existing questions. Delete questions first.",
        )

    await db.delete(scenario)
    await db.commit()
