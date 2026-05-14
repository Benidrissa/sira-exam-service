"""Celery task: extract raw text from uploaded source documents (PDF)."""

from __future__ import annotations

import asyncio
import io
import uuid

import structlog

from app.tasks.celery_app import celery_app

logger = structlog.get_logger(__name__)


@celery_app.task(name="extract_exam_source", bind=True, max_retries=3)
def extract_exam_source_task(self, source_id: str) -> dict:  # type: ignore[no-untyped-def]
    return asyncio.run(_extract(source_id))


async def _extract(source_id: str) -> dict:
    from app.core.database import AsyncSessionLocal
    from app.domain.models.exam import ExamSource, ExtractionStatus

    async with AsyncSessionLocal() as db:
        from sqlalchemy import select

        result = await db.execute(select(ExamSource).where(ExamSource.id == uuid.UUID(source_id)))
        source = result.scalar_one_or_none()
        if not source:
            logger.error("exam_source_not_found", source_id=source_id)
            return {"status": "error", "detail": "Source not found"}

        source.extraction_status = ExtractionStatus.extracting
        await db.commit()

        try:
            raw_text = await _read_from_storage(source.storage_key)
            source.raw_text = raw_text
            source.char_count = len(raw_text)
            source.extraction_status = ExtractionStatus.done
            logger.info("exam_source_extracted", source_id=source_id, chars=source.char_count)
        except Exception as exc:
            source.extraction_status = ExtractionStatus.failed
            logger.error("exam_source_extraction_failed", source_id=source_id, error=str(exc))
            await db.commit()
            raise

        await db.commit()
        return {"status": "done", "char_count": source.char_count}


async def _read_from_storage(storage_key: str) -> str:
    """Download object from MinIO and extract text via PyMuPDF."""
    import fitz  # PyMuPDF

    from app.infrastructure.storage import get_exam_storage

    storage = get_exam_storage()
    data: bytes = await storage.download(storage_key)

    doc = fitz.open(stream=io.BytesIO(data), filetype="pdf")
    pages = [page.get_text() for page in doc]
    return "\n\n".join(pages)
