"""
Sessions Routes
===============

Routes for managing investigation sessions.
"""

from typing import List, Optional
import asyncio
import json

from fastapi import APIRouter, Depends, HTTPException, WebSocket, WebSocketDisconnect

from core.auth import get_current_user, User, decode_token
from api.routes.investigation import (
    get_all_active_pipelines,
    get_active_pipeline,
    remove_active_pipeline,
    pop_active_task,
    get_session_websockets,
    clear_session_websockets,
    register_websocket,
    unregister_websocket,
)
from api.schemas import SessionInfo, ReportDTO, AgentFindingDTO
from api.routes.investigation import _final_reports, _active_tasks
from fastapi.responses import JSONResponse
from datetime import datetime, timezone

router = APIRouter(prefix="/api/v1/sessions", tags=["sessions"])


def _forensic_report_to_dto(report) -> ReportDTO:
    """
    Convert a ForensicReport Pydantic model to a serialization-safe ReportDTO.

    Handles UUID→str coercion and Optional[datetime]→ISO-string conversion
    explicitly so FastAPI never has to guess.
    """
    def _to_finding_dto(f: dict) -> AgentFindingDTO:
        return AgentFindingDTO(
            finding_id=str(f.get("finding_id", "")),
            agent_id=str(f.get("agent_id", "")),
            agent_name=str(f.get("agent_name", "")),
            finding_type=str(f.get("finding_type", "")),
            status=str(f.get("status", "CONFIRMED")),
            confidence_raw=float(f.get("confidence_raw", 0.0)),
            calibrated=bool(f.get("calibrated", False)),
            calibrated_probability=f.get("calibrated_probability"),
            court_statement=f.get("court_statement") or f.get("metadata", {}).get("court_statement"),
            robustness_caveat=bool(f.get("robustness_caveat", False)),
            robustness_caveat_detail=f.get("robustness_caveat_detail"),
            reasoning_summary=str(f.get("reasoning_summary", "")),
        )

    per_agent: dict = {}
    for agent_id, findings in (report.per_agent_findings or {}).items():
        per_agent[agent_id] = [_to_finding_dto(f) for f in findings]

    cross_modal = [_to_finding_dto(f) for f in (report.cross_modal_confirmed or [])]
    incomplete = [_to_finding_dto(f) for f in (report.incomplete_findings or [])]

    # TribunalCase objects need explicit serialization
    tribunal_resolved = []
    for item in (report.tribunal_resolved or []):
        if hasattr(item, "model_dump"):
            tribunal_resolved.append(item.model_dump(mode="json"))
        elif isinstance(item, dict):
            tribunal_resolved.append(item)

    contested = []
    for item in (report.contested_findings or []):
        if hasattr(item, "model_dump"):
            contested.append(item.model_dump(mode="json"))
        elif isinstance(item, dict):
            contested.append(item)

    signed_utc_str: Optional[str] = None
    if report.signed_utc is not None:
        if hasattr(report.signed_utc, "isoformat"):
            signed_utc_str = report.signed_utc.isoformat()
        else:
            signed_utc_str = str(report.signed_utc)

    return ReportDTO(
        report_id=str(report.report_id),
        session_id=str(report.session_id),
        case_id=report.case_id,
        executive_summary=report.executive_summary,
        per_agent_findings=per_agent,
        cross_modal_confirmed=cross_modal,
        contested_findings=contested,
        tribunal_resolved=tribunal_resolved,
        incomplete_findings=incomplete,
        uncertainty_statement=report.uncertainty_statement,
        cryptographic_signature=report.cryptographic_signature or "",
        report_hash=report.report_hash or "",
        signed_utc=signed_utc_str,
    )


@router.get("", response_model=List[SessionInfo])
async def list_sessions(current_user: User = Depends(get_current_user)):
    """List all active sessions. Requires authentication."""
    sessions = []
    for session_id, pipeline in get_all_active_pipelines().items():
        final_report = getattr(pipeline, "_final_report", None)
        error = getattr(pipeline, "_error", None)
        if final_report is not None:
            status = "completed"
        elif error:
            status = "error"
        else:
            status = "running"
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
    task = pop_active_task(session_id)
    if task and not task.done():
        task.cancel()

    # Close WebSocket connections
    for ws in get_session_websockets(session_id):
        try:
            await ws.close()
        except Exception:
            pass
    clear_session_websockets(session_id)

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


# ============================================================================
# REPORT ENDPOINT - Fetch final report for results page
# ============================================================================

@router.get("/{session_id}/report", response_model=ReportDTO)
async def get_session_report(
    session_id: str,
    current_user: User = Depends(get_current_user),
):
    """
    Get the final investigation report.

    Returns the completed report with all agent findings and arbiter synthesis.
    Used by the frontend results page to display the final analysis.
    """
    pipeline = get_active_pipeline(session_id)

    if not pipeline:
        # Check if we have a cached report
        if session_id in _final_reports:
            report, cached_time = _final_reports[session_id]
            # Return cached report if still valid (within 24 hours)
            if (datetime.now(timezone.utc) - cached_time).total_seconds() < 86400:
                return _forensic_report_to_dto(report)
            else:
                del _final_reports[session_id]

        raise HTTPException(
            status_code=404,
            detail=f"No investigation found for session {session_id}"
        )

    # Check if pipeline has completed
    report = getattr(pipeline, '_final_report', None)
    if not report:
        # Check if still running
        task = _active_tasks.get(session_id)
        if task and not task.done():
            return JSONResponse(
                status_code=202,
                content={
                    "status": "in_progress",
                    "session_id": session_id,
                    "message": "Investigation still in progress"
                }
            )

        # Check for error
        error = getattr(pipeline, '_error', None)
        if error:
            raise HTTPException(
                status_code=500,
                detail=f"Investigation failed: {error}"
            )

        raise HTTPException(
            status_code=404,
            detail="Report not yet available"
        )

    # Cache the raw report object and return the DTO
    _final_reports[session_id] = (report, datetime.now(timezone.utc))

    return _forensic_report_to_dto(report)


# ============================================================================
# STUB ENDPOINTS - Called by frontend, return graceful empty responses
# ============================================================================

@router.get("/{session_id}/brief/{agent_id}")
async def get_agent_brief(
    session_id: str,
    agent_id: str,
    current_user: User = Depends(get_current_user),
):
    """Return the agent's brief text if available, or an empty brief."""
    pipeline = get_active_pipeline(session_id)
    if not pipeline:
        if session_id not in _final_reports:
            raise HTTPException(status_code=404, detail="Session not found")
    return {"brief": ""}


@router.get("/{session_id}/checkpoints")
async def get_session_checkpoints(
    session_id: str,
    current_user: User = Depends(get_current_user),
):
    """Return any pending HITL checkpoints for the session."""
    pipeline = get_active_pipeline(session_id)
    if not pipeline:
        if session_id not in _final_reports:
            raise HTTPException(status_code=404, detail="Session not found")
    return []


