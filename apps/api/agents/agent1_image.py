"""
Agent 1 — Pixel Integrity Agent.

Pixel-level forensic expert for detecting manipulation, splicing,
compositing, and AI-generation traces.

MANDATE (strict): Pixel integrity and AI-generation detection ONLY.
Does NOT perform object detection, metadata analysis, audio analysis,
or video temporal analysis — those belong to Agents 3, 5, 2, and 4
respectively.

Phase 1 (initial, fast): CLIP semantic classification, OCR text extraction,
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
from core.media_kind import is_digitally_created_image, is_screen_capture_like
from core.react_loop import AgentFinding
from core.structured_logging import get_logger
from core.tool_registry import ToolRegistry

logger = get_logger(__name__)


class Agent1Image(ForensicAgent):
    """
    Agent 1 — Pixel Integrity Agent.

    Mandate (STRICT): Pixel integrity and AI-generation traces ONLY.
    This agent does NOT perform object detection, metadata analysis,
    audio analysis, or video temporal analysis.
    """

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

    @property
    def iteration_ceiling(self) -> int:
        # Include both initial and deep tasks to prevent truncation of the forensic pipeline.
        base_count = len(self.task_decomposition) + len(self.deep_task_decomposition)
        return self._compute_ceiling(base_count)

    @property
    def task_decomposition(self) -> list[str]:
        """
        Phase 1 — Initial Analysis (fast, runs on every image).

        Tasks are ordered from least to most expensive so the agent produces
        useful context early and accumulates evidence progressively.
        """
        base = [
            "Run analyze_image_content for semantic image understanding",
            "Run file_hash_verify for evidence integrity check",
        ]
        if self._is_screen_capture or self._is_digital_capture:
            return base + [
                "Run frequency_domain_analysis for frequency domain analysis",
                "Run extract_text_from_image for visible text extraction",
            ]
        base.insert(1, "Run neural_fingerprint for conceptual similarity detection")
        if self._is_lossless:
            # Lossless path: Frequency is useful, noiseprint preferred
            return base + [
                "Run frequency_domain_analysis for frequency domain analysis",
                "Run noiseprint_cluster for sensor-region source inconsistency",
                "Run extract_text_from_image for visible text extraction",
            ]
        # Lossy path: ELA is authoritative; FFT runs first for GAN/periodicity baseline
        return base + [
            "Run frequency_domain_analysis for frequency domain analysis",
            "Run neural_ela for high-confidence manipulation detection",
            "Run extract_text_from_image for visible text extraction",
        ]

    @property
    def deep_task_decomposition(self) -> list[str]:
        """
        Phase 2 — Deep Neural Forensics (heavy, runs in background after Phase 1).

        anomaly_tracer (ManTra-Net) is gated inside its handler — it only fires
        when Phase-1 or earlier Phase-2 tools reported a tampering signal.
        """
        base = [
            "Run diffusion_artifact_detector for AI-generation signatures",
            "Run f3_net_frequency for AI-GAN artifact detection",
            "Run gemini_deep_forensic for cross-tool evidence aggregation and semantic grounding",
        ]
        if self._is_screen_capture or self._is_digital_capture:
            return base
        base.insert(0, "Run neural_copy_move for dual-branch copy-move detection")
        base.insert(0, "Run neural_splicing for ViT-based region composition analysis")
        # Only add anomaly_tracer if not lossless (as it relies heavily on JPEG noise/ghosts)
        if not self._is_lossless:
            base.insert(-1, "Run anomaly_tracer for ManTra-Net universal anomaly tracing")
        # adversarial_robustness_check is expensive — only warranted when splicing or
        # copy-move is confirmed, as anti-forensic perturbations are only meaningful
        # in that context.
        base.insert(
            -1,
            "Run adversarial_robustness_check for anti-forensics perturbation stability check if splicing or copy-move was detected",
        )
        return base

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

        # ── Legacy/Compatibility mappings ─────────────────────────────────────
        # extract_evidence_text is used in some decomposition lists; map it to the unified OCR
        registry.register(
            "extract_evidence_text",
            self.extract_text_from_image_handler,
            "Evidence text extraction (unified)",
        )

        # ── Gemini Vision Handler (Unified) ───────────────────────────────────
        async def gemini_deep_forensic_handler(input_data: dict) -> dict:
            async def _signal_cb(msg: str) -> None:
                """Relay Gemini progress to the inter-agent bus for frontend streaming."""
                try:
                    if self.inter_agent_bus:
                        self.inter_agent_bus.signal_event(
                            self.session_id,
                            "agent1_gemini_signal",
                            {"progress": msg},
                        )
                except Exception as _e:
                    logger.debug(f"{self.agent_id}: Gemini signal relay failed", error=str(_e))

            return await self._gemini_deep_forensic_handler(
                input_data, signal_callback=_signal_cb
            )

        registry.register(
            "gemini_deep_forensic",
            gemini_deep_forensic_handler,
            "Gemini multimodal visual forensic synthesis and evidence aggregation",
        )

        return registry

    async def extract_text_from_image_handler(self, input_data: dict) -> dict:
        """Compatibility proxy for ImageHandlers' OCR."""
        if self._tool_registry is None:
            return {"error": "registry not built", "available": False}
        handler = self._tool_registry.get_handler("extract_text_from_image")
        if handler is None or handler is self.extract_text_from_image_handler:
            return {"error": "OCR handler not found or aliased to self", "available": False}
        return await handler(input_data)

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
        return (
            f"Starting image integrity analysis for '{name}'. "
            f"Phase 1 (fast): CLIP semantic classification, Tesseract OCR, "
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
        except Exception as e:
            logger.warning("on_tool_result failed", agent_id=self.agent_id, error=str(e))

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

            if any(k in image_type for k in ("social media", "screenshot", "document", "post")):
                await self.update_sub_task(
                    f"High-risk {image_type} identified — grounding metadata check..."
                )

            # AI generation suspicion
            if has_ai_marker or "digitally generated" in image_type:
                # Force immediate deep analysis for AI suspicion
                await self.inject_task(
                    description="Run diffusion_artifact_detector to confirm AI generation",
                    priority=20,
                )

            # surveillance footage
            if "surveillance" in image_type or "security" in image_type:
                await self.inject_task(
                    description="Run noise_fingerprint to check sensor consistency in surveillance frame",
                    priority=15,
                )

            await self.update_sub_task(f"Semantic Context: {image_type}")
            await self._publish_agent_context("initial", [finding])
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

            await self._publish_agent_context(
                "deep" if "neural" in tool_name else "initial", [finding]
            )
