"""
API Schemas for Forensic Council
=================================

Pydantic models for API request/response handling.
"""

from datetime import datetime
from typing import Any, Literal, Optional
from uuid import UUID

from pydantic import BaseModel, Field


class InvestigationRequest(BaseModel):
    """Request to start an investigation."""
    case_id: str = Field(..., description="Case identifier")
    investigator_id: str = Field(..., description="ID of the investigator")


class InvestigationResponse(BaseModel):
    """Response from starting an investigation."""
    session_id: str
    case_id: str
    status: str
    message: str


class AgentFindingDTO(BaseModel):
    """Serializable subset of AgentFinding for frontend."""
    finding_id: str
    agent_id: str
    agent_name: str
    finding_type: str
    status: str
    confidence_raw: float
    calibrated: bool
    calibrated_probability: Optional[float] = None
    court_statement: Optional[str] = None
    robustness_caveat: bool
    robustness_caveat_detail: Optional[str] = None
    reasoning_summary: str


class ReportDTO(BaseModel):
    """Serializable subset of ForensicReport for frontend."""
    report_id: str
    session_id: str
    case_id: str
    executive_summary: str
    per_agent_findings: dict[str, list[AgentFindingDTO]]
    cross_modal_confirmed: list[AgentFindingDTO]
    # contested_findings and tribunal_resolved are serialized FindingComparison/TribunalCase objects
    contested_findings: list[dict]
    tribunal_resolved: list[dict]
    incomplete_findings: list[AgentFindingDTO]
    uncertainty_statement: str
    cryptographic_signature: str
    report_hash: str
    signed_utc: str


class HITLDecisionRequest(BaseModel):
    """Request for human-in-the-loop decision."""
    session_id: str
    checkpoint_id: str
    agent_id: str
    decision: Literal["APPROVE", "REDIRECT", "OVERRIDE", "TERMINATE", "ESCALATE"]
    note: Optional[str] = None
    override_finding: Optional[dict] = None


class HITLCheckpointDTO(BaseModel):
    """HITL checkpoint information."""
    checkpoint_id: str
    session_id: str
    agent_id: str
    agent_name: str
    brief_text: str
    decision_needed: str
    created_at: str


class BriefUpdate(BaseModel):
    """WebSocket message model."""
    type: Literal["AGENT_UPDATE", "HITL_CHECKPOINT", "AGENT_COMPLETE", "PIPELINE_COMPLETE", "PIPELINE_PAUSED", "CONNECTED", "ERROR"]
    session_id: str
    agent_id: Optional[str] = None
    agent_name: Optional[str] = None
    message: str
    data: Optional[dict[str, Any]] = None


class SessionInfo(BaseModel):
    """Session information."""
    session_id: str
    case_id: str
    status: str
    started_at: str


class ErrorResponse(BaseModel):
    """Error response."""
    detail: str
    error_code: Optional[str] = None
