"""
HITL Routes
===========

Routes for human-in-the-loop decision handling with atomic processing.
"""

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException

from api.routes._session_state import get_active_pipeline
from api.schemas import HITLDecisionRequest
from core.auth import User, get_current_user
from core.react_loop import HumanDecision
from core.structured_logging import get_logger

logger = get_logger(__name__)

router = APIRouter(prefix="/api/v1/hitl", tags=["hitl"])


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
    # Idempotency check: has this decision already been processed?
    cache_key = f"hitl_decision:{decision.checkpoint_id}:{decision.decision}"

    redis = None
    try:
        from core.persistence.redis_client import get_redis_client
        redis = await get_redis_client()
        if redis:
            if await redis.get(cache_key):
                logger.info(
                    "HITL decision already processed (idempotent)",
                    checkpoint_id=decision.checkpoint_id,
                    decision=decision.decision
                )
                return {
                    "status": "already_processed",
                    "checkpoint_id": decision.checkpoint_id,
                    "decision": decision.decision
                }
    except Exception as e:
        logger.warning("Redis idempotency check failed, proceeding anyway", error=str(e))

    # Look up the active pipeline for this session
    pipeline = get_active_pipeline(decision.session_id)
    if pipeline is None:
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
            logger.warning("Failed to cache idempotency token", error=str(e))

        logger.info(
            "HITL decision processed successfully",
            checkpoint_id=decision.checkpoint_id,
            decision=decision.decision,
            investigator_id=current_user.user_id
        )

    except ValueError as e:
        logger.warning("Invalid HITL decision", error=str(e), checkpoint_id=decision.checkpoint_id)
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(
            "HITL decision processing failed",
            error=str(e),
            exc_info=True,
            checkpoint_id=decision.checkpoint_id
        )
        raise HTTPException(
            status_code=500,
            detail="Failed to process decision. The decision may have been partially applied."
        )

    return {
        "status": "processed",
        "message": f"Decision {decision.decision} applied for checkpoint {decision.checkpoint_id}",
        "session_id": decision.session_id,
        "checkpoint_id": decision.checkpoint_id,
    }
