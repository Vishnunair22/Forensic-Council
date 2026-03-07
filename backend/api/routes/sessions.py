"""
Sessions Routes
===============

Routes for managing investigation sessions.
"""

from typing import List
import asyncio
import json

from fastapi import APIRouter, Depends, HTTPException, WebSocket, WebSocketDisconnect

from core.auth import get_current_user, User, decode_token
from api.routes.investigation import (
    get_all_active_pipelines,
    get_active_pipeline,
    remove_active_pipeline,
    _active_tasks,
    _websocket_connections,
    register_websocket,
    unregister_websocket,
)
from api.schemas import SessionInfo

router = APIRouter(prefix="/api/v1/sessions", tags=["sessions"])


@router.get("", response_model=List[SessionInfo])
async def list_sessions(current_user: User = Depends(get_current_user)):
    """List all active sessions. Requires authentication."""
    sessions = []
    for session_id, pipeline in get_all_active_pipelines().items():
        status = "running" if not hasattr(pipeline, "_final_report") else "completed"
        session_info = SessionInfo(
            session_id=session_id,
            case_id=getattr(pipeline, "_case_id", "unknown"),
            status=status,
            started_at=getattr(pipeline, "_started_at", ""),
        )
        sessions.append(session_info)
    return sessions


@router.delete("/{session_id}")
async def terminate_session(session_id: str, current_user: User = Depends(get_current_user)):
    """Terminate a running session. Requires authentication."""
    if not get_active_pipeline(session_id):
        raise HTTPException(status_code=404, detail="Session not found")

    # Cancel the background task if still running
    task = _active_tasks.pop(session_id, None)
    if task and not task.done():
        task.cancel()

    # Close WebSocket connections
    if session_id in _websocket_connections:
        for ws in _websocket_connections[session_id]:
            try:
                await ws.close()
            except Exception:
                pass
        _websocket_connections[session_id] = []

    remove_active_pipeline(session_id)
    return {"status": "terminated", "session_id": session_id}


@router.websocket("/{session_id}/live")
async def live_updates(websocket: WebSocket, session_id: str):
    """
    WebSocket endpoint for live investigation updates.

    Auth: Client must send {"type": "AUTH", "token": "<jwt>"} within 10 s of
    connecting.  The pipeline session must exist — we poll briefly to handle
    the small window between POST /investigate returning and the WS arriving.
    """
    # ── 1. Wait for the pipeline to be registered (handles edge-case race) ──
    # The HTTP /investigate handler registers the pipeline *before* returning
    # the session_id to the client, so this should resolve almost immediately.
    for _ in range(20):  # up to 2 s
        if get_active_pipeline(session_id):
            break
        await asyncio.sleep(0.1)

    # ── 2. Accept the WebSocket BEFORE checking — required by the WS protocol.
    #       Closing before accept produces a broken handshake on many clients.
    await websocket.accept(subprotocol="forensic-v1")

    if not get_active_pipeline(session_id):
        await websocket.send_json({
            "type": "ERROR",
            "session_id": session_id,
            "message": "Session not found",
            "agent_id": None,
            "agent_name": None,
            "data": None,
        })
        await websocket.close(code=4004, reason="Session not found")
        return

    # ── 3. Authenticate via post-connect AUTH message ──────────────────────
    try:
        auth_raw = await asyncio.wait_for(websocket.receive_text(), timeout=10.0)
        auth_data = json.loads(auth_raw)

        if auth_data.get("type") != "AUTH":
            await websocket.send_json({
                "type": "ERROR",
                "session_id": session_id,
                "message": "First message must be AUTH",
                "agent_id": None,
                "agent_name": None,
                "data": None,
            })
            await websocket.close(code=4001, reason="Missing AUTH message")
            return

        token = auth_data.get("token")
        if not token:
            await websocket.send_json({
                "type": "ERROR",
                "session_id": session_id,
                "message": "Missing token in AUTH message",
                "agent_id": None,
                "agent_name": None,
                "data": None,
            })
            await websocket.close(code=4001, reason="Missing token")
            return

        try:
            token_data = await decode_token(token)
        except Exception:
            await websocket.send_json({
                "type": "ERROR",
                "session_id": session_id,
                "message": "Invalid or expired token",
                "agent_id": None,
                "agent_name": None,
                "data": None,
            })
            await websocket.close(code=4001, reason="Invalid token")
            return

    except asyncio.TimeoutError:
        await websocket.send_json({
            "type": "ERROR",
            "session_id": session_id,
            "message": "Authentication timeout",
            "agent_id": None,
            "agent_name": None,
            "data": None,
        })
        await websocket.close(code=4001, reason="Auth timeout")
        return
    except (json.JSONDecodeError, Exception):
        await websocket.send_json({
            "type": "ERROR",
            "session_id": session_id,
            "message": "Authentication failed",
            "agent_id": None,
            "agent_name": None,
            "data": None,
        })
        await websocket.close(code=4001, reason="Auth error")
        return

    # ── 4. Register and send welcome ──────────────────────────────────────
    register_websocket(session_id, websocket)

    try:
        # Welcome message — the client resolves its "connected" promise on this.
        await websocket.send_json({
            "type": "CONNECTED",
            "session_id": session_id,
            "agent_id": None,
            "agent_name": None,
            "message": "Connected to live updates",
            "data": {"status": "connected", "user_id": token_data.user_id},
        })

        # Keep connection alive; client may send heartbeat pings
        while True:
            await websocket.receive_text()

    except WebSocketDisconnect:
        pass
    except Exception:
        pass
    finally:
        unregister_websocket(session_id, websocket)
