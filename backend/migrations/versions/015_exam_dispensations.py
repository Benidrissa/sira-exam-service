"""Add exam_dispensations table — student exemptions (FR-4.29).

Revision ID: 015
Revises: 014
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import UUID

revision = "015"
down_revision = "014"
branch_labels = None
depends_on = None

_SCHEMA = "exam_svc"


def upgrade() -> None:
    op.create_table(
        "exam_dispensations",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("org_id", UUID(as_uuid=True), nullable=False),
        sa.Column("student_id", UUID(as_uuid=True), nullable=False),
        sa.Column("test_id", UUID(as_uuid=True), nullable=False),
        sa.Column("class_id", UUID(as_uuid=True), nullable=False),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column("granted_by", UUID(as_uuid=True), nullable=False),
        sa.Column(
            "granted_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["test_id"], [f"{_SCHEMA}.exam_tests.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["class_id"], [f"{_SCHEMA}.school_classes.id"], ondelete="CASCADE"),
        sa.UniqueConstraint("test_id", "student_id", name="uq_dispensation_test_student"),
        schema=_SCHEMA,
    )
    op.create_index(
        "ix_exam_dispensations_org_id", "exam_dispensations", ["org_id"], schema=_SCHEMA
    )
    op.create_index(
        "ix_exam_dispensations_student_id",
        "exam_dispensations",
        ["student_id"],
        schema=_SCHEMA,
    )
    op.create_index(
        "ix_exam_dispensations_test_id",
        "exam_dispensations",
        ["test_id"],
        schema=_SCHEMA,
    )
    op.create_index(
        "ix_exam_dispensations_class_id",
        "exam_dispensations",
        ["class_id"],
        schema=_SCHEMA,
    )


def downgrade() -> None:
    for idx in (
        "ix_exam_dispensations_class_id",
        "ix_exam_dispensations_test_id",
        "ix_exam_dispensations_student_id",
        "ix_exam_dispensations_org_id",
    ):
        op.drop_index(idx, table_name="exam_dispensations", schema=_SCHEMA)
    op.drop_table("exam_dispensations", schema=_SCHEMA)
