"""
ReAct Loop Engine and HITL Checkpoint System for Forensic Council.

Implements the core THOUGHT → ACTION → OBSERVATION reasoning loop
with Human-in-the-Loop (HITL) checkpoints for forensic analysis.
"""

# NOTE: Future refactor should split this module into:
# - react_loop_engine.py (ReActLoopEngine class and core logic)
# - react_step_types.py (ReActStep, AgentFinding, ReActLoopResult models)
# - llm_step_generator.py (LLM-based step generation factory)
# This would improve maintainability and reduce the 1200+ line file size.

from __future__ import annotations

import asyncio
import json
import uuid
from collections.abc import Callable, Coroutine
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator, model_validator

from core.config import Settings
from core.custody_logger import CustodyLogger, EntryType
from core.finding_formatter import (
    TOOL_LABELS as _EXTRACTED_TOOL_LABELS,
)
from core.finding_formatter import (
    build_detailed_reasoning as _fmt_build_detailed_reasoning,
)
from core.finding_formatter import (
    build_readable_summary as _fmt_build_readable_summary,
)
from core.finding_formatter import (
    format_tool_result as _fmt_format_tool_result,
)
from core.finding_formatter import (
    shape_analyst_finding as _fmt_shape_analyst_finding,
)
from core.hitl import (
    HITLCheckpointReason,
    HITLCheckpointState,
    HITLCheckpointStatus,
    HumanDecision,
    HumanDecisionType,
)
from core.llm_client import LLMClient, LLMResponse, parse_llm_step
from core.observability import get_tracer
from core.structured_logging import get_logger
from core.task_tool_config import get_task_tool_overrides
from core.tool_output_classifier import ToolOutputClassifier
from core.tool_registry import ToolRegistry, ToolResult
from core.tracing import PipelineTrace
from core.working_memory import TaskStatus, WorkingMemory, WorkingMemoryState

logger = get_logger(__name__)
_tracer = get_tracer("forensic-council.react_loop")


class ReActStepType(StrEnum):
    """Types of steps in a ReAct loop."""

    THOUGHT = "THOUGHT"
    ACTION = "ACTION"
    OBSERVATION = "OBSERVATION"


class ReActStep(BaseModel):
    """A single step in the ReAct reasoning chain."""

    step_type: Literal["THOUGHT", "ACTION", "OBSERVATION"] = Field(
        ..., description="Type of reasoning step"
    )
    content: str = Field(..., description="The content of the step")
    tool_name: str | None = Field(default=None, description="Tool name if ACTION step")
    tool_input: dict[str, Any] | None = Field(default=None, description="Tool input if ACTION step")
    tool_output: dict[str, Any] | None = Field(
        default=None, description="Tool output if OBSERVATION step"
    )
    iteration: int = Field(..., description="Current iteration number")
    timestamp_utc: datetime = Field(
        default_factory=lambda: datetime.now(UTC),
        description="UTC timestamp of the step",
    )


# --- RE-EXPORTS for backward compatibility ---
# These models are now located in core/hitl.py
# Re-exported here to avoid breaking existing imports.
__all__ = [
    "ReActLoopEngine",
    "ReActStep",
    "ReActStepType",
    "AgentFinding",
    "AgentFindingStatus",
    "ReActLoopResult",
    "HITLCheckpointReason",
    "HITLCheckpointStatus",
    "HITLCheckpointState",
    "HumanDecisionType",
    "HumanDecision",
]


class AgentFindingStatus(StrEnum):
    """Status of an agent finding."""

    CONFIRMED = "CONFIRMED"
    CONTESTED = "CONTESTED"
    INCONCLUSIVE = "INCONCLUSIVE"
    INCOMPLETE = "INCOMPLETE"
    NOT_APPLICABLE = "NOT_APPLICABLE"
    ABSTAIN = "ABSTAIN"


class AgentFinding(BaseModel):
    """A finding produced by an agent."""

    finding_id: uuid.UUID = Field(
        default_factory=uuid.uuid4, description="Unique finding identifier"
    )
    agent_id: str = Field(..., description="Agent that produced the finding")
    agent_name: str = Field(default="", description="Human-readable name of the agent")
    finding_type: str = Field(..., description="Type of finding")
    confidence_raw: float | None = Field(
        default=None,
        ge=0.0,
        le=1.0,
        description=(
            "Raw confidence score (0-1).  MUST be None when "
            "evidence_verdict is NOT_APPLICABLE or ERROR.  Nullable "
            "to enforce the semantic contract that not-applicable "
            "findings carry no confidence."
        ),
    )
    raw_confidence_score: float | None = Field(
        default=None,
        ge=0.0,
        le=1.0,
        description="Rescaled confidence score (Platt sigmoid), None if not rescaled",
    )
    calibrated: bool = Field(default=False, description="Whether confidence has been calibrated")
    calibration_status: str = Field(
        default="UNCALIBRATED",
        description="TRAINED if parameters were fitted to data, UNCALIBRATED if engineering defaults",
    )
    evidence_verdict: str = Field(
        default="INCONCLUSIVE",
        description=(
            "Strict semantic verdict from the EvidenceVerdict enum: "
            "POSITIVE, NEGATIVE, INCONCLUSIVE, NOT_APPLICABLE, ERROR. "
            "Every finding MUST carry this field.  Downstream consumers "
            "MUST check evidence_verdict before interpreting confidence."
        ),
    )
    status: Literal[
        "CONFIRMED",
        "CONTESTED",
        "INCONCLUSIVE",
        "INCOMPLETE",
        "NOT_APPLICABLE",
        "ABSTAIN",
    ] = Field(default="CONFIRMED", description="Finding status")
    robustness_caveat: bool = Field(
        default=False, description="Whether finding has robustness caveat"
    )
    robustness_caveat_detail: str | None = Field(
        default=None, description="Detail about robustness caveat"
    )
    evidence_refs: list[uuid.UUID] = Field(
        default_factory=list, description="References to evidence artifacts"
    )
    reasoning_summary: str = Field(
        default="", description="Summary of reasoning that led to finding"
    )
    extracted_text: list[str] = Field(
        default_factory=list, description="Text extracted from image via OCR"
    )
    metadata: dict[str, Any] = Field(
        default_factory=dict,
        description="Additional metadata including tool results and court_defensible flag",
    )

    @field_validator("metadata", mode="before")
    @classmethod
    def ensure_metadata_is_dict(cls, v: Any) -> dict[str, Any]:
        return v if v is not None else {}

    @model_validator(mode="after")
    def enforce_confidence_verdict_contract(self) -> AgentFinding:
        no_confidence_verdicts = {"NOT_APPLICABLE", "ERROR"}
        if self.evidence_verdict in no_confidence_verdicts and self.confidence_raw is not None:
            raise ValueError(
                f"confidence_raw must be None when evidence_verdict is {self.evidence_verdict!r}"
            )
        return self


class ReActLoopResult(BaseModel):
    """Result of a completed ReAct loop."""

    session_id: uuid.UUID = Field(..., description="Session ID")
    agent_id: str = Field(..., description="Agent ID")
    completed: bool = Field(default=False, description="Whether loop completed normally")
    terminated_by_human: bool = Field(
        default=False, description="Whether loop was terminated by human"
    )
    findings: list[AgentFinding] = Field(default_factory=list, description="Findings produced")
    hitl_checkpoints: list[HITLCheckpointState] = Field(
        default_factory=list, description="HITL checkpoints encountered"
    )
    total_iterations: int = Field(default=0, description="Total iterations run")
    react_chain: list[ReActStep] = Field(default_factory=list, description="Full reasoning chain")


# Type for LLM step generators - async function that returns next ReActStep
LLMStepGenerator = Callable[
    [list[ReActStep], WorkingMemoryState], Coroutine[Any, Any, ReActStep | None]
]


def create_llm_step_generator(
    llm_client: LLMClient,
    config: Settings,
    agent_name: str,
    evidence_context: dict[str, Any],
) -> LLMStepGenerator:
    """
    Create an LLM-based step generator for the ReAct loop.

    This factory creates a step generator that uses the LLM to reason about
    tool outputs and decide the next action, enabling true ReAct reasoning
    rather than just task decomposition.

    Args:
        llm_client: Initialized LLM client
        config: Application settings
        agent_name: Name of the agent for context
        evidence_context: Context about the evidence being analyzed

    Returns:
        LLMStepGenerator function that can be passed to ReActLoopEngine.run()
    """

    async def llm_step_generator(
        react_chain: list[ReActStep],
        state: WorkingMemoryState,
    ) -> ReActStep | None:
        """Generate next ReAct step using LLM reasoning."""

        # Skip if LLM is not enabled
        if (
            not config.llm_enable_react_reasoning
            or not config.llm_api_key
            or not llm_client.is_available
        ):
            return None

        # Build system prompt with forensic context
        system_prompt = _build_forensic_system_prompt(
            agent_name=agent_name,
            evidence_context=evidence_context,
            available_tasks=[t.description for t in state.tasks if t.status != "COMPLETE"],
        )

        # Get available tools from state/tool registry context
        available_tools = _get_available_tools_for_llm(state)

        # Get current task
        current_task = None
        for task in state.tasks:
            if task.status == "IN_PROGRESS":
                current_task = task.description
                break

        from core.config import get_settings as _get_settings

        # M-C-2: hard upper-bound for one reasoning step. generate_reasoning
        # _step internally iterates up to (4 candidates × 3 retries × llm_
        # timeout) ≈ 3+ minutes in pathological cases; the existing per-call
        # timeout is on the httpx layer only. This budget covers the entire
        # candidate fallback chain so a single ReAct iteration cannot exceed
        # ~2× llm_timeout regardless of provider flapping.
        _llm_budget = float(_get_settings().llm_timeout) * 2.0

        async def _attempt_llm_call() -> LLMResponse:
            return await asyncio.wait_for(
                llm_client.generate_reasoning_step(
                    system_prompt=system_prompt,
                    react_chain=[step.model_dump() for step in react_chain],
                    available_tools=available_tools,
                    current_task=current_task,
                ),
                timeout=_llm_budget,
            )

        def _parse_response(response: LLMResponse) -> ReActStep:
            """Strip markdown fences from content before parsing, then build step."""
            content = response.content or ""
            # Strip fences from text content so JSON embedded in fences doesn't
            # confuse the text-based action parser (tool_call path is already
            # handled in LLMClient._parse_openai_response).
            stripped = content.strip()
            if stripped.startswith("```"):
                first_nl = stripped.find("\n")
                if first_nl != -1:
                    stripped = stripped[first_nl + 1 :]
                else:
                    stripped = stripped[3:]
            if stripped.endswith("```"):
                stripped = stripped[: stripped.rfind("```")]
            stripped = stripped.strip()
            # Use stripped content only when no tool_call; preserve original
            # content for display when the model adds prose around fences.
            effective_content = stripped if not response.tool_call else content
            parsed = parse_llm_step(effective_content, response.tool_call)
            return ReActStep(
                step_type=parsed["step_type"],  # type: ignore[arg-type]
                content=parsed["content"],
                tool_name=parsed.get("tool_name"),
                tool_input=parsed.get("tool_input"),
                iteration=len(react_chain) + 1,
            )

        last_exc: BaseException | None = None
        for attempt in range(2):
            try:
                response: LLMResponse = await _attempt_llm_call()
                step = _parse_response(response)
                logger.info(
                    "LLM generated ReAct step",
                    agent_name=agent_name,
                    step_type=step.step_type,
                    tool_name=step.tool_name,
                    attempt=attempt,
                )
                return step
            except Exception as exc:
                last_exc = exc
                if attempt == 0:
                    logger.warning(
                        "LLM step generation failed on attempt 1; retrying once",
                        error=str(exc),
                        agent_name=agent_name,
                    )
                else:
                    logger.error(
                        "LLM step generation failed on both attempts; emitting THOUGHT fallback",
                        error=str(exc),
                        agent_name=agent_name,
                        exc_info=True,
                    )

        # Both attempts failed — emit a sanitized THOUGHT so the ReAct loop
        # continues without a hard stop instead of returning None and silently
        # stalling task decomposition.
        sanitized_reason = str(last_exc)[:120] if last_exc else "unknown error"
        return ReActStep(
            step_type="THOUGHT",
            content=(
                f"LLM reasoning unavailable ({sanitized_reason}). "
                "Proceeding with task-decomposition fallback."
            ),
            iteration=len(react_chain) + 1,
        )

    return llm_step_generator


def _build_forensic_system_prompt(
    agent_name: str,
    evidence_context: dict[str, Any],
    available_tasks: list[str],
) -> str:
    """
    Build a forensic-grade system prompt for the ReAct loop.

    The prompt:
    - Establishes the agent's exact forensic mandate and role identity
    - Gives structured guidance on evidence interpretation
    - Lists ALL outstanding tasks (not capped at 5)
    - Specifies court-admissible reasoning standards
    - Tells the model how to signal completion
    """
    mime_type = evidence_context.get("mime_type", "unknown")
    file_name = evidence_context.get("file_name", "unknown")
    file_size = evidence_context.get("file_size_bytes", "")
    file_hash = evidence_context.get("sha256", "")

    def _sanitize(val: Any) -> str:
        s = str(val) if val is not None else ""
        s = s.replace("\r", " ").replace("\n", " ")
        import re as _re

        s = _re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]", "", s)
        # Prompt injection hardening: escape potential instruction overrides
        injection_patterns = [
            r"(?i)ignore\s+(previous|all\s+|above)\s+(instructions|prompts|commands)",
            r"(?i)forget\s+(everything|all\s+|your\s+)instructions",
            r"(?i)new\s+instruction",
            r"(?i)you\s+are\s+(now|actually)\s+",
            r"(?i)instead\s+(of|use)",
            r"(?i)verdict\s*=\s*",
        ]
        for pattern in injection_patterns:
            s = _re.sub(pattern, "[FILTERED]", s)
        return s

    file_name = _sanitize(file_name)
    file_hash = _sanitize(file_hash)
    agent_name_safe = _sanitize(agent_name)

    # Build agent-specific mandate from name
    mandates = {
        "Agent1": "pixel-level image integrity — ELA, splicing, copy-move, noise fingerprinting, perceptual hashing",
        "Agent2": "audio authenticity — speaker diarization, anti-spoofing, prosody, splice detection, codec fingerprinting",
        "Agent3": "scene and object integrity — lighting consistency, shadow direction, semantic incongruence, object detection",
        "Agent4": "temporal video integrity — optical flow, frame consistency, face-swap detection, rolling shutter, deepfake frequency analysis",
        "Agent5": "metadata and provenance — EXIF extraction, GPS-timestamp validation, steganography, file structure, hex signatures",
        "Arbiter": "cross-modal deliberation — synthesising all agent findings into a court-admissible verdict",
    }
    agent_key = next((k for k in mandates if k.lower() in agent_name.lower()), None)
    mandate = mandates.get(agent_key or "", "multi-modal forensic analysis of the submitted evidence")

    size_line = f"  File size: {file_size} bytes\n" if file_size else ""
    hash_line = f"  SHA-256:   {file_hash}\n" if file_hash else ""

    tasks_block = "\n".join(f"  {i + 1}. {t}" for i, t in enumerate(available_tasks))

    prompt = f"""You are {agent_name_safe}, a specialist forensic analysis agent in the Forensic Council multi-agent system.

== EVIDENCE UNDER ANALYSIS ==
  File:      {file_name}
  MIME type: {mime_type}
{size_line}{hash_line}
== YOUR MANDATE ==
Your specialisation is {mandate}.

You operate in a legally accountable context. Your findings may be used in court proceedings.
Every conclusion must be grounded in tool output. Never speculate beyond what the evidence shows.

== REASONING PROTOCOL (ReAct) ==
Each turn you MUST do exactly ONE of:
  A) THINK — reason about what the current observations tell you and what the next
     most informative tool call would be. Be specific about WHY you are choosing
     the next tool. Reference previous observations explicitly.
  B) ACT   — call a tool using the function-calling interface. Pass the correct
     arguments. Do not hallucinate tool names; only use tools in the provided list.
  C) CONCLUDE — when all tasks are complete or you have sufficient evidence, write
     a High-Density Tactical Report of your findings. State: finding type, confidence (0.0-1.0),
     precise objects/anomalies detected (with spatial/metadata context), and any limitations. Then signal completion.

== OUTSTANDING TASKS ==
{tasks_block}

== FORENSIC STANDARDS ==
- Confidence scores must reflect actual tool output, not intuition.
- If a tool returns an error or unavailable result, log it and move on.
- Cross-reference findings across tools where possible.
- Distinguish CONFIRMED (multiple tools agree) from INDICATIVE (single tool) findings.
- Never fabricate data. If evidence is ambiguous, say so explicitly.
- When complete, begin your response with: "ANALYSIS COMPLETE:" followed by a
  High-Density Tactical Report covering:
  WEAPONS/CONTRABAND: [List specific items, locations, and confidence]
  SPLICING/LIGHTING ANOMALIES: [Detail shadow angles, specific ELA deviations, noise patterns]
  METADATA DISCREPANCIES: [Timestamp offsets, GPS mismatches, missing fields]
  CONCLUSION: [Final tactical summary]."""

    return prompt


def _get_available_tools_for_llm(state: WorkingMemoryState) -> list[dict[str, Any]]:
    """
    Return the full set of tools registered in the current agent's tool registry,
    formatted for LLM function-calling.

    Reads from state.tool_registry_snapshot if available (populated by base_agent
    before the ReAct loop starts). Falls back to a comprehensive static catalogue
    so the LLM always has accurate tool names even without a live registry.
    """
    # Use live registry snapshot if the base agent injected it
    registry_snapshot: list[dict] | None = getattr(state, "tool_registry_snapshot", None)
    if registry_snapshot:
        return registry_snapshot

    logger.warning(
        "tool_registry_snapshot not injected by base agent — falling back to static "
        "tool catalogue; LLM may suggest tools that are not registered for this agent"
    )
    # Comprehensive fallback catalogue — covers all real tools across all 5 agents
    return [
        # Agent 1 — Image
        {
            "name": "ela_full_image",
            "description": "Full-image Error Level Analysis — detects re-saved or spliced regions",
        },
        {
            "name": "ela_anomaly_classify",
            "description": "IsolationForest classification of ELA anomaly blocks",
        },
        {
            "name": "roi_extract",
            "description": "Extract Region of Interest bounding boxes from anomaly map",
        },
        {
            "name": "jpeg_ghost_detect",
            "description": "Detect JPEG re-compression ghosts (double-save artifacts)",
        },
        {
            "name": "frequency_domain_analysis",
            "description": "FFT spectral analysis — detect GAN/Stable Diffusion frequency artifacts",
        },
        {
            "name": "splicing_detect",
            "description": "DCT quantization table inconsistency — identifies spliced regions",
        },
        {
            "name": "noise_fingerprint",
            "description": "PRNU camera noise fingerprint — detects inconsistent sensor patterns",
        },
        {
            "name": "deepfake_frequency_check",
            "description": "GAN deepfake artifact detection in frequency domain",
        },
        {
            "name": "file_hash_verify",
            "description": "SHA-256 hash verification — confirms file integrity",
        },
        {
            "name": "neural_fingerprint",
            "description": "pHash perceptual similarity hash for near-duplicate detection",
        },
        {
            "name": "neural_copy_move",
            "description": "SIFT keypoint self-matching — detects copy-move forgery",
        },
        {
            "name": "extract_text_from_image",
            "description": "Tesseract OCR — extract visible text from image evidence",
        },
        {
            "name": "extract_evidence_text",
            "description": "Auto-dispatching OCR: PDF->PyMuPDF, Image->EasyOCR->Tesseract",
        },
        {
            "name": "analyze_image_content",
            "description": "CLIP semantic understanding — identify objects, scenes, context",
        },
        {
            "name": "visual_evidence_profile",
            "description": (
                "Shared visual evidence profile — local or configured-provider "
                "analysis of authenticity, objects, text, and routing context"
            ),
        },
        {
            "name": "gemini_deep_forensic",
            "description": "Deprecated alias for shared visual evidence profile",
        },
        # No-API fallback tools
        {
            "name": "reverse_image_search",
            "description": "Google reverse image search for online provenance (no API key required)",
        },
        {
            "name": "lens_style_multimodal_scan",
            "description": "On-device multi-modal scan with OCR, barcode, object, and logo analysis (no API key)",
        },
        # Agent 2 — Audio
        {
            "name": "speaker_diarize",
            "description": "Neural speaker diarization — count and segment speakers",
        },
        {
            "name": "anti_spoofing_detect",
            "description": "Neural audio anti-spoofing — detect synthetic/replayed speech",
        },
        {
            "name": "prosody_analyze",
            "description": "Praat prosody analysis — F0, jitter, shimmer, HNR",
        },
        {
            "name": "audio_splice_detect",
            "description": "ML splice point detection in audio waveform",
        },
        {
            "name": "background_noise_analysis",
            "description": "Background noise consistency across audio segments",
        },
        {
            "name": "codec_fingerprinting",
            "description": "Audio codec and encoding chain fingerprinting",
        },
        {
            "name": "visual_evidence_profile",
            "description": "Shared visual evidence profile — local or configured-provider analysis",
        },
        {
            "name": "gemini_deep_forensic",
            "description": "Deprecated alias for shared visual evidence profile",
        },
        # Agent 3 — Scene
        {
            "name": "object_detection",
            "description": "YOLOv8 object detection on full scene",
        },
        {
            "name": "lighting_consistency",
            "description": "Shadow direction and lighting consistency validation",
        },
        {
            "name": "scene_incongruence",
            "description": "CLIP semantic incongruence — objects that do not belong in scene",
        },
        {
            "name": "vector_contraband_search",
            "description": "SigLIP vector search for weapons and contraband concepts",
        },
        {
            "name": "lighting_correlation_initial",
            "description": "Initial lighting-vector correlation for compositing candidates",
        },
        {
            "name": "scale_validation",
            "description": "Object scale and proportion validation",
        },
        # Agent 4 — Video
        {
            "name": "optical_flow_analysis",
            "description": "Dense optical flow analysis — detect frame discontinuities",
        },
        {
            "name": "frame_extraction",
            "description": "Extract frame window for per-frame analysis",
        },
        {
            "name": "frame_consistency_analysis",
            "description": "Frame-to-frame histogram and edge consistency",
        },
        {
            "name": "face_swap_detection",
            "description": "DeepFace embedding comparison — detect face swap events",
        },
        # rPPG liveness is QUARANTINED — not registered by Agent4.
        # Do NOT list it here or the LLM may hallucinate a call to it.
        {
            "name": "video_metadata",
            "description": "Extract video container metadata",
        },
        {
            "name": "vfi_error_map",
            "description": "Video frame interpolation error mapping for motion inconsistencies",
        },
        {
            "name": "thumbnail_coherence",
            "description": "Embedded-thumbnail coherence check against video content",
        },
        {
            "name": "interframe_forgery_detector",
            "description": "Interframe forgery detection for motion ghosting and SSIM variance",
        },
        {
            "name": "rolling_shutter_validation",
            "description": "Rolling shutter signature validation against claimed device metadata",
        },
        {
            "name": "mediainfo_profile",
            "description": "Deep AV container profiling: codec, VFR flag, encoding tool, forensic flags",
        },
        {
            "name": "av_file_identity",
            "description": "Lightweight AV pre-screen: format, codec, duration, high-severity flags",
        },
        # Agent 5 — Metadata
        {
            "name": "exif_extract",
            "description": "Full EXIF extraction via ExifTool + hachoir including MakerNotes",
        },
        {
            "name": "metadata_anomaly_score",
            "description": "IsolationForest ML anomaly score on metadata fields",
        },
        {
            "name": "gps_timezone_validate",
            "description": "Cross-validate GPS coordinates against claimed timestamp timezone",
        },
        {
            "name": "steganography_scan",
            "description": "LSB steganography detection in image data",
        },
        {
            "name": "file_structure_analysis",
            "description": "Binary file structure forensic analysis — detect appended data",
        },
        {
            "name": "hex_signature_scan",
            "description": "Hex signature scan for hidden editing software watermarks",
        },
        {
            "name": "timestamp_analysis",
            "description": "Timestamp consistency analysis across all metadata fields",
        },
        {
            "name": "exif_isolation_forest",
            "description": "Isolation Forest outlier detection for EXIF metadata fields",
        },
        {
            "name": "astro_grounding",
            "description": "Shadow/sun/GPS/timestamp astronomical grounding",
        },
    ]


TOOL_TIMEOUT_POLICY = {
    "noiseprint_cluster": 300.0,
    "noise_fingerprint": 240.0,
    "neural_splicing": 180.0,
    "ela_full_image": 120.0,
    "object_detection": 120.0,
    "vector_contraband_search": 120.0,
}


class ReActLoopEngine:
    """
    Core ReAct (Reasoning + Acting) loop engine.

    Implements the THOUGHT → ACTION → OBSERVATION cycle with:
    - Human-in-the-Loop checkpoints at trigger conditions
    - Graceful degradation on tool unavailability
    - Full audit logging to chain of custody
    """

    # Task→tool mapping loaded from config/task_tool_overrides.yaml.
    # Accessed via property so the YAML is loaded lazily on first use.
    _TASK_TOOL_OVERRIDES_CACHE: dict[str, str] | None = None

    _AGENT_ID_TO_NAME: dict[str, str] = {
        "Agent1": "Image Forensics",
        "Agent2": "Audio Forensics",
        "Agent3": "Object Detection",
        "Agent4": "Video Forensics",
        "Agent5": "Metadata Forensics",
        "Agent1_deep": "Image Forensics",
        "Agent2_deep": "Audio Forensics",
        "Agent3_deep": "Object Detection",
        "Agent4_deep": "Video Forensics",
        "Agent5_deep": "Metadata Forensics",
    }

    _TOOL_LABELS: dict[str, str] = _EXTRACTED_TOOL_LABELS

    @classmethod
    def _get_task_tool_overrides(cls) -> dict[str, str]:
        """Load task→tool overrides from YAML config (cached)."""
        if cls._TASK_TOOL_OVERRIDES_CACHE is None:
            cls._TASK_TOOL_OVERRIDES_CACHE = get_task_tool_overrides()
        return cls._TASK_TOOL_OVERRIDES_CACHE

    def __init__(
        self,
        agent_id: str,
        session_id: uuid.UUID,
        iteration_ceiling: int,
        working_memory: WorkingMemory,
        custody_logger: CustodyLogger,
        redis_client: Any = None,
        hitl_timeout: float = 3600.0,
        heavy_tool_semaphore: asyncio.Semaphore | None = None,
        agent: Any | None = None,
        per_tool_timeout: float = 120.0,
        enable_internal_hitl: bool = True,
    ) -> None:
        """
        Initialize the ReAct loop engine.

        Args:
            agent_id: ID of the agent running this loop
            session_id: Session ID for this analysis
            iteration_ceiling: Maximum iterations before forced stop
            working_memory: Working memory for task tracking
            custody_logger: Logger for chain of custody
            redis_client: Redis client for HITL checkpoint storage
            hitl_timeout: Timeout in seconds for waiting on HITL resume (default 3600s = 1 hour)
            heavy_tool_semaphore: Shared semaphore for throttling heavy CPU/GPU tools
            per_tool_timeout: Per-tool execution timeout in seconds (default 120s).
                              Prevents a single slow tool from hanging the entire deep pass.
            enable_internal_hitl: Whether the loop may block on an agent-local
                checkpoint. Full investigations disable this because the
                orchestration layer owns the analyst decision gate.
        """
        self.agent_id = agent_id
        self.session_id = session_id
        self.iteration_ceiling = iteration_ceiling
        self.working_memory = working_memory
        self.custody_logger = custody_logger
        self.redis_client = redis_client
        self.hitl_timeout = hitl_timeout
        self.heavy_tool_semaphore = heavy_tool_semaphore
        self.agent = agent
        self.per_tool_timeout = per_tool_timeout
        self.enable_internal_hitl = enable_internal_hitl

        # Internal state
        self._current_iteration = 0
        self._react_chain: list[ReActStep] = []
        self._findings: list[AgentFinding] = []
        self._hitl_checkpoints: list[HITLCheckpointState] = []
        self._terminated = False
        self._current_checkpoint: HITLCheckpointState | None = None
        self._resume_event: asyncio.Event | None = None
        self._pending_decision: HumanDecision | None = None
        self._thought_buffer: list[str] = []  # M1: Captures multiple thoughts before an action

        # Initialize reasoning service
        from core.agent_reasoning import AgentReasoningService
        bus = getattr(agent, "inter_agent_bus", None)
        self.reasoning_service = AgentReasoningService(inter_agent_bus=bus)

    def _extract_confidence(self, output: Any, tool_name: str) -> tuple[float, bool]:
        """Extract a 0-1 confidence score from tool output. Returns (confidence, from_fallback)."""
        return ToolOutputClassifier.extract_confidence(output, tool_name, self.agent_id)

    @staticmethod
    def _has_not_applicable_marker(output: dict[str, Any]) -> bool:
        return ToolOutputClassifier.has_not_applicable_marker(output)

    @staticmethod
    def _looks_like_condition_skip(output: dict[str, Any]) -> bool:
        return ToolOutputClassifier.looks_like_condition_skip(output)

    @staticmethod
    def _positive_signal(output: dict[str, Any]) -> bool:
        return ToolOutputClassifier.positive_signal(output)

    def _classify_tool_output(
        self,
        output: Any,
        tool_name: str,
        confidence: float,
        conf_from_fallback: bool,
    ) -> tuple[str, str, float | None, bool]:
        """
        Convert heterogeneous tool output into the strict evidence contract.

        Returns (status, evidence_verdict, confidence_or_none, court_defensible).
        """
        return ToolOutputClassifier.classify(output, tool_name, confidence, conf_from_fallback)

    async def _handle_hitl_pause(
        self, checkpoint: HITLCheckpointState, hitl_reason: HITLCheckpointReason
    ) -> bool:
        """Wait for human decision at a HITL checkpoint. Returns True if loop should terminate."""
        self._resume_event = asyncio.Event()

        if self._pending_decision is None:
            try:
                await asyncio.wait_for(self._resume_event.wait(), timeout=self.hitl_timeout)
            except TimeoutError:
                try:
                    if self.custody_logger is not None:
                        await self.custody_logger.log_entry(
                            entry_type=EntryType.HITL_CHECKPOINT,
                            agent_id=self.agent_id,
                            session_id=self.session_id,
                            content={
                                "event": "HITL_TIMEOUT",
                                "checkpoint_id": str(checkpoint.checkpoint_id),
                                "reason": hitl_reason.value,
                                "timeout_seconds": self.hitl_timeout,
                                "iteration": self._current_iteration,
                            },
                        )
                except Exception as exc:
                    logger.debug(
                        "Failed to log HITL timeout",
                        agent_id=self.agent_id,
                        error=str(exc),
                    )
                self._terminated = True
                self._resume_event.clear()
                return True

        if self._pending_decision is not None:
            await self.resume_from_hitl(checkpoint.checkpoint_id, self._pending_decision)
            self._pending_decision = None
            self._resume_event.clear()

        return self._terminated

    async def _update_task_complete(self, step: ReActStep) -> None:
        """Mark the working-memory task associated with a completed tool call as COMPLETE."""
        _task_id_str = (step.tool_input or {}).get("_task_id")
        _wm_updated = False

        if _task_id_str:
            try:
                from uuid import UUID as _UUID

                await self.working_memory.update_task(
                    session_id=self.session_id,
                    agent_id=self.agent_id,
                    task_id=_UUID(_task_id_str),
                    status=TaskStatus.COMPLETE,
                    result_ref=step.tool_name,
                )
                _wm_updated = True
            except Exception as err:
                logger.warning(
                    f"Direct task COMPLETE failed for {_task_id_str}: {err}", agent_id=self.agent_id
                )

        if not _wm_updated:
            try:
                fresh_state = await self.working_memory.get_state(
                    session_id=self.session_id, agent_id=self.agent_id
                )
                if fresh_state:
                    for task in fresh_state.tasks:
                        if task.status == TaskStatus.IN_PROGRESS:
                            await self.working_memory.update_task(
                                session_id=self.session_id,
                                agent_id=self.agent_id,
                                task_id=task.task_id,
                                status=TaskStatus.COMPLETE,
                                result_ref=step.tool_name,
                            )
                            _wm_updated = True
                            break
            except Exception as err:
                logger.warning(f"WM scan task COMPLETE failed: {err}", agent_id=self.agent_id)

        if not _wm_updated:
            try:
                cache_state = await self.working_memory.get_state(
                    session_id=self.session_id, agent_id=self.agent_id
                )
                if cache_state:
                    for task in cache_state.tasks:
                        if task.status == TaskStatus.IN_PROGRESS:
                            task.status = TaskStatus.COMPLETE
                            task.result_ref = step.tool_name
                            _wm_updated = True
                    key = self.working_memory._get_key(self.session_id, self.agent_id)
                    self.working_memory._local_cache[key] = cache_state.model_dump_json()
            except Exception as exc:
                logger.debug(
                    "Local working-memory task completion fallback failed",
                    agent_id=self.agent_id,
                    error=str(exc),
                )

        if not _wm_updated:
            try:
                await self.working_memory.get_state(
                    session_id=self.session_id, agent_id=self.agent_id
                )
            except Exception as exc:
                if "No working memory found" in str(exc):
                    logger.info(
                        "Task completion skipped because working memory was already cleared",
                        agent_id=self.agent_id,
                        task_id=_task_id_str,
                        tool=step.tool_name,
                    )
                    return
            logger.error(
                "All task-completion fallbacks exhausted — task remains IN_PROGRESS; "
                "next iteration may re-run the same tool and produce duplicate findings",
                agent_id=self.agent_id,
                task_id=_task_id_str,
                tool=step.tool_name,
            )

    async def run(
        self,
        initial_thought: str,
        tool_registry: ToolRegistry,
        llm_generator: LLMStepGenerator | None = None,
    ) -> ReActLoopResult:
        """
        Run the ReAct loop from an initial thought.

        Args:
            initial_thought: The starting thought for the loop
            tool_registry: Registry of available tools
            llm_generator: Async function that generates next step from LLM.
                          If None, uses a simple mock that signals completion.

        Returns:
            ReActLoopResult with findings and reasoning chain
        """
        # Initialize working memory state
        try:
            state = await self.working_memory.get_state(
                session_id=self.session_id, agent_id=self.agent_id
            )
        except (ConnectionError, TimeoutError, OSError) as e:
            logger.debug(
                "Working memory read failed on init (transient?)",
                agent_id=self.agent_id,
                error=str(e),
            )
            state = None
        except Exception as e:
            logger.warning(
                "Working memory read failed on init (unexpected)",
                agent_id=self.agent_id,
                error=str(e),
                exc_info=True,
            )
            state = None

        with _tracer.start_as_current_span("react_loop.run") as _loop_span:
            _loop_span.set_attribute("agent_id", self.agent_id)
            _loop_span.set_attribute("session_id", str(self.session_id))
            _loop_span.set_attribute("iteration_ceiling", self.iteration_ceiling)

        # Log LLM availability for the run
        if llm_generator is not None:
            logger.debug(f"ReAct loop {self.agent_id}: LLM reasoning available")
        else:
            logger.info(f"ReAct loop {self.agent_id}: NO-LLM mode (task decomposition only)")

        # Create initial THOUGHT step
        initial_step = ReActStep(step_type="THOUGHT", content=initial_thought, iteration=0)
        self._react_chain.append(initial_step)
        self._thought_buffer.append(initial_thought)  # M1: Seed buffer with initial context
        await self._log_step(initial_step)

        self._current_iteration = 0
        _consecutive_thoughts = 0  # guard: force tool call after N pure-THOUGHT iterations

        # Main loop — increment BEFORE the body so iteration_ceiling is respected exactly
        while not self._terminated and self._current_iteration < self.iteration_ceiling:
            self._current_iteration += 1
            # Get current state
            try:
                state = await self.working_memory.get_state(
                    session_id=self.session_id, agent_id=self.agent_id
                )
            except (ConnectionError, TimeoutError, OSError) as e:
                logger.debug(
                    "Working memory read failed in loop (transient?)",
                    agent_id=self.agent_id,
                    iteration=self._current_iteration,
                    error=str(e),
                )
                state = None
            except Exception as e:
                logger.warning(
                    "Working memory read failed in loop (unexpected)",
                    agent_id=self.agent_id,
                    iteration=self._current_iteration,
                    error=str(e),
                    exc_info=True,
                )
                state = None
            if state is None:
                break

            # Check HITL triggers before proceeding
            hitl_reason = (
                await self.check_hitl_triggers(state)
                if self.enable_internal_hitl
                else None
            )
            if hitl_reason is not None:
                checkpoint = await self.pause_for_hitl(
                    reason=hitl_reason,
                    brief=f"Paused at iteration {self._current_iteration} due to {hitl_reason.value}",
                )
                self._hitl_checkpoints.append(checkpoint)
                if await self._handle_hitl_pause(checkpoint, hitl_reason):
                    break

            # Get next step from LLM or built-in task driver
            next_step = None
            if llm_generator is not None:
                next_step = await llm_generator(self._react_chain, state)

            # If LLM returned None (failure, not configured, or no suggestion),
            # fall back to the built-in task-decomposition driver so agents
            # still produce real tool-based findings without LLM reasoning.
            if next_step is None:
                next_step = await self._default_step_generator(state, tool_registry)

            if next_step is None:
                # Both LLM and task driver signal completion.
                # Check for untreated absences via self-reflection.
                injected_any = False
                if self.agent and hasattr(self.agent, "self_reflection_pass") and self._current_iteration < self.iteration_ceiling:
                    try:
                        report = await self.agent.self_reflection_pass(self._findings or [])
                        if report is None:
                            raise ValueError("self_reflection_pass returned None")
                        untreated = getattr(report, "untreated_absences", None) or []
                        for absence in untreated:
                            if "MISSING_PRNU_ANALYSIS" in absence:
                                has_np = False
                                for t in state.tasks:
                                    if "noiseprint" in t.description.lower() or "noise_fingerprint" in t.description.lower():
                                        has_np = True
                                        break
                                if not has_np:
                                    desc = "Run noiseprint_cluster for sensor-region source inconsistency" if getattr(self.agent, "_is_lossless", False) else "Run noise_fingerprint for sensor-level consistency check"
                                    await self.agent.inject_task(desc, priority=5)
                                    injected_any = True
                            elif "MISSING_EXIF_DATA" in absence:
                                has_exif = False
                                for t in state.tasks:
                                    if "exif" in t.description.lower():
                                        has_exif = True
                                        break
                                if not has_exif:
                                    await self.agent.inject_task("Run exif_extract for metadata check", priority=5)
                                    injected_any = True
                    except Exception as ref_err:
                        logger.warning(
                            "Self-reflection task injection failed",
                            agent_id=self.agent_id,
                            error=str(ref_err),
                        )

                if injected_any:
                    # Re-read state and get the next step
                    try:
                        state = await self.working_memory.get_state(
                            session_id=self.session_id, agent_id=self.agent_id
                        )
                        next_step = await self._default_step_generator(state, tool_registry)
                    except Exception:
                        next_step = None

                if next_step is None:
                    break

            next_step.iteration = self._current_iteration
            self._react_chain.append(next_step)
            if next_step.step_type == "THOUGHT":
                self._thought_buffer.append(next_step.content)  # M1: Accumulate reasoning
                _consecutive_thoughts += 1
                # After 3 consecutive THOUGHT-only iterations the LLM is looping
                # without calling any tool. Force the task driver to pick a tool
                # so the agent produces real findings before the ceiling is hit.
                if _consecutive_thoughts >= 3 and llm_generator is not None:
                    logger.warning(
                        "ReAct loop: 3 consecutive THOUGHT steps — forcing task driver",
                        agent_id=self.agent_id,
                        iteration=self._current_iteration,
                    )
                    _forced = await self._default_step_generator(state, tool_registry)
                    if _forced is not None:
                        _forced.iteration = self._current_iteration
                        self._react_chain.append(_forced)
                        await self._log_step(_forced)
                        next_step = _forced
                    _consecutive_thoughts = 0
            else:
                _consecutive_thoughts = 0
            await self._log_step(next_step)

            # Handle ACTION steps
            if next_step.step_type == "ACTION" and next_step.tool_name:
                with _tracer.start_as_current_span("react_loop.tool_call") as _tool_span:
                    _tool_span.set_attribute("tool_name", next_step.tool_name)
                    _tool_span.set_attribute("agent_id", self.agent_id)
                    _tool_span.set_attribute("iteration", self._current_iteration)

                    # Forensic Trace (IMPV-05) - persistent audit of tool call
                    trace = PipelineTrace(
                        session_id=self.session_id,
                        agent_id=self.agent_id,
                        operation=f"tool_call:{next_step.tool_name}",
                        metadata={
                            "iteration": self._current_iteration,
                            "input": next_step.tool_input,
                        },
                    )
                    await trace.start()

                    # Pre-tool thought validation
                    tool_input = next_step.tool_input or {}
                    try:
                        tool_input = await self.reasoning_service.pre_tool_reasoning(
                            session_id=str(self.session_id),
                            agent_id=self.agent_id,
                            tool_name=next_step.tool_name,
                            tool_input=tool_input,
                            working_memory=self.working_memory
                        )
                    except Exception as reasoning_err:
                        logger.warning(
                            "Pre-tool reasoning validation failed, continuing with original input",
                            error=str(reasoning_err),
                            agent_id=self.agent_id
                        )

                    # Dynamic per-tool timeout selection
                    tool_timeout = TOOL_TIMEOUT_POLICY.get(next_step.tool_name, self.per_tool_timeout)

                    try:
                        # Resolve the evidence file path + MIME so the registry's
                        # content-aware gate can ensure the right tool only runs
                        # for the right file type.
                        _ev = getattr(self.agent, "evidence_artifact", None)
                        _ev_path = str(getattr(_ev, "file_path", "") or "")
                        _ev_mime = str(getattr(_ev, "mime_type", "") or "")
                        tool_result = await asyncio.wait_for(
                            tool_registry.call(
                                tool_name=next_step.tool_name,
                                input_data=tool_input,
                                agent_id=self.agent_id,
                                session_id=self.session_id,
                                custody_logger=self.custody_logger,
                                semaphore=self.heavy_tool_semaphore,
                                evidence_file_path=_ev_path,
                                evidence_mime_type=_ev_mime,
                            ),
                            timeout=tool_timeout,
                        )
                        _tool_span.set_attribute("tool_success", tool_result.success)

                        # Complete forensic trace
                        if tool_result.success:
                            await trace.complete({"result_summary": str(tool_result.output)[:200]})
                        else:
                            await trace.fail(tool_result.error or "Unknown tool error")

                    except asyncio.CancelledError:
                        # Honour cooperative cancellation (terminate / shutdown).
                        await trace.fail("cancelled")
                        raise
                    except Exception as tool_exc:
                        # M-C-1: a tool failure must NOT abort the whole agent
                        # ReAct loop. Synthesize a failed ToolResult so the
                        # standard INCOMPLETE-finding emit path below runs and
                        # the remaining tools / iterations continue. Without
                        # this guard a single misbehaving handler took down
                        # the entire agent's investigation.
                        await trace.fail(str(tool_exc))
                        logger.warning(
                            "Tool raised an unhandled exception; continuing the ReAct loop",
                            agent_id=self.agent_id,
                            tool_name=next_step.tool_name,
                            error=str(tool_exc),
                            exc_info=True,
                        )
                        tool_result = ToolResult(
                            success=False,
                            output={},
                            error=f"{type(tool_exc).__name__}: {tool_exc}",
                            tool_name=next_step.tool_name,
                            unavailable=False,
                        )
                        _tool_span.set_attribute("tool_success", False)
                        _tool_span.set_attribute("tool_exception", type(tool_exc).__name__)
                    _tool_span.set_attribute("tool_unavailable", tool_result.unavailable)

                # --- Normalize and Ground Tool Result ---
                from core.tool_output_normalizer import normalize_tool_output
                if tool_result.success:
                    envelope = normalize_tool_output(
                        tool_name=next_step.tool_name,
                        output=tool_result.output,
                        available=not tool_result.unavailable,
                        agent_id=self.agent_id
                    )
                else:
                    envelope = normalize_tool_output(
                        tool_name=next_step.tool_name,
                        output={"error": tool_result.error or "Tool execution failed"},
                        available=not tool_result.unavailable,
                        agent_id=self.agent_id
                    )

                # Post-tool grounding
                finding = await self.reasoning_service.post_tool_reasoning(
                    session_id=str(self.session_id),
                    agent_id=self.agent_id,
                    tool_name=next_step.tool_name,
                    envelope=envelope,
                    working_memory=self.working_memory
                )

                if tool_result.success:
                    is_stub = isinstance(envelope.raw, dict) and (
                        envelope.raw.get("status") == "stub"
                        or not finding.metadata.get("court_defensible")
                    )
                    if finding.evidence_verdict not in ["ERROR", "NOT_APPLICABLE"] and not is_stub and finding.confidence_raw is not None:
                        try:
                            from core.calibration import get_calibration_layer
                            from core.severity import NON_INTEGRITY_TOOLS

                            if next_step.tool_name in NON_INTEGRITY_TOOLS:
                                # Deterministic/provenance tools (hash, EXIF, hex) don't
                                # have epistemic uncertainty and shouldn't be Platt-scaled.
                                finding.raw_confidence_score = finding.confidence_raw
                                finding.calibrated = False
                                finding.calibration_status = "UNCALIBRATED"
                            else:
                                calibration_layer = get_calibration_layer()
                                if calibration_layer:
                                    cal_result = calibration_layer.calibrate(
                                        agent_id=self.agent_id,
                                        raw_score=finding.confidence_raw,
                                        finding_class=next_step.tool_name,
                                    )
                                    finding.raw_confidence_score = cal_result.raw_confidence_score
                                    finding.calibrated = cal_result.calibration_status.value == "TRAINED"
                                    finding.calibration_status = cal_result.calibration_status.value
                                    finding.metadata["confidence_interval"] = cal_result.confidence_interval
                                    if cal_result.uncertainty:
                                        finding.metadata["uncertainty"] = cal_result.uncertainty.model_dump()

                                        # Check for epistemic uncertainty escalation (arXiv:2512.16614)
                                        if cal_result.uncertainty.should_escalate:
                                            logger.warning(
                                                "Epistemic uncertainty escalation triggered",
                                                agent_id=self.agent_id,
                                                tool_name=next_step.tool_name,
                                                epistemic=cal_result.uncertainty.epistemic_uncertainty,
                                                reason=cal_result.uncertainty.escalation_reason,
                                            )
                                            # Write escalation flag to working memory
                                            try:
                                                await self.working_memory.update_state(
                                                    session_id=self.session_id,
                                                    agent_id=self.agent_id,
                                                    updates={
                                                        "tribunal_escalation": True,
                                                        "escalation_reason": cal_result.uncertainty.escalation_reason,
                                                    },
                                                )
                                            except Exception as exc:
                                                logger.debug(
                                                    "Failed to persist epistemic escalation flag",
                                                    agent_id=self.agent_id,
                                                    tool_name=next_step.tool_name,
                                                    error=str(exc),
                                                )
                        except Exception as cal_err:
                            logger.warning(
                                "Calibration layer failed on post_tool_reasoning output",
                                agent_id=self.agent_id,
                                error=str(cal_err),
                                exc_info=True,
                            )

                # Attach preceding LLM thought/reasoning to metadata
                llm_reasoning = "\n".join(self._thought_buffer)
                self._thought_buffer = []
                finding.metadata["llm_reasoning"] = llm_reasoning

                # Dedup by tool_name
                tool_name = next_step.tool_name
                if not any(
                    f.metadata.get("tool_name") == tool_name
                    for f in self._findings
                    if hasattr(f, "metadata") and isinstance(f.metadata, dict)
                ):
                    self._findings.append(finding)

                # [INT-DECOMP] Reactive hook: Allow agent to inject tasks based on finding
                if self.agent is not None:
                    try:
                        await self.agent.on_tool_result(finding)
                    except Exception as hook_err:
                        logger.debug("Agent on_tool_result hook failed", error=str(hook_err))

                # Create OBSERVATION step
                observation = ReActStep(
                    step_type="OBSERVATION",
                    content=self._format_tool_result(tool_result),
                    tool_name=next_step.tool_name,
                    tool_output=tool_result.model_dump(),
                    iteration=self._current_iteration,
                )
                self._react_chain.append(observation)
                await self._log_step(observation)

                if not tool_result.success and self.custody_logger is not None:
                    try:
                        await self.custody_logger.log_entry(
                            entry_type=EntryType.ERROR,
                            agent_id=self.agent_id,
                            session_id=self.session_id,
                            content={
                                "tool_name": next_step.tool_name,
                                "error": tool_result.error or "unknown",
                                "iteration": self._current_iteration,
                            },
                        )
                    except Exception as exc:
                        logger.debug(
                            "Failed to log tool error to custody",
                            agent_id=self.agent_id,
                            tool_name=next_step.tool_name,
                            error=str(exc),
                        )

                # Mark the IN_PROGRESS task as COMPLETE now that the tool has run.
                await self._update_task_complete(next_step)

                # Check for tool unavailability HITL trigger
                if tool_result.unavailable:
                    hitl_reason = await self.check_hitl_triggers(state)
                    if hitl_reason == HITLCheckpointReason.TOOL_UNAVAILABLE:
                        checkpoint = await self.pause_for_hitl(
                            reason=hitl_reason,
                            brief=f"Tool '{next_step.tool_name}' unavailable",
                        )
                        self._hitl_checkpoints.append(checkpoint)

            # Update working memory with current iteration
            await self.working_memory.update_state(
                session_id=self.session_id,
                agent_id=self.agent_id,
                updates={"current_iteration": self._current_iteration},
            )

        # Build result
        return ReActLoopResult(
            session_id=self.session_id,
            agent_id=self.agent_id,
            completed=(not self._terminated),
            terminated_by_human=self._terminated,
            findings=self._findings,
            hitl_checkpoints=self._hitl_checkpoints,
            total_iterations=self._current_iteration,
            react_chain=self._react_chain,
        )

    async def _should_trigger_followup(
        self, task_description: str | None, tool_result: dict
    ) -> str | None:
        """
        Return a follow-up tool name if the result warrants deeper analysis,
        or None if the task can be marked complete.
        """
        task_lower = (task_description or "").lower()
        result_str = str(tool_result).lower()  # noqa: F841  kept for future pattern checks

        # If ELA finds anomaly regions, follow up with ROI extraction.
        # Checks both neural_ela key ("num_anomaly_regions") and the
        # legacy ela_full_image key (same field name).
        if "ela" in task_lower:
            if tool_result.get("num_anomaly_regions", 0) > 0:
                return "roi_extract"

        # If neural splicing detects a splice, escalate to noise fingerprint
        # for sensor-level cross-validation.
        if "splicing" in task_lower:
            if tool_result.get("splicing_detected", False):
                return "noise_fingerprint"

        # If GPS coordinates present in EXIF, validate against timestamp timezone.
        if "exif" in task_lower:
            if tool_result.get("gps_coordinates") is not None:
                return "gps_timezone_validate"

        return None

    async def check_hitl_triggers(self, state: WorkingMemoryState) -> HITLCheckpointReason | None:
        """
        Check if any HITL trigger conditions are met.

        Args:
            state: Current working memory state

        Returns:
            HITLCheckpointReason if triggered, None otherwise
        """
        # ITERATION_CEILING_50PCT HITL is disabled: the task-driver loop
        # advances one task per iteration deterministically, so "no complete
        # task at half ceiling" is expected during the first few iterations and
        # would trigger a spurious 300-second pause that freezes the UI.
        # This trigger was designed for an LLM free-form loop, not the
        # structured task-decomposition driver.  Leave it out.

        # Check for contested findings
        for task in state.tasks:
            if task.status == "CONTESTED":
                return HITLCheckpointReason.CONTESTED_FINDING

        for task in state.tasks:
            if hasattr(task, "severity_threshold") and task.severity_threshold:
                return HITLCheckpointReason.SEVERITY_THRESHOLD_BREACH

        # Check for tribunal escalation flag (set by epistemic uncertainty check)
        if getattr(state, "tribunal_escalation", False):
            return HITLCheckpointReason.TRIBUNAL_ESCALATION

        return None

    async def pause_for_hitl(self, reason: HITLCheckpointReason, brief: str) -> HITLCheckpointState:
        """
        Pause the loop for Human-in-the-Loop intervention.

        Args:
            reason: Why the checkpoint was triggered
            brief: Brief description for the investigator

        Returns:
            HITLCheckpointState with PAUSED status
        """
        # Serialize working memory state
        try:
            state = await self.working_memory.get_state(
                session_id=self.session_id, agent_id=self.agent_id
            )
        except (ConnectionError, TimeoutError, OSError) as e:
            logger.debug(
                "Working memory read failed at HITL checkpoint (transient?)",
                agent_id=self.agent_id,
                error=str(e),
            )
            state = None
        except Exception as e:
            logger.warning(
                "Working memory read failed at HITL checkpoint (unexpected)",
                agent_id=self.agent_id,
                error=str(e),
                exc_info=True,
            )
            state = None
        if state is None:
            serialized_state = {
                "_warning": "Working memory unavailable at checkpoint time — state may be incomplete",
                "agent_id": self.agent_id,
                "session_id": str(self.session_id),
            }
        else:
            serialized_state = state.model_dump()

        # Create checkpoint
        checkpoint = HITLCheckpointState(
            agent_id=self.agent_id,
            session_id=self.session_id,
            reason=reason,
            paused_at_iteration=self._current_iteration,
            investigator_brief=brief,
            status="PAUSED",
            serialized_state=serialized_state,
        )

        # Log HITL checkpoint
        if self.custody_logger:
            await self.custody_logger.log_entry(
                agent_id=self.agent_id,
                session_id=self.session_id,
                entry_type=EntryType.HITL_CHECKPOINT,
                content={
                    "checkpoint_id": str(checkpoint.checkpoint_id),
                    "reason": reason.value,
                    "paused_at_iteration": self._current_iteration,
                    "brief": brief,
                },
            )

        # Store checkpoint in Redis with a 15-minute TTL (900 s).
        # After expiry Redis evicts the key automatically; check_expired_hitl()
        # detects this on the next poll and emits a checkpoint_expired SSE event
        # so the frontend auto-resolves the pending review widget.
        if self.redis_client is not None:
            key = f"hitl:{self.session_id}:{self.agent_id}"
            await self.redis_client.set(
                key,
                json.dumps(checkpoint.model_dump(), default=str),
                ex=900,
            )

        self._current_checkpoint = checkpoint
        return checkpoint

    async def resume_from_hitl(self, checkpoint_id: uuid.UUID, decision: HumanDecision) -> None:
        """
        Resume the loop after a HITL decision.

        Args:
            checkpoint_id: ID of the checkpoint to resume from
            decision: The human decision
        """
        # Log human intervention
        if self.custody_logger:
            await self.custody_logger.log_entry(
                agent_id=self.agent_id,
                session_id=self.session_id,
                entry_type=EntryType.HUMAN_INTERVENTION,
                content={
                    "checkpoint_id": str(checkpoint_id),
                    "decision_type": decision.decision_type,
                    "investigator_id": decision.investigator_id,
                    "notes": decision.notes,
                },
            )

        # Handle different decision types
        if decision.decision_type == "TERMINATE":
            self._terminated = True
            if self._current_checkpoint:
                self._current_checkpoint.status = "TERMINATED"
            return

        if decision.decision_type == "OVERRIDE" and decision.override_finding:
            # Create a finding from the override
            finding = AgentFinding(
                agent_id=self.agent_id,
                finding_type="HUMAN_OVERRIDE",
                confidence_raw=1.0,  # Human judgment is certain
                status="CONFIRMED",
                reasoning_summary=decision.notes,
            )
            self._findings.append(finding)
            if self._current_checkpoint:
                self._current_checkpoint.status = "OVERRIDDEN"

        if decision.decision_type == "REDIRECT" and decision.redirect_context:
            # Inject redirect context into working memory
            await self.working_memory.update_state(
                session_id=self.session_id,
                agent_id=self.agent_id,
                updates={
                    "redirect_context": decision.redirect_context,
                    "tribunal_escalation": False,
                    "uncertainty_pause": False,
                    "last_tool_error": None,
                },
            )
            if self._current_checkpoint:
                self._current_checkpoint.status = "RESUMED"

        if decision.decision_type == "APPROVE":
            if self._current_checkpoint:
                self._current_checkpoint.status = "RESUMED"

            # Issue 5.5: Clear sticky escalation flags in working memory when approving.
            # Failure to clear these causes the check_hitl_triggers() logic to
            # immediately re-pause the loop on the next iteration.
            try:
                await self.working_memory.update_state(
                    session_id=self.session_id,
                    agent_id=self.agent_id,
                    updates={
                        "tribunal_escalation": False,
                        "uncertainty_pause": False,
                        "last_tool_error": None,
                    },
                )
            except Exception as e:
                logger.warning(f"Could not clear escalation flags on APPROVE: {e}")

        if decision.decision_type == "ESCALATE":
            # Mark for tribunal escalation
            await self.working_memory.update_state(
                session_id=self.session_id,
                agent_id=self.agent_id,
                updates={"tribunal_escalation": True},
            )
            if self._current_checkpoint:
                self._current_checkpoint.status = "RESUMED"

        # Clear checkpoint from Redis
        if self.redis_client is not None:
            key = f"hitl:{self.session_id}:{self.agent_id}"
            await self.redis_client.delete(key)

        # Signal resume
        self._pending_decision = decision
        if self._resume_event:
            self._resume_event.set()

    async def _default_step_generator(
        self,
        state: WorkingMemoryState,
        tool_registry: ToolRegistry,
    ) -> ReActStep | None:
        """
        Built-in task-decomposition driver for when no LLM is provided.

        Iterates pending tasks from working memory and invokes the best
        matching tool for each one, generating findings from the results.

        Returns:
            A THOUGHT step for the next pending task, or None if all tasks
            are done (signalling the loop to stop).
        """
        # Force-complete any orphaned IN_PROGRESS tasks before finding the next PENDING.
        # An IN_PROGRESS task at the start of a NEW iteration means the previous
        # COMPLETE-marking silently failed (the tool DID run — we have its finding).
        # Leaving it IN_PROGRESS causes this generator to re-run the same tool on
        # every subsequent iteration until the ceiling, producing duplicate findings.
        for task in state.tasks:
            if task.status == TaskStatus.IN_PROGRESS:
                try:
                    await self.working_memory.update_task(
                        session_id=self.session_id,
                        agent_id=self.agent_id,
                        task_id=task.task_id,
                        status=TaskStatus.COMPLETE,
                        result_ref="force_completed",
                    )
                    logger.debug(
                        f"Force-completed orphaned IN_PROGRESS task: {task.description}",
                        agent_id=self.agent_id,
                    )
                except Exception as _fc_err:
                    logger.warning(
                        f"Could not force-complete orphaned task {task.task_id}: {_fc_err}",
                        agent_id=self.agent_id,
                    )

        # Re-read state after any force-completions so PENDING scan is accurate
        try:
            state = await self.working_memory.get_state(
                session_id=self.session_id,
                agent_id=self.agent_id,
            )
        except Exception as exc:
            logger.debug(
                "Working memory refresh failed; using existing state",
                agent_id=self.agent_id,
                error=str(exc),
            )

        # Issue 5.3: Skip BLOCKED tasks — prefer IN_PROGRESS > PENDING, skip BLOCKED.
        # A BLOCKED task stalls the loop; mark it complete and move to the next.
        pending_task = None
        for task in state.tasks:
            if task.status == TaskStatus.BLOCKED:
                # Auto-skip: mark blocked tasks complete so the loop advances
                try:
                    await self.working_memory.update_task(
                        session_id=self.session_id,
                        agent_id=self.agent_id,
                        task_id=task.task_id,
                        status=TaskStatus.COMPLETE,
                        result_ref="skipped_blocked",
                    )
                    logger.debug(
                        f"Skipped BLOCKED task: {task.description}",
                        agent_id=self.agent_id,
                    )
                except Exception as exc:
                    logger.debug(
                        "Failed to skip blocked task",
                        agent_id=self.agent_id,
                        task_id=str(task.task_id),
                        error=str(exc),
                    )
                continue
            if task.status == TaskStatus.PENDING and pending_task is None:
                pending_task = task

        if pending_task is None:
            # All tasks complete (or force-completed) → signal loop to stop
            return None

        skip_tasks = {
            "self-reflection pass",
            "submit calibrated findings to arbiter",
            "submit findings",
            "calibrated findings",
            "synthesize cross-field consistency",  # Summary task - no tool needed
            "synthesize",  # Generic synthesis tasks
            "classify each anomaly",  # Classification tasks are summary/synthesis
            "issue collaborative call",  # Optional inter-agent tasks
            "for each suspicious anomaly",  # Iterative tasks handled by tools
            "for each flagged anomaly",  # Iterative tasks handled by tools
            "for frames containing",  # Conditional tasks
        }

        if pending_task.description and any(
            skip in pending_task.description.lower() for skip in skip_tasks
        ):
            try:
                await self.working_memory.update_task(
                    session_id=self.session_id,
                    agent_id=self.agent_id,
                    task_id=pending_task.task_id,
                    status=TaskStatus.COMPLETE,
                    result_ref="handled_by_pipeline",
                )
            except Exception as exc:
                logger.debug(
                    "Failed to mark pipeline-handled task complete",
                    agent_id=self.agent_id,
                    task_id=str(pending_task.task_id),
                    error=str(exc),
                )
            return ReActStep(
                step_type="THOUGHT",
                content=f"Task '{pending_task.description}' is handled by the pipeline orchestrator. Skipping.",
                iteration=self._current_iteration,
            )

        # Match the task to the best available tool
        # Uses the embedding-based TaskRouter (with YAML + keyword fallback)
        tools = tool_registry.list_tools()
        try:
            from core.task_router import get_task_router
            best_tool = get_task_router().route(
                pending_task.description, tools, agent_id=self.agent_id
            )
        except Exception as _router_err:
            logger.warning(
                "TaskRouter failed, falling back to legacy matcher",
                error=str(_router_err),
                agent_id=self.agent_id,
            )
            best_tool = self._match_tool_to_task(pending_task.description, tools)

        if best_tool is None:
            # No matching tool — emit an INCOMPLETE finding so the gap is visible
            # in the frontend instead of silently dropping the task.
            self._findings.append(
                AgentFinding(
                    agent_id=self.agent_id,
                    finding_type=f"Unmatched Task: {pending_task.description[:70]}",
                    confidence_raw=0.0,
                    status="INCOMPLETE",
                    reasoning_summary=(
                        f"No forensic tool is registered for this task: "
                        f"'{pending_task.description}'. "
                        f"Ensure the tool is registered in build_tool_registry() "
                        f"and mapped in task_tool_overrides.yaml."
                    ),
                    metadata={
                        "tool_name": "no_matching_tool",
                        "court_defensible": False,
                        "task_description": pending_task.description,
                    },
                )
            )
            try:
                await self.working_memory.update_task(
                    session_id=self.session_id,
                    agent_id=self.agent_id,
                    task_id=pending_task.task_id,
                    status=TaskStatus.COMPLETE,
                    result_ref="no_matching_tool",
                )
            except Exception as exc:
                logger.debug(
                    "Failed to mark unmatched task complete",
                    agent_id=self.agent_id,
                    task_id=str(pending_task.task_id),
                    error=str(exc),
                )
            return ReActStep(
                step_type="THOUGHT",
                content=(
                    f"Task '{pending_task.description}' has no matching tool. "
                    f"Recorded as INCOMPLETE finding and moving on."
                ),
                iteration=self._current_iteration,
            )

        # Mark task as IN_PROGRESS so heartbeat shows real task name,
        # then emit ACTION directly (skipping the wasteful THOUGHT step).
        # This halves iteration usage: 1 iteration per task instead of 2.
        try:
            await self.working_memory.update_task(
                session_id=self.session_id,
                agent_id=self.agent_id,
                task_id=pending_task.task_id,
                status=TaskStatus.IN_PROGRESS,
                result_ref=best_tool.name,
            )
        except Exception as exc:
            logger.debug(
                "Failed to mark task in progress",
                agent_id=self.agent_id,
                task_id=str(pending_task.task_id),
                error=str(exc),
            )

        return ReActStep(
            step_type="ACTION",
            content=f"Executing: {pending_task.description} → {best_tool.name}",
            tool_name=best_tool.name,
            tool_input={"artifact": None, "_task_id": str(pending_task.task_id)},
            iteration=self._current_iteration,
        )

    @staticmethod
    def _match_tool_to_task(task_description: str, tools: list):
        """
        Match a task description to the best available tool using keyword
        overlap between the task text and tool name/description.

        First checks explicit _TASK_TOOL_OVERRIDES mapping, then falls back
        to keyword scoring.

        Returns the best-matching Tool, or None if no reasonable match.
        """
        task_lower = task_description.lower().strip()

        # First check explicit overrides (loaded from YAML config)
        for keyword, tool_name in ReActLoopEngine._get_task_tool_overrides().items():
            if keyword in task_lower:
                matched = next((t for t in tools if t.name == tool_name), None)
                if matched:
                    return matched

        # Fall through to existing scoring logic
        best_tool = None
        best_score = 0

        for tool in tools:
            score = 0
            name_parts = tool.name.lower().replace("_", " ").split()
            desc_parts = tool.description.lower().split() if tool.description else []

            for part in name_parts:
                if len(part) > 2 and part in task_lower:
                    score += 3

            for part in desc_parts:
                if len(part) > 3 and part in task_lower:
                    score += 1

            if score > best_score:
                best_score = score
                best_tool = tool

        # Require at least some keyword overlap
        if best_score >= 2:
            return best_tool

        # No good match found - return None instead of falling back to first tool
        # The caller handles None by marking the task as blocked
        return None

    async def _log_step(self, step: ReActStep) -> None:
        """Log a ReAct step to the custody logger."""
        # Map step type to EntryType
        step_type_to_entry_type = {
            "THOUGHT": EntryType.THOUGHT,
            "ACTION": EntryType.ACTION,
            "OBSERVATION": EntryType.OBSERVATION,
        }
        entry_type = step_type_to_entry_type.get(step.step_type, EntryType.THOUGHT)
        if self.custody_logger:
            try:
                await self.custody_logger.log_entry(
                    agent_id=self.agent_id,
                    session_id=self.session_id,
                    entry_type=entry_type,
                    content={
                        "step_type": step.step_type,
                        "content": step.content,
                        "iteration": step.iteration,
                        "tool_name": step.tool_name,
                        "tool_input": step.tool_input,
                        "timestamp": step.timestamp_utc.isoformat(),
                    },
                )
            except Exception as _log_err:
                # Custody log is an audit trail, not a functional dependency.
                # A logging failure must never abort agent execution.
                logger.warning("_log_step: custody write failed (non-fatal)", error=str(_log_err))

    @staticmethod
    def _build_detailed_reasoning(tool_name: str, output: dict) -> str:
        """
        Generate specific, court-admissible reasoning based on tool output.
        Each tool type produces a unique numerical-rich summary sentence.
        """
        return _fmt_build_detailed_reasoning(tool_name, output)

    def _build_readable_summary(
        self,
        tool_name: str,
        task_description: str,
        tool_result: ToolResult,
        confidence: float,
        status: str,
        evidence_verdict: str = "INCONCLUSIVE",
        llm_reasoning: str | None = None,
    ) -> str:
        """
        Build a human-readable summary from a tool result.

        Uses tool-specific detailed reasoning builders for rich,
        court-admissible findings. Falls back to generic scalar extraction.
        """
        return _fmt_build_readable_summary(
            tool_name=tool_name,
            task_description=task_description,
            tool_result=tool_result,
            confidence=confidence,
            status=status,
            evidence_verdict=evidence_verdict,
            llm_reasoning=llm_reasoning,
            agent_id=self.agent_id,
        )

    def _shape_analyst_finding(
        self,
        tool_label: str,
        message: str,
        evidence_verdict: str,
        status: str,
        output: dict[str, Any],
    ) -> str:
        """Turn technical tool output into a concise analyst-facing finding."""
        return _fmt_shape_analyst_finding(
            tool_label=tool_label,
            message=message,
            evidence_verdict=evidence_verdict,
            status=status,
            output=output,
        )

    def _format_tool_result(self, result: ToolResult) -> str:
        """Format a tool result for observation content."""
        return _fmt_format_tool_result(result)

    def add_finding(self, finding: AgentFinding) -> None:
        """Add a finding to the result."""
        self._findings.append(finding)

    def set_pending_decision(self, decision: HumanDecision) -> None:
        """Set a pending decision for HITL resume (used in tests)."""
        self._pending_decision = decision
        if self._resume_event:
            self._resume_event.set()

    async def _run_deterministic_tool_chain(
        self,
        task: str,
        context: dict[str, Any],
    ) -> dict[str, Any]:
        """
        Execute all relevant tools in priority order without LLM.

        This ensures full forensic coverage even when APIs are down.
        CLIP + DETR + ELA are always run for image agents.
        """
        results = {
            "iteration_count": 1,
            "tool_executions": [],
            "findings": [],
            "mode": "deterministic_fallback"
        }

        tool_chain = self._get_prioritized_tools()

        logger.info(
            "Executing deterministic tool chain",
            agent_id=self.agent_id,
            tool_count=len(tool_chain),
            tools=[t["name"] for t in tool_chain]
        )

        for tool_def in tool_chain:
            tool_name = tool_def["name"]
            tool_params = tool_def.get("params", {})

            try:
                tool_result = await self._execute_tool_direct(tool_name, tool_params, context)

                results["tool_executions"].append({
                    "tool": tool_name,
                    "status": "success",
                    "output": tool_result
                })

                if "findings" in tool_result:
                    results["findings"].extend(tool_result["findings"])

            except Exception as e:
                logger.error(
                    "Tool execution failed in deterministic mode",
                    tool=tool_name,
                    error=str(e)
                )
                results["tool_executions"].append({
                    "tool": tool_name,
                    "status": "failed",
                    "error": str(e)
                })

        return results

    async def _execute_tool_direct(
        self,
        tool_name: str,
        tool_params: dict,
        context: dict[str, Any],
    ) -> dict[str, Any]:
        """Execute a tool directly without going through the full ReAct loop."""
        if hasattr(self, "_tool_registry") and self._tool_registry:
            result = await self._tool_registry.call(
                tool_name=tool_name,
                input_data=tool_params,
                agent_id=self.agent_id,
                session_id=self.session_id,
                custody_logger=self.custody_logger,
                semaphore=self.heavy_tool_semaphore,
            )
            return result.output or {} if result.success else {"error": result.error}
        return {}

    def _get_prioritized_tools(self) -> list[dict]:
        """
        Get ordered tool list for deterministic execution.

        Each agent has a different priority order based on forensic workflow.
        """
        tool_chains = {
            "agent1": [
                {"name": "extract_exif", "params": {}},
                {"name": "ela_anomaly_classifier", "params": {"sensitivity": "medium"}},
                {"name": "noise_fingerprint", "params": {}},
                {"name": "jpeg_ghost_detector", "params": {}},
                {"name": "copy_move_detector", "params": {"min_cluster_size": 5}},
                {"name": "splicing_detector", "params": {}},
                {"name": "object_detection", "params": {}},
                {"name": "analyze_image_content", "params": {}},
            ],
            "agent2": [
                {"name": "extract_audio_metadata", "params": {}},
                {"name": "speaker_diarization", "params": {}},
                {"name": "audio_splice_detector", "params": {}},
                {"name": "deepfake_frequency_analysis", "params": {}},
                {"name": "anti_spoofing_detector", "params": {}},
            ],
            "agent3": [
                {"name": "object_detection", "params": {}},
                {"name": "analyze_image_content", "params": {}},
                {"name": "lighting_analyzer", "params": {}},
                {"name": "scale_validator", "params": {}},
                {"name": "shadow_direction_analyzer", "params": {}},
            ],
            "agent4": [
                {"name": "extract_video_metadata", "params": {}},
                {"name": "optical_flow_analyzer", "params": {}},
                {"name": "face_swap_detector", "params": {}},
                {"name": "rolling_shutter_validator", "params": {}},
                {"name": "frame_interpolation_detector", "params": {}},
            ],
            "agent5": [
                {"name": "extract_exif", "params": {}},
                {"name": "gps_validator", "params": {}},
                {"name": "steganography_detector", "params": {}},
                {"name": "c2pa_validator", "params": {}},
                {"name": "metadata_anomaly_scorer", "params": {}},
            ],
        }

        return tool_chains.get(self.agent_id, [])
