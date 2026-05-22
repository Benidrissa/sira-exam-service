"""Unit tests for anonymous grading (FR-4.24) — service layer.

Tests use mocked AsyncSession so they work without a real database.
"""

from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import HTTPException

from app.domain.models.exam import (
    ExamAttempt,
    ExamBank,
    ExamTest,
    TestMode,
    TestStatus,
)
from app.domain.services import exam_submission_service

# ---------------------------------------------------------------------------
# Stable IDs
# ---------------------------------------------------------------------------

ORG_A = uuid.UUID("aaaaaaaa-0000-0000-0000-000000000001")
TEACHER_ID = uuid.UUID("cccccccc-0000-0000-0000-000000000001")
BANK_ID = uuid.UUID("dddddddd-0000-0000-0000-000000000001")
TEST_ID = uuid.UUID("eeeeeeee-0000-0000-0000-000000000001")
STUDENT_A = uuid.UUID("11111111-0000-0000-0000-000000000001")
STUDENT_B = uuid.UUID("22222222-0000-0000-0000-000000000002")
ANON_A = uuid.UUID("aaaaaaaa-1111-0000-0000-000000000001")
ANON_B = uuid.UUID("bbbbbbbb-2222-0000-0000-000000000002")

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_test(anonymous_grading: bool = False) -> ExamTest:
    test = ExamTest(
        id=TEST_ID,
        bank_id=BANK_ID,
        created_by=TEACHER_ID,
        title="Midterm",
        mode=TestMode.exam,
        shuffle_questions=False,
        show_feedback=False,
        mcq_weight=1.0,
        dissertation_weight=1.0,
        status=TestStatus.published,
        anonymous_grading=anonymous_grading,
    )
    return test


def _make_attempt(
    user_id: uuid.UUID,
    anon_id: uuid.UUID,
    validation_status: str = "pending",
) -> ExamAttempt:
    attempt = ExamAttempt(
        id=uuid.uuid4(),
        test_id=TEST_ID,
        user_id=user_id,
        anon_id=anon_id,
        question_ids=[],
        mcq_answers={"q1": [0]},  # non-null = submitted
        mcq_score=80.0,
        total_score=80.0,
        passed=True,
        validation_status=validation_status,
    )
    return attempt


def _mock_db() -> AsyncMock:
    db = AsyncMock()
    db.add = MagicMock()
    db.commit = AsyncMock()
    db.refresh = AsyncMock()
    db.execute = AsyncMock()
    db.get = AsyncMock()
    db.scalar = AsyncMock()
    return db


# ---------------------------------------------------------------------------
# TC-1: submissions list masks user_id when anonymous_grading=True
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_list_submissions_anonymous_masks_user_id() -> None:
    """AC1 — user_id replaced with anon_id when anonymous_grading=True."""
    db = _mock_db()
    test = _make_test(anonymous_grading=True)
    bank = ExamBank(
        id=BANK_ID,
        org_id=ORG_A,
        created_by=TEACHER_ID,
        title_fr="B",
        language="fr",
        passing_score=80.0,
    )
    attempt = _make_attempt(STUDENT_A, ANON_A, validation_status="pending")
    attempt.dissertation_answers = []

    # _get_test_with_org_guard returns test
    db.execute.side_effect = [
        # Execute call order inside list_test_submissions:
        #   1. _get_test_with_org_guard (ExamTest join)
        #   2. select(ExamAttempt) — submitted attempts
        #   3. select(TestAssignment) — for class resolution
        # db.get() is called separately for ExamBank (not in side_effect chain)
        _scalar(test),  # call 1
        _scalars([attempt]),  # call 2
        _scalars([]),  # call 3 (no assignments)
    ]
    db.get.return_value = bank

    rows = await exam_submission_service.list_test_submissions(db, test_id=TEST_ID, org_id=ORG_A)

    assert db.execute.call_count == 3, "Expected exactly 3 db.execute calls"
    assert len(rows) == 1
    # user_id field should carry the anon_id value, not the real student ID
    assert rows[0]["user_id"] == ANON_A
    assert rows[0]["user_id"] != STUDENT_A


# ---------------------------------------------------------------------------
# TC-2: anonymous_grading=False leaves user_id unchanged (AC5 regression)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_list_submissions_non_anonymous_preserves_user_id() -> None:
    """AC5 — existing behaviour unchanged when anonymous_grading=False."""
    db = _mock_db()
    test = _make_test(anonymous_grading=False)
    bank = ExamBank(
        id=BANK_ID,
        org_id=ORG_A,
        created_by=TEACHER_ID,
        title_fr="B",
        language="fr",
        passing_score=80.0,
    )
    attempt = _make_attempt(STUDENT_A, ANON_A, validation_status="pending")
    attempt.dissertation_answers = []

    db.execute.side_effect = [
        _scalar(test),  # call 1: _get_test_with_org_guard
        _scalars([attempt]),  # call 2: submitted attempts
        _scalars([]),  # call 3: TestAssignment (none)
    ]
    db.get.return_value = bank

    rows = await exam_submission_service.list_test_submissions(db, test_id=TEST_ID, org_id=ORG_A)

    assert db.execute.call_count == 3, "Expected exactly 3 db.execute calls"
    assert len(rows) == 1
    assert rows[0]["user_id"] == STUDENT_A


# ---------------------------------------------------------------------------
# TC-3: anon_id is set at attempt creation (AC7 — student flow unaffected)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_attempt_creation_assigns_anon_id() -> None:
    """AC7 — start_attempt assigns anon_id; stored data is not masked."""
    from app.domain.models.exam import ExamQuestion, QuestionType
    from app.domain.services.exam_attempt_service import start_attempt as start_exam_attempt

    db = _mock_db()
    test = _make_test(anonymous_grading=True)

    q = ExamQuestion(
        id=uuid.uuid4(),
        bank_id=BANK_ID,
        question_type=QuestionType.mcq,
        description="Q1",
        order_index=0,
        ai_generated=False,
        validated=True,
    )

    # Call order inside start_attempt:
    #   1. select(ExamTest).join(ExamBank) — load test
    #   2. select(ExamAttempt) — guard: no prior submitted attempt
    #   3. select(ExamQuestion) — fetch validated questions
    db.execute.side_effect = [
        _scalar(test),  # load test
        _scalar(None),  # no existing attempt
        _scalars([q]),  # load questions
    ]

    created_attempt = ExamAttempt(
        id=uuid.uuid4(),
        test_id=TEST_ID,
        user_id=STUDENT_A,
        anon_id=uuid.uuid4(),
        question_ids=[str(q.id)],
    )
    db.refresh.side_effect = lambda obj: setattr(obj, "anon_id", created_attempt.anon_id)

    attempt_obj, _, _ = await start_exam_attempt(
        db, test_id=TEST_ID, user_id=STUDENT_A, org_id=ORG_A
    )

    # user_id on the stored object must be the real student ID (no masking in storage)
    assert attempt_obj.user_id == STUDENT_A


# ---------------------------------------------------------------------------
# TC-4: anon-mapping returns 409 while any attempt is unvalidated (AC3)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_anon_mapping_409_when_unvalidated_exists() -> None:
    """AC3 — 409 raised if any submitted attempt still unvalidated."""
    db = _mock_db()
    test = _make_test(anonymous_grading=True)

    db.execute.side_effect = [_scalar(test)]
    db.scalar.return_value = 1  # 1 unvalidated attempt

    with pytest.raises(HTTPException) as exc:
        await exam_submission_service.get_anon_mapping(db, test_id=TEST_ID, org_id=ORG_A)

    assert exc.value.status_code == 409
    assert "unvalidated" in exc.value.detail.lower()


# ---------------------------------------------------------------------------
# TC-5: anon-mapping returns full mapping after all validated (AC4)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_anon_mapping_returns_mapping_when_all_validated() -> None:
    """AC4 — mapping returned correctly when all attempts validated."""
    db = _mock_db()
    test = _make_test(anonymous_grading=True)

    # Simulate rows returned from SELECT anon_id, user_id
    row_a = MagicMock()
    row_a.anon_id = ANON_A
    row_a.user_id = STUDENT_A
    row_b = MagicMock()
    row_b.anon_id = ANON_B
    row_b.user_id = STUDENT_B

    db.execute.side_effect = [
        _scalar(test),  # _get_test_with_org_guard
        _rows([row_a, row_b]),  # SELECT anon_id, user_id
    ]
    db.scalar.return_value = 0  # no unvalidated attempts

    result = await exam_submission_service.get_anon_mapping(db, test_id=TEST_ID, org_id=ORG_A)

    assert len(result) == 2
    ids = {r["anon_id"]: r["user_id"] for r in result}
    assert ids[ANON_A] == STUDENT_A
    assert ids[ANON_B] == STUDENT_B


# ---------------------------------------------------------------------------
# Mock helpers
# ---------------------------------------------------------------------------


def _scalar(value: object) -> AsyncMock:
    """Return a mock execute result whose scalar_one_or_none() returns value."""
    result = MagicMock()
    result.scalar_one_or_none = MagicMock(return_value=value)
    result.scalars = MagicMock(return_value=MagicMock(all=MagicMock(return_value=[])))
    result.all = MagicMock(return_value=[])
    return result


def _scalars(items: list) -> AsyncMock:
    """Return a mock execute result whose scalars().all() returns items."""
    result = MagicMock()
    result.scalar_one_or_none = MagicMock(return_value=items[0] if items else None)
    inner = MagicMock()
    inner.all = MagicMock(return_value=items)
    result.scalars = MagicMock(return_value=inner)
    result.all = MagicMock(return_value=items)
    return result


def _rows(items: list) -> AsyncMock:
    """Return a mock execute result whose .all() returns items."""
    result = MagicMock()
    result.all = MagicMock(return_value=items)
    result.scalar_one_or_none = MagicMock(return_value=None)
    result.scalars = MagicMock(return_value=MagicMock(all=MagicMock(return_value=[])))
    return result
