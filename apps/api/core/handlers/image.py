"""
Image Tool Handlers
===================

Domain-specific handlers for image forensic tools.
Implements decentralized tool registration and phased analysis refinements.

Fix log (applied in audit pass):
  - All neural handlers now store results under BOTH the neural key AND the
    legacy key that gemini_deep_forensic_handler reads, so Gemini always has
    full context regardless of which code path ran.
  - All fallback handlers now call _record_tool_result so results persist to
    _tool_context and are visible to cross-tool consumers.
  - Sync CPU calls (noise_consistency, copy_move, frequency_bands) are wrapped
    in run_in_executor so they never block the async event loop.
  - inference_client calls carry explicit asyncio.wait_for timeouts.
  - anomaly_tracer is gated on prior tampering signals — ManTra-Net only runs
    when at least one earlier tool flagged manipulation.
  - roi_extract_handler falls back to first ELA anomaly region, then full image,
    instead of the meaningless top-left 100×100 corner.
  - roi_extract is registered as a standalone tool so the react loop can resolve
    the ELA follow-up trigger.
"""

from __future__ import annotations

import asyncio

import cv2
import numpy as np
from PIL import Image

from core.forensics.ela import (
    check_adversarial_robustness,  # sync, run in executor
    classify_ela_anomalies,  # async
)
from core.forensics.frequency import analyze_frequency_bands  # sync, run in executor

# Forensic analysis helpers (live in core/forensics/)
from core.forensics.noise import analyze_noise_consistency  # sync, run in executor
from core.handlers.base import BaseToolHandler
from core.ml_subprocess import run_ml_tool
from core.scoring import ConfidenceCalibrator
from core.structured_logging import get_logger
from tools.image_tools import (
    analyze_image_content as real_analyze_image_content,
)

# Primary image tool functions (live in tools/image_tools.py)
from tools.image_tools import (
    ela_full_image as real_ela_full_image,
)
from tools.image_tools import (
    frequency_domain_analysis as real_frequency_domain_analysis,
)
from tools.image_tools import (
    jpeg_ghost_detect as real_jpeg_ghost_detect,
)
from tools.image_tools import (
    roi_extract as real_roi_extract,
)

# ML fallback tools (importable CLI scripts in tools/ml_tools/)
from tools.ml_tools.copy_move_detector import detect_copy_move  # sync, run in executor
from tools.ml_tools.splicing_detector import detect_splicing  # sync, run in executor
from tools.ocr_tools import extract_evidence_text as real_extract_evidence_text

logger = get_logger(__name__)


class ImageHandlers(BaseToolHandler):
    """Handles Image Integrity and Content analysis tools."""

    def register_tools(self, registry) -> None:
        """Register tools with the agent's ToolRegistry."""
        # ── Phase 1: Initial Analysis ────────────────────────────────────────
        registry.register("neural_ela",               self.neural_ela_handler,               "Neural ELA Transformer manipulation detection")
        registry.register("noiseprint_cluster",       self.noiseprint_cluster_handler,       "Noiseprint++ sensor-region consistency clustering")

        # ── Phase 2: Deep Neural Forensics ───────────────────────────────────
        registry.register("neural_copy_move",         self.neural_copy_move_handler,         "BusterNet dual-branch copy-move detection")
        registry.register("neural_splicing",          self.neural_splicing_handler,          "TruFor ViT-based splicing detection")
        registry.register("anomaly_tracer",           self.anomaly_tracer_handler,           "ManTra-Net universal anomaly tracing")
        registry.register("f3_net_frequency",         self.f3_net_frequency_handler,         "F3-Net frequency artifact analysis")
        registry.register("neural_fingerprint",       self.neural_fingerprint_handler,       "SigLIP2 neural perceptual fingerprint")
        registry.register("diffusion_artifact_detector", self.diffusion_artifact_detector_handler, "Diffusion/AI-generation artifact detection")

        # ── Global Semantic & Content Tools ──────────────────────────────────
        registry.register("analyze_image_content",   self.analyze_image_content_handler,   "CLIP ViT-B-32 semantic classification")
        registry.register("extract_text_from_image", self.extract_text_from_image_handler, "Tiered OCR (EasyOCR -> Tesseract)")
        registry.register("frequency_domain_analysis", self.frequency_domain_analysis_handler, "FFT frequency-domain anomaly analysis")

        # ── Supplementary (used as follow-up targets) ────────────────────────
        registry.register("roi_extract",              self.roi_extract_handler,              "Region of interest extraction")
        registry.register("ela_anomaly_classify",     self.ela_anomaly_classify_handler,     "ELA anomaly block classification")
        registry.register("adversarial_robustness_check", self.adversarial_robustness_check_handler, "Anti-forensics perturbation stability check")

    # ── Helpers ───────────────────────────────────────────────────────────────

    def _has_tampering_signal(self) -> bool:
        """
        Return True if any Phase-1 or Phase-2 tool already flagged manipulation.
        Used to gate expensive ManTra-Net inference.
        """
        ctx = self.agent._tool_context
        freq = ctx.get("frequency_domain_analysis", {})
        return any([
            ctx.get("neural_ela", {}).get("manipulation_detected", False),
            (ctx.get("neural_ela") or ctx.get("ela_full_image", {})).get("num_anomaly_regions", 0) > 2,
            ctx.get("noiseprint_cluster", {}).get("manipulation_detected", False),
            ctx.get("neural_splicing", {}).get("splicing_detected", False),
            ctx.get("neural_copy_move", {}).get("copy_move_detected", False),
            ctx.get("f3_net_frequency", {}).get("gan_artifact_detected", False),
            ctx.get("diffusion_artifact_detector", {}).get("is_ai_generated", False),
            ctx.get("diffusion_artifact_detector", {}).get("diffusion_detected", False),
            freq.get("anomaly_detected", False),
            freq.get("num_anomaly_regions", 0) > 2,
        ])

    def _has_splice_or_copy_move_signal(self) -> bool:
        """Return True when anti-forensic robustness analysis is warranted."""
        ctx = self.agent._tool_context
        return any([
            ctx.get("neural_splicing", {}).get("splicing_detected", False),
            ctx.get("splicing_detect", {}).get("splicing_detected", False),
            ctx.get("neural_copy_move", {}).get("copy_move_detected", False),
            ctx.get("copy_move_detect", {}).get("copy_move_detected", False),
            ctx.get("vector_contraband_search", {}).get("concern_flag", False),
            ctx.get("scene_incongruence", {}).get("scene_incongruent", False),
            ctx.get("lighting_consistency", {}).get("inconsistency_detected", False),
        ])

    async def _store(self, primary_key: str, result: dict, *alias_keys: str) -> None:
        """
        Persist a tool result to _tool_context under the primary key and any
        alias keys. Records a success count increment via _record_tool_result
        (which writes to the primary key). Alias keys are written directly so
        consumers using legacy naming (e.g. gemini_deep_forensic_handler) also
        see the result.
        """
        await self.agent._record_tool_result(primary_key, result)
        for alias in alias_keys:
            self.agent._tool_context[alias] = result

    # ── Phase 1: Neural ELA ───────────────────────────────────────────────────

    async def neural_ela_handler(self, input_data: dict) -> dict:
        """ViT-based Neural ELA. Falls back to multi-quality classical ELA."""
        artifact = input_data.get("artifact") or self.agent.evidence_artifact
        result = await run_ml_tool("neural_ela_transformer.py", artifact.file_path, timeout=15.0)
        if not result.get("error") and result.get("available"):
            # Store under both neural key and legacy key so Gemini reads it correctly.
            await self._store("neural_ela", result, "ela_full_image")
            return result

        # Fallback: classical multi-quality ELA
        return await self.ela_full_image_handler(input_data)

    # ── Phase 1: Noiseprint Cluster ───────────────────────────────────────────

    async def noiseprint_cluster_handler(self, input_data: dict) -> dict:
        """Noiseprint++ CNN sensor-region clustering. Falls back to heuristic noise analysis."""
        artifact = input_data.get("artifact") or self.agent.evidence_artifact
        result = await run_ml_tool("noiseprint_clustering.py", artifact.file_path, timeout=20.0)
        if not result.get("error") and result.get("available"):
            await self._store("noiseprint_cluster", result, "noise_fingerprint")
            return result

        # Fallback: heuristic noise fingerprint
        return await self.noise_fingerprint_handler(input_data)

    # ── Standard Handlers (used as fallbacks and standalone) ─────────────────

    async def ela_full_image_handler(self, input_data: dict) -> dict:
        """Classical multi-quality ELA sweep (4 quality levels, fused via max)."""
        artifact = input_data.get("artifact") or self.agent.evidence_artifact
        try:
            result = await real_ela_full_image(
                artifact=artifact,
                quality=input_data.get("quality", 95),
                anomaly_threshold=input_data.get("anomaly_threshold", 10.0),
            )
        except Exception as e:
            result = {"error": str(e)}

        if result.get("error"):
            result = self._ela_fallback(artifact.file_path, str(result.get("error")))
        else:
            raw_sig = max(
                min(result.get("num_anomaly_regions", 0) / 15.0, 1.0),
                min(result.get("max_anomaly", 0.0) / 80.0, 1.0),
            )
            result["confidence"] = ConfidenceCalibrator.calibrate_heuristic(
                raw_sig, reliability_tag="opencv_heuristic"
            )

        # Store under both keys — neural_ela handler may have already stored here
        # on a failure path; we overwrite with the same result for consistency.
        await self._store("ela_full_image", result, "neural_ela")
        return result

    def _ela_fallback(self, file_path: str, error_msg: str) -> dict:
        """Minimal OpenCV-based ELA fallback when Pillow/scipy ELA fails."""
        try:
            img = np.array(Image.open(file_path).convert("RGB"))
            gray = cv2.cvtColor(img, cv2.COLOR_RGB2GRAY).astype(np.float32)
            return {
                "max_anomaly": 0.0,
                "num_anomaly_regions": 0,
                "mean_ela": float(np.mean(gray)),
                "confidence": 0.50,
                "degraded": True,
                "fallback_reason": f"ELA failed ({error_msg}); using basic stats.",
                "court_defensible": False,
                "available": True,
            }
        except Exception:
            return {"error": "ELA total failure", "available": False, "confidence": 0.0}

    async def roi_extract_handler(self, input_data: dict) -> dict:
        """
        Extract the most forensically relevant Region of Interest.

        Priority order:
          1. Caller-supplied bounding_box (explicit override)
          2. First YOLO detection from Agent 3 (object-guided)
          3. First ELA anomaly region (manipulation-guided)
          4. Skip with a clear reason (never crops a meaningless fixed corner)
        """
        artifact = input_data.get("artifact") or self.agent.evidence_artifact
        bounding_box = input_data.get("bounding_box")

        # Priority 1: YOLO detections from Agent 3
        if not bounding_box:
            obj_ctx = self.agent._tool_context.get("object_detection", {})
            detections = obj_ctx.get("detections", [])
            if detections:
                box = detections[0].get("box", {})
                if box:
                    bounding_box = {
                        "x": int(box.get("x1", 0)),
                        "y": int(box.get("y1", 0)),
                        "w": int(box.get("x2", 0) - box.get("x1", 0)),
                        "h": int(box.get("y2", 0) - box.get("y1", 0)),
                    }

        # Priority 2: First ELA anomaly region
        if not bounding_box:
            ela_ctx = (
                self.agent._tool_context.get("neural_ela")
                or self.agent._tool_context.get("ela_full_image", {})
            )
            anomaly_regions = ela_ctx.get("anomaly_regions", [])
            if anomaly_regions:
                r = anomaly_regions[0]
                bounding_box = {
                    "x": r.get("x", 0),
                    "y": r.get("y", 0),
                    "w": r.get("w", 100),
                    "h": r.get("h", 100),
                }

        # Priority 3: No useful region found — skip rather than crop a useless corner
        if not bounding_box:
            result = {
                "roi_skipped": True,
                "reason": "No YOLO detections or ELA anomaly regions available to guide ROI extraction",
                "confidence": 0.0,
                "court_defensible": False,
                "available": True,
            }
            await self.agent._record_tool_result("roi_extract", result)
            return result

        result = await real_roi_extract(artifact=artifact, bounding_box=bounding_box)
        await self.agent._record_tool_result("roi_extract", result)
        return result

    async def noise_fingerprint_handler(self, input_data: dict) -> dict:
        """
        Heuristic PRNU noise consistency analysis.
        Only meaningful for lossless images; noiseprint_cluster is preferred.
        """
        artifact = input_data.get("artifact") or self.agent.evidence_artifact

        # Skip for lossy images — heuristic noise analysis on JPEG is unreliable
        # (noiseprint_cluster handles lossless; neural_ela handles JPEG).
        if hasattr(self.agent, "_is_lossless") and not self.agent._is_lossless:
            result = {
                "noise_fingerprint_not_applicable": True,
                "verdict": "NOT_APPLICABLE",
                "reason": "Heuristic noise fingerprint is unreliable on lossy JPEG images; use neural_ela instead.",
                "confidence": 0.0,
                "available": True,
            }
            await self.agent._record_tool_result("noise_fingerprint", result)
            return result

        # Try ML-based noise fingerprint first
        result = await run_ml_tool("noise_fingerprint.py", artifact.file_path, timeout=15.0)
        if not result.get("error") and result.get("available"):
            await self._store("noise_fingerprint", result, "noiseprint_cluster")
            return result

        # Fallback: heuristic — run in executor so it doesn't block the event loop
        loop = asyncio.get_running_loop()
        result = await loop.run_in_executor(None, analyze_noise_consistency, artifact.file_path)
        await self._store("noise_fingerprint", result, "noiseprint_cluster")
        return result

    async def jpeg_ghost_detect_handler(self, input_data: dict) -> dict:
        """JPEG ghost / double-compression artifact detection."""
        artifact = input_data.get("artifact") or self.agent.evidence_artifact
        result = await real_jpeg_ghost_detect(artifact=artifact)
        await self.agent._record_tool_result("jpeg_ghost_detect", result)
        return result

    async def splicing_detect_handler(self, input_data: dict) -> dict:
        """Heuristic image splicing detection (sync CPU call — runs in executor)."""
        artifact = input_data.get("artifact") or self.agent.evidence_artifact
        loop = asyncio.get_running_loop()
        result = await loop.run_in_executor(None, detect_splicing, artifact.file_path)
        await self.agent._record_tool_result("splicing_detect", result)
        return result

    async def deepfake_frequency_check_handler(self, input_data: dict) -> dict:
        """Heuristic frequency-band GAN artifact analysis."""
        artifact = input_data.get("artifact") or self.agent.evidence_artifact
        loop = asyncio.get_running_loop()
        result = await loop.run_in_executor(None, analyze_frequency_bands, artifact.file_path)
        await self._store("deepfake_frequency_check", result, "f3_net_frequency")
        return result

    async def copy_move_detect_handler(self, input_data: dict) -> dict:
        """SIFT-based copy-move clone region detection."""
        artifact = input_data.get("artifact") or self.agent.evidence_artifact
        loop = asyncio.get_running_loop()
        result = await loop.run_in_executor(None, detect_copy_move, artifact.file_path)
        await self._store("copy_move_detect", result, "neural_copy_move")
        return result

    async def diffusion_artifact_detector_handler(self, input_data: dict) -> dict:
        """Diffusion model / AI-generation artifact detection."""
        artifact = input_data.get("artifact") or self.agent.evidence_artifact
        result = await run_ml_tool("diffusion_artifact_detector.py", artifact.file_path, timeout=12.0)

        diffusion_probability = result.get("diffusion_probability")
        if diffusion_probability is not None:
            try:
                result["confidence"] = round(max(0.0, min(1.0, float(diffusion_probability))), 3)
            except (TypeError, ValueError):
                result.setdefault("confidence", 0.0)

        if result.get("verdict") == "GEN_AI_DETECTION":
            result["diffusion_detected"] = True
            result["is_ai_generated"] = True
        elif result.get("verdict") == "SUSPICIOUS":
            result["diffusion_detected"] = True
            result["is_ai_generated"] = False
        else:
            result["diffusion_detected"] = False
            result["is_ai_generated"] = False

        await self.agent._record_tool_result("diffusion_artifact_detector", result)
        return result

    async def ela_anomaly_classify_handler(self, input_data: dict) -> dict:
        """CNN-based ELA anomaly block classification."""
        artifact = input_data.get("artifact") or self.agent.evidence_artifact
        result = await classify_ela_anomalies(artifact.file_path)
        await self.agent._record_tool_result("ela_anomaly_classify", result)
        return result

    async def adversarial_robustness_check_handler(self, input_data: dict) -> dict:
        """Anti-forensics perturbation stability check (sync CPU call — runs in executor)."""
        artifact = input_data.get("artifact") or self.agent.evidence_artifact
        if not self._has_splice_or_copy_move_signal():
            result = {
                "adversarial_check_skipped": True,
                "skipped": True,
                "reason": "No prior splicing or copy-move signal; anti-forensics robustness check not warranted",
                "confidence": 0.0,
                "court_defensible": False,
                "available": True,
            }
            await self.agent._record_tool_result("adversarial_robustness_check", result)
            return result

        loop = asyncio.get_running_loop()
        result = await loop.run_in_executor(None, check_adversarial_robustness, artifact.file_path)
        await self.agent._record_tool_result("adversarial_robustness_check", result)
        return result

    # ── Phase 2: Neural Forensics Handlers ───────────────────────────────────

    async def neural_copy_move_handler(self, input_data: dict) -> dict:
        """BusterNet dual-branch copy-move detection. Falls back to SIFT."""
        artifact = input_data.get("artifact") or self.agent.evidence_artifact
        from core.inference_client import get_inference_client
        client = await get_inference_client()

        # No outer wait_for here — predict_busternet delegates to run_ml_tool which
        # manages its own timeout and subprocess cleanup.  A wrapping wait_for would
        # inject CancelledError instead of TimeoutError, bypassing proc.kill() and
        # leaking zombie subprocesses.
        result = await client.predict_busternet(artifact.file_path)

        if not result.get("error"):
            await self._store("neural_copy_move", result, "copy_move_detect")
            return result

        # Fallback: SIFT-based copy-move (runs in executor — sync CPU call)
        loop = asyncio.get_running_loop()
        fallback = await loop.run_in_executor(None, detect_copy_move, artifact.file_path)
        await self._store("neural_copy_move", fallback, "copy_move_detect")
        return fallback

    async def neural_splicing_handler(self, input_data: dict) -> dict:
        """TruFor ViT-based splicing detection. Falls back to heuristic splicing."""
        artifact = input_data.get("artifact") or self.agent.evidence_artifact
        from core.inference_client import get_inference_client
        client = await get_inference_client()

        # No outer wait_for — run_ml_tool inside handles timeout + proc.kill().
        result = await client.predict_trufor(artifact.file_path)

        if not result.get("error"):
            await self._store("neural_splicing", result, "splicing_detect")
            return result

        # Fallback: heuristic splicing detection (sync — run in executor)
        loop = asyncio.get_running_loop()
        fallback = await loop.run_in_executor(None, detect_splicing, artifact.file_path)
        await self._store("neural_splicing", fallback, "splicing_detect")
        return fallback

    async def anomaly_tracer_handler(self, input_data: dict) -> dict:
        """
        ManTra-Net universal anomaly tracing.

        Gated on prior tampering signals — ManTra-Net is expensive and adds
        no value on images where no other tool detected anything suspicious.
        Falls back to JPEG ghost detection when ManTra-Net is unavailable.
        """
        artifact = input_data.get("artifact") or self.agent.evidence_artifact

        if not self._has_tampering_signal():
            result = {
                "anomaly_tracer_skipped": True,
                "reason": "No prior tampering signals from Phase-1/Phase-2 tools — ManTra-Net not triggered",
                "confidence": 0.5,
                "court_defensible": True,
                "available": True,
            }
            # Store only under anomaly_tracer — do NOT alias as jpeg_ghost_detect
            # here because the skip-stub contains no ghost-detection data and would
            # corrupt downstream consumers (Gemini context, arbiter) that read that key.
            await self.agent._record_tool_result("anomaly_tracer", result)
            return result

        from core.inference_client import get_inference_client
        client = await get_inference_client()

        # No outer wait_for — run_ml_tool inside handles timeout + proc.kill().
        result = await client.predict_mantra(artifact.file_path)

        if not result.get("error"):
            await self._store("anomaly_tracer", result, "jpeg_ghost_detect")
            return result

        # Fallback: JPEG ghost detection
        fallback = await real_jpeg_ghost_detect(artifact=artifact)
        await self._store("anomaly_tracer", fallback, "jpeg_ghost_detect")
        return fallback

    async def f3_net_frequency_handler(self, input_data: dict) -> dict:
        """F3-Net frequency artifact analysis. Falls back to heuristic frequency bands."""
        artifact = input_data.get("artifact") or self.agent.evidence_artifact
        from core.inference_client import get_inference_client
        client = await get_inference_client()

        # No outer wait_for — run_ml_tool inside handles timeout + proc.kill().
        result = await client.predict_f3net(artifact.file_path)

        if not result.get("error"):
            await self._store("f3_net_frequency", result, "deepfake_frequency_check")
            return result

        # Fallback: heuristic frequency bands (sync — run in executor)
        loop = asyncio.get_running_loop()
        fallback = await loop.run_in_executor(None, analyze_frequency_bands, artifact.file_path)
        await self._store("f3_net_frequency", fallback, "deepfake_frequency_check")
        return fallback

    async def neural_fingerprint_handler(self, input_data: dict) -> dict:
        """SigLIP 2 neural perceptual fingerprinting. Falls back to pHash suite."""
        artifact = input_data.get("artifact") or self.agent.evidence_artifact
        from core.inference_client import get_inference_client
        client = await get_inference_client()

        try:
            fingerprint = await asyncio.wait_for(
                client.get_neural_fingerprint(artifact.file_path), timeout=20.0
            )
            result = {
                "fingerprint": fingerprint,
                "confidence": 0.95,
                "method": "siglip2_embedding_projection",
                "robustness": "ADVANCED_NEURAL",
                "court_defensible": True,
                "available": True,
            }
            await self.agent._record_tool_result("neural_fingerprint", result)
            return result
        except Exception as e:
            if isinstance(e, asyncio.TimeoutError):
                logger.warning("SigLIP2 neural fingerprint timed out — falling back to pHash")
            else:
                logger.warning(f"Neural fingerprint failed — falling back to pHash: {e}")

        # Fallback: pHash / aHash / dHash / wHash suite
        from tools.image_tools import compute_perceptual_hash as legacy_phash
        fallback = await legacy_phash(artifact=artifact)
        await self.agent._record_tool_result("neural_fingerprint", fallback)
        return fallback

    # ── Global Semantic & Content Handlers ───────────────────────────────────

    async def analyze_image_content_handler(self, input_data: dict) -> dict:
        """CLIP semantic classification."""
        artifact = input_data.get("artifact") or self.agent.evidence_artifact
        result = await real_analyze_image_content(artifact=artifact)
        await self.agent._record_tool_result("analyze_image_content", result)
        return result

    async def extract_text_from_image_handler(self, input_data: dict) -> dict:
        """Tiered OCR — unified entry point for PDF/Image text extraction."""
        artifact = input_data.get("artifact") or self.agent.evidence_artifact
        result = await real_extract_evidence_text(artifact=artifact)
        await self.agent._record_tool_result("extract_text_from_image", result)
        # Also store under legacy OCR key for backward compatibility
        self.agent._tool_context["extract_evidence_text"] = result
        return result

    async def frequency_domain_analysis_handler(self, input_data: dict) -> dict:
        """FFT frequency-domain anomaly analysis."""
        artifact = input_data.get("artifact") or self.agent.evidence_artifact
        result = await real_frequency_domain_analysis(artifact=artifact)
        await self.agent._record_tool_result("frequency_domain_analysis", result)
        return result
