"""Tests for ExamSource upload endpoint and service (FR-1.0)."""

from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.domain.models.exam import ExamBank, ExamSource, ExtractionStatus
from app.domain.services import exam_source_service
from tests.conftest import BANK_ID, ORG_A, ORG_B, TEACHER_ID


def _make_bank(org_id: uuid.UUID = ORG_A) -> ExamBank:
    bank = MagicMock(spec=ExamBank)
    bank.id = BANK_ID
    bank.org_id = org_id
    bank.created_by = TEACHER_ID
    return bank


def _make_source() -> ExamSource:
    source = MagicMock(spec=ExamSource)
    source.id = uuid.uuid4()
    source.bank_id = BANK_ID
    source.filename = "lecture.pdf"
    source.storage_key = f"exam-sources/{BANK_ID}/abc.pdf"
    source.extraction_status = ExtractionStatus.pending
    source.error_message = None
    source.raw_text = None
    source.char_count = None
    return source


# ---------------------------------------------------------------------------
# Service: upload_source
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_upload_source_success(mock_db: AsyncMock, mock_storage: AsyncMock) -> None:
    """Happy path: valid PDF, bank in same org → source created, task enqueued."""
    mock_db.execute.return_value.scalar_one_or_none.return_value = _make_bank()

    source = _make_source()
    mock_db.refresh = AsyncMock(side_effect=lambda s: None)

    with (
        patch("app.domain.services.exam_source_service.ExamSource", return_value=source),
        patch("app.tasks.extraction.extract_exam_source_task") as mock_task,
    ):
        mock_task.delay = MagicMock()
        result = await exam_source_service.upload_source(
            mock_db,
            bank_id=BANK_ID,
            org_id=ORG_A,
            filename="lecture.pdf",
            content_type="application/pdf",
            file_bytes=b"%PDF-1.4 test",
            storage=mock_storage,
        )

    mock_storage.upload.assert_awaited_once()
    mock_db.commit.assert_awaited()
    assert result.extraction_status == ExtractionStatus.pending


@pytest.mark.asyncio
async def test_upload_source_wrong_org_raises_404(
    mock_db: AsyncMock, mock_storage: AsyncMock
) -> None:
    """Bank belongs to ORG_B — teacher from ORG_A gets 404."""
    from fastapi import HTTPException

    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = None  # bank not found for this org
    mock_db.execute = AsyncMock(return_value=mock_result)

    with pytest.raises(HTTPException) as exc_info:
        await exam_source_service.upload_source(
            mock_db,
            bank_id=BANK_ID,
            org_id=ORG_A,
            filename="lecture.pdf",
            content_type="application/pdf",
            file_bytes=b"%PDF-1.4 test",
            storage=mock_storage,
        )

    assert exc_info.value.status_code == 404
    mock_storage.upload.assert_not_awaited()


@pytest.mark.asyncio
async def test_upload_source_unsupported_type_raises_415(
    mock_db: AsyncMock, mock_storage: AsyncMock
) -> None:
    """Non-PDF/Word file type → 415 Unsupported Media Type."""
    from fastapi import HTTPException

    mock_db.execute.return_value.scalar_one_or_none.return_value = _make_bank()

    with pytest.raises(HTTPException) as exc_info:
        await exam_source_service.upload_source(
            mock_db,
            bank_id=BANK_ID,
            org_id=ORG_A,
            filename="spreadsheet.xlsx",
            content_type="application/vnd.ms-excel",
            file_bytes=b"PK...",
            storage=mock_storage,
        )

    assert exc_info.value.status_code == 415
    mock_storage.upload.assert_not_awaited()


@pytest.mark.asyncio
async def test_upload_source_file_too_large_raises_413(
    mock_db: AsyncMock, mock_storage: AsyncMock
) -> None:
    """File exceeding 50 MB → 413 Request Entity Too Large."""
    from fastapi import HTTPException

    mock_db.execute.return_value.scalar_one_or_none.return_value = _make_bank()
    big_file = b"x" * (51 * 1024 * 1024)  # 51 MB

    with pytest.raises(HTTPException) as exc_info:
        await exam_source_service.upload_source(
            mock_db,
            bank_id=BANK_ID,
            org_id=ORG_A,
            filename="huge.pdf",
            content_type="application/pdf",
            file_bytes=big_file,
            storage=mock_storage,
        )

    assert exc_info.value.status_code == 413
    mock_storage.upload.assert_not_awaited()


# ---------------------------------------------------------------------------
# Service: list_sources / get_source
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_list_sources_wrong_org_raises_404(mock_db: AsyncMock) -> None:
    """list_sources returns 404 when bank org doesn't match."""
    from fastapi import HTTPException

    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = None
    mock_db.execute = AsyncMock(return_value=mock_result)

    with pytest.raises(HTTPException) as exc_info:
        await exam_source_service.list_sources(mock_db, bank_id=BANK_ID, org_id=ORG_B)

    assert exc_info.value.status_code == 404


@pytest.mark.asyncio
async def test_get_source_not_found_raises_404(mock_db: AsyncMock) -> None:
    """get_source returns 404 when source_id doesn't exist in bank."""
    from fastapi import HTTPException

    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = None
    mock_db.execute = AsyncMock(return_value=mock_result)

    with pytest.raises(HTTPException) as exc_info:
        await exam_source_service.get_source(
            mock_db,
            source_id=uuid.uuid4(),
            bank_id=BANK_ID,
            org_id=ORG_A,
        )

    assert exc_info.value.status_code == 404
