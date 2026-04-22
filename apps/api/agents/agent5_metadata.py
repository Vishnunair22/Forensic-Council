"""
Agent 5 - Provenance & Metadata Agent.

MANDATE (strict): Provenance, metadata structure, and chronology ONLY.
Analyzes EXIF metadata, GPS-timestamp consistency, file structure
integrity, C2PA provenance, and device fingerprint validation.

Does NOT perform steganography analysis as a primary tool (LSB
scan is registered but carries low reliability weight in the
arbiter). This agent produces court-defensible provenance findings
by staying narrow and deep.
"""

from __future__ import annotations

import asyncio

from agents.base_agent import ForensicAgent
from core.gemini_client import GeminiVisionClient
from core.handlers.metadata import MetadataHandlers
from core.handlers.video import VideoHandlers
from core.structured_logging import get_logger
from core.tool_registry import ToolRegistry

import uuid
from typing import Any
from core.config import Settings
from core.custody_logger import CustodyLogger
from core.episodic_memory import EpisodicMemory
from core.evidence import EvidenceArtifact
from core.persistence.evidence_store import EvidenceStore
from core.working_memory import WorkingMemory

logger = get_logger(__name__)

class Agent5Metadata(ForensicAgent):
    """
    Agent 5 - Provenance & Metadata Agent.

    Mandate (STRICT): Provenance, metadata structure, and chronology ONLY.
    This is the court-defensible provenance specialist — narrow and deep.
    """

    def inject_agent1_context(self, agent1_gemini_findings: dict) -> None:
        """Share Agent 1 Gemini vision findings with this agent instance."""
        self._agent1_context = agent1_gemini_findings or {}

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
        inter_agent_bus: Any | None = None,
    ) -> None:
        super().__init__(
            agent_id=agent_id,
            session_id=session_id,
            evidence_artifact=evidence_artifact,
            config=config,
            working_memory=working_memory,
            episodic_memory=episodic_memory,
            custody_logger=custody_logger,
            evidence_store=evidence_store,
            inter_agent_bus=inter_agent_bus,
        )
        self._agent1_context: dict = {}
        self._agent1_context_event: asyncio.Event | None = None

    @property
    def agent_name(self) -> str:
        return "Agent5_MetadataContext"

    @property
    def task_decomposition(self) -> list[str]:
        # PHASE 1: INITIAL ANALYSIS (Neural Refined)
        return [
            "Run file_hash_verify against ingestion hash",
            "Run exif_extract to capture all metadata fields",
            "Run compression_risk_audit to check for social media footprints",
            "Run exif_isolation_forest for ML-based field outlier detection",
            "Run astro_grounding to verify shadow-sun-gps-time parity",
            "Run gps_timezone_validate for coordinate timeline checking",
            "Run timestamp_analysis for cross-field date and time consistency",
        ]

    @property
    def deep_task_decomposition(self) -> list[str]:
        return [
            "Run file_structure_analysis for binary anomalies",
            "Run hex_signature_scan on raw bytes",
            "Run metadata_anomaly_score for probabilistic fabrication detection",
            "Run provenance_chain_verify for C2PA and digital provenance manifests",
            "Run camera_profile_match against claimed device model",
            "Run gemini_deep_forensic for Hardware-Grounded Provenance Verification",
        ]

    @property
    def iteration_ceiling(self) -> int:
        return self._compute_ceiling(len(self.task_decomposition))

    async def build_initial_thought(self) -> str:
        return (
            f"Starting metadata and context analysis for {self.evidence_artifact.artifact_id}. "
            f"I will extract all available EXIF data, validate GPS-timestamp consistency, "
            f"and analyze the file structure for any signs of fabrication or steganography."
        )

    @property
    def supported_file_types(self) -> list[str]:
        # Agent 5 is a universal analyst
        return ["*"]

    async def build_tool_registry(self) -> ToolRegistry:
        registry = ToolRegistry()

        # ── Domain Handlers (Decentralized) ──────────────────────────────────
        metadata_h = MetadataHandlers(self)
        registry.register_domain_handler(metadata_h)

        # AV Container Profiling (reusing Video domain) — only for video files
        _mime = getattr(self.evidence_artifact, "mime_type", "") or ""
        _fp = getattr(self.evidence_artifact, "file_path", "").lower()
        _is_av = _mime.startswith("video/") or _mime.startswith("audio/") or any(
            _fp.endswith(ext) for ext in (".mp4", ".avi", ".mov", ".mkv", ".webm", ".flv", ".wmv", ".m4v", ".mp3", ".wav", ".flac", ".ogg", ".aac", ".m4a")
        )
        if _is_av:
            video_h = VideoHandlers(self)
            registry.register("mediainfo_profile", video_h.mediainfo_profile_handler, "Deep AV container profiling")
            registry.register("av_file_identity", video_h.av_file_identity_handler, "Lightweight AV pre-screen")

        # Gemini deep forensic analysis
        _gemini = GeminiVisionClient(self.config)

        async def _gemini_signal_callback(msg: str):
            """Signal callback for early hand-off to Arbiter."""
            if self.inter_agent_bus:
                # Signal coordinates for geospatial grounding
                exif = self._tool_context.get("exif_extract", {})
                self.inter_agent_bus.signal_event(
                    self.session_id,
                    "agent5_initial_signal",
                    {"progress": msg, "has_gps": bool(exif.get("gps_coordinates"))}
                )

        async def gemini_deep_forensic_handler(input_data: dict) -> dict:
            artifact = input_data.get("artifact") or self.evidence_artifact

            # Wait for Agent1 context
            _ctx_event = getattr(self, "_agent1_context_event", None)
            if _ctx_event is not None and not _ctx_event.is_set():
                try:
                    await asyncio.wait_for(asyncio.shield(_ctx_event.wait()), timeout=60.0)
                except TimeoutError:
                    logger.warning(f"{self.agent_id}: Agent1 context wait timed out after 60s — proceeding without image-integrity context")
                    await self._record_tool_error(
                        "agent1_context_sync",
                        "Agent1 Gemini context unavailable (60s timeout) — metadata provenance analysis may lack image-integrity grounding",
                    )

            # Audit Fix: DYNAMIC CONTEXT AGGREGATION
            # Collect all successful tool results to ensure no blindspots (C2PA, Astro, Stego)
            dynamic_context = {}
            for tool_name, result in self._tool_context.items():
                if not isinstance(result, dict):
                    continue
                if result.get("error"):
                    # Skip error results in provenance synthesis
                    continue

                # Extract high-value forensic keys for Gemini
                dynamic_context[tool_name] = {
                    k: v for k, v in result.items()
                    if k not in ("exif_raw", "artifact", "error")
                }

            # Add Agent1 context if available
            a1 = getattr(self, "_agent1_context", {})
            context_summary = {"tools": dynamic_context, "agent1": a1}

            try:
                await self.update_sub_task("Synthesizing provenance and custody verdict...")
                finding = await _gemini.deep_forensic_analysis(
                    file_path=artifact.file_path,
                    exif_summary=context_summary,
                    signal_callback=_gemini_signal_callback
                )
            except Exception as e:
                await self._record_tool_error("gemini_deep_forensic", str(e))
                return {
                    "error": str(e),
                    "analysis_source": "gemini_vision",
                    "available": False,
                    "court_defensible": False,
                    "confidence": 0.0,
                }

            result = finding.to_finding_dict(self.agent_id)
            result["analysis_source"] = "gemini_vision"
            await self._record_tool_result("gemini_deep_forensic", result)
            return result

        registry.register("gemini_deep_forensic", gemini_deep_forensic_handler, "Gemini deep forensic analysis")

        return registry
