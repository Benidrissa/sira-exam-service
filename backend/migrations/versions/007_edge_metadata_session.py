"""007 — add edge_metadata JSONB to exam_sessions (E3-10)

Revision ID: 007
Revises: 006
Create Date: 2026-05-16
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "007"
down_revision = "006"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "exam_sessions",
        sa.Column("edge_metadata", postgresql.JSONB(), nullable=True),
        schema="exam_svc",
    )


def downgrade() -> None:
    op.drop_column("exam_sessions", "edge_metadata", schema="exam_svc")
