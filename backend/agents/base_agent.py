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
from core.logging import get_logger
from core.react_loop import (
    AgentFinding,
    HITLCheckpointReason,
    HumanDecision,
    ReActLoopEngine,
    ReActLoopResult,
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
        
        loop_result = await loop_engine.run(
            initial_thought=initial_thought,
            tool_registry=self._tool_registry,
            llm_generator=None  # Use built-in task-decomposition driver
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
        
        # RT3: Check for untreated absences (placeholder logic)
        untreated_absences = []
        # In a real implementation, this would check for missing expected data
        
        # RT4: Check for deprioritized avenues (placeholder logic)
        deprioritized_avenues = []
        # In a real implementation, this would check investigation logs
        
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
        )
        
        return report
    
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
