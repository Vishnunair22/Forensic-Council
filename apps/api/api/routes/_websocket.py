"""
WebSocket Routes
================

WebSocket endpoints for live investigation updates.
"""

import asyncio
import json
import time
from collections import deque

from fastapi import APIRouter, WebSocket, WebSocketDisconnect, HTTPException

from api.routes._authz import assert_session_access
from api.routes._session_state import (
    get_active_pipeline_metadata,
    get_session_websockets,
    unregister_websocket,
)
from core.auth import decode_token, User
from core.config import get_settings
from core.structured_logging import get_logger

router = APIRouter(prefix="/api/v1/sessions", tags=["sessions"])
logger = get_logger(__name__)

_ACTIVE_WS_CONNECTIONS = 0


@router.websocket("/{session_id}/live")
async def live_updates(websocket: WebSocket, session_id: str):
    global _ACTIVE_WS_CONNECTIONS
    settings = get_settings()  # Fix NameError
    MAX_WS = getattr(settings, "max_ws_connections", 1000)

    if _ACTIVE_WS_CONNECTIONS >= MAX_WS:
        await websocket.accept(subprotocol="forensic-v1")
        await websocket.send_json({"type": "ERROR", "message": "Server busy"})
        await websocket.close(code=1013, reason="Server busy")
        return

    _ACTIVE_WS_CONNECTIONS += 1
    try:
        await _live_updates_impl(websocket, session_id)
    finally:
        _ACTIVE_WS_CONNECTIONS -= 1


async def _live_updates_impl(websocket: WebSocket, session_id: str):
    """
    WebSocket endpoint for live investigation updates.

    Bridges messages from the background worker via Redis Pub/Sub.
    """
    # ── 1. Accept WebSocket and Authenticate ─────────────────────────────────
    await websocket.accept(subprotocol="forensic-v1")

    auth_token = (
        websocket.cookies.get("fc_session")
        or websocket.cookies.get("sessionid")
        or websocket.cookies.get("access_token")
    )

    if not auth_token:
        for protocol in websocket.scope.get("subprotocols", []):
            if protocol.startswith("token."):
                auth_token = protocol[6:]
                break

    if auth_token:
        logger.info("Extracted WebSocket auth token", session_id=session_id)

    if not auth_token:
        logger.warning("WebSocket auth failed: No token found", session_id=session_id)
        await websocket.send_json({"type": "ERROR", "message": "Auth required"})
        await websocket.close(code=4001)
        return

    user_id = "anonymous"
    try:
        token_data = await decode_token(auth_token)
        user_id = token_data.user_id
    except Exception as e:
        logger.warning(
            "WebSocket auth failed: Invalid token",
            session_id=session_id,
            error=str(e),
        )
        await websocket.send_json({"type": "ERROR", "message": "Invalid token"})
        await websocket.close(code=4001)
        return

    # ── 2. Wait for session metadata ─────────────────────────────────────────
    metadata = None
    for _i in range(60):  # up to 6 s
        metadata = await get_active_pipeline_metadata(session_id)
        if metadata:
            break
        await asyncio.sleep(0.1)

    if not metadata:
        logger.warning(
            "WebSocket connection rejected: Session metadata not found",
            session_id=session_id,
        )
        await websocket.send_json({"type": "ERROR", "message": "Session not found"})
        await websocket.close(code=4004)
        return

    if isinstance(metadata, dict) and metadata.get("status") == "interrupted":
        logger.warning(
            "WebSocket connection rejected: session was interrupted by API restart",
            session_id=session_id,
        )
        await websocket.send_json(
            {
                "type": "ERROR",
                "message": "This investigation was interrupted by a server restart and cannot be resumed. Please start a new investigation.",
                "data": {"status": "interrupted", "recoverable": False},
            }
        )
        await websocket.close(code=4010)
        return

    # ── 3. Verify session ownership ────────────────────────────────────────────
    auth_user = User(
        user_id=user_id, username=user_id, role=metadata.get("investigator_role", "investigator")
    )
    try:
        await assert_session_access(session_id, auth_user)
    except HTTPException as e:
        await websocket.send_json({"type": "ERROR", "message": e.detail})
        await websocket.close(code=4003)
        return

    # ── 4. Subscribe to Redis Updates for this session ───────────────────────
    IDLE_TIMEOUT = 300  # 5 minutes
    PING_INTERVAL = 30  # seconds
    MAX_MESSAGES_PER_MINUTE = 100

    last_activity = time.time()
    message_timestamps: deque[float] = deque(maxlen=200)

    async def _redis_subscriber():
        nonlocal last_activity
        from redis.asyncio import Redis

        settings = get_settings()
        dedicated_redis = None
        pubsub = None
        try:
            dedicated_redis = Redis(
                host=settings.redis_host,
                port=settings.redis_port,
                db=settings.redis_db,
                password=settings.redis_password,
                socket_timeout=None,
                socket_connect_timeout=5,
                socket_keepalive=True,
                decode_responses=True,
            )
            pubsub = dedicated_redis.pubsub()
            channel = f"forensic:updates:{session_id}"
            replay_key = f"forensic:replay:{session_id}"

            await pubsub.subscribe(channel)

            replay_messages = await dedicated_redis.lrange(replay_key, 0, -1)
            if replay_messages:
                for msg_json in replay_messages:
                    try:
                        data = json.loads(msg_json)
                        await websocket.send_json(data)
                        last_activity = time.time()
                    except Exception:
                        pass

            async for message in pubsub.listen():
                if message["type"] == "message":
                    data = json.loads(message["data"])
                    await websocket.send_json(data)
                    last_activity = time.time()
        except asyncio.CancelledError:
            raise
        except Exception as e:
            logger.warning("Redis subscriber error", session_id=session_id, error=str(e))
            try:
                await websocket.send_json(
                    {
                        "type": "ERROR",
                        "message": "Live update channel disconnected. Please refresh.",
                        "data": {"recoverable": True},
                    }
                )
            except Exception:
                pass
            await websocket.close(code=1011)
        finally:
            if pubsub:
                try:
                    await pubsub.unsubscribe()
                    await pubsub.aclose()
                except Exception:
                    pass
            if dedicated_redis:
                try:
                    await dedicated_redis.aclose()
                except Exception:
                    pass

    async def send_ping():
        try:
            while True:
                await asyncio.sleep(PING_INTERVAL)
                try:
                    await websocket.send_json({"type": "PING", "timestamp": time.time()})
                except Exception:
                    break
        except asyncio.CancelledError:
            pass
        except Exception as e:
            logger.debug("Ping task failed", session_id=session_id, error=str(e))

    async def monitor_idle():
        try:
            while True:
                await asyncio.sleep(10)
                if time.time() - last_activity > IDLE_TIMEOUT:
                    logger.warning(
                        "WebSocket idle timeout",
                        session_id=session_id,
                        idle_seconds=time.time() - last_activity,
                    )
                    await websocket.close(code=1000, reason="Idle timeout")
                    break
        except asyncio.CancelledError:
            pass
        except Exception as e:
            logger.debug("Idle monitor task failed", session_id=session_id, error=str(e))

    ping_task = asyncio.create_task(send_ping())
    idle_task = asyncio.create_task(monitor_idle())
    subscriber_task = asyncio.create_task(_redis_subscriber())

    try:
        await websocket.send_json(
            {
                "type": "CONNECTED",
                "session_id": session_id,
                "message": "Connected to distributed live updates",
                "data": {"status": "connected", "user_id": user_id},
            }
        )

        while True:
            try:
                data = await websocket.receive_text()
                last_activity = time.time()

                now = time.time()
                one_min_ago = now - 60

                while message_timestamps and message_timestamps[0] < one_min_ago:
                    message_timestamps.popleft()

                if len(message_timestamps) >= MAX_MESSAGES_PER_MINUTE:
                    logger.warning(
                        "WebSocket rate limit exceeded",
                        session_id=session_id,
                        messages_per_minute=len(message_timestamps),
                    )
                    await websocket.send_json(
                        {
                            "type": "ERROR",
                            "detail": "Rate limit exceeded. Maximum 100 messages per minute.",
                        }
                    )
                    await websocket.close(code=1008, reason="Rate limit exceeded")
                    break

                message_timestamps.append(now)

                try:
                    msg = json.loads(data)
                    if msg.get("type") == "PONG":
                        continue
                except json.JSONDecodeError:
                    pass

            except WebSocketDisconnect:
                break

    except WebSocketDisconnect:
        pass
    except asyncio.CancelledError:
        raise
    except Exception as ws_err:
        logger.warning("WebSocket error", session_id=session_id, error=str(ws_err))
    finally:
        ping_task.cancel()
        idle_task.cancel()
        subscriber_task.cancel()

        await asyncio.gather(ping_task, idle_task, subscriber_task, return_exceptions=True)
        unregister_websocket(session_id, websocket)
