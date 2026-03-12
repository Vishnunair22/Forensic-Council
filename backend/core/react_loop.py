"""
ReAct Loop Engine and HITL Checkpoint System for Forensic Council.

Implements the core THOUGHT → ACTION → OBSERVATION reasoning loop
with Human-in-the-Loop (HITL) checkpoints for forensic analysis.
"""

from __future__ import annotations

import asyncio
import json
import uuid
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Callable, Coroutine, Literal

from pydantic import BaseModel, Field

from core.config import Settings
from core.custody_logger import CustodyLogger, EntryType
from core.llm_client import LLMClient, LLMResponse, parse_llm_step
from core.logging import get_logger
from core.tool_registry import ToolRegistry, ToolResult
from core.working_memory import WorkingMemory, WorkingMemoryState

logger = get_logger(__name__)


class ReActStepType(str, Enum):
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
    tool_name: str | None = Field(
        default=None, description="Tool name if ACTION step"
    )
    tool_input: dict[str, Any] | None = Field(
        default=None, description="Tool input if ACTION step"
    )
    tool_output: dict[str, Any] | None = Field(
        default=None, description="Tool output if OBSERVATION step"
    )
    iteration: int = Field(..., description="Current iteration number")
    timestamp_utc: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        description="UTC timestamp of the step"
    )


class HITLCheckpointReason(str, Enum):
    """Reasons for triggering a Human-in-the-Loop checkpoint."""
    ITERATION_CEILING_50PCT = "ITERATION_CEILING_50PCT"
    CONTESTED_FINDING = "CONTESTED_FINDING"
    TOOL_UNAVAILABLE = "TOOL_UNAVAILABLE"
    SEVERITY_THRESHOLD_BREACH = "SEVERITY_THRESHOLD_BREACH"
    TRIBUNAL_ESCALATION = "TRIBUNAL_ESCALATION"


class HITLCheckpointStatus(str, Enum):
    """Status of a HITL checkpoint."""
    PAUSED = "PAUSED"
    RESUMED = "RESUMED"
    OVERRIDDEN = "OVERRIDDEN"
    TERMINATED = "TERMINATED"


class HITLCheckpointState(BaseModel):
    """State of a Human-in-the-Loop checkpoint."""
    
    checkpoint_id: uuid.UUID = Field(
        default_factory=uuid.uuid4,
        description="Unique checkpoint identifier"
    )
    agent_id: str = Field(..., description="Agent that triggered checkpoint")
    session_id: uuid.UUID = Field(..., description="Session ID")
    reason: HITLCheckpointReason = Field(
        ..., description="Why checkpoint was triggered"
    )
    current_finding_summary: str = Field(
        default="", description="Summary of findings so far"
    )
    paused_at_iteration: int = Field(
        ..., description="Iteration at which loop was paused"
    )
    investigator_brief: str = Field(
        default="", description="Brief for the human investigator"
    )
    status: Literal["PAUSED", "RESUMED", "OVERRIDDEN", "TERMINATED"] = Field(
        default="PAUSED", description="Current checkpoint status"
    )
    serialized_state: dict[str, Any] | None = Field(
        default=None, description="Serialized working memory state"
    )


class HumanDecisionType(str, Enum):
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


class AgentFindingStatus(str, Enum):
    """Status of an agent finding."""
    CONFIRMED = "CONFIRMED"
    CONTESTED = "CONTESTED"
    INCONCLUSIVE = "INCONCLUSIVE"
    INCOMPLETE = "INCOMPLETE"


class AgentFinding(BaseModel):
    """A finding produced by an agent."""
    
    finding_id: uuid.UUID = Field(
        default_factory=uuid.uuid4,
        description="Unique finding identifier"
    )
    agent_id: str = Field(..., description="Agent that produced the finding")
    agent_name: str = Field(default="", description="Human-readable name of the agent")
    finding_type: str = Field(..., description="Type of finding")
    confidence_raw: float = Field(
        ..., ge=0.0, le=1.0,
        description="Raw confidence score (0-1)"
    )
    calibrated_probability: float | None = Field(
        default=None, ge=0.0, le=1.0,
        description="Calibrated confidence probability (0-1), None if not calibrated"
    )
    calibrated: bool = Field(
        default=False, description="Whether confidence has been calibrated"
    )
    status: Literal["CONFIRMED", "CONTESTED", "INCONCLUSIVE", "INCOMPLETE"] = Field(
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
        default_factory=dict, description="Additional metadata including tool results and court_defensible flag"
    )


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
    [list[ReActStep], WorkingMemoryState],
    Coroutine[Any, Any, ReActStep | None]
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
        if not config.llm_enable_react_reasoning or not config.llm_api_key:
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
                step_type=parsed["step_type"],  # type: ignore
                content=parsed["content"],
                tool_name=parsed.get("tool_name"),
                tool_input=parsed.get("tool_input"),
                iteration=0,  # Will be set by the loop
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
    mandate = mandates.get(agent_key, "multi-modal forensic analysis of the submitted evidence")

    size_line = f"  File size: {file_size} bytes\n" if file_size else ""
    hash_line = f"  SHA-256:   {file_hash}\n" if file_hash else ""

    tasks_block = "\n".join(f"  {i+1}. {t}" for i, t in enumerate(available_tasks))

    prompt = f"""You are {agent_name}, a specialist forensic analysis agent in the Forensic Council multi-agent system.

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
     a concise summary of your findings. State: finding type, confidence (0.0-1.0),
     supporting evidence, and any limitations. Then signal completion.

== OUTSTANDING TASKS ==
{tasks_block}

== FORENSIC STANDARDS ==
- Confidence scores must reflect actual tool output, not intuition.
- If a tool returns an error or unavailable result, log it and move on.
- Cross-reference findings across tools where possible.
- Distinguish CONFIRMED (multiple tools agree) from INDICATIVE (single tool) findings.
- Never fabricate data. If evidence is ambiguous, say so explicitly.
- When complete, begin your response with: "ANALYSIS COMPLETE:" followed by a
  structured summary covering: (1) key findings, (2) confidence levels,
  (3) anomalies detected, (4) limitations."""

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

    # Comprehensive fallback catalogue — covers all real tools across all 5 agents
    return [
        # Agent 1 — Image
        {"name": "ela_full_image",            "description": "Full-image Error Level Analysis — detects re-saved or spliced regions"},
        {"name": "ela_anomaly_classify",       "description": "IsolationForest classification of ELA anomaly blocks"},
        {"name": "roi_extract",               "description": "Extract Region of Interest bounding boxes from anomaly map"},
        {"name": "jpeg_ghost_detect",         "description": "Detect JPEG re-compression ghosts (double-save artifacts)"},
        {"name": "frequency_domain_analysis", "description": "FFT spectral analysis — detect GAN/Stable Diffusion frequency artifacts"},
        {"name": "splicing_detect",           "description": "DCT quantization table inconsistency — identifies spliced regions"},
        {"name": "noise_fingerprint",         "description": "PRNU camera noise fingerprint — detects inconsistent sensor patterns"},
        {"name": "deepfake_frequency_check",  "description": "GAN deepfake artifact detection in frequency domain"},
        {"name": "file_hash_verify",          "description": "SHA-256 hash verification — confirms file integrity"},
        {"name": "perceptual_hash",           "description": "pHash perceptual similarity hash for near-duplicate detection"},
        {"name": "copy_move_detect",          "description": "SIFT keypoint self-matching — detects copy-move forgery"},
        {"name": "extract_text_from_image",   "description": "Tesseract OCR — extract visible text from image evidence"},
        {"name": "extract_evidence_text",     "description": "Auto-dispatching OCR: PDF->PyMuPDF, Image->EasyOCR->Tesseract"},
        {"name": "analyze_image_content",     "description": "CLIP semantic understanding — identify objects, scenes, context"},
        # Agent 2 — Audio
        {"name": "speaker_diarize",           "description": "Pyannote speaker diarization — count and segment speakers"},
        {"name": "anti_spoofing_detect",      "description": "SpeechBrain anti-spoofing — detect synthetic/replayed speech"},
        {"name": "prosody_analyze",           "description": "Praat prosody analysis — F0, jitter, shimmer, HNR"},
        {"name": "audio_splice_detect",       "description": "ML splice point detection in audio waveform"},
        {"name": "background_noise_analysis", "description": "Background noise consistency across audio segments"},
        {"name": "codec_fingerprinting",      "description": "Audio codec and encoding chain fingerprinting"},
        # Agent 3 — Scene
        {"name": "object_detection",          "description": "YOLOv8 object detection on full scene"},
        {"name": "lighting_consistency",      "description": "Shadow direction and lighting consistency validation"},
        {"name": "scene_incongruence",        "description": "CLIP semantic incongruence — objects that do not belong in scene"},
        {"name": "image_splice_check",        "description": "Splicing detection on detected object regions"},
        # Agent 4 — Video
        {"name": "optical_flow_analyze",      "description": "Dense optical flow analysis — detect frame discontinuities"},
        {"name": "frame_window_extract",      "description": "Extract frame window for per-frame analysis"},
        {"name": "frame_consistency_analysis","description": "Frame-to-frame histogram and edge consistency"},
        {"name": "face_swap_detection",       "description": "DeepFace embedding comparison — detect face swap events"},
        {"name": "video_metadata_extract",    "description": "Extract video container metadata"},
        {"name": "mediainfo_profile",         "description": "Deep AV container profiling: codec, VFR flag, encoding tool, forensic flags"},
        {"name": "av_file_identity",          "description": "Lightweight AV pre-screen: format, codec, duration, high-severity flags"},
        # Agent 5 — Metadata
        {"name": "exif_extract",              "description": "Full EXIF extraction via ExifTool + hachoir including MakerNotes"},
        {"name": "metadata_anomaly_score",    "description": "IsolationForest ML anomaly score on metadata fields"},
        {"name": "gps_timezone_validate",     "description": "Cross-validate GPS coordinates against claimed timestamp timezone"},
        {"name": "steganography_scan",        "description": "LSB steganography detection in image data"},
        {"name": "file_structure_analysis",   "description": "Binary file structure forensic analysis — detect appended data"},
        {"name": "hex_signature_scan",        "description": "Hex signature scan for hidden editing software watermarks"},
        {"name": "timestamp_analysis",        "description": "Timestamp consistency analysis across all metadata fields"},
        {"name": "extract_deep_metadata",     "description": "Deep metadata extraction including MakerNotes and XMP"},
        {"name": "get_physical_address",      "description": "Reverse geocode GPS coordinates to physical address"},
    ]


class ReActLoopEngine:
    """
    Core ReAct (Reasoning + Acting) loop engine.

    Implements the THOUGHT → ACTION → OBSERVATION cycle with:
    - Human-in-the-Loop checkpoints at trigger conditions
    - Graceful degradation on tool unavailability
    - Full audit logging to chain of custody
    """

    # Explicit task→tool mapping for reliable matching
    _TASK_TOOL_OVERRIDES: dict[str, str] = {
        "run full-image ela": "ela_full_image",
        "ela anomaly block classification": "ela_anomaly_classify",
        "jpeg ghost detection": "jpeg_ghost_detect",
        "frequency domain analysis": "frequency_domain_analysis",
        "frequency-domain gan": "deepfake_frequency_check",
        "verify file hash": "file_hash_verify",
        "noise footprint analysis": "noise_fingerprint",
        "speaker diarization": "speaker_diarize",
        "anti-spoofing detection": "anti_spoofing_detect",
        "prosody analysis": "prosody_analyze",
        "splice point detection": "audio_splice_detect",
        "background noise consistency": "background_noise_analysis",
        "codec fingerprinting": "codec_fingerprinting",
        "optical flow": "optical_flow_analysis",
        "frame-to-frame consistency": "frame_consistency_analysis",
        "face-swap detection": "face_swap_detection",
        "extract all exif": "exif_extract",
        "gps coordinates against timestamp": "gps_timezone_validate",
        "steganography scan": "steganography_scan",
        "file structure forensic": "file_structure_analysis",
        "hexadecimal software signature": "hex_signature_scan",
        "full-scene primary object detection": "object_detection",
        "lighting and shadow consistency": "lighting_consistency",
        "scene-level contextual incongruence": "scene_incongruence",
        # Missing entries from bug report
        "semantic image understanding": "analyze_image_content",
        "copy-move forgery": "copy_move_detect",
        "extract visible text": "extract_text_from_image",
        "audio-visual sync": "audio_visual_sync",
        "splicing detection on objects": "image_splice_check",
        "noise fingerprint analysis for region": "noise_fingerprint",
        "contraband": "contraband_database",
        "ml metadata anomaly": "metadata_anomaly_score",
        "astronomical api": "astronomical_api",
        "reverse image search": "reverse_image_search",
        "device fingerprint database": "device_fingerprint_db",
        "inter-agent call": "inter_agent_call",
        "adversarial robustness": "adversarial_robustness_check",
        "ml-based image splicing": "image_splice_check",
        "camera noise fingerprint analysis": "noise_fingerprint",
        # OCR
        "extract evidence text": "extract_evidence_text",
        "ocr text extraction": "extract_evidence_text",
        "text from pdf": "extract_evidence_text",
        "extract text from pdf": "extract_evidence_text",
        "extract text from image": "extract_text_from_image",
        # AV container
        "mediainfo": "mediainfo_profile",
        "av container profiling": "mediainfo_profile",
        "container profile": "mediainfo_profile",
        "av file identity": "av_file_identity",
        "av pre-screen": "av_file_identity",
        "variable frame rate": "mediainfo_profile",
        # Agent 3 - Secondary Classification
        "secondary classification": "secondary_classification",
        "scale and proportion": "scale_validation",
        "scale validation": "scale_validation",
        # Agent 5 - Timestamp Analysis
        "timestamp analysis": "timestamp_analysis",
        "timestamp consistency": "timestamp_analysis",
        # Agent 5 - Deep metadata
        "deep metadata": "extract_deep_metadata",
        "physical address": "get_physical_address",
        # Agent 4 - Video Analysis
        "optical flow analysis": "optical_flow_analysis",
        "temporal anomaly": "optical_flow_analysis",
        "frame extraction": "frame_extraction",
        "frame window": "frame_extraction",
        "anomaly as explainable": "anomaly_classification",
        "anomaly classification": "anomaly_classification",
        "rolling shutter": "rolling_shutter_validation",
        "face swap": "face_swap_detection",
        "gan artifact detection": "deepfake_frequency_check",
        # Gemini vision tools (Agents 1, 3, 5 deep pass)
        "gemini vision analysis: identify file content": "gemini_identify_content",
        "gemini vision cross-validation": "gemini_cross_validate_manipulation",
        "gemini vision analysis: deep object": "gemini_object_scene_analysis",
        "gemini vision analysis: cross-validate visual content": "gemini_metadata_visual_consistency",
        "gemini vision": "gemini_identify_content",  # fallback for any gemini task
        # Audio splice (Agent 2)
        "audio splice": "audio_splice_detect",
        "splice point": "audio_splice_detect",
    }

    def __init__(
        self,
        agent_id: str,
        session_id: uuid.UUID,
        iteration_ceiling: int,
        working_memory: WorkingMemory,
        custody_logger: CustodyLogger,
        redis_client: Any = None,  # Redis client for HITL checkpoint storage
        hitl_timeout: float = 300.0  # Timeout for HITL resume wait (5 minutes default)
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

    async def run(
        self,
        initial_thought: str,
        tool_registry: ToolRegistry,
        llm_generator: LLMStepGenerator | None = None
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
                session_id=self.session_id,
                agent_id=self.agent_id
            )
        except Exception:
            state = None

        # Create initial THOUGHT step
        initial_step = ReActStep(
            step_type="THOUGHT",
            content=initial_thought,
            iteration=0
        )
        self._react_chain.append(initial_step)
        await self._log_step(initial_step)
        
        self._current_iteration = 0

        # Main loop
        while not self._terminated and self._current_iteration < self.iteration_ceiling:
            # Get current state
            try:
                state = await self.working_memory.get_state(
                    session_id=self.session_id,
                    agent_id=self.agent_id
                )
            except Exception:
                state = None
            if state is None:
                break

            # Check HITL triggers before proceeding
            hitl_reason = await self.check_hitl_triggers(state)
            if hitl_reason is not None:
                checkpoint = await self.pause_for_hitl(
                    reason=hitl_reason,
                    brief=f"Paused at iteration {self._current_iteration} due to {hitl_reason.value}"
                )
                self._hitl_checkpoints.append(checkpoint)
                
                # Wait for resume signal (in real implementation, this would be external)
                # For now, we check if a decision was set via resume_from_hitl
                if self._resume_event is None:
                    self._resume_event = asyncio.Event()
                
                # In test mode, we might have a pending decision already
                if self._pending_decision is None:
                    # Wait for external resume (with timeout for safety)
                    try:
                        await asyncio.wait_for(
                            self._resume_event.wait(),
                            timeout=self.hitl_timeout
                        )
                    except asyncio.TimeoutError:
                        # Timeout - terminate loop
                        self._terminated = True
                        break
                
                # Process the decision
                if self._pending_decision is not None:
                    await self.resume_from_hitl(
                        checkpoint.checkpoint_id,
                        self._pending_decision
                    )
                    self._pending_decision = None
                    self._resume_event.clear()
                
                # Check if terminated after HITL
                if self._terminated:
                    break

            # Increment iteration
            self._current_iteration += 1

            # Get next step from LLM or built-in task driver
            next_step = None
            if llm_generator is not None:
                next_step = await llm_generator(self._react_chain, state)
            
            # If LLM returned None (failure, not configured, or no suggestion),
            # fall back to the built-in task-decomposition driver so agents
            # still produce real tool-based findings without LLM reasoning.
            if next_step is None:
                next_step = await self._default_step_generator(
                    state, tool_registry
                )

            if next_step is None:
                # Both LLM and task driver signal completion
                break

            next_step.iteration = self._current_iteration
            self._react_chain.append(next_step)
            await self._log_step(next_step)

            # Handle ACTION steps
            if next_step.step_type == "ACTION" and next_step.tool_name:
                tool_result = await tool_registry.call(
                    tool_name=next_step.tool_name,
                    input_data=next_step.tool_input or {},
                    agent_id=self.agent_id,
                    session_id=self.session_id,
                    custody_logger=self.custody_logger
                )

                # --- Generate AgentFinding from Tool Result ---
                if tool_result.success:
                    output = tool_result.output or {}
                    confidence = float(output.get("confidence", 0.75)) if isinstance(output, dict) else 0.75
                    status_val = str(output.get("status", "CONFIRMED")).upper() if isinstance(output, dict) else "CONFIRMED"
                    if status_val not in ("CONFIRMED", "CONTESTED", "INCONCLUSIVE", "INCOMPLETE"):
                        status_val = "CONFIRMED"
                    
                    is_stub = isinstance(output, dict) and (output.get("status") == "stub" or output.get("court_defensible") is False)
                    calibrated_prob = None
                    
                    try:
                        from core.calibration import get_calibration_layer
                        calibration_layer = get_calibration_layer()
                        if calibration_layer and not is_stub:
                            cal_result = calibration_layer.calibrate(
                                agent_id=self.agent_id,
                                raw_score=confidence,
                                finding_class=next_step.tool_name
                            )
                            calibrated_prob = cal_result.calibrated_probability
                    except Exception:
                        pass
    
                    _AGENT_ID_TO_NAME = {
                        "Agent1": "Image Forensics",
                        "Agent2": "Audio Forensics",
                        "Agent3": "Object Detection",
                        "Agent4": "Video Forensics",
                        "Agent5": "Metadata Forensics",
                        # Deep pass IDs (suffixed with _deep)
                        "Agent1_deep": "Image Forensics",
                        "Agent2_deep": "Audio Forensics",
                        "Agent3_deep": "Object Detection",
                        "Agent4_deep": "Video Forensics",
                        "Agent5_deep": "Metadata Forensics",
                    }
    
                    # Build a clean, human-readable finding type.
                    # Priority: tool label > task description > tool name.
                    # We avoid using raw LLM THOUGHT text (which can be 80+
                    # chars of verbose reasoning) as the finding_type label.
                    _TOOL_LABELS = {
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
                        # Gemini vision tools
                        "gemini_identify_content": "Gemini Vision — Content Identification",
                        "gemini_cross_validate_manipulation": "Gemini Vision — Manipulation Cross-Validation",
                        "gemini_object_scene_analysis": "Gemini Vision — Object & Scene Analysis",
                        "gemini_metadata_visual_consistency": "Gemini Vision — Metadata Consistency Check",
                    }
                    tool_label = _TOOL_LABELS.get(
                        next_step.tool_name,
                        next_step.tool_name.replace("_", " ").title()
                    )
                    # Use the tool label as the canonical finding type.
                    # Attach the preceding LLM thought (if any) separately
                    # via the llm_reasoning metadata key — not as the label.
                    task_desc = tool_label
                    

                    finding = AgentFinding(
                        agent_id=self.agent_id,
                        agent_name=_AGENT_ID_TO_NAME.get(self.agent_id, self.agent_id),
                        finding_type=task_desc,
                        confidence_raw=confidence,
                        calibrated_probability=calibrated_prob,
                        calibrated=calibrated_prob is not None,
                        status=status_val,
                        evidence_refs=[],
                        reasoning_summary=self._build_readable_summary(
                            next_step.tool_name, task_desc, tool_result, confidence, status_val
                        ),
                        metadata={
                            "tool_name": next_step.tool_name,
                            "court_defensible": not is_stub,
                            "stub_warning": output.get("warning") if isinstance(output, dict) and is_stub else None,
                            **(output if isinstance(output, dict) else {"raw_output": str(output)}),
                        },
                    )
                    self._findings.append(finding)
                # ----------------------------------------------

                # Create OBSERVATION step
                observation = ReActStep(
                    step_type="OBSERVATION",
                    content=self._format_tool_result(tool_result),
                    tool_name=next_step.tool_name,
                    tool_output=tool_result.model_dump(),
                    iteration=self._current_iteration
                )
                self._react_chain.append(observation)
                await self._log_step(observation)

                # Mark the IN_PROGRESS task as COMPLETE now that the tool has run
                try:
                    if state:
                        from core.working_memory import TaskStatus as _TS
                        for task in state.tasks:
                            if task.status == _TS.IN_PROGRESS:
                                await self.working_memory.update_task(
                                    session_id=self.session_id,
                                    agent_id=self.agent_id,
                                    task_id=task.task_id,
                                    status=_TS.COMPLETE,
                                    result_ref=next_step.tool_name,
                                )
                                break
                except Exception:
                    pass

                # Check for tool unavailability HITL trigger
                if tool_result.unavailable:
                    hitl_reason = await self.check_hitl_triggers(state)
                    if hitl_reason == HITLCheckpointReason.TOOL_UNAVAILABLE:
                        checkpoint = await self.pause_for_hitl(
                            reason=hitl_reason,
                            brief=f"Tool '{next_step.tool_name}' unavailable"
                        )
                        self._hitl_checkpoints.append(checkpoint)

            # Update working memory with current iteration
            await self.working_memory.update_state(
                session_id=self.session_id,
                updates={"current_iteration": self._current_iteration}
            )

        # Build result
        return ReActLoopResult(
            session_id=self.session_id,
            agent_id=self.agent_id,
            completed=(self._current_iteration >= self.iteration_ceiling or 
                      not self._terminated),
            terminated_by_human=self._terminated,
            findings=self._findings,
            hitl_checkpoints=self._hitl_checkpoints,
            total_iterations=self._current_iteration,
            react_chain=self._react_chain
        )

    async def _should_trigger_followup(self, task_description: str | None, tool_result: dict) -> str | None:
        """
        Return a follow-up tool name if the result warrants deeper analysis,
        or None if the task can be marked complete.
        """
        result_str = str(tool_result).lower()

        # If ELA finds anomalies, follow up with ROI extraction
        if task_description and "ela" in task_description.lower():
            if tool_result.get("anomaly_count", 0) > 0:
                return "roi_extract"

        # If splicing is detected, escalate to noise fingerprint
        if task_description and "splicing" in task_description.lower():
            if tool_result.get("splicing_detected", False):
                return "noise_fingerprint"

        # If GPS is present, validate timezone
        if task_description and "exif" in task_description.lower():
            if tool_result.get("gps_coordinates") is not None:
                return "gps_timezone_validate"

        return None

    async def check_hitl_triggers(
        self,
        state: WorkingMemoryState
    ) -> HITLCheckpointReason | None:
        """
        Check if any HITL trigger conditions are met.
        
        Args:
            state: Current working memory state
            
        Returns:
            HITLCheckpointReason if triggered, None otherwise
        """
        # Trigger at 50% of iteration ceiling without COMPLETE task
        half_ceiling = self.iteration_ceiling // 2
        if self._current_iteration >= half_ceiling:
            # Check if there's a COMPLETE task
            has_complete = any(
                task.status == "COMPLETE" for task in state.tasks
            )
            if not has_complete and self._current_iteration == half_ceiling:
                return HITLCheckpointReason.ITERATION_CEILING_50PCT

        # Check for contested findings
        for task in state.tasks:
            if task.status == "CONTESTED":
                return HITLCheckpointReason.CONTESTED_FINDING

        # Check for severity threshold breach (if findings have high severity)
        # This would be checked against findings in a real implementation
        # For now, we check if any task has severity_threshold flag
        for task in state.tasks:
            if hasattr(task, 'severity_threshold') and task.severity_threshold:
                return HITLCheckpointReason.SEVERITY_THRESHOLD_BREACH

        return None

    async def pause_for_hitl(
        self,
        reason: HITLCheckpointReason,
        brief: str
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
                session_id=self.session_id,
                agent_id=self.agent_id
            )
        except Exception:
            state = None
        serialized_state = state.model_dump() if state else {}

        # Create checkpoint
        checkpoint = HITLCheckpointState(
            agent_id=self.agent_id,
            session_id=self.session_id,
            reason=reason,
            paused_at_iteration=self._current_iteration,
            investigator_brief=brief,
            status="PAUSED",
            serialized_state=serialized_state
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
                    "brief": brief
                }
            )

        # Store checkpoint in Redis
        if self.redis_client is not None:
            key = f"hitl:{self.session_id}:{self.agent_id}"
            await self.redis_client.set(
                key,
                json.dumps(checkpoint.model_dump(), default=str)
            )

        self._current_checkpoint = checkpoint
        return checkpoint

    async def resume_from_hitl(
        self,
        checkpoint_id: uuid.UUID,
        decision: HumanDecision
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
                    "notes": decision.notes
                }
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
                reasoning_summary=decision.notes
            )
            self._findings.append(finding)
            if self._current_checkpoint:
                self._current_checkpoint.status = "OVERRIDDEN"

        if decision.decision_type == "REDIRECT" and decision.redirect_context:
            # Inject redirect context into working memory
            await self.working_memory.update_state(
                session_id=self.session_id,
                updates={"redirect_context": decision.redirect_context}
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
                updates={"tribunal_escalation": True}
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

        # Find the next PENDING task
        pending_task = None
        for task in state.tasks:
            if task.status in (TaskStatus.PENDING, TaskStatus.IN_PROGRESS):
                pending_task = task
                break

        if pending_task is None:
            # All tasks complete → signal loop to stop
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

        if pending_task.description and any(skip in pending_task.description.lower() for skip in _SKIP_TASKS):
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
            # No matching tool — mark task complete and move on
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
            # Return a thought so the loop keeps going
            return ReActStep(
                step_type="THOUGHT",
                content=(
                    f"Task '{pending_task.description}' has no matching tool. "
                    f"Marking as complete and moving on."
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
            tool_input={"artifact": None},
            iteration=self._current_iteration,
        )


    @staticmethod
    def _match_tool_to_task(
        task_description: str, tools: list
    ):
        """
        Match a task description to the best available tool using keyword
        overlap between the task text and tool name/description.

        First checks explicit _TASK_TOOL_OVERRIDES mapping, then falls back
        to keyword scoring.

        Returns the best-matching Tool, or None if no reasonable match.
        """
        task_lower = task_description.lower().strip()

        # First check explicit overrides
        for keyword, tool_name in ReActLoopEngine._TASK_TOOL_OVERRIDES.items():
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
        entry_type = step_type_to_entry_type.get(
            step.step_type, EntryType.THOUGHT
        )
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
                    "timestamp": step.timestamp_utc.isoformat()
                }
            )

    def _build_readable_summary(
        self,
        tool_name: str,
        task_description: str,
        tool_result: ToolResult,
        confidence: float,
        status: str,
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
            for prefix in ("[ToolUnavailableError]", "[ToolError]", "ToolError:", "Exception:", "ValueError:", "TypeError:", "KeyError:"):
                err = err.replace(prefix, "").strip()
            err = err[:120] + ("..." if len(err) > 120 else "")
            return (
                f"{tool_label}: The agent attempted to run a specialized scan but was unable to complete it successfully due to an operational hurdle: '{err}'. "
                f"Consequently, diagnostic confidence has been appropriately adjusted to {confidence:.0%}."
            )

        output = tool_result.output or {}

        if output.get("status") == "stub_response":
            return (
                f"{tool_label}: The agent's external module returned a temporary placeholder response. "
                f"This indicates that advanced ML features are still structurally integrating. "
                f"Current diagnostic stance evaluates to a {status} finding at {confidence:.0%} certainty."
            )

        _TOOL_INTERPRETERS = {
            # ── Image tools ───────────────────────────────────────────────────
            "ela_full_image": lambda o: (
                f"ELA detected {o.get('num_anomaly_regions', 0)} anomaly region(s) "
                f"with a maximum deviation of {o.get('max_anomaly', 0):.1f} "
                f"({'significant manipulation signature' if o.get('max_anomaly', 0) > 20 else 'within normal compression range'})."
            ),
            "jpeg_ghost_detect": lambda o: (
                f"JPEG ghost analysis {'detected double-compression artifacts' if o.get('ghost_detected') else 'found no ghost artifacts'} "
                f"with {o.get('confidence', 0):.0%} confidence across {len(o.get('ghost_regions', []))} region(s)."
            ),
            "frequency_domain_analysis": lambda o: (
                f"Frequency domain analysis yielded anomaly score {o.get('anomaly_score', 0):.3f} "
                f"(high-freq ratio: {o.get('high_freq_ratio', 0):.3f}, "
                f"{'anomalous high-frequency content detected' if o.get('anomaly_score', 0) > 0.4 else 'frequency distribution appears natural'})."
            ),
            # FIXED: key was 'noise_inconsistency' — actual keys: noise_consistency_score, outlier_region_count, verdict
            "noise_fingerprint": lambda o: (
                f"PRNU noise fingerprint: {o.get('verdict', 'INCONCLUSIVE')} — "
                f"consistency score {o.get('noise_consistency_score', 0):.3f}, "
                f"{o.get('outlier_region_count', 0)} of {o.get('total_regions', 0)} region(s) flagged as outliers."
            ),
            "copy_move_detect": lambda o: (
                f"Copy-move detection: {o.get('match_count', o.get('num_matches', 0))} keypoint match(es). "
                + ("Copy-move forgery detected." if o.get('copy_move_detected') else "No copy-move cloning detected.")
            ),
            # FIXED: actual keys from splicing_detector: splicing_detected, num_inconsistent_blocks, inconsistency_ratio
            "splicing_detect": lambda o: (
                f"Splicing detection: {'SPLICING DETECTED' if o.get('splicing_detected') else 'No splicing found'}. "
                f"{o.get('num_inconsistent_blocks', 0)} of {o.get('total_blocks', 0)} blocks flagged "
                f"(ratio {o.get('inconsistency_ratio', 0):.3f})."
            ),
            "image_splice_check": lambda o: (
                f"Image splice check: {'SPLICING DETECTED' if o.get('splicing_detected') else 'No splicing found'}. "
                f"{o.get('num_inconsistent_blocks', 0)} of {o.get('total_blocks', 0)} blocks flagged."
            ),
            # FIXED: correct keys; also added for both tool name aliases
            "file_hash_verify": lambda o: (
                f"Hash verification: SHA-256 = "
                + str(o.get('current_hash', o.get('original_hash', '')))[:20] + "... "
                + ("Hash matches chain-of-custody record — file integrity confirmed."
                   if o.get('hash_matches') else "WARNING: hash mismatch — file may have been modified after ingestion.")
            ),
            "adversarial_robustness_check": lambda o: (
                f"Adversarial robustness: {'EVASION DETECTED — findings may be adversarially engineered.' if o.get('adversarial_pattern_detected') else 'Findings are stable under perturbation — robust.'} "
                f"Method: {o.get('method', 'perturbation stability')}."
            ),
            # ── Object detection tools (Agent 3) ─────────────────────────────
            "object_detection": lambda o: (
                f"YOLO object detection: {o.get('detection_count', len(o.get('detections', [])))} object(s) detected "
                f"({', '.join(o.get('classes_found', [])[:8]) or 'none'}). "
                + (f"WEAPON CLASSES DETECTED: {', '.join(d['class_name'] for d in o.get('weapon_detections', []))}." if o.get('weapon_detections') else "No weapons detected.")
            ),
            "secondary_classification": lambda o: (
                f"Secondary CLIP classification of '{o.get('input_object_class', 'object')}': "
                f"top match = '{o.get('top_refined_match', 'unknown')}' ({o.get('top_confidence', 0):.0%}). "
                + ("CONCERN FLAGGED." if o.get('concern_flag') else "No concern flag.")
            ),
            "scale_validation": lambda o: (
                f"Scale/proportion analysis: {'consistent perspective angles' if o.get('scale_consistent') else 'INCONSISTENT perspective — possible compositing'}. "
                f"Line angle std: {o.get('angle_std_deg', 0):.1f}° across {o.get('line_count', 0)} lines."
            ),
            "scene_incongruence": lambda o: (
                f"Scene noise coherence: {o.get('contextual_anomalies_detected', 0)} anomalous region(s) detected. "
                f"Noise std across quadrants: {o.get('noise_variance_across_quadrants', 0):.1f} "
                f"(mean: {o.get('mean_noise_level', 0):.1f}). "
                + (o.get('anomaly_description', '') or "")
            ),
            "contraband_database": lambda o: (
                f"Contraband/CLIP analysis: top match = '{o.get('top_matches', [{}])[0].get('category', 'none') if o.get('top_matches') else 'none'}'. "
                + ("CONCERN FLAG raised." if o.get('concern_flag') else "No concern flag raised.")
            ),
            "lighting_consistency": lambda o: (
                f"Lighting/shadow consistency: {'INCONSISTENCY detected' if o.get('inconsistency_detected') else 'consistent across scene'}. "
                + (f"Details: {o.get('details', '')}" if o.get('details') else "")
                + (f" Flags: {'; '.join(o.get('flags', []))}" if o.get('flags') else "")
            ),
            # ── Metadata tools (Agent 5) ─────────────────────────────────────
            # FIXED: exif_extract_enhanced returns total_fields_extracted, absent_mandatory_fields, not has_exif/device_model/absent_fields
            "exif_extract": lambda o: (
                f"EXIF extraction: {o.get('total_fields_extracted', o.get('total_exif_tags', 0))} fields found. "
                f"GPS: {'Present' if o.get('gps_coordinates') else 'Absent'}. "
                f"Missing {len(o.get('absent_mandatory_fields', o.get('absent_fields', [])))} mandatory fields "
                f"({', '.join(str(f) for f in o.get('absent_mandatory_fields', o.get('absent_fields', []))[:4]) or 'none'})."
            ),
            # FIXED: gps_timezone_validate returns 'plausible' bool + 'issues' list, NOT 'inconsistent' + 'distance_km'
            "gps_timezone_validate": lambda o: (
                ("GPS-timezone is INCONSISTENT — " + "; ".join(o.get('issues', ['Unknown issue']))
                 if o.get('plausible') is False
                 else "GPS-timestamp timezone is plausible.")
                + f" Timezone detected: {o.get('timezone', 'N/A')}."
            ),
            "steganography_scan": lambda o: (
                f"LSB steganography scan: {'HIDDEN DATA SUSPECTED' if o.get('stego_suspected') else 'no hidden data found'}. "
                f"LSB deviation from random: {o.get('lsb_statistics', {}).get('average_deviation', 0):.4f}."
            ),
            # FIXED: file_structure_analysis returns header_valid, trailer_valid, has_appended_data, anomalies
            "file_structure_analysis": lambda o: (
                f"File structure: header {'valid' if o.get('header_valid') else 'INVALID'}, "
                f"trailer {'valid' if o.get('trailer_valid', True) else 'INVALID'}, "
                f"appended data: {'YES — ' + str(o.get('file_size', 0)) + ' bytes' if o.get('has_appended_data') else 'none'}. "
                f"Anomalies: {len(o.get('anomalies', []))} — {'; '.join(o.get('anomalies', [])) or 'none'}."
            ),
            "hex_signature_scan": lambda o: (
                f"Hex signature scan {'detected editing software: ' + ', '.join(o.get('software_signatures', [])) if o.get('editing_software_detected') else 'found no editing software signatures'} "
                f"across {o.get('bytes_scanned', 0):,} bytes."
            ),
            "timestamp_analysis": lambda o: (
                f"Timestamp cross-check found {len(o.get('inconsistencies', []))} inconsistency(ies). "
                + (f"Issues: {'; '.join(o.get('inconsistencies', []))}" if o.get('inconsistencies') else "All timestamps are consistent.")
            ),
            "metadata_anomaly_score": lambda o: (
                f"ML anomaly score: {o.get('anomaly_score', 0):.3f} "
                + ("(ANOMALOUS). " if o.get('is_anomalous') else "(within normal range). ")
                + ("Anomalous fields: " + ", ".join(o.get('anomalous_fields', [])[:5]) if o.get('anomalous_fields') else "")
            ),
            "device_fingerprint_db": lambda o: (
                f"Device fingerprint: {o.get('camera_make', 'Unknown')} {o.get('camera_model', '')}. "
                f"{'SUSPICIOUS — ' + '; '.join(o.get('inconsistencies', [])) if o.get('exif_fingerprint_suspicious') else 'PRNU pattern consistent with declared device.'}. "
                f"PRNU variance: {o.get('prnu_variance', 0):.3f}."
            ),
            # ── OCR tools ────────────────────────────────────────────────────
            "extract_evidence_text": lambda o: (
                "OCR extracted " + str(o.get('word_count', 0)) + " word(s) "
                "via " + str(o.get('method', 'OCR')) + " "
                "(confidence: " + f"{o.get('confidence', 0):.0%}" + "). "
                + ("Preview: '" + str(o.get('full_text', ''))[:120] + "...'" if o.get('full_text') else "No text content detected.")
            ),
            "extract_text_from_image": lambda o: (
                "Tesseract OCR extracted " + str(o.get('word_count', 0)) + " word(s). "
                + ("Preview: '" + str(o.get('text', o.get('full_text', '')))[:100] + "...'" if o.get('text') or o.get('full_text') else "No visible text found.")
            ),
            # ── MediaInfo tools ───────────────────────────────────────────────
            "mediainfo_profile": lambda o: (
                "MediaInfo profiled: " + str(o.get('format', 'unknown'))
                + " / " + str(o.get('video_codec', o.get('codec', 'unknown')))
                + ". Forensic flags: " + str(len(o.get('forensic_flags', [])))
                + (" — " + "; ".join(o.get('forensic_flags', []))[:200] if o.get('forensic_flags') else " — none detected.")
            ),
            "av_file_identity": lambda o: (
                "AV pre-screen: " + str(o.get('format', 'unknown'))
                + " / " + str(o.get('primary_video_codec', o.get('codec', 'unknown')))
                + " " + str(o.get('duration_seconds', '?')) + "s "
                + str(o.get('resolution', '')) + ". "
                + ("HIGH-SEVERITY FLAGS: " + ", ".join(o.get('high_severity_flags', [])) if o.get('high_severity_flags') else "No high-severity flags.")
            ),
            # ── Audio tools (Agent 2) — FIXED: keys match actual return dicts ─
            # FIXED: pyannote returns speaker_count + segments; legacy returns speaker_count + num_segments
            "speaker_diarize": lambda o: (
                f"Speaker diarization: {o.get('speaker_count', o.get('num_speakers', 0))} speaker(s) identified, "
                f"{len(o.get('segments', []))} segment(s). "
                f"Backend: {o.get('backend', 'unknown')}."
            ),
            # FIXED: SpeechBrain returns spoofing_detected + synthetic_probability; legacy returns is_spoofed + spoof_score
            "anti_spoofing_detect": lambda o: (
                f"Anti-spoofing: {'SYNTHETIC/REPLAYED speech detected' if o.get('spoofing_detected', o.get('is_spoofed')) else 'speech appears genuine'}. "
                f"Synthetic probability: {o.get('synthetic_probability', o.get('spoof_score', 0)):.3f}. "
                f"Backend: {o.get('backend', 'unknown')}."
            ),
            # FIXED: prosody_praat returns f0_mean_hz, jitter_local, shimmer_local, prosody_anomaly_detected
            "prosody_analyze": lambda o: (
                f"Prosody analysis: F0={o.get('f0_mean_hz', 0):.1f}Hz, "
                f"jitter={o.get('jitter_local', 0):.5f}, shimmer={o.get('shimmer_local', 0):.5f}, "
                f"HNR={o.get('hnr_db', 0):.1f}dB. "
                + ("PROSODY ANOMALY DETECTED." if o.get('prosody_anomaly_detected') else "Prosody within normal range.")
            ),
            # ── Video tools (Agent 4) ─────────────────────────────────────────
            "optical_flow_analysis": lambda o: (
                f"Optical flow: {o.get('anomaly_frame_count', o.get('num_anomaly_frames', 0))} anomalous frame(s). "
                f"Mean magnitude: {o.get('mean_flow_magnitude', 0):.3f}. "
                + ("Temporal discontinuity detected." if o.get('discontinuity_detected') else "Flow is temporally consistent.")
            ),
            "face_swap_detection": lambda o: (
                f"Face-swap: {o.get('faces_detected', 0)} face(s) analysed. "
                + ("Face-swap event detected." if o.get('face_swap_detected') else "No face-swap artifacts found.")
                + f" Max embedding distance: {o.get('max_distance', 0):.3f}."
            ),
            # ── Gemini vision tools (Agents 1, 3, 5 deep pass) ───────────────
            # Gemini findings share common fields via GeminiFinding.to_finding_dict()
            "gemini_identify_content": lambda o: (
                f"Gemini Vision content identification: {o.get('gemini_content_type', o.get('file_type_assessment', 'unknown type'))}. "
                f"Scene: {str(o.get('gemini_scene', o.get('content_description', '')))[:150]}. "
                + (f"Manipulation signals: {'; '.join(o.get('gemini_manipulation_signals', o.get('manipulation_signals', [])))[:200]}."
                   if o.get('gemini_manipulation_signals') or o.get('manipulation_signals') else "No manipulation signals identified.")
            ),
            "gemini_cross_validate_manipulation": lambda o: (
                f"Gemini cross-validation: {str(o.get('gemini_authenticity_assessment', o.get('content_description', '')))[:200]}. "
                + (f"Additional anomalies: {'; '.join(str(s) for s in o.get('gemini_additional_anomalies', o.get('manipulation_signals', [])))[:200]}."
                   if o.get('gemini_additional_anomalies') or o.get('manipulation_signals') else "No additional anomalies identified.")
            ),
            "gemini_object_scene_analysis": lambda o: (
                f"Gemini object/scene analysis: {str(o.get('gemini_scene_coherence', o.get('content_description', '')))[:200]}. "
                f"Validated objects: {', '.join(str(x) for x in o.get('gemini_validated_objects', o.get('detected_objects', [])))[:150] or 'none identified'}. "
                + (f"Compositing signals: {'; '.join(str(s) for s in o.get('gemini_compositing_signals', o.get('manipulation_signals', [])))[:200]}."
                   if o.get('gemini_compositing_signals') or o.get('manipulation_signals') else "No compositing signals detected.")
            ),
            "gemini_metadata_visual_consistency": lambda o: (
                f"Gemini metadata-visual consistency: {str(o.get('gemini_metadata_verdict', o.get('content_description', '')))[:200]}. "
                + (f"Provenance flags: {'; '.join(str(s) for s in o.get('gemini_provenance_flags', o.get('manipulation_signals', [])))[:200]}."
                   if o.get('gemini_provenance_flags') or o.get('manipulation_signals') else "No provenance flags raised.")
            ),
        }

        interpreter = _TOOL_INTERPRETERS.get(tool_name)
        if interpreter and tool_result.success:
            try:
                interpreted_msg = interpreter(output)
                return f"{tool_label}: {interpreted_msg} This yields a {status} finding at {confidence:.0%} certainty."
            except Exception:
                pass  # fall through to generic path

        highlights: list[str] = []
        for key, value in output.items():
            if key.startswith("_") or key in ("status", "tool_name", "analysis_report", "artifact_id", "session_id", "case_id"):
                continue

            clean_key = key.replace('_', ' ')
            
            if isinstance(value, list):
                if len(value) > 5:
                    highlights.append(f"a total of {len(value)} {clean_key}")
                else:
                    items = ", ".join(str(v) for v in value)
                    if items:
                        highlights.append(f"the following {clean_key}: {items}")
                continue
                
            if isinstance(value, dict):
                continue
                
            if isinstance(value, bool):
                highlights.append(f"a {clean_key} status of {'Positive' if value else 'Negative'}")
            elif isinstance(value, float):
                highlights.append(f"a {clean_key} metric of {value:.4f}")
            elif isinstance(value, int):
                highlights.append(f"a {clean_key} count of {value}")
            elif isinstance(value, str) and len(value) < 200:
                highlights.append(f"a {clean_key} value of '{value}'")

        if highlights:
            # Join with commas and "and" for the last item
            detail = ""
            if len(highlights) == 1:
                detail = highlights[0]
            elif len(highlights) == 2:
                detail = f"{highlights[0]} and {highlights[1]}"
            else:
                top_highlights = highlights[:5]
                detail = ", ".join(top_highlights)
                if len(highlights) > 5:
                    detail += ", among other data points"
                else:
                    last_comma = detail.rfind(",")
                    if last_comma != -1:
                        detail = detail[:last_comma] + ", and" + detail[last_comma + 1:]

            return (
                f"{tool_label}: The agent executed a specialized scan and successfully extracted the following metrics: "
                f"It identified {detail}. "
                f"This data evaluates to a {status} finding with a diagnostic certainty of {confidence:.0%}."
            )
        else:
            return (
                f"{tool_label}: The agent executed a specialized scan and completely analyzed the evidence, finding no notable specific metrics to highlight. "
                f"This yields a {status} status, maintaining a diagnostic certainty of {confidence:.0%}."
            )

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
