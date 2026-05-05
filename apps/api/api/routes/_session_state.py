"""
Session State & WebSocket Management
======================================

Manages active pipelines, WebSocket connections, background tasks,
and cached reports. Imported by investigation.py to keep route
handlers focused on request/response logic.
"""

from __future__ import annotations

import asyncio
import json
from datetime import UTC, datetime
from typing import Any

from api.schemas import BriefUpdate
from core.config import get_settings
from core.structured_logging import get_logger

logger = get_logger(__name__)
settings = get_settings()

# ── Module-level state stores ──────────────────────────────────────────────────
# WebSocket connections remain in-memory because they are tied to local sockets
_websocket_connections: dict[str, list] = {}

# Session metadata keys in Redis
SESSION_METADATA_KEY_PREFIX = "forensic:session:metadata:"
REPORT_CACHE_KEY_PREFIX = "forensic:session:report:"

# Agent metadata for WebSocket updates
AGENT_IDS = ["Agent1", "Agent2", "Agent3", "Agent4", "Agent5"]
AGENT_NAMES = {
    "Agent1": "Image Forensics",
    "Agent2": "Audio Forensics",
    "Agent3": "Object Detection",
    "Agent4": "Video Forensics",
    "Agent5": "Metadata Forensics",
}

# Session TTLs (IMPV-01)
_METADATA_TTL_SECONDS = 14400  # 4 Hours (Transient state)
_REPORT_TTL_SECONDS = 604800  # 7 Days (Hot cache for review)

# Replay Buffer (Race Condition Prevention)
REPLAY_BUFFER_KEY_PREFIX = "forensic:replay:"
REPLAY_BUFFER_MAX_LEN = 50
REPLAY_BUFFER_TTL = 300  # 5 minutes

# ── In-process state stores ────────────────────────────────────────────────────
# These must remain in-memory because they hold live Python objects (pipeline
# instances, asyncio Tasks) that cannot be serialised to Redis.
# _final_reports also serves as a 24-hour hot cache for completed reports.
_active_pipelines: dict[str, Any] = {}  # session_id → ForensicCouncilPipeline
_final_reports: dict[str, tuple[Any, datetime]] = {}  # session_id → (report, cached_at)
_active_tasks: dict[str, Any] = {}  # session_id → asyncio.Task


async def _get_redis():
    from core.persistence.redis_client import get_redis_client

    return await get_redis_client()


# ── Lifecycle ──────────────────────────────────────────────────────────────────


async def cleanup_connections() -> None:
    """Clean up local WebSocket connections on shutdown."""
    _websocket_connections.clear()
    logger.info("Local session state cleared")


# ── Active pipeline accessors ──────────────────────────────────────────────────


def set_active_pipeline(session_id: str, pipeline: Any) -> None:
    """Register a running pipeline instance."""
    _active_pipelines[session_id] = pipeline


def get_active_pipeline(session_id: str) -> Any | None:
    """Return the live pipeline object, or None if not found."""
    return _active_pipelines.get(session_id)


def get_all_active_pipelines() -> dict[str, Any]:
    """Return a snapshot of all active pipeline objects."""
    return dict(_active_pipelines)


def get_active_pipelines_count() -> int:
    """Return the number of currently running pipelines."""
    return len(_active_pipelines)


def remove_active_pipeline(session_id: str) -> None:
    """Remove a pipeline from the active set (non-raising)."""
    _active_pipelines.pop(session_id, None)


# ── Active task accessors ──────────────────────────────────────────────────────


def set_active_task(session_id: str, task: Any) -> None:
    """Track the asyncio.Task backing a session."""
    _active_tasks[session_id] = task


def pop_active_task(session_id: str) -> Any | None:
    """Remove and return the asyncio.Task for a session (non-raising)."""
    return _active_tasks.pop(session_id, None)


def evict_stale_sessions() -> None:
    """No-op placeholder — stale-report eviction is performed inline in run_investigation_task."""


# ── Pipeline/Session state accessors ──────────────────────────────────────────


async def set_active_pipeline_metadata(session_id: str, metadata: dict) -> None:
    """Store pipeline metadata (not the object) in Redis."""
    redis = await _get_redis()
    key = f"{SESSION_METADATA_KEY_PREFIX}{session_id}"
    await redis.set(key, metadata, ex=_METADATA_TTL_SECONDS)


async def get_active_pipeline_metadata(session_id: str) -> dict | None:
    """Retrieve pipeline metadata from Redis."""
    redis = await _get_redis()
    key = f"{SESSION_METADATA_KEY_PREFIX}{session_id}"
    return await redis.get_json(key)


# ── Report cache ──────────────────────────────────────────────────────────────


async def set_final_report(session_id: str, report: Any) -> None:
    """Cache final report in Redis with real creation timestamp."""
    redis = await _get_redis()
    key = f"{REPORT_CACHE_KEY_PREFIX}{session_id}"
    ts_key = f"{REPORT_CACHE_KEY_PREFIX}{session_id}:created_at"
    data = report.model_dump(mode="json") if hasattr(report, "model_dump") else report

    await redis.set(
        key,
        json.dumps(data, default=str),
        ex=_REPORT_TTL_SECONDS,
    )
    # Issue 9.2: Store the real creation timestamp alongside the report data
    await redis.set(ts_key, datetime.now(UTC).isoformat(), ex=_REPORT_TTL_SECONDS)


async def get_final_report(session_id: str) -> tuple[Any, datetime] | None:
    """Retrieve final report from Redis with real creation timestamp."""
    redis = await _get_redis()
    key = f"{REPORT_CACHE_KEY_PREFIX}{session_id}"
    ts_key = f"{REPORT_CACHE_KEY_PREFIX}{session_id}:created_at"
    data = await redis.get_json(key)
    if data:
        # Issue 9.2: Return the real creation timestamp instead of datetime.now()
        ts_raw = await redis.get(ts_key)
        if ts_raw:
            try:
                created_at = datetime.fromisoformat(ts_raw)
            except ValueError:
                created_at = datetime.now(UTC)
        else:
            created_at = datetime.now(UTC)
        return (data, created_at)
    return None


# ── WebSocket management ──────────────────────────────────────────────────────


def get_session_websockets(session_id: str) -> list:
    return _websocket_connections.get(session_id, [])


def register_websocket(session_id: str, websocket: Any) -> None:
    if session_id not in _websocket_connections:
        _websocket_connections[session_id] = []
    _websocket_connections[session_id].append(websocket)


def unregister_websocket(session_id: str, websocket: Any) -> None:
    if session_id in _websocket_connections:
        try:
            _websocket_connections[session_id].remove(websocket)
        except ValueError:
            pass


def clear_session_websockets(session_id: str) -> None:
    """Remove all WebSocket connections for a completed/terminated session."""
    _websocket_connections.pop(session_id, None)


async def broadcast_update(session_id: str, update: BriefUpdate) -> None:
    """
    Broadcast a WebSocket update.

    Issue 9.3: Dead WebSocket refs are automatically removed when send_json
    raises, preventing the connections dict from leaking closed sockets.
    """
    # 1. Send to local listeners (API process)
    if session_id in _websocket_connections:
        data = update.model_dump()
        dead: list = []
        for ws in _websocket_connections[session_id]:
            try:
                await ws.send_json(data)
            except Exception as e:
                logger.warning("Failed to send WebSocket message — marking dead", error=str(e))
                dead.append(ws)
        # Remove dead refs in a second pass to avoid mutating while iterating
        for ws in dead:
            unregister_websocket(session_id, ws)

    # 2. Publish to Redis for API/worker topologies.
    # Also write to Replay Buffer to prevent race conditions during subscriber startup.
    try:
        redis = await _get_redis()
        channel = f"forensic:updates:{session_id}"
        replay_key = f"{REPLAY_BUFFER_KEY_PREFIX}{session_id}"
        payload = json.dumps(update.model_dump())

        # Publish live
        await redis.client.publish(channel, payload)

        # Write to replay buffer (atomic capped list)
        async with redis.client.pipeline(transaction=True) as pipe:
            pipe.rpush(replay_key, payload)
            pipe.ltrim(replay_key, -REPLAY_BUFFER_MAX_LEN, -1)
            pipe.expire(replay_key, REPLAY_BUFFER_TTL)
            await pipe.execute()

    except Exception as e:
        logger.debug("Redis update broadcast failed", error=str(e))


# ── Batched WebSocket broadcasting ─────────────────────────────────────────────
# Accumulates updates per session and flushes them in a single batch at a
# configurable interval (default 1s) to reduce Redis I/O at scale.
_batch_buffers: dict[str, list[dict]] = {}
_batch_timers: dict[str, Any] = {}
BATCH_FLUSH_INTERVAL = 1.0  # seconds


async def _flush_batch(session_id: str) -> None:
    """Flush accumulated updates for a session in a single WebSocket frame."""
    updates = _batch_buffers.pop(session_id, [])
    _batch_timers.pop(session_id, None)
    if not updates:
        return
    if session_id not in _websocket_connections:
        return
    # Send as a single batch frame instead of N individual frames
    payload = {"type": "BATCH", "session_id": session_id, "updates": updates}
    dead: list = []
    for ws in _websocket_connections[session_id]:
        try:
            await ws.send_json(payload)
        except Exception as e:
            logger.warning("Failed to send batched WebSocket message — marking dead", error=str(e))
            dead.append(ws)
    # Remove dead refs in a second pass to avoid mutating while iterating
    for ws in dead:
        unregister_websocket(session_id, ws)


async def broadcast_update_batched(session_id: str, update: BriefUpdate) -> None:
    """
    Queue a WebSocket update for batched delivery.

    Updates are accumulated and flushed every BATCH_FLUSH_INTERVAL seconds.
    This reduces per-connection I/O from O(updates) to O(flushes) — critical
    at scale with 100+ concurrent users.
    """
    _batch_buffers.setdefault(session_id, []).append(update.model_dump())
    if session_id not in _batch_timers:

        async def _delayed_flush():
            await asyncio.sleep(BATCH_FLUSH_INTERVAL)
            await _flush_batch(session_id)

        _batch_timers[session_id] = asyncio.create_task(_delayed_flush())
