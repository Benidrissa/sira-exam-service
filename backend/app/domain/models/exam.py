"""Epic 1 + Phase 4 data models — exam generation, review, taking, and class scheduling."""

from __future__ import annotations

import enum
import uuid
from datetime import datetime

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    Enum,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base

# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------


class ExtractionStatus(str, enum.Enum):
    pending = "pending"
    extracting = "extracting"
    done = "done"
    failed = "failed"


class BankStatus(str, enum.Enum):
    draft = "draft"
    generating = "generating"
    review = "review"
    published = "published"
    archived = "archived"


class QuestionType(str, enum.Enum):
    mcq = "mcq"
    dissertation = "dissertation"


class Difficulty(str, enum.Enum):
    easy = "easy"
    medium = "medium"
    hard = "hard"


class TestMode(str, enum.Enum):
    exam = "exam"
    training = "training"
    review = "review"


class TestStatus(str, enum.Enum):
    draft = "draft"
    published = "published"
    archived = "archived"


class DissertationStatus(str, enum.Enum):
    pending = "pending"
    ai_scored = "ai_scored"
    human_reviewed = "human_reviewed"


class Quarter(str, enum.Enum):
    q1 = "q1"
    q2 = "q2"
    q3 = "q3"
    q4 = "q4"


class ComplaintStatus(str, enum.Enum):
    pending = "pending"
    approved = "approved"
    rejected = "rejected"


# ---------------------------------------------------------------------------
# Models
# ---------------------------------------------------------------------------


class ExamSource(Base):
    """Uploaded source document (PDF/Word) for exam generation."""

    __tablename__ = "exam_sources"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    bank_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("exam_banks.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    filename: Mapped[str] = mapped_column(Text, nullable=False)
    storage_key: Mapped[str] = mapped_column(Text, nullable=False)
    raw_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    char_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    extraction_status: Mapped[ExtractionStatus] = mapped_column(
        Enum(ExtractionStatus, name="extractionstatus", create_type=False),
        nullable=False,
        default=ExtractionStatus.pending,
    )
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    bank: Mapped[ExamBank] = relationship("ExamBank", back_populates="sources")


class ExamBank(Base):
    """Top-level exam container (one bank = one exam)."""

    __tablename__ = "exam_banks"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    org_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False, index=True)
    created_by: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False, index=True)
    title_fr: Mapped[str] = mapped_column(Text, nullable=False)
    title_en: Mapped[str | None] = mapped_column(Text, nullable=True)
    subject: Mapped[str | None] = mapped_column(Text, nullable=True)
    language: Mapped[str] = mapped_column(Text, nullable=False, default="fr")
    passing_score: Mapped[float] = mapped_column(Float, nullable=False, default=80.0)
    status: Mapped[BankStatus] = mapped_column(
        Enum(BankStatus, name="bankstatus", create_type=False),
        nullable=False,
        default=BankStatus.draft,
    )
    generation_task_id: Mapped[str | None] = mapped_column(Text, nullable=True)
    generation_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    course_code: Mapped[str | None] = mapped_column(Text, nullable=True)
    course_name: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    sources: Mapped[list[ExamSource]] = relationship(
        "ExamSource", back_populates="bank", cascade="all, delete-orphan"
    )
    scenarios: Mapped[list[ExamScenario]] = relationship(
        "ExamScenario",
        back_populates="bank",
        cascade="all, delete-orphan",
        order_by="ExamScenario.order_index",
    )
    questions: Mapped[list[ExamQuestion]] = relationship(
        "ExamQuestion", back_populates="bank", cascade="all, delete-orphan"
    )
    tests: Mapped[list[ExamTest]] = relationship(
        "ExamTest", back_populates="bank", cascade="all, delete-orphan"
    )


class ExamScenario(Base):
    """One scenario contains multiple questions (case study / reading passage)."""

    __tablename__ = "exam_scenarios"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    bank_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("exam_banks.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    title: Mapped[str] = mapped_column(Text, nullable=False)
    objective: Mapped[str | None] = mapped_column(Text, nullable=True)
    context_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    context_image_storage_key: Mapped[str | None] = mapped_column(Text, nullable=True)
    order_index: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    bank: Mapped[ExamBank] = relationship("ExamBank", back_populates="scenarios")
    questions: Mapped[list[ExamQuestion]] = relationship(
        "ExamQuestion", back_populates="scenario", order_by="ExamQuestion.order_index"
    )


class ExamQuestion(Base):
    """Individual question — MCQ or dissertation."""

    __tablename__ = "exam_questions"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    bank_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("exam_banks.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    scenario_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("exam_scenarios.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    question_type: Mapped[QuestionType] = mapped_column(
        Enum(QuestionType, name="questiontype", create_type=False),
        nullable=False,
        default=QuestionType.mcq,
    )
    title: Mapped[str | None] = mapped_column(Text, nullable=True)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    image_storage_key: Mapped[str | None] = mapped_column(Text, nullable=True)
    image_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    # MCQ fields
    options: Mapped[list | None] = mapped_column(JSONB, nullable=True)  # [{label, text}]
    correct_answer_indices: Mapped[list | None] = mapped_column(JSONB, nullable=True)  # [int]
    explanation: Mapped[str | None] = mapped_column(Text, nullable=True)
    # Dissertation fields
    model_answer: Mapped[str | None] = mapped_column(Text, nullable=True)
    rubric: Mapped[list | None] = mapped_column(
        JSONB, nullable=True
    )  # [{criterion, max_points, description}]
    # Metadata
    difficulty: Mapped[Difficulty] = mapped_column(
        Enum(Difficulty, name="difficulty", create_type=False),
        nullable=False,
        default=Difficulty.medium,
    )
    category: Mapped[str | None] = mapped_column(Text, nullable=True)
    order_index: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    ai_generated: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    validated: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    bank: Mapped[ExamBank] = relationship("ExamBank", back_populates="questions")
    scenario: Mapped[ExamScenario | None] = relationship("ExamScenario", back_populates="questions")


class ExamTest(Base):
    """Test configuration wrapping an ExamBank."""

    __tablename__ = "exam_tests"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    bank_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("exam_banks.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    created_by: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    title: Mapped[str] = mapped_column(Text, nullable=False)
    mode: Mapped[TestMode] = mapped_column(
        Enum(TestMode, name="testmode", create_type=False),
        nullable=False,
        default=TestMode.exam,
    )
    question_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    shuffle_questions: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    time_limit_minutes: Mapped[int | None] = mapped_column(Integer, nullable=True)
    show_feedback: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    mcq_weight: Mapped[float] = mapped_column(Float, nullable=False, default=1.0)
    dissertation_weight: Mapped[float] = mapped_column(Float, nullable=False, default=1.0)
    # FR-4.26: contribution of this exam to the course term grade (relative coefficient).
    exam_weight: Mapped[float] = mapped_column(Float, nullable=False, default=1.0)
    status: Mapped[TestStatus] = mapped_column(
        Enum(TestStatus, name="teststatus", create_type=False),
        nullable=False,
        default=TestStatus.draft,
    )
    anonymous_grading: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    __table_args__ = (
        CheckConstraint(
            "exam_weight >= 0 AND exam_weight <= 100", name="ck_exam_test_weight_range"
        ),
    )

    bank: Mapped[ExamBank] = relationship("ExamBank", back_populates="tests")
    attempts: Mapped[list[ExamAttempt]] = relationship(
        "ExamAttempt", back_populates="test", cascade="all, delete-orphan"
    )
    assignments: Mapped[list[TestAssignment]] = relationship(
        "TestAssignment", back_populates="test", cascade="all, delete-orphan"
    )


class ExamAttempt(Base):
    """A student's attempt at an ExamTest."""

    __tablename__ = "exam_attempts"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    test_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("exam_tests.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False, index=True)
    anon_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), nullable=False, default=uuid.uuid4, index=True
    )
    question_ids: Mapped[list] = mapped_column(JSONB, nullable=False)
    mcq_answers: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    mcq_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    total_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    passed: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    time_taken_sec: Mapped[int | None] = mapped_column(Integer, nullable=True)
    attempted_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    validation_status: Mapped[str] = mapped_column(Text, nullable=False, server_default="pending")
    validated_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    validated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    test: Mapped[ExamTest] = relationship("ExamTest", back_populates="attempts")
    dissertation_answers: Mapped[list[DissertationAnswer]] = relationship(
        "DissertationAnswer", back_populates="attempt", cascade="all, delete-orphan"
    )
    session: Mapped[ExamSession | None] = relationship(  # type: ignore[name-defined]  # noqa: F821
        "ExamSession", back_populates="attempt", uselist=False
    )
    complaints: Mapped[list[ScoreComplaint]] = relationship(
        "ScoreComplaint", back_populates="attempt", cascade="all, delete-orphan"
    )


class DissertationAnswer(Base):
    """Student answer to a dissertation question, with AI + human scoring."""

    __tablename__ = "dissertation_answers"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    attempt_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("exam_attempts.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    question_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("exam_questions.id"), nullable=False, index=True
    )
    answer_text: Mapped[str] = mapped_column(Text, nullable=False)
    ai_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    ai_feedback: Mapped[str | None] = mapped_column(Text, nullable=True)
    criterion_scores: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    ai_scored_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    human_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    human_feedback: Mapped[str | None] = mapped_column(Text, nullable=True)
    human_scored_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    human_scored_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    status: Mapped[DissertationStatus] = mapped_column(
        Enum(DissertationStatus, name="dissertationstatus", create_type=False),
        nullable=False,
        default=DissertationStatus.pending,
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    attempt: Mapped[ExamAttempt] = relationship(
        "ExamAttempt", back_populates="dissertation_answers"
    )
    question: Mapped[ExamQuestion] = relationship("ExamQuestion")


# ---------------------------------------------------------------------------
# Phase 4 models
# ---------------------------------------------------------------------------


class SchoolClass(Base):
    """Named cohort scoped to (org_id, name, academic_year). Tests are assigned to classes."""

    __tablename__ = "school_classes"
    __table_args__ = (
        UniqueConstraint("org_id", "name", "academic_year", name="uq_school_class_org_name_year"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    org_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False, index=True)
    name: Mapped[str] = mapped_column(Text, nullable=False)
    academic_year: Mapped[str] = mapped_column(Text, nullable=False)
    created_by: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    archived_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    members: Mapped[list[ClassMember]] = relationship(
        "ClassMember", back_populates="school_class", cascade="all, delete-orphan"
    )
    assignments: Mapped[list[TestAssignment]] = relationship(
        "TestAssignment", back_populates="school_class", cascade="all, delete-orphan"
    )


class ClassMember(Base):
    """Enrollment record linking a student user_id to a SchoolClass."""

    __tablename__ = "class_members"
    __table_args__ = (UniqueConstraint("class_id", "user_id", name="uq_class_member"),)

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    class_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("school_classes.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False, index=True)
    added_by: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    added_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    school_class: Mapped[SchoolClass] = relationship("SchoolClass", back_populates="members")


class TestAssignment(Base):
    """Scheduled delivery of an ExamTest to a SchoolClass with a time window and quarter."""

    __tablename__ = "test_assignments"
    __table_args__ = (
        UniqueConstraint("test_id", "class_id", name="uq_assignment_test_class"),
        CheckConstraint("closes_at > released_at", name="ck_assignment_window_valid"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    test_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("exam_tests.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    class_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("school_classes.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    released_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    closes_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    quarter: Mapped[Quarter] = mapped_column(
        Enum(Quarter, name="quarter", create_type=False),
        nullable=False,
    )
    assigned_by: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    test: Mapped[ExamTest] = relationship("ExamTest", back_populates="assignments")
    school_class: Mapped[SchoolClass] = relationship("SchoolClass", back_populates="assignments")


class ScoreComplaint(Base):
    """Student-initiated dispute on a question score or total attempt score."""

    __tablename__ = "score_complaints"
    __table_args__ = (
        # Covers question-level uniqueness (NULL != NULL in PG so this only constrains non-null)
        UniqueConstraint("attempt_id", "question_id", name="uq_complaint_per_question"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    attempt_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("exam_attempts.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    question_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("exam_questions.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    filed_by: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    reason: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[ComplaintStatus] = mapped_column(
        Enum(ComplaintStatus, name="complaintstatus", create_type=False),
        nullable=False,
        default=ComplaintStatus.pending,
    )
    reviewed_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    review_note: Mapped[str | None] = mapped_column(Text, nullable=True)
    score_override: Mapped[float | None] = mapped_column(Float, nullable=True)
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    attempt: Mapped[ExamAttempt] = relationship("ExamAttempt", back_populates="complaints")
    question: Mapped[ExamQuestion | None] = relationship("ExamQuestion")


class ExamAccessGrant(Base):
    """Admin grant allowing a student to review an exam bank/test without class enrollment."""

    __tablename__ = "exam_access_grants"
    __table_args__ = (
        CheckConstraint(
            "bank_id IS NOT NULL OR test_id IS NOT NULL",
            name="ck_grant_target",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    bank_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("exam_banks.id", ondelete="CASCADE"),
        nullable=True,
        index=True,
    )
    test_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("exam_tests.id", ondelete="CASCADE"),
        nullable=True,
        index=True,
    )
    student_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False, index=True)
    granted_by: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    org_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False, index=True)
    granted_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class ReviewAuditLog(Base):
    """Immutable log entry for every change to a DissertationAnswer human score."""

    __tablename__ = "review_audit_logs"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    answer_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("dissertation_answers.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    attempt_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False, index=True)
    test_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False, index=True)
    org_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False, index=True)
    actor_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    actor_role: Mapped[str] = mapped_column(Text, nullable=False)
    action: Mapped[str] = mapped_column(Text, nullable=False)
    old_values: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    new_values: Mapped[dict] = mapped_column(JSONB, nullable=False)
    occurred_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class GradeScale(Base):
    """A single letter-grade band in an org's grading scale (FR-4.28).

    A complete scale is the set of rows for one org, ordered by sort_order,
    contiguously covering 0-100. When an org has no rows a built-in default
    scale (F/D/C/B/A) is used instead.
    """

    __tablename__ = "grade_scales"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    org_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False, index=True)
    min_score: Mapped[float] = mapped_column(Float, nullable=False)
    max_score: Mapped[float] = mapped_column(Float, nullable=False)
    letter: Mapped[str] = mapped_column(String(4), nullable=False)
    gpa_points: Mapped[float] = mapped_column(Float, nullable=False)
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False)


class ExamDispensation(Base):
    """A student exemption from sitting a specific test (FR-4.29).

    An active, non-expired dispensation lets the student bypass the open-window
    and class-enrolment gates, and excludes the exam from their weighted term
    average. One dispensation per (test, student).
    """

    __tablename__ = "exam_dispensations"
    __table_args__ = (
        UniqueConstraint("test_id", "student_id", name="uq_dispensation_test_student"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    org_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False, index=True)
    student_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False, index=True)
    test_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("exam_tests.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    class_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("school_classes.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    reason: Mapped[str] = mapped_column(Text, nullable=False)
    granted_by: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    granted_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class TermGrade(Base):
    """A finalised per-course/term grade for a student (FR-4.32).

    Re-finalisation is non-destructive: the previous live row is kept and its
    superseded_by points to the new authoritative row.
    """

    __tablename__ = "term_grades"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    org_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False, index=True)
    student_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False, index=True)
    course_code: Mapped[str] = mapped_column(String(32), nullable=False)
    class_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("school_classes.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    academic_year: Mapped[str] = mapped_column(String(16), nullable=False)
    quarter: Mapped[Quarter] = mapped_column(
        Enum(Quarter, name="quarter", create_type=False), nullable=False
    )
    weighted_avg: Mapped[float | None] = mapped_column(Float, nullable=True)
    grade_letter: Mapped[str | None] = mapped_column(String(4), nullable=True)
    finalized_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    superseded_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("term_grades.id", ondelete="SET NULL"),
        nullable=True,
    )


class User(Base):
    """A login account for the exam service (real password authentication).

    The exam service is otherwise stateless about identity (it trusts JWT
    claims), but this table backs the password-login endpoint. user_id columns
    elsewhere reference this id by value (no FK, to stay compatible with
    externally-issued identities).
    """

    __tablename__ = "users"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    email: Mapped[str] = mapped_column(String(255), nullable=False, unique=True, index=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False, default="")
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    role: Mapped[str] = mapped_column(String(16), nullable=False, default="user")
    org_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False, index=True)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    failed_password_attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    password_locked_until: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
