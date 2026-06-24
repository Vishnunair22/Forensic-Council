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


def _sha256_file(path: str) -> str:
    """Stream a SHA-256 of a file on disk (P2.17 TOCTOU re-hash). Returns "" if the
    file cannot be read so the caller can skip the check rather than crash."""
    import hashlib

    h = hashlib.sha256()
    try:
        with open(path, "rb") as f:
            for chunk in iter(lambda: f.read(1024 * 1024), b""):
                h.update(chunk)
    except OSError:
        return ""
    return h.hexdigest()


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
        self._pre_warm_gen: int = 0  # F-5: incremented on each invalidation to detect stale pre-warm results
        self._suppress_arbiter_step_broadcasts: bool = False

        self._setup_infrastructure()

        self.custody_logger = None
        self.working_memory = None
        self.episodic_memory = None
        self.inter_agent_bus = None
        self.evidence_store = None
        self.session_manager = None
        self.arbiter = None
        self.signal_bus: SignalBus | None = None
        # Shared visual context (Gemini/local-ensemble preflight result), resolved
        # once at pipeline start and threaded onto every agent so no agent has to
        # generate it or wait on Agent 1. See _run_investigation_core.
        self._visual_context: Any = None

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
                        "analysis_phase": "initial",
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
                                "analysis_phase": "initial",
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
                                "analysis_phase": "initial",
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
            # Monotonic per-agent count of tools broadcast to the UI. Drives the
            # X/Y progress counter directly, independent of the ReAct loop's
            # _current_iteration — that counter interleaves THOUGHT steps and, in
            # the deep pass (a separate Agent1_deep loop), did not advance per tool,
            # leaving the frontend "1/5" counter frozen while the live text changed.
            _agent_tool_progress: dict[str, int] = {}

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
                        tool_display_names = {
                            "extract_text_from_image": "Forensic OCR",
                            "file_hash_verify": "Hash Verification",
                            "analyze_image_content": "Semantic Audit",
                            "frequency_domain_analysis": "FFT Noise Scan",
                            "neural_fingerprint": "Neural Fingerprint",
                            "diffusion_artifact_detector": "Diffusion Scan",
                            "object_detection": "Structural Audit",
                            "scene_incongruence": "Contextual Scan",
                            "hex_signature_scan": "Binary Signature",
                            "compression_risk_audit": "Compression Scan",
                            "provenance_chain_verify": "C2PA Provenance",
                            "timestamp_analysis": "Chronology Audit",
                            "file_structure_analysis": "Structure Check",
                            "visual_evidence_profile": "Visual Evidence Profile",
                        }

                        agent_name = AGENT_NAMES.get(agent_id, agent_id)
                        raw_tool_name = content.get("tool_name")
                        tool_name = (
                            raw_tool_name if isinstance(raw_tool_name, str) else None
                        )

                        display_name = tool_display_names.get(
                            tool_name,
                            tool_name.replace("_", " ").title()
                            if tool_name
                            else "Forensic Pass",
                        )

                        thinking_text = f"Running {display_name}..."
                        # Advance this agent's X/Y counter by one per broadcast tool
                        # action (initial pass). The DEEP pass ("*_deep") is driven by
                        # the deep progress monitor in pipeline_phases, which reports the
                        # authoritative completed-task count — emitting a competing count
                        # here would fight it, so leave tools_done unset for deep.
                        #
                        # Only count tools that will SURFACE as a Key Finding — context/
                        # custody tools (visual_evidence_profile, hash, file-type
                        # validation, frame extraction) execute but are never surfaced,
                        # so counting them drifted the live "X/Y" above the completed
                        # "N tools ran" (the denominator excludes them too, see
                        # _count_surfacing_tasks in pipeline_phases).
                        from orchestration.pipeline_phases import PREVIEW_EXCLUDED_TOOLS
                        _is_surfacing = str(tool_name or "").lower() not in PREVIEW_EXCLUDED_TOOLS
                        if agent_id.endswith("_deep"):
                            tools_done = None
                        elif not _is_surfacing:
                            # Keep the counter steady but still broadcast the live
                            # descriptor so the user sees the context tool running.
                            tools_done = _agent_tool_progress.get(agent_id, 0)
                        else:
                            _agent_tool_progress[agent_id] = _agent_tool_progress.get(agent_id, 0) + 1
                            tools_done = _agent_tool_progress[agent_id]
                        current_phase = "deep" if getattr(self, "run_deep_analysis_flag", False) else "initial"
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
                                    "analysis_phase": current_phase,
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
            if self._suppress_arbiter_step_broadcasts:
                return
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
                        data={"status": "deliberating", "thinking": msg, "analysis_phase": "initial"},
                    ),
                )
                existing = await get_active_pipeline_metadata(str(session_id)) or {}
                await set_active_pipeline_metadata(
                    str(session_id),
                    {**existing, "status": "deliberating", "brief": msg, "awaiting_decision": False},
                )
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
        detected_mime: str | None = None,
        validated_extension: str | None = None,
        content_sha256: str | None = None,
        file_size_bytes: int | None = None,
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
        self._intake_mime = detected_mime
        self._intake_extension = validated_extension
        self._intake_hash = content_sha256
        self._intake_size = file_size_bytes
        self._applicable_agents = None

        loop = asyncio.get_running_loop()
        self._investigation_deadline = loop.time() + self.config.investigation_timeout

        try:
            self._current_run_task = asyncio.current_task()
            register_pipeline(session_id, self)
            await self._run_investigation_core(
                evidence_file_path, case_id, investigator_id, original_filename, session_id,
                detected_mime=detected_mime,
                validated_extension=validated_extension,
                content_sha256=content_sha256,
                file_size_bytes=file_size_bytes,
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
        detected_mime: str | None = None,
        validated_extension: str | None = None,
        content_sha256: str | None = None,
        file_size_bytes: int | None = None,
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

        # Fix 3: Clear any stale decision keys from previous sessions or crashes
        try:
            from core.persistence.redis_client import get_redis_client
            redis = await get_redis_client()
            decision_patterns = [
                f"forensic:session:resume_decision:{session_id}:*",
                f"forensic:session:resume_decision:{session_id}",
            ]
            for pattern in decision_patterns:
                if "*" in pattern:
                    cursor = 0
                    while True:
                        cursor, keys = await redis.scan(cursor, match=pattern, count=100)
                        if keys:
                            await redis.delete(*keys)
                        if cursor == 0:
                            break
                else:
                    await redis.delete(pattern)
            logger.info("Cleared stale decision keys for session", session_id=str(session_id))
        except Exception as cleanup_err:
            logger.debug("Decision key cleanup failed (non-critical)", error=str(cleanup_err))

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
                    data={"status": "initiating", "thinking": "Securing evidence artifacts...", "analysis_phase": "initial"},
                ),
            )
        except Exception as _e:
            logger.debug("Pipeline-init broadcast skipped", error=str(_e))

        evidence_artifact = await self._ingest_evidence(
            evidence_file_path, session_id, investigator_id,
            original_filename=original_filename,
            detected_mime=detected_mime,
            content_sha256=content_sha256,
            file_size_bytes=file_size_bytes,
        )
        self._evidence_mime = evidence_artifact.mime_type if evidence_artifact else ""
        # Thread the original filename to the arbiter so the deterministic report
        # narrates the real file (e.g. "Image.jpeg"), not the case_id or a generic
        # placeholder.
        if self.arbiter is not None:
            self.arbiter.original_filename = original_filename or (
                getattr(evidence_artifact, "original_filename", None) if evidence_artifact else None
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
                    data={"status": "processing", "thinking": "Validating chain of custody...", "analysis_phase": "initial"},
                ),
            )
        except Exception as _e:
            logger.debug("Evidence-secured broadcast skipped", error=str(_e))

        if hasattr(self, "agent_factory"):
            self.agent_factory.set_evidence_artifact(evidence_artifact)
        if hasattr(self, "inter_agent_bus"):
            self.inter_agent_bus._evidence_artifact = evidence_artifact

        # ── Shared visual context (awaited, up-front) ─────────────────────────
        # Resolve the visual context BEFORE any agent runs so it is generated once
        # — never by Agent 1 — and is present in this (worker) process's bus +
        # working memory + Redis. The API route fires the same preflight, but that
        # runs in the API process and only shares via Redis; awaiting here is
        # idempotent (a Redis/hash cache hit is a cheap no-op) and guarantees every
        # agent starts warm instead of racing Agent 1. Best-effort: never block the
        # investigation if it fails — agents fall back to the store/local path.
        if (self._evidence_mime or "").startswith("image/"):
            try:
                from core.visual_context_store import create_visual_context_preflight

                self._visual_context = await create_visual_context_preflight(
                    session_id=str(session_id),
                    file_path=getattr(evidence_artifact, "file_path", None) or evidence_file_path,
                    sha256=self._intake_hash
                    or content_sha256
                    or getattr(evidence_artifact, "content_hash", "")
                    or "",
                    config=self.config,
                    working_memory=self.working_memory,
                    inter_agent_bus=self.inter_agent_bus,
                )
                logger.info(
                    "Shared visual context resolved up-front",
                    session_id=str(session_id),
                    available=self._visual_context is not None,
                    source=getattr(self._visual_context, "source", None),
                )
            except Exception as _vc_err:
                logger.warning(
                    "Up-front visual context resolution failed — agents will use fallback path",
                    session_id=str(session_id),
                    error=str(_vc_err),
                )

        all_agents = get_agent_registry().get_all_agent_ids()
        await self.session_manager.create_session(
            session_id=session_id,
            case_id=case_id,
            investigator_id=investigator_id,
            agent_ids=all_agents,
            content_sha256=self._intake_hash or getattr(self, "_intake_hash", None),
            file_size_bytes=self._intake_size or getattr(self, "_intake_size", None),
            detected_mime=self._intake_mime or getattr(self, "_intake_mime", None),
            validated_extension=self._intake_extension or getattr(self, "_intake_extension", None),
            applicable_agents=getattr(self, "_applicable_agents", None),
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
                    message="",
                    data={"status": "processing", "thinking": "Allocating neural resources...", "analysis_phase": "initial"},
                ),
            )
        except Exception as _e:
            logger.debug("Session-active broadcast skipped", error=str(_e))

        self.signal_bus = SignalBus(all_agents)

        from orchestration.session_manager import SessionStatus

        # P2.17 — TOCTOU guard: re-hash the evidence on disk immediately before the
        # agents read it and reject on mismatch. This proves the bytes analysed are
        # the bytes that were ingested and hashed, not a file swapped in between.
        if self._intake_hash:
            _ev_path = getattr(evidence_artifact, "file_path", None) or evidence_file_path
            _disk_hash = await asyncio.to_thread(_sha256_file, _ev_path)
            if _disk_hash and _disk_hash != self._intake_hash:
                from core.exceptions import EvidenceIntegrityError

                logger.error(
                    "Evidence integrity check failed before analysis — hash mismatch",
                    session_id=str(session_id),
                    intake_prefix=self._intake_hash[:12],
                    disk_prefix=_disk_hash[:12],
                )
                raise EvidenceIntegrityError(
                    "Evidence hash changed between ingestion and analysis — refusing to analyse."
                )

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

        # Check for majority agent failure — abort only when agents failed
        # WITHOUT producing any initial findings. Deep-pass timeouts produce
        # valid initial findings and must not count as "failed" here.
        failed_count = sum(1 for r in agent_results if r.error and not r.findings)
        active_count = sum(1 for r in agent_results if r.agent_active)
        if failed_count >= 3 and failed_count >= active_count // 2:
            error_msg = f"{failed_count} of {len(agent_results)} agents failed — investigation aborted"
            logger.error(error_msg)
            self._error = error_msg
            raise RuntimeError(error_msg)

        # Pre-warm is now started inside run_agents_concurrent() after each phase
        # so it runs concurrently with the HITL decision windows. _run_deliberation
        # waits for the task and falls back to a synchronous pre-warm if needed.
        report = await self._run_deliberation(
            arbiter_results, case_id, session_id,
            artifact_mime=evidence_artifact.mime_type if evidence_artifact else "",
        )

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
            logger.error(
                "Report enrichment failed — report will lack custody chain verification",
                error=str(enrich_err),
            )
            self._degradation_flags.append(
                f"Report enrichment failed: {enrich_err}. Report may not be court-admissible without complete chain of custody."
            )

        # Add calibration status to degradation flags if uncalibrated
        if hasattr(report, "calibration_status") and report.calibration_status in ("UNCALIBRATED", "IDENTITY"):
            self._degradation_flags.append(
                f"Model calibration: {report.calibration_status} (scores may not be reliable for court submission)"
            )

        if self._degradation_flags:
            report.degradation_flags = list(self._degradation_flags)

        self._final_report = await self.arbiter.sign_report(report)

        await self.session_manager.set_final_report(
            session_id=session_id,
            report_id=self._final_report.report_id,
        )

        try:
            from api.routes._session_state import set_final_report as cache_report
            await cache_report(str(session_id), self._final_report)
        except Exception as cache_err:
            logger.warning("Failed to cache report in Redis", error=str(cache_err))

        await self._broadcast_final_arbiter_status(
            session_id,
            "complete",
            f"Council report ready: {self._final_report.overall_verdict}.",
        )

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

    async def _run_arbiter_pre_warm(self, agent_results: dict[str, Any], case_id: str, *, suppress_broadcasts: bool = False) -> None:
        """Background task to run arbiter pre-warm with UI broadcasting."""
        if not self.arbiter:
            return
        previous_suppression = self._suppress_arbiter_step_broadcasts
        self._suppress_arbiter_step_broadcasts = suppress_broadcasts or previous_suppression

        # F-5: snapshot the generation at start so we can detect if
        # invalidate_pre_warm() was called while deliberate() was running.
        _gen_at_start = self._pre_warm_gen

        try:
            if not suppress_broadcasts:
                from api.routes._session_state import broadcast_update
                from api.schemas import BriefUpdate

                # Initial broadcast: arbiter preparation started.
                await broadcast_update(
                    str(self._session_id),
                    BriefUpdate(
                        type="ARBITER_UPDATE",
                        session_id=str(self._session_id),
                        message="Preparing council evidence weights.",
                        data={"status": "pre_warming", "thinking": "Preparing council evidence weights."},
                    )
                )

            _mime = getattr(self, "_evidence_mime", "")
            # B6: Pre-warm always uses deterministic logic (use_llm=False) so
            # Groq tokens are not wasted while the investigator reviews initial
            # results. The final report path (finalise_from_cache) invokes LLM
            # refinement exactly once when needed.
            report = await self.arbiter.deliberate(agent_results, case_id, use_llm=False, artifact_mime=_mime)

            # F-5: invalidation gate — if invalidate_pre_warm() was called
            # while deliberate() was running (e.g. user chose deep analysis),
            # discard the now-stale results instead of poisoning the cache.
            if self._pre_warm_gen != _gen_at_start:
                logger.debug("Pre-warm results discarded — pre-warm was invalidated while deliberate() was in flight")
                return

            self.arbiter._pre_warm_report = report
            self.arbiter._pre_warm_agent_results = agent_results
            self.arbiter._pre_warm_case_id = case_id
            self.arbiter._pre_warm_used_llm = False  # B6: pre-warm is always deterministic

            # Reconcile the live per-agent cards to the arbiter-grounded verdict the
            # signed report will use (single source of truth). The card streams a
            # preliminary per-agent self-assessment; once the pre-warm deliberation
            # has produced the grounded, visual-context-aware verdicts, broadcast
            # them so the evidence page never shows a verdict/confidence that the
            # result page will contradict (e.g. a screening-tier signal the arbiter
            # grounds to AUTHENTIC). Emitted unconditionally — this reconciliation
            # must happen even when arbiter STEP broadcasts are suppressed.
            try:
                from api.routes._session_state import broadcast_update as _bcast
                from api.schemas import BriefUpdate as _BUpd

                # Tag the broadcast with the ACTUAL phase. The frontend drops
                # cross-phase messages (a deep-phase card won't accept an
                # "initial"-tagged update), so a hardcoded phase silently
                # discarded the deep reconciliation — the deep card stayed on its
                # ungrounded preliminary verdict. Derive deep vs initial from the
                # findings the pre-warm deliberated over.
                _pw_phase = (
                    "deep"
                    if any(
                        str((f.get("metadata") or {}).get("analysis_phase") or "").lower() == "deep"
                        for _r in (agent_results or {}).values()
                        if isinstance(_r, dict)
                        for f in (_r.get("findings") or [])
                    )
                    else "initial"
                )
                _pas = getattr(report, "per_agent_summary", {}) or {}
                for _aid, _summ in _pas.items():
                    if not isinstance(_summ, dict) or _summ.get("skipped"):
                        continue
                    _gv = _summ.get("verdict")
                    _gc = _summ.get("confidence_pct")
                    if _gv is None or _gc is None:
                        continue
                    await _bcast(
                        str(self._session_id),
                        _BUpd(
                            type="AGENT_GROUNDED",
                            session_id=str(self._session_id),
                            agent_id=_aid,
                            message="Grounded verdict reconciled.",
                            data={
                                "agent_verdict": _gv,
                                "confidence": float(_gc) / 100.0,
                                "analysis_phase": _pw_phase,
                            },
                        ),
                    )
            except Exception as _grounded_err:
                logger.debug("Grounded per-agent reconciliation broadcast skipped", error=str(_grounded_err))

            if not suppress_broadcasts:
                # Final pre-warm broadcast: metrics are ready for the user decision.
                await broadcast_update(
                    str(self._session_id),
                    BriefUpdate(
                        type="ARBITER_UPDATE",
                        session_id=str(self._session_id),
                        message="Council evidence weights are ready for your decision.",
                        data={"status": "pre_warm_complete", "thinking": "Council evidence weights are ready for your decision."},
                    )
                )
        except Exception as e:
            logger.warning(f"Arbiter pre-warm background task failed: {e}")
        finally:
            self._suppress_arbiter_step_broadcasts = previous_suppression

    def invalidate_pre_warm(self) -> None:
        """Clear speculative arbiter state (e.g. if deep analysis is requested)."""
        if self._pre_warm_task and not self._pre_warm_task.done():
            self._pre_warm_task.cancel()
        self._pre_warm_task = None
        self._pre_warm_gen += 1  # F-5: invalidate any in-flight deliberate() results
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
                    # Per-finding guard: a single malformed finding (e.g. a
                    # primitive or slotted object with no __dict__) must not
                    # abort normalization for ALL agents. Drop the bad one and
                    # continue rather than raising out of the whole investigation.
                    try:
                        if hasattr(f, "model_dump"):
                            normalized_findings.append(f.model_dump(mode="json"))
                        elif isinstance(f, dict):
                            normalized_findings.append(f)
                        else:
                            normalized_findings.append(vars(f))
                    except Exception as norm_err:
                        logger.warning(
                            "Dropping un-normalizable finding",
                            agent_id=result.agent_id,
                            finding_type=type(f).__name__,
                            error=str(norm_err),
                        )

            arbiter_results[result.agent_id] = {
                "findings": normalized_findings,
                "reflection_report": result.reflection_report,
                "react_chain": result.react_chain,
                "agent_had_error": result.error is not None,
                "synthesis": result.synthesis,
            }
        return arbiter_results

    async def _run_deliberation(
        self, arbiter_results: dict[str, Any], case_id: str, session_id: UUID, artifact_mime: str = ""
    ):
        """Run council arbiter deliberation with timeout and fallback."""
        logger.info("Running council arbiter deliberation")
        _start = time.perf_counter()
        # Final reports must always complete inside the worker deadline. Agent-level
        # synthesis still uses the configured LLM provider; the arbiter report uses
        # grounded deterministic synthesis to avoid a late provider stall blocking
        # the whole investigation after all tools have already finished.
        use_llm = self.config.final_report_llm_enabled

        # Preserve pre-warm if it matches the current arbiter results hash,
        # otherwise cancel and replace.
        _pre_warm_ok = False
        if self._pre_warm_task and not self._pre_warm_task.done():
            try:
                _cached = getattr(self.arbiter, "_pre_warm_agent_results", None)
                if _cached is not None:
                    import hashlib

                    _old_hash = hashlib.sha256(
                        str(sorted(_cached.items())).encode()
                    ).hexdigest()[:16]
                    _new_hash = hashlib.sha256(
                        str(sorted(arbiter_results.items())).encode()
                    ).hexdigest()[:16]
                    _pre_warm_ok = _old_hash == _new_hash
            except Exception:
                pass
        if not _pre_warm_ok:
            if self._pre_warm_task:
                self._pre_warm_task.cancel()
                self._pre_warm_task = None
            self.arbiter.clear_pre_warm_cache()
        self.arbiter._pre_warm_agent_results = arbiter_results
        self.arbiter._pre_warm_case_id = case_id

        try:
            await self._broadcast_final_arbiter_status(
                session_id,
                "deliberating",
                "Compiling final report from agent findings.",
            )
            report = await asyncio.wait_for(
                self.arbiter.finalise_from_cache(use_llm=use_llm, artifact_mime=artifact_mime),
                timeout=120.0,
            )
        except TimeoutError:
            logger.warning("arbiter.finalise_from_cache() timed out — falling back to template")
            if use_llm:
                self._degradation_flags.append(
                    "Arbiter LLM synthesis timed out — report generated from templates."
                )
            # Deterministic fallback must always finish; give it real headroom so a
            # CPU-contended deterministic build can't also time out and abort the run.
            report = await asyncio.wait_for(
                self.arbiter.finalise_from_cache(use_llm=False, artifact_mime=artifact_mime),
                timeout=90.0,
            )
        await self._broadcast_final_arbiter_status(
            session_id,
            "synthesizing",
            f"Council verdict selected: {report.overall_verdict}. Signing and caching the report.",
        )

        logger.info(
            "Arbiter deliberation complete",
            session_id=str(session_id),
            elapsed_seconds=round(time.perf_counter() - _start, 2),
            verdict=report.overall_verdict,
        )
        return report

    async def _broadcast_final_arbiter_status(
        self,
        session_id: UUID,
        status: str,
        thinking: str,
    ) -> None:
        """Broadcast clean arbiter progress text and cache it for polling clients."""
        try:
            from api.routes._session_state import (
                broadcast_update,
                update_active_pipeline_metadata,
            )
            from api.schemas import BriefUpdate

            await broadcast_update(
                str(session_id),
                BriefUpdate(
                    type="ARBITER_UPDATE",
                    session_id=str(session_id),
                    message=thinking,
                    data={"status": status, "thinking": thinking},
                ),
            )
            # F-15: use atomic CAS for metadata status transition.
            # NOTE: Do NOT set terminal status "completed" here — that is the
            # responsibility of mark_investigation_completed() in
            # session_finalization.py. Setting it here prematurely causes the
            # idempotency guard to fire, skipping the DB update and leaving
            # investigation_state stuck at "queued".
            await update_active_pipeline_metadata(
                str(session_id),
                {
                    "status": "report_ready" if status == "complete" else status,
                    "brief": thinking,
                    "awaiting_decision": False,
                },
            )
        except Exception as exc:
            logger.debug("Arbiter status broadcast skipped", error=str(exc))

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
        detected_mime: str | None = None,
        content_sha256: str | None = None,
        file_size_bytes: int | None = None,
    ):
        """Ingest evidence file and create artifact."""
        from core.observability import get_tracer

        _tracer = get_tracer("forensic-council.pipeline")
        with _tracer.start_as_current_span("pipeline.ingest_evidence") as span:
            span.set_attribute("file_path", file_path)
            span.set_attribute("session_id", str(session_id))
            file_path_obj = Path(file_path)

            mime_type = detected_mime or self._get_mime_type(file_path)

            # F-6: cross-validate detected MIME against PIL content detection.
            # If the extension-based or route-provided MIME contradicts the
            # file's actual content, trust PIL (content) and log the mismatch.
            _pil_mime = self._get_mime_type(file_path)
            if _pil_mime != "application/octet-stream" and mime_type != _pil_mime:
                logger.info(
                    "MIME mismatch corrected by content detection",
                    route_or_extension=mime_type, content_detected=_pil_mime, path=str(file_path_obj),
                )
                mime_type = _pil_mime

            metadata: dict[str, Any] = {
                "mime_type": mime_type,
                "original_filename": original_filename or file_path_obj.name,
            }
            if content_sha256:
                metadata["content_sha256"] = content_sha256
            if file_size_bytes:
                metadata["file_size_bytes"] = file_size_bytes

            if mime_type and mime_type.startswith("image/"):
                try:
                    from core.image_evidence_routing import (
                        build_image_agent_tool_plan,
                        build_image_evidence_profile,
                    )
                    profile = build_image_evidence_profile(
                        path=file_path,
                        original_filename=original_filename or file_path_obj.name,
                        mime_type=mime_type,
                    )
                    plan = build_image_agent_tool_plan(profile)
                    metadata["image_evidence_profile"] = profile.model_dump()
                    metadata["agent_tool_plan"] = plan
                except Exception as route_err:
                    logger.warning("Failed to construct image routing profile or tool plan", error=str(route_err))

            stored_artifact = await self.evidence_store.ingest(
                file_path=file_path,
                session_id=session_id,
                agent_id=investigator_id,
                metadata=metadata,
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

    @staticmethod
    def _pil_format_to_mime() -> dict[str, str]:
        return {
            "JPEG": "image/jpeg", "PNG": "image/png", "GIF": "image/gif",
            "WEBP": "image/webp", "TIFF": "image/tiff", "BMP": "image/bmp",
            "HEIF": "image/heic", "AVIF": "image/avif", "ICO": "image/x-icon",
            "PPM": "image/x-portable-pixmap", "PGM": "image/x-portable-graymap",
            "PBM": "image/x-portable-bitmap",
        }

    def _get_mime_type(self, file_path: str) -> str:
        """MIME detection: content-based (PIL) first, then extension-based fallback.

        F-6: content detection always takes priority so a file with a wrong
        extension (e.g. PNG renamed to .jpg) gets the correct MIME type.
        """
        _pil_map = self._pil_format_to_mime()
        try:
            from PIL import Image
            with Image.open(file_path) as _img:
                pil_format = (_img.format or "").upper()
            if pil_format in _pil_map:
                return _pil_map[pil_format]
        except Exception:
            pass

        import mimetypes
        mime, _ = mimetypes.guess_type(file_path)
        return mime or "application/octet-stream"
