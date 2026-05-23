"""Unit tests for TestAssignment overlap guard (FR-4.3 / FR-4.4).

All tests use a mocked AsyncSession — no real DB required.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import HTTPException

from app.domain.models.exam import (
    ExamTest,
    Quarter,
    SchoolClass,
    TestAssignment,
    TestMode,
    TestStatus,
)
from app.domain.services import school_class_service

# ---------------------------------------------------------------------------
# Stable IDs
# ---------------------------------------------------------------------------

ORG = uuid.UUID("aaaaaaaa-0000-0000-0000-000000000001")
TEACHER = uuid.UUID("cccccccc-0000-0000-0000-000000000001")
BANK_ID = uuid.UUID("dddddddd-0000-0000-0000-000000000001")
TEST_ID = uuid.UUID("eeeeeeee-0000-0000-0000-000000000001")
CLASS_ID = uuid.UUID("ffffffff-0000-0000-0000-000000000001")

T0 = datetime(2026, 6, 1, 9, 0, tzinfo=UTC)  # 09:00
T1 = datetime(2026, 6, 1, 11, 0, tzinfo=UTC)  # 11:00
T2 = datetime(2026, 6, 1, 13, 0, tzinfo=UTC)  # 13:00

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _mock_db() -> AsyncMock:
    db = AsyncMock()
    db.add = MagicMock()
    db.commit = AsyncMock()
    db.refresh = AsyncMock()
    db.execute = AsyncMock()
    db.scalar = AsyncMock()
    return db


def _scalar(value):
    result = MagicMock()
    result.scalar_one_or_none.return_value = value
    return result


def _make_test() -> ExamTest:
    return ExamTest(
        id=TEST_ID,
        bank_id=BANK_ID,
        created_by=TEACHER,
        title="Midterm",
        mode=TestMode.exam,
        shuffle_questions=False,
        show_feedback=False,
        mcq_weight=1.0,
        dissertation_weight=1.0,
        status=TestStatus.published,
    )


def _make_class() -> SchoolClass:
    return SchoolClass(
        id=CLASS_ID,
        org_id=ORG,
        created_by=TEACHER,
        name="6ème A",
        academic_year="2025-2026",
    )


def _make_assignment(
    released_at: datetime,
    closes_at: datetime,
    assignment_id: uuid.UUID | None = None,
) -> TestAssignment:
    return TestAssignment(
        id=assignment_id or uuid.uuid4(),
        test_id=TEST_ID,
        class_id=CLASS_ID,
        released_at=released_at,
        closes_at=closes_at,
        quarter=Quarter.q1,
        assigned_by=TEACHER,
    )


# ---------------------------------------------------------------------------
# TC-1: create — overlap raises 409
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_create_overlap_raises_409() -> None:
    """Creating an assignment whose window overlaps an existing one raises 409."""
    db = _mock_db()
    existing_id = uuid.uuid4()

    # Call order inside create_assignment:
    #   1. select(ExamTest).join(ExamBank) — verify test
    #   2. select(SchoolClass) — verify class
    # db.scalar is used for the overlap check
    db.execute.side_effect = [
        _scalar(_make_test()),  # test exists and is published
        _scalar(_make_class()),  # class exists
    ]
    # Overlap check finds a conflict
    db.scalar.return_value = existing_id

    with pytest.raises(HTTPException) as exc_info:
        await school_class_service.create_assignment(
            db,
            test_id=TEST_ID,
            class_id=CLASS_ID,
            org_id=ORG,
            released_at=T0,  # 09:00 – 13:00 overlaps existing 09:00 – 11:00
            closes_at=T2,
            quarter=Quarter.q1,
            assigned_by=TEACHER,
        )

    assert exc_info.value.status_code == 409
    assert "window" in exc_info.value.detail.lower()


# ---------------------------------------------------------------------------
# TC-2: create — adjacent windows (no overlap) succeeds
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_create_no_overlap_ok() -> None:
    """Adjacent windows (new starts exactly when existing closes) are allowed."""
    db = _mock_db()

    db.execute.side_effect = [
        _scalar(_make_test()),  # test
        _scalar(_make_class()),  # class
    ]
    # No conflict found
    db.scalar.return_value = None
    db.refresh.side_effect = lambda obj: None

    await school_class_service.create_assignment(
        db,
        test_id=TEST_ID,
        class_id=CLASS_ID,
        org_id=ORG,
        released_at=T1,  # 11:00–13:00 is adjacent to a hypothetical 09:00–11:00
        closes_at=T2,
        quarter=Quarter.q1,
        assigned_by=TEACHER,
    )

    # db.add was called → assignment created
    assert db.add.called


# ---------------------------------------------------------------------------
# TC-3: update — shift into overlap raises 409
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_update_overlap_raises_409() -> None:
    """Extending an assignment's window to overlap another raises 409."""
    db = _mock_db()
    assignment_id = uuid.uuid4()
    existing = _make_assignment(T0, T1, assignment_id=assignment_id)

    # Call order inside update_assignment:
    #   1. select(TestAssignment).join(ExamTest).join(ExamBank) — fetch assignment
    # db.scalar used for overlap check
    db.execute.return_value = _scalar(existing)
    conflict_id = uuid.uuid4()
    db.scalar.return_value = conflict_id  # overlap found

    with pytest.raises(HTTPException) as exc_info:
        await school_class_service.update_assignment(
            db,
            assignment_id=assignment_id,
            org_id=ORG,
            closes_at=T2,  # extend 09:00 – 11:00 to 09:00 – 13:00, overlapping another
        )

    assert exc_info.value.status_code == 409
    assert "overlap" in exc_info.value.detail.lower() or "window" in exc_info.value.detail.lower()


# ---------------------------------------------------------------------------
# TC-4: update — self-overlap excluded; updating own dates succeeds
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_update_self_excluded() -> None:
    """Updating an assignment's own dates without touching others succeeds."""
    db = _mock_db()
    assignment_id = uuid.uuid4()
    existing = _make_assignment(T0, T1, assignment_id=assignment_id)

    db.execute.return_value = _scalar(existing)
    # No OTHER conflict (self is excluded from the query)
    db.scalar.return_value = None

    await school_class_service.update_assignment(
        db,
        assignment_id=assignment_id,
        org_id=ORG,
        closes_at=T1 + timedelta(minutes=30),
    )

    assert db.commit.called
