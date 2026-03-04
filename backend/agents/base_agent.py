"""
ForensicAgent Base Class and Self-Reflection System.

Every specialist agent (1-5) extends this base class.
Provides common investigation workflow, self-reflection, and memory integration.
"""

from __future__ import annotations

import uuid
from abc import ABC, abstractmethod
from typing import Any

from pydantic import BaseModel, Field

from core.config import Settings
from core.custody_logger import CustodyLogger, EntryType
from core.episodic_memory import EpisodicMemory, EpisodicEntry, ForensicSignatureType
from core.evidence import EvidenceArtifact
from core.inter_agent_bus import InterAgentCall, InterAgentCallType
from core.llm_client import LLMClient
from core.logging import get_logger
from core.react_loop import (
    AgentFinding,
    HITLCheckpointReason,
    HumanDecision,
    ReActLoopEngine,
    ReActLoopResult,
    create_llm_step_generator,
)
from core.tool_registry import ToolRegistry
from core.working_memory import WorkingMemory, WorkingMemoryState, Task, TaskStatus
from infra.evidence_store import EvidenceStore

logger = get_logger(__name__)


class SelfReflectionReport(BaseModel):
    """
    Report from self-reflection pass.
    
    Generated after each investigation to ensure quality and completeness.
    """
    all_tasks_complete: bool = Field(
        default=False,
        description="Whether all tasks in decomposition are complete"
    )
    incomplete_tasks: list[str] = Field(
        default_factory=list,
        description="List of incomplete task descriptions"
    )
    overconfident_findings: list[str] = Field(
        default_factory=list,
        description="Findings that may have inflated confidence"
    )
    untreated_absences: list[str] = Field(
        default_factory=list,
        description="Absence of expected data that wasn't analyzed"
    )
    deprioritized_avenues: list[str] = Field(
        default_factory=list,
        description="Investigation avenues that were deprioritized"
    )
    court_defensible: bool = Field(
        default=False,
        description="Whether findings are defensible in court"
    )
    reflection_notes: str = Field(
        default="",
        description="Additional notes from reflection"
    )


class ForensicAgent(ABC):
    """
    Abstract base class for all forensic specialist agents.
    
    Provides:
    - Common investigation workflow via run_investigation()
    - Self-reflection system for quality assurance
    - Integration with working memory, episodic memory, and chain of custody
    - Tool registry management
    
    Subclasses must implement:
    - agent_name property
    - task_decomposition property
    - iteration_ceiling property
    - build_tool_registry() method
    - build_initial_thought() method
    """
    
    def __init__(
        self,
        agent_id: str,
        session_id: uuid.UUID,
        evidence_artifact: EvidenceArtifact,
        config: Settings,
        working_memory: WorkingMemory,
        episodic_memory: EpisodicMemory,
        custody_logger: CustodyLogger,
        evidence_store: EvidenceStore,
    ) -> None:
        """
        Initialize a forensic agent.
        
        Args:
            agent_id: Unique identifier for this agent instance
            session_id: Session ID for this investigation
            evidence_artifact: The primary evidence artifact to analyze
            config: Application configuration
            working_memory: Working memory for task tracking
            episodic_memory: Episodic memory for forensic signatures
            custody_logger: Chain of custody logger
            evidence_store: Evidence store for artifact management
        """
        self.agent_id = agent_id
        self.session_id = session_id
        self.evidence_artifact = evidence_artifact
        self.config = config
        self.working_memory = working_memory
        self.episodic_memory = episodic_memory
        self.custody_logger = custody_logger
        self.evidence_store = evidence_store
        
        # Will be set during investigation
        self._tool_registry: ToolRegistry | None = None
        self._findings: list[AgentFinding] = []
        self._reflection_report: SelfReflectionReport | None = None
    
    # Abstract properties that must be overridden
    
    @property
    @abstractmethod
    def agent_name(self) -> str:
        """Human-readable name of this agent."""
        pass
    
    @property
    @abstractmethod
    def task_decomposition(self) -> list[str]:
        """
        List of tasks this agent performs.
        Hardcoded per agent based on architecture document.
        """
        pass
    
    @property
    @abstractmethod
    def iteration_ceiling(self) -> int:
        """Maximum iterations for the ReAct loop."""
        pass
    
    # Abstract methods that must be overridden
    
    @abstractmethod
    async def build_tool_registry(self) -> ToolRegistry:
        """
        Build and return the tool registry for this agent.
        
        Returns:
            ToolRegistry with all tools this agent can use
        """
        pass
    
    @abstractmethod
    async def build_initial_thought(self) -> str:
        """
        Build the initial thought for the ReAct loop.
        
        Returns:
            String containing the opening thought for investigation
        """
        pass
    
    # Concrete methods shared by all agents
    
    async def run_investigation(self) -> list[AgentFinding]:
        """
        Run the full investigation workflow.
        
        Steps:
        1. Initialize working memory with task_decomposition
        2. Log session start to CustodyLogger
        3. Build tool registry
        4. Check tool availability
        5. Build initial thought
        6. Run ReActLoopEngine
        7. Run self_reflection_pass()
        8. Return findings
        
        Returns:
            List of AgentFinding objects from the investigation
        """
        logger.info(
            "Starting investigation",
            agent_id=self.agent_id,
            agent_name=self.agent_name,
            session_id=str(self.session_id),
            artifact_id=str(self.evidence_artifact.artifact_id),
        )
        
        # Step 1: Initialize working memory with task decomposition
        await self._initialize_working_memory()
        
        # Step 2: Log session start
        if self.custody_logger:
            await self.custody_logger.log_entry(
                agent_id=self.agent_id,
                session_id=self.session_id,
                entry_type=EntryType.THOUGHT,  # Using THOUGHT as session marker
                content={
                    "action": "session_start",
                    "agent_name": self.agent_name,
                    "evidence_artifact_id": str(self.evidence_artifact.artifact_id),
                    "task_count": len(self.task_decomposition),
                }
            )
        
        # Step 3: Build tool registry
        self._tool_registry = await self.build_tool_registry()
        
        # Step 4: Check tool availability
        await self._check_tool_availability()
        
        # Step 5: Build initial thought
        initial_thought = await self.build_initial_thought()
        
        # Step 6: Run ReAct loop engine
        loop_engine = ReActLoopEngine(
            agent_id=self.agent_id,
            session_id=self.session_id,
            iteration_ceiling=self.iteration_ceiling,
            working_memory=self.working_memory,
            custody_logger=self.custody_logger,
            redis_client=None,  # HITL handled externally in production
        )
        
        # Create LLM step generator if enabled
        llm_generator = None
        if self.config.llm_enable_react_reasoning and self.config.llm_api_key:
            llm_client = LLMClient(self.config)
            evidence_context = {
                "mime_type": getattr(self.evidence_artifact, 'mime_type', 'unknown'),
                "file_name": getattr(self.evidence_artifact, 'file_path', 'unknown'),
            }
            llm_generator = create_llm_step_generator(
                llm_client=llm_client,
                config=self.config,
                agent_name=self.agent_name,
                evidence_context=evidence_context,
            )
            logger.info(
                "LLM reasoning enabled for ReAct loop",
                agent_id=self.agent_id,
                llm_provider=self.config.llm_provider,
                llm_model=self.config.llm_model,
            )
        
        loop_result = await loop_engine.run(
            initial_thought=initial_thought,
            tool_registry=self._tool_registry,
            llm_generator=llm_generator  # Use LLM if configured, else task-decomposition driver
        )
        
        self._findings = loop_result.findings
        self._react_chain = loop_result.react_chain
        self._loop_result = loop_result
        
        # Step 7: Run self-reflection pass
        self._reflection_report = await self.self_reflection_pass(self._findings)
        
        # Step 8: Return findings
        logger.info(
            "Investigation complete",
            agent_id=self.agent_id,
            session_id=str(self.session_id),
            finding_count=len(self._findings),
            all_tasks_complete=self._reflection_report.all_tasks_complete,
        )
        
        return self._findings
    
    async def _initialize_working_memory(self) -> None:
        """Initialize working memory with task decomposition."""
        await self.working_memory.initialize(
            session_id=self.session_id,
            agent_id=self.agent_id,
            tasks=self.task_decomposition,
            iteration_ceiling=self.iteration_ceiling,
        )
        
        logger.debug(
            "Working memory initialized",
            agent_id=self.agent_id,
            task_count=len(self.task_decomposition),
        )
    
    async def _check_tool_availability(self) -> None:
        """Check and log tool availability."""
        if self._tool_registry is None:
            return
        
        tools = self._tool_registry.list_tools()
        unavailable_tools = [t for t in tools if not t.available]
        
        if unavailable_tools and self.custody_logger:
            await self.custody_logger.log_entry(
                agent_id=self.agent_id,
                session_id=self.session_id,
                entry_type=EntryType.TOOL_CALL,
                content={
                    "action": "tool_availability_check",
                    "unavailable_tools": [t.name for t in unavailable_tools],
                    "total_tools": len(tools),
                    "available_tools": len(tools) - len(unavailable_tools),
                }
            )
            
            logger.warning(
                "Some tools unavailable",
                agent_id=self.agent_id,
                unavailable=[t.name for t in unavailable_tools],
            )
    
    async def self_reflection_pass(
        self,
        findings: list[AgentFinding]
    ) -> SelfReflectionReport:
        """
        Perform self-reflection on investigation findings.
        
        Uses 5 structured reflection prompts:
        - RT1: All tasks complete?
        - RT2: Overconfident findings?
        - RT3: Absences treated as signals?
        - RT4: Deprioritized avenues?
        - RT5: Confidence court-defensible?
        
        Args:
            findings: List of findings from the investigation
            
        Returns:
            SelfReflectionReport with reflection results
        """
        logger.info(
            "Running self-reflection pass",
            agent_id=self.agent_id,
            session_id=str(self.session_id),
        )
        
        # Get current working memory state
        state = await self.working_memory.get_state(
            session_id=self.session_id,
            agent_id=self.agent_id
        )
        
        # Get evidence artifact for context
        evidence_context = await self._get_evidence_context_for_reflection()
        
        # RT1: Check if all tasks are complete
        incomplete_tasks = []
        all_tasks_complete = True
        
        if state:
            for task in state.tasks:
                if task.status != TaskStatus.COMPLETE:
                    all_tasks_complete = False
                    incomplete_tasks.append(task.description)
        
        # RT2: Check for overconfident findings
        overconfident_findings = []
        for finding in findings:
            if finding.confidence_raw > 0.95 and not finding.calibrated:
                overconfident_findings.append(
                    f"{finding.finding_type}: {finding.confidence_raw:.2f}"
                )
        
        # RT3: Check for untreated absences (absence as signal)
        # Absence of expected data can itself be evidence
        untreated_absences = await self._check_untreated_absences(
            findings=findings,
            state=state,
            evidence_context=evidence_context,
        )
        
        # RT4: Check for deprioritized avenues
        # Investigation paths that were skipped or deprioritized
        deprioritized_avenues = await self._check_deprioritized_avenues(
            findings=findings,
            state=state,
            evidence_context=evidence_context,
        )
        
        # RT5: Check if confidence is court-defensible
        court_defensible = (
            all_tasks_complete and
            len(overconfident_findings) == 0 and
            len(findings) > 0
        )
        
        # Build reflection notes
        reflection_notes = []
        if incomplete_tasks:
            reflection_notes.append(f"Incomplete tasks: {len(incomplete_tasks)}")
        if overconfident_findings:
            reflection_notes.append(f"Overconfident findings: {len(overconfident_findings)}")
        if court_defensible:
            reflection_notes.append("Findings are court-defensible")
        else:
            reflection_notes.append("Findings may need additional review")
        
        report = SelfReflectionReport(
            all_tasks_complete=all_tasks_complete,
            incomplete_tasks=incomplete_tasks,
            overconfident_findings=overconfident_findings,
            untreated_absences=untreated_absences,
            deprioritized_avenues=deprioritized_avenues,
            court_defensible=court_defensible,
            reflection_notes="; ".join(reflection_notes),
        )
        
        # Log self-reflection
        if self.custody_logger:
            await self.custody_logger.log_entry(
                agent_id=self.agent_id,
                session_id=self.session_id,
                entry_type=EntryType.SELF_REFLECTION,
                content={
                    "all_tasks_complete": all_tasks_complete,
                    "incomplete_task_count": len(incomplete_tasks),
                    "overconfident_finding_count": len(overconfident_findings),
                    "court_defensible": court_defensible,
                    "reflection_notes": report.reflection_notes,
                }
            )
        
        logger.info(
            "Self-reflection complete",
            agent_id=self.agent_id,
            all_tasks_complete=all_tasks_complete,
            court_defensible=court_defensible,
            untreated_absence_count=len(untreated_absences),
            deprioritized_avenue_count=len(deprioritized_avenues),
        )
        
        return report
    
    async def _get_evidence_context_for_reflection(self) -> dict[str, Any]:
        """Get evidence context for reflection analysis."""
        context = {
            "mime_type": getattr(self.evidence_artifact, 'mime_type', 'unknown'),
            "file_extension": '',
            "has_exif": False,
            "has_audio": False,
            "has_video": False,
            "has_gps": False,
        }
        
        # Get file extension
        file_path = getattr(self.evidence_artifact, 'file_path', '')
        if file_path and '.' in file_path:
            context["file_extension"] = file_path.lower().split('.')[-1]
        
        # Check for common metadata indicators
        metadata = getattr(self.evidence_artifact, 'metadata', {}) or {}
        if isinstance(metadata, dict):
            context["has_exif"] = bool(metadata.get('exif'))
            context["has_gps"] = bool(metadata.get('gps_latitude'))
        
        # Determine media type
        mime = context["mime_type"].lower()
        context["has_audio"] = any(x in mime for x in ['audio', 'wav', 'mp3', 'ogg'])
        context["has_video"] = any(x in mime for x in ['video', 'mp4', 'avi', 'mov'])
        
        return context
    
    async def _check_untreated_absences(
        self,
        findings: list[AgentFinding],
        state: WorkingMemoryState | None,
        evidence_context: dict[str, Any],
    ) -> list[str]:
        """
        RT3: Check for untreated absences - missing expected data that could be signals.
        
        Absence of expected forensic artifacts can itself be evidence of manipulation.
        For example: missing EXIF in a camera-original, missing noise in a photo,
        or missing codec metadata in a video.
        """
        absences = []
        
        # Get finding types we have
        finding_types = {f.finding_type.lower() for f in findings}
        
        # Check for expected EXIF in image files
        mime = evidence_context.get("mime_type", "").lower()
        ext = evidence_context.get("file_extension", "").lower()
        
        is_image = any(x in mime for x in ['image', 'jpeg', 'jpg', 'png', 'tiff'])
        is_image = is_image or ext in ['jpg', 'jpeg', 'png', 'tiff', 'bmp', 'gif']
        
        if is_image:
            # Camera-original images should have EXIF
            has_exif_analysis = any("exif" in ft for ft in finding_types)
            has_metadata = evidence_context.get("has_exif", False)
            
            if has_exif_analysis and not has_metadata:
                absences.append(
                    "MISSING_EXIF_DATA: Image file lacks EXIF metadata, "
                    "which is unusual for camera-original files. May indicate "
                    "re-saving or metadata stripping."
                )
            
            # Check for missing noise fingerprint analysis result
            has_noise_analysis = any("noise" in ft or "fingerprint" in ft for ft in finding_types)
            if not has_noise_analysis:
                absences.append(
                    "MISSING_PRNU_ANALYSIS: No camera sensor noise fingerprint analysis "
                    "performed. This is a key technique for detecting region insertion."
                )
        
        # Check for expected audio/video metadata
        is_video = evidence_context.get("has_video", False)
        is_audio = evidence_context.get("has_audio", False)
        
        if is_video or is_audio:
            # Should have codec information
            has_codec_analysis = any("codec" in ft for ft in finding_types)
            if not has_codec_analysis:
                absences.append(
                    "MISSING_CODEC_FINGERPRINT: No codec fingerprinting analysis. "
                    "Codec metadata changes can indicate re-encoding or editing."
                )
        
        # Check for GPS-related absences
        if evidence_context.get("has_gps"):
            # If GPS exists, should validate it
            has_gps_validation = any("gps" in ft or "timezone" in ft for ft in finding_types)
            if not has_gps_validation:
                absences.append(
                    "UNTREATED_GPS_DATA: GPS coordinates present but not validated "
                    "against timezone or astronomical data."
                )
        
        # Check for missing hash verification
        has_hash_verify = any("hash" in ft for ft in finding_types)
        if not has_hash_verify:
            absences.append(
                "MISSING_HASH_VERIFICATION: No cryptographic hash verification performed. "
                "Cannot establish chain-of-custody baseline."
            )
        
        return absences
    
    async def _check_deprioritized_avenues(
        self,
        findings: list[AgentFinding],
        state: WorkingMemoryState | None,
        evidence_context: dict[str, Any],
    ) -> list[str]:
        """
        RT4: Check for deprioritized investigation avenues.
        
        Tracks which lines of inquiry were identified but not pursued,
        either due to time constraints, resource limitations, or tool unavailability.
        """
        deprioritized = []
        
        if not state:
            return deprioritized
        
        # Check tasks that were never started or abandoned
        for task in state.tasks:
            if task.status == TaskStatus.PENDING:
                # Task was never started - could be deprioritized
                deprioritized.append(
                    f"PENDING_TASK: '{task.description}' was never started. "
                    f"This may indicate the investigation was cut short."
                )
            elif task.status == TaskStatus.IN_PROGRESS:
                # Task started but not completed
                deprioritized.append(
                    f"INCOMPLETE_TASK: '{task.description}' was started but not completed. "
                    f"Results may be partial or inconclusive."
                )
        
        # Get finding types
        finding_types = {f.finding_type.lower() for f in findings}
        mime = evidence_context.get("mime_type", "").lower()
        
        # Check for high-value but unperformed analyses based on media type
        is_image = any(x in mime for x in ['image', 'jpeg', 'jpg', 'png'])
        is_video = evidence_context.get("has_video", False)
        is_audio = evidence_context.get("has_audio", False)
        
        if is_image:
            # ELA is foundational for image forensics
            has_ela = any("ela" in ft for ft in finding_types)
            if not has_ela:
                deprioritized.append(
                    "UNPERFORMED_ELA: Error Level Analysis not performed. "
                    "This is a fundamental technique for detecting re-compression artifacts."
                )
            
            # Copy-move detection
            has_copymove = any("copy" in ft or "move" in ft or "clone" in ft for ft in finding_types)
            if not has_copymove:
                deprioritized.append(
                    "UNPERFORMED_COPY_MOVE: Copy-move detection not performed. "
                    "Cloned regions are a common manipulation technique."
                )
        
        if is_video:
            # Frame consistency is crucial for video
            has_frame_check = any("frame" in ft for ft in finding_types)
            if not has_frame_check:
                deprioritized.append(
                    "UNPERFORMED_FRAME_ANALYSIS: No frame-to-frame consistency analysis. "
                    "Frame-level discontinuities can indicate splicing."
                )
            
            # Deepfake detection
            has_deepfake = any("deepfake" in ft or "face" in ft for ft in finding_types)
            if not has_deepfake:
                deprioritized.append(
                    "UNPERFORMED_DEEPFAKE_CHECK: Deepfake detection not performed. "
                    "Face-swap GAN artifacts have characteristic spectral signatures."
                )
        
        if is_audio:
            # Prosody analysis
            has_prosody = any("prosody" in ft or "pitch" in ft or "rhythm" in ft for ft in finding_types)
            if not has_prosody:
                deprioritized.append(
                    "UNPERFORMED_PROSODY_ANALYSIS: Prosody analysis not performed. "
                    "Synthetic voices often show unnatural pitch patterns."
                )
        
        # Check for adversarial/robustness testing (applies to all types)
        has_robustness = any("adversarial" in ft or "robustness" in ft for ft in finding_types)
        if not has_robustness:
            deprioritized.append(
                "UNPERFORMED_ROBUSTNESS_CHECK: No adversarial robustness testing. "
                "Findings may not hold up against anti-forensic countermeasures."
            )
        
        return deprioritized
    
    async def query_episodic_memory(
        self,
        signature_type: ForensicSignatureType,
        query_embedding: list[float],
        limit: int = 10
    ) -> list[EpisodicEntry]:
        """
        Query episodic memory for similar forensic signatures.
        
        Args:
            signature_type: Type of forensic signature to query
            query_embedding: Vector embedding for similarity search
            limit: Maximum number of results
            
        Returns:
            List of matching EpisodicEntry objects
        """
        if self.custody_logger:
            await self.custody_logger.log_entry(
                agent_id=self.agent_id,
                session_id=self.session_id,
                entry_type=EntryType.MEMORY_READ,
                content={
                    "action": "query_episodic_memory",
                    "signature_type": signature_type.value,
                    "limit": limit,
                }
            )
        
        results = await self.episodic_memory.query(
            signature_type=signature_type,
            query_embedding=query_embedding,
            limit=limit
        )
        
        return results
    
    async def store_episodic_finding(
        self,
        entry: EpisodicEntry,
        embedding: list[float]
    ) -> None:
        """
        Store a finding in episodic memory.
        
        Args:
            entry: The episodic entry to store
            embedding: Vector embedding for the entry
        """
        if self.custody_logger:
            await self.custody_logger.log_entry(
                agent_id=self.agent_id,
                session_id=self.session_id,
                entry_type=EntryType.MEMORY_WRITE,
                content={
                    "action": "store_episodic_finding",
                    "signature_type": entry.signature_type.value,
                    "session_id": str(entry.session_id),
                }
            )
        
        await self.episodic_memory.store(entry, embedding)
    
    async def flag_hitl(
        self,
        reason: HITLCheckpointReason,
        brief: str
    ) -> None:
        """
        Flag a Human-in-the-Loop checkpoint.
        
        Args:
            reason: Why the checkpoint is needed
            brief: Brief description for the investigator
        """
        logger.warning(
            "HITL checkpoint flagged",
            agent_id=self.agent_id,
            reason=reason.value,
            brief=brief,
        )
        
        # In production, this would trigger the actual HITL flow
        # For now, we just log it
        if self.custody_logger:
            await self.custody_logger.log_entry(
                agent_id=self.agent_id,
                session_id=self.session_id,
                entry_type=EntryType.HITL_CHECKPOINT,
                content={
                    "action": "flag_hitl",
                    "reason": reason.value,
                    "brief": brief,
                }
        )
    
    async def handle_inter_agent_call(
        self,
        call: "InterAgentCall"
    ) -> dict[str, Any]:
        """
        Handle an incoming inter-agent call.
        
        Default implementation: runs targeted sub-analysis based on call payload.
        Subclasses can override for specialized handling.
        
        Args:
            call: The inter-agent call request
            
        Returns:
            Dictionary containing findings from the sub-analysis
        """
        logger.info(
            "Handling inter-agent call",
            agent_id=self.agent_id,
            caller=call.caller_agent_id,
            call_type=call.call_type.value,
            call_id=str(call.call_id),
        )
        
        # Log the incoming call
        if self.custody_logger:
            await self.custody_logger.log_entry(
                agent_id=self.agent_id,
                session_id=self.session_id,
                entry_type=EntryType.INTER_AGENT_CALL,
                content={
                    "action": "handle_inter_agent_call",
                    "call_id": str(call.call_id),
                    "caller_agent_id": call.caller_agent_id,
                    "call_type": call.call_type.value,
                    "payload": call.payload,
                }
            )
        
        # Default implementation: return a summary based on payload
        # Subclasses should override this for specialized handling
        response = {
            "status": "acknowledged",
            "agent_id": self.agent_id,
            "agent_name": self.agent_name,
            "findings": [],
            "message": f"{self.agent_name} received call from {call.caller_agent_id}",
        }
        
        # If payload contains specific analysis requests, handle them
        if call.payload:
            timestamp_ref = call.payload.get("timestamp_ref")
            region_ref = call.payload.get("region_ref")
            context_finding = call.payload.get("context_finding")
            question = call.payload.get("question")
            
            if question:
                response["question_received"] = question
            
            if context_finding:
                response["context_received"] = context_finding
            
            # Subclasses should override to perform actual analysis
            response["analysis_performed"] = False
            response["note"] = "Subclass should override handle_inter_agent_call for actual analysis"
        
        return response
