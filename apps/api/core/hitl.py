"""
Human-in-the-Loop (HITL) Checkpoint System Models for Forensic Council.
"""

from __future__ import annotations

import uuid
from enum import StrEnum
from typing import Any, Literal

from pydantic import BaseModel, Field


class HITLCheckpointReason(StrEnum):
    """Reasons for triggering a Human-in-the-Loop checkpoint."""

    ITERATION_CEILING_50PCT = "ITERATION_CEILING_50PCT"
    CONTESTED_FINDING = "CONTESTED_FINDING"
    TOOL_UNAVAILABLE = "TOOL_UNAVAILABLE"
    SEVERITY_THRESHOLD_BREACH = "SEVERITY_THRESHOLD_BREACH"
    TRIBUNAL_ESCALATION = "TRIBUNAL_ESCALATION"


class HITLCheckpointStatus(StrEnum):
    """Status of a HITL checkpoint."""

    PAUSED = "PAUSED"
    RESUMED = "RESUMED"
    OVERRIDDEN = "OVERRIDDEN"
    TERMINATED = "TERMINATED"


class HITLCheckpointState(BaseModel):
    """State of a Human-in-the-Loop checkpoint."""

    checkpoint_id: uuid.UUID = Field(
        default_factory=uuid.uuid4, description="Unique checkpoint identifier"
    )
    agent_id: str = Field(..., description="Agent that triggered checkpoint")
    session_id: uuid.UUID = Field(..., description="Session ID")
    reason: HITLCheckpointReason = Field(..., description="Why checkpoint was triggered")
    current_finding_summary: str = Field(default="", description="Summary of findings so far")
    paused_at_iteration: int = Field(..., description="Iteration at which loop was paused")
    investigator_brief: str = Field(default="", description="Brief for the human investigator")
    status: Literal["PAUSED", "RESUMED", "OVERRIDDEN", "TERMINATED"] = Field(
        default="PAUSED", description="Current checkpoint status"
    )
    serialized_state: dict[str, Any] | None = Field(
        default=None, description="Serialized working memory state"
    )


class HumanDecisionType(StrEnum):
    """Types of human decisions in HITL."""

    APPROVE = "APPROVE"
    REDIRECT = "REDIRECT"
    OVERRIDE = "OVERRIDE"
    TERMINATE = "TERMINATE"
    ESCALATE = "ESCALATE"


class HumanDecision(BaseModel):
    """A human decision in response to a HITL checkpoint."""

    decision_type: Literal["APPROVE", "REDIRECT", "OVERRIDE", "TERMINATE", "ESCALATE"] = Field(
        ..., description="Type of decision made"
    )
    investigator_id: str = Field(..., description="ID of the human investigator")
    notes: str = Field(default="", description="Notes from the investigator")
    override_finding: dict[str, Any] | None = Field(
        default=None, description="Override finding if OVERRIDE decision"
    )
    redirect_context: str | None = Field(
        default=None, description="New context/direction if REDIRECT decision"
    )
