"""002 — add ExamSource.error_message and DissertationAnswer.criterion_scores

Revision ID: 002
Revises: 001
Create Date: 2026-05-14
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "002"
down_revision = "001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "exam_sources",
        sa.Column("error_message", sa.Text(), nullable=True),
        schema="exam_svc",
    )
    op.add_column(
        "dissertation_answers",
        sa.Column("criterion_scores", postgresql.JSONB(), nullable=True),
        schema="exam_svc",
    )


def downgrade() -> None:
    op.drop_column("dissertation_answers", "criterion_scores", schema="exam_svc")
    op.drop_column("exam_sources", "error_message", schema="exam_svc")
