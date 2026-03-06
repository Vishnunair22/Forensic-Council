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
from api.routes.investigation import get_all_active_pipelines, get_active_pipeline, remove_active_pipeline, _active_tasks, _websocket_connections, register_websocket, unregister_websocket
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
    """WebSocket endpoint for live investigation updates. Requires authentication via AUTH message after connection."""
    # Validate session exists BEFORE accepting to prevent session enumeration attacks
    if not get_active_pipeline(session_id):
        await websocket.close(code=4004, reason="Session not found")
        return

    # First accept the connection
    # Use subprotocol to acknowledge the client's protocol request
    await websocket.accept(subprotocol="forensic-v1")

    # Wait for authentication message from client with timeout
    try:
        auth_message = await asyncio.wait_for(websocket.receive_text(), timeout=10.0)
        auth_data = json.loads(auth_message)
        
        if auth_data.get("type") != "AUTH":
            await websocket.send_json({
                "type": "ERROR",
                "session_id": session_id,
                "message": "Missing authentication message",
                "agent_id": None,
                "agent_name": None
            })
            await websocket.close(code=4001, reason="Missing authentication message")
            return
            
        token = auth_data.get("token")
        if not token:
            await websocket.send_json({
                "type": "ERROR",
                "session_id": session_id,
                "message": "Missing token",
                "agent_id": None,
                "agent_name": None
            })
            await websocket.close(code=4001, reason="Missing token")
            return
            
        # Verify the token
        try:
            token_data = await decode_token(token)
        except Exception:
            await websocket.send_json({
                "type": "ERROR",
                "session_id": session_id,
                "message": "Invalid or expired token",
                "agent_id": None,
                "agent_name": None
            })
            await websocket.close(code=4001, reason="Invalid or expired token")
            return
            
    except asyncio.TimeoutError:
        await websocket.send_json({
            "type": "ERROR",
            "session_id": session_id,
            "message": "Authentication timeout",
            "agent_id": None,
            "agent_name": None
        })
        await websocket.close(code=4001, reason="Authentication timeout")
        return
    except json.JSONDecodeError:
        await websocket.send_json({
            "type": "ERROR",
            "session_id": session_id,
            "message": "Invalid JSON in authentication message",
            "agent_id": None,
            "agent_name": None
        })
        await websocket.close(code=4001, reason="Invalid JSON in authentication message")
        return
    except Exception:
        await websocket.send_json({
            "type": "ERROR",
            "session_id": session_id,
            "message": "Authentication failed",
            "agent_id": None,
            "agent_name": None
        })
        await websocket.close(code=4001, reason="Authentication failed")
        return

    # Register this connection
    register_websocket(session_id, websocket)

    try:
        # Send welcome message with all required fields
        await websocket.send_json({
            "type": "AGENT_UPDATE",
            "session_id": session_id,
            "agent_id": None,
            "agent_name": None,
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
