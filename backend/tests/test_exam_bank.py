"""Unit tests for ExamBank CRUD — service layer + router.

Tests use mocked AsyncSession so they work without a real database.
The enum `create_type=False` issue (same as etutor-digital-ph conftest)
is avoided entirely because we mock at the service level.
"""

from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import HTTPException

from app.domain.models.exam import BankStatus, ExamBank, ExamTest, TestStatus
from app.domain.services.exam_bank_service import (
    create_bank,
    delete_bank,
    ensure_default_test,
    get_bank,
    list_banks,
    update_bank,
)
from app.schemas.exam import ExamBankCreate, ExamBankUpdate

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

ORG_A = uuid.uuid4()
ORG_B = uuid.uuid4()
USER_ID = uuid.uuid4()
BANK_ID = uuid.uuid4()


def _make_bank(org_id: uuid.UUID = ORG_A, bank_id: uuid.UUID = BANK_ID) -> ExamBank:
    bank = ExamBank(
        id=bank_id,
        org_id=org_id,
        created_by=USER_ID,
        title_fr="Examen de test",
        language="fr",
        passing_score=80.0,
        status=BankStatus.draft,
    )
    return bank


def _mock_db() -> AsyncMock:
    db = AsyncMock()
    db.add = MagicMock()
    db.commit = AsyncMock()
    db.refresh = AsyncMock()
    return db


# ---------------------------------------------------------------------------
# Service-level tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_create_bank_sets_draft_status() -> None:
    db = _mock_db()
    data = ExamBankCreate(title_fr="Examen Sciences", language="fr")

    created = None

    async def fake_refresh(obj: ExamBank) -> None:
        nonlocal created
        created = obj

    db.refresh.side_effect = fake_refresh

    bank = await create_bank(db, org_id=ORG_A, created_by=USER_ID, data=data)

    db.add.assert_called_once()
    db.commit.assert_called_once()
    assert bank.status == BankStatus.draft
    assert bank.org_id == ORG_A
    assert bank.title_fr == "Examen Sciences"


@pytest.mark.asyncio
async def test_list_banks_scoped_to_org() -> None:
    db = _mock_db()
    bank_a = _make_bank(ORG_A)
    bank_b = _make_bank(ORG_B)  # different org — must NOT appear

    mock_result = MagicMock()
    mock_result.scalars.return_value.all.return_value = [bank_a]
    db.execute = AsyncMock(return_value=mock_result)

    banks = await list_banks(db, org_id=ORG_A)

    assert len(banks) == 1
    assert banks[0].org_id == ORG_A
    # bank_b never appears
    assert bank_b not in banks


@pytest.mark.asyncio
async def test_get_bank_not_found_raises_404() -> None:
    db = _mock_db()
    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = None
    db.execute = AsyncMock(return_value=mock_result)

    with pytest.raises(HTTPException) as exc_info:
        await get_bank(db, bank_id=uuid.uuid4(), org_id=ORG_A)

    assert exc_info.value.status_code == 404


@pytest.mark.asyncio
async def test_get_bank_wrong_org_raises_404() -> None:
    db = _mock_db()
    # Bank exists but belongs to ORG_B, caller passes ORG_A → returns None
    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = None
    db.execute = AsyncMock(return_value=mock_result)

    with pytest.raises(HTTPException) as exc_info:
        await get_bank(db, bank_id=BANK_ID, org_id=ORG_A)

    assert exc_info.value.status_code == 404


@pytest.mark.asyncio
async def test_update_bank_partial() -> None:
    db = _mock_db()
    bank = _make_bank()

    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = bank
    db.execute = AsyncMock(return_value=mock_result)

    updated = await update_bank(
        db,
        bank_id=BANK_ID,
        org_id=ORG_A,
        data=ExamBankUpdate(title_fr="Nouveau titre"),
    )

    assert updated.title_fr == "Nouveau titre"
    assert updated.language == "fr"  # unchanged


@pytest.mark.asyncio
async def test_delete_bank_sets_archived() -> None:
    db = _mock_db()
    bank = _make_bank()

    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = bank
    db.execute = AsyncMock(return_value=mock_result)

    await delete_bank(db, bank_id=BANK_ID, org_id=ORG_A)

    assert bank.status == BankStatus.archived
    db.commit.assert_called_once()


# ---------------------------------------------------------------------------
# ensure_default_test — published banks must always have a usable test so the
# teacher action buttons + student scheduling flow work (UAT bug fix).
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_ensure_default_test_creates_when_missing() -> None:
    db = _mock_db()
    bank = _make_bank()
    bank.status = BankStatus.published

    # No existing test for this bank (the bank-row lock SELECT shares this mock; its
    # result is ignored by the helper)
    mock_result = MagicMock()
    mock_result.scalars.return_value.first.return_value = None
    db.execute = AsyncMock(return_value=mock_result)

    test = await ensure_default_test(db, bank=bank, created_by=USER_ID)

    db.add.assert_called_once()
    db.commit.assert_called_once()
    assert test.bank_id == bank.id
    assert test.title == bank.title_fr
    assert test.status == TestStatus.published
    assert test.created_by == USER_ID


@pytest.mark.asyncio
async def test_ensure_default_test_is_idempotent() -> None:
    db = _mock_db()
    bank = _make_bank()
    bank.status = BankStatus.published

    existing = ExamTest(
        id=uuid.uuid4(),
        bank_id=bank.id,
        created_by=USER_ID,
        title="Examen existant",
        status=TestStatus.published,
    )
    mock_result = MagicMock()
    mock_result.scalars.return_value.first.return_value = existing
    db.execute = AsyncMock(return_value=mock_result)

    test = await ensure_default_test(db, bank=bank, created_by=USER_ID)

    # Returns the existing test without creating a duplicate
    assert test is existing
    db.add.assert_not_called()
    db.commit.assert_not_called()
