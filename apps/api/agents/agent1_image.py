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
from core.image_routing import TOOL_TO_TASK_DESCRIPTION, build_image_forensic_routing
from core.image_utils import is_lossless_image
from core.media_kind import (
    is_camera_still_candidate,
    is_digitally_created_image,
    is_document_like,
    is_recompressed_web_image,
    is_screen_capture_like,
)
from core.react_loop import AgentFinding
from core.structured_logging import get_logger
from core.tool_names import TOOL_VISUAL_PROFILE
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

    async def _validate_evidence_artifact(self) -> dict:
        """Run validation chain BEFORE building task list."""
        artifact = self.evidence_artifact
        file_path = str(getattr(artifact, "file_path", "") or "")
        from pathlib import Path

        p = Path(file_path)
        if not p.exists():
            if getattr(self.config, "app_env", "") == "testing":
                return {
                    "status": "test_missing_file",
                    "mime": getattr(artifact, "mime_type", "") or "",
                    "size_mb": 0.0,
                }
            raise ValueError(f"Evidence file not found: {file_path}")

        size_mb = p.stat().st_size / (1024 * 1024)
        if size_mb > 500:
            raise ValueError(f"Evidence file too large: {size_mb:.1f}MB")

        try:
            from PIL import Image
            with Image.open(file_path) as img:
                img.verify()
        except Exception as e:
            raise ValueError(f"Corrupted image file: {e}") from e

        mime = getattr(artifact, "mime_type", "") or ""
        if mime and not mime.startswith("image/"):
            raise ValueError(f"Not a valid image file: {mime}")

        return {"status": "validated", "mime": mime, "size_mb": size_mb}

    @property
    def task_decomposition(self) -> list[str]:
        """
        Phase 1 tasks are derived from file classification.
        """
        from core.image_evidence_routing import get_agent_plan
        plan = get_agent_plan(self.evidence_artifact, self.agent_id, phase="initial")
        if plan:
            return plan

        classification = getattr(self, '_file_classification', None)
        if not classification:
            classification = self._legacy_classify()

        recommended_tools = classification.recommended_tools
        base_tasks = []

        from core.image_routing import TOOL_TO_TASK_DESCRIPTION
        for tool in recommended_tools:
            if tool == "file_hash_verify":
                continue
            task_desc = TOOL_TO_TASK_DESCRIPTION.get(tool)
            if task_desc:
                base_tasks.append(task_desc)

        if "visual_evidence_profile" not in " ".join(base_tasks):
            base_tasks.append("Run visual_evidence_profile for visual evidence profile and forensic routing hints")

        return base_tasks

    def _legacy_classify(self):
        """Fallback classification using legacy heuristics."""
        from core.file_classifier import FileClassification

        return FileClassification(
            primary_category="screenshot" if (self._is_screen_capture or self._is_digital_capture)
            else "document" if self._is_document
            else "live_photograph",
            confidence=0.6,
        )

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
        from core.image_evidence_routing import get_agent_plan
        plan = get_agent_plan(self.evidence_artifact, self.agent_id, phase="deep")
        if plan:
            return plan

        if self._is_screen_capture or self._is_digital_capture:
            # Gemini already ran in Phase 1 for screenshots. Phase 2 uses
            # classical ML tools for AI-generation detection (deepfakes are
            # often shared as screenshots of generated content).
            # neural_fingerprint excluded — no perceptual signal value for
            # unique UI states. deepfake_frequency_check excluded — high
            # false positive rate on compressed UI edge aliasing.
            return [
                "Run f3_net_frequency for AI-GAN artifact detection",
                "Run diffusion_artifact_detector for AI-generation signatures",
                "Run synthid_watermark_detect for SynthID and AI watermark detection",
            ]

        # Natural photos: fast high-signal tools first, heavy tools later
        tasks = [
            "Run diffusion_artifact_detector for AI-generation signatures",
            "Run synthid_watermark_detect for SynthID and AI watermark detection",
            "Run f3_net_frequency for AI-GAN artifact detection",
            "Run neural_splicing for SRM-residual region composition screening",
            "Run neural_copy_move for ORB+RANSAC copy-move screening",
        ]
        # anomaly_tracer relies heavily on JPEG noise/ghosts — skip for lossless
        if not self._is_lossless:
            tasks.append("Run anomaly_tracer for statistical anomaly screening")
        # adversarial_robustness_check removed from base — injected reactively in
        # _reason_step when neural_splicing or neural_copy_move returns POSITIVE.
        # Gemini removed from Phase 2 — Phase 1 result in shared context.
        return tasks

    async def build_tool_registry(self) -> ToolRegistry:
        registry = ToolRegistry()

        # ── Pre-flight validation ──────────────────────────────────────────────
        await self._validate_evidence_artifact()

        # ── File Classification (single source of truth) ──────────────────────
        from core.file_classifier import classify_evidence_file
        classification = await classify_evidence_file(self.evidence_artifact)
        self._file_classification = classification

        logger.info(
            "Tool registry built for category",
            category=classification.primary_category,
            recommended_tools=len(classification.recommended_tools),
        )

        # ── Register category-specific tools ──────────────────────────────────
        # NOTE: file_hash_verify is registered exclusively by Agent 5 (Provenance).
        # Agent 1 reads the hash result from shared context instead of running it.

        # Only register image handlers for tools in the recommended set
        image_h = ImageHandlers(self)
        registry.register("neural_splicing", image_h.neural_splicing_handler, "TruFor ViT-based splicing detection")
        registry.register("neural_copy_move", image_h.neural_copy_move_handler, "BusterNet dual-branch copy-move detection")
        # Sensor-noise residual clustering — the lossless-appropriate Phase-1
        # integrity screen (ELA is NOT_APPLICABLE on lossless). Scheduled by the
        # deterministic plan for lossless camera photos and keyed on by the
        # _reason_step multi-cluster escalation rule. Registered unconditionally;
        # it only runs when the plan/rules call for it (content gate keeps it to images).
        registry.register("noiseprint_cluster", image_h.noiseprint_cluster_handler, "Sensor noise residual clustering (K-means)")
        registry.register("anomaly_tracer", image_h.anomaly_tracer_handler, "ManTra-Net universal anomaly tracing")
        registry.register("f3_net_frequency", image_h.f3_net_frequency_handler, "F3-Net frequency artifact analysis")
        registry.register("diffusion_artifact_detector", image_h.diffusion_artifact_detector_handler, "Diffusion/AI-generation artifact detection")
        if classification.primary_category == "screenshot":
            registry.register("detect_font_inconsistency", image_h.detect_font_inconsistency_handler, "Font consistency analysis")
            registry.register("detect_ui_overlay_forgery", image_h.detect_ui_overlay_forgery_handler, "UI overlay forgery detection")
            registry.register("frequency_domain_analysis", image_h.frequency_domain_analysis_handler, "FFT frequency-domain analysis")
        elif classification.primary_category in ("live_photograph", "object_scene", "web_image"):
            registry.register("neural_ela", image_h.neural_ela_handler, "Neural ELA manipulation detection")
            registry.register("frequency_domain_analysis", image_h.frequency_domain_analysis_handler, "FFT frequency-domain analysis")
            registry.register("neural_fingerprint", image_h.neural_fingerprint_handler, "SigLIP2 neural fingerprint")
        elif classification.primary_category == "document":
            registry.register("frequency_domain_analysis", image_h.frequency_domain_analysis_handler, "FFT frequency-domain analysis")
            registry.register("neural_ela", image_h.neural_ela_handler, "Neural ELA manipulation detection")
        elif classification.primary_category == "ai_generated_suspect":
            registry.register("frequency_domain_analysis", image_h.frequency_domain_analysis_handler, "FFT frequency-domain analysis")
            registry.register("diffusion_artifact_detector", image_h.diffusion_artifact_detector_handler, "Diffusion artifact detection")
            registry.register("deepfake_frequency_check", image_h.deepfake_frequency_check_handler, "GAN/Deepfake frequency check")

        # ── Reactive follow-up integrity tools ─────────────────────────────────
        # These are NOT in the initial task plan — they only execute when a
        # reactive rule in _reason_step / _on_tool_result_impl / _escalate_from_
        # visual_profile injects them (e.g. ROI extraction after a high-confidence
        # ELA positive, adversarial check after confirmed splicing, jpeg_ghost on
        # ELA/FFT disagreement, deepfake-frequency on person/AI content). They were
        # previously unregistered, so every injected escalation task either mis-
        # routed to a different tool or surfaced as an "Unmatched Task" — i.e. the
        # agent's adaptive reasoning was inert. Registering them here activates it.
        # All are pixel-integrity tools (Agent1's mandate) — NO content/OCR tools.
        # Applicability is enforced downstream by the content-aware gate
        # (jpeg_ghost_detect → NOT_APPLICABLE on lossless) and the screenshot guard
        # in _reason_step, so registering them unconditionally is safe.
        for _react_tool, _react_handler, _react_desc in (
            ("roi_extract", image_h.roi_extract_handler, "Region-of-interest localized forensic extraction"),
            ("adversarial_robustness_check", image_h.adversarial_robustness_check_handler, "Anti-forensics perturbation stability check"),
            ("jpeg_ghost_detect", image_h.jpeg_ghost_detect_handler, "JPEG ghost / double-compression artifact detection"),
            ("deepfake_frequency_check", image_h.deepfake_frequency_check_handler, "GAN/Deepfake frequency artifact check"),
        ):
            if _react_tool not in registry.handlers:
                registry.register(_react_tool, _react_handler, _react_desc)

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

            if result and result.get("available", True):
                try:
                    if self.inter_agent_bus:
                        self.inter_agent_bus.set_visual_profile(
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
                description = (
                    result.get("reasoning_summary")
                    or result.get("content_description")
                    or metadata.get("content_description")
                    or ""
                )
                routing_source = metadata.get("forensic_routing") or {}
                if not routing_source:
                    routing_source = {
                        "image_category": (
                            "screenshot" if self._is_screen_capture or self._is_digital_capture
                            else "document" if self._is_document
                            else "live_photograph"
                        )
                    }
                routing = build_image_forensic_routing(
                    routing_source,
                    description=str(description),
                    file_path=str(getattr(self.evidence_artifact, "file_path", "") or ""),
                )
                metadata["forensic_routing"] = routing
                result["metadata"] = metadata
                skip_tools = [
                    str(tool).lower().replace("_", "")
                    for tool in routing.get("skip_tools", [])
                ]
                recommended_tools = {
                    str(tool)
                    for tool in routing.get("recommended_initial_tools", [])
                    if tool
                }

                if skip_tools or recommended_tools:
                    state = await self.working_memory.get_state(
                        self.session_id,
                        self.agent_id,
                    )
                    updated_tasks = []
                    seen_tools: set[str] = set()

                    for task in state.tasks:
                        matched_tool = None
                        for name in registry.handlers.keys():
                            if name in task.description:
                                matched_tool = name
                                break

                        if matched_tool:
                            seen_tools.add(matched_tool)
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

                    for tool_name in recommended_tools - seen_tools:
                        task_desc = TOOL_TO_TASK_DESCRIPTION.get(tool_name)
                        if task_desc and tool_name in registry.handlers:
                            await self.inject_task(task_desc, priority=14)

                    if self.inter_agent_bus:
                        self.inter_agent_bus.set_visual_profile(
                            str(self.session_id),
                            result,
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

        # NOTE: TOOL_GEMINI_DEEP ("gemini_deep_forensic") is NOT registered here.
        # It is a legacy alias kept in tool_names.py for backward-compatible
        # deserialization of old persisted tasks. New runs use TOOL_VISUAL_PROFILE.

        # ── SynthID / AI Watermark Detection ─────────────────────────────────
        async def synthid_watermark_handler(input_data: dict) -> dict:
            from core.ml_subprocess import run_ml_script_subprocess
            file_path = str(getattr(self.evidence_artifact, "file_path", ""))
            try:
                result = await run_ml_script_subprocess(
                    script_name="synthid_watermark_detector",
                    input_path=file_path,
                    timeout=75,
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

    async def _verify_required_tools_executed(self) -> None:
        """After Phase 1 completes, verify all required tools actually ran."""
        classification = getattr(self, '_file_classification', None)
        if not classification:
            return

        required_tools = set(classification.recommended_tools)
        executed_tools = set(self._tool_context.keys())

        missing = required_tools - executed_tools
        if missing:
            logger.warning(
                "Incomplete forensic coverage",
                category=classification.primary_category,
                missing_tools=list(missing),
            )

        logger.info(
            "Tool coverage verified",
            category=classification.primary_category,
            required=len(required_tools),
            executed=len(executed_tools),
        )

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

        if self._is_screen_capture or self._is_digital_capture:
            screenshot_irrelevant = {
                "noiseprint_cluster",
                "noise_fingerprint",
                "neural_splicing",
                "splicing_detect",
                "neural_copy_move",
                "copy_move_detect",
                "adversarial_robustness_check",
                "roi_extract",
                "ela_full_image",
                "neural_ela",
                "jpeg_ghost_detect",
            }
            if tool_name in screenshot_irrelevant:
                logger.info(
                    "Skipping camera-image reactive expansion for screen capture",
                    agent_id=self.agent_id,
                    tool_name=tool_name,
                )
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


    async def _escalate_from_visual_profile(self, profile_meta: dict) -> None:
        """Content-driven integrity routing, sourced from the shared visual context.

        Agent 1 no longer runs content tools (analyze_image_content / OCR) — those
        belong to Agent 3. Instead it reads what the evidence IS from the shared
        preflight visual context (threaded as self.visual_context, with the visual
        profile finding metadata as a fallback) and pre-injects the integrity tools
        that content warrants: deepfake/diffusion for people or AI markers, font/UI
        forgery for screenshots, and ROI-guided ELA for salient objects.
        """
        vc = getattr(self, "visual_context", None)

        def _vc_str(attr: str) -> str:
            return str(getattr(vc, attr, "") or "").lower() if vc is not None else ""

        desc = _vc_str("scene_description") or str(profile_meta.get("content_description") or "").lower()
        ftype = _vc_str("file_type_assessment") or str(
            profile_meta.get("file_type_assessment") or profile_meta.get("content_type") or ""
        ).lower()

        labels: list[str] = []
        if vc is not None:
            for o in (getattr(vc, "detected_objects", None) or []):
                lbl = getattr(o, "label", None) if not isinstance(o, dict) else o.get("label")
                if lbl:
                    labels.append(str(lbl).lower())
        for o in (profile_meta.get("detected_objects") or []):
            lbl = o.get("label") if isinstance(o, dict) else o
            if lbl:
                labels.append(str(lbl).lower())

        signals: list[str] = []
        if vc is not None:
            integ = getattr(vc, "image_integrity_context", None)
            signals += [str(s).lower() for s in (getattr(integ, "visible_manipulation_signals", None) or [])]
            signals += [str(s).lower() for s in (getattr(integ, "ai_generation_signals", None) or [])]
        signals += [str(s).lower() for s in (profile_meta.get("manipulation_signals") or [])]

        combined = " ".join([desc, ftype, " ".join(labels), " ".join(signals)])

        person_kw = ("person", "people", "man", "woman", "face", "portrait", "selfie", "human")
        ai_kw = ("ai image", "ai-generated", "digitally generated", "synthetic", "diffusion", "gan", "artificial")
        object_kw = ("vehicle", "weapon", "building", "product", "object", "scene")
        handwritten_kw = ("handwritten", "handwriting", "manuscript", "cursive", "written note")
        crime_kw = ("crime scene", "blood", "injury", "weapon", "knife", "firearm", "gun", "violence")

        has_person = any(k in combined for k in person_kw)
        has_ai = any(k in combined for k in ai_kw)
        has_object = any(k in combined for k in object_kw)
        has_handwritten = any(k in combined for k in handwritten_kw)
        has_crime = any(k in combined for k in crime_kw)
        is_screenshot = "screenshot" in combined or "screen capture" in combined or ftype == "screenshot"

        if has_person or has_ai:
            logger.info("Visual-context content trigger; injecting deepfake frequency audit", agent_id=self.agent_id)
            await self.inject_task(
                description="Run deepfake_frequency_check for GAN/Diffusion artifacts", priority=15
            )
        if has_ai:
            await self.inject_task(
                description="Run diffusion_artifact_detector to confirm AI generation", priority=20
            )
        if is_screenshot:
            await self.inject_task(
                description="Run detect_font_inconsistency for screenshot text font analysis", priority=13
            )
            await self.inject_task(
                description="Run detect_ui_overlay_forgery for screenshot UI overlay analysis", priority=13
            )
        if has_object:
            await self.inject_task(
                description="Run roi_extract guided by object detection for targeted ELA on subject", priority=12
            )
        # Content-domain signals (handwriting / crime-scene) are routed to Agent 3
        # via the bus — Agent 1 no longer runs OCR/content tools itself.
        if has_handwritten and self.inter_agent_bus:
            self.inter_agent_bus.signal_event(
                self.session_id, "handwriting_detected", {"agent_id": self.agent_id, "source": "visual_context"}
            )
        if has_crime and self.inter_agent_bus:
            self.inter_agent_bus.signal_event(
                self.session_id, "crime_scene_detected", {"agent_id": self.agent_id, "source": "visual_context"}
            )

    async def _on_tool_result_impl(self, finding: AgentFinding) -> None:
        """Implementation of reactive task expansion."""
        tool_name = finding.metadata.get("tool_name")

        # 1. [REACTIVE] Content-driven integrity routing — sourced from the shared
        # visual profile. Content tools (analyze_image_content / extract_text) now
        # belong to Agent 3 (object/content axis, canonical tool taxonomy). Agent 1
        # reads what the evidence IS from the shared preflight visual context and
        # pre-injects the integrity tools that content warrants.
        if tool_name in ("visual_evidence_profile", "shared_visual_evidence_profile"):
            await self._escalate_from_visual_profile(finding.metadata or {})
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
