"""
app/api/v1/ws.py

WebSocket endpoint for real-time in-app notifications.

  GET /api/v1/ws/notifications?token=<JWT>

JWT validate qilinadi (tenant_slug + user_id), so'ngra Redis pub/sub kanallariga
subscribe qilamiz:
  notif:{tenant_slug}:{user_id}        — shaxsiy
  notif:{tenant_slug}:role:{role}      — role broadcast
  notif:{tenant_slug}:branch:{branch}  — branch broadcast
"""
from __future__ import annotations

import asyncio
import json
import logging
from typing import Optional

from fastapi import APIRouter, Query, WebSocket, WebSocketDisconnect, status

from app.core.config import settings
from app.core.security import decode_token

logger = logging.getLogger(__name__)
router = APIRouter(tags=["ws"])

HEARTBEAT_INTERVAL = 30  # sekund


@router.websocket("/ws/notifications")
async def notifications_ws(
    websocket: WebSocket,
    token: Optional[str] = Query(None),
):
    if not token:
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION, reason="missing_token")
        return

    payload = decode_token(token)
    if not payload or payload.get("type") != "access":
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION, reason="invalid_token")
        return

    user_id     = payload.get("sub")
    tenant_slug = payload.get("tenant_slug")
    role        = payload.get("role")
    branch_id   = payload.get("branch_id")
    if not user_id or not tenant_slug:
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION, reason="invalid_claims")
        return

    await websocket.accept()
    logger.info("ws.connect tenant=%s user=%s role=%s", tenant_slug, user_id, role)

    # ── Redis pub/sub (async client) ──────────────────────────────────
    try:
        from redis import asyncio as aioredis
        client = aioredis.from_url(settings.REDIS_URL, decode_responses=True)
    except Exception as e:
        logger.error("ws.redis.init.error err=%s", e)
        await websocket.close(code=status.WS_1011_INTERNAL_ERROR, reason="redis_unavailable")
        return

    pubsub = client.pubsub()
    channels = [
        f"notif:{tenant_slug}:{user_id}",
        f"notif:{tenant_slug}:role:{role}",
    ]
    if branch_id:
        channels.append(f"notif:{tenant_slug}:branch:{branch_id}")

    try:
        await pubsub.subscribe(*channels)
    except Exception as e:
        logger.error("ws.subscribe.error err=%s", e)
        await websocket.close(code=status.WS_1011_INTERNAL_ERROR)
        await client.close()
        return

    await websocket.send_text(json.dumps({"type": "ready", "channels": channels}))

    async def heartbeat():
        try:
            while True:
                await asyncio.sleep(HEARTBEAT_INTERVAL)
                await websocket.send_text(json.dumps({"type": "ping"}))
        except Exception:
            return

    hb_task = asyncio.create_task(heartbeat())

    try:
        async for message in pubsub.listen():
            if message["type"] != "message":
                continue
            try:
                data = message["data"]
                if isinstance(data, bytes):
                    data = data.decode()
                # Forward as-is (already JSON)
                await websocket.send_text(json.dumps({
                    "type": "notification",
                    "channel": message.get("channel"),
                    "payload": json.loads(data) if isinstance(data, str) else data,
                }))
            except WebSocketDisconnect:
                break
            except Exception as e:
                logger.warning("ws.forward.error err=%s", e)
    except WebSocketDisconnect:
        pass
    except Exception as e:
        logger.exception("ws.loop.error err=%s", e)
    finally:
        hb_task.cancel()
        try:
            await pubsub.unsubscribe()
            await pubsub.close()
            await client.close()
        except Exception:
            pass
        logger.info("ws.disconnect tenant=%s user=%s", tenant_slug, user_id)
