"""Shared pytest fixtures for the exam service test suite."""

from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, MagicMock

import pytest

# Stable org / user IDs reused across tests
ORG_A = uuid.UUID("aaaaaaaa-0000-0000-0000-000000000001")
ORG_B = uuid.UUID("bbbbbbbb-0000-0000-0000-000000000001")
TEACHER_ID = uuid.UUID("cccccccc-0000-0000-0000-000000000001")
BANK_ID = uuid.UUID("dddddddd-0000-0000-0000-000000000001")


@pytest.fixture
def mock_db() -> AsyncMock:
    """Lightweight AsyncSession mock for service-layer unit tests."""
    db = AsyncMock()
    db.add = MagicMock()
    db.commit = AsyncMock()
    db.refresh = AsyncMock()
    db.execute = AsyncMock()
    return db


@pytest.fixture
def mock_storage() -> AsyncMock:
    """Mock of ExamEvidenceStorage with async upload/download methods."""
    storage = AsyncMock()
    storage.upload = AsyncMock(return_value="exam-sources/bank/source.pdf")
    storage.download = AsyncMock(return_value=b"")
    storage.presigned_get_url = AsyncMock(return_value="https://minio/presigned")
    return storage
