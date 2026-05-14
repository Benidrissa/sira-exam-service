"""WebSocket signaling layer — real-time proctor event delivery via Redis pub/sub.

E2-3: Implements FR-2.6 (proctor dashboard live feed).
Each exam session gets a Redis channel: proctor:session:{session_id}.
Celery tasks publish to that channel; proctor clients subscribe via WS.
"""

from __future__ import annotations

import asyncio
import json
import uuid
from datetime import UTC, datetime

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from app.core.redis_client import get_redis

router = APIRouter(prefix="/ws", tags=["websocket"])

# In-memory registry: session_id -> set[WebSocket]
# Only used for same-process fast-path; Redis pub/sub handles multi-process fanout.
_proctor_connections: dict[str, set[WebSocket]] = {}


async def broadcast_to_session(session_id: str, message: dict) -> None:  # type: ignore[type-arg]
    """Publish a message to Redis so all instances can fan out to connected proctors."""
    redis = await get_redis()
    await redis.publish(f"proctor:session:{session_id}", json.dumps(message))


@router.websocket("/proctor/{session_id}")
async def proctor_ws(websocket: WebSocket, session_id: str) -> None:
    """Proctor connects here to receive live events for a session.

    Incoming client messages:
        {"type": "acknowledge", "alert_id": "<uuid>", "user_id": "<uuid>"}
    Outgoing server messages: JSON payloads published by Celery tasks.
    """
    await websocket.accept()
    _proctor_connections.setdefault(session_id, set()).add(websocket)

    redis = await get_redis()
    pubsub = redis.pubsub()
    await pubsub.subscribe(f"proctor:session:{session_id}")

    async def _redis_listener() -> None:
        async for msg in pubsub.listen():
            if msg["type"] == "message":
                data = msg["data"]
                text = data.decode() if isinstance(data, bytes) else data
                await websocket.send_text(text)

    async def _client_listener() -> None:
        while True:
            raw = await websocket.receive_text()
            try:
                payload = json.loads(raw)
            except json.JSONDecodeError:
                continue

            if payload.get("type") == "acknowledge":
                alert_id_str: str = payload.get("alert_id", "")
                user_id_str: str = payload.get("user_id", "")
                if not alert_id_str:
                    continue
                try:
                    alert_uuid = uuid.UUID(alert_id_str)
                    actor_uuid = uuid.UUID(user_id_str) if user_id_str else uuid.uuid4()
                except ValueError:
                    continue

                from app.core.database import AsyncSessionLocal
                from app.domain.models.proctor import ProctorAlert  # type: ignore[attr-defined]

                async with AsyncSessionLocal() as db:
                    alert = await db.get(ProctorAlert, alert_uuid)
                    if alert and not alert.acknowledged:
                        alert.acknowledged = True
                        alert.acknowledged_by = actor_uuid
                        alert.acknowledged_at = datetime.now(UTC)
                        await db.commit()

    try:
        await asyncio.gather(_redis_listener(), _client_listener())
    except WebSocketDisconnect:
        pass
    except Exception:  # noqa: BLE001
        pass
    finally:
        _proctor_connections.get(session_id, set()).discard(websocket)
        await pubsub.unsubscribe(f"proctor:session:{session_id}")
        await pubsub.aclose()
