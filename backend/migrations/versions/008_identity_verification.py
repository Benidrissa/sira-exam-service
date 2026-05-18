"""Add identity verification columns to exam_sessions (E3-15).

Revision ID: 008
Revises: 007
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "008"
down_revision = "007"
branch_labels = None
depends_on = None

_SCHEMA = "exam_svc"


def upgrade() -> None:
    op.add_column(
        "exam_sessions",
        sa.Column("identity_verified", sa.Boolean(), nullable=False, server_default="false"),
        schema=_SCHEMA,
    )
    op.add_column(
        "exam_sessions",
        sa.Column("identity_selfie_key", sa.Text(), nullable=True),
        schema=_SCHEMA,
    )
    op.add_column(
        "exam_sessions",
        sa.Column("identity_status", sa.String(20), nullable=True),
        schema=_SCHEMA,
    )
    op.add_column(
        "exam_sessions",
        sa.Column(
            "identity_verified_at",
            sa.DateTime(timezone=True),
            nullable=True,
        ),
        schema=_SCHEMA,
    )


def downgrade() -> None:
    for col in ("identity_verified_at", "identity_status", "identity_selfie_key", "identity_verified"):
        op.drop_column("exam_sessions", col, schema=_SCHEMA)
