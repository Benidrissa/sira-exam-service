"""MinIO exam-evidence storage — presigned URLs for snapshots and reference frames (E2-4)."""

from __future__ import annotations

import structlog

from app.infrastructure.storage import get_exam_storage

logger = structlog.get_logger(__name__)

_SNAPSHOT_UPLOAD_EXPIRY = 300  # 5 minutes
_SNAPSHOT_DOWNLOAD_EXPIRY = 3600  # 1 hour
_REFERENCE_FRAME_UPLOAD_EXPIRY = 300  # 5 minutes


async def get_snapshot_upload_url(session_id: str, snapshot_id: str) -> str:
    """Return a presigned PUT URL for uploading a webcam snapshot.

    Key format: ``snapshots/<session_id>/<snapshot_id>.jpg``
    URL expires in 300 seconds.
    """
    key = f"snapshots/{session_id}/{snapshot_id}.jpg"
    storage = get_exam_storage()
    url = await storage.presigned_put_url(key, expiry=_SNAPSHOT_UPLOAD_EXPIRY)
    logger.debug("snapshot_upload_url_issued", session_id=session_id, snapshot_id=snapshot_id)
    return url


async def get_snapshot_download_url(storage_key: str) -> str:
    """Return a presigned GET URL for downloading a snapshot.

    URL expires in 3600 seconds.
    """
    storage = get_exam_storage()
    return await storage.presigned_get_url(storage_key, expiry=_SNAPSHOT_DOWNLOAD_EXPIRY)


async def get_reference_frame_upload_url(session_id: str) -> str:
    """Return a presigned PUT URL for uploading a reference/ID photo.

    Key format: ``reference_frames/<session_id>.jpg``
    URL expires in 300 seconds.
    """
    key = f"reference_frames/{session_id}.jpg"
    storage = get_exam_storage()
    url = await storage.presigned_put_url(key, expiry=_REFERENCE_FRAME_UPLOAD_EXPIRY)
    logger.debug("reference_frame_upload_url_issued", session_id=session_id)
    return url


_OFFLINE_FRAME_UPLOAD_EXPIRY = 600  # 10 minutes (vs 300s for live frames)


async def get_offline_frame_upload_url(session_id: str, snapshot_id: str) -> tuple[str, str]:
    """Return (presigned_put_url, storage_key) for an offline-captured frame."""
    key = f"snapshots/{session_id}/{snapshot_id}.jpg"
    storage = get_exam_storage()
    url = await storage.presigned_put_url(key, expiry=_OFFLINE_FRAME_UPLOAD_EXPIRY)
    return url, key


_IDENTITY_SELFIE_UPLOAD_EXPIRY = 300  # 5 minutes


async def get_identity_selfie_upload_url(session_id: str) -> tuple[str, str]:
    """Return (presigned_put_url, storage_key) for uploading a pre-exam identity selfie.

    Key format: ``identity_selfies/<session_id>/<epoch_ms>.jpg``
    """
    from datetime import UTC, datetime

    ts = int(datetime.now(UTC).timestamp() * 1000)
    key = f"identity_selfies/{session_id}/{ts}.jpg"
    storage = get_exam_storage()
    url = await storage.presigned_put_url(key, expiry=_IDENTITY_SELFIE_UPLOAD_EXPIRY)
    logger.debug("identity_selfie_upload_url_issued", session_id=session_id)
    return url, key


async def ensure_exam_evidence_bucket() -> None:
    """Create the exam-evidence bucket if it does not already exist."""
    storage = get_exam_storage()
    await storage.ensure_bucket()
    logger.info("exam_evidence_bucket_ready", bucket=storage._bucket)
