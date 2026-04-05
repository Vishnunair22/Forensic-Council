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
from typing import Any, AsyncIterator

from fastapi import APIRouter, Depends, Request
from fastapi.responses import StreamingResponse

from core.auth import User, get_current_user
from core.structured_logging import get_logger

logger = get_logger(__name__)

router = APIRouter(prefix="/api/v1", tags=["sse"])


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

    # Create a queue to receive broadcasts
    queue: asyncio.Queue[dict[str, Any]] = asyncio.Queue(maxsize=100)

    # Register as a "pseudo-WebSocket" consumer
    class SSEConsumer:
        """Minimal consumer that puts messages into a queue."""

        def __init__(self, q: asyncio.Queue):
            self._queue = q

        async def send_json(self, data: dict) -> None:
            try:
                self._queue.put_nowait(data)
            except asyncio.QueueFull:
                pass  # Drop oldest — client is too slow

    consumer = SSEConsumer(queue)

    if session_id not in _websocket_connections:
        _websocket_connections[session_id] = []
    _websocket_connections[session_id].append(consumer)

    try:
        # Send initial connection event
        yield f"event: connected\ndata: {json.dumps({'type': 'CONNECTED', 'session_id': session_id})}\n\n"

        while True:
            # Check if client disconnected
            if await request.is_disconnected():
                break

            try:
                # Wait for events with timeout (send keepalive every 30s)
                msg = await asyncio.wait_for(queue.get(), timeout=30.0)
                yield f"data: {json.dumps(msg)}\n\n"
            except asyncio.TimeoutError:
                # Keepalive
                yield ": keepalive\n\n"

    finally:
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
