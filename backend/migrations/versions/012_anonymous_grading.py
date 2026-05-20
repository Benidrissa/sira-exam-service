"""Add anonymous_grading to exam_tests and anon_id to exam_attempts (FR-4.24).

Revision ID: 012
Revises: 011
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import UUID

revision = "012"
down_revision = "011"
branch_labels = None
depends_on = None

_SCHEMA = "exam_svc"


def upgrade() -> None:
    # --- ExamTest: anonymous grading flag -----------------------------------
    op.add_column(
        "exam_tests",
        sa.Column(
            "anonymous_grading",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
        schema=_SCHEMA,
    )

    # --- ExamAttempt: stable random anon_id ---------------------------------
    # Add nullable first so the column can be created on a table with existing rows
    op.add_column(
        "exam_attempts",
        sa.Column("anon_id", UUID(as_uuid=True), nullable=True),
        schema=_SCHEMA,
    )

    # Backfill: assign a UUID to every existing attempt
    op.execute(
        f"UPDATE {_SCHEMA}.exam_attempts SET anon_id = gen_random_uuid() WHERE anon_id IS NULL"
    )

    # Enforce NOT NULL
    op.alter_column("exam_attempts", "anon_id", nullable=False, schema=_SCHEMA)

    # Unique index — one anon_id per attempt, used as a stable opaque identifier
    op.create_index(
        "ix_exam_attempts_anon_id",
        "exam_attempts",
        ["anon_id"],
        unique=True,
        schema=_SCHEMA,
    )


def downgrade() -> None:
    op.drop_index("ix_exam_attempts_anon_id", table_name="exam_attempts", schema=_SCHEMA)
    op.drop_column("exam_attempts", "anon_id", schema=_SCHEMA)
    op.drop_column("exam_tests", "anonymous_grading", schema=_SCHEMA)
