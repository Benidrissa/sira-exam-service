"""006 — Edge AI server foundations: merge 004+005, ProctorSnapshot edge columns (E3-9)

Revision ID: 006
Revises: 004, 005
Create Date: 2026-05-16
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "006"
down_revision = ("004", "005")
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "proctor_snapshots", sa.Column("frame_sha256", sa.Text(), nullable=True), schema="exam_svc"
    )
    op.add_column(
        "proctor_snapshots", sa.Column("edge_verdict", sa.Text(), nullable=True), schema="exam_svc"
    )
    op.add_column(
        "proctor_snapshots",
        sa.Column("edge_confidence", sa.Float(), nullable=True),
        schema="exam_svc",
    )
    op.add_column(
        "proctor_snapshots",
        sa.Column("edge_model_version", sa.Text(), nullable=True),
        schema="exam_svc",
    )
    op.add_column(
        "proctor_snapshots",
        sa.Column("is_offline_frame", sa.Boolean(), nullable=False, server_default="false"),
        schema="exam_svc",
    )
    op.add_column(
        "proctor_snapshots",
        sa.Column("captured_at", sa.DateTime(timezone=True), nullable=True),
        schema="exam_svc",
    )
    op.add_column(
        "proctor_snapshots",
        sa.Column("integrity_check_passed", sa.Boolean(), nullable=True),
        schema="exam_svc",
    )
    op.add_column(
        "proctor_snapshots",
        sa.Column("integrity_failure_reason", sa.Text(), nullable=True),
        schema="exam_svc",
    )
    op.add_column(
        "proctor_snapshots",
        sa.Column("edge_processed", sa.Boolean(), nullable=False, server_default="false"),
        schema="exam_svc",
    )


def downgrade() -> None:
    for col in [
        "edge_processed",
        "integrity_failure_reason",
        "integrity_check_passed",
        "captured_at",
        "is_offline_frame",
        "edge_model_version",
        "edge_confidence",
        "edge_verdict",
        "frame_sha256",
    ]:
        op.drop_column("proctor_snapshots", col, schema="exam_svc")
