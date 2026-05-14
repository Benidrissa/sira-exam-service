"""MinIO/S3 storage for exam evidence (private ACL, presigned URLs)."""

from __future__ import annotations

import io
from functools import lru_cache

import aiobotocore.session
import structlog

from app.core.config import settings

logger = structlog.get_logger(__name__)

PRESIGNED_EXPIRY = 300  # seconds


class ExamEvidenceStorage:
    def __init__(self) -> None:
        self._session = aiobotocore.session.get_session()
        self._endpoint = (
            f"{'https' if settings.minio_use_ssl else 'http'}://{settings.minio_endpoint}"
        )
        self._bucket = settings.minio_exam_bucket

    def _client_kwargs(self) -> dict:
        return {
            "service_name": "s3",
            "endpoint_url": self._endpoint,
            "aws_access_key_id": settings.minio_access_key,
            "aws_secret_access_key": settings.minio_secret_key,
        }

    async def ensure_bucket(self) -> None:
        async with self._session.create_client(**self._client_kwargs()) as client:
            try:
                await client.head_bucket(Bucket=self._bucket)
            except Exception:
                await client.create_bucket(Bucket=self._bucket)
                logger.info("exam_bucket_created", bucket=self._bucket)

    async def upload(
        self, key: str, data: bytes, content_type: str = "application/octet-stream"
    ) -> str:
        async with self._session.create_client(**self._client_kwargs()) as client:
            await client.put_object(
                Bucket=self._bucket,
                Key=key,
                Body=io.BytesIO(data),
                ContentType=content_type,
            )
        return key

    async def download(self, key: str) -> bytes:
        async with self._session.create_client(**self._client_kwargs()) as client:
            response = await client.get_object(Bucket=self._bucket, Key=key)
            return await response["Body"].read()

    async def presigned_get_url(self, key: str, expiry: int = PRESIGNED_EXPIRY) -> str:
        async with self._session.create_client(**self._client_kwargs()) as client:
            return await client.generate_presigned_url(
                "get_object",
                Params={"Bucket": self._bucket, "Key": key},
                ExpiresIn=expiry,
            )

    async def presigned_put_url(self, key: str, expiry: int = PRESIGNED_EXPIRY) -> str:
        async with self._session.create_client(**self._client_kwargs()) as client:
            return await client.generate_presigned_url(
                "put_object",
                Params={"Bucket": self._bucket, "Key": key},
                ExpiresIn=expiry,
            )


@lru_cache(maxsize=1)
def get_exam_storage() -> ExamEvidenceStorage:
    return ExamEvidenceStorage()
