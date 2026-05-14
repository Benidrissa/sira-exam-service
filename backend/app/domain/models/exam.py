"""Epic 1 data models — exam generation, review, and taking."""

from __future__ import annotations

import enum
import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, Enum, Float, ForeignKey, Integer, Text, func
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
    status: Mapped[TestStatus] = mapped_column(
        Enum(TestStatus, name="teststatus", create_type=False),
        nullable=False,
        default=TestStatus.draft,
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    bank: Mapped[ExamBank] = relationship("ExamBank", back_populates="tests")
    attempts: Mapped[list[ExamAttempt]] = relationship(
        "ExamAttempt", back_populates="test", cascade="all, delete-orphan"
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
    question_ids: Mapped[list] = mapped_column(JSONB, nullable=False)
    mcq_answers: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    mcq_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    total_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    passed: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    time_taken_sec: Mapped[int | None] = mapped_column(Integer, nullable=True)
    attempted_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    test: Mapped[ExamTest] = relationship("ExamTest", back_populates="attempts")
    dissertation_answers: Mapped[list[DissertationAnswer]] = relationship(
        "DissertationAnswer", back_populates="attempt", cascade="all, delete-orphan"
    )
    session: Mapped[ExamSession | None] = relationship(  # type: ignore[name-defined]  # noqa: F821
        "ExamSession", back_populates="attempt", uselist=False
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
