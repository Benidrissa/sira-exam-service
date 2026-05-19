"""Add validation_status, validated_by, validated_at to exam_attempts.

These columns were intended to be part of migration 009 but the DB was already
at revision 009 when Track C added them, so Alembic never applied them.

Revision ID: 010
Revises: 009
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import UUID

revision = "010"
down_revision = "009"
branch_labels = None
depends_on = None

_SCHEMA = "exam_svc"


def upgrade() -> None:
    op.add_column(
        "exam_attempts",
        sa.Column(
            "validation_status",
            sa.Text(),
            nullable=False,
            server_default="pending",
        ),
        schema=_SCHEMA,
    )
    op.add_column(
        "exam_attempts",
        sa.Column("validated_by", UUID(as_uuid=True), nullable=True),
        schema=_SCHEMA,
    )
    op.add_column(
        "exam_attempts",
        sa.Column("validated_at", sa.DateTime(timezone=True), nullable=True),
        schema=_SCHEMA,
    )


def downgrade() -> None:
    for col in ("validated_at", "validated_by", "validation_status"):
        op.drop_column("exam_attempts", col, schema=_SCHEMA)
