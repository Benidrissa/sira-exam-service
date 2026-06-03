"""Add exam_weight to exam_tests (FR-4.26).

Each exam contributes a weighted coefficient to its course term grade.

Revision ID: 013
Revises: 012
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "013"
down_revision = "012"
branch_labels = None
depends_on = None

_SCHEMA = "exam_svc"


def upgrade() -> None:
    op.add_column(
        "exam_tests",
        sa.Column(
            "exam_weight",
            sa.Float(),
            nullable=False,
            server_default=sa.text("1.0"),
        ),
        schema=_SCHEMA,
    )
    op.create_check_constraint(
        "ck_exam_test_weight_range",
        "exam_tests",
        "exam_weight >= 0 AND exam_weight <= 100",
        schema=_SCHEMA,
    )


def downgrade() -> None:
    op.drop_constraint("ck_exam_test_weight_range", "exam_tests", type_="check", schema=_SCHEMA)
    op.drop_column("exam_tests", "exam_weight", schema=_SCHEMA)
