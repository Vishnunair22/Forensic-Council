"""
Sessions Routes
===============

Routes for managing investigation sessions.
"""

import asyncio
import json
import time
from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.responses import JSONResponse
from pydantic import BaseModel as _BaseModel

from api.routes._session_state import (
    _final_reports,
    get_active_pipeline,
    get_active_pipeline_metadata,
    get_session_websockets,
    register_websocket,
    set_active_pipeline_metadata,
    unregister_websocket,
)
from api.routes._authz import assert_session_access
from api.schemas import AgentFindingDTO, ReportDTO, ReportStatusDTO, SessionInfo
from core.auth import User, decode_token, get_current_user
from core.severity import assign_severity_tier as _assign_severity_tier
from core.structured_logging import get_logger

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

        def _opt_float(value):
            if value is None:
                return None
            try:
                return float(value)
            except (TypeError, ValueError):
                return None

        evidence_verdict = str(
            d.get("evidence_verdict") or meta.get("evidence_verdict") or "INCONCLUSIVE"
        ).upper()
        if evidence_verdict not in {
            "POSITIVE",
            "NEGATIVE",
            "INCONCLUSIVE",
            "NOT_APPLICABLE",
            "ERROR",
        }:
            evidence_verdict = "INCONCLUSIVE"

        dto = AgentFindingDTO(
            finding_id=str(d.get("finding_id", "")),
            agent_id=str(d.get("agent_id", "")),
            agent_name=str(d.get("agent_name", d.get("agent_id", ""))),
            finding_type=str(d.get("finding_type", "Unknown")),
            status=str(d.get("status", "CONFIRMED")),
            confidence_raw=_opt_float(d.get("confidence_raw")),
            evidence_verdict=evidence_verdict,
            calibrated=bool(d.get("calibrated", False)),
            calibrated_probability=_opt_float(d.get("calibrated_probability")),
            raw_confidence_score=_opt_float(d.get("raw_confidence_score"))
            or _opt_float(d.get("confidence_raw")),
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
        try:
            real = [_to_finding_dto(f) for f in findings if _is_real_finding(f)]
            if real:
                per_agent[agent_id] = real
        except Exception as e:
            logger.warning(
                "Failed to convert findings for agent",
                agent_id=agent_id,
                error=str(e),
            )
            # Skip this agent's findings rather than failing the entire report

    cross_modal = []
    try:
        cross_modal = [
            _to_finding_dto(f) for f in (report.cross_modal_confirmed or []) if _is_real_finding(f)
        ]
    except Exception as e:
        logger.warning("Failed to convert cross-modal findings", error=str(e))

    incomplete = []
    try:
        incomplete = [
            _to_finding_dto(f) for f in (report.incomplete_findings or []) if _is_real_finding(f)
        ]
    except Exception as e:
        logger.warning("Failed to convert incomplete findings", error=str(e))

    # TribunalCase objects need explicit serialization
    tribunal_resolved = []
    for item in report.tribunal_resolved or []:
        try:
            if hasattr(item, "model_dump"):
                tribunal_resolved.append(item.model_dump(mode="json"))
            elif isinstance(item, dict):
                tribunal_resolved.append(item)
        except Exception as e:
            logger.warning("Failed to serialize tribunal case", error=str(e))

    contested = []
    for item in report.contested_findings or []:
        try:
            if hasattr(item, "model_dump"):
                contested.append(item.model_dump(mode="json"))
            elif isinstance(item, dict):
                contested.append(item)
        except Exception as e:
            logger.warning("Failed to serialize contested finding", error=str(e))

    signed_utc_str: str | None = None
    if report.signed_utc is not None:
        try:
            if hasattr(report.signed_utc, "isoformat"):
                signed_utc_str = report.signed_utc.isoformat()
            else:
                signed_utc_str = str(report.signed_utc)
        except Exception as e:
            logger.warning("Failed to serialize signed_utc", error=str(e))
            signed_utc_str = None

    # Build DTO — let construction errors propagate to the route handler as 500
    return ReportDTO(
        report_id=str(report.report_id),
        session_id=str(report.session_id),
        case_id=report.case_id,
        executive_summary=report.executive_summary or "",
        per_agent_findings=per_agent,
        per_agent_metrics=getattr(report, "per_agent_metrics", {}) or {},
        per_agent_analysis=getattr(report, "per_agent_analysis", {}) or {},
        overall_confidence=float(getattr(report, "overall_confidence", 0.0) or 0.0),
        overall_error_rate=float(getattr(report, "overall_error_rate", 0.0) or 0.0),
        overall_verdict=str(
            getattr(report, "overall_verdict", "REVIEW REQUIRED") or "REVIEW REQUIRED"
        ),
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
        compression_penalty=float(getattr(report, "compression_penalty", 1.0) or 1.0),
        confidence_min=float(getattr(report, "confidence_min", 0.0) or 0.0),
        confidence_max=float(getattr(report, "confidence_max", 0.0) or 0.0),
        confidence_std_dev=float(getattr(report, "confidence_std_dev", 0.0) or 0.0),
        applicable_agent_count=int(getattr(report, "applicable_agent_count", 0) or 0),
        skipped_agents=dict(getattr(report, "skipped_agents", {}) or {}),
        analysis_coverage_note=getattr(report, "analysis_coverage_note", "") or "",
        per_agent_summary=dict(getattr(report, "per_agent_summary", {}) or {}),
        degradation_flags=list(getattr(report, "degradation_flags", []) or []),
        cross_modal_fusion=dict(getattr(report, "cross_modal_fusion", {}) or {}),
    )


@router.get("", response_model=list[SessionInfo])
async def list_sessions(current_user: User = Depends(get_current_user)):
    """List all active sessions. Requires authentication."""
    # This now only lists sessions from Redis metadata
    from api.routes._session_state import SESSION_METADATA_KEY_PREFIX
    from core.persistence.redis_client import get_redis_client

    redis = await get_redis_client()
    keys = await redis.keys(f"{SESSION_METADATA_KEY_PREFIX}*")

    sessions = []
    for key in keys:
        session_id = key.replace(SESSION_METADATA_KEY_PREFIX, "")
        metadata = await redis.get_json(key)
        if metadata and isinstance(metadata, dict):
            sessions.append(
                SessionInfo(
                    session_id=session_id,
                    case_id=metadata.get("case_id", "unknown"),
                    status=metadata.get("status", "running"),
                    started_at=metadata.get("created_at", ""),
                )
            )
    return sessions


@router.delete("/{session_id}")
async def terminate_session(session_id: str, current_user: User = Depends(get_current_user)):
    """Terminate a running session. Requires authentication and session ownership."""
    await assert_session_access(session_id, current_user)

    # Close local WebSocket connections
    for ws in get_session_websockets(session_id):
        try:
            await ws.close()
        except Exception:
            pass
    # register_websocket/unregister_websocket and get_session_websockets
    # are still needed for local broadcast, so we don't clear them entirely here.

    # Note: In a distributed system, we would publish a TERMINATE event to Redis
    # so the worker in another process can stop its pipeline.
    # For now, we just remove the metadata.
    from core.persistence.redis_client import get_redis_client

    redis = await get_redis_client()
    await redis.delete(f"forensic:session:metadata:{session_id}")

    return {"status": "terminated", "session_id": session_id}


@router.websocket("/{session_id}/live")
async def live_updates(websocket: WebSocket, session_id: str):
    """
    WebSocket endpoint for live investigation updates.

    Bridges messages from the background worker via Redis Pub/Sub.
    """
    from api.routes._session_state import (
        get_active_pipeline_metadata,
    )
    from core.persistence.redis_client import get_redis_client

    # ── 1. Accept WebSocket and Authenticate ─────────────────────────────────
    # We must accept the connection before we can send JSON error messages.
    # We use a subprotocol-based token fallback for environments where cookies
    # are blocked or stripped (e.g. cross-origin development).
    await websocket.accept(subprotocol="forensic-v1")

    # Check for session cookies (fc_session or sessionid) or access_token
    auth_token = (
        websocket.cookies.get("fc_session")
        or websocket.cookies.get("sessionid")
        or websocket.cookies.get("access_token")
    )

    # Fallback: check subprotocols if cookie is missing
    if not auth_token:
        for protocol in websocket.scope.get("subprotocols", []):
            if protocol.startswith("token."):
                auth_token = protocol[6:]
                break

    if auth_token:
        # Debug: log token extraction (obscure the middle)
        token_preview = (
            f"{auth_token[:10]}...{auth_token[-10:]}" if len(auth_token) > 20 else "short"
        )
        logger.info(
            "Extracted WebSocket auth token", session_id=session_id, token_preview=token_preview
        )

    if not auth_token:
        logger.warning("WebSocket auth failed: No token found", session_id=session_id)
        await websocket.send_json({"type": "ERROR", "message": "Auth required"})
        await websocket.close(code=4001)
        return

    user_id = "anonymous"
    try:
        # Decode token to verify and get user_id
        token_data = await decode_token(auth_token)
        user_id = token_data.user_id
    except Exception as e:
        logger.warning(
            "WebSocket auth failed: Invalid token",
            session_id=session_id,
            error=str(e),
        )
        await websocket.send_json({"type": "ERROR", "message": "Invalid token"})
        await websocket.close(code=4001)
        return

    # ── 2. Wait for session metadata ─────────────────────────────────────────
    # We wait up to 6 seconds for metadata to appear in Redis (indicating
    # the pipeline has been initialized by the /investigate endpoint).
    metadata = None
    for _i in range(60):  # up to 6 s
        metadata = await get_active_pipeline_metadata(session_id)
        if metadata:
            break
        await asyncio.sleep(0.1)

    if not metadata:
        logger.warning(
            "WebSocket connection rejected: Session metadata not found",
            session_id=session_id,
        )
        await websocket.send_json({"type": "ERROR", "message": "Session not found"})
        await websocket.close(code=4004)
        return

    # Reject connections for sessions interrupted by a prior API restart.
    # The investigation cannot be resumed — the client should start a new one.
    if isinstance(metadata, dict) and metadata.get("status") == "interrupted":
        logger.warning(
            "WebSocket connection rejected: session was interrupted by API restart",
            session_id=session_id,
        )
        await websocket.send_json(
            {
                "type": "ERROR",
                "message": "This investigation was interrupted by a server restart and cannot be resumed. Please start a new investigation.",
                "data": {"status": "interrupted", "recoverable": False},
            }
        )
        await websocket.close(code=4010)
        return

    # ── 3. Verify session ownership ────────────────────────────────────────────
    # Create a minimal user object for authorization check
    from core.auth import User

    auth_user = User(user_id=user_id, username=user_id, role=metadata.get("investigator_role", "investigator"))
    try:
        await assert_session_access(session_id, auth_user)
    except HTTPException as e:
        await websocket.send_json({"type": "ERROR", "message": e.detail})
        await websocket.close(code=4003)
        return

    # ── 4. Subscribe to Redis Updates for this session ───────────────────────
    # WebSocket configuration - declare BEFORE task creation
    IDLE_TIMEOUT = 300  # 5 minutes
    PING_INTERVAL = 30  # seconds
    MAX_MESSAGES_PER_MINUTE = 100
    from collections import deque

    last_activity = time.time()
    message_timestamps: deque[float] = deque(maxlen=200)

    # This task listens for messages published by the Worker to the session channel
    # and forwards them directly to the user's specific WebSocket connection.
    async def _redis_subscriber():
        nonlocal last_activity
        pubsub = None
        try:
            redis = await get_redis_client()
            pubsub = redis.client.pubsub()
            channel = f"forensic:updates:{session_id}"
            await pubsub.subscribe(channel)

            async for message in pubsub.listen():
                if message["type"] == "message":
                    data = json.loads(message["data"])
                    await websocket.send_json(data)
                    last_activity = time.time()  # Keep connection alive during long output
        except asyncio.CancelledError:
            raise
        except Exception as e:
            logger.warning("Redis subscriber error", session_id=session_id, error=str(e))
            try:
                await websocket.send_json({
                    "type": "ERROR",
                    "message": "Live update channel disconnected. Please refresh.",
                    "data": {"recoverable": True},
                })
            except Exception:
                pass
            await websocket.close(code=1011)
        finally:
            if pubsub:
                try:
                    await pubsub.unsubscribe()
                except Exception:
                    pass
                try:
                    await pubsub.aclose()
                except Exception:
                    pass

    # Note: We do NOT call register_websocket() here - all messages come via
    # Redis pub/sub to avoid double-delivery in single-process mode

    async def send_ping():
        """Send periodic ping to detect stale connections."""
        try:
            while True:
                await asyncio.sleep(PING_INTERVAL)
                try:
                    await websocket.send_json({"type": "PING", "timestamp": time.time()})
                except Exception:
                    break
        except asyncio.CancelledError:
            pass
        except Exception as e:
            logger.debug("Ping task failed", session_id=session_id, error=str(e))

    async def monitor_idle():
        """Monitor for idle connections and close them."""
        try:
            while True:
                await asyncio.sleep(10)
                if time.time() - last_activity > IDLE_TIMEOUT:
                    logger.warning(
                        "WebSocket idle timeout",
                        session_id=session_id,
                        idle_seconds=time.time() - last_activity,
                    )
                    await websocket.close(code=1000, reason="Idle timeout")
                    break
        except asyncio.CancelledError:
            pass
        except Exception as e:
            logger.debug("Idle monitor task failed", session_id=session_id, error=str(e))

    ping_task = asyncio.create_task(send_ping())
    idle_task = asyncio.create_task(monitor_idle())
    subscriber_task = asyncio.create_task(_redis_subscriber())

    try:
        await websocket.send_json(
            {
                "type": "CONNECTED",
                "session_id": session_id,
                "message": "Connected to distributed live updates",
                "data": {"status": "connected", "user_id": user_id},
            }
        )

        # Wait for client to close or disconnect
        while True:
            try:
                # Expect PONG responses or other messages
                data = await websocket.receive_text()
                last_activity = time.time()

                # Rate limit check
                now = time.time()
                one_min_ago = now - 60

                # Remove old timestamps (deque O(1) vs list O(n))
                while message_timestamps and message_timestamps[0] < one_min_ago:
                    message_timestamps.popleft()

                if len(message_timestamps) >= MAX_MESSAGES_PER_MINUTE:
                    logger.warning(
                        "WebSocket rate limit exceeded",
                        session_id=session_id,
                        messages_per_minute=len(message_timestamps),
                    )
                    await websocket.send_json(
                        {
                            "type": "ERROR",
                            "detail": "Rate limit exceeded. Maximum 100 messages per minute.",
                        }
                    )
                    await websocket.close(code=1008, reason="Rate limit exceeded")
                    break

                message_timestamps.append(now)

                # Handle PONG responses
                try:
                    msg = json.loads(data)
                    if msg.get("type") == "PONG":
                        continue  # Heartbeat response, skip processing
                except json.JSONDecodeError:
                    pass  # Non-JSON text, ignore

            except WebSocketDisconnect:
                break

    except WebSocketDisconnect:
        pass
    except asyncio.CancelledError:
        raise
    except Exception as ws_err:
        logger.warning("WebSocket error", session_id=session_id, error=str(ws_err))
    finally:
        # Cancel background tasks
        ping_task.cancel()
        idle_task.cancel()
        subscriber_task.cancel()

        # Wait for tasks to finish
        # BUG-11: Clean up background tasks concurrently and safely
        await asyncio.gather(ping_task, idle_task, subscriber_task, return_exceptions=True)

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
    Returns status from Redis persistence. Never raises — always returns a
    safe JSON body so the frontend can keep polling without hitting 500s.
    """
    await assert_session_access(session_id, current_user)

    try:
        from api.routes._session_state import get_active_pipeline_metadata, get_final_report

        # 1. Check if report is already complete (in-memory / Redis cache)
        try:
            report_data = await get_final_report(session_id)
            if report_data:
                report, _ = report_data
                report_id = (
                    report.get("report_id")
                    if isinstance(report, dict)
                    else getattr(report, "report_id", session_id)
                )
                return {"status": "complete", "report_id": str(report_id)}
        except Exception as _e:
            logger.debug("Report cache check failed", session_id=session_id, error=str(_e))

        # 2. Check active metadata in Redis
        try:
            metadata = await get_active_pipeline_metadata(session_id)
            if metadata:
                status = metadata.get("status", "running")
                if status == "completed":
                    return {"status": "complete", "report_id": session_id}
                if status == "error":
                    return {"status": "error", "message": metadata.get("error", "Unknown error")}
                msg = metadata.get("brief") or "Investigation in progress…"
                return {"status": "running", "message": msg}
        except Exception as _e:
            logger.debug("Pipeline metadata check failed", session_id=session_id, error=str(_e))

        # 3. DB fallback
        try:
            from core.session_persistence import get_session_persistence

            persistence = await get_session_persistence()
            db_row = await persistence.get_report(session_id)
            if db_row:
                s = db_row.get("status", "")
                if s == "completed":
                    return {"status": "complete", "report_id": session_id}
                if s in ("running", "pending"):
                    return {"status": "running", "message": "Investigation in progress…"}
                if s == "error":
                    return {
                        "status": "error",
                        "message": db_row.get("error_message", "Unknown error"),
                    }
        except Exception as _e:
            logger.debug("DB status check failed", session_id=session_id, error=str(_e))

        return {"status": "not_found"}

    except Exception as e:
        logger.warning("arbiter-status unexpected error", session_id=session_id, error=str(e))
        return {"status": "running", "message": "Checking investigation status…"}


# ============================================================================
# REPORT ENDPOINT - Fetch final report for results page
# ============================================================================


@router.get(
    "/{session_id}/report",
    response_model=None,
    responses={200: {"model": ReportDTO}, 202: {"model": ReportStatusDTO}},
)
async def get_session_report(
    session_id: str,
    current_user: User = Depends(get_current_user),
):
    """
    Get the final investigation report.

    Resolution order (most recent / most reliable first):
    1. In-memory pipeline object  — fastest; only available on the originating replica
    2. Redis final report cache — survives restarts, visible to all replicas
    3. In-memory final_reports cache — survives pipeline eviction for up to 24 h
    4. PostgreSQL session_reports  — survives restarts and is visible to all replicas
    """
    await assert_session_access(session_id, current_user)

    pipeline = get_active_pipeline(session_id)

    # ── 1. In-memory pipeline ─────────────────────────────────────────────────
    if pipeline:
        report = getattr(pipeline, "_final_report", None)
        if report:
            _final_reports[session_id] = (report, datetime.now(UTC))
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
        if (datetime.now(UTC) - cached_at).total_seconds() < 86_400:
            return _forensic_report_to_dto(report)
        del _final_reports[session_id]

    # ── 2b. Redis cache (when use_redis_worker=True) ──────────────────────────
    try:
        from api.routes._session_state import get_final_report

        redis_hit = await get_final_report(session_id)
        if redis_hit:
            payload, created_at = redis_hit
            _final_reports[session_id] = (payload, created_at)
            return _forensic_report_to_dto(payload)
    except Exception as _e:
        logger.warning("Redis report cache lookup failed", session_id=session_id, error=str(_e))

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
                from api.schemas import AgentFindingDTO as _AFD
                from api.schemas import ReportDTO as _RD

                def _opt_float(value):
                    if value is None:
                        return None
                    try:
                        return float(value)
                    except (TypeError, ValueError):
                        return None

                def _rebuild_finding(f: dict) -> _AFD:
                    metadata = f.get("metadata") or {}
                    evidence_verdict = str(
                        f.get("evidence_verdict")
                        or metadata.get("evidence_verdict")
                        or "INCONCLUSIVE"
                    ).upper()
                    if evidence_verdict not in {
                        "POSITIVE",
                        "NEGATIVE",
                        "INCONCLUSIVE",
                        "NOT_APPLICABLE",
                        "ERROR",
                    }:
                        evidence_verdict = "INCONCLUSIVE"
                    dto = _AFD(
                        finding_id=str(f.get("finding_id", "")),
                        agent_id=str(f.get("agent_id", "")),
                        agent_name=str(f.get("agent_name", "")),
                        finding_type=str(f.get("finding_type", "")),
                        status=str(f.get("status", "CONFIRMED")),
                        confidence_raw=_opt_float(f.get("confidence_raw")),
                        evidence_verdict=evidence_verdict,
                        calibrated=bool(f.get("calibrated", False)),
                        calibrated_probability=_opt_float(f.get("calibrated_probability")),
                        raw_confidence_score=_opt_float(f.get("raw_confidence_score"))
                        or _opt_float(f.get("confidence_raw")),
                        calibration_status=str(f.get("calibration_status", "UNCALIBRATED")),
                        court_statement=f.get("court_statement"),
                        robustness_caveat=bool(f.get("robustness_caveat", False)),
                        robustness_caveat_detail=f.get("robustness_caveat_detail"),
                        reasoning_summary=str(f.get("reasoning_summary", "")),
                        metadata=metadata or None,
                    )
                    # D-H2: Ensure severity_tier is populated for DB-rehydrated reports
                    dto.severity_tier = _assign_severity_tier(dto)
                    return dto

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
                    cross_modal_confirmed=[
                        _rebuild_finding(f) for f in rd.get("cross_modal_confirmed", [])
                    ],
                    contested_findings=rd.get("contested_findings", []),
                    tribunal_resolved=rd.get("tribunal_resolved", []),
                    incomplete_findings=[
                        _rebuild_finding(f) for f in rd.get("incomplete_findings", [])
                    ],
                    uncertainty_statement=rd.get("uncertainty_statement", ""),
                    cryptographic_signature=rd.get("cryptographic_signature", ""),
                    report_hash=rd.get("report_hash", ""),
                    signed_utc=rd.get("signed_utc"),
                    verdict_sentence=rd.get("verdict_sentence", ""),
                    key_findings=list(rd.get("key_findings") or []),
                    reliability_note=rd.get("reliability_note", ""),
                    manipulation_probability=float(rd.get("manipulation_probability") or 0.0),
                    compression_penalty=float(rd.get("compression_penalty") or 1.0),
                    confidence_min=float(rd.get("confidence_min") or 0.0),
                    confidence_max=float(rd.get("confidence_max") or 0.0),
                    confidence_std_dev=float(rd.get("confidence_std_dev") or 0.0),
                    applicable_agent_count=int(rd.get("applicable_agent_count") or 0),
                    skipped_agents=dict(rd.get("skipped_agents") or {}),
                    analysis_coverage_note=rd.get("analysis_coverage_note", ""),
                    per_agent_summary=dict(rd.get("per_agent_summary") or {}),
                    degradation_flags=list(rd.get("degradation_flags") or []),
                    cross_modal_fusion=dict(rd.get("cross_modal_fusion") or {}),
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


@router.get("/{session_id}/report/download")
async def download_report(
    session_id: str,
    current_user: User = Depends(get_current_user),
):
    """
    Download the forensic report as a JSON file.

    Returns the report with proper Content-Disposition headers for file download.
    """
    # Get the report or the 202 response using existing logic
    report_or_response = await get_session_report(session_id, current_user)

    # If still in progress, return the 202 status response unchanged.
    if isinstance(report_or_response, JSONResponse):
        return report_or_response

    # Generate filename with timestamp
    timestamp = datetime.now(UTC).strftime("%Y%m%d_%H%M%S")
    filename = f"forensic_report_{session_id}_{timestamp}.json"

    # Serialize Pydantic model before passing to JSONResponse
    content = report_or_response.model_dump(mode="json")
    return JSONResponse(
        content=content,
        headers={
            "Content-Disposition": f'attachment; filename="{filename}"',
            "X-Content-Type-Options": "nosniff",
            "Cache-Control": "no-cache, no-store, must-revalidate",
        },
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
    await assert_session_access(session_id, current_user)

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
                    in_progress = [
                        t
                        for t in tasks
                        if getattr(t, "status", None)
                        and str(getattr(t, "status", "")) == "IN_PROGRESS"
                    ]
                    if in_progress:
                        brief_text = getattr(in_progress[-1], "description", "")
        except Exception as e:
            logger.debug("Failed to extract agent brief", session_id=session_id, agent_id=agent_id, error=str(e))

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
    await assert_session_access(session_id, current_user)

    pipeline = get_active_pipeline(session_id)
    if not pipeline and session_id not in _final_reports:
        raise HTTPException(status_code=404, detail="Session not found")

    checkpoints = []
    try:
        from core.session_persistence import get_session_persistence

        persistence = await get_session_persistence()
        rows = (
            await persistence.client.fetch(
                """
            SELECT checkpoint_id, agent_id, reason, investigator_brief, status, created_utc
            FROM hitl_checkpoints
            WHERE session_id = $1 AND status = 'PAUSED'
            ORDER BY created_utc DESC
            """,
                session_id,
            )
            if persistence.client
            else []
        )
        for row in rows:
            checkpoints.append(
                {
                    "checkpoint_id": str(row["checkpoint_id"]),
                    "session_id": session_id,
                    "agent_id": row["agent_id"],
                    "agent_name": row["agent_id"],
                    "brief_text": row.get("investigator_brief") or "",
                    "decision_needed": "APPROVE, REDIRECT, OVERRIDE, TERMINATE, or ESCALATE",
                    "created_at": row["created_utc"].isoformat() if row.get("created_utc") else "",
                }
            )
    except Exception as e:
        # Non-fatal — return empty list if DB unavailable
        from core.structured_logging import get_logger as _gl

        _gl(__name__).warning("Failed to fetch checkpoints", error=str(e), exc_info=True)

    return checkpoints


# ============================================================================
# RESUME ENDPOINT — placed here so it lives at /api/v1/sessions/{session_id}/resume
# matching the frontend call from useSimulation.ts
# ============================================================================


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
    from core.persistence.redis_client import get_redis_client

    _log = _get_logger(__name__)

    # Validate session_id format first (D-H1)
    from api.routes._authz import validate_session_id

    validate_session_id(session_id)

    _log.info(
        "Resume investigation called",
        session_id=session_id,
        deep_analysis=request.deep_analysis,
        user_id=current_user.user_id,
    )

    # Check session exists and user owns it
    metadata = await get_active_pipeline_metadata(session_id)
    if not metadata:
        raise HTTPException(
            status_code=404,
            detail=f"No active investigation found for session {session_id}",
        )

    # Verify ownership (non-admins can't resume other users' investigations)
    owner = metadata.get("investigator_id")
    if current_user.role not in ("admin", "auditor") and owner != current_user.user_id:
        raise HTTPException(
            status_code=403,
            detail="You do not have access to this investigation",
        )

    # Now write the decision key
    redis = await get_redis_client()
    decision_key = f"forensic:session:resume_decision:{session_id}"
    await redis.set(
        decision_key,
        json.dumps(
            {
                "deep_analysis": request.deep_analysis,
                "decided_by": current_user.user_id,
                "decided_at": datetime.now(UTC).isoformat(),
            }
        ),
        ex=14400,
    )

    pipeline = get_active_pipeline(session_id)
    if not pipeline:
        await set_active_pipeline_metadata(
            session_id,
            {
                **metadata,
                "status": "resume_requested",
                "deep_analysis": request.deep_analysis,
                "resume_requested_at": datetime.now(UTC).isoformat(),
            },
        )
        return {
            "status": "resumed",
            "session_id": session_id,
            "deep_analysis": request.deep_analysis,
            "message": "Deep analysis started"
            if request.deep_analysis
            else "Proceeding to final report",
        }

    # Idempotency check first: if the decision event is already set the pipeline
    # already received the signal — return gracefully regardless of whether
    # _awaiting_user_decision has been reset back to False by the pipeline loop.
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

    # Only raise 400 after confirming idempotency doesn't apply
    if not getattr(pipeline, "_awaiting_user_decision", False):
        raise HTTPException(
            status_code=400,
            detail="Pipeline is not in a paused state waiting for decision",
        )

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
        "message": "Deep analysis started"
        if request.deep_analysis
        else "Proceeding to final report",
    }
