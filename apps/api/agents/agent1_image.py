"""
Agent 1 — Pixel Integrity Agent.

Pixel-level forensic expert for detecting manipulation, splicing,
compositing, and AI-generation traces.

MANDATE (strict): Pixel integrity and AI-generation detection ONLY.
Does NOT perform object detection, metadata analysis, audio analysis,
or video temporal analysis — those belong to Agents 3, 5, 2, and 4
respectively.

Phase 1 (initial, fast): CLIP semantic classification, Gemini/EasyOCR text extraction,
  SigLIP2 neural fingerprint, SHA-256 integrity check, FFT frequency scan,
  and either ViT Neural ELA (JPEG) or Noiseprint++ sensor clustering (lossless).

Phase 2 (deep, neural): TruFor splicing, BusterNet copy-move, diffusion
  artifact detection, F3-Net frequency, ManTra-Net anomaly tracing (gated),
  and Gemini visual forensic synthesis for evidence aggregation.
"""

from __future__ import annotations

import os
from functools import cached_property

from agents.base_agent import ForensicAgent
from core.handlers.image import ImageHandlers
from core.handlers.metadata import MetadataHandlers
from core.image_utils import is_lossless_image
from core.media_kind import (
    is_camera_still_candidate,
    is_digitally_created_image,
    is_screen_capture_like,
    is_document_like,
    is_recompressed_web_image,
)
from core.react_loop import AgentFinding
from core.structured_logging import get_logger
from core.tool_names import TOOL_GEMINI_DEEP, TOOL_VISUAL_PROFILE
from core.tool_registry import ToolRegistry

logger = get_logger(__name__)


class Agent1Image(ForensicAgent):
    """
    Agent 1 — Pixel Integrity Agent.

    Mandate (STRICT): Pixel integrity and AI-generation traces ONLY.
    This agent does NOT perform object detection, metadata analysis,
    audio analysis, or video temporal analysis.
    """

    persona: str = (
        "You are Dr. Maya Reyes, a 15-year forensic image integrity examiner with the FBI Digital Evidence Lab. "
        "You specialize in JPEG re-compression analysis, sensor PRNU patterns, neural model artifacts, and "
        "GAN/Diffusion provenance traces. You report only what your tools measured. You never speculate beyond "
        "the data. You explicitly mark fallback heuristics as such. You write 2-3 sentence verdicts that a "
        "non-technical jury can understand. You always cite at least one specific metric in your verdict."
    )

    @property
    def agent_name(self) -> str:
        return "Agent1_ImageIntegrity"

    @cached_property
    def _is_lossless(self) -> bool:
        """Cached: whether the evidence file is a lossless image format."""
        file_path = getattr(self.evidence_artifact, "file_path", "") or ""
        mime = getattr(self.evidence_artifact, "mime_type", "") or ""
        return is_lossless_image(file_path, mime or None)

    @cached_property
    def _is_screen_capture(self) -> bool:
        """Cached: whether the evidence looks like a screenshot/digital capture."""
        return is_screen_capture_like(self.evidence_artifact)

    @cached_property
    def _is_digital_capture(self) -> bool:
        """Cached: whether the evidence is a non-camera digital image container."""
        return is_digitally_created_image(self.evidence_artifact)

    @cached_property
    def _is_document(self) -> bool:
        """Cached: whether the image is classified as a document/scanned text."""
        return is_document_like(self.evidence_artifact)

    @cached_property
    def _is_recompressed_web(self) -> bool:
        """Cached: whether the image is a recompressed web download."""
        return is_recompressed_web_image(self.evidence_artifact)

    @cached_property
    def _is_camera(self) -> bool:
        """Cached: whether the image originates from a camera (has camera EXIF tags)."""
        return is_camera_still_candidate(self.evidence_artifact)

    @property
    def iteration_ceiling(self) -> int:
        # Include both initial and deep tasks to prevent truncation of the forensic pipeline.
        base_count = len(self.task_decomposition) + len(self.deep_task_decomposition)
        return self._compute_ceiling(base_count)

    @property
    def task_decomposition(self) -> list[str]:
        """
        Phase 1 — Initial Analysis (fast, runs on every image).

        Ordered by forensic signal value: primary manipulation detectors run
        first so the investigator sees high-confidence findings early.
        Cheap context tools (CLIP, OCR, FFT) follow.

        Design rules:
          - visual_evidence_profile runs once at the beginning as the session-wide
            visual evidence profile. In local_only mode it is produced exclusively by
            the local visual ensemble; in hybrid mode it may be produced by a configured
            provider.
          - extract_text_from_image is only useful for documents (scanned text)
            and screenshots (UI text) — OCR on camera photos or web downloads
            wastes a task slot. It is reactively injected by _on_tool_result_impl
            when analyze_image_content detects handwritten content.
          - Camera JPEGs get a dedicated branch (5 tools) instead of falling
            through to the generic lossy/JPEG default.
        """
        if self._is_document:
            return [
                "Run file_hash_verify for evidence integrity check",
                "Run visual_evidence_profile for visual evidence profile and forensic routing hints",
                "Run extract_text_from_image for OCR and document content identification",
                "Run analyze_image_content for semantic document classification",
                "Run frequency_domain_analysis for frequency domain analysis",
                "Run neural_ela for JPEG manipulation detection",
                "Run neural_fingerprint for conceptual similarity detection",
            ]
        if self._is_recompressed_web:
            # jpeg_ghost_detect and ela_full_image removed from base — reactively
            # injected by _reason_step when ELA/FFT disagree (no coverage lost).
            return [
                "Run file_hash_verify for evidence integrity check",
                "Run visual_evidence_profile for visual evidence profile and forensic routing hints",
                "Run neural_ela for high-confidence manipulation detection",
                "Run neural_fingerprint for conceptual similarity detection",
                "Run analyze_image_content for semantic image understanding",
                "Run frequency_domain_analysis for frequency domain analysis",
            ]
        if self._is_screen_capture or self._is_digital_capture:
            # Screenshots: hash integrity → OCR (primary signal for UI) → semantic →
            # frequency scan. neural_fingerprint deferred to deep — conceptual similarity
            # is less informative for screenshots which are inherently unique UI states.
            # The shared visual evidence profile remains the primary routing context.
            return [
                "Run file_hash_verify for evidence integrity check",
                "Run visual_evidence_profile for visual evidence profile and forensic routing hints",
                "Run extract_text_from_image for visible text extraction",
                "Run analyze_image_content for semantic image understanding",
                "Run frequency_domain_analysis for frequency domain analysis",
            ]
        if self._is_lossless:
            # Lossless: noiseprint sensor clustering is the primary manipulation signal.
            # neural_fingerprint → CLIP context → FFT supporting.
            return [
                "Run file_hash_verify for evidence integrity check",
                "Run visual_evidence_profile for visual evidence profile and forensic routing hints",
                "Run noiseprint_cluster for sensor-region source inconsistency",
                "Run neural_fingerprint for conceptual similarity detection",
                "Run analyze_image_content for semantic image understanding",
                "Run frequency_domain_analysis for frequency domain analysis",
            ]
        if self._is_camera:
            # Camera JPEGs: neural ELA is the primary manipulation detector.
            # No Gemini or OCR in Phase 1 — they are expensive and low-value
            # for natural photos. OCR is reactively injected if text is found.
            return [
                "Run file_hash_verify for evidence integrity check",
                "Run visual_evidence_profile for visual evidence profile and forensic routing hints",
                "Run neural_ela for high-confidence manipulation detection",
                "Run neural_fingerprint for conceptual similarity detection",
                "Run analyze_image_content for semantic image understanding",
                "Run frequency_domain_analysis for frequency domain analysis",
            ]
        # Lossy/JPEG fallback: Neural ELA is the primary manipulation signal.
        # No Gemini or OCR — same reasoning as camera branch.
        return [
            "Run file_hash_verify for evidence integrity check",
            "Run visual_evidence_profile for visual evidence profile and forensic routing hints",
            "Run neural_ela for high-confidence manipulation detection",
            "Run neural_fingerprint for conceptual similarity detection",
            "Run analyze_image_content for semantic image understanding",
            "Run frequency_domain_analysis for frequency domain analysis",
        ]

    @property
    def deep_task_decomposition(self) -> list[str]:
        """
        Phase 2 — Deep Neural Forensics (heavy, runs in background after Phase 1).

        Tools are ordered by signal-to-cost ratio: fast high-signal tools first
        so the UI shows progress and the agent can gate expensive tools early.

        Gating:
          - anomaly_tracer (ManTra-Net) — only fires when Phase-1 or earlier
            Phase-2 tools reported a tampering signal.
          - adversarial_robustness_check — only when splicing/copy-move confirmed.
        """
        if self._is_screen_capture or self._is_digital_capture:
            # Gemini already ran in Phase 1 for screenshots — result is in shared
            # context for Agents 3/5. Phase 2 uses classical ML tools exclusively.
            # Deepfake detection is included because modern deepfakes are often
            # shared as screenshots of videos or generated content.
            return [
                "Run neural_fingerprint for conceptual similarity detection",
                "Run f3_net_frequency for AI-GAN artifact detection",
                "Run deepfake_frequency_check for GAN/Diffusion artifacts",
                "Run diffusion_artifact_detector for AI-generation signatures",
                "Run synthid_watermark_detect for SynthID and AI watermark detection",
            ]

        # Natural photos: fast high-signal tools first, heavy tools later
        tasks = [
            "Run diffusion_artifact_detector for AI-generation signatures",
            "Run synthid_watermark_detect for SynthID and AI watermark detection",
            "Run f3_net_frequency for AI-GAN artifact detection",
            "Run neural_splicing for ViT-based region composition analysis",
            "Run neural_copy_move for dual-branch copy-move detection",
        ]
        # anomaly_tracer relies heavily on JPEG noise/ghosts — skip for lossless
        if not self._is_lossless:
            tasks.append("Run anomaly_tracer for ManTra-Net universal anomaly tracing")
        # adversarial_robustness_check removed from base — injected reactively in
        # _reason_step when neural_splicing or neural_copy_move returns POSITIVE.
        # Gemini removed from Phase 2 — Phase 1 result in shared context.
        return tasks

    @property
    def supported_file_types(self) -> list[str]:
        return ["image/"]

    async def build_tool_registry(self) -> ToolRegistry:
        registry = ToolRegistry()

        # ── Domain Handlers (Phase 1 + Phase 2 neural tools) ─────────────────
        # Audit Fix: ImageHandlers now also provides analyze_image_content,
        # extract_text_from_image (unified), and frequency_domain_analysis.
        registry.register_domain_handler(ImageHandlers(self))

        # ── Hash verification (from metadata domain) ──────────────────────────
        metadata_h = MetadataHandlers(self)
        registry.register(
            "file_hash_verify",
            metadata_h.file_hash_verify_handler,
            "SHA-256 hash verification against ingestion record",
        )


        # ── Shared Visual Evidence Profile Handler ─────────────────────────────
        async def visual_evidence_profile_handler(input_data: dict) -> dict:
            async def _signal_cb(msg: str) -> None:
                """Relay visual-profile progress to the inter-agent bus."""
                try:
                    if self.inter_agent_bus:
                        self.inter_agent_bus.signal_event(
                            self.session_id,
                            "agent1_visual_profile_signal",
                            {"progress": msg},
                        )
                except Exception as exc:
                    logger.debug(
                        f"{self.agent_id}: Visual profile signal relay failed",
                        error=str(exc),
                    )

            result = await self._visual_evidence_profile_handler(
                input_data,
                signal_callback=_signal_cb,
            )

            if result and not result.get("error"):
                try:
                    if self.inter_agent_bus:
                        self.inter_agent_bus.set_image_context(
                            str(self.session_id),
                            result,
                        )
                except Exception as ctx_err:
                    logger.debug(
                        f"{self.agent_id}: Failed to store shared image context",
                        error=str(ctx_err),
                    )

            # Dynamic content-aware tool gating using forensic_routing.
            try:
                metadata = result.get("metadata", {}) or {}
                routing = metadata.get("forensic_routing", {}) or {}
                skip_tools = [
                    str(tool).lower().replace("_", "")
                    for tool in routing.get("skip_tools", [])
                ]

                if skip_tools:
                    state = await self.working_memory.get_state(
                        self.session_id,
                        self.agent_id,
                    )
                    updated_tasks = []

                    for task in state.tasks:
                        matched_tool = None
                        for name in registry.handlers.keys():
                            if name in task.description:
                                matched_tool = name
                                break

                        if matched_tool:
                            normalized = matched_tool.lower().replace("_", "")
                            if normalized in skip_tools:
                                logger.info(
                                    "Dynamically skipping tool based on forensic routing",
                                    agent_id=self.agent_id,
                                    tool_name=matched_tool,
                                )
                                task.status = "COMPLETE"
                                task.result_ref = "skipped_by_forensic_routing"
                                task.sub_task_info = (
                                    "Skipped by content-aware forensic routing"
                                )

                        updated_tasks.append(task)

                    await self.working_memory.update_state(
                        self.session_id,
                        self.agent_id,
                        {"tasks": [task.model_dump() for task in updated_tasks]},
                    )
            except Exception as exc:
                logger.warning(
                    "Error applying visual-profile routing",
                    agent_id=self.agent_id,
                    error=str(exc),
                )

            return result

        registry.register(
            TOOL_VISUAL_PROFILE,
            visual_evidence_profile_handler,
            "Shared visual evidence profile and forensic routing context",
        )

        # Compatibility alias for old persisted task descriptions only.
        registry.register(
            TOOL_GEMINI_DEEP,
            visual_evidence_profile_handler,
            "Deprecated alias for shared visual evidence profile",
        )

        # ── SynthID / AI Watermark Detection ─────────────────────────────────
        async def synthid_watermark_handler(input_data: dict) -> dict:
            from core.ml_subprocess import run_ml_script_subprocess
            file_path = str(getattr(self.evidence_artifact, "file_path", ""))
            try:
                result = await run_ml_script_subprocess(
                    script_name="synthid_watermark_detector",
                    input_path=file_path,
                    timeout=30,
                )
                return result
            except Exception:
                # Fallback: run inline if subprocess unavailable
                try:
                    import os
                    import sys
                    sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "tools", "ml_tools"))
                    from synthid_watermark_detector import detect_ai_watermark
                    return detect_ai_watermark(file_path)
                except Exception as e2:
                    return {"available": False, "error": str(e2), "verdict": "ERROR"}

        registry.register(
            "synthid_watermark_detect",
            synthid_watermark_handler,
            "Detect SynthID, C2PA ai_generated, and AI software watermarks",
        )

        # ── No-API Fallback Search Tools ──────────────────────────────────────
        async def reverse_image_search_handler(input_data: dict) -> dict:
            from tools.google_search_tools import reverse_image_search
            artifact = input_data.get("artifact") or self.evidence_artifact
            result = await reverse_image_search(artifact=artifact)
            return result

        registry.register(
            "reverse_image_search",
            reverse_image_search_handler,
            "Google reverse image search for online provenance (no API key required)",
        )

        async def lens_style_scan_handler(input_data: dict) -> dict:
            from tools.lens_style_tools import lens_style_multimodal_scan
            artifact = input_data.get("artifact") or self.evidence_artifact
            result = await lens_style_multimodal_scan(artifact=artifact)
            return result

        registry.register(
            "lens_style_multimodal_scan",
            lens_style_scan_handler,
            "On-device multi-modal scan with OCR, barcode, object, and logo analysis (no API key)",
        )

        return registry


    async def build_initial_thought(self) -> str:
        name = os.path.basename(getattr(self.evidence_artifact, "file_path", "unknown"))
        lossless = self._is_lossless
        digital = self._is_screen_capture or self._is_digital_capture
        phase1_tool = (
            "digital-capture FFT and OCR checks"
            if digital
            else "Noiseprint++ sensor clustering"
            if lossless
            else "ViT Neural ELA manipulation detection"
        )
        if digital:
            return (
                f"Starting screen capture integrity analysis for '{name}'. "
                f"Phase 1: OCR text extraction, CLIP semantic classification, "
                f"SHA-256 integrity check, FFT frequency scan, "
                f"and SigLIP2 neural fingerprint for GAN/Diffusion signature detection."
            )

        return (
            f"Starting image integrity analysis for '{name}'. "
            f"Phase 1 (fast): CLIP semantic classification, "
            f"Gemini multimodal OCR (primary), EasyOCR fallback, Tesseract last-resort, "
            f"SigLIP2 neural fingerprint, SHA-256 integrity check, FFT frequency scan, "
            f"and {phase1_tool}. "
            f"Phase 2 (deep, background): TruFor splicing, BusterNet copy-move, "
            f"diffusion_artifact_detector for AI-generation signatures, "
            f"F3-Net frequency, ManTra-Net anomaly tracing, "
            f"and Gemini multimodal visual forensic synthesis."
        )

    async def on_tool_result(self, finding: AgentFinding) -> None:
        """Reactive task expansion based on pixel and semantic signals."""
        try:
            await self._on_tool_result_impl(finding)
            await self._reason_step(finding)
            # Ensure findings are progressively published to the UI to prevent hanging
            phase = finding.metadata.get("analysis_phase", "initial")
            await self._publish_agent_context(phase, [finding])
        except Exception as e:
            logger.warning("on_tool_result failed", agent_id=self.agent_id, error=str(e))

    async def _reason_step(self, finding: AgentFinding) -> None:
        """Domain-specific forensic logic to handle tool interaction patterns."""
        tool_name = finding.metadata.get("tool_name")
        if not tool_name:
            return

        findings = self._findings

        # 1. ELA + frequency disagreement
        ela_finding = next((f for f in findings if f.metadata.get("tool_name") in ("neural_ela", "ela_full_image")), None)
        fft_finding = next((f for f in findings if f.metadata.get("tool_name") == "frequency_domain_analysis"), None)
        if ela_finding and fft_finding:
            ela_pos = ela_finding.evidence_verdict == "POSITIVE" or ela_finding.metadata.get("manipulation_detected") is True or ela_finding.metadata.get("num_anomaly_regions", 0) > 0
            fft_neg = fft_finding.evidence_verdict in ("NEGATIVE", "CLEAN") or (fft_finding.metadata.get("anomaly_detected") is False and fft_finding.metadata.get("num_anomaly_regions", 0) == 0)
            if ela_pos and fft_neg:
                has_ghost = any("jpeg_ghost_detect" in (t.description or "").lower() for t in getattr(self, "_react_chain", []) if hasattr(t, "description"))
                has_f3 = any("f3_net_frequency" in (t.description or "").lower() for t in getattr(self, "_react_chain", []) if hasattr(t, "description"))
                
                state = await self.working_memory.get_state(session_id=self.session_id, agent_id=self.agent_id)
                if state:
                    has_ghost = has_ghost or any("jpeg_ghost_detect" in t.description.lower() for t in state.tasks)
                    has_f3 = has_f3 or any("f3_net_frequency" in t.description.lower() for t in state.tasks)

                if not has_ghost:
                    logger.info("Reasoning Step: ELA and FFT disagreement. Injecting jpeg_ghost_detect.", agent_id=self.agent_id)
                    await self.inject_task(description="Run jpeg_ghost_detect for double compression analysis", priority=15)
                if not has_f3:
                    logger.info("Reasoning Step: ELA and FFT disagreement. Injecting f3_net_frequency.", agent_id=self.agent_id)
                    await self.inject_task(description="Run f3_net_frequency for AI-GAN artifact detection", priority=15)

        # 2. noiseprint multi-cluster
        if tool_name == "noiseprint_cluster":
            num_clusters = finding.metadata.get("num_clusters", 1)
            sensor_inconsistent = finding.metadata.get("sensor_inconsistency_detected", False)
            if (finding.evidence_verdict == "POSITIVE" or sensor_inconsistent or num_clusters > 1):
                state = await self.working_memory.get_state(session_id=self.session_id, agent_id=self.agent_id)
                has_splicing = any("splicing" in t.description.lower() for t in state.tasks) if state else False
                has_copy_move = any("copy_move" in t.description.lower() for t in state.tasks) if state else False
                if not has_splicing:
                    logger.info("Reasoning Step: noiseprint multi-cluster anomaly. Injecting neural_splicing.", agent_id=self.agent_id)
                    await self.inject_task(description="Run neural_splicing for ViT-based region composition analysis", priority=18)
                if not has_copy_move:
                    logger.info("Reasoning Step: noiseprint multi-cluster anomaly. Injecting neural_copy_move.", agent_id=self.agent_id)
                    await self.inject_task(description="Run neural_copy_move for dual-branch copy-move detection", priority=18)

        # 3. copy-move confirmation after splicing
        if tool_name in ("neural_splicing", "splicing_detect"):
            if finding.evidence_verdict == "POSITIVE" or finding.metadata.get("splicing_detected") is True:
                state = await self.working_memory.get_state(session_id=self.session_id, agent_id=self.agent_id)
                has_copy_move = any("copy_move" in t.description.lower() for t in state.tasks) if state else False
                if not has_copy_move:
                    logger.info("Reasoning Step: Splicing detected. Injecting neural_copy_move to confirm clone source.", agent_id=self.agent_id)
                    await self.inject_task(description="Run neural_copy_move for dual-branch copy-move detection", priority=17)

        # 4. diffusion confidence without frequency anomaly
        diff_finding = next((f for f in findings if f.metadata.get("tool_name") == "diffusion_artifact_detector"), None)
        if diff_finding and fft_finding:
            diff_pos = diff_finding.evidence_verdict == "POSITIVE" or (diff_finding.confidence_raw or 0.0) > 0.8
            fft_neg = fft_finding.evidence_verdict in ("NEGATIVE", "CLEAN") or (fft_finding.metadata.get("anomaly_detected") is False and fft_finding.metadata.get("num_anomaly_regions", 0) == 0)
            if diff_pos and fft_neg:
                state = await self.working_memory.get_state(session_id=self.session_id, agent_id=self.agent_id)
                has_synthid = any("synthid" in t.description.lower() for t in state.tasks) if state else False
                has_f3 = any("f3_net_frequency" in t.description.lower() for t in state.tasks) if state else False
                if not has_synthid:
                    logger.info("Reasoning Step: High diffusion confidence but clean FFT. Injecting synthid_watermark_detect.", agent_id=self.agent_id)
                    await self.inject_task(description="Run synthid_watermark_detect for SynthID and AI watermark detection", priority=16)
                if not has_f3 and not (ela_finding and fft_finding and ela_pos and fft_neg):
                    logger.info("Reasoning Step: High diffusion confidence but clean FFT. Injecting f3_net_frequency.", agent_id=self.agent_id)
                    await self.inject_task(description="Run f3_net_frequency for AI-GAN artifact detection", priority=16)

        # 5. ROI injection on high-confidence ELA positives
        if tool_name in ("neural_ela", "ela_full_image"):
            ela_high_conf = (finding.evidence_verdict == "POSITIVE" and (finding.confidence_raw or 0.0) > 0.75) or finding.metadata.get("num_anomaly_regions", 0) > 3
            if ela_high_conf:
                state = await self.working_memory.get_state(session_id=self.session_id, agent_id=self.agent_id)
                has_roi = any("roi_extract" in t.description.lower() for t in state.tasks) if state else False
                if not has_roi:
                    logger.info("Reasoning Step: High-confidence ELA anomaly. Injecting roi_extract.", agent_id=self.agent_id)
                    await self.inject_task(description="Run roi_extract for localized forensic region analysis", priority=20)

        # 6. Reactive adversarial check on splicing or copy-move confirmation
        if tool_name in {"neural_splicing", "splicing_detect", "neural_copy_move", "copy_move_detect"}:
            if finding.evidence_verdict == "POSITIVE":
                state = await self.working_memory.get_state(session_id=self.session_id, agent_id=self.agent_id)
                has_adversarial = any("adversarial" in t.description.lower() for t in state.tasks) if state else False
                if not has_adversarial:
                    logger.info("Reasoning Step: Splicing/copy-move confirmed. Injecting adversarial_robustness_check.", agent_id=self.agent_id)
                    await self.inject_task(description="Run adversarial_robustness_check for anti-forensics perturbation stability check", priority=16)


    async def _on_tool_result_impl(self, finding: AgentFinding) -> None:
        """Implementation of reactive task expansion."""
        tool_name = finding.metadata.get("tool_name")

        # 1. [REACTIVE] analyze_image_content: Update sub-task with semantic context
        if tool_name == "analyze_image_content":
            image_type = (finding.metadata.get("image_type") or "unknown").lower()
            all_classifications = finding.metadata.get("all_classifications", [])

            # [RESTORED] Check for person, face, or AI markers for deepfake escalation
            # Robust keyword matching for forensic semantic triggers
            person_keywords = {
                "person",
                "people",
                "man",
                "woman",
                "face",
                "portrait",
                "selfie",
                "human",
            }
            has_person = any(k in image_type for k in person_keywords) or any(
                any(k in str(c.get("category", "")).lower() for k in person_keywords)
                and (c.get("score") or 0.0) > 0.4
                for c in all_classifications
            )

            ai_keywords = {"ai image", "digitally generated", "synthetic", "diffusion", "gan"}
            has_ai_marker = any(k in image_type for k in ai_keywords) or any(
                any(k in str(c.get("category", "")).lower() for k in ai_keywords)
                and (c.get("score") or 0.0) > 0.4
                for c in all_classifications
            )

            if has_person or has_ai_marker:
                logger.info(
                    f"Semantic trigger: {image_type}; injecting deepfake frequency audit",
                    agent_id=self.agent_id,
                )
                await self.inject_task(
                    description="Run deepfake_frequency_check for GAN/Diffusion artifacts",
                    priority=15,
                )

            if "screenshot" in image_type or "screen capture" in image_type:
                logger.info(
                    f"Screenshot detected: {image_type}; injecting font/UI forensics",
                    agent_id=self.agent_id,
                )
                await self.inject_task(
                    description="Run detect_font_inconsistency for screenshot text font analysis",
                    priority=13,
                )
                await self.inject_task(
                    description="Run detect_ui_overlay_forgery for screenshot UI overlay analysis",
                    priority=13,
                )

            object_keywords = {"vehicle", "weapon", "building", "product", "object", "scene"}
            has_object = any(k in image_type for k in object_keywords) or any(
                any(k in str(c.get("category", "")).lower() for k in object_keywords)
                and (c.get("score") or 0.0) > 0.4
                for c in all_classifications
            )

            if has_object:
                logger.info(
                    f"Object semantic trigger: {image_type}; injecting object ELA audit",
                    agent_id=self.agent_id,
                )
                await self.inject_task(
                    description="Run roi_extract guided by object detection for targeted ELA on subject",
                    priority=12,
                )

            # AI generation suspicion
            if has_ai_marker or "digitally generated" in image_type:
                # Force immediate deep analysis for AI suspicion
                await self.inject_task(
                    description="Run diffusion_artifact_detector to confirm AI generation",
                    priority=20,
                )

            # Reactive routing: handwritten content detection
            handwritten_keywords = {"handwritten", "handwriting", "hand writing", "manuscript", "cursive", "written note"}
            has_handwritten = any(k in image_type for k in handwritten_keywords) or any(
                any(k in str(c.get("category", "")).lower() for k in handwritten_keywords)
                and (c.get("score") or 0.0) > 0.35
                for c in all_classifications
            )
            if has_handwritten:
                logger.info(
                    f"Handwritten content detected: {image_type}; routing to handwriting OCR",
                    agent_id=self.agent_id,
                )
                await self.inject_task(
                    description="Run extract_text_from_image for handwriting OCR with adaptive fallback",
                    priority=12,
                )
                if self.inter_agent_bus:
                    self.inter_agent_bus.signal_event(
                        self.session_id,
                        "handwriting_detected",
                        {"agent_id": self.agent_id, "image_type": image_type},
                    )

            # Reactive routing: crime scene / weapon / document detection
            crime_keywords = {"crime scene", "blood", "injury", "weapon", "knife", "firearm", "gun", "violence"}
            has_crime_scene = any(k in image_type for k in crime_keywords) or any(
                any(k in str(c.get("category", "")).lower() for k in crime_keywords)
                and (c.get("score") or 0.0) > 0.35
                for c in all_classifications
            )
            if has_crime_scene:
                logger.info(
                    f"Crime scene / weapon content detected: {image_type}; routing to Agent 3",
                    agent_id=self.agent_id,
                )
                if self.inter_agent_bus:
                    self.inter_agent_bus.signal_event(
                        self.session_id,
                        "crime_scene_detected",
                        {"agent_id": self.agent_id, "image_type": image_type},
                    )


            await self.update_sub_task(f"Semantic Context: {image_type}")
            return

        # 1b. [REACTIVE] extract_text_from_image: Gemini content identification triggers deepfake escalation
        if tool_name == "extract_text_from_image":
            ocr_ctx = self._tool_context.get("extract_text_from_image", {})
            content_type = str(ocr_ctx.get("content_type") or "").lower()
            content_desc = str(ocr_ctx.get("content_description") or "").lower()
            combined = content_type + " " + content_desc

            person_keywords = {"person", "people", "man", "woman", "face", "portrait", "selfie", "human"}
            ai_keywords = {"ai", "generated", "synthetic", "diffusion", "gan", "artificial"}

            has_person = any(k in combined for k in person_keywords)
            has_ai_marker = any(k in combined for k in ai_keywords)

            if has_person or has_ai_marker:
                logger.info(
                    f"Gemini OCR content_type='{content_type}' triggered deepfake escalation",
                    agent_id=self.agent_id,
                )
                await self.inject_task(
                    description="Run deepfake_frequency_check for GAN/Diffusion artifacts",
                    priority=14,
                )
            if has_ai_marker:
                await self.inject_task(
                    description="Run diffusion_artifact_detector to confirm AI generation",
                    priority=19,
                )

            # Reactive routing: handwritten content from OCR context
            handwriting_keywords = {"handwritten", "handwriting", "manuscript", "cursive", "ink", "pen"}
            has_handwriting = any(k in combined for k in handwriting_keywords)
            if has_handwriting:
                logger.info(
                    f"OCR context suggests handwritten content; routing handwriting signal",
                    agent_id=self.agent_id,
                )
                if self.inter_agent_bus:
                    self.inter_agent_bus.signal_event(
                        self.session_id,
                        "handwriting_detected",
                        {"agent_id": self.agent_id, "source": "extract_text_from_image", "content_type": content_type},
                    )
            return

        # 2. If neural forensic tools flag high-confidence manipulation, inject localized ROI extraction
        if tool_name in {
            "neural_copy_move",
            "copy_move_detect",
            "neural_ela",
            "neural_splicing",
            "splicing_detect",
        }:
            if finding.evidence_verdict == "POSITIVE" and (finding.confidence_raw or 0.0) > 0.75:
                logger.info(
                    f"High-confidence {tool_name} signal; injecting ROI extraction",
                    agent_id=self.agent_id,
                )
                await self.inject_task(
                    description="Run roi_extract for localized forensic region analysis",
                    priority=20,
                )

        return
