"""Add grade_scales table — per-org letter/GPA scale (FR-4.28).

Revision ID: 014
Revises: 013
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import UUID

revision = "014"
down_revision = "013"
branch_labels = None
depends_on = None

_SCHEMA = "exam_svc"


def upgrade() -> None:
    op.create_table(
        "grade_scales",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("org_id", UUID(as_uuid=True), nullable=False),
        sa.Column("min_score", sa.Float(), nullable=False),
        sa.Column("max_score", sa.Float(), nullable=False),
        sa.Column("letter", sa.String(length=4), nullable=False),
        sa.Column("gpa_points", sa.Float(), nullable=False),
        sa.Column("sort_order", sa.Integer(), nullable=False),
        schema=_SCHEMA,
    )
    op.create_index("ix_grade_scales_org_id", "grade_scales", ["org_id"], schema=_SCHEMA)


def downgrade() -> None:
    op.drop_index("ix_grade_scales_org_id", table_name="grade_scales", schema=_SCHEMA)
    op.drop_table("grade_scales", schema=_SCHEMA)
