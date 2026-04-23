"""
Forensic Council Pipeline
=========================

End-to-end orchestration pipeline for forensic evidence analysis.
"""

from __future__ import annotations

import asyncio
import inspect
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import UUID, uuid4

from core.agent_registry import get_agent_registry
from core.config import Settings, get_settings


class SignalBus:
    """Async signal bus for cross-agent coordination and early deliberation."""
    def __init__(self, agent_ids: list[str]):
        self.events = {aid: asyncio.Event() for aid in agent_ids}
        self.findings = {aid: [] for aid in agent_ids}
        self.quorum_event = asyncio.Event()
        self._required_quorum = max(1, len(agent_ids) // 2 + 1)
        self._ready_agents = set()

    def signal_ready(self, agent_id: str, initial_findings: list):
        """Signal that an agent has finished its initial investigation."""
        if agent_id in self.events:
            self.findings[agent_id] = initial_findings
            self.events[agent_id].set()
            self._ready_agents.add(agent_id)
            if len(self._ready_agents) >= self._required_quorum:
                self.quorum_event.set()

    async def wait_for_quorum(self, timeout: float = 60.0):
        """Wait until a quorum of agents is ready."""
        try:
            await asyncio.wait_for(self.quorum_event.wait(), timeout=timeout)
            return True
        except TimeoutError:
            return False
from agents.arbiter import CouncilArbiter, ForensicReport
from core.custody_logger import CustodyLogger, EntryType
from core.episodic_memory import EpisodicMemory
from core.evidence import EvidenceArtifact
from core.inter_agent_bus import InterAgentBus
from core.observability import get_tracer
from core.persistence.evidence_store import EvidenceStore
from core.react_loop import AgentFinding, HumanDecision
from core.structured_logging import get_logger
from core.working_memory import WorkingMemory
from orchestration.session_manager import SessionManager, SessionStatus

_tracer = get_tracer("forensic-council.pipeline")
logger = get_logger(__name__)


class AgentFactory:
    """
    Factory for creating and re-invoking forensic agents.

    Provides a clean interface for the Arbiter to re-invoke agents
    during challenge loops without needing direct knowledge of agent
    instantiation details.
    """

    def __init__(
        self,
        config: Settings,
        working_memory: WorkingMemory,
        episodic_memory: EpisodicMemory,
        custody_logger: CustodyLogger,
        evidence_store: EvidenceStore,
        inter_agent_bus: InterAgentBus | None = None,
    ):
        self.config = config
        self.working_memory = working_memory
        self.episodic_memory = episodic_memory
        self.custody_logger = custody_logger
        self.evidence_store = evidence_store
        self.inter_agent_bus = inter_agent_bus
        self._evidence_artifact: EvidenceArtifact | None = None

    def set_evidence_artifact(self, artifact: EvidenceArtifact) -> None:
        """Set the evidence artifact for agent re-invocation."""
        self._evidence_artifact = artifact

    async def reinvoke_agent(
        self,
        agent_id: str,
        session_id: UUID,
        challenge_context: dict[str, Any],
    ) -> dict[str, Any]:
        """
        Re-invoke an agent with challenge context.

        Args:
            agent_id: ID of the agent to re-invoke (Agent1-5)
            session_id: Session ID for the investigation
            challenge_context: Context from the contradicting finding

        Returns:
            Agent results including findings and reflection report
        """
        if self._evidence_artifact is None:
            raise ValueError(
                "Evidence artifact not set - call set_evidence_artifact first"
            )

        logger.info(
            "Re-invoking agent for challenge loop",
            agent_id=agent_id,
            session_id=str(session_id),
            challenge_id=challenge_context.get("challenge_id"),
        )

        # Build agent kwargs
        agent_kwargs = {
            "agent_id": agent_id,
            "session_id": session_id,
            "evidence_artifact": self._evidence_artifact,
            "config": self.config,
            "working_memory": self.working_memory,
            "episodic_memory": self.episodic_memory,
            "custody_logger": self.custody_logger,
            "evidence_store": self.evidence_store,
        }

        # Add inter_agent_bus for Agent2, Agent3, and Agent4
        if agent_id in ("Agent2", "Agent3", "Agent4") and self.inter_agent_bus:
            agent_kwargs["inter_agent_bus"] = self.inter_agent_bus

        # Create and run the agent. Prefer the registry's class API, but keep
        # compatibility with tests/legacy registries that expose create_agent().
        registry = get_agent_registry()
        create_agent = getattr(registry, "create_agent", None)
        used_create_agent = callable(create_agent)
        if used_create_agent:
            agent = create_agent(**agent_kwargs)
        else:
            agent_class = self._get_agent_class(agent_id)
            agent = agent_class(**agent_kwargs)

        # Run investigation with challenge context injected into initial thought
        if challenge_context.get("contradiction"):
            contradiction = challenge_context["contradiction"]
            if isinstance(contradiction, str):
                contradiction = {"finding_type": "contradiction", "detail": contradiction}
            # Store challenge context so the agent's build_initial_thought
            # can reference it for a focused re-examination.
            agent._challenge_context = challenge_context
        challenge_id = challenge_context.get("challenge_id")
        if isinstance(challenge_id, str):
            try:
                challenge_id = UUID(challenge_id)
            except ValueError:
                pass
        if used_create_agent and challenge_id is not None:
            maybe_findings = agent.run_investigation(challenge_id)
        else:
            maybe_findings = agent.run_investigation()
        findings = await maybe_findings if inspect.isawaitable(maybe_findings) else maybe_findings

        serialized_findings = [
            f.model_dump(mode="json") if hasattr(f, "model_dump") else f
            for f in findings
        ]

        reflection_report = (
            getattr(agent, "__dict__", {}).get("_reflection_report")
            if hasattr(agent, "__dict__")
            else getattr(agent, "_reflection_report", None)
        )

        # Return results in expected format
        return {
            "agent_id": agent_id,
            "findings": serialized_findings,
            "reflection_report": (
                reflection_report.model_dump(mode="json")
                if reflection_report and hasattr(reflection_report, "model_dump")
                else {}
            ),
            "react_chain": _serialize_react_chain(getattr(agent, "_react_chain", [])),
            "challenge_context": challenge_context,
        }

    def _get_agent_class(self, agent_id: str) -> type:
        """Get the agent class from the central registry."""
        return get_agent_registry().get_agent_class(agent_id)


class AgentLoopResult:
    """Result from running an agent's investigation loop."""

    def __init__(
        self,
        agent_id: str,
        findings: list[dict[str, Any]],
        reflection_report: dict[str, Any],
        react_chain: list[dict[str, Any]],
        error: str | None = None,
        agent_active: bool = True,
        supports_file_type: bool = True,
        deep_findings_count: int = 0,
    ):
        self.agent_id = agent_id
        self.findings = findings
        self.reflection_report = reflection_report
        self.react_chain = react_chain
        self.error = error
        self.agent_active = agent_active  # Whether agent actually ran
        self.supports_file_type = (
            supports_file_type  # Whether agent supports this file type
        )
        self.deep_findings_count = (
            deep_findings_count  # Number of findings from deep analysis
        )


def _serialize_react_chain(react_chain: list[Any]) -> list[dict[str, Any]]:
    """Convert ReActStep objects to JSON-safe dicts before storing in reports."""
    serialized: list[dict[str, Any]] = []
    for step in react_chain:
        if isinstance(step, dict):
            serialized.append(step)
        elif hasattr(step, "model_dump"):
            serialized.append(step.model_dump(mode="json"))
        else:
            serialized.append({"content": str(step)})
    return serialized


class ForensicCouncilPipeline:
    """
    End-to-end pipeline for forensic evidence analysis.

    Orchestrates:
    - Evidence ingestion and artifact creation
    - Multi-agent investigation (5 specialist agents)
    - Council arbiter deliberation
    - Report generation with cryptographic signing
    """

    def __init__(self, config: Settings | None = None):
        """
        Initialize the pipeline.

        Args:
            config: Optional override configuration
        """
        self.config = config or get_settings()

        self._degradation_flags: list[str] = []

        # Report and error state, set by the investigation task.
        self._final_report: ForensicReport | None = None
        self._error: str | None = None

        # Deep analysis pause/resume, set by the investigation wrapper.
        # when the initial analysis completes and the user must decide.
        self.deep_analysis_decision_event: asyncio.Event = asyncio.Event()
        self.run_deep_analysis_flag: bool = False
        self._awaiting_user_decision: bool = False
        self._arbiter_step: str = ""

        # Initialize infrastructure
        self._setup_infrastructure()

        # Initialize components
        self.custody_logger: CustodyLogger | None = None
        self.working_memory: WorkingMemory | None = None
        self.episodic_memory: EpisodicMemory | None = None
        self.inter_agent_bus: InterAgentBus | None = None
        self.evidence_store: EvidenceStore | None = None
        self.session_manager: SessionManager | None = None
        self.arbiter: CouncilArbiter | None = None
        self.signal_bus: SignalBus | None = None

    def _setup_infrastructure(self) -> None:
        """Set up infrastructure slot placeholders; actual connections are
        acquired lazily in _initialize_components using the global singletons."""
        self._redis = None
        self._qdrant = None
        self._postgres = None

    async def _initialize_components(self, session_id: UUID) -> None:
        """Initialize all components for a session."""
        from core.persistence.postgres_client import get_postgres_client
        from core.persistence.qdrant_client import get_qdrant_client

        if self._redis is None:
            try:
                from core.persistence.redis_client import get_redis_client

                self._redis = await get_redis_client()
            except Exception as e:
                logger.warning("Failed to connect to Redis", error=str(e))
                self._redis = None
                self._degradation_flags.append(
                    "Redis unavailable; working memory fell back to in-process dict. "
                    "rate limiting and token blacklisting may be degraded."
                )

        if self._qdrant is None:
            try:
                self._qdrant = await get_qdrant_client()
            except Exception as e:
                logger.warning("Failed to connect to Qdrant", error=str(e))
                self._qdrant = None
                self._degradation_flags.append(
                    "Qdrant unavailable; episodic memory and historical case-linking disabled."
                )

        if self._postgres is None:
            try:
                self._postgres = await get_postgres_client()
            except Exception as e:
                logger.warning("Failed to connect to PostgreSQL", error=str(e))
                self._postgres = None

        # Initialize custody logger
        self.custody_logger = CustodyLogger(
            postgres_client=self._postgres,
        )

        # Native event broadcast.
        try:
            from api.routes._session_state import AGENT_NAMES, broadcast_update
            from api.schemas import BriefUpdate

            ws_session_id = str(session_id)
            original_log_entry = self.custody_logger.log_entry

            async def broadcast_log_entry(**kwargs):
                result = await original_log_entry(**kwargs)
                try:
                    entry_type = kwargs.get("entry_type")
                    content = kwargs.get("content", {})
                    raw_agent_id = kwargs.get("agent_id")
                    agent_id = raw_agent_id if isinstance(raw_agent_id, str) else "system"
                    type_val = getattr(entry_type, "value", str(entry_type))

                    if type_val == "HITL_CHECKPOINT" and isinstance(content, dict):
                        agent_name = AGENT_NAMES.get(agent_id, agent_id)
                        await broadcast_update(ws_session_id, BriefUpdate(
                            type="HITL_CHECKPOINT", session_id=ws_session_id, agent_id=agent_id, agent_name=agent_name,
                            message=f"HITL checkpoint: {content.get('reason', 'Review required')}",
                            data={"status": "paused", "checkpoint": {"id": content.get("checkpoint_id"), "agent_id": agent_id, "reason": content.get("reason"), "brief": content.get("brief")}}
                        ))
                    elif type_val in ("THOUGHT", "ACTION") and isinstance(content, dict):
                        if content.get("action") == "session_start": return result
                        agent_name = AGENT_NAMES.get(agent_id, agent_id)
                        raw_tool_name = content.get("tool_name") if type_val == "ACTION" else None
                        tool_name = raw_tool_name if isinstance(raw_tool_name, str) else None
                        thinking_text = f"Calling {tool_name.replace('_', ' ').title()}..." if tool_name else content.get("content", "Analyzing...")
                        iteration = content.get("iteration")
                        tools_done = iteration if isinstance(iteration, int) and iteration > 0 else None
                        await broadcast_update(ws_session_id, BriefUpdate(
                            type="AGENT_UPDATE", session_id=ws_session_id, agent_id=agent_id, agent_name=agent_name, message=thinking_text, data={
                                "status": "running",
                                "thinking": thinking_text,
                                "tool_name": tool_name,
                                "tools_done": tools_done,
                            }
                        ))
                except Exception as e:
                    logger.debug("Broadcast failed", error=str(e))
                return result

            self.custody_logger.log_entry = broadcast_log_entry
        except ImportError:
            pass  # Ignore if not running in an environment with FastAPI schemas.

        from core.persistence.evidence_store import EvidenceStore
        from core.persistence.storage import LocalStorageBackend

        if self.evidence_store is None:
            self.evidence_store = EvidenceStore(
                postgres_client=self._postgres,
                storage_backend=LocalStorageBackend(
                    storage_path=str(self.config.evidence_storage_path)
                ),
                custody_logger=self.custody_logger,
            )

        # Initialize working memory
        self.working_memory = WorkingMemory(
            redis_client=self._redis,
            custody_logger=self.custody_logger,
        )

        # Initialize episodic memory
        self.episodic_memory = EpisodicMemory(
            qdrant_client=self._qdrant,
            custody_logger=self.custody_logger,
        )

        # Initialize inter-agent bus; pass all available components so the
        # _create_agent() fallback works if any agent fails to register itself.
        # evidence_artifact is set later (post-ingestion) via direct assignment.
        self.inter_agent_bus = InterAgentBus(
            config=self.config,
            session_id=session_id,
            working_memory=self.working_memory,
            episodic_memory=self.episodic_memory,
            custody_logger=self.custody_logger,
            evidence_store=self.evidence_store,
        )

        # Initialize session manager
        self.session_manager = SessionManager(redis_client=self._redis)

        # Initialize agent factory for challenge loops
        self.agent_factory = AgentFactory(
            config=self.config,
            working_memory=self.working_memory,
            episodic_memory=self.episodic_memory,
            custody_logger=self.custody_logger,
            evidence_store=self.evidence_store,
            inter_agent_bus=self.inter_agent_bus,
        )

        # Initialize arbiter with agent factory
        self.arbiter = CouncilArbiter(
            session_id=session_id,
            custody_logger=self.custody_logger,
            inter_agent_bus=self.inter_agent_bus,
            agent_factory=self.agent_factory,
            config=self.config,
        )

    async def run_investigation(
        self,
        evidence_file_path: str,
        case_id: str,
        investigator_id: str,
        original_filename: str | None = None,
        session_id: UUID | None = None,
    ) -> ForensicReport:
        """
        Run a complete forensic investigation on evidence.
        """
        logger.info(
            "Starting forensic investigation",
            case_id=case_id,
            investigator_id=investigator_id,
            evidence_path=evidence_file_path,
        )

        # Step 1 & 2: Create session and ingest evidence
        session_id = session_id or uuid4()
        self._case_id = case_id
        self._started_at = datetime.now(UTC).isoformat()
        self._degradation_flags = []

        loop = asyncio.get_running_loop()
        self._investigation_deadline = loop.time() + self.config.investigation_timeout

        try:
            await self._run_investigation_core(
                evidence_file_path, case_id, investigator_id, original_filename, session_id
            )
            if self._error:
                raise RuntimeError(self._error)

            if self._final_report is None:
                raise RuntimeError("Investigation finished but no report was generated")

            return self._final_report

        finally:
            # Ensure working memory is cleared even on failure
            await self._clear_working_memory_for_session(session_id)

    async def _run_investigation_core(
        self,
        evidence_file_path: str,
        case_id: str,
        investigator_id: str,
        original_filename: str | None,
        session_id: UUID,
    ) -> None:
        """Core logic for the investigation pipeline."""
        await self._initialize_components(session_id)

        # Create evidence artifact
        evidence_artifact = await self._ingest_evidence(
            evidence_file_path,
            session_id,
            investigator_id,
            original_filename=original_filename,
        )

        # Set evidence artifact in factory and bus
        if hasattr(self, "agent_factory"):
            self.agent_factory.set_evidence_artifact(evidence_artifact)
        if hasattr(self, "inter_agent_bus"):
            self.inter_agent_bus._evidence_artifact = evidence_artifact

        # Create session in manager with all registered agents
        all_agents = get_agent_registry().get_all_agent_ids()
        await self.session_manager.create_session(
            session_id=session_id,
            case_id=case_id,
            investigator_id=investigator_id,
            agent_ids=all_agents,
        )

        # Initialize signal bus
        self.signal_bus = SignalBus(all_agents)

        # Run agents concurrently
        # Note: We pass the signal_bus so agents can trigger early quorum
        agent_results = await self._run_agents_concurrent(
            evidence_artifact=evidence_artifact,
            session_id=session_id,
        )

        # Mark all registered agents as completed
        for aid in get_agent_registry().get_all_agent_ids():
            await self.session_manager.update_agent_status(
                session_id=session_id,
                agent_id=aid,
                status=SessionStatus.COMPLETED,
            )

        # Deliberate and sign report
        # DELIBERATION START: Arbiter can start early if quorum reached in signal_bus
        # For now, we still wait for deep passes to finish, but we ensure the signal_bus
        # has the context for early synthesis and episodic memory pre-fetching.
        arbiter_results = self._normalize_agent_results(agent_results)
        report = await self._run_deliberation(arbiter_results, case_id, session_id)

        # Enrich and sign report
        await self._enrich_report(report, session_id, evidence_artifact, agent_results)
        self._final_report = await self.arbiter.sign_report(report)

        # Finalize session
        await self.session_manager.set_final_report(
            session_id=session_id,
            report_id=self._final_report.report_id,
        )

        if self.custody_logger:
            await self.custody_logger.log_entry(
                entry_type=EntryType.REPORT_SIGNED,
                agent_id="Arbiter",
                session_id=session_id,
                content={
                    "report_id": str(self._final_report.report_id),
                    "total_findings": sum(
                        len(f) for f in self._final_report.per_agent_findings.values()
                    ),
                },
            )

    def _normalize_agent_results(self, agent_results: list[AgentLoopResult]) -> dict[str, Any]:
        """Normalize agent findings for the arbiter."""
        arbiter_results = {}
        for result in agent_results:
            normalized_findings = []
            if result.error is not None:
                error_finding = AgentFinding(
                    agent_id=result.agent_id,
                    finding_type=f"{result.agent_id} error",
                    status="INCOMPLETE",
                    confidence_raw=0.0,
                    evidence_verdict="ERROR",
                    reasoning_summary=f"Agent failed during investigation: {result.error}",
                    metadata={
                        "court_statement": "This agent encountered an error and could not complete analysis.",
                    },
                )
                normalized_findings.append(error_finding.model_dump(mode="json"))
            else:
                for f in result.findings:
                    if hasattr(f, "model_dump"):
                        normalized_findings.append(f.model_dump(mode="json"))
                    elif isinstance(f, dict):
                        normalized_findings.append(f)
                    else:
                        normalized_findings.append(vars(f))

            arbiter_results[result.agent_id] = {
                "findings": normalized_findings,
                "reflection_report": result.reflection_report,
                "react_chain": result.react_chain,
                "agent_had_error": result.error is not None,
            }
        return arbiter_results

    async def _run_deliberation(
        self, arbiter_results: dict[str, Any], case_id: str, session_id: UUID
    ) -> ForensicReport:
        """Run council arbiter deliberation with timeout and fallback."""
        logger.info("Running council arbiter deliberation")
        _start = time.perf_counter()
        use_llm = bool(self.config.llm_enable_post_synthesis)
        try:
            report = await asyncio.wait_for(
                self.arbiter.deliberate(
                    arbiter_results, case_id=case_id, use_llm=use_llm
                ),
                timeout=90.0,
            )
        except TimeoutError:
            logger.warning("arbiter.deliberate() timed out - falling back to template")
            if use_llm:
                self._degradation_flags.append(
                    "Arbiter LLM synthesis timed out - report generated from templates."
                )
            report = await asyncio.wait_for(
                self.arbiter.deliberate(arbiter_results, case_id=case_id, use_llm=False),
                timeout=30.0,
            )

        logger.info(
            "Arbiter deliberation complete",
            session_id=str(session_id),
            elapsed_seconds=round(time.perf_counter() - _start, 2),
            verdict=report.overall_verdict,
        )
        return report

    async def _enrich_report(
        self,
        report: ForensicReport,
        session_id: UUID,
        artifact: EvidenceArtifact,
        agent_results: list[AgentLoopResult],
    ) -> None:
        """Enrich the report with metadata, logs, and degradation flags."""
        # 1. Gemini degradation detection
        self._detect_gemini_degradation(report)

        # 2. Collect metadata and logs with 15s timeouts
        tasks = [
            self._collect_case_linking_flags(session_id, artifact),
            self._get_custody_log(session_id),
            self._get_version_trees(artifact.artifact_id),
        ]
        results = await asyncio.gather(*[asyncio.wait_for(t, timeout=15.0) for t in tasks], return_exceptions=True)

        report.case_linking_flags = results[0] if not isinstance(results[0], BaseException) else []
        report.chain_of_custody_log = results[1] if not isinstance(results[1], BaseException) else []
        report.evidence_version_trees = results[2] if not isinstance(results[2], BaseException) else []

        if any(isinstance(r, (Exception, asyncio.TimeoutError)) for r in results):
            logger.warning("One or more enrichment tasks failed or timed out")

        # 3. Add agent-specific fields
        report.react_chains = {
            r.agent_id: r.react_chain for r in agent_results if r.error is None
        }
        report.self_reflection_outputs = {
            r.agent_id: r.reflection_report for r in agent_results if r.error is None
        }

        # 4. Chain-of-custody verification
        await self._verify_custody_integrity(session_id)

        # 5. Apply degradation flags
        if self._degradation_flags:
            report.degradation_flags.extend(self._degradation_flags)

    def _detect_gemini_degradation(self, report: ForensicReport) -> None:
        """Detect and flag Gemini API degradation."""
        gemini_key = self.config.gemini_api_key
        if not gemini_key or "your_gemini_key" in gemini_key:
            return

        gemini_findings = report.gemini_vision_findings
        if not gemini_findings:
            self._degradation_flags.append(
                "Gemini vision API produced no findings - deep-pass agents fell back to local analysis."
            )
        elif all(self._is_gemini_error(f) for f in gemini_findings):
            # Check if reason is refusal (safety)
            is_refusal = any("safety" in str(f.get("metadata", {}).get("error", "")).lower() for f in gemini_findings)
            if is_refusal:
                self._degradation_flags.append(
                    "FORENSIC_SIGNAL_REFUSED: Gemini vision API refused to analyze content due to safety filters. "
                    "This refusal itself is a critical signal of potentially sensitive/illegal material."
                )
            else:
                self._degradation_flags.append(
                    "Gemini vision API returned errors for all analyses - deep-pass agents used local fallback."
                )

    @staticmethod
    def _is_gemini_error(finding: Any) -> bool:
        """Helper to determine if a Gemini finding is an error."""
        if not isinstance(finding, dict):
            return False
        return bool(
            finding.get("error")
            or finding.get("metadata", {}).get("error")
            or finding.get("status") == "INCOMPLETE"
        )

    async def _verify_custody_integrity(self, session_id: UUID) -> None:
        """Verify chain-of-custody integrity."""
        if not (self.custody_logger and self.custody_logger._postgres):
            self._degradation_flags.append("Chain-of-custody verification skipped - DB unavailable.")
            return

        try:
            chain_report = await asyncio.wait_for(self.custody_logger.verify_chain(session_id), timeout=15.0)
            if not chain_report.valid:
                self._degradation_flags.append(
                    f"CRITICAL: Custody integrity FAILED (entry {chain_report.broken_at}). Report may be tampered."
                )
        except Exception as e:
            logger.warning("Custody verification failed", error=str(e))
            self._degradation_flags.append(f"Custody verification could not complete: {e}")

    async def _clear_working_memory_for_session(self, session_id: UUID) -> None:
        """Issue 14.3: Clean up working memory (Redis + WAL) for all agents after session ends."""
        if self.working_memory is None:
            return
        agent_ids = get_agent_registry().get_all_agent_ids() + ["Arbiter"]
        for aid in agent_ids:
            try:
                await self.working_memory.clear(session_id, aid)
            except Exception as e:
                logger.debug("Working memory clear failed", agent_id=aid, error=str(e))

    async def _ingest_evidence(
        self,
        file_path: str,
        session_id: UUID,
        investigator_id: str,
        original_filename: str | None = None,
    ) -> EvidenceArtifact:
        """Ingest evidence file and create artifact."""
        with _tracer.start_as_current_span("pipeline.ingest_evidence") as span:
            span.set_attribute("file_path", file_path)
            span.set_attribute("session_id", str(session_id))
            file_path_obj = Path(file_path)

            # Store in evidence store inside the span so the full ingest is traced.
            stored_artifact = await self.evidence_store.ingest(
                file_path=file_path,
                session_id=session_id,
                agent_id=investigator_id,
                metadata={
                    "mime_type": self._get_mime_type(file_path),
                    "original_filename": original_filename or file_path_obj.name,
                },
            )

        return stored_artifact

    async def _run_agents_concurrent(
        self,
        evidence_artifact: EvidenceArtifact,
        session_id: UUID,
    ) -> list[AgentLoopResult]:
        """
        Run all 5 specialist agents concurrently.

        Only agents that support the uploaded file type will run.
        After initial investigation, deep analysis is run for supported agents.
        """

        with _tracer.start_as_current_span("pipeline.run_agents_concurrent") as span:
            span.set_attribute("session_id", str(session_id))

        # --- TWO-PHASE EXECUTION for cross-agent context sharing ---
        # Phase 1: Run all agents' INITIAL passes concurrently, then
        # Phase 2: Inject Agent 1's Gemini findings into Agent 3 and run all deep passes

        async def run_agent_initial_only(
            agent_class,
            agent_id: str,
            extra_kwargs: dict = None,
        ) -> tuple:
            """Run only the initial investigation pass. Returns (agent_instance, initial_findings)."""
            agent = None
            with _tracer.start_as_current_span(
                f"agent.{agent_id}.initial_pass"
            ) as span:
                span.set_attribute("agent_id", agent_id)
                try:
                    kwargs = {
                        "agent_id": agent_id,
                        "session_id": session_id,
                        "evidence_artifact": evidence_artifact,
                        "config": self.config,
                        "working_memory": self.working_memory,
                        "episodic_memory": self.episodic_memory,
                        "custody_logger": self.custody_logger,
                        "evidence_store": self.evidence_store,
                    }
                    if extra_kwargs:
                        kwargs.update(extra_kwargs)
                    agent = agent_class(**kwargs)
                    if self.inter_agent_bus is not None:
                        self.inter_agent_bus.register_agent(agent_id, agent)
                    if not agent.supports_uploaded_file:
                        return agent, [], "unsupported"
                    logger.info(f"Running {agent_id} initial investigation")
                    initial_findings = await asyncio.wait_for(
                        agent.run_investigation(),
                        timeout=min(float(self.config.investigation_timeout), 300.0),
                    )
                    span.set_attribute("finding_count", len(initial_findings))
                    # Signal the bus for early deliberation unblocking
                    if self.signal_bus:
                        self.signal_bus.signal_ready(agent_id, initial_findings)

                    return agent, initial_findings, "complete"
                except Exception as e:
                    logger.error(
                        f"{agent_id} initial pass failed", error=str(e), exc_info=True
                    )
                    findings = list(getattr(agent, "_findings", []) or []) if agent is not None else []
                    try:
                        from core.react_loop import AgentFinding

                        findings.append(
                            AgentFinding(
                                agent_id=agent_id,
                                agent_name=getattr(agent, "agent_name", agent_id),
                                finding_type="Initial Analysis Incomplete",
                                confidence_raw=0.0,
                                raw_confidence_score=0.0,
                                status="INCOMPLETE",
                                evidence_verdict="ERROR",
                                reasoning_summary=(
                                    f"{agent_id} did not finish inside the initial-analysis guardrail: {e}. "
                                    "Partial tool findings were preserved and the analyst may continue instead of being blocked."
                                ),
                                metadata={
                                    "tool_name": "initial_analysis_guardrail",
                                    "court_defensible": False,
                                    "tool_error": str(e),
                                },
                            )
                        )
                    except Exception:
                        pass
                    return agent, findings, "error"

        async def run_agent_deep_only(
            agent,
            agent_id: str,
            initial_findings: list,
            supports_file: bool,
        ) -> AgentLoopResult:
            """Run the deep investigation pass on an already-initialized agent."""
            if agent is None:
                return AgentLoopResult(
                    agent_id=agent_id,
                    findings=[],
                    reflection_report={},
                    react_chain=[],
                    agent_active=False,
                    supports_file_type=supports_file,
                    error="Initial pass failed",
                )
            if not supports_file:
                return AgentLoopResult(
                    agent_id=agent_id,
                    findings=[],
                    reflection_report={},
                    react_chain=[],
                    agent_active=False,
                    supports_file_type=False,
                )
            with _tracer.start_as_current_span(f"agent.{agent_id}.deep_pass") as span:
                span.set_attribute("agent_id", agent_id)
                try:
                    initial_count = len(initial_findings)
                    logger.info(f"Running {agent_id} deep investigation")
                    await asyncio.wait_for(
                        agent.run_deep_investigation(),
                        timeout=self.config.investigation_timeout,
                    )
                    all_findings = getattr(agent, "_findings", initial_findings)
                    deep_count = max(0, len(all_findings) - initial_count)
                    span.set_attribute("deep_finding_count", deep_count)
                    span.set_attribute("total_finding_count", len(all_findings))
                    return AgentLoopResult(
                        agent_id=agent_id,
                        findings=[f.model_dump(mode="json") for f in all_findings],
                        reflection_report=(
                            getattr(agent, "_reflection_report", None).model_dump(mode="json")
                            if getattr(agent, "_reflection_report", None)
                            else {}
                        ),
                        react_chain=_serialize_react_chain(getattr(agent, "_react_chain", [])),
                        agent_active=True,
                        supports_file_type=True,
                        deep_findings_count=max(0, deep_count),
                    )
                except Exception as e:
                    logger.error(
                        f"{agent_id} deep pass failed", error=str(e), exc_info=True
                    )
                    return AgentLoopResult(
                        agent_id=agent_id,
                        findings=[f.model_dump(mode="json") for f in initial_findings],
                        reflection_report={},
                        react_chain=_serialize_react_chain(getattr(agent, "_react_chain", [])),
                        agent_active=True,
                        supports_file_type=True,
                        error=str(e),
                    )

        # (Dynamic decomposition based on registry)
        registry = get_agent_registry()
        agent_def_list = []
        for aid in registry.get_all_agent_ids():
            extra = {}
            if aid in ("Agent2", "Agent3", "Agent4"):
                extra = {"inter_agent_bus": self.inter_agent_bus}
            agent_def_list.append((registry.get_agent_class(aid), aid, extra))

        async def _broadcast_agent_status(aid: str, status: str, message: str, findings=None, error=None, agent_inst=None):
            try:
                from api.routes._session_state import AGENT_NAMES, broadcast_update
                from api.schemas import BriefUpdate
                from core.severity import assign_severity_tier

                aname = AGENT_NAMES.get(aid, aid)
                preview = []
                synthesis = getattr(agent_inst, "_agent_synthesis", None) if agent_inst is not None else None
                if findings:
                    for f in findings:
                        m = f.metadata if hasattr(f, "metadata") else f.get("metadata", {}) if isinstance(f, dict) else {}
                        tool = m.get("tool_name") or (f.finding_type if hasattr(f, "finding_type") else f.get("finding_type"))
                        s = f.reasoning_summary if hasattr(f, "reasoning_summary") else f.get("reasoning_summary", "")
                        if not s:
                            continue
                        sev = assign_severity_tier(f)
                        evidence_verdict = str(
                            getattr(f, "evidence_verdict", "")
                            if hasattr(f, "evidence_verdict")
                            else f.get("evidence_verdict", "")
                        ).upper()
                        finding_status = str(
                            getattr(f, "status", "")
                            if hasattr(f, "status")
                            else f.get("status", "")
                        ).upper()
                        if evidence_verdict == "ERROR" or finding_status == "INCOMPLETE":
                            tv = "NEEDS_REVIEW"
                        elif evidence_verdict in ("POSITIVE", "TAMPERED", "SUSPICIOUS", "MANIPULATED") or sev in ("CRITICAL", "HIGH", "MEDIUM"):
                            tv = "FLAGGED"
                        elif evidence_verdict == "NOT_APPLICABLE" or finding_status == "NOT_APPLICABLE":
                            tv = "NOT_APPLICABLE"
                        else:
                            tv = "CLEAN"
                        preview.append({
                            "tool": tool,
                            "summary": s[:320],
                            "severity": sev,
                            "verdict": tv,
                            "key_signal": m.get("section_key_signal") or m.get("raw_tool_summary") or "",
                            "confidence": getattr(f, "confidence_raw", None) if hasattr(f, "confidence_raw") else f.get("confidence_raw"),
                            "section": m.get("section") or "",
                        })
                if isinstance(synthesis, dict) and not preview:
                    summary = str(synthesis.get("narrative_summary") or "").strip()
                    if summary:
                        preview.append({
                            "tool": "agent_synthesis",
                            "summary": summary[:420],
                            "severity": "LOW",
                            "verdict": str(synthesis.get("verdict") or "INCONCLUSIVE"),
                        })

                await broadcast_update(str(session_id), BriefUpdate(
                    type="AGENT_COMPLETE" if status in ("complete", "error", "skipped") else "AGENT_UPDATE",
                    session_id=str(session_id), agent_id=aid, agent_name=aname, message=message,
                    data={
                        "status": status,
                        "findings_count": len(findings) if findings else 0,
                        "error": error,
                        "findings_preview": preview,
                        "agent_verdict": synthesis.get("verdict") if isinstance(synthesis, dict) else None,
                        "tool_error_rate": getattr(agent_inst, "_agent_error_rate", None) if agent_inst is not None else None,
                        "tools_ran": getattr(agent_inst, "_tool_success_count", None) if agent_inst is not None else None,
                        "tools_failed": getattr(agent_inst, "_tool_error_count", None) if agent_inst is not None else None,
                        "section_flags": synthesis.get("sections") if isinstance(synthesis, dict) else None,
                    }
                ))
            except Exception as exc:
                logger.debug("Agent status broadcast failed", agent_id=aid, error=str(exc))

        async def run_agent_initial_with_status(cls, aid, ex):
            await _broadcast_agent_status(aid, "running", f"Running {aid} initial pass...")
            agent, initial_findings, result_status = await run_agent_initial_only(cls, aid, ex)
            if result_status == "unsupported":
                await _broadcast_agent_status(
                    aid,
                    "skipped",
                    f"{aid} skipped initial analysis because this file type is not supported by the agent.",
                    error="Agent skipped initial analysis as this file type is not supported.",
                    agent_inst=agent,
                )
            else:
                message = (
                    f"{aid} initial analysis completed with partial findings."
                    if result_status == "error"
                    else f"{aid} initial analysis complete."
                )
                await _broadcast_agent_status(
                    aid,
                    "complete",
                    message,
                    findings=initial_findings,
                    error=None,
                    agent_inst=agent,
                )
            return agent, initial_findings, result_status

        raw_initial = await asyncio.gather(
            *[run_agent_initial_with_status(cls, aid, ex) for cls, aid, ex in agent_def_list],
            return_exceptions=True,
        )

        # Mapping results back to instances (index-aligned with registry order)
        agent_map = {}
        for i, aid in enumerate(registry.get_all_agent_ids()):
            res = raw_initial[i] if not isinstance(raw_initial[i], BaseException) else (None, [], "error")
            agent_map[aid] = res

        agent1, a1_init, a1_ok = agent_map["Agent1"]
        agent2, a2_init, a2_ok = agent_map["Agent2"]
        agent3, a3_init, a3_ok = agent_map["Agent3"]
        agent4, a4_init, a4_ok = agent_map["Agent4"]
        agent5, a5_init, a5_ok = agent_map["Agent5"]

        initial_results = [
            AgentLoopResult(
                agent_id=aid,
                findings=[f.model_dump(mode="json") if hasattr(f, "model_dump") else f for f in findings],
                reflection_report=(
                    getattr(agent, "_reflection_report", None).model_dump(mode="json")
                    if getattr(agent, "_reflection_report", None)
                    else {}
                ),
                react_chain=_serialize_react_chain(getattr(agent, "_react_chain", [])),
                agent_active=status != "unsupported",
                supports_file_type=status != "unsupported",
            )
            for aid, (agent, findings, status) in agent_map.items()
        ]

        async def _await_deep_analysis_decision() -> bool:
            from api.routes._session_state import (
                broadcast_update,
                get_active_pipeline_metadata,
                set_active_pipeline_metadata,
            )
            from api.schemas import BriefUpdate
            from core.persistence.redis_client import get_redis_client

            decision_key = f"forensic:session:resume_decision:{session_id}"
            redis = await get_redis_client()
            await redis.delete(decision_key)

            self._awaiting_user_decision = True
            self.deep_analysis_decision_event.clear()
            self.run_deep_analysis_flag = False
            existing_metadata = await get_active_pipeline_metadata(str(session_id)) or {}
            await set_active_pipeline_metadata(
                str(session_id),
                {
                    **existing_metadata,
                    "status": "awaiting_decision",
                    "brief": "Initial analysis complete. Awaiting analyst decision.",
                    "awaiting_decision": True,
                },
            )
            await broadcast_update(
                str(session_id),
                BriefUpdate(
                    type="PIPELINE_PAUSED",
                    session_id=str(session_id),
                    message="Initial analysis complete. Awaiting analyst decision.",
                    data={
                        "status": "awaiting_decision",
                        "initial_results_ready": True,
                    },
                ),
            )

            try:
                while True:
                    decision = await redis.get_json(decision_key)
                    if isinstance(decision, dict):
                        self.run_deep_analysis_flag = bool(decision.get("deep_analysis"))
                        return self.run_deep_analysis_flag
                    if self.deep_analysis_decision_event.is_set():
                        return bool(self.run_deep_analysis_flag)
                    await asyncio.sleep(0.5)
            finally:
                self._awaiting_user_decision = False
                try:
                    await redis.delete(decision_key)
                except Exception:
                    pass

        if not await _await_deep_analysis_decision():
            logger.info("Deep analysis skipped by analyst decision", session_id=str(session_id))
            return initial_results

        # --- Phase 2: All deep passes concurrently with Early Signal Sync ---
        #
        # Agents subscribe to early signals from context producers (e.g. Agent 1).
        # This unblocks their own deep-pass tools (like Gemini) as soon as
        # higher-priority context is available, rather than waiting for the
        # producer's entire deep pass to finish.
        context_event = asyncio.Event()
        context_injected: set[str] = set()

        def _broadcast_context(producer_finding: Any):
            """Generic context broadcaster for early deep-pass signals."""
            try:
                meta = {}
                if hasattr(producer_finding, "metadata"):
                    meta = producer_finding.metadata if isinstance(producer_finding.metadata, dict) else {}
                elif isinstance(producer_finding, dict):
                    meta = producer_finding.get("metadata", {}) or producer_finding

                if meta:
                    for aid, (agent_inst, _, _) in agent_map.items():
                        if agent_inst is None or aid in context_injected:
                            continue
                        if hasattr(agent_inst, "inject_agent1_context"):
                            agent_inst.inject_agent1_context(meta)
                            context_injected.add(aid)
                    logger.info("Early context broadcast triggered from producer")

                context_event.set()
            except Exception as _cb_err:
                logger.warning(f"Early signal callback failed: {_cb_err}")

        # Configure producers and consumers
        producer_id = "Agent1" # Primary vision producer
        producer_inst = agent_map.get(producer_id, (None, None, "error"))[0]

        if producer_inst:
            producer_inst._gemini_signal_callback = _broadcast_context

        # Prepare all agents for the signal
        for _aid, (agent_inst, _, _) in agent_map.items():
            if agent_inst and hasattr(agent_inst, "_agent1_context_event"):
                agent_inst._agent1_context_event = context_event

        async def _run_deep_with_fallback(aid: str) -> AgentLoopResult:
            a_inst, a_init, a_status = agent_map[aid]
            a_supported = a_status != "unsupported"

            if not a_supported:
                return AgentLoopResult(
                    agent_id=aid,
                    findings=[],
                    reflection_report={},
                    react_chain=[],
                    agent_active=False,
                    supports_file_type=False,
                )

            await _broadcast_agent_status(aid, "running", f"Running {aid} deep pass...")
            # Start the deep pass
            result = await run_agent_deep_only(a_inst, aid, a_init, a_supported)

            if result.error:
                await _broadcast_agent_status(aid, "error", f"{aid} error: {result.error}", error=result.error, agent_inst=a_inst)
            else:
                await _broadcast_agent_status(aid, "complete", f"{aid} analysis complete.", findings=result.findings, agent_inst=a_inst)

            # Fallback for producers: if early signal didn't fire, ensure event is set
            if aid == producer_id:
                try:
                    # Scan findings for the tool result if callback never fired
                    gemini_res = {}
                    for f in result.findings or []:
                        if isinstance(f, dict) and f.get("metadata", {}).get("tool_name") == "gemini_deep_forensic":
                            gemini_res = f.get("metadata", {})
                            break

                    if gemini_res:
                        _broadcast_context(gemini_res)
                finally:
                    context_event.set()

            return result

        # Run all deep passes in parallel
        raw_deep_all = await asyncio.gather(
            *[_run_deep_with_fallback(aid) for aid in agent_map.keys()],
            return_exceptions=True,
        )
        raw_deep = list(raw_deep_all)
        # Unwrap any exceptions into error results rather than propagating
        agent_ids_deep = get_agent_registry().get_all_agent_ids()
        results = []
        for i, r in enumerate(raw_deep):
            if isinstance(r, BaseException):
                logger.error(
                    f"Agent {agent_ids_deep[i]} deep pass raised unexpectedly",
                    error=str(r),
                    exc_info=r,
                )
                results.append(
                    AgentLoopResult(
                        agent_id=agent_ids_deep[i],
                        findings=[],
                        reflection_report={},
                        react_chain=[],
                        error=str(r),
                        agent_active=False,
                    )
                )
            else:
                results.append(r)

        # Log summary of active agents
        active_agents = [r.agent_id for r in results if r.agent_active]
        skipped_agents = [r.agent_id for r in results if not r.supports_file_type]
        logger.info(
            "Agent execution summary",
            active_agents=active_agents,
            skipped_agents=skipped_agents,
        )

        for aid in get_agent_registry().get_all_agent_ids():
            if self.inter_agent_bus is not None:
                self.inter_agent_bus.unregister_agent(aid)

        return list(results)

    async def _checkpoint_agent_result(
        self,
        session_id: UUID,
        agent_id: str,
        findings: list,
    ) -> None:
        """Issue 6.3: Checkpoint a completed agent's findings to Redis so the
        work is not lost if the Uvicorn worker is killed mid-investigation."""
        if self._redis is None:
            return
        import json as _json
        key = f"forensic:checkpoint:{session_id}:{agent_id}"
        ttl = self.config.session_ttl_hours * 3600
        try:
            serializable = [
                f.model_dump(mode="json") if hasattr(f, "model_dump") else f
                for f in findings
            ]
            await self._redis.set(key, _json.dumps(serializable), ex=ttl)
            logger.debug(
                "Checkpointed agent findings to Redis",
                agent_id=agent_id,
                count=len(findings),
            )
        except Exception as e:
            logger.warning(
                "Failed to checkpoint agent result", agent_id=agent_id, error=str(e)
            )

    async def handle_hitl_decision(
        self,
        session_id: UUID,
        checkpoint_id: UUID,
        decision: HumanDecision,
    ) -> None:
        """
        Route human decision to correct agent's loop engine.

        Args:
            session_id: Session ID
            checkpoint_id: Checkpoint ID requiring human decision
            decision: Human decision (approve, reject, modify)
        """
        logger.info(
            "Handling HITL decision",
            session_id=str(session_id),
            checkpoint_id=str(checkpoint_id),
            decision=decision.decision_type,
        )

        # Get checkpoint info
        checkpoints = await self.session_manager.get_active_checkpoints(session_id)
        checkpoint = next(
            (cp for cp in checkpoints if cp.checkpoint_id == checkpoint_id), None
        )

        if not checkpoint:
            raise ValueError(f"Checkpoint {checkpoint_id} not found")

        # Resolve in session manager
        await self.session_manager.resolve_checkpoint(
            checkpoint_id=checkpoint_id,
            decision={
                "status": decision.decision_type,
                "notes": decision.notes,
                "modified_content": decision.override_finding,
            },
        )

        # Log the decision
        if self.custody_logger:
            await self.custody_logger.log_entry(
                entry_type=EntryType.HITL_DECISION,
                agent_id=checkpoint.agent_id,
                session_id=session_id,
                content={
                    "checkpoint_id": str(checkpoint_id),
                    "decision": decision.decision_type,
                    "notes": decision.notes,
                },
            )

    async def _collect_case_linking_flags(
        self,
        session_id: UUID,
        evidence_artifact: EvidenceArtifact,
    ) -> list[dict[str, Any]]:
        """Collect case linking flags from episodic memory."""
        flags = []

        try:
            entries = await self.episodic_memory.get_by_session(session_id)
            for entry in entries:
                if entry.signature_type and "LINK" in entry.signature_type.value:
                    flags.append(
                        {
                            "flag_type": entry.signature_type.value,
                            "description": entry.description,
                            "artifact_id": str(entry.artifact_id),
                        }
                    )
        except Exception as e:
            logger.warning("Failed to collect case linking flags", error=str(e))

        return flags

    async def _get_custody_log(self, session_id: UUID) -> list[dict[str, Any]]:
        """Get chain of custody log for session."""
        try:
            chain = await self.custody_logger.get_session_chain(session_id)
            return [
                {
                    "entry_id": str(e.entry_id),
                    "entry_type": e.entry_type.value,
                    "agent_id": e.agent_id,
                    "timestamp_utc": e.timestamp_utc.isoformat(),
                    "content_hash": e.content_hash,
                }
                for e in chain
            ]
        except Exception as e:
            logger.warning("Failed to get custody log", error=str(e))
            return []

    async def _get_version_trees(
        self,
        artifact_id: UUID,
    ) -> list[dict[str, Any]]:
        """Get evidence version trees."""
        try:
            tree = await self.evidence_store.get_version_tree(artifact_id)
            if not tree:
                return []

            versions = tree.get_all_artifacts()
            return [
                {
                    "artifact_id": str(v.artifact_id),
                    "parent_id": str(v.parent_id) if v.parent_id else None,
                    "content_hash": v.content_hash,
                    "created_at": v.timestamp_utc.isoformat(),
                }
                for v in versions
            ]
        except Exception as e:
            logger.warning("Failed to get version trees", error=str(e))
            return []

    def _get_mime_type(self, file_path: str) -> str:
        """
        Detect MIME type from file magic bytes (not extension).

        Uses python-magic (libmagic) to read the actual file header bytes,
        so a renamed or extension-spoofed file is identified correctly.
        Falls back to extension-based mapping if libmagic is unavailable.
        """
        try:
            import magic  # python-magic is already a project dependency.

            return magic.from_file(file_path, mime=True)
        except Exception:
            # Extension-based fallback kept for robustness.
            ext = Path(file_path).suffix.lower()
            mime_types = {
                ".jpg": "image/jpeg",
                ".jpeg": "image/jpeg",
                ".png": "image/png",
                ".gif": "image/gif",
                ".bmp": "image/bmp",
                ".tiff": "image/tiff",
                ".webp": "image/webp",
                ".wav": "audio/wav",
                ".mp3": "audio/mpeg",
                ".flac": "audio/flac",
                ".mp4": "video/mp4",
                ".avi": "video/x-msvideo",
                ".mov": "video/quicktime",
                ".mkv": "video/x-matroska",
                ".pdf": "application/pdf",
            }
            return mime_types.get(ext, "application/octet-stream")
