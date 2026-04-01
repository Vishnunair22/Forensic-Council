"""
Sessions Routes
===============

Routes for managing investigation sessions.
"""

from typing import List, Optional
import asyncio

from fastapi import APIRouter, Depends, HTTPException, WebSocket, WebSocketDisconnect

from core.auth import get_current_user, User, decode_token
from core.structured_logging import get_logger
from api.routes.investigation import (
    get_all_active_pipelines,
    get_active_pipeline,
    remove_active_pipeline,
    pop_active_task,
    get_session_websockets,
    clear_session_websockets,
    register_websocket,
    unregister_websocket,
    _assign_severity_tier,
)
from api.schemas import SessionInfo, ReportDTO, AgentFindingDTO
from api.routes.investigation import _final_reports, _active_tasks
from fastapi.responses import JSONResponse
from datetime import datetime, timezone

router = APIRouter(prefix="/api/v1/sessions", tags=["sessions"])
logger = get_logger(__name__)


def _forensic_report_to_dto(report) -> ReportDTO:
    """
    Convert a ForensicReport Pydantic model to a serialization-safe ReportDTO.

    Handles UUID→str coercion and Optional[datetime]→ISO-string conversion
    explicitly so FastAPI never has to guess.

    Also normalises findings so that:
    - findings tagged with metadata.analysis_phase are preserved
    - stub/no-op findings (zero reasoning_summary and no tool output) are filtered
    - per_agent_findings only includes agents with at least 1 real finding
    """
    def _as_dict(f) -> dict:
        """Convert finding to dict — handles both Pydantic models and plain dicts."""
        if isinstance(f, dict):
            return f
        if hasattr(f, "model_dump"):
            return f.model_dump(mode="json")
        if hasattr(f, "__dict__"):
            return vars(f)
        return {}

    def _to_finding_dto(f) -> AgentFindingDTO:
        d = _as_dict(f)
        meta = d.get("metadata") or {}
        if isinstance(meta, str):
            # Shouldn't happen, but guard against accidental serialisation
            try:
                import json as _json
                meta = _json.loads(meta)
            except Exception:
                meta = {}
        dto = AgentFindingDTO(
            finding_id=str(d.get("finding_id", "")),
            agent_id=str(d.get("agent_id", "")),
            agent_name=str(d.get("agent_name", d.get("agent_id", ""))),
            finding_type=str(d.get("finding_type", "Unknown")),
            status=str(d.get("status", "CONFIRMED")),
            confidence_raw=float(d.get("confidence_raw") or 0.0),
            calibrated=bool(d.get("calibrated", False)),
            calibrated_probability=d.get("raw_confidence_score") or d.get("calibrated_probability"),
            raw_confidence_score=d.get("raw_confidence_score") or d.get("calibrated_probability"),
            calibration_status=str(d.get("calibration_status", "UNCALIBRATED")),
            court_statement=d.get("court_statement") or meta.get("court_statement"),
            robustness_caveat=bool(d.get("robustness_caveat", False)),
            robustness_caveat_detail=d.get("robustness_caveat_detail"),
            reasoning_summary=str(d.get("reasoning_summary") or ""),
            metadata=meta if meta else None,
        )
        dto.severity_tier = _assign_severity_tier(d)
        return dto

    def _is_real_finding(f) -> bool:
        """Filter out pure no-op placeholder findings."""
        d = _as_dict(f)
        summary = str(d.get("reasoning_summary") or "")
        ftype = str(d.get("finding_type") or "")
        # Skip entries that are clearly empty placeholders
        if not summary and not ftype:
            return False
        # Skip "file type not applicable" stubs from unsupported agents
        if ftype.lower() in ("file type not applicable", "format not supported"):
            return False
        return True

    per_agent: dict = {}
    for agent_id, findings in (report.per_agent_findings or {}).items():
        real = [_to_finding_dto(f) for f in findings if _is_real_finding(f)]
        if real:
            per_agent[agent_id] = real

    cross_modal = [_to_finding_dto(f) for f in (report.cross_modal_confirmed or []) if _is_real_finding(f)]
    incomplete = [_to_finding_dto(f) for f in (report.incomplete_findings or []) if _is_real_finding(f)]

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
        executive_summary=report.executive_summary or "",
        per_agent_findings=per_agent,
        per_agent_metrics=getattr(report, "per_agent_metrics", {}) or {},
        per_agent_analysis=getattr(report, "per_agent_analysis", {}) or {},
        overall_confidence=getattr(report, "overall_confidence", 0.0) or 0.0,
        overall_error_rate=getattr(report, "overall_error_rate", 0.0) or 0.0,
        overall_verdict=getattr(report, "overall_verdict", "REVIEW REQUIRED") or "REVIEW REQUIRED",
        cross_modal_confirmed=cross_modal,
        contested_findings=contested,
        tribunal_resolved=tribunal_resolved,
        incomplete_findings=incomplete,
        uncertainty_statement=report.uncertainty_statement or "",
        cryptographic_signature=report.cryptographic_signature or "",
        report_hash=report.report_hash or "",
        signed_utc=signed_utc_str,
        verdict_sentence=getattr(report, "verdict_sentence", "") or "",
        key_findings=list(getattr(report, "key_findings", []) or []),
        reliability_note=getattr(report, "reliability_note", "") or "",
        manipulation_probability=float(getattr(report, "manipulation_probability", 0.0) or 0.0),
        confidence_min=float(getattr(report, "confidence_min", 0.0) or 0.0),
        confidence_max=float(getattr(report, "confidence_max", 0.0) or 0.0),
        confidence_std_dev=float(getattr(report, "confidence_std_dev", 0.0) or 0.0),
        applicable_agent_count=int(getattr(report, "applicable_agent_count", 0) or 0),
        skipped_agents=dict(getattr(report, "skipped_agents", {}) or {}),
        analysis_coverage_note=getattr(report, "analysis_coverage_note", "") or "",
        per_agent_summary=dict(getattr(report, "per_agent_summary", {}) or {}),
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
    # Higher timeout (12s) to handle slow disk/DB during initial ingestion.
    pipeline_found = False
    for i in range(120):  # up to 12 s
        if get_active_pipeline(session_id):
            pipeline_found = True
            break
        if i % 20 == 0 and i > 0:
            from core.structured_logging import get_logger as _gl
            _gl(__name__).info(f"WS for {session_id} still waiting for pipeline registration...")
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
    # ── 3. Authenticate via HttpOnly cookie in upgrade headers ─────────────
    # Cookies are automatically sent by the browser in the initial WS upgrade HTTP request.
    token = websocket.cookies.get("access_token")
    
    if not token:
        # Fallback to subprotocols for non-browser clients if needed
        for protocol in websocket.scope.get("subprotocols", []):
            if protocol.startswith("token."):
                token = protocol[6:]
                break

    if not token:
        await websocket.send_json({
            "type": "ERROR",
            "session_id": session_id,
            "message": "Authentication required. Missing access token.",
        })
        await websocket.close(code=4001, reason="Authentication required")
        return

    try:
        token_data = await decode_token(token)
    except Exception:
        await websocket.send_json({
            "type": "ERROR",
            "session_id": session_id,
            "message": "Invalid or expired session. Please log in again.",
        })
        await websocket.close(code=4001, reason="Invalid session")
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
    except asyncio.CancelledError:
        # Must re-raise CancelledError so asyncio task cancellation works correctly
        raise
    except Exception:
        pass
    finally:
        unregister_websocket(session_id, websocket)


# ============================================================================
# ARBITER STATUS ENDPOINT - Lightweight poll to track arbiter deliberation
# ============================================================================

@router.get("/{session_id}/arbiter-status")
async def get_arbiter_status(
    session_id: str,
    current_user: User = Depends(get_current_user),
):
    """
    Lightweight endpoint polled by the frontend while the arbiter compiles.
    Returns one of:
      - {status: running,   message: current step}
      - {status: complete,  report_id: ...}
      - {status: error,     message: ...}
      - {status: not_found}
    """
    pipeline = get_active_pipeline(session_id)

    # Report already in memory cache
    if session_id in _final_reports:
        report, _ = _final_reports[session_id]
        return {"status": "complete", "report_id": str(report.report_id)}

    if pipeline:
        report = getattr(pipeline, "_final_report", None)
        if report:
            return {"status": "complete", "report_id": str(report.report_id)}

        error = getattr(pipeline, "_error", None)
        if error:
            return {"status": "error", "message": error[:200]}

        evt = getattr(pipeline, "deep_analysis_decision_event", None)
        task = _active_tasks.get(session_id)
        task_running = task is not None and not task.done()

        if evt and not evt.is_set():
            return {"status": "running", "message": "Agents analysing evidence…"}

        # Post-decision: arbiter / final report (even if task handle missing or asyncio finished)
        live_step = getattr(pipeline, "_arbiter_step", "") or ""
        msg = (
            live_step
            if live_step
            else "Arbiter deliberating — synthesising findings…"
        )
        if task_running:
            return {"status": "running", "message": msg}
        if task is not None and task.done():
            # Task finished but _final_report and _error are both None —
            # the pipeline crashed without setting either sentinel.
            if not getattr(pipeline, "_final_report", None) and not getattr(pipeline, "_error", None):
                return {"status": "error", "message": "Pipeline terminated unexpectedly — no report generated."}
            return {"status": "running", "message": "Finalising report…"}
        return {"status": "running", "message": msg}

    # Try DB
    try:
        from core.session_persistence import get_session_persistence
        persistence = await get_session_persistence()
        db_row = await persistence.get_report(session_id)
        if db_row:
            s = db_row.get("status", "")
            if s == "completed":
                return {"status": "complete", "report_id": session_id}
            if s in ("running", "pending"):
                return {"status": "running", "message": "Investigation in progress..."}
            if s == "error":
                return {"status": "error", "message": db_row.get("error_message", "Unknown error")}
    except Exception:
        pass

    return {"status": "not_found"}


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

    Resolution order (most recent / most reliable first):
    1. In-memory pipeline object  — fastest; only available on the originating replica
    2. In-memory final_reports cache — survives pipeline eviction for up to 24 h
    3. PostgreSQL session_reports  — survives restarts and is visible to all replicas
    """
    pipeline = get_active_pipeline(session_id)

    # ── 1. In-memory pipeline ─────────────────────────────────────────────────
    if pipeline:
        report = getattr(pipeline, "_final_report", None)
        if report:
            _final_reports[session_id] = (report, datetime.now(timezone.utc))
            return _forensic_report_to_dto(report)

        # Failed (error set on pipeline)
        error = getattr(pipeline, "_error", None)
        if error:
            raise HTTPException(status_code=500, detail=f"Investigation failed: {error}")

        # Pipeline exists but report not ready: agents, arbiter, or persistence in flight.
        # Do not fall through to 404 just because _active_tasks lost the handle or the
        # asyncio Task appears done for one scheduling slice (breaks Accept → results poll).
        return JSONResponse(
            status_code=202,
            content={
                "status": "in_progress",
                "session_id": session_id,
                "message": "Investigation still in progress",
            },
        )

    # ── 2. In-memory reports cache ────────────────────────────────────────────
    if session_id in _final_reports:
        report, cached_at = _final_reports[session_id]
        if (datetime.now(timezone.utc) - cached_at).total_seconds() < 86_400:
            return _forensic_report_to_dto(report)
        del _final_reports[session_id]

    # ── 3. PostgreSQL — restart-resilient fallback ────────────────────────────
    try:
        from core.session_persistence import get_session_persistence
        persistence = await get_session_persistence()
        db_row = await persistence.get_report(session_id)
        if db_row:
            status = db_row.get("status")
            if status == "error":
                raise HTTPException(
                    status_code=500,
                    detail=f"Investigation failed: {db_row.get('error_message', 'unknown')}",
                )
            if status in ("running", "pending"):
                return JSONResponse(
                    status_code=202,
                    content={
                        "status": "in_progress",
                        "session_id": session_id,
                        "message": "Investigation still in progress",
                    },
                )
            if status == "completed" and db_row.get("report_data"):
                # Re-hydrate from the stored JSON dict
                from api.schemas import ReportDTO as _RD, AgentFindingDTO as _AFD

                def _rebuild_finding(f: dict) -> _AFD:
                    return _AFD(
                        finding_id=str(f.get("finding_id", "")),
                        agent_id=str(f.get("agent_id", "")),
                        agent_name=str(f.get("agent_name", "")),
                        finding_type=str(f.get("finding_type", "")),
                        status=str(f.get("status", "CONFIRMED")),
                        confidence_raw=float(f.get("confidence_raw", 0.0)),
                        calibrated=bool(f.get("calibrated", False)),
                        calibrated_probability=f.get("raw_confidence_score") or f.get("calibrated_probability"),
                        raw_confidence_score=f.get("raw_confidence_score") or f.get("calibrated_probability"),
                        court_statement=f.get("court_statement"),
                        robustness_caveat=bool(f.get("robustness_caveat", False)),
                        robustness_caveat_detail=f.get("robustness_caveat_detail"),
                        reasoning_summary=str(f.get("reasoning_summary", "")),
                        metadata=f.get("metadata"),
                    )

                rd = db_row["report_data"]
                per_agent = {
                    agent_id: [_rebuild_finding(f) for f in findings]
                    for agent_id, findings in (rd.get("per_agent_findings") or {}).items()
                }
                return _RD(
                    report_id=str(rd.get("report_id", "")),
                    session_id=str(rd.get("session_id", session_id)),
                    case_id=rd.get("case_id", ""),
                    executive_summary=rd.get("executive_summary", ""),
                    per_agent_findings=per_agent,
                    per_agent_metrics=rd.get("per_agent_metrics") or {},
                    per_agent_analysis=rd.get("per_agent_analysis") or {},
                    overall_confidence=float(rd.get("overall_confidence") or 0.0),
                    overall_error_rate=float(rd.get("overall_error_rate") or 0.0),
                    overall_verdict=rd.get("overall_verdict") or "REVIEW REQUIRED",
                    cross_modal_confirmed=[_rebuild_finding(f) for f in rd.get("cross_modal_confirmed", [])],
                    contested_findings=rd.get("contested_findings", []),
                    tribunal_resolved=rd.get("tribunal_resolved", []),
                    incomplete_findings=[_rebuild_finding(f) for f in rd.get("incomplete_findings", [])],
                    uncertainty_statement=rd.get("uncertainty_statement", ""),
                    cryptographic_signature=rd.get("cryptographic_signature", ""),
                    report_hash=rd.get("report_hash", ""),
                    signed_utc=rd.get("signed_utc"),
                    verdict_sentence=rd.get("verdict_sentence", ""),
                    key_findings=list(rd.get("key_findings") or []),
                    reliability_note=rd.get("reliability_note", ""),
                    manipulation_probability=float(rd.get("manipulation_probability") or 0.0),
                    confidence_min=float(rd.get("confidence_min") or 0.0),
                    confidence_max=float(rd.get("confidence_max") or 0.0),
                    confidence_std_dev=float(rd.get("confidence_std_dev") or 0.0),
                    applicable_agent_count=int(rd.get("applicable_agent_count") or 0),
                    skipped_agents=dict(rd.get("skipped_agents") or {}),
                    analysis_coverage_note=rd.get("analysis_coverage_note", ""),
                    per_agent_summary=dict(rd.get("per_agent_summary") or {}),
                )
    except HTTPException:
        raise
    except Exception as db_err:
        # A transient DB error (e.g. connection timeout) must not masquerade as
        # a 404 — the session may exist but the DB is temporarily unavailable.
        logger.error(
            "DB report lookup failed",
            session_id=session_id,
            error=str(db_err),
        )
        raise HTTPException(
            status_code=503,
            detail="Report lookup temporarily unavailable — please retry shortly.",
        )

    raise HTTPException(
        status_code=404,
        detail=f"No investigation found for session {session_id}",
    )


# ============================================================================
# BRIEF ENDPOINT — last known thinking text for an agent
# ============================================================================

@router.get("/{session_id}/brief/{agent_id}")
async def get_agent_brief(
    session_id: str,
    agent_id: str,
    current_user: User = Depends(get_current_user),
):
    """
    Return the most recent reasoning brief for an agent.

    Attempts (in order):
    1. Live working-memory snapshot from the active pipeline
    2. Falls back to empty string — brief is non-critical UI decoration
    """
    pipeline = get_active_pipeline(session_id)
    if not pipeline and session_id not in _final_reports:
        raise HTTPException(status_code=404, detail="Session not found")

    brief_text = ""
    if pipeline:
        try:
            wm = getattr(pipeline, "working_memory", None)
            if wm is not None:
                from uuid import UUID
                state = await wm.get_state(UUID(session_id), agent_id)
                if state:
                    # Extract the most recent in-progress task description as brief
                    tasks = getattr(state, "tasks", [])
                    in_progress = [t for t in tasks if getattr(t, "status", None) and
                                   str(getattr(t, "status", "")) == "IN_PROGRESS"]
                    if in_progress:
                        brief_text = getattr(in_progress[-1], "description", "")
        except Exception:
            pass  # brief is non-critical

    return {"brief": brief_text}


# ============================================================================
# CHECKPOINTS ENDPOINT — pending HITL decisions
# ============================================================================

@router.get("/{session_id}/checkpoints")
async def get_session_checkpoints(
    session_id: str,
    current_user: User = Depends(get_current_user),
):
    """
    Return pending HITL checkpoints for a session.

    Checks the active pipeline first, then falls back to the database.
    """
    pipeline = get_active_pipeline(session_id)
    if not pipeline and session_id not in _final_reports:
        raise HTTPException(status_code=404, detail="Session not found")

    checkpoints = []
    try:
        from core.session_persistence import get_session_persistence
        persistence = await get_session_persistence()
        rows = await persistence.client.fetch(
            """
            SELECT checkpoint_id, agent_id, reason, investigator_brief, status, created_utc
            FROM hitl_checkpoints
            WHERE session_id = $1 AND status = 'PAUSED'
            ORDER BY created_utc DESC
            """,
            session_id,
        ) if persistence.client else []
        for row in rows:
            checkpoints.append({
                "checkpoint_id": str(row["checkpoint_id"]),
                "session_id": session_id,
                "agent_id": row["agent_id"],
                "agent_name": row["agent_id"],
                "brief_text": row.get("investigator_brief") or "",
                "decision_needed": "APPROVE, REDIRECT, OVERRIDE, TERMINATE, or ESCALATE",
                "created_at": row["created_utc"].isoformat() if row.get("created_utc") else "",
            })
    except Exception as e:
        # Non-fatal — return empty list if DB unavailable
        from core.structured_logging import get_logger as _gl
        _gl(__name__).warning(f"Failed to fetch checkpoints: {e}")

    return checkpoints




# ============================================================================
# RESUME ENDPOINT — placed here so it lives at /api/v1/sessions/{session_id}/resume
# matching the frontend call from useSimulation.ts
# ============================================================================

from pydantic import BaseModel as _BaseModel


class ResumeRequest(_BaseModel):
    """Request body for the resume endpoint."""
    deep_analysis: bool


@router.post("/{session_id}/resume")
async def resume_investigation(
    session_id: str,
    request: ResumeRequest,
    current_user: User = Depends(get_current_user),
):
    """
    Resume investigation after initial analysis decision.

    Called by the frontend when the user clicks:
    - "Accept Analysis"  → deep_analysis=False → skip deep pass, proceed to arbiter
    - "Deep Analysis"    → deep_analysis=True  → run heavy ML analysis

    The pipeline must be in a paused state (waiting on deep_analysis_decision_event).
    Returns 200 with idempotency: if the event was already set, returns
    {"status": "already_resumed"} rather than 409.
    """
    from core.structured_logging import get_logger as _get_logger
    _log = _get_logger(__name__)

    _log.info(
        "Resume investigation called",
        session_id=session_id,
        deep_analysis=request.deep_analysis,
        user_id=current_user.user_id,
    )

    pipeline = get_active_pipeline(session_id)
    if not pipeline:
        raise HTTPException(
            status_code=404,
            detail=f"No active investigation found for session {session_id}",
        )

    if not hasattr(pipeline, "deep_analysis_decision_event"):
        raise HTTPException(
            status_code=400,
            detail="Pipeline is not in a paused state waiting for decision",
        )

    # Idempotent — if already resumed, return gracefully
    if pipeline.deep_analysis_decision_event.is_set():
        _log.info(
            "Resume called but decision already made — returning idempotent 200",
            session_id=session_id,
        )
        return {
            "status": "already_resumed",
            "session_id": session_id,
            "deep_analysis": request.deep_analysis,
            "message": "Investigation already resumed",
        }

    pipeline.run_deep_analysis_flag = request.deep_analysis
    pipeline.deep_analysis_decision_event.set()

    _log.info(
        "Investigation resume signal sent",
        session_id=session_id,
        deep_analysis=request.deep_analysis,
    )

    return {
        "status": "resumed",
        "session_id": session_id,
        "deep_analysis": request.deep_analysis,
        "message": "Deep analysis started" if request.deep_analysis else "Proceeding to final report",
    }
