"""Initial Epic 1 tables — exam generation and taking.

Revision ID: 001
Revises:
Create Date: 2026-05-14
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    # --- Enums ---
    extractionstatus = postgresql.ENUM(
        "pending",
        "extracting",
        "done",
        "failed",
        name="extractionstatus",
        create_type=True,
    )
    bankstatus = postgresql.ENUM(
        "draft",
        "generating",
        "review",
        "published",
        "archived",
        name="bankstatus",
        create_type=True,
    )
    questiontype = postgresql.ENUM(
        "mcq",
        "dissertation",
        name="questiontype",
        create_type=True,
    )
    difficulty = postgresql.ENUM(
        "easy",
        "medium",
        "hard",
        name="difficulty",
        create_type=True,
    )
    testmode = postgresql.ENUM(
        "exam",
        "training",
        "review",
        name="testmode",
        create_type=True,
    )
    teststatus = postgresql.ENUM(
        "draft",
        "published",
        "archived",
        name="teststatus",
        create_type=True,
    )
    dissertationstatus = postgresql.ENUM(
        "pending",
        "ai_scored",
        "human_reviewed",
        name="dissertationstatus",
        create_type=True,
    )

    for enum in (
        extractionstatus,
        bankstatus,
        questiontype,
        difficulty,
        testmode,
        teststatus,
        dissertationstatus,
    ):
        enum.create(op.get_bind(), checkfirst=True)

    # --- exam_banks ---
    op.create_table(
        "exam_banks",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("org_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("created_by", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("title_fr", sa.Text, nullable=False),
        sa.Column("title_en", sa.Text, nullable=True),
        sa.Column("subject", sa.Text, nullable=True),
        sa.Column("language", sa.Text, nullable=False, server_default="fr"),
        sa.Column("passing_score", sa.Float, nullable=False, server_default="80.0"),
        sa.Column(
            "status",
            sa.Enum(
                "draft",
                "generating",
                "review",
                "published",
                "archived",
                name="bankstatus",
                create_type=False,
            ),
            nullable=False,
            server_default="draft",
        ),
        sa.Column("generation_task_id", sa.Text, nullable=True),
        sa.Column("generation_error", sa.Text, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("ix_exam_banks_org_id", "exam_banks", ["org_id"])
    op.create_index("ix_exam_banks_created_by", "exam_banks", ["created_by"])

    # --- exam_sources ---
    op.create_table(
        "exam_sources",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "bank_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("exam_banks.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("filename", sa.Text, nullable=False),
        sa.Column("storage_key", sa.Text, nullable=False),
        sa.Column("raw_text", sa.Text, nullable=True),
        sa.Column("char_count", sa.Integer, nullable=True),
        sa.Column(
            "extraction_status",
            sa.Enum(
                "pending",
                "extracting",
                "done",
                "failed",
                name="extractionstatus",
                create_type=False,
            ),
            nullable=False,
            server_default="pending",
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("ix_exam_sources_bank_id", "exam_sources", ["bank_id"])

    # --- exam_scenarios ---
    op.create_table(
        "exam_scenarios",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "bank_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("exam_banks.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("title", sa.Text, nullable=False),
        sa.Column("objective", sa.Text, nullable=True),
        sa.Column("context_text", sa.Text, nullable=True),
        sa.Column("context_image_storage_key", sa.Text, nullable=True),
        sa.Column("order_index", sa.Integer, nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("ix_exam_scenarios_bank_id", "exam_scenarios", ["bank_id"])

    # --- exam_questions ---
    op.create_table(
        "exam_questions",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "bank_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("exam_banks.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "scenario_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("exam_scenarios.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "question_type",
            sa.Enum("mcq", "dissertation", name="questiontype", create_type=False),
            nullable=False,
            server_default="mcq",
        ),
        sa.Column("title", sa.Text, nullable=True),
        sa.Column("description", sa.Text, nullable=False),
        sa.Column("image_storage_key", sa.Text, nullable=True),
        sa.Column("image_url", sa.Text, nullable=True),
        sa.Column("options", postgresql.JSONB, nullable=True),
        sa.Column("correct_answer_indices", postgresql.JSONB, nullable=True),
        sa.Column("explanation", sa.Text, nullable=True),
        sa.Column("model_answer", sa.Text, nullable=True),
        sa.Column("rubric", postgresql.JSONB, nullable=True),
        sa.Column(
            "difficulty",
            sa.Enum("easy", "medium", "hard", name="difficulty", create_type=False),
            nullable=False,
            server_default="medium",
        ),
        sa.Column("category", sa.Text, nullable=True),
        sa.Column("order_index", sa.Integer, nullable=False, server_default="0"),
        sa.Column("ai_generated", sa.Boolean, nullable=False, server_default="false"),
        sa.Column("validated", sa.Boolean, nullable=False, server_default="false"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("ix_exam_questions_bank_id", "exam_questions", ["bank_id"])
    op.create_index("ix_exam_questions_scenario_id", "exam_questions", ["scenario_id"])

    # --- exam_tests ---
    op.create_table(
        "exam_tests",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "bank_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("exam_banks.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("created_by", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("title", sa.Text, nullable=False),
        sa.Column(
            "mode",
            sa.Enum("exam", "training", "review", name="testmode", create_type=False),
            nullable=False,
            server_default="exam",
        ),
        sa.Column("question_count", sa.Integer, nullable=True),
        sa.Column("shuffle_questions", sa.Boolean, nullable=False, server_default="true"),
        sa.Column("time_limit_minutes", sa.Integer, nullable=True),
        sa.Column("show_feedback", sa.Boolean, nullable=False, server_default="false"),
        sa.Column("mcq_weight", sa.Float, nullable=False, server_default="1.0"),
        sa.Column("dissertation_weight", sa.Float, nullable=False, server_default="1.0"),
        sa.Column(
            "status",
            sa.Enum("draft", "published", "archived", name="teststatus", create_type=False),
            nullable=False,
            server_default="draft",
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("ix_exam_tests_bank_id", "exam_tests", ["bank_id"])

    # --- exam_attempts ---
    op.create_table(
        "exam_attempts",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "test_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("exam_tests.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("question_ids", postgresql.JSONB, nullable=False),
        sa.Column("mcq_answers", postgresql.JSONB, nullable=True),
        sa.Column("mcq_score", sa.Float, nullable=True),
        sa.Column("total_score", sa.Float, nullable=True),
        sa.Column("passed", sa.Boolean, nullable=True),
        sa.Column("time_taken_sec", sa.Integer, nullable=True),
        sa.Column("attempted_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("ix_exam_attempts_test_id", "exam_attempts", ["test_id"])
    op.create_index("ix_exam_attempts_user_id", "exam_attempts", ["user_id"])

    # --- dissertation_answers ---
    op.create_table(
        "dissertation_answers",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "attempt_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("exam_attempts.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "question_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("exam_questions.id"),
            nullable=False,
        ),
        sa.Column("answer_text", sa.Text, nullable=False),
        sa.Column("ai_score", sa.Float, nullable=True),
        sa.Column("ai_feedback", sa.Text, nullable=True),
        sa.Column("ai_scored_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("human_score", sa.Float, nullable=True),
        sa.Column("human_feedback", sa.Text, nullable=True),
        sa.Column("human_scored_by", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("human_scored_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "status",
            sa.Enum(
                "pending",
                "ai_scored",
                "human_reviewed",
                name="dissertationstatus",
                create_type=False,
            ),
            nullable=False,
            server_default="pending",
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("ix_dissertation_answers_attempt_id", "dissertation_answers", ["attempt_id"])
    op.create_index("ix_dissertation_answers_question_id", "dissertation_answers", ["question_id"])


def downgrade() -> None:
    op.drop_table("dissertation_answers")
    op.drop_table("exam_attempts")
    op.drop_table("exam_tests")
    op.drop_table("exam_questions")
    op.drop_table("exam_scenarios")
    op.drop_table("exam_sources")
    op.drop_table("exam_banks")

    for name in (
        "dissertationstatus",
        "teststatus",
        "testmode",
        "difficulty",
        "questiontype",
        "bankstatus",
        "extractionstatus",
    ):
        op.execute(f"DROP TYPE IF EXISTS {name}")
