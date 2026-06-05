"""Regression test for get_student_available_tests (scheduled-exams dashboard).

A student can have more than one attempt row for a test (e.g. an abandoned,
unsubmitted attempt). The per-test lookup must take the most recent rather than
assuming exactly one (which raised MultipleResultsFound → 500). The mocked
session can't reproduce the DB-level raise, so this guards the happy path and
asserts the query is limited to one row.
"""

from __future__ import annotations

import uuid
from datetime import UTC, timedelta
from datetime import datetime as dt
from unittest.mock import AsyncMock, MagicMock

from app.domain.models.exam import (
    ClassMember,
    ExamAttempt,
    ExamBank,
    ExamTest,
    Quarter,
    SchoolClass,
    TestAssignment,
)
from app.domain.services import school_class_service as svc

ORG = uuid.UUID("aaaaaaaa-0000-0000-0000-000000000001")
STUDENT = uuid.UUID("dddddddd-0000-0000-0000-000000000002")
CLASS_ID = uuid.UUID("dddddddd-0000-0000-0000-000000000009")
NOW = dt.now(tz=UTC)


def _scalar(value):
    r = MagicMock()
    r.scalar_one_or_none.return_value = value
    return r


def _scalars(items):
    r = MagicMock()
    r.scalars.return_value.all.return_value = items
    return r


async def test_returns_latest_attempt_without_crashing() -> None:
    test = ExamTest(id=uuid.uuid4(), bank_id=uuid.uuid4(), title="Midterm", exam_weight=1.0)
    asgn = TestAssignment(
        id=uuid.uuid4(),
        test_id=test.id,
        class_id=CLASS_ID,
        released_at=NOW - timedelta(days=1),
        closes_at=NOW + timedelta(days=1),
        quarter=Quarter.q1,
    )
    asgn.test = test
    asgn.school_class = SchoolClass(id=CLASS_ID, org_id=ORG, name="C", academic_year="2025-2026")
    latest = ExamAttempt(id=uuid.uuid4(), test_id=test.id, user_id=STUDENT)
    bank = ExamBank(id=test.bank_id, org_id=ORG, title_fr="B", language="fr", passing_score=60.0)

    db = MagicMock()
    db.execute = AsyncMock(
        side_effect=[
            _scalars([ClassMember(class_id=CLASS_ID, user_id=STUDENT)]),  # members
            _scalars([asgn]),  # assignments
            _scalar(latest),  # per-test attempt (LIMIT 1 → at most one row)
            _scalar(bank),  # bank
        ]
    )

    rows = await svc.get_student_available_tests(db, user_id=STUDENT, org_id=ORG)
    assert len(rows) == 1
    assert rows[0]["has_attempted"] is True
    assert rows[0]["attempt_id"] == latest.id

    # The attempt query must be limited so multiple rows can't raise.
    attempt_stmt = str(db.execute.await_args_list[2].args[0])
    assert "LIMIT" in attempt_stmt.upper()
