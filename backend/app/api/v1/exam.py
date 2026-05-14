"""Exam API — generation, review, CRUD, taking. (E1-1 through E1-9)"""

from __future__ import annotations

import uuid

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
