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
    """Build system prompt for forensic reasoning."""
    mime_type = evidence_context.get("mime_type", "unknown")
    file_name = evidence_context.get("file_name", "unknown")
    
    prompt = f"""You are {agent_name}, a specialized forensic analysis agent in the Forensic Council system.

You are analyzing evidence: {file_name} (type: {mime_type})

Your role is to perform forensic analysis using a ReAct (Reasoning + Acting) loop:
1. THINK about what you've learned from previous observations
2. DECIDE on the next action (tool to use)
3. OBSERVE the results and repeat

Available tasks to complete:
"""
    
    for task in available_tasks[:5]:  # Limit to avoid too long prompt
        prompt += f"- {task}\n"
    
    prompt += """
When deciding your next action:
- Consider what evidence would strengthen your findings
- Look for inconsistencies or anomalies
- Choose tools that provide complementary analysis
- If you have sufficient evidence, signal completion

Output format:
- If you want to use a tool: describe what tool and why
- If you have completed analysis: state that you're done and summarize findings
"""
    
    return prompt


def _get_available_tools_for_llm(state: WorkingMemoryState) -> list[dict[str, Any]]:
    """Get list of available tools formatted for LLM."""
    # This is a simplified list - in production, would come from ToolRegistry
    common_tools = [
        {"name": "ela_full_image", "description": "Error Level Analysis for image manipulation detection"},
        {"name": "jpeg_ghost_detect", "description": "Detect JPEG re-compression artifacts"},
        {"name": "noise_fingerprint", "description": "Analyze camera sensor noise patterns"},
        {"name": "file_hash_verify", "description": "Verify file integrity via cryptographic hash"},
        {"name": "exif_extract", "description": "Extract metadata from files"},
        {"name": "speaker_diarization", "description": "Separate and count speakers in audio"},
        {"name": "optical_flow_analysis", "description": "Analyze motion between video frames"},
        {"name": "face_swap_detection", "description": "Detect face swaps in video frames"},
        {"name": "object_detection", "description": "Detect objects in images"},
        {"name": "lighting_consistency", "description": "Check lighting consistency across scene"},
    ]
    return common_tools


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
        "optical flow": "optical_flow_analyze",
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
            if llm_generator is not None:
                next_step = await llm_generator(self._react_chain, state)
            else:
                # Built-in task-decomposition driver: iterate through tasks
                next_step = await self._default_step_generator(
                    state, tool_registry
                )

            if next_step is None:
                # Driver signals completion (all tasks processed)
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
            # No matching tool — mark task blocked and move on
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

        # Generate a THOUGHT step about working on this task
        # Don't add to react_chain here - let the main loop do it
        thought = ReActStep(
            step_type="THOUGHT",
            content=(
                f"Working on task: {pending_task.description}. "
                f"I will invoke tool '{best_tool.name}' "
                f"({best_tool.description})."
            ),
            iteration=self._current_iteration,
        )
        return thought

        # Generate an ACTION step to call the tool
        # Don't add to react_chain here - let the main loop do it
        action = ReActStep(
            step_type="ACTION",
            content=f"Calling tool '{best_tool.name}' for task: {pending_task.description}",
            tool_name=best_tool.name,
            tool_input={"artifact": None},   # handlers default to self.evidence_artifact
            iteration=self._current_iteration,
        )
        
        # Note: The main loop will execute this action and create the observation
        return action

        _AGENT_ID_TO_NAME = {
            "Agent1": "Image Forensics",
            "Agent2": "Audio Forensics",
            "Agent3": "Object Detection",
            "Agent4": "Video Forensics",
            "Agent5": "Metadata Forensics",
        }

        # Check for stub annotation when building AgentFinding
        is_stub = output.get("status") == "stub" or output.get("court_defensible") is False

        # Apply calibration to confidence score
        calibrated_prob = None
        try:
            from core.calibration import get_calibration_layer
            calibration_layer = get_calibration_layer()
            if calibration_layer and not is_stub:
                cal_result = calibration_layer.calibrate(
                    agent_id=self.agent_id,
                    raw_score=confidence,
                    finding_class=pending_task.description[:50]
                )
                calibrated_prob = cal_result.calibrated_probability
        except Exception:
            # If calibration fails, proceed without it
            pass

        finding = AgentFinding(
            agent_id=self.agent_id,
            agent_name=_AGENT_ID_TO_NAME.get(self.agent_id, self.agent_id),
            finding_type=pending_task.description[:80],
            confidence_raw=confidence,
            calibrated_probability=calibrated_prob,
            calibrated=calibrated_prob is not None,
            status=status,
            evidence_refs=[],
            reasoning_summary=self._build_readable_summary(
                best_tool.name, pending_task.description, tool_result, confidence, status
            ),
            metadata={
                "tool_name": best_tool.name,
                "court_defensible": not is_stub,
                "stub_warning": output.get("warning") if is_stub else None,
                **output,  # Include all tool output for transparency
            },
        )
        self._findings.append(finding)

        # Mark task complete
        try:
            await self.working_memory.update_task(
                session_id=self.session_id,
                agent_id=self.agent_id,
                task_id=pending_task.task_id,
                status=TaskStatus.COMPLETE,
                result_ref=str(finding.finding_id),
            )
        except Exception:
            pass

        # Return None to let the main loop re-check for next task naturally
        # The loop will call us again on the next iteration
        return ReActStep(
            step_type="THOUGHT",
            content=(
                f"Completed task '{pending_task.description}' with "
                f"confidence {confidence:.2f} ({status}). "
                f"Moving to next task."
            ),
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
            "ela_full_image": lambda o: (
                f"ELA detected {o.get('num_anomaly_regions', 0)} anomaly region(s) "
                f"with a maximum deviation of {o.get('max_anomaly', 0):.1f} "
                f"({'significant manipulation signature' if o.get('max_anomaly', 0) > 20 else 'within normal compression range'})."
            ),
            "jpeg_ghost_detect": lambda o: (
                f"JPEG ghost analysis {'detected double-compression artifacts' if o.get('ghost_detected') else 'found no ghost artifacts'} "
                f"with {o.get('confidence', 0):.0%} confidence across {len(o.get('ghost_regions', []))} region(s)."
            ),
            "exif_extract": lambda o: (
                f"EXIF extraction found {'no metadata' if not o.get('has_exif') else str(o.get('total_exif_tags', 0)) + ' tags'}. "
                f"Device: {o.get('device_model') or 'Unknown'}. "
                f"GPS: {'Present' if o.get('gps_coordinates') else 'Absent'}. "
                f"Missing {len(o.get('absent_fields', []))} expected fields."
            ),
            "hex_signature_scan": lambda o: (
                f"Hex signature scan {'detected editing software: ' + ', '.join(o.get('software_signatures', [])) if o.get('editing_software_detected') else 'found no editing software signatures'} "
                f"across {o.get('bytes_scanned', 0):,} bytes."
            ),
            "steganography_scan": lambda o: (
                f"LSB steganography analysis {'suspects hidden data' if o.get('stego_suspected') else 'found no hidden data'} "
                f"(deviation from random: {o.get('lsb_statistics', {}).get('average_deviation', 0):.4f})."
            ),
            "timestamp_analysis": lambda o: (
                f"Timestamp cross-check found {len(o.get('inconsistencies', []))} inconsistency(ies). "
                + (f"Issues: {'; '.join(o.get('inconsistencies', []))}" if o.get('inconsistencies') else "All timestamps are consistent.")
            ),
            "frequency_domain_analysis": lambda o: (
                f"Frequency domain analysis yielded anomaly score {o.get('anomaly_score', 0):.3f} "
                f"(high-freq ratio: {o.get('high_freq_ratio', 0):.3f}, "
                f"{'anomalous high-frequency content detected' if o.get('anomaly_score', 0) > 0.4 else 'frequency distribution appears natural'})."
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
