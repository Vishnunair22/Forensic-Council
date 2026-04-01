"""
API Schemas for Forensic Council
=================================

Pydantic models for API request/response handling.
"""

from typing import Any, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field


class InvestigationRequest(BaseModel):
    """Request to start an investigation."""
    model_config = ConfigDict(extra="forbid")
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
    calibrated_probability: Optional[float] = None  # DEPRECATED — use raw_confidence_score
    raw_confidence_score: Optional[float] = None
    calibration_status: str = "UNCALIBRATED"  # TRAINED or UNCALIBRATED
    court_statement: Optional[str] = None
    robustness_caveat: bool
    robustness_caveat_detail: Optional[str] = None
    reasoning_summary: str
    metadata: Optional[dict[str, Any]] = None  # includes analysis_phase, analysis_source, etc.
    severity_tier: str = "LOW"   # INFO / LOW / MEDIUM / HIGH / CRITICAL


class AgentMetricsDTO(BaseModel):
    """Per-agent performance metrics for the result page."""
    agent_id: str
    agent_name: str
    total_tools_called: int = 0
    tools_succeeded: int = 0
    tools_failed: int = 0
    tools_not_applicable: int = 0
    error_rate: float = 0.0
    confidence_score: float = 0.0
    finding_count: int = 0
    skipped: bool = False


class ReportDTO(BaseModel):
    """Serializable subset of ForensicReport for frontend."""
    report_id: str
    session_id: str
    case_id: str
    executive_summary: str
    per_agent_findings: dict[str, list[AgentFindingDTO]] = Field(default_factory=dict)
    per_agent_metrics: dict[str, Any] = Field(default_factory=dict)
    per_agent_analysis: dict[str, str] = Field(default_factory=dict)
    overall_confidence: float = 0.0
    overall_error_rate: float = 0.0
    overall_verdict: str = "REVIEW REQUIRED"
    cross_modal_confirmed: list[AgentFindingDTO] = Field(default_factory=list)
    # contested_findings and tribunal_resolved are serialized FindingComparison/TribunalCase objects
    contested_findings: list[dict] = Field(default_factory=list)
    tribunal_resolved: list[dict] = Field(default_factory=list)
    incomplete_findings: list[AgentFindingDTO] = Field(default_factory=list)
    uncertainty_statement: str
    cryptographic_signature: str
    report_hash: str
    signed_utc: Optional[str] = None
    # Structured summary
    verdict_sentence: str = ""
    key_findings: list[str] = Field(default_factory=list)
    reliability_note: str = ""
    # Verdict enrichment
    manipulation_probability: float = 0.0
    # Confidence range across active agents (C)
    confidence_min: float = 0.0
    confidence_max: float = 0.0
    confidence_std_dev: float = 0.0
    # Agent coverage
    applicable_agent_count: int = 0
    skipped_agents: dict[str, str] = Field(default_factory=dict)
    analysis_coverage_note: str = ""
    # Flat per-agent summary (D)
    per_agent_summary: dict[str, Any] = Field(default_factory=dict)
    # Degradation transparency — non-empty means analysis ran in reduced-capability mode.
    # Must be surfaced as a visible warning in any UI, printout, or court exhibit.
    degradation_flags: list[str] = Field(default_factory=list)


class HITLDecisionRequest(BaseModel):
    """Request for human-in-the-loop decision."""
    model_config = ConfigDict(extra="forbid")
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
