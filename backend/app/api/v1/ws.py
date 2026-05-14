"""WebSocket signaling layer — real-time proctor event delivery via Redis pub/sub.

E2-3: Implements FR-2.6 (proctor dashboard live feed).
Each exam session gets a Redis channel: proctor:session:{session_id}.
Celery tasks publish to that channel; proctor clients subscribe via WS.
"""

from __future__ import annotations

import asyncio
import contextlib
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


async def _redis_listener(websocket: WebSocket, pubsub: object) -> None:  # type: ignore[type-arg]
    """Forward Redis pub/sub messages to the WebSocket client."""
    async for msg in pubsub.listen():  # type: ignore[union-attr]
        if msg["type"] == "message":
            data = msg["data"]
            text = data.decode() if isinstance(data, bytes) else data
            await websocket.send_text(text)


async def _client_listener(
    websocket: WebSocket,
    db: object,  # type: ignore[type-arg]
    actor_user_id: uuid.UUID,
) -> None:
    """Receive client messages and process acknowledgements."""
    while True:
        raw = await websocket.receive_text()
        try:
            payload = json.loads(raw)
        except json.JSONDecodeError:
            continue

        if payload.get("type") == "acknowledge":
            alert_id_str: str = payload.get("alert_id", "")
            if not alert_id_str:
                continue
            try:
                alert_uuid = uuid.UUID(alert_id_str)
            except ValueError:
                continue

            from app.core.database import AsyncSessionLocal
            from app.domain.models.proctor import ProctorAlert  # type: ignore[attr-defined]

            async with AsyncSessionLocal() as ack_db:
                alert = await ack_db.get(ProctorAlert, alert_uuid)
                if alert and not alert.acknowledged:
                    alert.acknowledged = True
                    alert.acknowledged_by = actor_user_id
                    alert.acknowledged_at = datetime.now(UTC)
                    await ack_db.commit()


@router.websocket("/proctor/{session_id}")
async def proctor_ws(websocket: WebSocket, session_id: str, token: str = "") -> None:
    """Proctor connects here to receive live events for a session.

    Query params:
        token: raw session token (required) — validated against session_token_hash in DB.

    Incoming client messages:
        {"type": "acknowledge", "alert_id": "<uuid>"}
    Outgoing server messages: JSON payloads published by Celery tasks.
    """
    # Validate token before accepting the connection
    from app.core.database import AsyncSessionLocal
    from app.domain.services.proctor_session_service import (  # type: ignore[attr-defined]
        verify_session_token,
    )

    async with AsyncSessionLocal() as db:
        session = await verify_session_token(db, raw_token=token)
        if not session or str(session.id) != session_id:
            await websocket.close(code=1008)
            return

    actor_user_id: uuid.UUID = session.user_id

    await websocket.accept()
    _proctor_connections.setdefault(session_id, set()).add(websocket)

    redis = await get_redis()
    pubsub = redis.pubsub()
    await pubsub.subscribe(f"proctor:session:{session_id}")

    redis_task = asyncio.create_task(_redis_listener(websocket, pubsub))
    client_task = asyncio.create_task(_client_listener(websocket, None, actor_user_id))

    try:
        _done, pending = await asyncio.wait(
            [redis_task, client_task],
            return_when=asyncio.FIRST_COMPLETED,
        )
        for task in pending:
            task.cancel()
            with contextlib.suppress(asyncio.CancelledError, Exception):
                await task
    except (WebSocketDisconnect, Exception):  # noqa: BLE001
        pass
    finally:
        _proctor_connections.get(session_id, set()).discard(websocket)
        await pubsub.unsubscribe(f"proctor:session:{session_id}")
        await pubsub.aclose()
