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
import uuid
from functools import cached_property
from typing import Any

from agents.base_agent import ForensicAgent
from core.config import Settings
from core.custody_logger import CustodyLogger
from core.episodic_memory import EpisodicMemory
from core.evidence import EvidenceArtifact
from core.handlers.image import ImageHandlers
from core.handlers.metadata import MetadataHandlers
from core.handlers.video import VideoHandlers
from core.media_kind import is_digitally_created_image, is_screen_capture_like
from core.persistence.evidence_store import EvidenceStore
from core.react_loop import AgentFinding
from core.structured_logging import get_logger
from core.tool_registry import ToolRegistry
from core.working_memory import WorkingMemory

logger = get_logger(__name__)


class Agent5Metadata(ForensicAgent):
    """
    Agent 5 - Provenance & Metadata Agent.

    Mandate (STRICT): Provenance, metadata structure, and chronology ONLY.
    This is the court-defensible provenance specialist — narrow and deep.
    """

    persona: str = (
        "You are Dr. James Whitfield, a digital forensics examiner and court-certified expert witness "
        "with 18 years specializing in EXIF metadata provenance, timestamp chronology, compression "
        "platform fingerprinting, and C2PA chain-of-custody verification. Your findings are written "
        "for evidentiary use: you cite exact EXIF field names, hash values, and timestamp discrepancies. "
        "You flag when metadata has been stripped, re-embedded, or is inconsistent with claimed provenance. "
        "You never assert authenticity from metadata alone — you note what the data can and cannot prove."
    )

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
        heavy_tool_semaphore: asyncio.Semaphore | None = None,
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
            heavy_tool_semaphore=heavy_tool_semaphore,
        )
        self._agent1_context: dict = {}
        self._agent1_context_event: asyncio.Event = asyncio.Event()

    def inject_agent1_context(self, agent1_gemini_findings: dict) -> None:
        """Share Agent 1 Gemini vision findings with this agent instance."""
        self._agent1_context = agent1_gemini_findings or {}
        self._agent1_context_event.set()

    @cached_property
    def _is_digital_image(self) -> bool:
        return is_digitally_created_image(self.evidence_artifact)

    @cached_property
    def _is_screen_capture(self) -> bool:
        return is_screen_capture_like(self.evidence_artifact)

    @cached_property
    def _is_av_media(self) -> bool:
        mime = getattr(self.evidence_artifact, "mime_type", "") or ""
        file_path = getattr(self.evidence_artifact, "file_path", "").lower()
        return mime.startswith(("audio/", "video/")) or file_path.endswith(
            (
                ".mp4",
                ".avi",
                ".mov",
                ".mkv",
                ".webm",
                ".flv",
                ".wmv",
                ".m4v",
                ".mp3",
                ".wav",
                ".flac",
                ".ogg",
                ".aac",
                ".m4a",
            )
        )

    @cached_property
    def _is_image_media(self) -> bool:
        mime = (getattr(self.evidence_artifact, "mime_type", "") or "").lower()
        file_path = (getattr(self.evidence_artifact, "file_path", "") or "").lower()
        return mime.startswith("image/") or file_path.endswith(
            (
                ".jpg",
                ".jpeg",
                ".png",
                ".gif",
                ".bmp",
                ".tiff",
                ".tif",
                ".webp",
                ".heic",
                ".heif",
                ".dng",
                ".avif",
                ".raw",
            )
        )

    @cached_property
    def _is_document_media(self) -> bool:
        mime = (getattr(self.evidence_artifact, "mime_type", "") or "").lower()
        file_path = (getattr(self.evidence_artifact, "file_path", "") or "").lower()
        return mime in {
            "application/pdf",
            "text/plain",
            "text/csv",
            "application/msword",
            "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            "application/vnd.ms-excel",
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            "application/vnd.ms-powerpoint",
            "application/vnd.openxmlformats-officedocument.presentationml.presentation",
        } or file_path.endswith(
            (
                ".pdf",
                ".txt",
                ".csv",
                ".doc",
                ".docx",
                ".xls",
                ".xlsx",
                ".ppt",
                ".pptx",
            )
        )

    def _should_run_gemini_provenance(self) -> bool:
        """Gate Agent 5's Gemini call — only when cross-validation is high-value.

        Agent 5's Gemini prompt is a narrower GPS/timestamp/device provenance
        cross-validation, not the full 13-section forensic prompt. Only fire
        when there's data worth cross-validating or when Agent 1 flagged
        suspicion.
        """
        exif = self._tool_context.get("exif_extract", {}) or {}
        has_gps = bool(isinstance(exif, dict) and exif.get("gps_coordinates"))
        software = str(exif.get("software", "")).lower() if isinstance(exif, dict) else ""
        editing_tools = {"photoshop", "gimp", "lightroom", "picsart", "snapseed", "canva", "capcut"}
        has_editing_sw = any(tool in software for tool in editing_tools)
        # Read Agent 1 shared context for manipulation suspicion
        agent1_suspicious = False
        try:
            if self.inter_agent_bus:
                shared = self.inter_agent_bus.get_visual_profile(str(self.session_id)) or {}
                verdict = shared.get("metadata", {}).get("authenticity_verdict", "")
                agent1_suspicious = verdict in ("SUSPICIOUS", "LIKELY_MANIPULATED")
        except Exception:
            pass
        return has_gps or has_editing_sw or agent1_suspicious

    @property
    def agent_name(self) -> str:
        return "Agent5_MetadataContext"

    @property
    def task_decomposition(self) -> list[str]:
        from core.image_evidence_routing import get_agent_plan
        # Agent5 is the document content + provenance authority (no separate document
        # agent). Documents get the native content analysis (AI-generated-text +
        # tampering determination, via the shared preflight profile) plus text
        # extraction, ahead of the structural/provenance checks.
        if self._is_document_media:
            return [
                "Run read_shared_image_context to incorporate the native document content analysis (AI-generated-text and document-tampering determination)",
                "Run extract_text_from_image for document text extraction",
                "Run ai_text_detector for AI-generated-text statistical screening",
                "Run file_hash_verify against ingestion hash",
                "Run file_structure_analysis for binary anomalies in headers and trailers",
                "Run hex_signature_scan for raw-byte software signatures",
                "Run timestamp_analysis for filesystem chronology consistency",
            ]
        plan = get_agent_plan(self.evidence_artifact, self.agent_id, phase="initial")
        if plan:
            return plan

        # Fallback logic
        if self._is_av_media:
            return [
                "Run file_hash_verify against ingestion hash",
                "Run file_structure_analysis for binary anomalies in headers and trailers",
                "Run hex_signature_scan for raw-byte software signatures",
                "Run av_file_identity for AV container identity pre-screen",
                "Run mediainfo_profile for stream and codec provenance",
            ]

        if not self._is_image_media:
            tasks = [
                "Run file_hash_verify against ingestion hash",
                "Run file_structure_analysis for binary anomalies in headers and trailers",
                "Run hex_signature_scan for raw-byte software signatures",
                "Run compression_risk_audit to check for social media footprints",
                "Run timestamp_analysis for filesystem chronology consistency",
            ]
            if self._is_document_media:
                tasks.insert(1, "Run extract_text_from_image for document text extraction")
            return tasks

        core_tasks = [
            "Run file_hash_verify against ingestion hash",
            "Run exif_extract to capture all metadata fields",
            "Run file_structure_analysis for binary anomalies in headers and trailers",
            "Run hex_signature_scan for raw-byte software signatures",
            "Run compression_risk_audit to check for social media footprints",
        ]
        if self._is_screen_capture or self._is_digital_image:
            # For screenshots: fast integrity + binary checks only.
            # Agent 1 already handles OCR (extract_text_from_image) and semantic analysis.
            # timestamp_analysis deferred to deep pass (screenshots rarely have meaningful EXIF timestamps).
            return [
                "Run file_hash_verify against ingestion hash",
                "Run exif_extract to record screenshot container metadata and software hints",
                "Run hex_signature_scan for raw-byte software signatures",
                "Run compression_risk_audit to check for social media footprints",
                "Run file_structure_analysis for binary anomalies in headers and trailers",
            ]

        # exif_isolation_forest moved to Phase 2 — Phase 1 should be fast screening only
        return core_tasks + [
            "Run timestamp_analysis for cross-field date and time consistency",
        ]

    @property
    def deep_task_decomposition(self) -> list[str]:
        from core.image_evidence_routing import get_agent_plan
        plan = get_agent_plan(self.evidence_artifact, self.agent_id, phase="deep")
        if plan:
            return plan

        # Fallback logic
        if self._is_screen_capture or self._is_digital_image:
            return [
                "Run timestamp_analysis for cross-field date and time consistency",
                "Run provenance_chain_verify for C2PA and digital provenance manifests",
                "Read shared image context for screenshot timestamp and provenance cross-check",
            ]
        if self._is_document_media:
            # Re-ground deep in the native document determination so the deep
            # verdict can't regress below initial (keeps AI-text / tampering live).
            return [
                "Run read_shared_image_context to incorporate the native document content analysis (AI-generated-text and document-tampering determination)",
                "Run metadata_anomaly_score for probabilistic fabrication detection",
                "Run provenance_chain_verify for C2PA and digital provenance manifests",
            ]
        if self._is_av_media:
            return [
                "Run provenance_chain_verify for C2PA and digital provenance manifests",
            ]
        if not self._is_image_media:
            return [
                "Run provenance_chain_verify for C2PA and digital provenance manifests",
            ]
        # exif_isolation_forest moved from Phase 1 (heavy ML — belongs in deep pass)
        tasks = [
            "Run metadata_anomaly_score for probabilistic fabrication detection",
            "Run exif_isolation_forest for ML-based field outlier detection",
            "Run provenance_chain_verify for C2PA and digital provenance manifests",
        ]
        # camera_profile_match only if camera make is known from Phase 1 EXIF
        exif = self._tool_context.get("exif_extract", {}) or {}
        if isinstance(exif, dict) and exif.get("camera_make"):
            tasks.append("Run camera_profile_match against claimed device model")
        # GPS-dependent tools only if GPS coordinates are present
        if isinstance(exif, dict) and exif.get("gps_coordinates"):
            tasks.append("Run astro_grounding to verify shadow-sun-gps-time parity")
            tasks.append("Run gps_timezone_validate for coordinate-timezone timeline cross-check")
        # Agent 1's visual profile is reused when Phase 1 EXIF detected editing
        # software, GPS data is present, or Agent 1 flagged suspicion.
        if self._should_run_gemini_provenance():
            tasks.append("Read shared image context for GPS/Timestamp/Device Provenance Cross-Validation")
        return tasks

    @property
    def iteration_ceiling(self) -> int:
        # Include both initial and deep tasks to prevent truncation of the forensic pipeline.
        base_count = len(self.task_decomposition) + len(self.deep_task_decomposition)
        return self._compute_ceiling(base_count)

    async def build_initial_thought(self) -> str:
        return (
            f"Starting provenance and binary-integrity analysis for {self.evidence_artifact.artifact_id}. "
            f"I will perform a deep bitstream audit to hunt for chimeric file structures, "
            f"hidden editor signatures in the trailer, and EXIF/GPS inconsistencies. "
            f"My goal is to determine if the file's provenance matches its claimed technical origin."
        )

    async def build_tool_registry(self) -> ToolRegistry:
        registry = ToolRegistry()

        # ── Domain Handlers (Decentralized) ──────────────────────────────────
        metadata_h = MetadataHandlers(self)
        registry.register_domain_handler(metadata_h)

        # AV Container Profiling (reusing Video domain) — only for AV media
        if self._is_av_media:
            video_h = VideoHandlers(self)
            registry.register(
                "mediainfo_profile",
                video_h.mediainfo_profile_handler,
                "Deep AV container profiling",
            )
            registry.register(
                "av_file_identity", video_h.av_file_identity_handler, "Lightweight AV pre-screen"
            )

        # ── Shared Agent 1 Visual Profile Reader ──────────────────────────────
        async def read_shared_image_context_handler(input_data: dict) -> dict:
            async def _visual_profile_signal_callback(msg: str):
                """Signal callback for early hand-off to Arbiter."""
                if self.inter_agent_bus:
                    exif = self._tool_context.get("exif_extract", {})
                    self.inter_agent_bus.signal_event(
                        self.session_id,
                        "agent5_initial_signal",
                        {"progress": msg, "has_gps": bool(exif.get("gps_coordinates"))},
                    )

            return await self._visual_evidence_profile_handler(
                input_data, signal_callback=_visual_profile_signal_callback
            )

        registry.register(
            "read_shared_image_context",
            read_shared_image_context_handler,
            "Read Agent 1 visual evidence profile for provenance grounding",
        )

        # ── OCR (for screenshot timestamp extraction) ─────────────────────────
        image_h = ImageHandlers(self)
        registry.register(
            "extract_text_from_image",
            image_h.extract_text_from_image_handler,
            "Tiered OCR for displayed metadata extraction",
        )
        registry.register(
            "extract_evidence_text",
            image_h.extract_text_from_image_handler,
            "Alias for extract_text_from_image (document text extraction)",
        )

        return registry

    def _visual_profile(self) -> dict:
        """Return the shared visual context dict from _tool_context or inter_agent_bus."""
        ctx = getattr(self, "_tool_context", {}) or {}
        profile = ctx.get("visual_evidence_profile") or ctx.get("read_shared_image_context") or {}
        if not profile and self.inter_agent_bus:
            try:
                profile = self.inter_agent_bus.get_visual_profile(str(self.session_id)) or {}
            except Exception:
                pass
        if hasattr(profile, "to_finding_dict"):
            profile = profile.to_finding_dict()
        return profile if isinstance(profile, dict) else {}

    async def on_tool_result(self, finding: AgentFinding) -> None:
        """Reactive task expansion based on metadata signals."""
        try:
            await self._on_tool_result_impl(finding)
        except Exception as e:
            logger.warning("on_tool_result failed", agent_id=self.agent_id, error=str(e))

    async def _on_tool_result_impl(self, finding: AgentFinding) -> None:
        """Pure Python adaptive rules — zero LLM calls."""
        tool_name = finding.metadata.get("tool_name")

        # ── Rule 1: EXIF extraction results ───────────────────────────────
        if tool_name == "exif_extract":
            software = str(finding.metadata.get("software", "")).lower()
            has_gps = bool(
                finding.metadata.get("gps_coordinates")
                or finding.metadata.get("gps_location")
                or finding.metadata.get("latitude")
            )
            has_timestamp = bool(
                finding.metadata.get("datetime_original")
                or finding.metadata.get("date_time")
                or finding.metadata.get("capture_time")
            )
            exif_empty = finding.evidence_verdict == "NOT_APPLICABLE" or (
                not finding.metadata.get("fields_extracted")
                and not has_gps
                and not has_timestamp
                and not software
            )

            # 1a. Editing software signature → hex-level structure audit
            editing_tools = {"photoshop", "gimp", "lightroom", "picsart", "snapseed", "canva", "capcut"}
            if any(t in software for t in editing_tools):
                logger.info(
                    f"Editing software detected: {software}; injecting structure audit",
                    agent_id=self.agent_id,
                )
                await self.inject_task(
                    description="Run file_structure_analysis for hidden hex-level manipulation artifacts",
                    priority=15,
                )

            # 1b. GPS coordinates present → validate against timezone and sun position
            if has_gps:
                logger.info("GPS coordinates in EXIF — injecting timezone and astronomical validation",
                    agent_id=self.agent_id)
                await self.inject_task(
                    description="Run gps_timezone_validate to cross-check GPS location against EXIF timezone",
                    priority=14,
                )
                if has_timestamp:
                    await self.inject_task(
                        description="Run astro_grounding to validate sun position against GPS and timestamp",
                        priority=12,
                    )

            # 1c. Cross-modal conflict: EXIF claims camera origin but visual context says screenshot
            profile = self._visual_profile()
            file_type = str(profile.get("file_type_assessment") or "").lower()
            content_desc = str(profile.get("content_description") or "").lower()
            visual_is_screenshot = any(
                t in file_type or t in content_desc
                for t in ("screenshot", "screen capture", "digital ui", "web page")
            )
            camera_exif_keys = {"camera_make", "camera_model", "focal_length", "aperture", "iso"}
            has_camera_exif = any(finding.metadata.get(k) for k in camera_exif_keys)

            if visual_is_screenshot and has_camera_exif:
                logger.info(
                    "Cross-modal conflict: EXIF claims camera origin but visual context confirms screenshot "
                    "— injecting isolation forest at critical priority",
                    agent_id=self.agent_id,
                )
                await self.inject_task(
                    description="Run exif_isolation_forest for metadata fabrication pattern detection",
                    priority=20,
                )

            # 1d. Completely stripped EXIF on image that should have metadata → hex scan
            if exif_empty and not visual_is_screenshot:
                logger.info(
                    "EXIF absent on non-screenshot image — possible metadata stripping; injecting hex scan",
                    agent_id=self.agent_id,
                )
                await self.inject_task(
                    description="Run hex_signature_scan to detect stripped or overwritten metadata signatures",
                    priority=16,
                )

        # ── Rule 2: Metadata anomaly score ────────────────────────────────
        if tool_name == "metadata_anomaly_score":
            if finding.evidence_verdict == "POSITIVE" and (finding.confidence_raw or 0.0) > 0.7:
                logger.info(
                    "High metadata anomaly score — injecting provenance and timestamp audits",
                    agent_id=self.agent_id,
                )
                await self.inject_task(
                    description="Run provenance_chain_verify for C2PA/JUMBF integrity check",
                    priority=10,
                )
                await self.inject_task(
                    description="Run timestamp_analysis for chronology consistency cross-check",
                    priority=11,
                )
                await self.inject_task(
                    description="Read shared image context for Hardware-Grounded Provenance Verification",
                    priority=8,
                )

        # ── Rule 3: GPS timezone mismatch → escalate to astronomical check ─
        if tool_name == "gps_timezone_validate":
            if finding.evidence_verdict == "POSITIVE" or finding.metadata.get("timezone_mismatch"):
                logger.info(
                    "GPS/timezone mismatch confirmed — injecting astronomical sun-position check",
                    agent_id=self.agent_id,
                )
                await self.inject_task(
                    description="Run astro_grounding to validate sun position against claimed GPS and timestamp",
                    priority=14,
                )

        # ── Rule 4: EXIF isolation forest POSITIVE → C2PA verification ────
        if tool_name == "exif_isolation_forest":
            if finding.evidence_verdict == "POSITIVE" and (finding.confidence_raw or 0.0) > 0.65:
                logger.info(
                    "EXIF isolation forest flagged fabrication patterns — injecting C2PA check",
                    agent_id=self.agent_id,
                )
                await self.inject_task(
                    description="Run c2pa_verify for cryptographic content authenticity verification",
                    priority=18,
                )
