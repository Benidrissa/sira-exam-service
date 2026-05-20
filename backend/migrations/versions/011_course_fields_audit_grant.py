"""Add course fields to exam_banks, archived_at to school_classes, exam_access_grants, review_audit_logs.

Revision ID: 011
Revises: 010
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB, UUID

revision = "011"
down_revision = "010"
branch_labels = None
depends_on = None

_SCHEMA = "exam_svc"


def upgrade() -> None:
    # --- ExamBank: course identity (FR-4.18) ----------------------------------
    op.add_column(
        "exam_banks",
        sa.Column("course_code", sa.String(32), nullable=True),
        schema=_SCHEMA,
    )
    op.add_column(
        "exam_banks",
        sa.Column("course_name", sa.Text(), nullable=True),
        schema=_SCHEMA,
    )

    # --- SchoolClass: archival (FR-4.19) -------------------------------------
    op.add_column(
        "school_classes",
        sa.Column("archived_at", sa.DateTime(timezone=True), nullable=True),
        schema=_SCHEMA,
    )

    # --- exam_access_grants (FR-4.20) -----------------------------------------
    op.create_table(
        "exam_access_grants",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "bank_id",
            UUID(as_uuid=True),
            sa.ForeignKey(f"{_SCHEMA}.exam_banks.id", ondelete="CASCADE"),
            nullable=True,
        ),
        sa.Column(
            "test_id",
            UUID(as_uuid=True),
            sa.ForeignKey(f"{_SCHEMA}.exam_tests.id", ondelete="CASCADE"),
            nullable=True,
        ),
        sa.Column("student_id", UUID(as_uuid=True), nullable=False),
        sa.Column("granted_by", UUID(as_uuid=True), nullable=False),
        sa.Column("org_id", UUID(as_uuid=True), nullable=False),
        sa.Column(
            "granted_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            "bank_id IS NOT NULL OR test_id IS NOT NULL",
            name="ck_grant_target",
        ),
        schema=_SCHEMA,
    )
    op.create_index(
        "ix_exam_access_grants_bank_id", "exam_access_grants", ["bank_id"], schema=_SCHEMA
    )
    op.create_index(
        "ix_exam_access_grants_test_id", "exam_access_grants", ["test_id"], schema=_SCHEMA
    )
    op.create_index(
        "ix_exam_access_grants_student_id", "exam_access_grants", ["student_id"], schema=_SCHEMA
    )
    op.create_index(
        "ix_exam_access_grants_org_id", "exam_access_grants", ["org_id"], schema=_SCHEMA
    )

    # --- review_audit_logs (FR-4.21) ------------------------------------------
    op.create_table(
        "review_audit_logs",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "answer_id",
            UUID(as_uuid=True),
            sa.ForeignKey(f"{_SCHEMA}.dissertation_answers.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("attempt_id", UUID(as_uuid=True), nullable=False),
        sa.Column("test_id", UUID(as_uuid=True), nullable=False),
        sa.Column("org_id", UUID(as_uuid=True), nullable=False),
        sa.Column("actor_id", UUID(as_uuid=True), nullable=False),
        sa.Column("actor_role", sa.Text(), nullable=False),
        sa.Column("action", sa.Text(), nullable=False),
        sa.Column("old_values", JSONB(), nullable=True),
        sa.Column("new_values", JSONB(), nullable=False),
        sa.Column(
            "occurred_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        schema=_SCHEMA,
    )
    op.create_index(
        "ix_review_audit_logs_answer_id", "review_audit_logs", ["answer_id"], schema=_SCHEMA
    )
    op.create_index(
        "ix_review_audit_logs_attempt_id", "review_audit_logs", ["attempt_id"], schema=_SCHEMA
    )
    op.create_index(
        "ix_review_audit_logs_test_id", "review_audit_logs", ["test_id"], schema=_SCHEMA
    )
    op.create_index(
        "ix_review_audit_logs_org_id", "review_audit_logs", ["org_id"], schema=_SCHEMA
    )


def downgrade() -> None:
    op.drop_table("review_audit_logs", schema=_SCHEMA)
    op.drop_table("exam_access_grants", schema=_SCHEMA)
    op.drop_column("school_classes", "archived_at", schema=_SCHEMA)
    op.drop_column("exam_banks", "course_name", schema=_SCHEMA)
    op.drop_column("exam_banks", "course_code", schema=_SCHEMA)
