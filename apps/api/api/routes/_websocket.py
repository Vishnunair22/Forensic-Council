"""
WebSocket Routes
================

WebSocket endpoints for live investigation updates.
"""

import asyncio
import json
import time
from collections import deque
from typing import Any

from fastapi import APIRouter, HTTPException, WebSocket, WebSocketDisconnect

from api.routes._authz import assert_session_access
from api.routes._session_state import (
    get_active_pipeline_metadata,
    register_websocket,
    unregister_websocket,
)
from core.auth import User, UserRole, decode_token
from core.config import get_settings
from core.structured_logging import get_logger

router = APIRouter(prefix="/api/v1/sessions", tags=["sessions"])
logger = get_logger(__name__)

_ws_lock = asyncio.Lock()
_ACTIVE_WS_CONNECTIONS = 0
MAX_MESSAGES_PER_MINUTE = 100
IDLE_TIMEOUT = 300


@router.websocket("/{session_id}/live")
async def live_updates(websocket: WebSocket, session_id: str):
    global _ACTIVE_WS_CONNECTIONS
    settings = get_settings()
    max_ws = getattr(settings, "max_ws_connections", 1000)

    # Authenticate BEFORE accept — read cookies/headers on the raw ASGI scope
    auth_token = (
        websocket.cookies.get("fc_session")
        or websocket.cookies.get("sessionid")
        or websocket.cookies.get("access_token")
    )

    user_id = "anonymous"
    token_role: str | None = None
    if auth_token:
        try:
            token_data = await decode_token(auth_token)
            user_id = token_data.user_id
            token_role = getattr(token_data, "role", None)
        except Exception:
            pass

    if not user_id or user_id == "anonymous":
        await websocket.close(code=4001, reason="Auth required")
        return

    async with _ws_lock:
        if _ACTIVE_WS_CONNECTIONS >= max_ws:
            await websocket.close(code=1013, reason="Server busy")
            return
        _ACTIVE_WS_CONNECTIONS += 1

    try:
        await _live_updates_impl(websocket, session_id, user_id, token_role)
    finally:
        async with _ws_lock:
            _ACTIVE_WS_CONNECTIONS -= 1


async def _live_updates_impl(websocket: WebSocket, session_id: str, user_id: str, token_role: str | None):
    """
    WebSocket endpoint for live investigation updates.

    Bridges messages from the background worker via Redis Pub/Sub.
    """
    # ── 1. Accept now that auth passed ─────────────────────────────────────────
    await websocket.accept(subprotocol="forensic-v1")

    # ── 2. Wait for session metadata ─────────────────────────────────────────
    # Metadata is written to Redis by start_investigation() before the HTTP
    # response is returned, so it should be present on the first read.  The
    # loop is a defensive guard against any transient Redis propagation delay.
    metadata = None
    for _i in range(10):  # up to 1 s
        metadata = await get_active_pipeline_metadata(session_id)
        if metadata:
            break
        await asyncio.sleep(0.1)

    if not metadata:
        # Check if pipeline exists in-memory (Redis metadata may lag after restart)
        from orchestration.pipeline_registry import get_pipeline

        pipeline = get_pipeline(session_id)
        if pipeline is not None:
            metadata = {"status": "running", "investigator_id": "pending"}
            logger.info(
                "WebSocket reconnecting: Found active pipeline in memory",
                session_id=session_id,
            )
        else:
            # DB fallback: session may exist in persistent storage even if the
            # Redis key expired or was evicted (e.g. after an API restart).
            from api.routes._authz import _load_session_metadata_from_db

            metadata = await _load_session_metadata_from_db(session_id)
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
    # S-H-4: role MUST come from the signed JWT (token_role), never from
    # session metadata. Fall back to "investigator" only if the token did
    # not include a role claim — never elevate from metadata.
    try:
        role = UserRole(token_role) if token_role else UserRole.INVESTIGATOR
    except ValueError:
        role = UserRole.INVESTIGATOR

    auth_user = User(
        user_id=user_id,
        username=user_id,
        role=role,
    )
    try:
        await assert_session_access(session_id, auth_user)
    except HTTPException as e:
        await websocket.send_json({"type": "ERROR", "message": e.detail})
        await websocket.close(code=4003)
        return

    # C-C-1: register in the in-process WS connection map so that pipeline-
    # local broadcasts (the non-Redis-worker path, used in single-container
    # dev deployments) actually reach this socket. Previously the handler
    # only subscribed to Redis pub/sub; broadcast_update against the local
    # map silently dropped messages and the unregister call at function-end
    # was a no-op.
    register_websocket(session_id, websocket)

    # ── 4. Subscribe to Redis Updates for this session ───────────────────────
    idle_timeout = IDLE_TIMEOUT  # 5 minutes
    ping_interval = 30  # seconds
    max_messages_per_minute = MAX_MESSAGES_PER_MINUTE

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
            control_channel = f"forensic:control:{session_id}"
            replay_key = f"forensic:replay:{session_id}"

            await pubsub.subscribe(channel, control_channel)

            dedicated_redis_any: Any = dedicated_redis
            replay_messages = await dedicated_redis_any.lrange(replay_key, 0, -1)
            if replay_messages:
                for msg_json in replay_messages:
                    try:
                        data = json.loads(msg_json)
                        await websocket.send_json(data)
                        last_activity = time.time()
                    except Exception as replay_error:
                        logger.debug(
                            "Failed to replay WebSocket update",
                            session_id=session_id,
                            error=str(replay_error),
                        )

            async for message in pubsub.listen():
                if message["type"] == "message":
                    channel_name = message.get("channel", "")
                    if channel_name == control_channel:
                        payload = json.loads(message["data"])
                        if payload.get("type") == "SESSION_TERMINATED":
                            await websocket.send_json({"type": "ERROR", "message": payload.get("reason", "Session terminated")})
                            await websocket.close(code=1000, reason="Session terminated")
                            return
                        continue
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
            except Exception as send_error:
                logger.debug(
                    "Failed to send WebSocket subscriber error",
                    session_id=session_id,
                    error=str(send_error),
                )
            await websocket.close(code=1011)
        finally:
            if pubsub:
                try:
                    await pubsub.unsubscribe()
                    await pubsub.close()
                except Exception as pubsub_error:
                    logger.debug(
                        "Failed to close WebSocket pubsub",
                        session_id=session_id,
                        error=str(pubsub_error),
                    )
            if dedicated_redis:
                try:
                    await dedicated_redis.aclose()
                except Exception as redis_close_error:
                    logger.debug(
                        "Failed to close WebSocket Redis client",
                        session_id=session_id,
                        error=str(redis_close_error),
                    )

    async def send_ping():
        nonlocal last_activity
        try:
            while True:
                await asyncio.sleep(ping_interval)
                try:
                    await websocket.send_json({"type": "PING", "timestamp": time.time()})
                    last_activity = time.time()
                except Exception:
                    break
        except asyncio.CancelledError:
            pass
        except Exception as e:
            logger.debug("Ping task failed", session_id=session_id, error=str(e))

    async def monitor_idle():
        nonlocal last_activity
        try:
            while True:
                await asyncio.sleep(10)
                if time.time() - last_activity > idle_timeout:
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

                if len(message_timestamps) >= max_messages_per_minute:
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
