"""
ReAct Loop Engine and HITL Checkpoint System for Forensic Council.

Implements the core THOUGHT → ACTION → OBSERVATION reasoning loop
with Human-in-the-Loop (HITL) checkpoints for forensic analysis.
"""

from __future__ import annotations

import asyncio
import json
import uuid
from collections.abc import Callable, Coroutine
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator

from core.config import Settings
from core.custody_logger import CustodyLogger, EntryType
from core.llm_client import LLMClient, LLMResponse, parse_llm_step
from core.observability import get_tracer
from core.structured_logging import get_logger
from core.task_tool_config import get_task_tool_overrides
from core.tool_registry import ToolRegistry, ToolResult
from core.tracing import PipelineTrace
from core.working_memory import WorkingMemory, WorkingMemoryState

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
    tool_input: dict[str, Any] | None = Field(
        default=None, description="Tool input if ACTION step"
    )
    tool_output: dict[str, Any] | None = Field(
        default=None, description="Tool output if OBSERVATION step"
    )
    iteration: int = Field(..., description="Current iteration number")
    timestamp_utc: datetime = Field(
        default_factory=lambda: datetime.now(UTC),
        description="UTC timestamp of the step",
    )


from core.hitl import (
    HITLCheckpointReason,
    HITLCheckpointStatus,
    HITLCheckpointState,
    HumanDecisionType,
    HumanDecision,
)
from core.tool_interpreters import _TOOL_INTERPRETERS

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
    calibrated: bool = Field(
        default=False, description="Whether confidence has been calibrated"
    )
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
        "CONFIRMED", "CONTESTED", "INCONCLUSIVE", "INCOMPLETE",
        "NOT_APPLICABLE", "ABSTAIN",
    ] = Field(
        default="CONFIRMED", description="Finding status"
    )
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


class ReActLoopResult(BaseModel):
    """Result of a completed ReAct loop."""

    session_id: uuid.UUID = Field(..., description="Session ID")
    agent_id: str = Field(..., description="Agent ID")
    completed: bool = Field(
        default=False, description="Whether loop completed normally"
    )
    terminated_by_human: bool = Field(
        default=False, description="Whether loop was terminated by human"
    )
    findings: list[AgentFinding] = Field(
        default_factory=list, description="Findings produced"
    )
    hitl_checkpoints: list[HITLCheckpointState] = Field(
        default_factory=list, description="HITL checkpoints encountered"
    )
    total_iterations: int = Field(default=0, description="Total iterations run")
    react_chain: list[ReActStep] = Field(
        default_factory=list, description="Full reasoning chain"
    )


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
            available_tasks=[
                t.description for t in state.tasks if t.status != "COMPLETE"
            ],
        )

        # Get available tools from state/tool registry context
        available_tools = _get_available_tools_for_llm(state)

        # Get current task
        current_task = None
        for task in state.tasks:
            if task.status == "IN_PROGRESS":
                current_task = task.description
                break

        try:
            # Call LLM for reasoning
            response: LLMResponse = await llm_client.generate_reasoning_step(
                system_prompt=system_prompt,
                react_chain=[step.model_dump() for step in react_chain],
                available_tools=available_tools,
                current_task=current_task,
            )

            # Parse response into a ReAct step
            parsed = parse_llm_step(response.content, response.tool_call)

            # Create the ReAct step
            step = ReActStep(
                step_type=parsed["step_type"],  # type: ignore[arg-type]  # parse_llm_step returns dict[str, Any]; step_type value is always a valid Literal
                content=parsed["content"],
                tool_name=parsed.get("tool_name"),
                tool_input=parsed.get("tool_input"),
            )

            logger.info(
                "LLM generated ReAct step",
                agent_name=agent_name,
                step_type=step.step_type,
                tool_name=step.tool_name,
            )

            return step

        except Exception as e:
            logger.error(
                "LLM step generation failed, falling back to default",
                error=str(e),
                agent_name=agent_name,
                exc_info=True,
            )
            return None

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
    mandate = mandates.get(
        agent_key, "multi-modal forensic analysis of the submitted evidence"
    )

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
    registry_snapshot: list[dict] | None = getattr(
        state, "tool_registry_snapshot", None
    )
    if registry_snapshot:
        return registry_snapshot

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
            "name": "perceptual_hash",
            "description": "pHash perceptual similarity hash for near-duplicate detection",
        },
        {
            "name": "copy_move_detect",
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
            "name": "gemini_deep_forensic",
            "description": "Gemini 2.5 Flash neural vision audit — deep analysis of authenticity, objects, and text",
        },
        # Agent 2 — Audio
        {
            "name": "speaker_diarize",
            "description": "Neural speaker diarization — count and segment speakers",
        },
        {
            "name": "anti_spoofing_detect",
            "description": "SpeechBrain anti-spoofing — detect synthetic/replayed speech",
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
            "name": "gemini_deep_forensic",
            "description": "Gemini 2.5 Flash neural audio audit — identifies voice clones and sentiment anomalies",
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
            "name": "image_splice_check",
            "description": "Splicing detection on detected object regions",
        },
        # Agent 4 — Video
        {
            "name": "optical_flow_analyze",
            "description": "Dense optical flow analysis — detect frame discontinuities",
        },
        {
            "name": "frame_window_extract",
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
            "name": "video_metadata_extract",
            "description": "Extract video container metadata",
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
            "name": "extract_deep_metadata",
            "description": "Deep metadata extraction including MakerNotes and XMP",
        },
        {
            "name": "get_physical_address",
            "description": "Reverse geocode GPS coordinates to physical address",
        },
    ]


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

    _TOOL_LABELS: dict[str, str] = {
        "ela_full_image": "ELA — Image Manipulation",
        "ela_anomaly_classify": "ELA Anomaly Classification",
        "jpeg_ghost_detect": "JPEG Ghost Detection",
        "frequency_domain_analysis": "Frequency Domain Analysis",
        "deepfake_frequency_check": "GAN/Deepfake Frequency Check",
        "noise_fingerprint": "PRNU Noise Fingerprint",
        "copy_move_detect": "Copy-Move Forgery Detection",
        "extract_evidence_text": "OCR Text Extraction",
        "extract_text_from_image": "OCR Text Extraction",
        "analyze_image_content": "Semantic Image Analysis",
        "perceptual_hash": "Perceptual Hash (pHash)",
        "file_hash_verify": "File Hash Verification",
        "splicing_detect": "Splicing Detection",
        "image_splice_check": "Image Splice Check",
        "roi_extract": "Region of Interest Extraction",
        "speaker_diarize": "Speaker Diarization",
        "anti_spoofing_detect": "Anti-Spoofing Detection",
        "prosody_analyze": "Prosody Analysis",
        "audio_splice_detect": "Audio Splice Detection",
        "background_noise_analysis": "Background Noise Consistency",
        "codec_fingerprinting": "Codec Fingerprinting",
        "audio_visual_sync": "Audio-Visual Sync Check",
        "object_detection": "Object Detection (YOLO)",
        "lighting_consistency": "Lighting & Shadow Consistency",
        "scene_incongruence": "Scene Incongruence (CLIP)",
        "secondary_classification": "Secondary Object Classification",
        "scale_validation": "Scale & Proportion Validation",
        "contraband_database": "Contraband / Weapons CLIP Analysis",
        "optical_flow_analysis": "Optical Flow Analysis",
        "optical_flow_analyze": "Optical Flow Analysis",
        "frame_extraction": "Frame Window Extraction",
        "frame_window_extract": "Frame Window Extraction",
        "frame_consistency_analysis": "Frame Consistency Analysis",
        "face_swap_detection": "Face-Swap Detection",
        "video_metadata": "Video Metadata Extraction",
        "video_metadata_extract": "Video Metadata Extraction",
        "anomaly_classification": "Anomaly Classification",
        "rolling_shutter_validation": "Rolling Shutter Validation",
        "mediainfo_profile": "MediaInfo Container Profile",
        "av_file_identity": "AV File Identity Pre-Screen",
        "exif_extract": "EXIF Metadata Extraction",
        "metadata_anomaly_score": "Metadata Anomaly Score (ML)",
        "gps_timezone_validate": "GPS-Timezone Validation",
        "steganography_scan": "Steganography Scan",
        "file_structure_analysis": "File Structure Analysis",
        "hex_signature_scan": "Hex Signature Scan",
        "timestamp_analysis": "Timestamp Consistency Analysis",
        "extract_deep_metadata": "Deep Metadata Extraction",
        "get_physical_address": "GPS Reverse Geocoding",
        "astronomical_api": "Astronomical Timestamp Validation",
        "reverse_image_search": "Reverse Image Search (pHash)",
        "device_fingerprint_db": "Device Fingerprint Analysis",
        "adversarial_robustness_check": "Adversarial Robustness Check",
        "neural_ela": "Neural ELA — ViT Manipulation Detection",
        "noiseprint_cluster": "Noiseprint++ Sensor Clustering",
        "neural_fingerprint": "SigLIP2 Neural Perceptual Fingerprint",
        "neural_splicing": "TruFor ViT Splicing Detection",
        "neural_copy_move": "BusterNet Dual-Branch Copy-Move",
        "anomaly_tracer": "ManTra-Net Universal Anomaly Tracer",
        "f3_net_frequency": "F3-Net Frequency Artifact Analysis",
        "diffusion_artifact_detector": "Diffusion/AI-Generation Artifact Detection",
        "gemini_identify_content": "Gemini Vision — Content Identification",
        "gemini_cross_validate_manipulation": "Gemini Vision — Manipulation Cross-Validation",
        "gemini_object_scene_analysis": "Gemini Vision — Object & Scene Analysis",
        "gemini_metadata_visual_consistency": "Gemini Vision — Metadata Consistency Check",
        "gemini_deep_forensic": "Gemini Deep Forensic Analysis",
        "prnu_analysis": "PRNU Camera Sensor Fingerprint",
        "cfa_demosaicing": "CFA Demosaicing Pattern Analysis",
        "voice_clone_detect": "Voice Clone Detection",
        "enf_analysis": "ENF Frequency Analysis",
        "object_text_ocr": "Object Region OCR",
        "document_authenticity": "Document Authenticity Check",
        "c2pa_verify": "C2PA Content Credentials",
        "thumbnail_mismatch": "Thumbnail Mismatch Detection",
        "sensor_db_query": "Camera Sensor DB Query",
    }

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
        redis_client: Any = None,  # Redis client for HITL checkpoint storage
        hitl_timeout: float = 300.0,  # Timeout for HITL resume wait (5 minutes default)
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
            hitl_timeout: Timeout in seconds for waiting on HITL resume (default 300s = 5 min)
        """
        self.agent_id = agent_id
        self.session_id = session_id
        self.iteration_ceiling = iteration_ceiling
        self.working_memory = working_memory
        self.custody_logger = custody_logger
        self.redis_client = redis_client
        self.hitl_timeout = hitl_timeout

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

    def _extract_confidence(self, output: Any, tool_name: str) -> tuple[float, bool]:
        """Extract a 0-1 confidence score from tool output. Returns (confidence, from_fallback)."""
        raw_conf: float | None = None
        if isinstance(output, dict):
            raw_conf = output.get("confidence")
            if raw_conf is None and "confidence" in output:
                raw_conf = 0.50
            if raw_conf is None:
                for key in ("anomaly_score", "tampering_score", "synthetic_probability",
                            "forgery_score", "diffusion_probability"):
                    val = output.get(key)
                    if isinstance(val, (int, float)):
                        raw_conf = 1.0 - max(0.0, min(1.0, float(val)))
                        break
            if raw_conf is None:
                for key in ("noise_consistency_score", "consistency_score",
                            "overall_consistency", "avg_confidence", "confidence_score"):
                    val = output.get(key)
                    if isinstance(val, (int, float)):
                        raw_conf = max(0.0, min(1.0, float(val)))
                        break
            if raw_conf is None:
                if "detections" in output:
                    raw_conf = 0.60 if len(output.get("detections") or []) > 0 else 0.40
                elif "objects_detected" in output:
                    raw_conf = 0.55 if len(output.get("objects_detected") or []) > 0 else 0.40
                elif output.get("hash_matches") is True:
                    raw_conf = 1.0
                elif output.get("hash_matches") is False:
                    raw_conf = 0.30
                elif output.get("scale_consistent") is True:
                    raw_conf = 0.85
                elif output.get("scale_consistent") is False:
                    raw_conf = 0.40
                elif "verdict" in output:
                    v = str(output.get("verdict", "")).upper()
                    if v in ("CONSISTENT", "AUTHENTIC", "CLEAN", "NATURAL_OR_CLEAN",
                             "LIKELY_AUTHENTIC", "LIKELY_GENUINE", "CONTENT_CREDENTIALS_PRESENT",
                             "NO_CONTENT_CREDENTIALS"):
                        raw_conf = 0.85
                    elif v in ("INCONSISTENT", "SUSPICIOUS", "TAMPERED"):
                        raw_conf = 0.40
                    elif v in ("INCONCLUSIVE", "ERROR"):
                        raw_conf = 0.50
                    elif v == "NOT_APPLICABLE":
                        raw_conf = 0.0
                elif output.get("ai_probability") is not None:
                    raw_conf = round(max(0.10, 1.0 - float(output["ai_probability"])), 3)
                elif output.get("synthetic_probability") is not None:
                    raw_conf = round(max(0.10, 1.0 - float(output["synthetic_probability"])), 3)
                elif output.get("spoof_probability") is not None:
                    raw_conf = round(max(0.10, 1.0 - float(output["spoof_probability"])), 3)
                elif output.get("num_anomaly_regions") is not None:
                    raw_conf = 0.85 if int(output["num_anomaly_regions"]) == 0 else 0.40
                elif output.get("anomaly_detected") is True or output.get("inconsistency_detected") is True:
                    raw_conf = 0.40
                elif output.get("anomaly_detected") is False or output.get("inconsistency_detected") is False:
                    raw_conf = 0.85
                elif output.get("header_valid") is not None:
                    anomalies = output.get("anomalies", [])
                    raw_conf = 0.85 if isinstance(anomalies, list) and len(anomalies) == 0 else 0.40
                elif output.get("editing_software_detected") is True:
                    raw_conf = 0.30
                elif output.get("editing_software_detected") is False:
                    raw_conf = 0.90
                elif "present_fields" in output and "absent_fields" in output:
                    present = len(output.get("present_fields") or [])
                    absent = len(output.get("absent_fields") or [])
                    total = present + absent
                    raw_conf = max(0.40, min(0.90, present / total)) if total > 0 else 0.50
                elif "plausible" in output:
                    p = output.get("plausible")
                    raw_conf = 0.80 if p is True else (0.40 if p is False else 0.50)

        from_fallback = raw_conf is None
        try:
            confidence = float(raw_conf) if raw_conf is not None else 0.50
        except (TypeError, ValueError):
            confidence = 0.50
            from_fallback = True

        if from_fallback:
            logger.warning(
                "Unrecognised tool output format — confidence fallback to 0.50",
                tool=tool_name,
                agent_id=self.agent_id,
                output_keys=list(output.keys()) if isinstance(output, dict) else type(output).__name__,
            )
        return confidence, from_fallback

    async def _handle_hitl_pause(
        self, checkpoint: "HITLCheckpointState", hitl_reason: "HITLCheckpointReason"
    ) -> bool:
        """Wait for human decision at a HITL checkpoint. Returns True if loop should terminate."""
        self._resume_event = asyncio.Event()

        if self._pending_decision is None:
            try:
                await asyncio.wait_for(self._resume_event.wait(), timeout=self.hitl_timeout)
            except TimeoutError:
                try:
                    if self.custody_logger is not None:
                        await self.custody_logger.log(
                            entry_type="SYSTEM_EVENT",
                            agent_id=self.agent_id,
                            session_id=str(self.session_id),
                            content={
                                "event": "HITL_TIMEOUT",
                                "checkpoint_id": str(checkpoint.checkpoint_id),
                                "reason": hitl_reason.value,
                                "timeout_seconds": self.hitl_timeout,
                                "iteration": self._current_iteration,
                            },
                        )
                except Exception:
                    pass
                self._terminated = True
                return True

        if self._pending_decision is not None:
            await self.resume_from_hitl(checkpoint.checkpoint_id, self._pending_decision)
            self._pending_decision = None
            self._resume_event.clear()

        return self._terminated

    async def _update_task_complete(self, step: "ReActStep") -> None:
        """Mark the working-memory task associated with a completed tool call as COMPLETE."""
        from core.working_memory import TaskStatus as _TS

        _task_id_str = (step.tool_input or {}).get("_task_id")
        _wm_updated = False

        if _task_id_str:
            try:
                from uuid import UUID as _UUID
                await self.working_memory.update_task(
                    session_id=self.session_id,
                    agent_id=self.agent_id,
                    task_id=_UUID(_task_id_str),
                    status=_TS.COMPLETE,
                    result_ref=step.tool_name,
                )
                _wm_updated = True
            except Exception as err:
                logger.warning(f"Direct task COMPLETE failed for {_task_id_str}: {err}",
                               agent_id=self.agent_id)

        if not _wm_updated:
            try:
                fresh_state = await self.working_memory.get_state(
                    session_id=self.session_id, agent_id=self.agent_id)
                if fresh_state:
                    for task in fresh_state.tasks:
                        if task.status == _TS.IN_PROGRESS:
                            await self.working_memory.update_task(
                                session_id=self.session_id,
                                agent_id=self.agent_id,
                                task_id=task.task_id,
                                status=_TS.COMPLETE,
                                result_ref=step.tool_name,
                            )
                            _wm_updated = True
                            break
            except Exception as err:
                logger.warning(f"WM scan task COMPLETE failed: {err}", agent_id=self.agent_id)

        if not _wm_updated:
            try:
                cache_state = await self.working_memory.get_state(
                    session_id=self.session_id, agent_id=self.agent_id)
                if cache_state:
                    for task in cache_state.tasks:
                        if task.status == _TS.IN_PROGRESS:
                            task.status = _TS.COMPLETE
                            task.result_ref = step.tool_name
                    key = self.working_memory._get_key(self.session_id, self.agent_id)
                    self.working_memory._local_cache[key] = cache_state.model_dump_json()
            except Exception:
                pass

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
            logger.debug("Working memory read failed on init (transient?)", agent_id=self.agent_id, error=str(e))
            state = None
        except Exception as e:
            logger.warning("Working memory read failed on init (unexpected)", agent_id=self.agent_id, error=str(e), exc_info=True)
            state = None

        with _tracer.start_as_current_span("react_loop.run") as _loop_span:
            _loop_span.set_attribute("agent_id", self.agent_id)
            _loop_span.set_attribute("session_id", str(self.session_id))
            _loop_span.set_attribute("iteration_ceiling", self.iteration_ceiling)

            # Create initial THOUGHT step
            initial_step = ReActStep(
                step_type="THOUGHT", content=initial_thought, iteration=0
            )
            self._react_chain.append(initial_step)
            self._thought_buffer.append(initial_thought)  # M1: Seed buffer with initial context
            await self._log_step(initial_step)

        self._current_iteration = 0

        # Main loop — increment BEFORE the body so iteration_ceiling is respected exactly
        while not self._terminated and self._current_iteration < self.iteration_ceiling:
            self._current_iteration += 1
            # Get current state
            try:
                state = await self.working_memory.get_state(
                    session_id=self.session_id, agent_id=self.agent_id
                )
            except (ConnectionError, TimeoutError, OSError) as e:
                logger.debug("Working memory read failed in loop (transient?)", agent_id=self.agent_id, iteration=self._current_iteration, error=str(e))
                state = None
            except Exception as e:
                logger.warning("Working memory read failed in loop (unexpected)", agent_id=self.agent_id, iteration=self._current_iteration, error=str(e), exc_info=True)
                state = None
            if state is None:
                break

            # Check HITL triggers before proceeding
            hitl_reason = await self.check_hitl_triggers(state)
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
                # Both LLM and task driver signal completion
                break

            next_step.iteration = self._current_iteration
            self._react_chain.append(next_step)
            if next_step.step_type == "THOUGHT":
                self._thought_buffer.append(next_step.content)  # M1: Accumulate reasoning
            await self._log_step(next_step)

            # Handle ACTION steps
            if next_step.step_type == "ACTION" and next_step.tool_name:
                with _tracer.start_as_current_span(
                    "react_loop.tool_call"
                ) as _tool_span:
                    _tool_span.set_attribute("tool_name", next_step.tool_name)
                    _tool_span.set_attribute("agent_id", self.agent_id)
                    _tool_span.set_attribute("iteration", self._current_iteration)
                    
                    # Forensic Trace (IMPV-05) - persistent audit of tool call
                    trace = PipelineTrace(
                        session_id=self.session_id,
                        agent_id=self.agent_id,
                        operation=f"tool_call:{next_step.tool_name}",
                        metadata={"iteration": self._current_iteration, "input": next_step.tool_input}
                    )
                    await trace.start()

                    try:
                        tool_result = await tool_registry.call(
                            tool_name=next_step.tool_name,
                            input_data=next_step.tool_input or {},
                            agent_id=self.agent_id,
                            session_id=self.session_id,
                            custody_logger=self.custody_logger,
                        )
                        _tool_span.set_attribute("tool_success", tool_result.success)

                        # Complete forensic trace
                        if tool_result.success:
                            await trace.complete({"result_summary": str(tool_result.data)[:200]})
                        else:
                            await trace.fail(tool_result.error or "Unknown tool error")

                    except Exception as tool_exc:
                        await trace.fail(str(tool_exc))
                        raise
                    _tool_span.set_attribute(
                        "tool_unavailable", tool_result.unavailable
                    )

                # --- Generate AgentFinding from Tool Result ---
                if tool_result.success:
                    output = tool_result.output or {}
                    confidence, _conf_from_fallback = self._extract_confidence(
                        output, next_step.tool_name
                    )
                    status_val = (
                        str(output.get("status", "CONFIRMED")).upper()
                        if isinstance(output, dict)
                        else "CONFIRMED"
                    )
                    if status_val not in ("CONFIRMED", "CONTESTED", "INCONCLUSIVE", "INCOMPLETE"):
                        status_val = "CONFIRMED"
                    is_stub = isinstance(output, dict) and (
                        output.get("status") == "stub"
                        or output.get("court_defensible") is False
                        or _conf_from_fallback
                    )
                    calibrated_prob = None

                    cal_status_str = "UNCALIBRATED"
                    _ci_dict = None
                    _uncertainty = None
                    try:
                        from core.calibration import get_calibration_layer

                        calibration_layer = get_calibration_layer()
                        if calibration_layer and not is_stub:
                            cal_result = calibration_layer.calibrate(
                                agent_id=self.agent_id,
                                raw_score=confidence,
                                finding_class=next_step.tool_name,
                            )
                            calibrated_prob = cal_result.raw_confidence_score
                            cal_status_str = cal_result.calibration_status.value
                            _ci_dict = cal_result.confidence_interval
                            _uncertainty = cal_result.uncertainty
                    except Exception:
                        logger.warning(
                            "Calibration layer failed",
                            agent_id=self.agent_id,
                            exc_info=True,
                        )
                    tool_label = self._TOOL_LABELS.get(
                        next_step.tool_name,
                        next_step.tool_name.replace("_", " ").title(),
                    )
                    # [M1] Attach preceding thoughts to metadata for trace richness.
                    llm_reasoning = "\n".join(self._thought_buffer)
                    self._thought_buffer = []  # Clear after associating with action

                    # Use the tool label as the canonical finding type.
                    # Attach the preceding LLM thought (if any) separately
                    # via the llm_reasoning metadata key — not as the label.
                    task_desc = tool_label

                    finding = AgentFinding(
                        agent_id=self.agent_id,
                        agent_name=self._AGENT_ID_TO_NAME.get(self.agent_id, self.agent_id),
                        finding_type=task_desc,
                        confidence_raw=confidence,
                        raw_confidence_score=calibrated_prob,
                        calibrated=cal_status_str == "TRAINED",
                        calibration_status=cal_status_str,
                        status=status_val,
                        evidence_refs=[],
                        reasoning_summary=self._build_readable_summary(
                            next_step.tool_name,
                            task_desc,
                            tool_result,
                            confidence,
                            status_val,
                            llm_reasoning=llm_reasoning,
                        ),
                        metadata={
                            "tool_name": next_step.tool_name,
                            "court_defensible": not is_stub,
                            "stub_warning": output.get("warning")
                            if isinstance(output, dict) and is_stub
                            else None,
                            "confidence_interval": _ci_dict,
                            "uncertainty": _uncertainty.model_dump()
                            if _uncertainty
                            else None,
                            "llm_reasoning": llm_reasoning,  # [M1] Injected trace data
                            **(
                                output
                                if isinstance(output, dict)
                                else {"raw_output": str(output)}
                            ),
                        },
                    )
                    self._findings.append(finding)

                    # Check for epistemic uncertainty escalation (arXiv:2512.16614)
                    if _uncertainty and _uncertainty.should_escalate:
                        logger.warning(
                            "Epistemic uncertainty escalation triggered",
                            agent_id=self.agent_id,
                            tool_name=next_step.tool_name,
                            epistemic=_uncertainty.epistemic_uncertainty,
                            reason=_uncertainty.escalation_reason,
                        )
                        # Write escalation flag to working memory
                        try:
                            await self.working_memory.update_state(
                                session_id=self.session_id,
                                agent_id=self.agent_id,
                                updates={
                                    "tribunal_escalation": True,
                                    "escalation_reason": _uncertainty.escalation_reason,
                                },
                            )
                        except Exception:
                            pass
                # ----------------------------------------------

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
                    except Exception:
                        pass

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

    async def check_hitl_triggers(
        self, state: WorkingMemoryState
    ) -> HITLCheckpointReason | None:
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

        # Check for severity threshold breach (if findings have high severity)
        # This would be checked against findings in a real implementation
        # For now, we check if any task has severity_threshold flag
        for task in state.tasks:
            if hasattr(task, "severity_threshold") and task.severity_threshold:
                return HITLCheckpointReason.SEVERITY_THRESHOLD_BREACH

        # Check for tribunal escalation flag (set by epistemic uncertainty check)
        if getattr(state, "tribunal_escalation", False):
            return HITLCheckpointReason.TRIBUNAL_ESCALATION

        return None

    async def pause_for_hitl(
        self, reason: HITLCheckpointReason, brief: str
    ) -> HITLCheckpointState:
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
            logger.debug("Working memory read failed at HITL checkpoint (transient?)", agent_id=self.agent_id, error=str(e))
            state = None
        except Exception as e:
            logger.warning("Working memory read failed at HITL checkpoint (unexpected)", agent_id=self.agent_id, error=str(e), exc_info=True)
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

        # Store checkpoint in Redis
        if self.redis_client is not None:
            key = f"hitl:{self.session_id}:{self.agent_id}"
            await self.redis_client.set(
                key, json.dumps(checkpoint.model_dump(), default=str)
            )

        self._current_checkpoint = checkpoint
        return checkpoint

    async def resume_from_hitl(
        self, checkpoint_id: uuid.UUID, decision: HumanDecision
    ) -> None:
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
                updates={"redirect_context": decision.redirect_context},
            )
            if self._current_checkpoint:
                self._current_checkpoint.status = "RESUMED"

        if decision.decision_type == "APPROVE":
            if self._current_checkpoint:
                self._current_checkpoint.status = "RESUMED"

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
        from core.working_memory import TaskStatus

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
        except Exception:
            pass  # Use existing state if refresh fails

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
                except Exception:
                    pass
                continue
            if task.status == TaskStatus.PENDING and pending_task is None:
                pending_task = task

        if pending_task is None:
            # All tasks complete (or force-completed) → signal loop to stop
            return None

        _SKIP_TASKS = {
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
            skip in pending_task.description.lower() for skip in _SKIP_TASKS
        ):
            try:
                await self.working_memory.update_task(
                    session_id=self.session_id,
                    agent_id=self.agent_id,
                    task_id=pending_task.task_id,
                    status=TaskStatus.COMPLETE,
                    result_ref="handled_by_pipeline",
                )
            except Exception:
                pass
            return ReActStep(
                step_type="THOUGHT",
                content=f"Task '{pending_task.description}' is handled by the pipeline orchestrator. Skipping.",
                iteration=self._current_iteration,
            )

        # Match the task to the best available tool
        tools = tool_registry.list_tools()
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
            except Exception:
                pass
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
        except Exception:
            pass

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

    def _build_readable_summary(
        self,
        tool_name: str,
        task_description: str,
        tool_result: ToolResult,
        confidence: float,
        status: str,
        llm_reasoning: str | None = None,
    ) -> str:
        """
        Build a human-readable summary from a tool result.

        Filters out large data blobs (arrays, maps) and extracts only
        meaningful scalar metrics to produce a concise sentence for the
        frontend agent cards.
        """
        tool_label = tool_name.replace("_", " ").title()

        if not tool_result.success:
            err = tool_result.error or "unknown error"
            for prefix in (
                "[ToolUnavailableError]",
                "[ToolError]",
                "ToolError:",
                "Exception:",
                "ValueError:",
                "TypeError:",
                "KeyError:",
            ):
                err = err.replace(prefix, "").strip()
            # Classify error type for a cleaner message
            if (
                "ModuleNotFoundError" in err
                or "ImportError" in err
                or "No module named" in err
            ):
                dep_name = err.split("'")[1] if "'" in err else "required dependency"
                err_msg = f"ML dependency '{dep_name}' not installed — tool skipped."
            elif "Timeout" in err or "timeout" in err:
                err_msg = "Tool timed out — likely model cold-start. Result skipped."
            elif "FileNotFoundError" in err:
                err_msg = "Evidence file not accessible — skipped."
            else:
                err_msg = err[:140] + ("…" if len(err) > 140 else "")
            return f"{tool_label}: {err_msg} Confidence adjusted to {confidence:.0%}."

        # M1 Refinement: If LLM generated specific reasoning, prepend it to the technical result
        reasoning_prefix = ""
        if llm_reasoning:
            # Clean up the reasoning — take the last sentence or first 100 chars
            last_thought = llm_reasoning.strip().split("\n")[-1]
            if len(last_thought) > 120:
                last_thought = last_thought[:117] + "..."
            reasoning_prefix = f"[{last_thought}] "

        output = tool_result.output or {}

        if output.get("status") == "stub_response":
            return (
                f"{reasoning_prefix}{tool_label}: The agent's external module returned a temporary placeholder response. "
                f"This indicates that advanced ML features are still structurally integrating. "
                f"Confidence: {confidence:.0%}."
            )

        # Standard forensic summary building starts here
        parts = [reasoning_prefix + f"{tool_label} analysis complete."]

        if "verdict" in output:
            parts.append(f"Verdict: {output['verdict']}.")

        # Use imported tool interpreters
        global _TOOL_INTERPRETERS

        interpreter = _TOOL_INTERPRETERS.get(tool_name)
        if interpreter and tool_result.success:
            try:
                interpreted_msg = interpreter(output)
                # Do not restate a hard "{confidence}% certainty" sentence here,
                # as the UI already shows calibrated confidence and this wording
                # can be misleading. Keep this as a plain, human-readable summary.
                return f"{tool_label}: {interpreted_msg}"
            except Exception:
                pass  # fall through to generic path

        highlights: list[str] = []
        for key, value in output.items():
            if key.startswith("_") or key in (
                "status",
                "tool_name",
                "analysis_report",
                "artifact_id",
                "session_id",
                "case_id",
            ):
                continue

            clean_key = key.replace("_", " ")

            if isinstance(value, list):
                if len(value) > 5:
                    highlights.append(f"{len(value)} {clean_key}")
                else:
                    items = ", ".join(str(v) for v in value)
                    if items:
                        highlights.append(f"{clean_key}: {items}")
                continue

            if isinstance(value, dict):
                continue

            if isinstance(value, bool):
                highlights.append(f"{clean_key}: {'yes' if value else 'no'}")
            elif isinstance(value, float):
                highlights.append(f"{clean_key} {value:.3f}")
            elif isinstance(value, int):
                highlights.append(f"{clean_key} {value}")
            elif isinstance(value, str) and len(value) < 200:
                highlights.append(f"{clean_key}: {value}")

        if highlights:
            # Show top 4 metrics concisely
            top = highlights[:4]
            detail = "; ".join(top)
            if len(highlights) > 4:
                detail += f" (+{len(highlights) - 4} more)"
            return f"{tool_label}: {detail}."
        else:
            return f"{tool_label}: analysis complete — no anomalies detected."

    def _format_tool_result(self, result: ToolResult) -> str:
        """Format a tool result for observation content."""
        if result.unavailable:
            return f"Tool '{result.tool_name}' is unavailable. Error: {result.error}"
        if result.success:
            return f"Tool '{result.tool_name}' succeeded. Output: {result.output}"
        return f"Tool '{result.tool_name}' failed. Error: {result.error}"

    def add_finding(self, finding: AgentFinding) -> None:
        """Add a finding to the result."""
        self._findings.append(finding)

    def set_pending_decision(self, decision: HumanDecision) -> None:
        """Set a pending decision for HITL resume (used in tests)."""
        self._pending_decision = decision
        if self._resume_event:
            self._resume_event.set()
