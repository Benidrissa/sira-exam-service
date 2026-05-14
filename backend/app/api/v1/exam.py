"""Exam API — generation, review, CRUD, taking. (E1-1 through E1-9)"""

from __future__ import annotations

import uuid

from fastapi import APIRouter, File, UploadFile, status

from app.api.deps import DB, TeacherUser
from app.domain.models.exam import BankStatus
from app.domain.services import (
    exam_bank_service,
    exam_question_service,
    exam_scenario_service,
    exam_source_service,
)
from app.infrastructure.storage import get_exam_storage
from app.schemas.exam import (
    BulkValidationResponse,
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
)

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
