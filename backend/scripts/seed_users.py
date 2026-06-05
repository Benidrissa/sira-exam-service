"""Seed the 3 university test accounts (idempotent) + a takeable exam.

Run inside the backend container with passwords supplied via env:

    docker exec \
      -e SEED_TEACHER_PASSWORD=... \
      -e SEED_STUDENT_PASSWORD=... \
      -e SEED_ADMIN_PASSWORD=... \
      sira-exam-service-backend-1 python scripts/seed_users.py

Passwords are NEVER hardcoded or committed. Re-running is safe.
"""

from __future__ import annotations

import asyncio
import os
import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy import select

from app.core.database import AsyncSessionLocal
from app.domain.models.exam import (
    ClassMember,
    ExamBank,
    ExamTest,
    Quarter,
    SchoolClass,
    TestAssignment,
    TestStatus,
    User,
)
from app.domain.services import password_service

ORG = uuid.UUID("aaaaaaaa-0000-0000-0000-000000000001")
TEACHER_ID = uuid.UUID("cccccccc-0000-0000-0000-000000000001")  # existing demo teacher
STUDENT_ID = uuid.UUID("dddddddd-0000-0000-0000-000000000002")  # existing demo student
ADMIN_ID = uuid.UUID("bbbbbbbb-0000-0000-0000-000000000001")  # new admin

ACCOUNTS = [
    ("teacher@sira.test", "University Teacher", TEACHER_ID, "expert", "SEED_TEACHER_PASSWORD"),
    ("student@sira.test", "University Student", STUDENT_ID, "user", "SEED_STUDENT_PASSWORD"),
    ("admin@sira.test", "University Admin", ADMIN_ID, "admin", "SEED_ADMIN_PASSWORD"),
]


async def _upsert_user(db, email, name, uid, role, password) -> None:
    existing = (await db.execute(select(User).where(User.email == email))).scalar_one_or_none()
    pw_hash = password_service.hash_password(password)
    if existing:
        existing.password_hash = pw_hash
        existing.role = role
        existing.is_active = True
        existing.failed_password_attempts = 0
        existing.password_locked_until = None
        print(f"  updated  {email} ({role}) id={existing.id}")
    else:
        db.add(
            User(
                id=uid,
                email=email,
                name=name,
                password_hash=pw_hash,
                role=role,
                org_id=ORG,
                is_active=True,
            )
        )
        print(f"  created  {email} ({role}) id={uid}")


async def _seed_takeable_exam(db) -> None:
    """Ensure the student is enrolled in a class with an open, published test."""
    # 1) class
    cls = (
        await db.execute(
            select(SchoolClass).where(
                SchoolClass.org_id == ORG,
                SchoolClass.name == "University Test Class",
                SchoolClass.academic_year == "2025-2026",
            )
        )
    ).scalar_one_or_none()
    if cls is None:
        cls = SchoolClass(
            org_id=ORG,
            name="University Test Class",
            academic_year="2025-2026",
            created_by=TEACHER_ID,
        )
        db.add(cls)
        await db.flush()
        print(f"  created  class {cls.id}")
    else:
        print(f"  class exists {cls.id}")

    # 2) enroll student
    member = (
        await db.execute(
            select(ClassMember).where(
                ClassMember.class_id == cls.id, ClassMember.user_id == STUDENT_ID
            )
        )
    ).scalar_one_or_none()
    if member is None:
        db.add(ClassMember(class_id=cls.id, user_id=STUDENT_ID, added_by=TEACHER_ID))
        print("  enrolled student")
    else:
        print("  student already enrolled")

    # 3) a published test owned by the teacher
    test = (
        await db.execute(
            select(ExamTest)
            .join(ExamBank, ExamTest.bank_id == ExamBank.id)
            .where(
                ExamBank.org_id == ORG,
                ExamTest.created_by == TEACHER_ID,
                ExamTest.status == TestStatus.published,
            )
            .limit(1)
        )
    ).scalar_one_or_none()
    if test is None:
        print("  WARN: no published test owned by the teacher — skipping assignment")
        return

    # 4) assign with an open window
    assignment = (
        await db.execute(
            select(TestAssignment).where(
                TestAssignment.test_id == test.id, TestAssignment.class_id == cls.id
            )
        )
    ).scalar_one_or_none()
    now = datetime.now(UTC)
    if assignment is None:
        db.add(
            TestAssignment(
                test_id=test.id,
                class_id=cls.id,
                released_at=now - timedelta(days=1),
                closes_at=now + timedelta(days=30),
                quarter=Quarter.q1,
                assigned_by=TEACHER_ID,
            )
        )
        print(f"  assigned test {test.id} (open until +30d)")
    else:
        # keep the window open on re-run
        assignment.released_at = now - timedelta(days=1)
        assignment.closes_at = now + timedelta(days=30)
        print(f"  assignment exists for test {test.id} — window refreshed")


async def main() -> None:
    missing = [env for *_, env in ACCOUNTS if not os.environ.get(env)]
    if missing:
        raise SystemExit(f"Missing required password env vars: {', '.join(missing)}")

    async with AsyncSessionLocal() as db:
        print("Seeding users:")
        for email, name, uid, role, env in ACCOUNTS:
            await _upsert_user(db, email, name, uid, role, os.environ[env])
        print("Seeding takeable exam:")
        await _seed_takeable_exam(db)
        await db.commit()
    print("Done.")


if __name__ == "__main__":
    asyncio.run(main())
