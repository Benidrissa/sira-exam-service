"""Phase 4 — school classes, test assignments, score complaints.

Revision ID: 009
Revises: 008
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import UUID

revision = "009"
down_revision = "008"
branch_labels = None
depends_on = None

_SCHEMA = "exam_svc"


def _create_enum_if_not_exists(name: str, values: list[str]) -> None:
    op.execute(
        f"""
        DO $$ BEGIN
            CREATE TYPE {_SCHEMA}.{name} AS ENUM ({", ".join(repr(v) for v in values)});
        EXCEPTION WHEN duplicate_object THEN NULL;
        END $$;
        """
    )


def upgrade() -> None:
    # --- ENUMs ----------------------------------------------------------------
    _create_enum_if_not_exists("quarter", ["q1", "q2", "q3", "q4"])
    _create_enum_if_not_exists("complaintstatus", ["pending", "approved", "rejected"])

    # --- school_classes -------------------------------------------------------
    op.create_table(
        "school_classes",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("org_id", UUID(as_uuid=True), nullable=False),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("academic_year", sa.Text(), nullable=False),
        sa.Column("created_by", UUID(as_uuid=True), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.UniqueConstraint(
            "org_id", "name", "academic_year", name="uq_school_class_org_name_year"
        ),
        schema=_SCHEMA,
    )
    op.create_index("ix_school_classes_org_id", "school_classes", ["org_id"], schema=_SCHEMA)

    # --- class_members --------------------------------------------------------
    op.create_table(
        "class_members",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "class_id",
            UUID(as_uuid=True),
            sa.ForeignKey(f"{_SCHEMA}.school_classes.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("user_id", UUID(as_uuid=True), nullable=False),
        sa.Column("added_by", UUID(as_uuid=True), nullable=False),
        sa.Column(
            "added_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.UniqueConstraint("class_id", "user_id", name="uq_class_member"),
        schema=_SCHEMA,
    )
    op.create_index("ix_class_members_class_id", "class_members", ["class_id"], schema=_SCHEMA)
    op.create_index("ix_class_members_user_id", "class_members", ["user_id"], schema=_SCHEMA)

    # --- test_assignments -----------------------------------------------------
    # Use Text() for enum columns to avoid SQLAlchemy CREATE TYPE in op.create_table,
    # then ALTER to the proper enum types after table creation.
    op.create_table(
        "test_assignments",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "test_id",
            UUID(as_uuid=True),
            sa.ForeignKey(f"{_SCHEMA}.exam_tests.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "class_id",
            UUID(as_uuid=True),
            sa.ForeignKey(f"{_SCHEMA}.school_classes.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("released_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("closes_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("quarter", sa.Text(), nullable=False),  # cast to enum below
        sa.Column("assigned_by", UUID(as_uuid=True), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.UniqueConstraint("test_id", "class_id", name="uq_assignment_test_class"),
        sa.CheckConstraint("closes_at > released_at", name="ck_assignment_window_valid"),
        schema=_SCHEMA,
    )
    op.execute(
        f"ALTER TABLE {_SCHEMA}.test_assignments "
        f"ALTER COLUMN quarter TYPE {_SCHEMA}.quarter "
        f"USING quarter::{_SCHEMA}.quarter"
    )
    op.create_index("ix_test_assignments_test_id", "test_assignments", ["test_id"], schema=_SCHEMA)
    op.create_index(
        "ix_test_assignments_class_id", "test_assignments", ["class_id"], schema=_SCHEMA
    )

    # --- score_complaints -----------------------------------------------------
    op.create_table(
        "score_complaints",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "attempt_id",
            UUID(as_uuid=True),
            sa.ForeignKey(f"{_SCHEMA}.exam_attempts.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "question_id",
            UUID(as_uuid=True),
            sa.ForeignKey(f"{_SCHEMA}.exam_questions.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("filed_by", UUID(as_uuid=True), nullable=False),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column(
            "status", sa.Text(), nullable=False, server_default="pending"
        ),  # cast to enum below
        sa.Column("reviewed_by", UUID(as_uuid=True), nullable=True),
        sa.Column("review_note", sa.Text(), nullable=True),
        sa.Column("score_override", sa.Float(), nullable=True),
        sa.Column("reviewed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        # Covers question-level uniqueness (NULL != NULL in PG, so this only constrains non-null)
        sa.UniqueConstraint("attempt_id", "question_id", name="uq_complaint_per_question"),
        schema=_SCHEMA,
    )
    op.execute(
        f"ALTER TABLE {_SCHEMA}.score_complaints "
        f"ALTER COLUMN status TYPE {_SCHEMA}.complaintstatus "
        f"USING status::{_SCHEMA}.complaintstatus"
    )
    op.execute(
        f"ALTER TABLE {_SCHEMA}.score_complaints "
        f"ALTER COLUMN status SET DEFAULT 'pending'::{_SCHEMA}.complaintstatus"
    )
    op.create_index(
        "ix_score_complaints_attempt_id", "score_complaints", ["attempt_id"], schema=_SCHEMA
    )
    op.create_index("ix_score_complaints_status", "score_complaints", ["status"], schema=_SCHEMA)
    # Partial unique index: one total-score complaint (question_id IS NULL) per attempt
    op.execute(
        f"CREATE UNIQUE INDEX uq_complaint_total "
        f"ON {_SCHEMA}.score_complaints(attempt_id) WHERE question_id IS NULL"
    )

    # --- validation columns on exam_attempts -----------------------------------
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
    op.execute(f"DROP INDEX IF EXISTS {_SCHEMA}.uq_complaint_total")
    op.drop_table("score_complaints", schema=_SCHEMA)
    op.drop_table("test_assignments", schema=_SCHEMA)
    op.drop_table("class_members", schema=_SCHEMA)
    op.drop_table("school_classes", schema=_SCHEMA)
    op.execute(f"DROP TYPE IF EXISTS {_SCHEMA}.complaintstatus")
    op.execute(f"DROP TYPE IF EXISTS {_SCHEMA}.quarter")
