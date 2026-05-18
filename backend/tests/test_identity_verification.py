"""Tests for E3-15: Pre-exam selfie + ID identity verification."""
from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from tests.conftest import ORG_A

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_session(
    verified: bool = False,
    status: str | None = None,
    selfie_key: str | None = None,
) -> MagicMock:
    s = MagicMock()
    s.id = uuid.uuid4()
    s.user_id = uuid.UUID("dddddddd-0000-0000-0000-000000000002")
    s.org_id = ORG_A
    s.identity_verified = verified
    s.identity_status = status
    s.identity_selfie_key = selfie_key
    s.identity_verified_at = None
    return s


# ---------------------------------------------------------------------------
# exam_evidence helper
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_identity_selfie_upload_url_returns_url_and_key() -> None:
    """get_identity_selfie_upload_url returns a (url, key) tuple with expected key prefix."""
    from app.infrastructure.exam_evidence import get_identity_selfie_upload_url

    session_id = str(uuid.uuid4())
    with patch(
        "app.infrastructure.exam_evidence.get_exam_storage"
    ) as mock_get_storage:
        mock_storage = AsyncMock()
        mock_storage.presigned_put_url = AsyncMock(return_value="https://minio/identity-url")
        mock_get_storage.return_value = mock_storage

        url, key = await get_identity_selfie_upload_url(session_id)

    assert url == "https://minio/identity-url"
    assert key.startswith(f"identity_selfies/{session_id}/")
    assert key.endswith(".jpg")


# ---------------------------------------------------------------------------
# API endpoint: POST /identity/recorded
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_identity_selfie_recorded_sets_pending_and_enqueues(mock_db: AsyncMock) -> None:
    """POST /identity/recorded saves key, sets status=pending, enqueues verify_identity."""
    from app.api.v1.proctor import identity_selfie_recorded
    from app.schemas.proctor import IdentitySelfieRecordedRequest

    session = _make_session()
    mock_db.get = AsyncMock(return_value=session)

    user = MagicMock()
    user.user_id = str(session.user_id)
    user.org_id = str(ORG_A)

    with patch("app.api.v1.proctor._get_session_or_404", return_value=session), \
         patch("app.api.v1.proctor.verify_identity") as mock_task:
        mock_task.delay = MagicMock()
        result = await identity_selfie_recorded(
            session_id=session.id,
            body=IdentitySelfieRecordedRequest(storage_key="identity_selfies/sid/123.jpg"),
            db=mock_db,
            user=user,
        )

    assert session.identity_selfie_key == "identity_selfies/sid/123.jpg"
    assert session.identity_status == "pending"
    mock_task.delay.assert_called_once_with(str(session.id))
    assert result.session_id == session.id


@pytest.mark.asyncio
async def test_identity_selfie_recorded_already_verified_returns_409(mock_db: AsyncMock) -> None:
    """POST /identity/recorded returns 409 when session is already verified."""
    from fastapi import HTTPException

    from app.api.v1.proctor import identity_selfie_recorded
    from app.schemas.proctor import IdentitySelfieRecordedRequest

    session = _make_session(verified=True)
    user = MagicMock()
    user.user_id = str(session.user_id)
    user.org_id = str(ORG_A)

    with patch("app.api.v1.proctor._get_session_or_404", return_value=session), \
         pytest.raises(HTTPException) as exc_info:
        await identity_selfie_recorded(
            session_id=session.id,
            body=IdentitySelfieRecordedRequest(storage_key="identity_selfies/sid/123.jpg"),
            db=mock_db,
            user=user,
        )

    assert exc_info.value.status_code == 409


# ---------------------------------------------------------------------------
# API endpoint: GET /identity/status
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_identity_status_returns_current_state(mock_db: AsyncMock) -> None:
    """GET /identity/status returns the current identity_status and verified flag."""
    from app.api.v1.proctor import get_identity_status

    session = _make_session(verified=False, status="analyzing")
    user = MagicMock()
    user.user_id = str(session.user_id)
    user.org_id = str(ORG_A)

    with patch("app.api.v1.proctor._get_session_or_404", return_value=session):
        result = await get_identity_status(
            session_id=session.id,
            db=mock_db,
            user=user,
        )

    assert result.identity_verified is False
    assert result.identity_status == "analyzing"


# ---------------------------------------------------------------------------
# Celery task: verify_identity
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_verify_identity_async_sets_verified_on_claude_pass() -> None:
    """_verify_identity_async sets identity_verified=True when Claude confirms face+ID."""
    from app.tasks.proctor_tasks import _verify_identity_async

    session = _make_session(selfie_key="identity_selfies/sid/123.jpg")

    mock_tool_input = {
        "face_visible": True,
        "id_visible": True,
        "face_matches_id": True,
        "confidence": 0.92,
        "reason": "Face and ID clearly visible",
    }
    mock_content = MagicMock()
    mock_content.input = mock_tool_input
    mock_response = MagicMock()
    mock_response.content = [mock_content]

    with patch("app.tasks.proctor_tasks.asyncio") as _mock_asyncio, \
         patch("app.core.database.celery_db") as mock_celery_db_cls, \
         patch("app.infrastructure.storage.get_exam_storage") as _mock_storage_factory, \
         patch("anthropic.Anthropic") as mock_anthropic_cls:

        mock_db_ctx = AsyncMock()
        mock_db_ctx.__aenter__ = AsyncMock(return_value=mock_db_ctx)
        mock_db_ctx.__aexit__ = AsyncMock(return_value=False)
        mock_db_ctx.get = AsyncMock(return_value=session)
        mock_db_ctx.commit = AsyncMock()
        mock_celery_db_cls.return_value = mock_db_ctx

        mock_storage = AsyncMock()
        mock_storage.download = AsyncMock(return_value=b"\xff\xd8\xff\xe0test")
        _mock_storage_factory.return_value = mock_storage

        mock_anthropic_inst = MagicMock()
        mock_anthropic_inst.messages.create.return_value = mock_response
        mock_anthropic_cls.return_value = mock_anthropic_inst

        result = await _verify_identity_async(str(session.id))

    assert result["verified"] is True
    assert session.identity_verified is True
    assert session.identity_status == "verified"
    assert session.identity_verified_at is not None


@pytest.mark.asyncio
async def test_verify_identity_async_sets_failed_when_no_id() -> None:
    """_verify_identity_async sets identity_verified=False when ID not visible."""
    from app.tasks.proctor_tasks import _verify_identity_async

    session = _make_session(selfie_key="identity_selfies/sid/123.jpg")

    mock_tool_input = {
        "face_visible": True,
        "id_visible": False,
        "face_matches_id": False,
        "confidence": 0.40,
        "reason": "ID not visible in frame",
    }
    mock_content = MagicMock()
    mock_content.input = mock_tool_input
    mock_response = MagicMock()
    mock_response.content = [mock_content]

    with patch("app.core.database.celery_db") as mock_celery_db_cls, \
         patch("app.infrastructure.storage.get_exam_storage") as _mock_storage_factory, \
         patch("anthropic.Anthropic") as mock_anthropic_cls:

        mock_db_ctx = AsyncMock()
        mock_db_ctx.__aenter__ = AsyncMock(return_value=mock_db_ctx)
        mock_db_ctx.__aexit__ = AsyncMock(return_value=False)
        mock_db_ctx.get = AsyncMock(return_value=session)
        mock_db_ctx.commit = AsyncMock()
        mock_celery_db_cls.return_value = mock_db_ctx

        mock_storage = AsyncMock()
        mock_storage.download = AsyncMock(return_value=b"\xff\xd8\xff\xe0test")
        _mock_storage_factory.return_value = mock_storage

        mock_anthropic_inst = MagicMock()
        mock_anthropic_inst.messages.create.return_value = mock_response
        mock_anthropic_cls.return_value = mock_anthropic_inst

        result = await _verify_identity_async(str(session.id))

    assert result["verified"] is False
    assert session.identity_verified is False
    assert session.identity_status == "failed"
