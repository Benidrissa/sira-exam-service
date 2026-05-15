"""Exam API — generation, review, CRUD, taking. (E1-1 through E1-9)"""

from __future__ import annotations

import uuid

from celery.result import AsyncResult
from fastapi import APIRouter, File, HTTPException, UploadFile, status

from app.api.deps import DB, CurrentUser, TeacherUser
from app.domain.models.exam import BankStatus
from app.domain.services import (
    exam_answer_service,
    exam_attempt_service,
    exam_bank_service,
    exam_question_service,
    exam_scenario_service,
    exam_source_service,
)
from app.infrastructure.storage import get_exam_storage
from app.schemas.exam import (
    BulkValidationResponse,
    DissertationAnswerResponse,
    ExamAttemptResponse,
    ExamBankCreate,
    ExamBankResponse,
    ExamBankUpdate,
    ExamQuestionBulkCreate,
    ExamQuestionCreate,
    ExamQuestionResponse,
    ExamQuestionUpdate,
    ExamScenarioCreate,
    ExamScenarioResponse,
    ExamScenarioUpdate,
    ExamSourceResponse,
    ExamTestCreate,
    ExamTestResponse,
    ExamTestUpdate,
    GenerateBriefRequest,
    GenerationStatusResponse,
    HumanScoreUpdate,
    RegenerateRequest,
    StartAttemptResponse,
    SubmitAttemptRequest,
)
from app.tasks.celery_app import celery_app

router = APIRouter(prefix="/exam", tags=["exam"])


@router.get("/health")
async def health() -> dict:
    return {"status": "ok", "service": "sira-exam"}


# ---------------------------------------------------------------------------
# E1-1: ExamBank CRUD
# ---------------------------------------------------------------------------


@router.post("/banks", response_model=ExamBankResponse, status_code=status.HTTP_201_CREATED)
async def create_exam_bank(
    data: ExamBankCreate,
    db: DB,
    user: TeacherUser,
) -> ExamBankResponse:
    org_id = uuid.UUID(user.org_id) if user.org_id else uuid.UUID(int=0)
    bank = await exam_bank_service.create_bank(
        db,
        org_id=org_id,
        created_by=uuid.UUID(user.user_id),
        data=data,
    )
    return ExamBankResponse.model_validate(bank)


@router.get("/banks", response_model=list[ExamBankResponse])
async def list_exam_banks(
    db: DB,
    user: TeacherUser,
    bank_status: BankStatus | None = None,
) -> list[ExamBankResponse]:
    org_id = uuid.UUID(user.org_id) if user.org_id else uuid.UUID(int=0)
    banks = await exam_bank_service.list_banks(db, org_id=org_id, status_filter=bank_status)
    return [ExamBankResponse.model_validate(b) for b in banks]


@router.get("/banks/{bank_id}", response_model=ExamBankResponse)
async def get_exam_bank(
    bank_id: uuid.UUID,
    db: DB,
    user: TeacherUser,
) -> ExamBankResponse:
    org_id = uuid.UUID(user.org_id) if user.org_id else uuid.UUID(int=0)
    bank = await exam_bank_service.get_bank(db, bank_id=bank_id, org_id=org_id)
    return ExamBankResponse.model_validate(bank)


@router.patch("/banks/{bank_id}", response_model=ExamBankResponse)
async def update_exam_bank(
    bank_id: uuid.UUID,
    data: ExamBankUpdate,
    db: DB,
    user: TeacherUser,
) -> ExamBankResponse:
    org_id = uuid.UUID(user.org_id) if user.org_id else uuid.UUID(int=0)
    bank = await exam_bank_service.update_bank(db, bank_id=bank_id, org_id=org_id, data=data)
    return ExamBankResponse.model_validate(bank)


@router.delete("/banks/{bank_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_exam_bank(
    bank_id: uuid.UUID,
    db: DB,
    user: TeacherUser,
) -> None:
    org_id = uuid.UUID(user.org_id) if user.org_id else uuid.UUID(int=0)
    await exam_bank_service.delete_bank(db, bank_id=bank_id, org_id=org_id)


# ---------------------------------------------------------------------------
# E1-1 (FR-1.0): ExamSource — PDF upload + extraction
# ---------------------------------------------------------------------------


@router.post(
    "/banks/{bank_id}/sources",
    response_model=ExamSourceResponse,
    status_code=status.HTTP_201_CREATED,
)
async def upload_exam_source(
    bank_id: uuid.UUID,
    db: DB,
    user: TeacherUser,
    file: UploadFile = File(...),
) -> ExamSourceResponse:
    """Upload a source document (PDF/Word) to an exam bank.

    The file is stored in MinIO and an async extraction task is enqueued.
    Poll the returned source's `extraction_status` until `done`.
    """
    org_id = uuid.UUID(user.org_id) if user.org_id else uuid.UUID(int=0)
    file_bytes = await file.read()
    source = await exam_source_service.upload_source(
        db,
        bank_id=bank_id,
        org_id=org_id,
        filename=file.filename or "document",
        content_type=file.content_type or "application/octet-stream",
        file_bytes=file_bytes,
        storage=get_exam_storage(),
    )
    return ExamSourceResponse.model_validate(source)


@router.get("/banks/{bank_id}/sources", response_model=list[ExamSourceResponse])
async def list_exam_sources(
    bank_id: uuid.UUID,
    db: DB,
    user: TeacherUser,
) -> list[ExamSourceResponse]:
    org_id = uuid.UUID(user.org_id) if user.org_id else uuid.UUID(int=0)
    sources = await exam_source_service.list_sources(db, bank_id=bank_id, org_id=org_id)
    return [ExamSourceResponse.model_validate(s) for s in sources]


@router.get("/banks/{bank_id}/sources/{source_id}", response_model=ExamSourceResponse)
async def get_exam_source(
    bank_id: uuid.UUID,
    source_id: uuid.UUID,
    db: DB,
    user: TeacherUser,
) -> ExamSourceResponse:
    org_id = uuid.UUID(user.org_id) if user.org_id else uuid.UUID(int=0)
    source = await exam_source_service.get_source(
        db, source_id=source_id, bank_id=bank_id, org_id=org_id
    )
    return ExamSourceResponse.model_validate(source)


# ---------------------------------------------------------------------------
# E1-3 (FR-1.3): Generation brief endpoint
# ---------------------------------------------------------------------------


def _generation_status_response(
    bank, task_state: str | None, progress_pct: int | None
) -> GenerationStatusResponse:  # noqa: E501
    return GenerationStatusResponse(
        bank_id=bank.id,
        task_id=bank.generation_task_id,
        status=bank.status,
        task_state=task_state,
        progress_pct=progress_pct,
        scenario_count=None,
        error_message=bank.generation_error,
        created_at=bank.created_at,
        updated_at=bank.updated_at,
    )


@router.post(
    "/banks/{bank_id}/generate",
    response_model=GenerationStatusResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
async def generate_exam(
    bank_id: uuid.UUID,
    data: GenerateBriefRequest,
    db: DB,
    user: TeacherUser,
) -> GenerationStatusResponse:
    """Enqueue AI exam generation (FR-1.3). Returns 202 with task_id."""

    from app.tasks.generation import generate_exam_task

    org_id = uuid.UUID(user.org_id) if user.org_id else uuid.UUID(int=0)
    bank = await exam_bank_service.get_bank(db, bank_id=bank_id, org_id=org_id)

    if bank.status == BankStatus.generating:
        return _generation_status_response(bank, "PENDING", 10)

    task = generate_exam_task.delay(
        bank_id=str(bank_id),
        test_objective=data.test_objective,
        scenarios_brief=[sb.model_dump() for sb in data.scenarios_brief],
    )
    bank.generation_task_id = task.id
    bank.status = BankStatus.generating
    bank.generation_error = None
    await db.commit()
    await db.refresh(bank)
    return _generation_status_response(bank, "PENDING", 0)


# ---------------------------------------------------------------------------
# E1-4 (FR-1.4): Generation status polling + per-scenario regeneration
# ---------------------------------------------------------------------------


@router.get("/banks/{bank_id}/generation/status", response_model=GenerationStatusResponse)
async def get_generation_status(
    bank_id: uuid.UUID,
    db: DB,
    user: TeacherUser,
) -> GenerationStatusResponse:
    """Poll Celery task state for exam generation (FR-1.4)."""
    org_id = uuid.UUID(user.org_id) if user.org_id else uuid.UUID(int=0)
    bank = await exam_bank_service.get_bank(db, bank_id=bank_id, org_id=org_id)

    task_state: str | None = None
    progress_pct: int | None = None

    if bank.generation_task_id:
        result = AsyncResult(bank.generation_task_id, app=celery_app)
        task_state = result.state
        if result.state == "SUCCESS":
            progress_pct = 100
        elif result.state == "FAILURE":
            progress_pct = 0
            if not bank.generation_error:
                bank.generation_error = str(result.info)[:500]
                await db.commit()
        elif result.state in ("STARTED", "RETRY"):
            progress_pct = 50
        else:
            progress_pct = 10

    return _generation_status_response(bank, task_state, progress_pct)


@router.post(
    "/banks/{bank_id}/scenarios/{scenario_id}/regenerate",
    response_model=GenerationStatusResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
async def regenerate_scenario(
    bank_id: uuid.UUID,
    scenario_id: uuid.UUID,
    data: RegenerateRequest,
    db: DB,
    user: TeacherUser,
) -> GenerationStatusResponse:
    """Re-generate questions for a single scenario (FR-1.4.3)."""
    from app.tasks.generation import regenerate_scenario_task

    org_id = uuid.UUID(user.org_id) if user.org_id else uuid.UUID(int=0)
    bank = await exam_bank_service.get_bank(db, bank_id=bank_id, org_id=org_id)

    objective = data.test_objective or bank.title_fr
    task = regenerate_scenario_task.delay(
        bank_id=str(bank_id),
        scenario_id=str(scenario_id),
        test_objective=objective,
    )
    bank.generation_task_id = task.id
    bank.status = BankStatus.generating
    bank.generation_error = None
    await db.commit()
    await db.refresh(bank)
    return _generation_status_response(bank, "PENDING", 0)


# ---------------------------------------------------------------------------
# E1-5 (FR-1.5): Scenario CRUD
# ---------------------------------------------------------------------------


def _org(user: TeacherUser) -> uuid.UUID:
    return uuid.UUID(user.org_id) if user.org_id else uuid.UUID(int=0)


def _uid(user: TeacherUser) -> uuid.UUID:
    return uuid.UUID(user.user_id)


def _is_admin(user: TeacherUser) -> bool:
    return bool(user.is_admin)


@router.post(
    "/banks/{bank_id}/scenarios",
    response_model=ExamScenarioResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_scenario(
    bank_id: uuid.UUID,
    data: ExamScenarioCreate,
    db: DB,
    user: TeacherUser,
) -> ExamScenarioResponse:
    scenario = await exam_scenario_service.create_scenario(
        db, bank_id=bank_id, org_id=_org(user), created_by=_uid(user), data=data
    )
    return ExamScenarioResponse.model_validate(scenario)


@router.get("/banks/{bank_id}/scenarios", response_model=list[ExamScenarioResponse])
async def list_scenarios(
    bank_id: uuid.UUID, db: DB, user: TeacherUser
) -> list[ExamScenarioResponse]:
    scenarios = await exam_scenario_service.list_scenarios(db, bank_id=bank_id, org_id=_org(user))
    return [ExamScenarioResponse.model_validate(s) for s in scenarios]


@router.get("/banks/{bank_id}/scenarios/{scenario_id}", response_model=ExamScenarioResponse)
async def get_scenario(
    bank_id: uuid.UUID, scenario_id: uuid.UUID, db: DB, user: TeacherUser
) -> ExamScenarioResponse:
    scenario = await exam_scenario_service.get_scenario(
        db, scenario_id=scenario_id, bank_id=bank_id, org_id=_org(user)
    )
    return ExamScenarioResponse.model_validate(scenario)


@router.patch("/banks/{bank_id}/scenarios/{scenario_id}", response_model=ExamScenarioResponse)
async def update_scenario(
    bank_id: uuid.UUID,
    scenario_id: uuid.UUID,
    data: ExamScenarioUpdate,
    db: DB,
    user: TeacherUser,
) -> ExamScenarioResponse:
    scenario = await exam_scenario_service.update_scenario(
        db,
        scenario_id=scenario_id,
        bank_id=bank_id,
        org_id=_org(user),
        created_by=_uid(user),
        is_admin=_is_admin(user),
        data=data,
    )
    return ExamScenarioResponse.model_validate(scenario)


@router.delete("/banks/{bank_id}/scenarios/{scenario_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_scenario(
    bank_id: uuid.UUID, scenario_id: uuid.UUID, db: DB, user: TeacherUser
) -> None:
    await exam_scenario_service.delete_scenario(
        db,
        scenario_id=scenario_id,
        bank_id=bank_id,
        org_id=_org(user),
        created_by=_uid(user),
        is_admin=_is_admin(user),
    )


# ---------------------------------------------------------------------------
# E1-5 (FR-1.5): Question CRUD
# ---------------------------------------------------------------------------


@router.post(
    "/banks/{bank_id}/questions",
    response_model=list[ExamQuestionResponse],
    status_code=status.HTTP_201_CREATED,
)
async def bulk_create_questions(
    bank_id: uuid.UUID,
    data: ExamQuestionBulkCreate,
    db: DB,
    user: TeacherUser,
) -> list[ExamQuestionResponse]:
    questions = await exam_question_service.bulk_create_questions(
        db,
        bank_id=bank_id,
        org_id=_org(user),
        created_by=_uid(user),
        items=data.questions,
    )
    return [ExamQuestionResponse.model_validate(q) for q in questions]


@router.post(
    "/banks/{bank_id}/question",
    response_model=ExamQuestionResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_question(
    bank_id: uuid.UUID,
    data: ExamQuestionCreate,
    db: DB,
    user: TeacherUser,
) -> ExamQuestionResponse:
    question = await exam_question_service.create_question(
        db, bank_id=bank_id, org_id=_org(user), created_by=_uid(user), data=data
    )
    return ExamQuestionResponse.model_validate(question)


@router.get("/banks/{bank_id}/questions", response_model=list[ExamQuestionResponse])
async def list_questions(
    bank_id: uuid.UUID, db: DB, user: TeacherUser
) -> list[ExamQuestionResponse]:
    questions = await exam_question_service.list_questions(db, bank_id=bank_id, org_id=_org(user))
    return [ExamQuestionResponse.model_validate(q) for q in questions]


@router.get("/questions/{question_id}", response_model=ExamQuestionResponse)
async def get_question(
    question_id: uuid.UUID, bank_id: uuid.UUID, db: DB, user: TeacherUser
) -> ExamQuestionResponse:
    question = await exam_question_service.get_question(
        db, question_id=question_id, bank_id=bank_id, org_id=_org(user)
    )
    return ExamQuestionResponse.model_validate(question)


@router.patch("/questions/{question_id}", response_model=ExamQuestionResponse)
async def update_question(
    question_id: uuid.UUID,
    bank_id: uuid.UUID,
    data: ExamQuestionUpdate,
    db: DB,
    user: TeacherUser,
) -> ExamQuestionResponse:
    question = await exam_question_service.update_question(
        db,
        question_id=question_id,
        bank_id=bank_id,
        org_id=_org(user),
        created_by=_uid(user),
        is_admin=_is_admin(user),
        data=data,
    )
    return ExamQuestionResponse.model_validate(question)


@router.delete("/questions/{question_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_question(
    question_id: uuid.UUID, bank_id: uuid.UUID, db: DB, user: TeacherUser
) -> None:
    await exam_question_service.delete_question(
        db,
        question_id=question_id,
        bank_id=bank_id,
        org_id=_org(user),
        created_by=_uid(user),
        is_admin=_is_admin(user),
    )


# ---------------------------------------------------------------------------
# E1-6 (FR-1.6): Question validation + publish gate
# ---------------------------------------------------------------------------


@router.post("/questions/{question_id}/validate", response_model=ExamQuestionResponse)
async def validate_question(
    question_id: uuid.UUID, bank_id: uuid.UUID, db: DB, user: TeacherUser
) -> ExamQuestionResponse:
    """Mark a single question as validated (FR-1.6.1)."""
    question = await exam_question_service.validate_question(
        db, question_id=question_id, bank_id=bank_id, org_id=_org(user)
    )
    return ExamQuestionResponse.model_validate(question)


@router.post("/banks/{bank_id}/validate-all", response_model=BulkValidationResponse)
async def validate_all_questions(
    bank_id: uuid.UUID, db: DB, user: TeacherUser
) -> BulkValidationResponse:
    """Bulk-validate all questions and publish the bank (FR-1.6.2/1.6.3)."""
    validated_count, bank = await exam_question_service.validate_all_and_publish(
        db, bank_id=bank_id, org_id=_org(user)
    )
    return BulkValidationResponse(
        bank_id=bank_id,
        validated_count=validated_count,
        bank_status=bank.status,
    )


# ---------------------------------------------------------------------------
# ExamTest — create (FR-1.7 precondition: bank must be published)
# ---------------------------------------------------------------------------


@router.post(
    "/banks/{bank_id}/tests",
    response_model=ExamTestResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_exam_test(
    bank_id: uuid.UUID,
    body: ExamTestCreate,
    user: TeacherUser,
    db: DB,
) -> object:
    """Create a test configuration from a published exam bank."""
    return await exam_bank_service.create_test(
        db,
        bank_id=bank_id,
        created_by=user.user_id,
        org_id=user.org_id,
        data=body,
    )


@router.patch("/tests/{test_id}", response_model=ExamTestResponse)
async def update_exam_test(
    test_id: uuid.UUID,
    body: ExamTestUpdate,
    user: TeacherUser,
    db: DB,
) -> object:
    """Update an ExamTest (e.g. publish, change title, toggle shuffle)."""
    from sqlalchemy import select

    from app.domain.models.exam import ExamTest

    result = await db.execute(
        select(ExamTest).where(ExamTest.id == test_id)
    )
    test = result.scalar_one_or_none()
    if not test:
        raise HTTPException(status_code=404, detail="ExamTest not found")
    for field, value in body.model_dump(exclude_none=True).items():
        setattr(test, field, value)
    await db.commit()
    await db.refresh(test)
    return test


# ---------------------------------------------------------------------------
# E1-7 (FR-1.7): ExamAttempt — start + submit
# ---------------------------------------------------------------------------


@router.post(
    "/tests/{test_id}/start",
    response_model=StartAttemptResponse,
    status_code=status.HTTP_201_CREATED,
)
async def start_exam_attempt(
    test_id: uuid.UUID,
    db: DB,
    user: CurrentUser,
) -> StartAttemptResponse:
    """Draw questions and create an ExamAttempt (FR-1.7.1).

    Returns attempt + pre-loaded questions so the frontend needs a single call.
    """
    org_id = uuid.UUID(user.org_id) if user.org_id else uuid.UUID(int=0)
    attempt, test, questions = await exam_attempt_service.start_attempt(
        db,
        test_id=test_id,
        user_id=uuid.UUID(user.user_id),
        org_id=org_id,
    )
    return StartAttemptResponse(
        attempt_id=attempt.id,
        test_id=attempt.test_id,
        user_id=attempt.user_id,
        bank_id=test.bank_id,
        question_ids=attempt.question_ids,
        time_limit_minutes=test.time_limit_minutes,
        questions=[ExamQuestionResponse.model_validate(q) for q in questions],
    )


@router.post("/attempts/{attempt_id}/submit", response_model=ExamAttemptResponse)
async def submit_exam_attempt(
    attempt_id: uuid.UUID,
    data: SubmitAttemptRequest,
    db: DB,
    user: CurrentUser,
) -> ExamAttemptResponse:
    """Score MCQ, create dissertation answer rows, enqueue AI grading (FR-1.7.2)."""
    attempt = await exam_attempt_service.submit_attempt(
        db,
        attempt_id=attempt_id,
        user_id=uuid.UUID(user.user_id),
        mcq_answers=data.mcq_answers,
        dissertation_answers=data.dissertation_answers,
        time_taken_sec=data.time_taken_sec,
    )
    return ExamAttemptResponse.model_validate(attempt)


# ---------------------------------------------------------------------------
# E1-9 (FR-1.9): Dissertation review + human scoring
# ---------------------------------------------------------------------------


@router.get(
    "/tests/{test_id}/dissertation-review",
    response_model=list[DissertationAnswerResponse],
)
async def list_dissertation_review(
    test_id: uuid.UUID,
    db: DB,
    user: TeacherUser,
) -> list[DissertationAnswerResponse]:
    """List dissertation answers pending teacher review (FR-1.9.1)."""
    org_id = uuid.UUID(user.org_id) if user.org_id else uuid.UUID(int=0)
    answers = await exam_answer_service.list_for_review(db, test_id=test_id, org_id=org_id)
    return [DissertationAnswerResponse.model_validate(a) for a in answers]


@router.patch("/answers/{answer_id}/human-score", response_model=DissertationAnswerResponse)
async def apply_human_score(
    answer_id: uuid.UUID,
    data: HumanScoreUpdate,
    db: DB,
    user: TeacherUser,
) -> DissertationAnswerResponse:
    """Apply teacher grade to a dissertation answer (FR-1.9.2)."""
    org_id = uuid.UUID(user.org_id) if user.org_id else uuid.UUID(int=0)
    answer = await exam_answer_service.apply_human_score(
        db,
        answer_id=answer_id,
        org_id=org_id,
        graded_by=uuid.UUID(user.user_id),
        human_score=data.human_score,
        human_feedback=data.human_feedback,
    )
    return DissertationAnswerResponse.model_validate(answer)
