"""
Session State & WebSocket Management
======================================

Manages active pipelines, WebSocket connections, background tasks,
and cached reports. Imported by investigation.py to keep route
handlers focused on request/response logic.
"""
from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from typing import Any, Optional

from core.config import get_settings
from core.structured_logging import get_logger
from api.schemas import BriefUpdate

logger = get_logger(__name__)
settings = get_settings()

# ── Module-level state stores ──────────────────────────────────────────────────
# Lazy-imported to avoid circular imports — ForensicCouncilPipeline is set
# via set_pipeline_class() from investigation.py at module load time.
_active_pipelines: dict[str, Any] = {}
_websocket_connections: dict[str, list] = {}
_active_tasks: dict[str, asyncio.Task] = {}
_final_reports: dict[str, tuple[Any, datetime]] = {}

# Agent metadata for WebSocket updates
AGENT_IDS = ["Agent1", "Agent2", "Agent3", "Agent4", "Agent5"]
AGENT_NAMES = {
    "Agent1": "Image Forensics",
    "Agent2": "Audio Forensics",
    "Agent3": "Object Detection",
    "Agent4": "Video Forensics",
    "Agent5": "Metadata Forensics",
}

# Session TTL
_SESSION_TTL_SECONDS = settings.session_ttl_hours * 3600


# ── Lifecycle ──────────────────────────────────────────────────────────────────

def cleanup_connections() -> None:
    """Clean up all WebSocket connections, tasks, and active pipelines on shutdown."""
    for sid, task in list(_active_tasks.items()):
        if not task.done():
            task.cancel()
            logger.info("Cancelled in-flight investigation task", session_id=sid)
    _active_tasks.clear()
    _websocket_connections.clear()
    _active_pipelines.clear()
    _final_reports.clear()


def evict_stale_sessions() -> None:
    """Remove completed sessions that have exceeded SESSION_TTL."""
    now = datetime.now(timezone.utc)
    stale = [
        sid for sid, (_, cached_at) in list(_final_reports.items())
        if (now - cached_at).total_seconds() > _SESSION_TTL_SECONDS
    ]
    for sid in stale:
        _final_reports.pop(sid, None)
        task = _active_tasks.get(sid)
        if task is None or task.done():
            _active_pipelines.pop(sid, None)
            _active_tasks.pop(sid, None)
            _websocket_connections.pop(sid, None)
    if stale:
        logger.info(f"Evicted {len(stale)} stale session(s) from memory")


# ── Pipeline accessors ────────────────────────────────────────────────────────

def get_active_pipelines_count() -> int:
    return len(_active_pipelines)

def get_active_pipeline(session_id: str) -> Optional[Any]:
    return _active_pipelines.get(session_id)

def get_all_active_pipelines() -> dict:
    return _active_pipelines.copy()

def set_active_pipeline(session_id: str, pipeline: Any) -> None:
    _active_pipelines[session_id] = pipeline

def remove_active_pipeline(session_id: str) -> None:
    _active_pipelines.pop(session_id, None)

def clear_active_pipelines() -> None:
    _active_pipelines.clear()
    _final_reports.clear()


# ── Task accessors ────────────────────────────────────────────────────────────

def set_active_task(session_id: str, task: asyncio.Task) -> None:
    _active_tasks[session_id] = task

def pop_active_task(session_id: str) -> Optional[asyncio.Task]:
    return _active_tasks.pop(session_id, None)


# ── Report cache ──────────────────────────────────────────────────────────────

def set_final_report(session_id: str, report: Any) -> None:
    _final_reports[session_id] = (report, datetime.now(timezone.utc))

def get_final_report(session_id: str) -> Optional[tuple[Any, datetime]]:
    return _final_reports.get(session_id)


# ── WebSocket management ──────────────────────────────────────────────────────

def get_session_websockets(session_id: str) -> list:
    return _websocket_connections.get(session_id, [])

def clear_session_websockets(session_id: str) -> None:
    _websocket_connections.pop(session_id, None)

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

async def broadcast_update(session_id: str, update: BriefUpdate) -> None:
    """Broadcast a WebSocket update to all connected clients."""
    if session_id in _websocket_connections:
        for ws in _websocket_connections[session_id]:
            try:
                await ws.send_json(update.model_dump())
            except Exception as e:
                logger.warning(f"Failed to send WebSocket message: {e}")


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
    for ws in _websocket_connections[session_id]:
        try:
            await ws.send_json(payload)
        except Exception as e:
            logger.warning(f"Failed to send batched WebSocket message: {e}")


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
