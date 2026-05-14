"""ExamSource service — file upload, storage, and DB operations."""

from __future__ import annotations

import uuid
from pathlib import Path

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.models.exam import ExamBank, ExamSource, ExtractionStatus
from app.infrastructure.storage import ExamEvidenceStorage

_ALLOWED_MIME_TYPES = {
    "application/pdf",
    "application/msword",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
}
_MAX_FILE_BYTES = 50 * 1024 * 1024  # 50 MB


async def upload_source(
    db: AsyncSession,
    *,
    bank_id: uuid.UUID,
    org_id: uuid.UUID,
    filename: str,
    content_type: str,
    file_bytes: bytes,
    storage: ExamEvidenceStorage,
) -> ExamSource:
    """Upload a source document to MinIO and create an ExamSource row.

    Validates the bank belongs to org_id, uploads the file, creates the DB
    row with status=pending, and enqueues the extraction Celery task.

    Raises:
        HTTPException(404): bank not found or wrong org
        HTTPException(415): unsupported file type
        HTTPException(413): file exceeds 50 MB
    """
    # Validate bank ownership
    result = await db.execute(
        select(ExamBank).where(ExamBank.id == bank_id, ExamBank.org_id == org_id)
    )
    bank = result.scalar_one_or_none()
    if bank is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="ExamBank not found")

    # Validate file
    if content_type not in _ALLOWED_MIME_TYPES:
        raise HTTPException(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            detail=f"Unsupported file type '{content_type}'. Only PDF and Word are accepted.",
        )
    if len(file_bytes) > _MAX_FILE_BYTES:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail="File exceeds the 50 MB limit.",
        )

    # Build storage key: exam-sources/{bank_id}/{uuid}.{ext}
    ext = Path(filename).suffix.lstrip(".") or "bin"
    source_id = uuid.uuid4()
    storage_key = f"exam-sources/{bank_id}/{source_id}.{ext}"

    # Upload to MinIO
    await storage.upload(storage_key, file_bytes, content_type=content_type)

    # Persist DB row
    source = ExamSource(
        id=source_id,
        bank_id=bank_id,
        filename=filename,
        storage_key=storage_key,
        extraction_status=ExtractionStatus.pending,
    )
    db.add(source)
    await db.commit()
    await db.refresh(source)

    # Enqueue extraction (fire-and-forget)
    from app.tasks.extraction import extract_exam_source_task  # local import avoids circular

    extract_exam_source_task.delay(str(source.id))

    return source


async def get_source(
    db: AsyncSession,
    *,
    source_id: uuid.UUID,
    bank_id: uuid.UUID,
    org_id: uuid.UUID,
) -> ExamSource:
    """Retrieve a source verifying it belongs to the bank and org.

    Raises:
        HTTPException(404): source not found, wrong bank, or wrong org
    """
    result = await db.execute(
        select(ExamSource)
        .join(ExamBank, ExamSource.bank_id == ExamBank.id)
        .where(
            ExamSource.id == source_id,
            ExamSource.bank_id == bank_id,
            ExamBank.org_id == org_id,
        )
    )
    source = result.scalar_one_or_none()
    if source is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="ExamSource not found")
    return source


async def list_sources(
    db: AsyncSession,
    *,
    bank_id: uuid.UUID,
    org_id: uuid.UUID,
) -> list[ExamSource]:
    """List all sources for a bank, verifying org ownership."""
    # Verify bank belongs to org first
    result = await db.execute(
        select(ExamBank).where(ExamBank.id == bank_id, ExamBank.org_id == org_id)
    )
    if result.scalar_one_or_none() is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="ExamBank not found")

    sources_result = await db.execute(
        select(ExamSource)
        .where(ExamSource.bank_id == bank_id)
        .order_by(ExamSource.created_at.desc())
    )
    return list(sources_result.scalars().all())
