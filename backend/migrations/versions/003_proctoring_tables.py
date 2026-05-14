"""003 — proctoring tables: exam_sessions, proctor_snapshots, proctor_events, proctor_alerts

Revision ID: 003
Revises: 002
Create Date: 2026-05-14
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "003"
down_revision = "002"
branch_labels = None
depends_on = None


def _create_enum_if_not_exists(name: str, values: list[str]) -> None:
    """Create a PostgreSQL ENUM type — idempotent via EXCEPTION handling."""
    values_sql = ", ".join(f"'{v}'" for v in values)
    op.execute(
        f"""DO $$ BEGIN
            CREATE TYPE {name} AS ENUM ({values_sql});
        EXCEPTION WHEN duplicate_object THEN
            NULL;
        END $$;"""
    )


def upgrade() -> None:
    # --- New ENUM types ---
    _create_enum_if_not_exists(
        "sessionstatus", ["active", "terminated", "expired", "completed"]
    )
    _create_enum_if_not_exists(
        "snapshotanalysis", ["pending", "analyzing", "clean", "flagged", "error"]
    )
    _create_enum_if_not_exists(
        "eventseverity", ["info", "low", "medium", "high", "critical"]
    )

    # --- exam_sessions ---
    op.create_table(
        "exam_sessions",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "attempt_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("exam_attempts.id", ondelete="CASCADE"),
            nullable=False,
            unique=True,
        ),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("org_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("session_token_hash", sa.Text, nullable=False, unique=True),
        sa.Column(
            "status",
            postgresql.ENUM(
                "active", "terminated", "expired", "completed",
                name="sessionstatus", create_type=False,
            ),
            nullable=False,
            server_default="active",
        ),
        sa.Column("lockdown_mode", sa.Boolean, nullable=False, server_default="false"),
        sa.Column("phase", sa.Text, nullable=False, server_default="remote"),
        sa.Column("started_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("ended_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_heartbeat_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "consecutive_missed_heartbeats", sa.Integer, nullable=False, server_default="0"
        ),
        sa.Column("consent_given", sa.Boolean, nullable=False, server_default="false"),
        sa.Column("consent_given_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("reference_frame_key", sa.Text, nullable=True),
        sa.Column("termination_reason", sa.Text, nullable=True),
    )
    op.create_index("ix_exam_sessions_attempt_id", "exam_sessions", ["attempt_id"])
    op.create_index("ix_exam_sessions_user_id", "exam_sessions", ["user_id"])
    op.create_index("ix_exam_sessions_org_id", "exam_sessions", ["org_id"])

    # --- proctor_snapshots ---
    op.create_table(
        "proctor_snapshots",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "session_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("exam_sessions.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("storage_key", sa.Text, nullable=False),
        sa.Column("taken_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column(
            "analysis_status",
            postgresql.ENUM(
                "pending", "analyzing", "clean", "flagged", "error",
                name="snapshotanalysis", create_type=False,
            ),
            nullable=False,
            server_default="pending",
        ),
        sa.Column("analysis_result", postgresql.JSONB, nullable=True),
        sa.Column("violation_detected", sa.Boolean, nullable=True),
        sa.Column("violation_type", sa.Text, nullable=True),
        sa.Column("confidence", sa.Float, nullable=True),
    )
    op.create_index("ix_proctor_snapshots_session_id", "proctor_snapshots", ["session_id"])

    # --- proctor_events ---
    op.create_table(
        "proctor_events",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "session_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("exam_sessions.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("event_type", sa.Text, nullable=False),
        sa.Column(
            "severity",
            postgresql.ENUM(
                "info", "low", "medium", "high", "critical",
                name="eventseverity", create_type=False,
            ),
            nullable=False,
            server_default="info",
        ),
        sa.Column("payload", postgresql.JSONB, nullable=True),
        sa.Column("occurred_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("ix_proctor_events_session_id", "proctor_events", ["session_id"])

    # --- proctor_alerts ---
    op.create_table(
        "proctor_alerts",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "session_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("exam_sessions.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "event_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("proctor_events.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "severity",
            postgresql.ENUM(
                "info", "low", "medium", "high", "critical",
                name="eventseverity", create_type=False,
            ),
            nullable=False,
            server_default="info",
        ),
        sa.Column("message", sa.Text, nullable=False),
        sa.Column("acknowledged", sa.Boolean, nullable=False, server_default="false"),
        sa.Column("acknowledged_by", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("acknowledged_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index(
        "ix_proctor_alerts_session_id_acknowledged",
        "proctor_alerts",
        ["session_id", "acknowledged"],
    )


def downgrade() -> None:
    op.drop_table("proctor_alerts")
    op.drop_table("proctor_events")
    op.drop_table("proctor_snapshots")
    op.drop_table("exam_sessions")

    for name in ("eventseverity", "snapshotanalysis", "sessionstatus"):
        op.execute(f"DROP TYPE IF EXISTS {name}")
