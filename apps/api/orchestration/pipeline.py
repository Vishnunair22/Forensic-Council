"""
Forensic Council Pipeline
=========================

End-to-end orchestration pipeline for forensic evidence analysis.

This module is the thin orchestrator. Implementation details live in:
  orchestration/signal_bus.py      — SignalBus, quorum logic
  orchestration/agent_factory.py   — AgentFactory, AgentLoopResult
  orchestration/pipeline_phases.py — concurrent agent execution, HITL gate
  orchestration/pipeline_enrichment.py — report enrichment, custody verify
"""

from __future__ import annotations

import asyncio
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import UUID, uuid4

from agents.arbiter import CouncilArbiter
from core.agent_registry import get_agent_registry
from core.config import Settings, get_settings
from core.inter_agent_bus import InterAgentBus
from core.persistence.evidence_store import EvidenceStore
from core.structured_logging import get_logger

# Re-export so existing imports keep working
from orchestration.agent_factory import AgentFactory, AgentLoopResult
from orchestration.pipeline_registry import register_pipeline, unregister_pipeline
from orchestration.session_manager import SessionManager
from orchestration.signal_bus import SignalBus

logger = get_logger(__name__)

# Public re-exports consumed by tests and worker.py
__all__ = [
    "ForensicCouncilPipeline",
    "SignalBus",
    "AgentFactory",
    "AgentLoopResult",
    "CouncilArbiter",
    "EvidenceStore",
    "InterAgentBus",
    "SessionManager",
    "get_agent_registry",
]


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
        self.config = config or get_settings()

        self._degradation_flags: list[str] = []
        self._final_report = None
        self._error: str | None = None
        self._current_run_task: asyncio.Task | None = None

        self.deep_analysis_decision_event: asyncio.Event = asyncio.Event()
        self.run_deep_analysis_flag: bool = False
        self._awaiting_user_decision: bool = False
        self._arbiter_step: str = ""
        self._session_id: UUID | None = None
        self._pre_warm_task: asyncio.Task | None = None

        self._setup_infrastructure()

        self.custody_logger = None
        self.working_memory = None
        self.episodic_memory = None
        self.inter_agent_bus = None
        self.evidence_store = None
        self.session_manager = None
        self.arbiter = None
        self.signal_bus: SignalBus | None = None

        self.heavy_tool_semaphore = asyncio.Semaphore(
            max(1, (self.config.max_parallel_heavy_tools or 2))
        )

    def _setup_infrastructure(self) -> None:
        self._redis = None
        self._qdrant = None
        self._postgres = None

    async def _initialize_components(self, session_id: UUID) -> None:
        """Initialize all components for a session."""
        from api.routes._session_state import broadcast_update
        from api.schemas import BriefUpdate
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
                    "Rate limiting and token blacklisting may be degraded."
                )

        try:
            await broadcast_update(
                str(session_id),
                BriefUpdate(
                    type="AGENT_UPDATE",
                    session_id=str(session_id),
                    agent_id=None,
                    message="Initializing forensic core...",
                    data={
                        "status": "initiating",
                        "thinking": "Establishing secure neural bridge...",
                    },
                ),
            )
        except Exception as _e:
            logger.debug("Initial broadcast skipped (SSE not yet open)", error=str(_e))

        if self._qdrant is None:
            try:
                try:
                    await broadcast_update(
                        str(session_id),
                        BriefUpdate(
                            type="AGENT_UPDATE",
                            session_id=str(session_id),
                            agent_id=None,
                            message="Establishing episodic link...",
                            data={
                                "status": "initiating",
                                "thinking": "Syncing with Qdrant vector space...",
                            },
                        ),
                    )
                except Exception as _e:
                    logger.debug("Qdrant connect broadcast skipped", error=str(_e))
                self._qdrant = await get_qdrant_client()
            except Exception as e:
                logger.warning("Failed to connect to Qdrant", error=str(e))
                self._qdrant = None
                self._degradation_flags.append(
                    "Qdrant unavailable; episodic memory and historical case-linking disabled."
                )

        if self._postgres is None:
            try:
                try:
                    await broadcast_update(
                        str(session_id),
                        BriefUpdate(
                            type="AGENT_UPDATE",
                            session_id=str(session_id),
                            agent_id=None,
                            message="Connecting to custody ledger...",
                            data={
                                "status": "initiating",
                                "thinking": "Securing Postgres persistence layer...",
                            },
                        ),
                    )
                except Exception as _e:
                    logger.debug("Postgres connect broadcast skipped", error=str(_e))
                self._postgres = await get_postgres_client()
            except Exception as e:
                logger.warning("Failed to connect to PostgreSQL", error=str(e))
                self._postgres = None
                self._degradation_flags.append(
                    "PostgreSQL unavailable; custody log and report persistence disabled. "
                    "Reports will exist in memory only for this session."
                )

        from core.custody_logger import CustodyLogger

        self.custody_logger = CustodyLogger(postgres_client=self._postgres)

        # Broadcast custody entries to the UI without changing the logger API.
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
                        await broadcast_update(
                            ws_session_id,
                            BriefUpdate(
                                type="HITL_CHECKPOINT",
                                session_id=ws_session_id,
                                agent_id=agent_id,
                                agent_name=agent_name,
                                message=f"HITL checkpoint: {content.get('reason', 'Review required')}",
                                data={
                                    "status": "paused",
                                    "checkpoint": {
                                        "id": content.get("checkpoint_id"),
                                        "agent_id": agent_id,
                                        "reason": content.get("reason"),
                                        "brief": content.get("brief"),
                                    },
                                },
                            ),
                        )
                    elif type_val == "ACTION" and isinstance(content, dict):
                        # Only broadcast ACTION entries that have a real tool_name.
                        # THOUGHT entries after all tools complete cause progress text to
                        # keep cycling on the frontend after analysis is done.
                        if content.get("action") == "session_start":
                            return result
                        if not content.get("tool_name"):
                            return result

                        # Humanized tool names for frontend progress display
                        TOOL_DISPLAY_NAMES = {
                            "extract_text_from_image": "Forensic OCR",
                            "file_hash_verify": "Hash Verification",
                            "analyze_image_content": "Semantic Audit",
                            "frequency_domain_analysis": "FFT Noise Scan",
                            "neural_fingerprint_scan": "Neural Fingerprint",
                            "diffusion_artifact_detection": "Diffusion Scan",
                            "gan_artifact_audit": "GAN Neural Pass",
                            "f3_net_splicing_scan": "Splicing Audit",
                            "object_detection": "Structural Audit",
                            "scene_incongruence": "Contextual Scan",
                            "hex_signature_scan": "Binary Signature",
                            "compression_risk_audit": "Compression Scan",
                            "provenance_chain_verify": "C2PA Provenance",
                            "timestamp_analysis": "Chronology Audit",
                            "file_structure_analysis": "Structure Check",
                            "gemini_deep_forensic": "Multimodal Synthesis",
                        }

                        agent_name = AGENT_NAMES.get(agent_id, agent_id)
                        raw_tool_name = content.get("tool_name")
                        tool_name = (
                            raw_tool_name if isinstance(raw_tool_name, str) else None
                        )

                        display_name = TOOL_DISPLAY_NAMES.get(
                            tool_name,
                            tool_name.replace("_", " ").title()
                            if tool_name
                            else "Forensic Pass",
                        )

                        thinking_text = f"Running {display_name}..."
                        iteration = content.get("iteration")
                        tools_done = (
                            iteration if isinstance(iteration, int) and iteration > 0 else None
                        )
                        await broadcast_update(
                            ws_session_id,
                            BriefUpdate(
                                type="AGENT_UPDATE",
                                session_id=ws_session_id,
                                agent_id=agent_id,
                                agent_name=agent_name,
                                message=thinking_text,
                                data={
                                    "status": "running",
                                    "thinking": thinking_text,
                                    "tool_name": tool_name,
                                    "tools_done": tools_done,
                                },
                            ),
                        )
                except Exception as e:
                    logger.debug("Broadcast failed", error=str(e))
                return result

            self.custody_logger.log_entry = broadcast_log_entry
        except ImportError as _e:
            logger.warning(
                "FastAPI schemas unavailable; custody broadcast patch skipped", error=str(_e)
            )

        from core.persistence.storage import LocalStorageBackend

        if self.evidence_store is None:
            self.evidence_store = EvidenceStore(
                postgres_client=self._postgres,
                storage_backend=LocalStorageBackend(
                    storage_path=str(self.config.evidence_storage_path)
                ),
                custody_logger=self.custody_logger,
            )

        from core.episodic_memory import EpisodicMemory
        from core.working_memory import WorkingMemory

        self.working_memory = WorkingMemory(
            redis_client=self._redis,
            custody_logger=self.custody_logger,
        )
        self.episodic_memory = EpisodicMemory(
            qdrant_client=self._qdrant,
            custody_logger=self.custody_logger,
        )
        self.inter_agent_bus = InterAgentBus(
            config=self.config,
            session_id=session_id,
            working_memory=self.working_memory,
            episodic_memory=self.episodic_memory,
            custody_logger=self.custody_logger,
            evidence_store=self.evidence_store,
        )
        self.inter_agent_bus.set_abort_handler(self._handle_global_abort)
        await self.inter_agent_bus.start()

        self.session_manager = SessionManager(redis_client=self._redis)

        self.agent_factory = AgentFactory(
            config=self.config,
            working_memory=self.working_memory,
            episodic_memory=self.episodic_memory,
            custody_logger=self.custody_logger,
            evidence_store=self.evidence_store,
            inter_agent_bus=self.inter_agent_bus,
        )

        self.arbiter = CouncilArbiter(
            session_id=session_id,
            custody_logger=self.custody_logger,
            inter_agent_bus=self.inter_agent_bus,
            agent_factory=self.agent_factory,
            config=self.config,
        )

        async def _broadcast_arbiter_step(msg: str):
            try:
                from api.routes._session_state import (
                    broadcast_update,
                    get_active_pipeline_metadata,
                    set_active_pipeline_metadata,
                )
                from api.schemas import BriefUpdate

                await broadcast_update(
                    str(session_id),
                    BriefUpdate(
                        type="ARBITER_UPDATE",
                        session_id=str(session_id),
                        agent_id=None,
                        message=msg,
                        data={"status": "deliberating", "thinking": msg},
                    ),
                )
                existing = await get_active_pipeline_metadata(str(session_id)) or {}
                await set_active_pipeline_metadata(str(session_id), {**existing, "brief": msg})
            except Exception as _e:
                logger.debug("Arbiter step broadcast skipped", error=str(_e))

        self.arbiter._step_hook = _broadcast_arbiter_step

    async def run_investigation(
        self,
        evidence_file_path: str,
        case_id: str,
        investigator_id: str,
        original_filename: str | None = None,
        session_id: UUID | None = None,
    ):
        """Run a complete forensic investigation on evidence."""
        logger.info(
            "Starting forensic investigation",
            case_id=case_id,
            investigator_id=investigator_id,
            evidence_path=evidence_file_path,
        )

        session_id = session_id or uuid4()
        self._session_id = session_id
        self._case_id = case_id
        self._started_at = datetime.now(UTC).isoformat()
        self._degradation_flags = []

        loop = asyncio.get_running_loop()
        self._investigation_deadline = loop.time() + self.config.investigation_timeout

        try:
            self._current_run_task = asyncio.current_task()
            register_pipeline(session_id, self)
            await self._run_investigation_core(
                evidence_file_path, case_id, investigator_id, original_filename, session_id
            )
            if self._error:
                raise RuntimeError(self._error)
            if self._final_report is None:
                raise RuntimeError("Investigation finished but no report was generated")
            return self._final_report
        except asyncio.CancelledError:
            logger.warning("Investigation cancelled (Global Abort)")
            if self._error:
                raise RuntimeError(f"Investigation aborted: {self._error}") from None
            raise
        finally:
            self._current_run_task = None
            unregister_pipeline(session_id)
            await self._clear_working_memory_for_session(session_id)

    async def _run_investigation_core(
        self,
        evidence_file_path: str,
        case_id: str,
        investigator_id: str,
        original_filename: str | None,
        session_id: UUID,
    ) -> None:
        """Core investigation orchestration."""
        from core.agent_registry import get_agent_registry
        from core.custody_logger import EntryType
        from core.observability import get_tracer
        from orchestration.pipeline_enrichment import enrich_report
        from orchestration.pipeline_phases import run_agents_concurrent

        _tracer = get_tracer("forensic-council.pipeline")
        from core.agent_registry import AgentID

        await self._initialize_components(session_id)

        # Defensive pre-flight clear: Ensure no stale Redis/WAL keys exist for this session ID
        await self._clear_working_memory_for_session(session_id)

        try:
            from api.routes._session_state import broadcast_update
            from api.schemas import BriefUpdate

            await broadcast_update(
                str(session_id),
                BriefUpdate(
                    type="AGENT_UPDATE",
                    session_id=str(session_id),
                    agent_id=None,
                    message="Forensic pipeline initialized. Ingesting evidence...",
                    data={"status": "initiating", "thinking": "Securing evidence artifacts..."},
                ),
            )
        except Exception as _e:
            logger.debug("Pipeline-init broadcast skipped", error=str(_e))

        evidence_artifact = await self._ingest_evidence(
            evidence_file_path, session_id, investigator_id, original_filename=original_filename
        )

        try:
            from api.routes._session_state import broadcast_update
            from api.schemas import BriefUpdate

            await broadcast_update(
                str(session_id),
                BriefUpdate(
                    type="AGENT_UPDATE",
                    session_id=str(session_id),
                    agent_id=None,
                    message="Evidence secured. Initializing forensic session...",
                    data={"status": "processing", "thinking": "Validating chain of custody..."},
                ),
            )
        except Exception as _e:
            logger.debug("Evidence-secured broadcast skipped", error=str(_e))

        if hasattr(self, "agent_factory"):
            self.agent_factory.set_evidence_artifact(evidence_artifact)
        if hasattr(self, "inter_agent_bus"):
            self.inter_agent_bus._evidence_artifact = evidence_artifact

        all_agents = get_agent_registry().get_all_agent_ids()
        await self.session_manager.create_session(
            session_id=session_id,
            case_id=case_id,
            investigator_id=investigator_id,
            agent_ids=all_agents,
        )

        try:
            from api.routes._session_state import broadcast_update
            from api.schemas import BriefUpdate

            await broadcast_update(
                str(session_id),
                BriefUpdate(
                    type="AGENT_UPDATE",
                    session_id=str(session_id),
                    agent_id=None,
                    message="Session active. Dispatching specialist agents...",
                    data={"status": "processing", "thinking": "Allocating neural resources..."},
                ),
            )
        except Exception as _e:
            logger.debug("Session-active broadcast skipped", error=str(_e))

        self.signal_bus = SignalBus(all_agents)

        from orchestration.session_manager import SessionStatus

        await self.session_manager.update_agent_status(
            session_id=session_id,
            agent_id="all",
            status=SessionStatus.RUNNING,
        )

        agent_results = await run_agents_concurrent(
            pipeline=self,
            evidence_artifact=evidence_artifact,
            session_id=session_id,
        )

        from orchestration.session_manager import SessionStatus

        for aid in get_agent_registry().get_all_agent_ids():
            await self.session_manager.update_agent_status(
                session_id=session_id,
                agent_id=aid,
                status=SessionStatus.COMPLETED,
            )

        arbiter_results = self._normalize_agent_results(agent_results)

        # Speculative Pre-warm: Start the arbiter metrics/verdict computation in background
        # while waiting for the HITL gate (Accept/Deep decision).
        self._pre_warm_task = asyncio.create_task(
            self._run_arbiter_pre_warm(arbiter_results, case_id)
        )
        report = await self._run_deliberation(arbiter_results, case_id, session_id)

        try:
            from orchestration.pipeline_enrichment import enrich_report
            await enrich_report(
                pipeline=self,
                report=report,
                session_id=session_id,
                artifact=evidence_artifact,
                agent_results=agent_results,
            )
        except Exception as enrich_err:
            logger.warning(
                "Report enrichment failed — proceeding with unsigned base report",
                error=str(enrich_err),
            )
            self._degradation_flags.append(
                f"Report enrichment failed: {enrich_err}. Some metadata may be incomplete."
            )

        self._final_report = await self.arbiter.sign_report(report)

        # Add calibration status to degradation flags if uncalibrated
        if hasattr(report, "calibration_status") and report.calibration_status in ("UNCALIBRATED", "IDENTITY"):
            self._degradation_flags.append(
                f"Model calibration: {report.calibration_status} (scores may not be reliable for court submission)"
            )

        if self._degradation_flags:
            self._final_report.degradation_flags = self._degradation_flags

        await self.session_manager.set_final_report(
            session_id=session_id,
            report_id=self._final_report.report_id,
        )

        try:
            from api.routes._session_state import set_final_report as cache_report
            await cache_report(str(session_id), self._final_report)
        except Exception as cache_err:
            logger.warning("Failed to cache report in Redis", error=str(cache_err))

        if self.custody_logger:
            from core.agent_registry import AgentID
            from core.custody_logger import EntryType
            await self.custody_logger.log_entry(
                entry_type=EntryType.REPORT_SIGNED,
                agent_id=AgentID.ARBITER.value,
                session_id=session_id,
                content={
                    "report_id": str(self._final_report.report_id),
                    "total_findings": sum(
                        len(f) for f in self._final_report.per_agent_findings.values()
                    ),
                },
            )

        try:
            from api.routes._session_state import broadcast_update
            from api.schemas import BriefUpdate

            await broadcast_update(
                str(session_id),
                BriefUpdate(
                    type="REPORT_READY",
                    session_id=str(session_id),
                    message=f"Forensic report ready: {self._final_report.overall_verdict}",
                    data={
                        "report_id": str(self._final_report.report_id),
                        "verdict": self._final_report.overall_verdict,
                    },
                ),
            )
        except Exception as _e:
            logger.debug("REPORT_READY broadcast skipped", error=str(_e))

        if hasattr(self, "inter_agent_bus"):
            await self.inter_agent_bus.stop()

    async def _run_arbiter_pre_warm(self, agent_results: dict[str, Any], case_id: str) -> None:
        """Background task to run arbiter pre-warm with UI broadcasting."""
        if not self.arbiter:
            return
        try:
            from api.routes._session_state import broadcast_update
            from api.schemas import BriefUpdate

            # Initial broadast: Deliberation started
            await broadcast_update(
                str(self._session_id),
                BriefUpdate(
                    type="ARBITER_UPDATE",
                    session_id=str(self._session_id),
                    data={"status": "pre_warming", "thinking": "Synthesizing agent cross-modal signals..."},
                )
            )

            await self.arbiter.pre_warm(agent_results, case_id)

            # Final pre-warm broadcast: Metrics ready
            await broadcast_update(
                str(self._session_id),
                BriefUpdate(
                    type="ARBITER_UPDATE",
                    session_id=str(self._session_id),
                    data={"status": "pre_warm_complete", "thinking": "Speculative synthesis complete. Standing by for decision."},
                )
            )
        except Exception as e:
            logger.warning(f"Arbiter pre-warm background task failed: {e}")

    def invalidate_pre_warm(self) -> None:
        """Clear speculative arbiter state (e.g. if deep analysis is requested)."""
        if self._pre_warm_task and not self._pre_warm_task.done():
            self._pre_warm_task.cancel()
        self._pre_warm_task = None
        if self.arbiter:
            self.arbiter.clear_pre_warm_cache()

    def _normalize_agent_results(self, agent_results: list[AgentLoopResult]) -> dict[str, Any]:
        """Normalize agent findings for the arbiter."""
        from core.react_loop import AgentFinding

        arbiter_results = {}
        for result in agent_results:
            normalized_findings = []
            if result.error is not None:
                error_finding = AgentFinding(
                    agent_id=result.agent_id,
                    finding_type=f"{result.agent_id} error",
                    status="INCOMPLETE",
                    confidence_raw=None,
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
    ):
        """Run council arbiter deliberation with timeout and fallback."""
        logger.info("Running council arbiter deliberation")
        _start = time.perf_counter()
        use_llm = bool(self.config.llm_enable_post_synthesis)

        # Ensure pre-warm is complete before starting final synthesis
        if self._pre_warm_task:
            try:
                await asyncio.wait_for(self._pre_warm_task, timeout=20.0)
            except Exception as e:
                logger.warning("Arbiter pre-warm failed or timed out, re-running synchronously", error=str(e))
                await self.arbiter.pre_warm(arbiter_results, case_id=case_id)
            self._pre_warm_task = None

        try:
            report = await asyncio.wait_for(
                self.arbiter.finalise_from_cache(use_llm=use_llm),
                timeout=90.0,
            )
        except TimeoutError:
            logger.warning("arbiter.finalise_from_cache() timed out — falling back to template")
            if use_llm:
                self._degradation_flags.append(
                    "Arbiter LLM synthesis timed out — report generated from templates."
                )
            report = await asyncio.wait_for(
                self.arbiter.finalise_from_cache(use_llm=False),
                timeout=30.0,
            )

        logger.info(
            "Arbiter deliberation complete",
            session_id=str(session_id),
            elapsed_seconds=round(time.perf_counter() - _start, 2),
            verdict=report.overall_verdict,
        )
        return report

    async def _handle_global_abort(self, payload: dict | None = None) -> None:
        """Handle a GLOBAL_ABORT signal by cancelling the investigation."""
        reason = (
            payload.get("reason", "Unknown forensic violation")
            if payload
            else "Unknown forensic violation"
        )
        self._error = f"GLOBAL_ABORT: {reason}"

        if self._session_id is not None:
            try:
                from api.routes._session_state import broadcast_update
                from api.schemas import BriefUpdate

                await broadcast_update(
                    str(self._session_id),
                    BriefUpdate(
                        type="PIPELINE_QUARANTINED",
                        session_id=str(self._session_id),
                        message=f"CRITICAL: Pipeline quarantined. Reason: {reason}",
                        data={"status": "quarantined", "reason": reason},
                    ),
                )
            except Exception as _e:
                logger.debug("Quarantine broadcast skipped", error=str(_e))

        if self._current_run_task:
            self._current_run_task.cancel()

    async def _clear_working_memory_for_session(self, session_id: UUID) -> None:
        """Clean up working memory (Redis + WAL) for all agents after session ends."""
        if self.working_memory is None:
            return
        from core.agent_registry import get_agent_registry

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
    ):
        """Ingest evidence file and create artifact."""
        from core.observability import get_tracer

        _tracer = get_tracer("forensic-council.pipeline")
        with _tracer.start_as_current_span("pipeline.ingest_evidence") as span:
            span.set_attribute("file_path", file_path)
            span.set_attribute("session_id", str(session_id))
            file_path_obj = Path(file_path)

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

    async def handle_hitl_decision(self, session_id: UUID, checkpoint_id: UUID, decision) -> None:
        """Route human decision to correct agent's loop engine."""

        logger.info(
            "Handling HITL decision",
            session_id=str(session_id),
            checkpoint_id=str(checkpoint_id),
            decision=decision.decision_type,
        )

        checkpoints = await self.session_manager.get_active_checkpoints(session_id)
        checkpoint = next((cp for cp in checkpoints if cp.checkpoint_id == checkpoint_id), None)
        if not checkpoint:
            raise ValueError(f"Checkpoint {checkpoint_id} not found")

        await self.session_manager.resolve_checkpoint(
            checkpoint_id=checkpoint_id,
            decision={
                "status": decision.decision_type,
                "notes": decision.notes,
                "metadata": decision.metadata,
            },
        )

        # Logic to notify the agent loop can follow here
        # (e.g. by setting an event the agent is waiting on)

    def _get_mime_type(self, file_path: str) -> str:
        """Lightweight MIME detection."""
        import mimetypes
        mime, _ = mimetypes.guess_type(file_path)
        return mime or "application/octet-stream"
