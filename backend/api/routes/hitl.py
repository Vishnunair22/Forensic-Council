"""
HITL Routes
===========

Routes for human-in-the-loop decision handling.
"""

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException

from api.schemas import HITLDecisionRequest
from api.routes.investigation import get_active_pipeline
from core.auth import get_current_user, User
from core.react_loop import HumanDecision

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
    
    Args:
        decision: The decision including session_id, checkpoint_id, agent_id,
                  and the decision type (APPROVE, REDIRECT, OVERRIDE, TERMINATE, TRIBUNAL)
    """
    # Look up the active pipeline for this session
    pipeline = get_active_pipeline(decision.session_id)
    if pipeline is None:
        raise HTTPException(
            status_code=404,
            detail=f"No active investigation found for session {decision.session_id}"
        )

    # Build the HumanDecision from the request
    try:
        human_decision = HumanDecision(
            decision_type=decision.decision,
            investigator_id=decision.agent_id,
            notes=decision.note or "",
            override_finding=decision.override_finding,
        )
        await pipeline.handle_hitl_decision(
            session_id=UUID(decision.session_id),
            checkpoint_id=UUID(decision.checkpoint_id),
            decision=human_decision,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to process decision: {str(e)}")

    return {
        "status": "processed",
        "message": f"Decision {decision.decision} applied for checkpoint {decision.checkpoint_id}",
        "session_id": decision.session_id,
    }
