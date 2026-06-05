"""Add users table — real password authentication.

Revision ID: 017
Revises: 016
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import UUID

revision = "017"
down_revision = "016"
branch_labels = None
depends_on = None

_SCHEMA = "exam_svc"


def upgrade() -> None:
    op.create_table(
        "users",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("email", sa.String(length=255), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False, server_default=""),
        sa.Column("password_hash", sa.String(length=255), nullable=False),
        sa.Column("role", sa.String(length=16), nullable=False, server_default="user"),
        sa.Column("org_id", UUID(as_uuid=True), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column(
            "failed_password_attempts",
            sa.Integer(),
            nullable=False,
            server_default="0",
        ),
        sa.Column("password_locked_until", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
        ),
        schema=_SCHEMA,
    )
    op.create_index("ix_users_email", "users", ["email"], unique=True, schema=_SCHEMA)
    op.create_index("ix_users_org_id", "users", ["org_id"], schema=_SCHEMA)


def downgrade() -> None:
    op.drop_index("ix_users_org_id", table_name="users", schema=_SCHEMA)
    op.drop_index("ix_users_email", table_name="users", schema=_SCHEMA)
    op.drop_table("users", schema=_SCHEMA)
