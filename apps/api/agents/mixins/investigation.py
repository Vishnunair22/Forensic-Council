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
    heavy_tool_semaphore: asyncio.Semaphore | None
    task_decomposition: list[str]
    deep_task_decomposition: list[str]

    # Required methods from other mixins/base
    async def build_tool_registry(self) -> Any: ...
    async def build_initial_thought(self) -> str: ...
    def supports_uploaded_file(self) -> bool: ...
    def _signal_completion(self, skipped: bool = False) -> None: ...
    async def _initialize_working_memory(self) -> None: ...

    async def inject_task(self, description: str, priority: int = 10) -> None:
        """
        Dynamically inject a new task into the investigation pipeline.
        Used for reactive task decomposition based on intermediate findings.
        """
        try:
            from core.working_memory import TaskStatus

            await self.working_memory.create_task(
                session_id=self.session_id,
                agent_id=self.agent_id,
                description=description,
                status=TaskStatus.PENDING,
                priority=priority,
            )
            logger.info("Dynamic task injected", agent_id=self.agent_id, task=description)
        except Exception as e:
            logger.error("Failed to inject dynamic task", agent_id=self.agent_id, error=str(e))

    async def _check_tool_availability(self) -> None:
        """Log unavailable tools to custody; does not raise — agents degrade gracefully."""
        if getattr(self, "_tool_registry", None) is None:
            return
        unavailable = [t.name for t in self._tool_registry.list_tools() if not t.available]
        if unavailable:
            logger.warning(
                "Tools unavailable at investigation start",
                agent_id=self.agent_id,
                unavailable_tools=unavailable,
            )
            if self.custody_logger:
                from core.custody_logger import EntryType

                await self.custody_logger.log_entry(
                    agent_id=self.agent_id,
                    session_id=self.session_id,
                    entry_type=EntryType.TOOL_CALL,
                    content={
                        "action": "tool_availability_check",
                        "unavailable_tools": unavailable,
                        "note": "Degraded mode — these tools will produce INCOMPLETE findings",
                    },
                )

    async def _retrieve_episodic_context(self) -> str: ...
    async def self_reflection_pass(self, findings: list[AgentFinding]) -> Any: ...

    async def _publish_tool_registry_snapshot(self, agent_id: str | None = None) -> None:
        """Expose the live tool catalogue to working memory for LLM ReAct mode."""
        registry = getattr(self, "_tool_registry", None)
        if registry is None:
            return
        snapshot = [tool.model_dump() for tool in registry.list_tools()]
        try:
            await self.working_memory.update_state(
                session_id=self.session_id,
                agent_id=agent_id or self.agent_id,
                updates={"tool_registry_snapshot": snapshot},
            )
        except Exception as exc:
            logger.debug(
                "Failed to publish tool registry snapshot",
                agent_id=agent_id or self.agent_id,
                error=str(exc),
            )

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
                    tool_success_count=self._tool_success_count,  # type: ignore[attr-defined]
                    tool_error_count=self._tool_error_count,  # type: ignore[attr-defined]
                    phase=phase,
                ),
                timeout=timeout_s,
            )
            if synthesis_result:
                self._agent_confidence = synthesis_result.get("agent_confidence")
                self._agent_error_rate = synthesis_result.get("agent_error_rate")
                self._agent_synthesis = synthesis_result

                # Apply refined summaries and section metadata back to findings
                sections = synthesis_result.get("sections", [])
                for section in sections:
                    refined = section.get("refined_findings", [])
                    for item in refined:
                        tool_name = item.get("tool")
                        friendly_text = item.get("user_friendly_summary")
                        if tool_name and friendly_text:
                            for f in findings:
                                # Match by tool_name in metadata or finding_type
                                f_tool = f.metadata.get("tool_name") or f.finding_type
                                if f_tool == tool_name:
                                    f.metadata["llm_refined_summary"] = friendly_text
                                    f.metadata["section_id"] = section.get("id")
                                    f.metadata["section_label"] = section.get("label")
                                    # Map severity to frontend-friendly flags
                                    sev = section.get("severity", "LOW")
                                    f.metadata["section_flag"] = (
                                        "bad"
                                        if sev in ("HIGH", "CRITICAL")
                                        else ("warn" if sev == "MEDIUM" else "ok")
                                    )
                                    # Also store the section-level opinion for context
                                    f.metadata["llm_synthesis"] = section.get("opinion")

                return synthesis_result
        except Exception as e:
            logger.warning(f"{phase.title()} synthesis failed: {e}", exc_info=True)
        return None

    async def _publish_agent_context(
        self,
        phase: str,
        findings: list[AgentFinding],
    ) -> None:
        """Publish compact cross-agent context for sibling-agent grounding."""
        if not self.working_memory:
            return
        compact_tools = {}
        for tool_name, result in getattr(self, "_tool_context", {}).items():
            if not isinstance(result, dict):
                continue
            compact_tools[tool_name] = {
                key: value
                for key, value in result.items()
                if key
                in {
                    "verdict",
                    "status",
                    "confidence",
                    "manipulation_detected",
                    "splicing_detected",
                    "copy_move_detected",
                    "is_ai_generated",
                    "diffusion_detected",
                    "device_model",
                    "software",
                    "gps_info",
                    "image_type",
                    "all_classifications",
                    "detections",
                    "weapon_detections",
                    "classes_found",
                    "metadata_timeline_consistent",
                    "inconsistency_detected",
                    "anomaly_detected",
                    "summary",
                }
            }

        context = {
            "phase": phase,
            "agent_id": self.agent_id,
            "agent_name": self.agent_name,
            "initial_summary": getattr(self, "_agent_synthesis", None) or {},
            "tool_context": compact_tools,
            "finding_count": len(findings),
            "agent_confidence": getattr(self, "_agent_confidence", None),
            "agent_error_rate": getattr(self, "_agent_error_rate", None),
        }
        try:
            await self.working_memory.set_agent_context(
                self.session_id,
                self.agent_id,
                context,
            )
        except Exception as exc:
            logger.debug(
                "Failed to publish agent context",
                agent_id=self.agent_id,
                phase=phase,
                error=str(exc),
            )

    def _build_deterministic_synthesis(
        self,
        findings: list[AgentFinding],
        phase: str,
    ) -> dict[str, Any]:
        """Build metrics and evidence-grounded summaries when the LLM is unavailable."""
        actionable = [
            f
            for f in findings
            if f.status != "NOT_APPLICABLE" and f.evidence_verdict != "NOT_APPLICABLE"
        ]
        confidence_values = [
            float(f.confidence_raw)
            for f in actionable
            if f.confidence_raw is not None
            and f.status != "INCOMPLETE"
            and f.evidence_verdict != "ERROR"
        ]
        confidence = (
            round(sum(confidence_values) / len(confidence_values), 3) if confidence_values else 0.0
        )
        error_count = sum(
            1 for f in actionable if f.status == "INCOMPLETE" or f.evidence_verdict == "ERROR"
        )
        error_rate = round(error_count / len(actionable), 3) if actionable else 0.0
        positive_count = sum(1 for f in actionable if f.evidence_verdict == "POSITIVE")
        negative_count = sum(1 for f in actionable if f.evidence_verdict == "NEGATIVE")

        if positive_count >= 2:
            verdict = "TAMPERED"
        elif positive_count == 1 or error_rate > 0.25:
            verdict = "SUSPICIOUS"
        elif (
            error_rate == 0 and actionable and negative_count >= max(1, int(len(actionable) * 0.75))
        ):
            verdict = "AUTHENTIC"
            if confidence < 0.7:
                confidence = 0.7
        elif confidence >= 0.7 and error_rate == 0:
            verdict = "AUTHENTIC"
        else:
            verdict = "INCONCLUSIVE"

        def _tool_name(f: AgentFinding) -> str:
            return str(f.metadata.get("tool_name") or f.finding_type).replace("_", " ").title()

        def _severity(f: AgentFinding) -> str:
            verdict = str(f.evidence_verdict or "").upper()
            status = str(f.status or "").upper()
            if verdict in {"POSITIVE", "TAMPERED", "SUSPICIOUS", "MANIPULATED"}:
                conf = float(f.confidence_raw or 0.0)
                return "HIGH" if conf >= 0.7 else "MEDIUM"
            if verdict == "ERROR" or status == "INCOMPLETE":
                return "MEDIUM"
            return "LOW"

        sorted_findings = sorted(
            actionable,
            key=lambda f: (
                1 if str(f.evidence_verdict).upper() == "POSITIVE" else 0,
                float(f.confidence_raw or 0.0),
            ),
            reverse=True,
        )
        top_findings = sorted_findings[:4]
        if top_findings:
            primary = top_findings[0]
            primary_summary = primary.reasoning_summary.strip()
            narrative = (
                f"{_tool_name(primary)} reported {primary.evidence_verdict.lower()} evidence "
                f"at {float(primary.confidence_raw or 0.0):.0%} confidence: "
                f"{primary_summary[:180]}"
            )
        else:
            narrative = (
                f"{self.agent_name} found no applicable forensic signals for this file type "
                f"during {phase} analysis."
            )

        sections = []
        for idx, f in enumerate(top_findings, start=1):
            tool_name = str(f.metadata.get("tool_name") or f.finding_type)
            degraded = bool(f.metadata.get("degraded") or f.metadata.get("fallback_reason"))
            sections.append(
                {
                    "id": f"tool_signal_{idx}",
                    "label": _tool_name(f),
                    "opinion": f.reasoning_summary[:420],
                    "severity": _severity(f),
                    "refined_findings": [
                        {
                            "tool": tool_name,
                            "user_friendly_summary": f.reasoning_summary[:300],
                        }
                    ],
                    "key_signal": f.metadata.get("raw_tool_summary") or f.finding_type,
                    "flag": "warn" if degraded else ("bad" if _severity(f) in {"HIGH", "CRITICAL"} else "ok"),
                }
            )
        return {
            "agent_confidence": confidence,
            "agent_error_rate": error_rate,
            "verdict": verdict,
            "narrative_summary": narrative,
            "sections": sections,
            "synthesis_source": "tool_grounded_deterministic",
            "fallback_reason": "LLM narrative unavailable; summary generated directly from model/tool outputs.",
        }

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

        await self._initialize_working_memory()

        self._tool_registry = await self.build_tool_registry()
        await self._publish_tool_registry_snapshot()
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
            heavy_tool_semaphore=self.heavy_tool_semaphore,
            agent=self,
        )

        llm_generator = None
        if self.config.llm_enable_react_reasoning and self.config.llm_api_key:
            llm_client = LLMClient(self.config)
            if llm_client.is_available:
                llm_generator = create_llm_step_generator(
                    llm_client=llm_client,
                    config=self.config,
                    agent_name=self.agent_name,
                    evidence_context={
                        "mime_type": getattr(self.evidence_artifact, "mime_type", "")
                    },
                )

        loop_result = await loop_engine.run(
            initial_thought=initial_thought,
            tool_registry=self._tool_registry,
            llm_generator=llm_generator,
        )

        self._findings = loop_result.findings
        self._react_chain = loop_result.react_chain
        self._loop_result = loop_result

        synthesis = await self._synthesize_findings_once(
            self._findings, phase="initial", timeout_s=15.0
        )

        if synthesis is None:
            synthesis = self._build_deterministic_synthesis(self._findings, phase="initial")
        if not synthesis or not synthesis.get("sections"):
            synthesis = self._build_deterministic_synthesis(self._findings, phase="initial")
        self._agent_confidence = synthesis["agent_confidence"]
        self._agent_error_rate = synthesis["agent_error_rate"]
        self._agent_synthesis = synthesis

        await self._publish_agent_context("initial", self._findings)
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
        await self._publish_tool_registry_snapshot(deep_agent_id)

        loop_engine = ReActLoopEngine(
            agent_id=deep_agent_id,
            session_id=self.session_id,
            iteration_ceiling=len(deep_tasks) + 3,
            working_memory=self.working_memory,
            custody_logger=self.custody_logger,
            heavy_tool_semaphore=self.heavy_tool_semaphore,
            agent=self,
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
        synthesis = await self._synthesize_findings_once(
            self._findings, phase="deep", timeout_s=20.0
        )
        if synthesis is None:
            synthesis = self._build_deterministic_synthesis(self._findings, phase="deep")
        if not synthesis or not synthesis.get("sections"):
            synthesis = self._build_deterministic_synthesis(self._findings, phase="deep")
        self._agent_confidence = synthesis["agent_confidence"]
        self._agent_error_rate = synthesis["agent_error_rate"]
        self._agent_synthesis = synthesis
        await self._publish_agent_context("deep", self._findings)
        self._reflection_report = await self.self_reflection_pass(self._findings)
        await deep_trace.complete({"deep_finding_count": len(deep_findings)})
        return deep_findings

    async def run_challenge(
        self, contradicting_finding: dict[str, Any], context: dict[str, Any]
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
                },
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
            heavy_tool_semaphore=self.heavy_tool_semaphore,
        )

        llm_generator = None
        if self.config.llm_enable_react_reasoning and self.config.llm_api_key:
            llm_client = LLMClient(self.config)
            llm_generator = create_llm_step_generator(
                llm_client=llm_client,
                config=self.config,
                agent_name=self.agent_name,
                evidence_context={"challenge_mode": True, "contradiction": contradicting_finding},
            )

        if self._tool_registry is None:
            self._tool_registry = await self.build_tool_registry()

        loop_result = await loop_engine.run(
            initial_thought=challenge_thought,
            tool_registry=self._tool_registry,
            llm_generator=llm_generator,
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
