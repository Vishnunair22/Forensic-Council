"""
Sessions Routes
================

Routes for managing investigation sessions.
"""

from typing import List

from fastapi import APIRouter, HTTPException, WebSocket, WebSocketDisconnect

from api.routes.investigation import _active_pipelines, _active_tasks, _websocket_connections, register_websocket, unregister_websocket
from api.schemas import SessionInfo

router = APIRouter(prefix="/api/v1/sessions", tags=["sessions"])


@router.get("", response_model=List[SessionInfo])
async def list_sessions():
    """List all active sessions."""
    sessions = []
    for session_id, pipeline in _active_pipelines.items():
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
async def terminate_session(session_id: str):
    """Terminate a running session."""
    if session_id not in _active_pipelines:
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

    del _active_pipelines[session_id]

    return {"status": "terminated", "session_id": session_id}


@router.websocket("/{session_id}/live")
async def live_updates(websocket: WebSocket, session_id: str):
    """WebSocket endpoint for live investigation updates."""
    # S4: Validate session exists before accepting
    if session_id not in _active_pipelines:
        await websocket.close(code=4004, reason="Session not found")
        return

    await websocket.accept()

    # Register this connection
    register_websocket(session_id, websocket)

    try:
        # Send welcome message
        await websocket.send_json({
            "type": "AGENT_UPDATE",
            "session_id": session_id,
            "message": "Connected to live updates",
            "data": {"status": "connected"}
        })

        # Keep connection alive and handle incoming messages
        while True:
            # Wait for any message (could be used for heartbeats or commands)
            data = await websocket.receive_text()
            # For now, we just keep the connection alive

    except WebSocketDisconnect:
        pass
    finally:
        unregister_websocket(session_id, websocket)
