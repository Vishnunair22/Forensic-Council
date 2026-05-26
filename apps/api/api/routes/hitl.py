"""
HITL Routes
===========

Routes for human-in-the-loop decision handling with atomic processing.
"""

import json
from datetime import UTC, datetime
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException

from api.routes import _session_state
from api.schemas import BriefUpdate, HITLDecisionRequest
from core.auth import User, get_current_user
from core.config import get_settings
from core.react_loop import HumanDecision
from core.structured_logging import get_logger

logger = get_logger(__name__)

router = APIRouter(prefix="/api/v1/hitl", tags=["hitl"])


def get_active_pipeline(session_id: str):
    """Compatibility wrapper for tests and older imports."""
    return _session_state.get_active_pipeline(session_id)


@router.get("/checkpoint/{session_id}/{agent_id}")
async def check_expired_hitl(
    session_id: str,
    agent_id: str,
    current_user: User = Depends(get_current_user),
):
    """
    Poll the HITL checkpoint key for a given session/agent pair.

    Returns the checkpoint JSON if the key still exists in Redis.
    If the 900s TTL has elapsed and the key is missing, emits a
    ``HITL_EXPIRED`` SSE event for the session and returns
    ``{"status": "expired", ...}``.

    The frontend polls this endpoint while a HITL review widget is active;
    on an ``expired`` response it can auto-dismiss the widget without
    requiring a human action.
    """
    from api.routes._authz import assert_session_access

    await assert_session_access(session_id, current_user)

    redis = None
    try:
        from core.persistence.redis_client import get_redis_client

        redis = await get_redis_client()
    except Exception as exc:
        raise HTTPException(status_code=503, detail="Redis unavailable") from exc

    key = f"hitl:{session_id}:{agent_id}"
    try:
        raw = await redis.get(key)
    except Exception as exc:
        raise HTTPException(status_code=503, detail="Redis read error") from exc

    if raw is not None:
        try:
            checkpoint = json.loads(raw)
        except Exception:
            checkpoint = {"raw": raw}
        return {"status": "active", "checkpoint": checkpoint}

    # Key missing — TTL expired or checkpoint was never created.
    # Emit HITL_EXPIRED so the SSE stream carries the expiry signal to all
    # connected clients (not just the poller).
    try:
        await _session_state.broadcast_update(
            session_id,
            BriefUpdate(
                type="HITL_EXPIRED",
                session_id=session_id,
                agent_id=agent_id,
                message=f"HITL checkpoint for {agent_id} expired (auto-resolved after 15 min)",
                data={"agent_id": agent_id, "session_id": session_id, "auto_resolved": True},
            ),
        )
    except Exception as exc:
        logger.warning(
            "Failed to broadcast HITL_EXPIRED event",
            session_id=session_id,
            agent_id=agent_id,
            error=str(exc),
        )

    return {
        "status": "expired",
        "session_id": session_id,
        "agent_id": agent_id,
        "message": "HITL checkpoint has expired (auto-resolved after 15 minutes)",
    }


@router.post("/decision")
async def submit_decision(
    decision: HITLDecisionRequest,
    current_user: User = Depends(get_current_user),
):
    """
    Submit a human-in-the-loop decision for a checkpoint.

    Routes the decision to the active pipeline for the given session,
    which then forwards it to the correct agent's ReAct loop engine.

    Includes idempotency check to prevent duplicate processing.

    Args:
        decision: The decision including session_id, checkpoint_id, agent_id,
                  and the decision type (APPROVE, REDIRECT, OVERRIDE, TERMINATE, TRIBUNAL)
    """
    # Idempotency check: has this checkpoint already been decided?
    # Use checkpoint_id only so a user changing their mind (APPROVE -> REDIRECT)
    # is rejected — the first decision stands.
    cache_key = f"hitl_decision:{decision.checkpoint_id}"

    redis = None
    try:
        from core.persistence.redis_client import get_redis_client

        redis = await get_redis_client()
        if redis:
            if await redis.get(cache_key):
                logger.info(
                    "HITL decision already processed (idempotent)",
                    checkpoint_id=decision.checkpoint_id,
                    decision=decision.decision,
                )
                return {
                    "status": "already_processed",
                    "checkpoint_id": decision.checkpoint_id,
                    "decision": decision.decision,
                }
    except Exception as e:
        logger.error("Redis idempotency check failed", error=str(e), exc_info=True)
        if get_settings().app_env == "production":
            raise HTTPException(
                status_code=503,
                detail="Decision idempotency service unavailable. Please retry shortly.",
            ) from e
        logger.warning("Redis idempotency check failed, proceeding anyway", error=str(e))

    # Verify the user has access to this session.
    from api.routes._authz import assert_session_access

    await assert_session_access(decision.session_id, current_user)

    # Look up the active pipeline for this session
    pipeline = get_active_pipeline(decision.session_id)

    # B-H-9: in worker-mode deployments the pipeline runs in a separate
    # process, so _active_pipelines is always empty on this API replica.
    # Mirror the resume_investigation pattern: publish the decision over
    # Redis pub/sub for the worker, persist an idempotency-friendly key,
    # and return 202 Accepted. The worker subscribes to
    # `forensic:notify_decision` and applies the decision against its own
    # in-memory pipeline.
    if pipeline is None:
        settings = get_settings()
        if settings.use_redis_worker and redis is not None:
            try:
                await redis.publish(
                    "forensic:notify_decision",
                    json.dumps(
                        {
                            "session_id": decision.session_id,
                            "checkpoint_id": decision.checkpoint_id,
                            "agent_id": decision.agent_id,
                            "decision": decision.decision,
                            "investigator_id": current_user.user_id,
                            "note": decision.note or "",
                            "override_finding": decision.override_finding,
                        }
                    ),
                )
                # Idempotency token so a retry from the client doesn't
                # re-publish on the second hit.
                try:
                    await redis.set(cache_key, "1", ex=3600)
                except Exception as set_err:
                    logger.warning(
                        "Failed to set HITL idempotency key after publish",
                        checkpoint_id=decision.checkpoint_id,
                        error=str(set_err),
                    )
                logger.info(
                    "HITL decision dispatched via worker pub/sub",
                    checkpoint_id=decision.checkpoint_id,
                    decision=decision.decision,
                    investigator_id=current_user.user_id,
                )
                return {
                    "status": "accepted",
                    "message": f"Decision {decision.decision} dispatched to worker",
                    "session_id": decision.session_id,
                    "checkpoint_id": decision.checkpoint_id,
                    "dispatched_at": datetime.now(UTC).isoformat(),
                }
            except Exception as exc:
                logger.error(
                    "Worker pub/sub dispatch failed for HITL decision",
                    error=str(exc),
                    checkpoint_id=decision.checkpoint_id,
                    exc_info=True,
                )
                raise HTTPException(
                    status_code=503,
                    detail="Decision worker is temporarily unavailable. Please retry.",
                ) from exc
        raise HTTPException(
            status_code=404,
            detail=f"No active investigation found for session {decision.session_id}",
        )

    # Build the HumanDecision from the request
    try:
        human_decision = HumanDecision(
            decision_type=decision.decision,
            investigator_id=current_user.user_id,  # Use actual investigator, not agent_id
            notes=decision.note or "",
            override_finding=decision.override_finding,
        )
        await pipeline.handle_hitl_decision(
            session_id=UUID(decision.session_id),
            checkpoint_id=UUID(decision.checkpoint_id),
            decision=human_decision,
        )

        # Mark as processed (idempotency token) - 1 hour expiry
        try:
            if redis:
                await redis.set(cache_key, "1", ex=3600)
        except Exception as e:
            logger.error(
                "Failed to cache idempotency token after decision processed",
                checkpoint_id=decision.checkpoint_id,
                error=str(e),
                exc_info=True,
            )

        logger.info(
            "HITL decision processed successfully",
            checkpoint_id=decision.checkpoint_id,
            decision=decision.decision,
            investigator_id=current_user.user_id,
        )

    except ValueError as e:
        logger.warning("Invalid HITL decision", error=str(e), checkpoint_id=decision.checkpoint_id)
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(
            "HITL decision processing failed",
            error=str(e),
            exc_info=True,
            checkpoint_id=decision.checkpoint_id,
        )
        raise HTTPException(
            status_code=500,
            detail="Failed to process decision. The decision may have been partially applied.",
        )

    return {
        "status": "processed",
        "message": f"Decision {decision.decision} applied for checkpoint {decision.checkpoint_id}",
        "session_id": decision.session_id,
        "checkpoint_id": decision.checkpoint_id,
    }
