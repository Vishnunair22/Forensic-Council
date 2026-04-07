"""
Agent 1 — Image Integrity Agent.

Pixel-level forensic expert for detecting manipulation, splicing,
compositing, and anti-forensics evasion.
"""

from __future__ import annotations

import os

from PIL import Image

from agents.base_agent import ForensicAgent

# Core Forensic Engines
from core.forensics.ela import check_adversarial_robustness, classify_ela_anomalies
from core.forensics.frequency import analyze_frequency_bands
from core.forensics.noise import analyze_noise_consistency
from core.forensics.sift import detect_copy_move
from core.forensics.splicing import detect_splicing
from core.gemini_client import GeminiVisionClient
from core.image_utils import is_lossless_image
from core.ml_subprocess import run_ml_tool
from core.structured_logging import get_logger
from core.tool_registry import ToolRegistry
from tools.image_tools import (
    analyze_image_content as real_analyze_image_content,
)
from tools.image_tools import (
    compute_perceptual_hash as real_compute_perceptual_hash,
)

# Import real tool implementations
from tools.image_tools import (
    ela_full_image as real_ela_full_image,
)
from tools.image_tools import (
    extract_text_from_image as real_extract_text_from_image,
)
from tools.image_tools import (
    file_hash_verify as real_file_hash_verify,
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
from tools.ocr_tools import extract_evidence_text as real_extract_evidence_text

logger = get_logger(__name__)

class Agent1Image(ForensicAgent):
    """
    Agent 1 — Image Integrity Agent.

    Mandate: Detect manipulation, splicing, compositing, and anti-forensics
    evasion at the pixel level.
    """

    @property
    def agent_name(self) -> str:
        return "Agent1_ImageIntegrity"

    @property
    def _is_lossless(self) -> bool:
        file_path = getattr(self.evidence_artifact, "file_path", "") or ""
        mime = getattr(self.evidence_artifact, "mime_type", "") or ""
        return is_lossless_image(file_path, mime or None)

    @property
    def iteration_ceiling(self) -> int:
        """Maximum iterations — tasks + 2 buffer to prevent runaway loops."""
        return len(self.task_decomposition) + 2

    @property
    def task_decomposition(self) -> list[str]:
        base = [
            "Perform semantic image understanding to identify image type and context",
            "Run frequency-domain GAN artifact detection",
            "Compute perceptual hash for similarity detection",
        ]
        if self._is_lossless:
            return base + [
                "Run noise footprint analysis for region source inconsistency",
            ]
        else:
            return base + [
                "Run full-image ELA and map anomaly regions",
                "Perform ELA anomaly block classification",
                "Run JPEG ghost detection",
            ]

    @property
    def deep_task_decomposition(self) -> list[str]:
        """
        [2026 EDITION] Heavy forensic pass.
        Runs Diffusion detection and Gemini 3.1 Semantic Grounding.
        """
        return [
            "Run 2026 Diffusion Artifact Detector for generative AI residues",
            "Perform Gemini 3.1 Semantic Grounding on suspicious ELA/noise regions",
            "Self-reflection pass",
        ]

    async def build_tool_registry(self) -> ToolRegistry:
        registry = ToolRegistry()

        # ── Standard Tool Handlers ───────────────────────────────────────────

        async def ela_full_image_handler(input_data: dict) -> dict:
            artifact = input_data.get("artifact") or self.evidence_artifact
            result = await real_ela_full_image(
                artifact=artifact,
                evidence_store=input_data.get("evidence_store"),
                quality=input_data.get("quality", 95),
                anomaly_threshold=input_data.get("anomaly_threshold", 10.0),
            )
            await (self._record_tool_error("ela_full_image", result["error"]) if result.get("error") else self._record_tool_result("ela_full_image", result))
            return result

        async def roi_extract_handler(input_data: dict) -> dict:
            artifact = input_data.get("artifact") or self.evidence_artifact
            try:
                img = Image.open(artifact.file_path)
                w, h = img.size
                cx, cy = w // 2, h // 2
                crop_size = min(w, h) // 4
                bounding_box = input_data.get("bounding_box", {"x": max(0, cx-crop_size), "y": max(0, cy-crop_size), "w": crop_size*2, "h": crop_size*2})
            except Exception:
                bounding_box = input_data.get("bounding_box", {"x": 0, "y": 0, "w": 100, "h": 100})
            return await real_roi_extract(artifact=artifact, bounding_box=bounding_box, evidence_store=input_data.get("evidence_store"))

        async def jpeg_ghost_detect_handler(input_data: dict) -> dict:
            artifact = input_data.get("artifact") or self.evidence_artifact
            result = await real_jpeg_ghost_detect(artifact=artifact, quality_levels=input_data.get("quality_levels"), ghost_threshold=input_data.get("ghost_threshold", 5.0))
            await (self._record_tool_error("jpeg_ghost_detect", result["error"]) if result.get("error") else self._record_tool_result("jpeg_ghost_detect", result))
            return result

        # ── Refactored Core Forensic Handlers ────────────────────────────────

        async def ela_anomaly_classify_handler(input_data: dict) -> dict:
            artifact = input_data.get("artifact") or self.evidence_artifact
            if self._is_lossless:
                return {"ela_not_applicable": True, "anomaly_detected": False, "available": True}

            result = await run_ml_tool("ela_anomaly_classifier.py", artifact.file_path, extra_args=["--quality", str(input_data.get("quality", 95))], timeout=10.0)
            if not result.get("error") and result.get("available"):
                await self._record_tool_result("ela_anomaly_classify", result)
                return result

            p_ela = self._tool_context.get("ela_full_image", {})
            res = await classify_ela_anomalies(artifact.file_path, input_data.get("quality", 95), p_ela.get("ela_mean"))
            await self._record_tool_result("ela_anomaly_classify", res)
            return res

        async def splicing_detect_handler(input_data: dict) -> dict:
            artifact = input_data.get("artifact") or self.evidence_artifact
            result = await run_ml_tool("splicing_detector.py", artifact.file_path, timeout=10.0)
            return result if (not result.get("error") and result.get("available")) else detect_splicing(artifact.file_path)

        async def noise_fingerprint_handler(input_data: dict) -> dict:
            artifact = input_data.get("artifact") or self.evidence_artifact
            if self._is_lossless:
                return {"noise_fingerprint_not_applicable": True, "verdict": "NOT_APPLICABLE", "available": True}

            regions = input_data.get("regions", 4)
            result = await run_ml_tool("noise_fingerprint.py", artifact.file_path, extra_args=["--regions", str(regions)], timeout=10.0)
            if not result.get("error") and result.get("available"):
                await self._record_tool_result("noise_fingerprint", result)
                return result

            res = analyze_noise_consistency(artifact.file_path, regions)
            await self._record_tool_result("noise_fingerprint", res)
            return res

        async def deepfake_frequency_check_handler(input_data: dict) -> dict:
            artifact = input_data.get("artifact") or self.evidence_artifact
            res = analyze_frequency_bands(artifact.file_path)
            await self._record_tool_result("deepfake_frequency_check", res)
            return res

        async def copy_move_detect_handler(input_data: dict) -> dict:
            artifact = input_data.get("artifact") or self.evidence_artifact
            result = await run_ml_tool("copy_move_detector.py", artifact.file_path, timeout=15.0)
            return result if (not result.get("error") and result.get("available")) else detect_copy_move(artifact.file_path)

        async def adversarial_robustness_check_handler(input_data: dict) -> dict:
            artifact = input_data.get("artifact") or self.evidence_artifact
            return check_adversarial_robustness(artifact.file_path)

        # ── Registration ─────────────────────────────────────────────────────

        registry.register("ela_full_image", ela_full_image_handler, "Full-image ELA")
        registry.register("roi_extract", roi_extract_handler, "ROI extraction")
        registry.register("jpeg_ghost_detect", jpeg_ghost_detect_handler, "JPEG ghost detect")
        registry.register("ela_anomaly_classify", ela_anomaly_classify_handler, "ELA block classification")
        registry.register("splicing_detect", splicing_detect_handler, "Composition detection")
        registry.register("noise_fingerprint", noise_fingerprint_handler, "Noise consistency")
        registry.register("deepfake_frequency_check", deepfake_frequency_check_handler, "GAN artifact check")
        registry.register("copy_move_detect", copy_move_detect_handler, "SIFT copy-move check")
        registry.register("adversarial_robustness_check", adversarial_robustness_check_handler, "ELA stability check")

        # Wrapped tools
        registry.register("file_hash_verify", self._wrap_tool(real_file_hash_verify), "Hash verification")
        registry.register("perceptual_hash", self._wrap_tool(real_compute_perceptual_hash), "PHash computation")
        registry.register("frequency_domain_analysis", self._wrap_tool(real_frequency_domain_analysis), "FFT analysis")
        registry.register("extract_text_from_image", self._wrap_tool(real_extract_text_from_image), "OCR extraction")
        registry.register("extract_evidence_text", self._wrap_tool(real_extract_evidence_text), "Evidence text extraction")
        registry.register("analyze_image_content", self._wrap_tool(real_analyze_image_content), "CLIP semantic check")

        # ── 2026 Tools ───────────────────────────────────────────────────────

        async def diffusion_artifact_detector_handler(input_data: dict) -> dict:
            artifact = input_data.get("artifact") or self.evidence_artifact
            result = await run_ml_tool("diffusion_artifact_detector.py", artifact.file_path, timeout=12.0)
            if not result.get("error") and result.get("available"):
                await self._record_tool_result("diffusion_artifact_detector", result)
            return result

        registry.register("diffusion_artifact_detector", diffusion_artifact_detector_handler, "Diffusion artifact check")

        # Gemini Handler
        _gemini = GeminiVisionClient(self.config)
        async def gemini_deep_forensic_handler(input_data: dict) -> dict:
            artifact = input_data.get("artifact") or self.evidence_artifact
            try:
                finding = await _gemini.deep_forensic_analysis(file_path=artifact.file_path)
                result = finding.to_finding_dict(self.agent_id)
                result["analysis_source"] = "gemini_vision"
                self._gemini_vision_result = result
                return result
            except Exception as e:
                await self._record_tool_error("gemini_deep_forensic", str(e))
                return {"error": str(e), "analysis_source": "gemini_vision"}

        registry.register("gemini_deep_forensic", gemini_deep_forensic_handler, "Gemini vision analysis")

        return registry

    def _wrap_tool(self, func):
        async def handler(input_data: dict):
            return await func(artifact=input_data.get("artifact") or self.evidence_artifact)
        return handler

    async def build_initial_thought(self) -> str:
        path = getattr(self.evidence_artifact, "file_path", "unknown")
        name = os.path.basename(path)
        return f"Starting image integrity analysis for {name}. I will run pixel-level diagnostics (ELA, FFT, SIFT) and deep vision analysis via Gemini."

    async def run_investigation(self):
        await self._initialize_working_memory()
        path = self.evidence_artifact.file_path.lower()
        if path.endswith((".wav", ".mp3", ".mp4", ".mov", ".avi")):
            from core.react_loop import AgentFinding
            return [AgentFinding(agent_id=self.agent_id, finding_type="Not Applicable", confidence_raw=1.0, status="CONFIRMED", reasoning_summary="File is audio/video; image analysis skipped.")]

        self._skip_memory_init = True
        self._tool_registry = await self.build_tool_registry()
        return await super().run_investigation()
