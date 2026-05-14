"""ExamBank service — CRUD operations scoped to the calling user's org."""

from __future__ import annotations

import uuid

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.models.exam import BankStatus, ExamBank
from app.schemas.exam import ExamBankCreate, ExamBankUpdate


async def create_bank(
    db: AsyncSession,
    *,
    org_id: uuid.UUID,
    created_by: uuid.UUID,
    data: ExamBankCreate,
) -> ExamBank:
    bank = ExamBank(
        org_id=org_id,
        created_by=created_by,
        title_fr=data.title_fr,
        title_en=data.title_en,
        subject=data.subject,
        language=data.language,
        passing_score=data.passing_score,
        status=BankStatus.draft,
    )
    db.add(bank)
    await db.commit()
    await db.refresh(bank)
    return bank


async def list_banks(
    db: AsyncSession,
    *,
    org_id: uuid.UUID,
    status_filter: BankStatus | None = None,
) -> list[ExamBank]:
    stmt = select(ExamBank).where(ExamBank.org_id == org_id)
    if status_filter is not None:
        stmt = stmt.where(ExamBank.status == status_filter)
    stmt = stmt.order_by(ExamBank.created_at.desc())
    result = await db.execute(stmt)
    return list(result.scalars().all())


async def get_bank(
    db: AsyncSession,
    *,
    bank_id: uuid.UUID,
    org_id: uuid.UUID,
) -> ExamBank:
    result = await db.execute(
        select(ExamBank).where(ExamBank.id == bank_id, ExamBank.org_id == org_id)
    )
    bank = result.scalar_one_or_none()
    if bank is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="ExamBank not found")
    return bank


async def update_bank(
    db: AsyncSession,
    *,
    bank_id: uuid.UUID,
    org_id: uuid.UUID,
    data: ExamBankUpdate,
) -> ExamBank:
    bank = await get_bank(db, bank_id=bank_id, org_id=org_id)
    update_data = data.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(bank, field, value)
    await db.commit()
    await db.refresh(bank)
    return bank


async def delete_bank(
    db: AsyncSession,
    *,
    bank_id: uuid.UUID,
    org_id: uuid.UUID,
) -> None:
    bank = await get_bank(db, bank_id=bank_id, org_id=org_id)
    bank.status = BankStatus.archived
    await db.commit()
