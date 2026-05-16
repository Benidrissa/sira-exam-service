"""004 — add snapshot_interval_ms to exam_sessions (E3-1)

Revision ID: 004
Revises: 003
Create Date: 2026-05-16
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "004"
down_revision = "003"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "exam_sessions",
        sa.Column(
            "snapshot_interval_ms",
            sa.Integer(),
            nullable=False,
            server_default="10000",
        ),
        schema="exam_svc",
    )


def downgrade() -> None:
    op.drop_column("exam_sessions", "snapshot_interval_ms", schema="exam_svc")
