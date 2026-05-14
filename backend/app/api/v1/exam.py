"""Exam API — generation, review, CRUD, taking. (E1-1 through E1-9)"""

from __future__ import annotations

import uuid

from celery.result import AsyncResult
from fastapi import APIRouter, File, UploadFile, status

from app.api.deps import DB, TeacherUser
from app.domain.models.exam import BankStatus
from app.domain.services import exam_bank_service, exam_source_service
from app.infrastructure.storage import get_exam_storage
from app.schemas.exam import (
    ExamBankCreate,
    ExamBankResponse,
    ExamBankUpdate,
    ExamSourceResponse,
    GenerateBriefRequest,
    GenerationStatusResponse,
    RegenerateRequest,
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
