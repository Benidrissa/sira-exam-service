"""Add term_grades table — finalised per-course/term grades (FR-4.32).

Revision ID: 016
Revises: 015
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import ENUM, UUID

revision = "016"
down_revision = "015"
branch_labels = None
depends_on = None

_SCHEMA = "exam_svc"
# Reference the existing "quarter" enum (created in migration 009) without
# recreating it. create_type=False is honoured by postgresql.ENUM (not the
# generic sa.Enum), so no CREATE TYPE is emitted.
_QUARTER = ENUM("q1", "q2", "q3", "q4", name="quarter", create_type=False)


def upgrade() -> None:
    op.create_table(
        "term_grades",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("org_id", UUID(as_uuid=True), nullable=False),
        sa.Column("student_id", UUID(as_uuid=True), nullable=False),
        sa.Column("course_code", sa.String(length=32), nullable=False),
        sa.Column("class_id", UUID(as_uuid=True), nullable=False),
        sa.Column("academic_year", sa.String(length=16), nullable=False),
        sa.Column("quarter", _QUARTER, nullable=False),
        sa.Column("weighted_avg", sa.Float(), nullable=True),
        sa.Column("grade_letter", sa.String(length=4), nullable=True),
        sa.Column(
            "finalized_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("superseded_by", UUID(as_uuid=True), nullable=True),
        sa.ForeignKeyConstraint(["class_id"], [f"{_SCHEMA}.school_classes.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["superseded_by"],
            [f"{_SCHEMA}.term_grades.id"],
            ondelete="SET NULL",
            use_alter=True,
            name="fk_term_grades_superseded_by",
        ),
        schema=_SCHEMA,
    )
    op.create_index("ix_term_grades_org_id", "term_grades", ["org_id"], schema=_SCHEMA)
    op.create_index("ix_term_grades_student_id", "term_grades", ["student_id"], schema=_SCHEMA)
    op.create_index("ix_term_grades_class_id", "term_grades", ["class_id"], schema=_SCHEMA)


def downgrade() -> None:
    for idx in (
        "ix_term_grades_class_id",
        "ix_term_grades_student_id",
        "ix_term_grades_org_id",
    ):
        op.drop_index(idx, table_name="term_grades", schema=_SCHEMA)
    op.drop_table("term_grades", schema=_SCHEMA)
