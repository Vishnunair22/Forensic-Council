"""
Sessions Routes
===============

Routes for managing investigation sessions.
"""

from typing import List

from fastapi import APIRouter, Depends, HTTPException, WebSocket, WebSocketDisconnect

from core.auth import get_current_user, User, decode_token
from api.routes.investigation import _active_pipelines, _active_tasks, _websocket_connections, register_websocket, unregister_websocket
from api.schemas import SessionInfo

router = APIRouter(prefix="/api/v1/sessions", tags=["sessions"])


@router.get("", response_model=List[SessionInfo])
async def list_sessions(current_user: User = Depends(get_current_user)):
    """List all active sessions. Requires authentication."""
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
async def terminate_session(session_id: str, current_user: User = Depends(get_current_user)):
    """Terminate a running session. Requires authentication."""
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
    """WebSocket endpoint for live investigation updates. Requires authentication via subprotocol."""
    # S4: Validate session exists before accepting
    if session_id not in _active_pipelines:
        await websocket.close(code=4004, reason="Session not found")
        return

    # Authenticate via subprotocol token
    # Expected subprotocol: "Bearer <token>"
    auth_header = websocket.headers.get("authorization", "")
    if not auth_header.startswith("Bearer "):
        await websocket.close(code=4001, reason="Missing or invalid authorization header")
        return
    
    token = auth_header[7:]  # Remove "Bearer " prefix
    
    # Verify the token before accepting the connection
    try:
        token_data = await decode_token(token)
    except Exception:
        await websocket.close(code=4001, reason="Invalid or expired token")
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
            "data": {"status": "connected", "user_id": token_data.user_id}
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
