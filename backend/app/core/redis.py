import redis.asyncio as aioredis

from app.core.config import settings

_redis_client: aioredis.Redis | None = None

EXAM_KEY_PREFIX = "exam:"


def get_redis() -> aioredis.Redis:
    global _redis_client
    if _redis_client is None:
        _redis_client = aioredis.from_url(
            settings.redis_url,
            encoding="utf-8",
            decode_responses=True,
        )
    return _redis_client


def exam_key(suffix: str) -> str:
    """Namespace all Redis keys under exam: to avoid collisions with Sira."""
    return f"{EXAM_KEY_PREFIX}{suffix}"


async def close_redis() -> None:
    global _redis_client
    if _redis_client is not None:
        await _redis_client.aclose()
        _redis_client = None
