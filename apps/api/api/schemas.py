"""
API Schemas for Forensic Council
=================================

Pydantic models for API request/response handling.
"""

from typing import Annotated, Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator


def _validate_password_bytes(v: str) -> str:
    """Shared validator: reject passwords that exceed bcrypt's 72-byte limit."""
    byte_length = len(v.encode("utf-8"))
    if byte_length > 72:
        raise ValueError(
            f"Password is {byte_length} UTF-8 bytes, which exceeds the 72-byte bcrypt "
            "limit. Please shorten your password."
        )
    return v


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
    calibrated_probability: float | None = (
        None  # DEPRECATED — use raw_confidence_score
    )
    raw_confidence_score: float | None = None
    calibration_status: str = "UNCALIBRATED"  # TRAINED or UNCALIBRATED
    court_statement: str | None = None
    robustness_caveat: bool
    robustness_caveat_detail: str | None = None
    reasoning_summary: str
    metadata: dict[str, Any] | None = (
        None  # includes analysis_phase, analysis_source, etc.
    )
    severity_tier: str = "LOW"  # INFO / LOW / MEDIUM / HIGH / CRITICAL


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
    signed_utc: str | None = None
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
    note: str | None = None
    override_finding: dict | None = None


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

    type: Literal[
        "AGENT_UPDATE",
        "HITL_CHECKPOINT",
        "AGENT_COMPLETE",
        "PIPELINE_COMPLETE",
        "PIPELINE_PAUSED",
        "CONNECTED",
        "ERROR",
    ]
    session_id: str
    agent_id: str | None = None
    agent_name: str | None = None
    message: str
    data: dict[str, Any] | None = None


class SessionInfo(BaseModel):
    """Session information."""

    session_id: str
    case_id: str
    status: str
    started_at: str


class ErrorResponse(BaseModel):
    """Error response."""

    detail: str
    error_code: str | None = None


class ReportStatusDTO(BaseModel):
    """Returned when the investigation is still in progress."""

    status: str = "in_progress"
    session_id: str
    message: str = "Investigation still in progress"


class ChangePasswordRequest(BaseModel):
    """Request to change the current user's password."""

    model_config = ConfigDict(extra="forbid")

    current_password: str = Field(..., description="The user's current password")
    new_password: str = Field(..., min_length=8, description="The desired new password")

    @field_validator("current_password", "new_password")
    @classmethod
    def password_within_bcrypt_limit(cls, v: str) -> str:
        return _validate_password_bytes(v)


class CreateUserRequest(BaseModel):
    """Request to create a new user (admin only)."""

    model_config = ConfigDict(extra="forbid")

    username: str = Field(..., min_length=3, max_length=64)
    password: str = Field(..., min_length=8, description="Initial password for the new user")
    role: Literal["admin", "investigator"] = "investigator"

    @field_validator("password")
    @classmethod
    def password_within_bcrypt_limit(cls, v: str) -> str:
        return _validate_password_bytes(v)
