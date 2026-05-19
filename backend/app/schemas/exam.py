"""Pydantic request/response schemas for the exam service."""

from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.domain.models.exam import (
    BankStatus,
    Difficulty,
    DissertationStatus,
    ExtractionStatus,
    Quarter,
    QuestionType,
    TestMode,
    TestStatus,
)

# ---------------------------------------------------------------------------
# ExamBank
# ---------------------------------------------------------------------------


class ExamBankCreate(BaseModel):
    title_fr: str = Field(..., min_length=1, max_length=500)
    title_en: str | None = None
    subject: str | None = None
    language: str = "fr"
    passing_score: float = Field(80.0, ge=0.0, le=100.0)


class ExamBankUpdate(BaseModel):
    title_fr: str | None = Field(None, min_length=1, max_length=500)
    title_en: str | None = None
    subject: str | None = None
    language: str | None = None
    passing_score: float | None = Field(None, ge=0.0, le=100.0)
    status: BankStatus | None = None


class ExamBankResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    org_id: uuid.UUID
    created_by: uuid.UUID
    title_fr: str
    title_en: str | None
    subject: str | None
    language: str
    passing_score: float
    status: BankStatus
    generation_task_id: str | None
    generation_error: str | None
    created_at: datetime
    updated_at: datetime


# ---------------------------------------------------------------------------
# ExamSource
# ---------------------------------------------------------------------------


class ExamSourceResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    bank_id: uuid.UUID
    filename: str
    storage_key: str
    raw_text: str | None
    char_count: int | None
    extraction_status: ExtractionStatus
    error_message: str | None
    created_at: datetime


# ---------------------------------------------------------------------------
# ExamScenario
# ---------------------------------------------------------------------------


class ExamScenarioCreate(BaseModel):
    title: str = Field(..., min_length=1, max_length=500)
    objective: str | None = None
    context_text: str | None = None
    order_index: int = Field(0, ge=0)


class ExamScenarioUpdate(BaseModel):
    title: str | None = Field(None, min_length=1, max_length=500)
    objective: str | None = None
    context_text: str | None = None
    order_index: int | None = Field(None, ge=0)


class ExamScenarioResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    bank_id: uuid.UUID
    title: str
    objective: str | None
    context_text: str | None
    context_image_storage_key: str | None
    order_index: int
    created_at: datetime
    updated_at: datetime


# ---------------------------------------------------------------------------
# ExamQuestion
# ---------------------------------------------------------------------------


class ExamQuestionCreate(BaseModel):
    scenario_id: uuid.UUID | None = None
    question_type: QuestionType = QuestionType.mcq
    title: str | None = None
    description: str = Field(..., min_length=1)
    options: list[dict] | None = None
    correct_answer_indices: list[int] | None = None
    explanation: str | None = None
    model_answer: str | None = None
    rubric: list[dict] | None = None
    difficulty: Difficulty = Difficulty.medium
    category: str | None = None
    order_index: int = Field(0, ge=0)
    ai_generated: bool = False


class ExamQuestionUpdate(BaseModel):
    scenario_id: uuid.UUID | None = None
    question_type: QuestionType | None = None
    title: str | None = None
    description: str | None = Field(None, min_length=1)
    options: list[dict] | None = None
    correct_answer_indices: list[int] | None = None
    explanation: str | None = None
    model_answer: str | None = None
    rubric: list[dict] | None = None
    difficulty: Difficulty | None = None
    category: str | None = None
    order_index: int | None = Field(None, ge=0)
    validated: bool | None = None


class ExamQuestionResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    bank_id: uuid.UUID
    scenario_id: uuid.UUID | None
    question_type: QuestionType
    title: str | None
    description: str
    image_storage_key: str | None
    image_url: str | None
    options: list | None
    correct_answer_indices: list | None
    explanation: str | None
    model_answer: str | None
    rubric: list | None
    difficulty: Difficulty
    category: str | None
    order_index: int
    ai_generated: bool
    validated: bool
    created_at: datetime
    updated_at: datetime


# ---------------------------------------------------------------------------
# ExamTest
# ---------------------------------------------------------------------------


class ExamTestCreate(BaseModel):
    title: str = Field(..., min_length=1, max_length=500)
    mode: TestMode = TestMode.exam
    question_count: int | None = Field(None, ge=1)
    shuffle_questions: bool = True
    time_limit_minutes: int | None = Field(None, ge=1)
    show_feedback: bool = False
    mcq_weight: float = Field(1.0, ge=0.0)
    dissertation_weight: float = Field(1.0, ge=0.0)


class ExamTestUpdate(BaseModel):
    title: str | None = Field(None, min_length=1, max_length=500)
    mode: TestMode | None = None
    question_count: int | None = Field(None, ge=1)
    shuffle_questions: bool | None = None
    time_limit_minutes: int | None = Field(None, ge=1)
    show_feedback: bool | None = None
    mcq_weight: float | None = Field(None, ge=0.0)
    dissertation_weight: float | None = Field(None, ge=0.0)
    status: TestStatus | None = None


class ExamTestResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    bank_id: uuid.UUID
    created_by: uuid.UUID
    title: str
    mode: TestMode
    question_count: int | None
    shuffle_questions: bool
    time_limit_minutes: int | None
    show_feedback: bool
    mcq_weight: float
    dissertation_weight: float
    status: TestStatus
    created_at: datetime
    updated_at: datetime


# ---------------------------------------------------------------------------
# ExamAttempt
# ---------------------------------------------------------------------------


class ExamAttemptResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    test_id: uuid.UUID
    user_id: uuid.UUID
    question_ids: list
    mcq_answers: dict | None
    mcq_score: float | None
    total_score: float | None
    passed: bool | None
    time_taken_sec: int | None
    attempted_at: datetime


# ---------------------------------------------------------------------------
# Bulk question create + validation (E1-5, E1-6)
# ---------------------------------------------------------------------------


class ExamQuestionBulkCreate(BaseModel):
    questions: list[ExamQuestionCreate] = Field(..., min_length=1, max_length=500)


class BulkValidationResponse(BaseModel):
    bank_id: uuid.UUID
    validated_count: int
    bank_status: BankStatus


# ---------------------------------------------------------------------------
# Attempt start/submit (E1-7)
# ---------------------------------------------------------------------------


class SubmitAttemptRequest(BaseModel):
    mcq_answers: dict[str, list[int]] = Field(default_factory=dict)
    dissertation_answers: dict[str, str] = Field(default_factory=dict)
    time_taken_sec: int | None = Field(None, ge=1)


class StartAttemptResponse(BaseModel):
    """ExamAttempt + pre-loaded questions so the player needs only one API call."""

    attempt_id: uuid.UUID
    test_id: uuid.UUID
    user_id: uuid.UUID
    bank_id: uuid.UUID
    question_ids: list
    time_limit_minutes: int | None
    questions: list[ExamQuestionResponse]


# ---------------------------------------------------------------------------
# Human scoring (E1-9)
# ---------------------------------------------------------------------------


class HumanScoreUpdate(BaseModel):
    human_score: float = Field(..., ge=0.0)
    human_feedback: str = Field(..., min_length=1, max_length=5000)


# ---------------------------------------------------------------------------
# DissertationAnswer
# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
# Generation (E1-3, E1-4)
# ---------------------------------------------------------------------------


class ScenarioBrief(BaseModel):
    title: str = Field(..., min_length=1, max_length=300)
    objective: str | None = Field(None, max_length=1000)
    question_count: int = Field(3, ge=1, le=20)


class GenerateBriefRequest(BaseModel):
    test_objective: str = Field(..., min_length=1, max_length=1000)
    scenarios_brief: list[ScenarioBrief] = Field(..., min_length=1, max_length=10)


class GenerationStatusResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    bank_id: uuid.UUID
    task_id: str | None
    status: BankStatus
    task_state: str | None
    progress_pct: int | None
    scenario_count: int | None
    error_message: str | None
    created_at: datetime
    updated_at: datetime


class RegenerateRequest(BaseModel):
    test_objective: str | None = Field(None, min_length=1, max_length=1000)


# ---------------------------------------------------------------------------
# DissertationAnswer
# ---------------------------------------------------------------------------


class DissertationAnswerResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    attempt_id: uuid.UUID
    question_id: uuid.UUID
    answer_text: str
    ai_score: float | None
    ai_feedback: str | None
    criterion_scores: dict | None
    ai_scored_at: datetime | None
    human_score: float | None
    human_feedback: str | None
    human_scored_by: uuid.UUID | None
    human_scored_at: datetime | None
    status: DissertationStatus
    created_at: datetime


# ---------------------------------------------------------------------------
# Phase 4 — Class Management + Scheduling
# ---------------------------------------------------------------------------


class SchoolClassCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=200)
    academic_year: str = Field(..., pattern=r"^\d{4}-\d{4}$")


class SchoolClassUpdate(BaseModel):
    name: str | None = Field(None, min_length=1, max_length=200)
    academic_year: str | None = Field(None, pattern=r"^\d{4}-\d{4}$")


class SchoolClassResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    org_id: uuid.UUID
    name: str
    academic_year: str
    created_by: uuid.UUID
    created_at: datetime


class ClassMemberCreate(BaseModel):
    user_id: uuid.UUID


class ClassMemberResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    class_id: uuid.UUID
    user_id: uuid.UUID
    added_by: uuid.UUID
    added_at: datetime


class SchoolClassDetailResponse(SchoolClassResponse):
    members: list[ClassMemberResponse] = []


class TestAssignmentCreate(BaseModel):
    class_id: uuid.UUID
    released_at: datetime
    closes_at: datetime
    quarter: Quarter

    @model_validator(mode="after")
    def validate_window(self) -> "TestAssignmentCreate":
        if self.closes_at <= self.released_at:
            raise ValueError("closes_at must be after released_at")
        return self


class TestAssignmentUpdate(BaseModel):
    released_at: datetime | None = None
    closes_at: datetime | None = None
    quarter: Quarter | None = None


class TestAssignmentResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    test_id: uuid.UUID
    class_id: uuid.UUID
    released_at: datetime
    closes_at: datetime
    quarter: Quarter
    assigned_by: uuid.UUID
    created_at: datetime


class StudentTestSummary(BaseModel):
    test_id: uuid.UUID
    test_title: str
    bank_subject: str | None
    released_at: datetime
    closes_at: datetime
    quarter: Quarter
    class_name: str
    academic_year: str
    has_attempted: bool
    attempt_id: uuid.UUID | None
