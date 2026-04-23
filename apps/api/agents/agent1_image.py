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
from core.gemini_client import GeminiVisionClient
from core.handlers.image import ImageHandlers
from core.handlers.metadata import MetadataHandlers
from core.image_utils import is_lossless_image
from core.media_kind import is_digitally_created_image, is_screen_capture_like
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
        return self._compute_ceiling(len(self.task_decomposition))

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
        base.insert(-1, "Run adversarial_robustness_check for anti-forensics perturbation stability check if splicing or copy-move was detected")
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
        registry.register("file_hash_verify", metadata_h.file_hash_verify_handler, "SHA-256 hash verification against ingestion record")

        # ── Legacy/Compatibility mappings ─────────────────────────────────────
        # extract_evidence_text is used in some decomposition lists; map it to the unified OCR
        registry.register("extract_evidence_text", self.extract_text_from_image_handler, "Evidence text extraction (unified)")

        # ── Gemini Vision Handler ─────────────────────────────────────────────
        _gemini = GeminiVisionClient(self.config)

        async def gemini_deep_forensic_handler(input_data: dict) -> dict:
            """
            Gemini multimodal visual forensic synthesis.

            Aggregates results from ALL prior tools (both Phase-1 and Phase-2)
            into a cross-tool context summary before calling Gemini.

            Uses a priority lookup (_get_ctx) that checks the neural key first,
            then the legacy key, so the handler is correct regardless of which
            code path (neural success vs. fallback) populated _tool_context.
            """
            artifact = input_data.get("artifact") or self.evidence_artifact

            # Audit Fix 3: DYNAMIC CONTEXT AGGREGATION
            # Instead of a hardcoded map, we digest ALL successful results
            # from _tool_context so Gemini has total visibility without code updates.
            # Brutal Context Synthesis: Ensure all Phase-1/2 signals are summarized
            # with high fidelity for the multi-modal Gemini audit.
            # Audit Fix: DYNAMIC CONTEXT AGGREGATION
            from core.context_utils import aggregate_tool_context
            context_summary = aggregate_tool_context(self._tool_context, agent_id=self.agent_id)

            # EXIF Cross-modal check
            if self.working_memory:
                try:
                    agent5_context = await self.working_memory.get_agent_context(self.session_id, "Agent5")
                    exif_data = agent5_context.get("exif_extract", {})
                    if exif_data:
                        context_summary["metadata_audit"] = {
                            "camera": exif_data.get("device_model"),
                            "software": exif_data.get("software"),
                            "gps": bool(exif_data.get("gps_info")),
                            "timestamp_mismatch": exif_data.get("metadata_timeline_consistent") is False
                        }
                except Exception as _ctx_err:
                    logger.warning(
                        f"{self.agent_id}: EXIF cross-modal context retrieval failed — Gemini will proceed without metadata audit",
                        error=str(_ctx_err),
                    )

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

            try:
                finding = await _gemini.deep_forensic_analysis(
                    file_path=artifact.file_path,
                    exif_summary=context_summary,
                    signal_callback=_signal_cb,
                )
                result = finding.to_finding_dict(self.agent_id)
                result["analysis_source"] = "gemini_vision"

                await self._record_tool_result("gemini_deep_forensic", result)
                return result
            except Exception as e:
                await self._record_tool_error("gemini_deep_forensic", str(e))
                return {
                    "error": str(e),
                    "analysis_source": "gemini_vision",
                    "available": False,
                    "court_defensible": False,
                    "confidence": 0.0,
                }

        registry.register("gemini_deep_forensic", gemini_deep_forensic_handler, "Gemini multimodal visual forensic synthesis and evidence aggregation")

        return registry

    async def extract_text_from_image_handler(self, input_data: dict) -> dict:
        """Compatibility proxy for ImageHandlers' OCR."""
        handler = (
            self._tool_registry.get_handler("extract_text_from_image")
            if self._tool_registry is not None
            else None
        )
        if handler:
            return await handler(input_data)
        return {"error": "OCR handler not found", "available": False}

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
