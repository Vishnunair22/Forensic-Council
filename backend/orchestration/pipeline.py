"""
Forensic Council Pipeline
=========================

End-to-end orchestration pipeline for forensic evidence analysis.
"""

from __future__ import annotations

import asyncio
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional
from uuid import UUID, uuid4

from core.config import Settings, get_settings
from core.custody_logger import CustodyLogger, EntryType
from core.episodic_memory import EpisodicMemory
from core.evidence import EvidenceArtifact
from core.inter_agent_bus import InterAgentBus
from core.observability import get_tracer
from core.structured_logging import get_logger
from core.react_loop import HumanDecision
from core.working_memory import WorkingMemory
from infra.evidence_store import EvidenceStore



from agents.agent1_image import Agent1Image
from agents.agent2_audio import Agent2Audio
from agents.agent3_object import Agent3Object
from agents.agent4_video import Agent4Video
from agents.agent5_metadata import Agent5Metadata
from agents.arbiter import CouncilArbiter, ForensicReport

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
        inter_agent_bus: Optional[InterAgentBus] = None,
    ):
        self.config = config
        self.working_memory = working_memory
        self.episodic_memory = episodic_memory
        self.custody_logger = custody_logger
        self.evidence_store = evidence_store
        self.inter_agent_bus = inter_agent_bus
        self._evidence_artifact: Optional[EvidenceArtifact] = None

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

        # Create the appropriate agent class
        agent_class = self._get_agent_class(agent_id)

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

        # Create and run the agent
        agent = agent_class(**agent_kwargs)

        # Run investigation
        findings = await agent.run_investigation()

        # Return results in expected format
        return {
            "agent_id": agent_id,
            "findings": [f.model_dump() for f in findings],
            "reflection_report": (
                agent._reflection_report.model_dump()
                if hasattr(agent, "_reflection_report") and agent._reflection_report
                else {}
            ),
            "react_chain": getattr(agent, "_react_chain", []),
            "challenge_context": challenge_context,
        }

    def _get_agent_class(self, agent_id: str) -> type:
        """Get the agent class for a given agent ID."""
        agent_map = {
            "Agent1": Agent1Image,
            "Agent2": Agent2Audio,
            "Agent3": Agent3Object,
            "Agent4": Agent4Video,
            "Agent5": Agent5Metadata,
        }

        if agent_id not in agent_map:
            raise ValueError(f"Unknown agent_id: {agent_id}")

        return agent_map[agent_id]


class AgentLoopResult:
    """Result from running an agent's investigation loop."""

    def __init__(
        self,
        agent_id: str,
        findings: list[dict[str, Any]],
        reflection_report: dict[str, Any],
        react_chain: list[dict[str, Any]],
        error: Optional[str] = None,
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


class ForensicCouncilPipeline:
    """
    End-to-end pipeline for forensic evidence analysis.

    Orchestrates:
    - Evidence ingestion and artifact creation
    - Multi-agent investigation (5 specialist agents)
    - Council arbiter deliberation
    - Report generation with cryptographic signing
    """

    def __init__(self, config: Optional[Settings] = None):
        """
        Initialize the pipeline.

        Args:
            config: Optional override configuration
        """
        self.config = config or get_settings()

        # State tracking for the two-phase deep analysis pause
        self.deep_analysis_decision_event = asyncio.Event()
        self.run_deep_analysis_flag = False
        self._degradation_flags: list[str] = []

        # Report and error state — set by the investigation task
        self._final_report: Optional[ForensicReport] = None
        self._error: Optional[str] = None

        # Initialize infrastructure
        self._setup_infrastructure()

        # Initialize components
        self.custody_logger: Optional[CustodyLogger] = None
        self.working_memory: Optional[WorkingMemory] = None
        self.episodic_memory: Optional[EpisodicMemory] = None
        self.inter_agent_bus: Optional[InterAgentBus] = None
        self.evidence_store: Optional[EvidenceStore] = None
        self.session_manager: Optional[SessionManager] = None
        self.arbiter: Optional[CouncilArbiter] = None

    def _setup_infrastructure(self) -> None:
        """Set up infrastructure slot placeholders — actual connections are
        acquired lazily in _initialize_components using the global singletons."""
        self._redis = None
        self._qdrant = None
        self._postgres = None

    async def _initialize_components(self, session_id: UUID) -> None:
        """Initialize all components for a session."""
        from infra.qdrant_client import get_qdrant_client
        from infra.postgres_client import get_postgres_client

        if self._redis is None:
            try:
                from infra.redis_client import get_redis_client

                self._redis = await get_redis_client()
            except Exception as e:
                logger.warning("Failed to connect to Redis", error=str(e))
                self._redis = None
                self._degradation_flags.append(
                    "Redis unavailable — working memory fell back to in-process dict; "
                    "rate limiting and token blacklisting may be degraded."
                )

        if self._qdrant is None:
            try:
                self._qdrant = await get_qdrant_client()
            except Exception as e:
                logger.warning("Failed to connect to Qdrant", error=str(e))
                self._qdrant = None
                self._degradation_flags.append(
                    "Qdrant unavailable — episodic memory and historical case-linking disabled."
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

        from infra.storage import LocalStorageBackend
        from infra.evidence_store import EvidenceStore

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

        # Initialize inter-agent bus
        self.inter_agent_bus = InterAgentBus()

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

        Steps:
        1. Ingest evidence → EvidenceArtifact (with hash)
        2. Create session_id UUID (use provided if available)
        3. Instantiate all 5 agents with shared evidence artifact and session
        4. Run agents concurrently (asyncio.gather) — each runs full ReAct loop
        5. Collect all AgentLoopResults
        6. Pass to CouncilArbiter.deliberate()
        7. Return signed ForensicReport

        Args:
            evidence_file_path: Path to the evidence file
            case_id: Case identifier
            investigator_id: ID of the investigator running this analysis
            session_id: Optional existing session_id to use (for continued sessions)

        Returns:
            Signed ForensicReport with all findings
        """
        logger.info(
            "Starting forensic investigation",
            case_id=case_id,
            investigator_id=investigator_id,
            evidence_path=evidence_file_path,
        )

        with _tracer.start_as_current_span("pipeline.run_investigation") as span:
            span.set_attribute("case_id", case_id)
            span.set_attribute("investigator_id", investigator_id)
            span.set_attribute("evidence_path", evidence_file_path)

        # Step 1 & 2: Create session and ingest evidence
        # Use provided session_id if available, otherwise create new one
        if session_id is None:
            session_id = uuid4()
        self._case_id = case_id
        self._started_at = datetime.now(timezone.utc).isoformat()
        self._degradation_flags: list[str] = []
        # Issue 6.1: Use asyncio monotonic clock consistently for all deadline
        # arithmetic so clock adjustments (NTP slew) cannot skew the budget.
        loop = asyncio.get_event_loop()
        self._investigation_deadline = (
            loop.time() + self.config.investigation_timeout
        )

        await self._initialize_components(session_id)

        # Create evidence artifact
        evidence_artifact = await self._ingest_evidence(
            evidence_file_path,
            session_id,
            investigator_id,
            original_filename=original_filename,
        )

        # Set evidence artifact in agent factory for challenge loops
        if hasattr(self, "agent_factory"):
            self.agent_factory.set_evidence_artifact(evidence_artifact)

        # Set evidence artifact in inter-agent bus for on-demand agent creation
        if hasattr(self, "inter_agent_bus"):
            self.inter_agent_bus._evidence_artifact = evidence_artifact
            self.inter_agent_bus._session_id = session_id

        # Create session in manager
        await self.session_manager.create_session(
            session_id=session_id,
            case_id=case_id,
            investigator_id=investigator_id,
            agent_ids=["Agent1", "Agent2", "Agent3", "Agent4", "Agent5"],
        )

        # Step 3 & 4: Instantiate and run all agents concurrently
        agent_results = await self._run_agents_concurrent(
            evidence_artifact=evidence_artifact,
            session_id=session_id,
        )

        # Step 5: Mark all agents as completed
        for aid in ["Agent1", "Agent2", "Agent3", "Agent4", "Agent5"]:
            await self.session_manager.update_agent_status(
                session_id=session_id,
                agent_id=aid,
                status=SessionStatus.COMPLETED,
            )

        # Step 6: Run arbiter deliberation
        logger.info("Running council arbiter deliberation")

        # Build agent results dict for arbiter
        arbiter_results = {}
        for result in agent_results:
            if result.error is None:
                # Normalize findings to dictionaries to prevent AttributeError in arbiter
                normalized_findings = []
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
                }

        # Run deliberation with a hard 90-second ceiling so the pipeline never
        # hangs indefinitely if Groq is down. If it times out, regenerate the
        # report without LLM synthesis (template fallback path in the arbiter).
        with _tracer.start_as_current_span("pipeline.arbiter_deliberation") as span:
            span.set_attribute("case_id", case_id)
            span.set_attribute("agent_count", len(arbiter_results))
            _arbiter_start = time.perf_counter()
            try:
                report = await asyncio.wait_for(
                    self.arbiter.deliberate(arbiter_results, case_id=case_id),
                    timeout=90.0,
                )
                span.set_attribute("verdict", str(report.overall_verdict))
            except asyncio.TimeoutError:
                logger.warning(
                    "arbiter.deliberate() exceeded 90 s — regenerating with LLM disabled",
                    session_id=str(session_id),
                )
                self._degradation_flags.append(
                    "Arbiter LLM synthesis timed out after 90 s — report narrative generated "
                    "from templates, not AI synthesis. Verdict and findings are unaffected."
                )
                report = await asyncio.wait_for(
                    self.arbiter.deliberate(
                        arbiter_results, case_id=case_id, use_llm=False
                    ),
                    timeout=30.0,
                )
                span.set_attribute("verdict", str(report.overall_verdict))
                span.set_attribute("timeout", True)

        _arbiter_elapsed = time.perf_counter() - _arbiter_start
        logger.info(
            "Arbiter deliberation complete",
            session_id=str(session_id),
            elapsed_seconds=round(_arbiter_elapsed, 2),
            verdict=report.overall_verdict,
            findings_count=sum(len(f) for f in report.per_agent_findings.values()),
        )
        if _arbiter_elapsed > 120:
            logger.warning(
                "Arbiter deliberation took unusually long",
                elapsed_seconds=round(_arbiter_elapsed, 2),
                session_id=str(session_id),
            )

        # ── Detect Gemini degradation ────────────────────────────────────────
        # If Gemini is configured but all gemini_vision findings are errors,
        # or no gemini_vision findings appear at all, flag degradation.
        gemini_key = self.config.gemini_api_key
        is_gemini_configured = bool(gemini_key) and "your_gemini_key" not in (
            gemini_key or ""
        )
        if is_gemini_configured:
            gemini_findings = report.gemini_vision_findings
            if not gemini_findings:
                self._degradation_flags.append(
                    "Gemini vision API was configured but produced no findings — "
                    "deep-pass agents (1, 3, 5) fell back to local OpenCV analysis. "
                    "Possible causes: invalid API key, model quota exceeded, network error."
                )
            else:
                # Check if ALL Gemini findings are errors (none succeeded)
                all_gemini_errored = all(
                    isinstance(gf, dict)
                    and (
                        gf.get("error")
                        or gf.get("metadata", {}).get("error")
                        or gf.get("status") == "INCOMPLETE"
                    )
                    for gf in gemini_findings
                )
                if all_gemini_errored:
                    error_msgs = [
                        gf.get("error")
                        or gf.get("metadata", {}).get("error", "unknown")
                        for gf in gemini_findings
                        if isinstance(gf, dict)
                    ]
                    first_err = str(error_msgs[0])[:200] if error_msgs else "unknown"
                    self._degradation_flags.append(
                        f"Gemini vision API returned errors for all {len(gemini_findings)} analysis(es): "
                        f"{first_err}. Deep-pass agents used local OpenCV fallback."
                    )

        # Add additional fields to report (each capped at 15 s to prevent hangs
        # when external infra is slow or unreachable after the arbiter finishes).
        try:
            report.case_linking_flags = await asyncio.wait_for(
                self._collect_case_linking_flags(session_id, evidence_artifact),
                timeout=15.0,
            )
        except asyncio.TimeoutError:
            logger.warning("Case linking flags collection timed out")
            report.case_linking_flags = []

        try:
            report.chain_of_custody_log = await asyncio.wait_for(
                self._get_custody_log(session_id),
                timeout=15.0,
            )
        except asyncio.TimeoutError:
            logger.warning("Custody log fetch timed out")
            report.chain_of_custody_log = []

        try:
            report.evidence_version_trees = await asyncio.wait_for(
                self._get_version_trees(evidence_artifact.artifact_id),
                timeout=15.0,
            )
        except asyncio.TimeoutError:
            logger.warning("Version trees fetch timed out")
            report.evidence_version_trees = []

        report.react_chains = {
            r.agent_id: r.react_chain for r in agent_results if r.error is None
        }
        report.self_reflection_outputs = {
            r.agent_id: r.reflection_report for r in agent_results if r.error is None
        }

        # Verify chain-of-custody integrity before signing the report.
        # A broken chain means an entry was tampered with after being written —
        # this is a critical integrity failure that must be disclosed.
        if self.custody_logger and self.custody_logger._postgres is not None:
            try:
                chain_report = await asyncio.wait_for(
                    self.custody_logger.verify_chain(session_id),
                    timeout=15.0,
                )
                if not chain_report.valid:
                    logger.error(
                        "Chain-of-custody integrity check FAILED before report signing",
                        session_id=str(session_id),
                        broken_at=str(chain_report.broken_at),
                        reason=chain_report.broken_reason,
                    )
                    self._degradation_flags.append(
                        f"CRITICAL: Chain-of-custody integrity verification FAILED "
                        f"(entry {chain_report.broken_at}: {chain_report.broken_reason}). "
                        "This report's evidential chain may have been tampered with."
                    )
                else:
                    logger.info(
                        "Chain-of-custody integrity verified",
                        session_id=str(session_id),
                        total_entries=chain_report.total_entries,
                    )
            except Exception as _verify_err:
                logger.warning(
                    "Chain-of-custody verification raised an exception",
                    error=str(_verify_err),
                    session_id=str(session_id),
                )
                self._degradation_flags.append(
                    f"Chain-of-custody verification could not complete: {_verify_err}"
                )
        else:
            self._degradation_flags.append(
                "Chain-of-custody verification skipped — PostgreSQL unavailable."
            )

        # Propagate all pipeline-level degradation flags into the report BEFORE signing
        # so they are covered by the cryptographic signature.
        if self._degradation_flags:
            report.degradation_flags.extend(self._degradation_flags)
            logger.warning(
                "Report contains degradation flags",
                session_id=str(session_id),
                flag_count=len(self._degradation_flags),
                flags=self._degradation_flags,
            )

        # Resign report after adding all fields — broadcast final step if hook set
        _sign_step_hook = getattr(self.arbiter, "_step_hook", None)
        if _sign_step_hook is not None:
            try:
                await _sign_step_hook("Signing cryptographic hash…")
            except Exception as e:
                logger.debug("Sign step hook failed", error=str(e))
        report = await self.arbiter.sign_report(report)

        # Step 7: Return signed report
        await self.session_manager.set_final_report(
            session_id=session_id,
            report_id=report.report_id,
        )

        # Log completion
        if self.custody_logger:
            await self.custody_logger.log_entry(
                entry_type=EntryType.REPORT_SIGNED,
                agent_id="Arbiter",
                session_id=session_id,
                content={
                    "report_id": str(report.report_id),
                    "total_findings": sum(
                        len(f) for f in report.per_agent_findings.values()
                    ),
                },
            )

        logger.info(
            "Investigation complete",
            report_id=str(report.report_id),
            session_id=str(session_id),
        )

        return report

    async def _clear_working_memory_for_session(self, session_id: UUID) -> None:
        """Issue 14.3: Clean up working memory (Redis + WAL) for all agents after session ends."""
        if self.working_memory is None:
            return
        agent_ids = ["Agent1", "Agent2", "Agent3", "Agent4", "Agent5", "Arbiter"]
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

        # Store in evidence store
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
                    if not agent.supports_uploaded_file:
                        return agent, [], False
                    logger.info(f"Running {agent_id} initial investigation")
                    initial_findings = await asyncio.wait_for(
                        agent.run_investigation(),
                        timeout=self.config.investigation_timeout,
                    )
                    span.set_attribute("finding_count", len(initial_findings))
                    # Issue 6.3: Persist each agent's initial findings to Redis
                    # immediately so a worker crash doesn't lose completed work.
                    await self._checkpoint_agent_result(session_id, agent_id, initial_findings)
                    return agent, initial_findings, True
                except Exception as e:
                    logger.error(
                        f"{agent_id} initial pass failed", error=str(e), exc_info=True
                    )
                    return None, [], False

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
                        findings=[f.model_dump() for f in all_findings],
                        reflection_report=(
                            getattr(agent, "_reflection_report", None).model_dump()
                            if getattr(agent, "_reflection_report", None)
                            else {}
                        ),
                        react_chain=getattr(agent, "_react_chain", []),
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
                        findings=[f.model_dump() for f in initial_findings],
                        reflection_report={},
                        react_chain=getattr(agent, "_react_chain", []),
                        agent_active=True,
                        supports_file_type=True,
                        error=str(e),
                    )

        # --- Phase 1: All initial passes concurrently ---
        (
            (agent1, a1_init, a1_ok),
            (agent2, a2_init, a2_ok),
            (agent3, a3_init, a3_ok),
            (agent4, a4_init, a4_ok),
            (agent5, a5_init, a5_ok),
        ) = [
            r if not isinstance(r, BaseException) else (None, [], False)
            for r in await asyncio.gather(
                run_agent_initial_only(Agent1Image, "Agent1"),
                run_agent_initial_only(
                    Agent2Audio, "Agent2", {"inter_agent_bus": self.inter_agent_bus}
                ),
                run_agent_initial_only(
                    Agent3Object, "Agent3", {"inter_agent_bus": self.inter_agent_bus}
                ),
                run_agent_initial_only(
                    Agent4Video, "Agent4", {"inter_agent_bus": self.inter_agent_bus}
                ),
                run_agent_initial_only(Agent5Metadata, "Agent5"),
                return_exceptions=True,
            )
        ]

        # --- Phase 2: All deep passes concurrently with Agent1 context sync ---
        #
        # Agent3 and Agent5 run their tools immediately (in parallel with Agent1's
        # Gemini). They block ONLY at their own Gemini call, waiting for Agent1's
        # vision findings via an asyncio.Event injected before we launch.  This
        # eliminates the old sequential bottleneck while preserving cross-agent
        # accuracy: Agent3/5 Gemini calls receive Agent1 context as soon as it is
        # ready, then compare it against their own tool findings for final synthesis.
        agent1_context_event = asyncio.Event()

        # Inject the event BEFORE launching deep passes so handlers can await it.
        if agent3 is not None:
            agent3._agent1_context_event = agent1_context_event
        if agent5 is not None:
            agent5._agent1_context_event = agent1_context_event

        async def _run_agent1_deep_and_signal() -> AgentLoopResult:
            """Run Agent1 deep, inject context into Agent3/5, then set the event."""
            result = await run_agent_deep_only(agent1, "Agent1", a1_init, a1_ok)
            try:
                if agent1 is not None:
                    gemini_result = getattr(agent1, "_gemini_vision_result", {})
                    if not gemini_result:
                        for f in result.findings or []:
                            if (
                                isinstance(f, dict)
                                and f.get("metadata", {}).get("tool_name")
                                == "gemini_deep_forensic"
                            ):
                                gemini_result = f.get("metadata", {})
                                break
                    if gemini_result:
                        if agent3 is not None:
                            agent3.inject_agent1_context(gemini_result)
                        if agent5 is not None:
                            agent5.inject_agent1_context(gemini_result)
                        logger.info(
                            "Agent1 Gemini context injected into Agent3/5",
                            has_content_type=bool(
                                gemini_result.get("gemini_content_type")
                            ),
                            has_objects=bool(
                                gemini_result.get("gemini_detected_objects")
                            ),
                        )
            except Exception as _ctx_err:
                logger.warning(
                    f"Could not inject Agent1 context into Agent3/5: {_ctx_err}"
                )
            finally:
                # Always unblock Agent3/5 — even if Agent1 failed or context was empty.
                agent1_context_event.set()
            return result

        raw_deep_all = await asyncio.gather(
            _run_agent1_deep_and_signal(),
            run_agent_deep_only(agent2, "Agent2", a2_init, a2_ok),
            run_agent_deep_only(agent3, "Agent3", a3_init, a3_ok),
            run_agent_deep_only(agent4, "Agent4", a4_init, a4_ok),
            run_agent_deep_only(agent5, "Agent5", a5_init, a5_ok),
            return_exceptions=True,
        )
        raw_deep = list(raw_deep_all)
        # Unwrap any exceptions into error results rather than propagating
        agent_ids_deep = ["Agent1", "Agent2", "Agent3", "Agent4", "Agent5"]
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
            serialisable = [
                f.model_dump(mode="json") if hasattr(f, "model_dump") else f
                for f in findings
            ]
            await self._redis.set(key, _json.dumps(serialisable), ex=ttl)
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
            import magic  # python-magic — already a project dependency

            return magic.from_file(file_path, mime=True)
        except Exception:
            # Extension-based fallback — kept for robustness
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
