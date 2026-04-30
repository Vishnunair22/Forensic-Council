"""
Server-Sent Events (SSE) Progress Endpoint
============================================

Provides a lightweight SSE endpoint for real-time investigation progress
updates. Unlike WebSocket, SSE:
- Works through all proxies and CDNs
- No reconnection complexity
- Automatic browser reconnection
- Works with HttpOnly cookies natively
"""

from __future__ import annotations

import asyncio
import json
from collections.abc import AsyncIterator
from typing import Any

from fastapi import APIRouter, Depends, Request
from fastapi.responses import StreamingResponse

from core.auth import User, get_current_user
from core.config import get_settings
from core.structured_logging import get_logger

logger = get_logger(__name__)

router = APIRouter(prefix="/api/v1", tags=["sse"])

CRITICAL_TYPES = frozenset(
    {"PIPELINE_COMPLETE", "ERROR", "PIPELINE_PAUSED", "HITL_CHECKPOINT", "PIPELINE_QUARANTINED"}
)


async def _event_generator(
    session_id: str,
    request: Request,
) -> AsyncIterator[str]:
    """
    Generate SSE events for a session.

    Listens to the same broadcast_update channel as WebSocket clients
    and yields Server-Sent Events formatted strings.
    """
    # Import the shared WebSocket connections registry
    from api.routes._session_state import _websocket_connections

    # Increase queue size from 100 → 500
    queue: asyncio.Queue[dict[str, Any]] = asyncio.Queue(maxsize=500)

    # Register as a "pseudo-WebSocket" consumer
    class SSEConsumer:
        """Priority-aware SSE consumer. Never drops critical terminal events."""

        def __init__(self, q: asyncio.Queue):
            self._queue = q

        async def send_json(self, data: dict) -> None:
            is_critical = data.get("type") in CRITICAL_TYPES
            if not self._queue.full():
                self._queue.put_nowait(data)
                return
            if is_critical:
                # Evict oldest non-critical item to make room
                tmp: list = []
                while not self._queue.empty():
                    tmp.append(self._queue.get_nowait())
                drop_idx = next(
                    (i for i, m in enumerate(tmp) if m.get("type") not in CRITICAL_TYPES),
                    None,
                )
                if drop_idx is not None:
                    tmp.pop(drop_idx)
                for item in tmp:
                    try:
                        self._queue.put_nowait(item)
                    except asyncio.QueueFull:
                        break
                try:
                    self._queue.put_nowait(data)
                except asyncio.QueueFull:
                    pass  # queue is entirely critical messages; accept the drop
            # else: non-critical dropped — safe

    consumer = SSEConsumer(queue)

    if session_id not in _websocket_connections:
        _websocket_connections[session_id] = []
    _websocket_connections[session_id].append(consumer)

    # When using the Redis worker topology the pipeline runs in a separate
    # container. broadcast_update() in the worker finds no local SSE consumers
    # and publishes to Redis pub/sub instead. Subscribe here to bridge those
    # worker-published updates into this SSE stream.
    redis_task: asyncio.Task | None = None
    pubsub = None

    settings = get_settings()
    dedicated_redis = None
    pubsub = None
    if settings.use_redis_worker:
        try:
            from redis.asyncio import Redis

            dedicated_redis = Redis(
                host=settings.redis_host,
                port=settings.redis_port,
                db=settings.redis_db,
                password=settings.redis_password,
                socket_timeout=None,  # No timeout for pub/sub listening
                socket_connect_timeout=5,
                socket_keepalive=True,
                decode_responses=True,
            )
            pubsub = dedicated_redis.pubsub()
            channel = f"forensic:updates:{session_id}"
            replay_key = f"forensic:replay:{session_id}"

            # 1. Subscribe first (captures all future messages)
            await pubsub.subscribe(channel)

            # 2. Replay any missed messages from the buffer
            replay_messages = await dedicated_redis.lrange(replay_key, 0, -1)
            if replay_messages:
                for msg_json in replay_messages:
                    try:
                        data = json.loads(msg_json)
                        await consumer.send_json(data)
                    except Exception as replay_error:
                        logger.debug(
                            "Failed to replay SSE update",
                            session_id=session_id,
                            error=str(replay_error),
                        )

            async def _redis_listener(ps, _channel: str) -> None:
                try:
                    async for message in ps.listen():
                        if message["type"] == "message":
                            try:
                                data = json.loads(message["data"])
                                await consumer.send_json(data)
                            except Exception as message_error:
                                logger.debug(
                                    "Failed to forward SSE Redis message",
                                    session_id=session_id,
                                    error=str(message_error),
                                )
                except asyncio.CancelledError:
                    pass
                except Exception as exc:
                    logger.debug(
                        "Redis pub/sub listener error",
                        session_id=session_id,
                        error=str(exc),
                    )

            redis_task = asyncio.create_task(_redis_listener(pubsub, channel))
            logger.debug("Redis pub/sub subscriber started", session_id=session_id, channel=channel)
        except Exception as exc:
            logger.warning(
                "Could not start Redis pub/sub subscriber",
                session_id=session_id,
                error=str(exc),
            )

    try:
        # Send initial connection event with retry hint
        yield f"retry: 2000\nevent: connected\ndata: {json.dumps({'type': 'CONNECTED', 'session_id': session_id})}\n\n"

        while True:
            # Check if client disconnected
            if await request.is_disconnected():
                break

            try:
                # Wait for events with timeout (send keepalive every 15s for Caddy)
                msg = await asyncio.wait_for(queue.get(), timeout=15.0)
                yield f"data: {json.dumps(msg)}\n\n"
            except TimeoutError:
                # Keepalive
                yield ": keepalive\n\n"

    finally:
        # Cancel Redis pub/sub listener
        if redis_task is not None:
            redis_task.cancel()
            try:
                await redis_task
            except asyncio.CancelledError:
                pass
            except Exception as task_error:
                logger.debug(
                    "SSE Redis listener shutdown failed",
                    session_id=session_id,
                    error=str(task_error),
                )
        if pubsub is not None:
            try:
                await pubsub.unsubscribe()
                await pubsub.aclose()
            except Exception as pubsub_error:
                logger.debug(
                    "SSE pubsub shutdown failed",
                    session_id=session_id,
                    error=str(pubsub_error),
                )
        if dedicated_redis is not None:
            try:
                await dedicated_redis.aclose()
            except Exception as redis_close_error:
                logger.debug(
                    "SSE Redis client shutdown failed",
                    session_id=session_id,
                    error=str(redis_close_error),
                )

        # Unregister consumer
        try:
            _websocket_connections.get(session_id, []).remove(consumer)
        except ValueError:
            pass


@router.get("/sessions/{session_id}/progress")
async def sse_progress(
    session_id: str,
    request: Request,
    current_user: User = Depends(get_current_user),
):
    """
    SSE endpoint for real-time investigation progress.

    Returns a StreamingResponse with text/event-stream content type.
    Browser EventSource API automatically reconnects on disconnection.

    Usage (frontend):
        const es = new EventSource(`/api/v1/sessions/${sessionId}/progress`);
        es.onmessage = (e) => {
            const data = JSON.parse(e.data);
            // Handle AGENT_UPDATE, AGENT_COMPLETE, etc.
        };
    """
    return StreamingResponse(
        _event_generator(session_id, request),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",  # Disable nginx buffering
        },
    )
