"""Unit tests for exam dispensation / exemption (FR-4.29) — service layer.

Uses a mocked AsyncSession so no database is required.
"""

from __future__ import annotations

import uuid
from datetime import UTC, timedelta
from datetime import datetime as dt
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import HTTPException
from sqlalchemy.exc import IntegrityError

from app.domain.models.exam import ExamDispensation, ExamTest
from app.domain.services import dispensation_service as svc

ORG = uuid.UUID("aaaaaaaa-0000-0000-0000-000000000001")
OTHER_ORG = uuid.UUID("aaaaaaaa-0000-0000-0000-0000000000ff")
TEACHER = uuid.UUID("cccccccc-0000-0000-0000-000000000001")
STUDENT = uuid.UUID("11111111-0000-0000-0000-000000000001")
TEST_ID = uuid.UUID("eeeeeeee-0000-0000-0000-000000000001")
CLASS_ID = uuid.UUID("dddddddd-0000-0000-0000-000000000009")
DISP_ID = uuid.UUID("ffffffff-0000-0000-0000-000000000001")


def _db() -> MagicMock:
    db = MagicMock()
    db.execute = AsyncMock()
    db.scalar = AsyncMock()
    db.commit = AsyncMock()
    db.rollback = AsyncMock()
    db.refresh = AsyncMock()
    db.add = MagicMock()
    db.delete = AsyncMock()
    db.get = AsyncMock()
    return db


def _guard_returns_test(db: MagicMock) -> None:
    """Make the org-guard query resolve to a test."""
    result = MagicMock()
    result.scalar_one_or_none.return_value = ExamTest(id=TEST_ID, bank_id=uuid.uuid4())
    db.execute.return_value = result


# --- create -----------------------------------------------------------------


async def test_create_requires_enrollment() -> None:
    db = _db()
    _guard_returns_test(db)
    db.scalar.return_value = None  # not enrolled

    with pytest.raises(HTTPException) as exc:
        await svc.create_dispensation(
            db,
            org_id=ORG,
            granted_by=TEACHER,
            student_id=STUDENT,
            test_id=TEST_ID,
            class_id=CLASS_ID,
            reason="medical",
        )
    assert exc.value.status_code == 422


async def test_create_duplicate_conflicts() -> None:
    db = _db()
    _guard_returns_test(db)
    db.scalar.return_value = object()  # enrolled
    db.commit.side_effect = IntegrityError("dup", {}, Exception())

    with pytest.raises(HTTPException) as exc:
        await svc.create_dispensation(
            db,
            org_id=ORG,
            granted_by=TEACHER,
            student_id=STUDENT,
            test_id=TEST_ID,
            class_id=CLASS_ID,
            reason="medical",
        )
    assert exc.value.status_code == 409
    db.rollback.assert_awaited_once()


async def test_create_success() -> None:
    db = _db()
    _guard_returns_test(db)
    db.scalar.return_value = object()  # enrolled

    out = await svc.create_dispensation(
        db,
        org_id=ORG,
        granted_by=TEACHER,
        student_id=STUDENT,
        test_id=TEST_ID,
        class_id=CLASS_ID,
        reason="medical",
    )
    db.add.assert_called_once()
    db.commit.assert_awaited_once()
    assert out.student_id == STUDENT
    assert out.reason == "medical"


# --- delete -----------------------------------------------------------------


async def test_delete_not_found() -> None:
    db = _db()
    db.get.return_value = None
    with pytest.raises(HTTPException) as exc:
        await svc.delete_dispensation(db, dispensation_id=DISP_ID, org_id=ORG)
    assert exc.value.status_code == 404


async def test_delete_wrong_org_is_404() -> None:
    db = _db()
    db.get.return_value = ExamDispensation(
        id=DISP_ID, org_id=OTHER_ORG, student_id=STUDENT, test_id=TEST_ID
    )
    with pytest.raises(HTTPException) as exc:
        await svc.delete_dispensation(db, dispensation_id=DISP_ID, org_id=ORG)
    assert exc.value.status_code == 404


async def test_delete_after_submission_conflicts() -> None:
    db = _db()
    db.get.return_value = ExamDispensation(
        id=DISP_ID, org_id=ORG, student_id=STUDENT, test_id=TEST_ID
    )
    db.scalar.return_value = object()  # an existing submitted attempt
    with pytest.raises(HTTPException) as exc:
        await svc.delete_dispensation(db, dispensation_id=DISP_ID, org_id=ORG)
    assert exc.value.status_code == 409


async def test_delete_success() -> None:
    db = _db()
    db.get.return_value = ExamDispensation(
        id=DISP_ID, org_id=ORG, student_id=STUDENT, test_id=TEST_ID
    )
    db.scalar.return_value = None  # no submitted attempt
    await svc.delete_dispensation(db, dispensation_id=DISP_ID, org_id=ORG)
    db.delete.assert_awaited_once()
    db.commit.assert_awaited_once()


# --- get_active_dispensation (drives the start_attempt bypass) --------------


def _scalar_result(value: object | None) -> MagicMock:
    result = MagicMock()
    result.scalar_one_or_none.return_value = value
    return result


async def test_active_none_when_absent() -> None:
    db = _db()
    db.execute.return_value = _scalar_result(None)
    assert await svc.get_active_dispensation(db, test_id=TEST_ID, student_id=STUDENT) is None


async def test_active_returns_non_expiring() -> None:
    db = _db()
    disp = ExamDispensation(id=DISP_ID, test_id=TEST_ID, student_id=STUDENT, expires_at=None)
    db.execute.return_value = _scalar_result(disp)
    assert await svc.get_active_dispensation(db, test_id=TEST_ID, student_id=STUDENT) is disp


async def test_active_returns_future_expiry() -> None:
    db = _db()
    future = dt.now(tz=UTC) + timedelta(days=1)
    disp = ExamDispensation(id=DISP_ID, test_id=TEST_ID, student_id=STUDENT, expires_at=future)
    db.execute.return_value = _scalar_result(disp)
    out = await svc.get_active_dispensation(db, test_id=TEST_ID, student_id=STUDENT)
    assert out is disp


async def test_expired_dispensation_is_inactive() -> None:
    db = _db()
    past = dt.now(tz=UTC) - timedelta(seconds=1)
    disp = ExamDispensation(id=DISP_ID, test_id=TEST_ID, student_id=STUDENT, expires_at=past)
    db.execute.return_value = _scalar_result(disp)
    out = await svc.get_active_dispensation(db, test_id=TEST_ID, student_id=STUDENT)
    assert out is None  # expired → blocked by normal gate
