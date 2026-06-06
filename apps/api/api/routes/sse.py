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
from fastapi.exceptions import HTTPException
from fastapi.responses import StreamingResponse

from core.auth import User, get_current_user
from core.config import get_settings
from core.structured_logging import get_logger

logger = get_logger(__name__)

router = APIRouter(prefix="/api/v1", tags=["sse"])

CRITICAL_TYPES = frozenset(
    {"PIPELINE_COMPLETE", "ERROR", "PIPELINE_PAUSED", "HITL_CHECKPOINT", "PIPELINE_QUARANTINED", "STREAM_ERROR"}
)


async def _event_generator(
    session_id: str,
    request: Request,
    last_event_id: str | None = None,
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

    # Register AFTER entering the try block so the finally cleanup always runs,
    # even when the Redis setup phase raises before the try is entered.
    settings = get_settings()
    dedicated_redis = None
    pubsub = None
    # Tracks how many buffered events precede the client's reconnect point.
    # Set inside the Redis block if Last-Event-ID is provided; defaults to 0.
    # Register consumer inside this try block so the finally cleanup runs
    # even if Redis setup fails — prevents a permanent leak in _websocket_connections.
    if session_id not in _websocket_connections:
        _websocket_connections[session_id] = []
    _websocket_connections[session_id].append(consumer)

    replay_start = 0
    redis_task: asyncio.Task | None = None  # initialized here so finally block is always safe
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

            # 2. Replay any missed messages from the buffer.
            # Each buffered entry is stored as a JSON string (the raw message).
            # When the client supplies a Last-Event-ID header we skip every
            # buffered entry up to and including that position index so the
            # client receives only the delta it missed.
            dedicated_redis_any: Any = dedicated_redis
            replay_messages = await dedicated_redis_any.lrange(replay_key, 0, -1)
            replayed_types: set[str] = set()

            # Determine the replay start position from Last-Event-ID.
            # We encode event IDs as "<session_id>:<zero-based-index>".
            replay_start = 0
            if last_event_id and last_event_id.startswith(f"{session_id}:"):
                try:
                    last_idx = int(last_event_id.split(":", 1)[1])
                    replay_start = last_idx + 1
                except (ValueError, IndexError):
                    replay_start = 0

            if replay_messages:
                for idx, msg_json in enumerate(replay_messages):
                    if idx < replay_start:
                        continue
                    try:
                        data = json.loads(msg_json)
                        await consumer.send_json(data)
                        replayed_types.add(data.get("type", ""))
                    except Exception as replay_error:
                        logger.debug(
                            "Failed to replay SSE update",
                            session_id=session_id,
                            error=str(replay_error),
                        )

            # 3. If the replay buffer didn't include a terminal event, check
            # Redis metadata — the pipeline may have completed before the
            # replay key was populated (e.g. on a fast investigation or after
            # a Redis flush). This path works across worker/API processes
            # because get_active_pipeline_metadata reads from Redis, not
            # from the in-process _final_reports dict.
            terminal_replayed = bool(replayed_types & CRITICAL_TYPES)
            if not terminal_replayed:
                from api.routes._session_state import get_active_pipeline_metadata

                meta = await get_active_pipeline_metadata(session_id)
                if isinstance(meta, dict):
                    status = meta.get("status")
                    if status in ("completed", "error"):
                        event_type = "PIPELINE_COMPLETE" if status == "completed" else "ERROR"
                        await consumer.send_json(
                            {
                                "type": event_type,
                                "session_id": session_id,
                                "message": meta.get("brief", ""),
                                "data": {"status": status, "synthesized_from_metadata": True},
                            }
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
                    logger.error(
                        "Redis pub/sub listener dropped — injecting STREAM_ERROR so client reconnects",
                        session_id=session_id,
                        error=str(exc),
                    )
                    await consumer.send_json(
                        {
                            "type": "STREAM_ERROR",
                            "session_id": session_id,
                            "message": "Live stream interrupted. Reconnect to resume.",
                        }
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

        # Track a per-stream event counter so the client can resume from
        # the exact position after a reconnect via the Last-Event-ID header.
        # IDs are scoped per session: "<session_id>:<monotonic_index>".
        # Starts at replay_start so IDs stay globally monotonic across reconnects.
        _event_index = replay_start

        while True:
            # Check if client disconnected
            if await request.is_disconnected():
                break

            try:
                # Wait for events with timeout (send keepalive every 15s for Caddy)
                msg = await asyncio.wait_for(queue.get(), timeout=15.0)
                event_id = f"{session_id}:{_event_index}"
                _event_index += 1
                yield f"id: {event_id}\ndata: {json.dumps(msg)}\n\n"
            except TimeoutError:
                # Keepalive
                yield ": keepalive\n\n"
    except Exception as stream_exc:
        logger.error("SSE event generator error", session_id=session_id, error=str(stream_exc))
        try:
            yield f"event: error\ndata: {json.dumps({'type': 'ERROR', 'message': str(stream_exc)})}\n\n"
        except Exception as yield_err:
            logger.warning("Failed to yield SSE error event", error=str(yield_err))
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
    Supports the Last-Event-ID header for resume-from-disconnect replay.
    """
    # Read Last-Event-ID header for reconnect replay support
    last_event_id: str | None = request.headers.get("Last-Event-ID") or request.headers.get("last-event-id")
    try:
        from api.routes._authz import assert_session_access
        await assert_session_access(session_id, current_user)
    except HTTPException as auth_exc:
        # Return a plain JSON error — not a StreamingResponse. The browser
        # EventSource API fires onerror on any non-200 status without exposing
        # the status code to JS; returning a StreamingResponse with a 403 body
        # causes infinite reconnect loops. A JSON 4xx response is detectable
        # by the client's fetch-based pre-check before opening EventSource.
        from fastapi.responses import JSONResponse as _JSONResponse
        return _JSONResponse(
            status_code=auth_exc.status_code,
            content={"detail": str(auth_exc.detail)},
        )

    return StreamingResponse(
        _event_generator(session_id, request, last_event_id=last_event_id),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache, no-transform",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",  # Disable nginx/Caddy buffering
            "Transfer-Encoding": "chunked",
        },
    )
