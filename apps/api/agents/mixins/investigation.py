"""
Investigation Mixin for Forensic Agents.
Handles ReAct loops, deep analysis pass, and arbiter challenges.
"""

from __future__ import annotations

import asyncio
import uuid
from typing import Any

from core.llm_client import LLMClient
from core.react_loop import AgentFinding, ReActLoopEngine, create_llm_step_generator
from core.structured_logging import get_logger
from core.synthesis import SynthesisService
from core.tracing import PipelineTrace

logger = get_logger(__name__)


class AgentInvestigationMixin:
    """
    Mixin handling the ReAct investigation loop and various pass types.
    """

    agent_id: str
    session_id: uuid.UUID
    config: Any
    working_memory: Any
    custody_logger: Any
    inter_agent_bus: Any
    evidence_artifact: Any
    iteration_ceiling: int
    agent_name: str
    task_decomposition: list[str]
    deep_task_decomposition: list[str]

    # Required methods from other mixins/base
    async def build_tool_registry(self) -> Any: ...
    async def build_initial_thought(self) -> str: ...
    def supports_uploaded_file(self) -> bool: ...
    def _signal_completion(self, skipped: bool = False) -> None: ...
    async def _initialize_working_memory(self) -> None: ...
    async def _check_tool_availability(self) -> None: ...
    async def _retrieve_episodic_context(self) -> str: ...
    async def self_reflection_pass(self, findings: list[AgentFinding]) -> Any: ...

    async def _synthesize_findings_once(
        self,
        findings: list[AgentFinding],
        phase: str,
        timeout_s: float = 15.0,
    ) -> dict[str, Any] | None:
        """Run one bounded post-analysis synthesis call for card/report narration."""
        if not (self.config.llm_enable_post_synthesis and self.config.llm_api_key):
            return None
        try:
            synthesis_service = SynthesisService(self.config)
            synthesis_result = await asyncio.wait_for(
                synthesis_service.synthesize_findings(
                    agent_id=self.agent_id,
                    agent_name=self.agent_name,
                    findings=findings,
                    evidence_artifact=self.evidence_artifact,
                    tool_success_count=self._tool_success_count,
                    tool_error_count=self._tool_error_count,
                    phase=phase,
                ),
                timeout=timeout_s,
            )
            if synthesis_result:
                self._agent_confidence = synthesis_result.get("agent_confidence")
                self._agent_error_rate = synthesis_result.get("agent_error_rate")
                self._agent_synthesis = synthesis_result
                return synthesis_result
        except Exception as e:
            logger.warning(f"{phase.title()} synthesis failed: {e}")
        return None

    async def run_investigation(self) -> list[AgentFinding]:
        """Run the full investigation workflow."""
        agent_trace = PipelineTrace(
            session_id=self.session_id,
            agent_id=self.agent_id,
            operation="initial_investigation",
            metadata={"agent_name": self.agent_name},
        )
        await agent_trace.start()

        if not self.supports_uploaded_file:
            finding = AgentFinding(
                agent_id=self.agent_id,
                finding_type="File type not applicable",
                status="NOT_APPLICABLE",
                confidence_raw=None,
                evidence_verdict="NOT_APPLICABLE",
                reasoning_summary="Unsupported file format.",
            )
            self._signal_completion(skipped=True)
            self._findings = [finding]
            return self._findings

        if not getattr(self, "_skip_memory_init", False):
            await self._initialize_working_memory()

        self._tool_registry = await self.build_tool_registry()
        await self._check_tool_availability()
        self._episodic_context = await self._retrieve_episodic_context()
        initial_thought = await self.build_initial_thought()
        if self._episodic_context:
            initial_thought = f"{initial_thought}\n\n{self._episodic_context}"

        loop_engine = ReActLoopEngine(
            agent_id=self.agent_id,
            session_id=self.session_id,
            iteration_ceiling=self.iteration_ceiling,
            working_memory=self.working_memory,
            custody_logger=self.custody_logger,
        )

        llm_generator = None
        if self.config.llm_enable_react_reasoning and self.config.llm_api_key:
            llm_client = LLMClient(self.config)
            if llm_client.is_available:
                llm_generator = create_llm_step_generator(
                    llm_client=llm_client,
                    config=self.config,
                    agent_name=self.agent_name,
                    evidence_context={"mime_type": getattr(self.evidence_artifact, "mime_type", "")},
                )

        loop_result = await loop_engine.run(
            initial_thought=initial_thought,
            tool_registry=self._tool_registry,
            llm_generator=llm_generator,
        )

        self._findings = loop_result.findings
        self._react_chain = loop_result.react_chain
        self._loop_result = loop_result

        await self._synthesize_findings_once(self._findings, phase="initial", timeout_s=15.0)

        if self._agent_confidence is None:
            self._agent_confidence = 0.0
        if self._agent_error_rate is None:
            self._agent_error_rate = 1.0

        self._reflection_report = await self.self_reflection_pass(self._findings)
        self._signal_completion(skipped=False)
        await agent_trace.complete({"finding_count": len(self._findings)})
        return self._findings

    async def run_deep_investigation(self) -> list[AgentFinding]:
        """Run the deep/heavy investigation pass in background."""
        deep_tasks = self.deep_task_decomposition
        if not deep_tasks:
            for f in self._findings:
                f.metadata["analysis_phase"] = "initial"
            return self._findings

        deep_trace = PipelineTrace(
            session_id=self.session_id,
            agent_id=self.agent_id,
            operation="deep_investigation",
            metadata={"agent_name": self.agent_name},
        )
        await deep_trace.start()

        for f in self._findings:
            f.metadata["analysis_phase"] = "initial"
        if self._tool_registry is None:
            self._tool_registry = await self.build_tool_registry()

        deep_agent_id = f"{self.agent_id}_deep"
        self._deep_wm_namespace = deep_agent_id
        await self.working_memory.initialize(
            self.session_id, deep_agent_id, deep_tasks, len(deep_tasks) + 3
        )

        loop_engine = ReActLoopEngine(
            agent_id=deep_agent_id,
            session_id=self.session_id,
            iteration_ceiling=len(deep_tasks) + 3,
            working_memory=self.working_memory,
            custody_logger=self.custody_logger,
        )

        loop_result = await loop_engine.run(
            initial_thought=f"DEEP ANALYSIS PASS — {self.agent_name}. Running {len(deep_tasks)} tools.",
            tool_registry=self._tool_registry,
            llm_generator=None,
        )

        deep_findings = loop_result.findings
        for f in deep_findings:
            f.agent_id = self.agent_id
            f.metadata["analysis_phase"] = "deep"

        self._findings = self._findings + deep_findings
        await self._synthesize_findings_once(self._findings, phase="deep", timeout_s=20.0)
        self._reflection_report = await self.self_reflection_pass(self._findings)
        await deep_trace.complete({"deep_finding_count": len(deep_findings)})
        return deep_findings

    async def run_challenge(
        self,
        contradicting_finding: dict[str, Any],
        context: dict[str, Any]
    ) -> list[AgentFinding]:
        """Re-invokes the agent's ReAct loop to resolve a contradiction."""
        logger.info(f"Agent {self.agent_id} challenged by Arbiter")

        from core.custody_logger import EntryType
        if self.custody_logger:
            await self.custody_logger.log_entry(
                agent_id=self.agent_id,
                session_id=self.session_id,
                entry_type=EntryType.TRIBUNAL_EVENT,
                content={
                    "action": "run_challenge",
                    "contradicting_agent": contradicting_finding.get("agent_id"),
                    "contradiction_type": contradicting_finding.get("finding_type"),
                }
            )

        challenge_thought = (
            f"The Council Arbiter has flagged a contradiction between my findings "
            f"and Agent {contradicting_finding.get('agent_id')}. "
            f"I must re-examine the evidence and either confirm or revise my verdict."
        )

        loop_engine = ReActLoopEngine(
            agent_id=self.agent_id,
            session_id=self.session_id,
            iteration_ceiling=max(3, self.iteration_ceiling // 2),
            working_memory=self.working_memory,
            custody_logger=self.custody_logger,
        )

        llm_generator = None
        if self.config.llm_enable_react_reasoning and self.config.llm_api_key:
            llm_client = LLMClient(self.config)
            llm_generator = create_llm_step_generator(
                llm_client=llm_client,
                config=self.config,
                agent_name=self.agent_name,
                evidence_context={"challenge_mode": True, "contradiction": contradicting_finding}
            )

        if self._tool_registry is None:
            self._tool_registry = await self.build_tool_registry()

        loop_result = await loop_engine.run(
            initial_thought=challenge_thought,
            tool_registry=self._tool_registry,
            llm_generator=llm_generator
        )

        self._findings = loop_result.findings
        return self._findings

    async def flag_hitl(self, reason: Any, brief: str) -> None:
        """Flag a Human-in-the-Loop checkpoint."""
        logger.warning(f"HITL checkpoint flagged: {reason.value} - {brief}")
        if self.custody_logger:
            from core.custody_logger import EntryType
            await self.custody_logger.log_entry(
                agent_id=self.agent_id,
                session_id=self.session_id,
                entry_type=EntryType.HITL_CHECKPOINT,
                content={"action": "flag_hitl", "reason": reason.value, "brief": brief},
            )

    async def handle_inter_agent_call(self, call: Any) -> dict[str, Any]:
        """Handle an incoming inter-agent call."""
        logger.info(f"Handling inter-agent call from {call.caller_agent_id}")
        if self.custody_logger:
            from core.custody_logger import EntryType
            await self.custody_logger.log_entry(
                agent_id=self.agent_id,
                session_id=self.session_id,
                entry_type=EntryType.INTER_AGENT_CALL,
                content={
                    "action": "handle_inter_agent_call",
                    "caller_agent_id": call.caller_agent_id,
                    "payload": call.payload,
                },
            )
        return {"status": "acknowledged", "agent_id": self.agent_id}
