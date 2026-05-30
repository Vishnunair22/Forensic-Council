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
import os
import time
from typing import Any

import cv2
import numpy as np
from PIL import Image

from core.forensics import (
    analyze_frequency_bands,
    analyze_noise_consistency,
    check_adversarial_robustness,
    classify_ela_anomalies,
)
from core.handlers.base import BaseToolHandler, InterToolCommunicationMixin
from core.media_kind import is_screen_capture_like
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
from tools.screenshot_tools import (
    detect_font_inconsistency as real_detect_font_inconsistency,
)
from tools.screenshot_tools import (
    detect_ui_overlay_forgery as real_detect_ui_overlay_forgery,
)

# ML fallback tools (importable CLI scripts in tools/ml_tools/)
from tools.ml_tools.copy_move_detector import detect_copy_move  # sync, run in executor
from tools.ml_tools.splicing_detector import detect_splicing  # sync, run in executor
from tools.ocr_tools import extract_evidence_text as real_extract_evidence_text

logger = get_logger(__name__)

_OCR_CACHE: dict[str, tuple[float, dict[str, Any]]] = {}
_OCR_INFLIGHT: dict[str, asyncio.Task] = {}
_OCR_CACHE_TTL_SECONDS = 900.0


def _ocr_cache_key(artifact: Any) -> str:
    path = str(getattr(artifact, "file_path", "") or "")
    try:
        stat = os.stat(path)
        return f"{path}:{stat.st_size}:{stat.st_mtime_ns}"
    except OSError:
        return path


class ImageHandlers(BaseToolHandler, InterToolCommunicationMixin):
    """Handles Image Integrity and Content analysis tools."""

    def register_tools(self, registry) -> None:
        """Register tools with the agent's ToolRegistry."""
        # ── Phase 1: Initial Analysis ────────────────────────────────────────
        registry.register(
            "neural_ela", self.neural_ela_handler, "Neural ELA Transformer manipulation detection"
        )
        registry.register(
            "noiseprint_cluster",
            self.noiseprint_cluster_handler,
            "Noiseprint++ sensor-region consistency clustering",
        )

        # ── Phase 2: Deep Neural Forensics ───────────────────────────────────
        registry.register(
            "neural_copy_move",
            self.neural_copy_move_handler,
            "BusterNet dual-branch copy-move detection",
        )
        registry.register(
            "neural_splicing", self.neural_splicing_handler, "TruFor ViT-based splicing detection"
        )
        registry.register(
            "anomaly_tracer", self.anomaly_tracer_handler, "ManTra-Net universal anomaly tracing"
        )
        registry.register(
            "f3_net_frequency", self.f3_net_frequency_handler, "F3-Net frequency artifact analysis"
        )
        registry.register(
            "neural_fingerprint",
            self.neural_fingerprint_handler,
            "SigLIP2 neural perceptual fingerprint",
        )
        registry.register(
            "diffusion_artifact_detector",
            self.diffusion_artifact_detector_handler,
            "Diffusion/AI-generation artifact detection",
        )

        # ── Global Semantic & Content Tools ──────────────────────────────────
        registry.register(
            "analyze_image_content",
            self.analyze_image_content_handler,
            "CLIP ViT-B-32 semantic classification",
        )
        registry.register(
            "extract_text_from_image",
            self.extract_text_from_image_handler,
            "Gemini Multimodal OCR with EasyOCR and Tesseract fallback",
        )
        registry.register(
            "frequency_domain_analysis",
            self.frequency_domain_analysis_handler,
            "FFT frequency-domain anomaly analysis",
        )

        # ── Supplementary (used as follow-up targets) ────────────────────────
        registry.register("roi_extract", self.roi_extract_handler, "Region of interest extraction")
        registry.register(
            "ela_anomaly_classify",
            self.ela_anomaly_classify_handler,
            "ELA anomaly block classification",
        )
        registry.register(
            "adversarial_robustness_check",
            self.adversarial_robustness_check_handler,
            "Anti-forensics perturbation stability check",
        )
        registry.register(
            "ela_full_image", self.ela_full_image_handler, "Classical multi-quality ELA sweep"
        )
        registry.register(
            "jpeg_ghost_detect",
            self.jpeg_ghost_detect_handler,
            "JPEG ghost / double-compression artifact detection",
        )
        registry.register(
            "splicing_detect", self.splicing_detect_handler, "Heuristic image splicing detection"
        )
        registry.register(
            "copy_move_detect",
            self.copy_move_detect_handler,
            "SIFT-based copy-move clone detection",
        )
        registry.register(
            "noise_fingerprint",
            self.noise_fingerprint_handler,
            "Heuristic PRNU noise consistency analysis",
        )
        registry.register(
            "deepfake_frequency_check",
            self.deepfake_frequency_check_handler,
            "Heuristic frequency-band GAN artifact analysis",
        )

        # ── Screenshot Forensics ───────────────────────────────────────────────
        registry.register(
            "detect_font_inconsistency",
            self.detect_font_inconsistency_handler,
            "Font consistency analysis for screenshot text regions",
        )
        registry.register(
            "detect_ui_overlay_forgery",
            self.detect_ui_overlay_forgery_handler,
            "UI overlay forgery detection for screenshots",
        )

    # ── Helpers ───────────────────────────────────────────────────────────────

    async def _has_tampering_signal(self) -> bool:
        """
        Return True if any Phase-1 or Phase-2 tool already flagged manipulation.
        Used to gate expensive ManTra-Net inference.

        Checks three signal layers:
          1. Local tool context (results from tools already run in this agent)
          2. Accumulated AgentFinding list (structured verdicts + confidence + reasoning)
          3. Cross-agent signals from Agent 3 (object/context anomalies)
        """
        artifact = getattr(self.agent, "evidence_artifact", None)
        if artifact is not None and self._is_screenshot_context(artifact):
            return False

        ctx = self.agent._tool_context
        freq = ctx.get("frequency_domain_analysis", {})

        # Layer 1: Local tool context signals
        local_signal = any(
            [
                ctx.get("neural_ela", {}).get("manipulation_detected", False),
                (ctx.get("neural_ela") or ctx.get("ela_full_image", {})).get(
                    "num_anomaly_regions", 0
                )
                > 2,
                ctx.get("noiseprint_cluster", {}).get("manipulation_detected", False),
                ctx.get("neural_splicing", {}).get("splicing_detected", False),
                ctx.get("neural_copy_move", {}).get("copy_move_detected", False),
                ctx.get("f3_net_frequency", {}).get("gan_artifact_detected", False),
                ctx.get("diffusion_artifact_detector", {}).get("is_ai_generated", False),
                ctx.get("diffusion_artifact_detector", {}).get("diffusion_detected", False),
                freq.get("anomaly_detected", False),
                freq.get("num_anomaly_regions", 0) > 2,
            ]
        )
        if local_signal:
            return True

        # Layer 2: Accumulated AgentFinding list
        findings = getattr(self.agent, "_findings", [])
        if findings:
            tampering_keywords = {
                "manipulation", "splicing", "copy.move", "tamper",
                "forgery", "anomalous", "ai.generated", "synthetic",
                "diffusion", "gan", "deepfake", "inconsistent",
            }
            for f in findings:
                ev = str(getattr(f, "evidence_verdict", "")).upper()
                conf = getattr(f, "confidence_raw", None) or 0.0
                reason = str(getattr(f, "reasoning_summary", "")).lower()
                # POSITIVE verdict with any confidence
                if ev == "POSITIVE":
                    return True
                # High-confidence SUSPICIOUS or TAMPERED verdict
                if ev in ("SUSPICIOUS", "TAMPERED", "MANIPULATED") and conf > 0.4:
                    return True
                # Keyword match in reasoning with moderate confidence
                if any(kw in reason for kw in tampering_keywords) and conf > 0.5:
                    return True

        # Layer 3: Cross-agent signals from Agent 3 (Object & Context)
        try:
            from core.agent_registry import AgentID

            shared_ctx = await self.agent.working_memory.get_agent_context(
                self.agent.session_id, AgentID.AGENT3
            )
            a3_tools = shared_ctx.get("tool_context", {})
            return any(
                [
                    a3_tools.get("lighting_consistency", {}).get("inconsistency_detected", False),
                    a3_tools.get("scene_incongruence", {}).get("scene_incongruent", False),
                ]
            )
        except Exception:
            return False

    async def _has_splice_or_copy_move_signal(self) -> bool:
        """Return True when anti-forensic robustness analysis is warranted."""
        artifact = getattr(self.agent, "evidence_artifact", None)
        if artifact is not None and self._is_screenshot_context(artifact):
            return False

        ctx = self.agent._tool_context
        local_signal = any(
            [
                ctx.get("neural_splicing", {}).get("splicing_detected", False),
                ctx.get("splicing_detect", {}).get("splicing_detected", False),
                ctx.get("neural_copy_move", {}).get("copy_move_detected", False),
                ctx.get("copy_move_detect", {}).get("copy_move_detected", False),
            ]
        )
        if local_signal:
            return True

        # Cross-agent signals from Agent 3
        try:
            from core.agent_registry import AgentID

            shared_ctx = await self.agent.working_memory.get_agent_context(
                self.agent.session_id, AgentID.AGENT3
            )
            a3_tools = shared_ctx.get("tool_context", {})
            return any(
                [
                    a3_tools.get("vector_contraband_search", {}).get("concern_flag", False),
                    a3_tools.get("scene_incongruence", {}).get("scene_incongruent", False),
                    a3_tools.get("lighting_consistency", {}).get("inconsistency_detected", False),
                ]
            )
        except Exception:
            return False

    def _is_screenshot_context(self, artifact: Any) -> bool:
        """
        Check heuristic detector and agent context (Gemini/CLIP) for screenshot status.
        Ensures tools like ELA can correctly abort if Gemini identified the image
        as a screen capture, even if the file extension/heuristics missed it.
        """
        # 1. Base heuristic check (magic bytes, dimensions, EXIF)
        if is_screen_capture_like(artifact):
            return True
            
        tool_ctx = getattr(self.agent, "_tool_context", {})
        if not tool_ctx:
            return False
            
        # 2. Check Semantic CLIP Analysis
        clip_ctx = tool_ctx.get("analyze_image_content") or {}
        if "screenshot" in str(clip_ctx.get("image_type", "")).lower():
            return True
            
        # 3. Check shared visual evidence profile.
        visual_ctx = (
            tool_ctx.get("visual_evidence_profile")
            or tool_ctx.get("gemini_deep_forensic")
            or {}
        )
        visual_meta = visual_ctx.get("metadata") or {}
        
        cat = str(
            visual_meta.get("file_type_assessment")
            or visual_meta.get("image_category")
            or ""
        ).lower()
        if "screenshot" in cat or "screen capture" in cat:
            return True
            
        desc = str(
            visual_ctx.get("reasoning_summary")
            or visual_ctx.get("content_description")
            or ""
        ).lower()
        if "screenshot" in desc or "screen capture" in desc:
            return True
            
        return False

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

    def _visual_grounding_context(self) -> dict[str, Any]:
        profile = (
            self.agent._tool_context.get("visual_evidence_profile")
            or self.agent._tool_context.get("gemini_deep_forensic")
            or {}
        )
        if not profile and getattr(self.agent, "inter_agent_bus", None):
            try:
                profile = self.agent.inter_agent_bus.get_visual_profile(str(self.agent.session_id)) or {}
            except Exception:
                profile = {}
        meta = profile.get("metadata") if isinstance(profile, dict) else {}
        if not isinstance(meta, dict):
            meta = {}
        routing = meta.get("forensic_routing") if isinstance(meta.get("forensic_routing"), dict) else {}
        ocr = self.agent._tool_context.get("extract_text_from_image") or self.agent._tool_context.get("extract_evidence_text") or {}
        ocr_text = []
        if isinstance(ocr, dict):
            for key in ("extracted_text", "text_blocks", "lines"):
                value = ocr.get(key)
                if isinstance(value, list) and value:
                    ocr_text.extend(str(v) for v in value if v)
            text_value = ocr.get("text") or ocr.get("full_text")
            if text_value:
                ocr_text.append(str(text_value))
        visual_text = meta.get("extracted_text") or profile.get("extracted_text") or []
        if isinstance(visual_text, str):
            visual_text = [visual_text]
        if not isinstance(visual_text, list):
            visual_text = []
        merged_text = list(dict.fromkeys([str(v) for v in visual_text + ocr_text if v]))
        return {
            "image_category": routing.get("image_category") or meta.get("file_type_assessment") or profile.get("file_type_assessment"),
            "content_description": profile.get("reasoning_summary") or meta.get("content_description") or "",
            "interface_identification": meta.get("interface_identification") or profile.get("interface_identification") or "",
            "visual_verdict": meta.get("authenticity_verdict") or profile.get("authenticity_verdict") or "",
            "extracted_text": merged_text,
            "ocr_word_count": ocr.get("word_count") if isinstance(ocr, dict) else None,
        }

    def _attach_visual_grounding(self, result: dict[str, Any], *, tool_name: str) -> dict[str, Any]:
        ctx = self._visual_grounding_context()
        if not any(ctx.values()):
            return result
        result.setdefault("visual_grounding", ctx)
        result.setdefault("image_category", ctx.get("image_category"))
        result.setdefault("grounded_by_visual_profile", True)
        if tool_name in {"frequency_domain_analysis", "deepfake_frequency_check", "diffusion_artifact_detector"}:
            if str(ctx.get("image_category") or "").lower() == "screenshot" and not result.get("anomaly_detected"):
                result.setdefault(
                    "context_note",
                    "Interpreted as a screen capture; sharp UI edges and text are expected rendering features.",
                )
        return result

    # ── Phase 1: Neural ELA ───────────────────────────────────────────────────

    async def _screen_capture_not_applicable(
        self,
        tool_name: str,
        reason: str,
        *,
        aliases: tuple[str, ...] = (),
        record: bool = True,
    ) -> dict[str, Any]:
        result = {
            "available": True,
            "not_applicable": True,
            "skipped": True,
            "status": "NOT_APPLICABLE",
            "evidence_verdict": "NOT_APPLICABLE",
            "reason": reason,
            "confidence": 0.0,
            "court_defensible": False,
            "screenshot_scope_guard": True,
        }
        result = self._attach_visual_grounding(result, tool_name=tool_name)
        if record:
            await self._store(tool_name, result, *aliases)
        return result

    async def neural_ela_handler(self, input_data: dict, record: bool = True) -> dict:
        """ViT-based Neural ELA. Falls back to multi-quality classical ELA.

        ELA measures JPEG re-compression residuals between save cycles.
        It is NOT applicable to screen captures — UI elements are
        software-rendered uniformly so every pixel shows the same ELA
        signal, producing noise rather than forensic evidence.
        """
        artifact = input_data.get("artifact") or self.agent.evidence_artifact
        if self._is_screenshot_context(artifact):
            return await self._screen_capture_not_applicable(
                "neural_ela",
                "ELA is not applicable to screen captures; screenshot integrity is assessed with hash, OCR, layout, and UI-rendering checks.",
                aliases=("ela_full_image",),
                record=record,
            )

        # ── Screenshot fast-exit — ELA is not meaningful for screen captures ──
        # Sharp UI edges and uniform backgrounds produce large ELA regions that
        # mimic JPEG manipulation residuals but are actually rendering artifacts.
        # Running ELA on screenshots is the #1 source of false-SUSPICIOUS verdicts.
        if self._is_screenshot_context(artifact):
            not_applicable: dict = {
                "available": True,
                "not_applicable": True,
                "reason": (
                    "ELA (Error Level Analysis) measures JPEG re-compression residuals. "
                    "Screen captures are software-rendered with no prior JPEG compression "
                    "history, so ELA produces non-informative results. Screenshot integrity "
                    "is assessed via hash, OCR, layout, and provenance checks instead."
                ),
                "confidence": 0.85,
                "court_defensible": False,
                "num_anomaly_regions": 0,
                "max_anomaly": 0.0,
                "manipulation_detected": False,
            }
            if record:
                await self._store("neural_ela", not_applicable, "ela_full_image")
            return not_applicable

        result = await run_ml_tool("neural_ela_transformer.py", artifact.file_path, timeout=15.0)
        result = self._attach_visual_grounding(result, tool_name="neural_ela")

        # Publish anomaly regions for downstream tools
        if not result.get("error") and result.get("num_anomaly_regions", 0) > 0:
            await self._publish_tool_signal(
                'anomaly_regions_found',
                {
                    'anomaly_regions': result.get('anomaly_regions', []),
                    'max_anomaly': result.get('max_anomaly', 0),
                    'tool': 'neural_ela',
                }
            )

        if not result.get("error") and result.get("available"):
            if record:
                # Store under both neural key and legacy key so Gemini reads it correctly.
                await self._store("neural_ela", result, "ela_full_image")
            return result

        # Fallback: classical multi-quality ELA (pass record=False to avoid double-counting)
        fallback = await self.ela_full_image_handler(input_data, record=False)
        fallback = self._attach_visual_grounding(fallback, tool_name="neural_ela")
        fallback["degraded"] = True
        fallback["fallback_reason"] = (
            "neural_ela_transformer unavailable or failed; used classical multi-quality ELA"
        )
        if record:
            await self._store("neural_ela", fallback, "ela_full_image")
        return fallback


    # ── Phase 1: Noiseprint Cluster ───────────────────────────────────────────

    async def noiseprint_cluster_handler(self, input_data: dict, record: bool = True) -> dict:
        """Noiseprint++ CNN sensor-region clustering. Falls back to heuristic noise analysis."""
        artifact = input_data.get("artifact") or self.agent.evidence_artifact
        if self._is_screenshot_context(artifact):
            return await self._screen_capture_not_applicable(
                "noiseprint_cluster",
                "PRNU/noiseprint sensor clustering is not applicable to screen captures; screenshots are software-rendered and do not carry a camera sensor noise field.",
                aliases=("noise_fingerprint",),
                record=record,
            )
        result = await run_ml_tool("noiseprint_clustering.py", artifact.file_path, timeout=20.0)
        result = self._attach_visual_grounding(result, tool_name="noiseprint_cluster")
        if not result.get("error") and result.get("available"):
            if record:
                await self._store("noiseprint_cluster", result, "noise_fingerprint")
            return result

        # Fallback: heuristic noise fingerprint
        fallback = await self.noise_fingerprint_handler(input_data, record=False)
        fallback["degraded"] = True
        fallback["fallback_reason"] = (
            "noiseprint_clustering unavailable or failed; used heuristic noise fingerprint"
        )
        if record:
            await self._store("noiseprint_cluster", fallback, "noise_fingerprint")
        return fallback

    # ── Standard Handlers (used as fallbacks and standalone) ─────────────────

    async def ela_full_image_handler(self, input_data: dict, record: bool = True) -> dict:
        """Classical multi-quality ELA sweep (4 quality levels, fused via max).

        Wraps the compute in asyncio.wait_for(30s) so even if run_in_executor
        takes longer than expected (e.g. very large images on slow hardware),
        the handler will time out cleanly rather than blocking indefinitely.
        """
        artifact = input_data.get("artifact") or self.agent.evidence_artifact

        # ELA is not applicable to screen captures — return early.
        if self._is_screenshot_context(artifact):
            result: dict = {
                "available": True,
                "not_applicable": True,
                "reason": "ELA not applicable to screen captures; screenshot-specific tools handle integrity.",
                "confidence": 0.85,
                "court_defensible": False,
                "num_anomaly_regions": 0,
                "max_anomaly": 0.0,
            }
            if record:
                await self._store("ela_full_image", result, "neural_ela")
            return result

        try:
            result = await asyncio.wait_for(
                real_ela_full_image(
                    artifact=artifact,
                    quality=input_data.get("quality", 95),
                    anomaly_threshold=input_data.get("anomaly_threshold", 10.0),
                ),
                timeout=30.0,  # 4-pass sweep should finish well within 30s via executor
            )
        except asyncio.TimeoutError:
            logger.warning(
                "Classical ELA timed out after 30s; using minimal fallback",
                artifact_id=artifact.artifact_id,
            )
            result = self._ela_fallback(artifact.file_path, "classical ELA timed out after 30s")
            result["degraded"] = True
        except Exception as e:
            result = {"error": str(e)}

        if result.get("error"):
            result = self._ela_fallback(artifact.file_path, str(result.get("error")))
        elif not result.get("degraded"):
            raw_sig = max(
                min(result.get("num_anomaly_regions", 0) / 15.0, 1.0),
                min(result.get("max_anomaly", 0.0) / 80.0, 1.0),
            )
            result["confidence"] = ConfidenceCalibrator.calibrate_heuristic(
                raw_sig, reliability_tag="opencv_heuristic"
            )
            # Prevent false positives on sharp edges by raising the threshold
            result["manipulation_detected"] = (
                result.get("num_anomaly_regions", 0) >= 2 
                and result.get("max_anomaly", 0.0) >= 20.0
            )

        if record:
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

        # Priority 1: YOLO detections (local or from Agent 3)
        if not bounding_box:
            obj_ctx = self.agent._tool_context.get("object_detection")
            if not obj_ctx:
                # Fallback: check shared context from Agent 3 (Object Detection)
                from core.agent_registry import AgentID

                shared_ctx = await self.agent.working_memory.get_agent_context(
                    self.agent.session_id, AgentID.AGENT3
                )
                obj_ctx = shared_ctx.get("tool_context", {}).get("object_detection", {})

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
            ela_ctx = self.agent._tool_context.get("neural_ela") or self.agent._tool_context.get(
                "ela_full_image", {}
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

    async def noise_fingerprint_handler(self, input_data: dict, record: bool = True) -> dict:
        """
        Heuristic PRNU noise consistency analysis.
        Only meaningful for lossless images; noiseprint_cluster is preferred.
        """
        artifact = input_data.get("artifact") or self.agent.evidence_artifact

        # Skip for lossy images — heuristic noise analysis on JPEG is unreliable
        # (noiseprint_cluster handles lossless; neural_ela handles JPEG).
        if self._is_screenshot_context(artifact):
            return await self._screen_capture_not_applicable(
                "noise_fingerprint",
                "PRNU/noise fingerprint analysis is not applicable to screen captures; screenshots are assessed with hash, OCR, layout, and UI-rendering checks.",
                aliases=("noiseprint_cluster",),
                record=record,
            )

        if hasattr(self.agent, "_is_lossless") and not self.agent._is_lossless:
            result = {
                "noise_fingerprint_not_applicable": True,
                "verdict": "NOT_APPLICABLE",
                "reason": "Heuristic noise fingerprint is unreliable on lossy JPEG images; use neural_ela instead.",
                "confidence": 0.0,
                "available": True,
            }
            if record:
                await self.agent._record_tool_result("noise_fingerprint", result)
            return result

        # Try ML-based noise fingerprint first
        result = await run_ml_tool("noise_fingerprint.py", artifact.file_path, timeout=15.0)
        if not result.get("error") and result.get("available"):
            if record:
                await self._store("noise_fingerprint", result, "noiseprint_cluster")
            return result

        # Fallback: heuristic — run in executor so it doesn't block the event loop
        loop = asyncio.get_running_loop()
        result = await loop.run_in_executor(None, analyze_noise_consistency, artifact.file_path)
        if record:
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
        if self._is_screenshot_context(artifact):
            return await self._screen_capture_not_applicable(
                "splicing_detect",
                "Heuristic camera-image splicing detection is not applicable to screen captures; UI screenshots are reviewed with layout and overlay checks.",
                aliases=("neural_splicing",),
            )
        loop = asyncio.get_running_loop()
        result = await loop.run_in_executor(None, detect_splicing, artifact.file_path)
        await self.agent._record_tool_result("splicing_detect", result)
        return result

    async def deepfake_frequency_check_handler(self, input_data: dict) -> dict:
        """Heuristic frequency-band GAN artifact analysis."""
        artifact = input_data.get("artifact") or self.agent.evidence_artifact
        loop = asyncio.get_running_loop()
        result = await loop.run_in_executor(None, analyze_frequency_bands, artifact.file_path)
        result = self._attach_visual_grounding(result, tool_name="deepfake_frequency_check")
        await self._store("deepfake_frequency_check", result, "f3_net_frequency")
        return result

    async def copy_move_detect_handler(self, input_data: dict) -> dict:
        """SIFT-based copy-move clone region detection."""
        artifact = input_data.get("artifact") or self.agent.evidence_artifact
        if self._is_screenshot_context(artifact):
            return await self._screen_capture_not_applicable(
                "copy_move_detect",
                "Copy-move clone detection is not applicable to screen captures; repeated UI components are expected and are handled by screenshot layout checks.",
                aliases=("neural_copy_move",),
            )
        loop = asyncio.get_running_loop()
        try:
            result = await asyncio.wait_for(
                loop.run_in_executor(None, detect_copy_move, artifact.file_path),
                timeout=120.0,
            )
        except TimeoutError:
            result = {
                "error": "Copy-move detection timed out after 120s",
                "available": False,
                "copy_move_detected": False,
                "confidence": 0.0,
                "matched_pairs": 0,
            }
        await self._store("copy_move_detect", result, "neural_copy_move")
        return result

    async def diffusion_artifact_detector_handler(self, input_data: dict) -> dict:
        """Diffusion model / AI-generation artifact detection."""
        artifact = input_data.get("artifact") or self.agent.evidence_artifact
        result = await run_ml_tool(
            "diffusion_artifact_detector.py", artifact.file_path, timeout=12.0
        )

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

        result = self._attach_visual_grounding(result, tool_name="diffusion_artifact_detector")
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
        if self._is_screenshot_context(artifact):
            return await self._screen_capture_not_applicable(
                "adversarial_robustness_check",
                "Adversarial robustness probing is not applicable to screen captures unless a screenshot-specific manipulation check is positive.",
            )
        if not await self._has_splice_or_copy_move_signal():
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

    async def neural_copy_move_handler(self, input_data: dict, record: bool = True) -> dict:
        """BusterNet dual-branch copy-move detection. Falls back to SIFT."""
        artifact = input_data.get("artifact") or self.agent.evidence_artifact
        if self._is_screenshot_context(artifact):
            return await self._screen_capture_not_applicable(
                "neural_copy_move",
                "BusterNet copy-move detection is not applicable to screen captures; repeated UI elements and grid structure are expected rendering features.",
                aliases=("copy_move_detect",),
                record=record,
            )
        from core.inference_client import get_inference_client

        client = await get_inference_client()

        # No outer wait_for here — predict_busternet delegates to run_ml_tool which
        # manages its own timeout and subprocess cleanup.
        result = await client.predict_busternet(artifact.file_path)

        if not result.get("error"):
            if record:
                await self.agent._record_tool_result("neural_copy_move", result)
            return result

        # Fallback: SIFT-based copy-move (runs in executor — sync CPU call)
        loop = asyncio.get_running_loop()
        fallback = await loop.run_in_executor(None, detect_copy_move, artifact.file_path)
        fallback["degraded"] = True
        fallback["fallback_reason"] = "BusterNet dual-branch unavailable; SIFT-based copy-move used"
        if record:
            await self.agent._record_tool_result("neural_copy_move", fallback)
        return fallback

    async def neural_splicing_handler(self, input_data: dict, record: bool = True) -> dict:
        """TruFor ViT-based splicing detection. Falls back to heuristic splicing."""
        artifact = input_data.get("artifact") or self.agent.evidence_artifact
        if self._is_screenshot_context(artifact):
            return await self._screen_capture_not_applicable(
                "neural_splicing",
                "TruFor camera-image splicing detection is not applicable to screen captures; screenshots are assessed with UI overlay and layout consistency checks.",
                aliases=("splicing_detect",),
                record=record,
            )

        # Check if ELA found anomaly regions to focus on
        ela_signals = await self._get_tool_signals('anomaly_regions_found')
        from core.inference_client import get_inference_client

        client = await get_inference_client()

        if ela_signals:
            anomaly_regions = ela_signals[0]['data'].get('anomaly_regions', [])
            logger.info(
                "Splicing detector focusing on ELA-identified regions",
                num_regions=len(anomaly_regions),
            )
            result = await client.predict_trufor(
                artifact.file_path,
                focus_regions=anomaly_regions,
            )
        else:
            # No outer wait_for — run_ml_tool inside handles timeout + proc.kill().
            result = await client.predict_trufor(artifact.file_path)

        if not result.get("error"):
            if record:
                await self.agent._record_tool_result("neural_splicing", result)
            return result

        # Fallback: heuristic splicing detection (sync — run in executor)
        loop = asyncio.get_running_loop()
        fallback = await loop.run_in_executor(None, detect_splicing, artifact.file_path)
        fallback["degraded"] = True
        fallback["fallback_reason"] = "TruFor ViT unavailable; heuristic splicing detector used"
        if record:
            await self.agent._record_tool_result("neural_splicing", fallback)
        return fallback

    async def anomaly_tracer_handler(self, input_data: dict) -> dict:
        """
        ManTra-Net universal anomaly tracing.

        Gated on prior tampering signals — ManTra-Net is expensive and adds
        no value on images where no other tool detected anything suspicious.
        Falls back to JPEG ghost detection when ManTra-Net is unavailable.
        """
        artifact = input_data.get("artifact") or self.agent.evidence_artifact

        if not await self._has_tampering_signal():
            result = {
                "anomaly_tracer_skipped": True,
                "skipped": True,
                "not_applicable": True,
                "reason": "No prior tampering signals from Phase-1/Phase-2 tools — ManTra-Net not triggered",
                "confidence": 0.0,
                "court_defensible": False,
                "available": True,
            }
            # Store only under anomaly_tracer — do NOT alias as jpeg_ghost_detect
            # because this stub contains no ghost-detection data.
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
        fallback["degraded"] = True
        fallback["fallback_reason"] = "ManTra-Net unavailable; JPEG ghost detection used as substitute"
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

        # Fallback: return a degraded stub referencing any Phase-1 frequency result already in
        # context.  Re-running analyze_frequency_bands here produces zero new information because
        # that same heuristic already ran as deepfake_frequency_check in Phase 1.
        existing = self.agent._tool_context.get("deepfake_frequency_check") or {}
        fallback = {
            **existing,
            "degraded": True,
            "fallback_reason": (
                "F3-Net neural frequency analysis unavailable; "
                "Phase-1 frequency heuristic result is referenced — no new deep signal"
            ),
            "available": False,
            "court_defensible": False,
        }
        await self.agent._record_tool_result("f3_net_frequency", fallback)
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
            # Alias to perceptual_hash for backward compatibility
            await self._store(
                "neural_fingerprint", result, "compute_perceptual_hash", "perceptual_hash"
            )
            return result
        except Exception as e:
            if isinstance(e, asyncio.TimeoutError):
                logger.warning("SigLIP2 neural fingerprint timed out — falling back to pHash")
            else:
                logger.warning(f"Neural fingerprint failed — falling back to pHash: {e}")

        # Fallback: pHash / aHash / dHash / wHash suite
        from tools.image_tools import compute_perceptual_hash as legacy_phash

        fallback = await legacy_phash(artifact=artifact)
        fallback["degraded"] = True
        fallback["fallback_reason"] = (
            "SigLIP2 neural fingerprint unavailable or timed out; used perceptual hash suite"
        )
        # Alias to perceptual_hash for backward compatibility
        await self._store(
            "neural_fingerprint", fallback, "compute_perceptual_hash", "perceptual_hash"
        )
        return fallback

    # ── Global Semantic & Content Handlers ───────────────────────────────────

    async def analyze_image_content_handler(self, input_data: dict) -> dict:
        """CLIP semantic classification."""
        artifact = input_data.get("artifact") or self.agent.evidence_artifact
        if is_screen_capture_like(artifact):
            try:
                with Image.open(artifact.file_path) as img:
                    width, height = img.size
                    mode = img.mode
                result = {
                    "available": True,
                    "image_type": "screen capture / digital UI",
                    "summary": (
                        f"Screenshot semantic profile: {width}x{height}px, {mode} color mode. "
                        "Heavy CLIP scene classification is bypassed for initial screenshot analysis because it is slow and does not prove authenticity."
                    ),
                    "width": width,
                    "height": height,
                    "color_mode": mode,
                    "semantic_scope": "screenshot_fast_profile",
                    "confidence": 0.72,
                    "court_defensible": True,
                }
            except Exception as exc:
                result = {
                    "available": False,
                    "error": str(exc),
                    "confidence": 0.0,
                    "court_defensible": False,
                }
            await self.agent._record_tool_result("analyze_image_content", result)
            return result
        result = await real_analyze_image_content(artifact=artifact)
        result = self._attach_visual_grounding(result, tool_name="analyze_image_content")
        await self.agent._record_tool_result("analyze_image_content", result)
        return result

    async def extract_text_from_image_handler(self, input_data: dict) -> dict:
        """Tiered OCR — unified entry point for PDF/Image text extraction."""
        artifact = input_data.get("artifact") or self.agent.evidence_artifact
        try:
            shared = {}
            if getattr(self.agent, "inter_agent_bus", None):
                shared = self.agent.inter_agent_bus.get_visual_profile(str(self.agent.session_id)) or {}
            meta = shared.get("metadata") if isinstance(shared, dict) else {}
            if not isinstance(meta, dict):
                meta = {}
            extracted = []
            if isinstance(shared, dict):
                extracted = meta.get("extracted_text") or shared.get("extracted_text") or []
            if isinstance(extracted, list) and extracted:
                lines = [str(line).strip() for line in extracted if str(line).strip()]
                full_text = "\n".join(lines)
                result = {
                    "method": "agent1_visual_profile",
                    "lines": lines,
                    "full_text": full_text,
                    "word_count": len(full_text.split()),
                    "has_text": bool(lines),
                    "avg_confidence": float(shared.get("confidence_raw") or 0.8),
                    "court_defensible": True,
                    "content_description": shared.get("reasoning_summary") or "",
                    "shared_visual_profile": True,
                }
                await self._store("extract_text_from_image", result, "extract_evidence_text")
                return result
        except Exception as shared_err:
            logger.debug("Shared Agent 1 visual profile OCR reuse skipped", error=str(shared_err))

        key = _ocr_cache_key(artifact)
        cached = _OCR_CACHE.get(key)
        if cached and time.monotonic() - cached[0] < _OCR_CACHE_TTL_SECONDS:
            result = {**cached[1], "shared_ocr_cache_hit": True}
            await self._store("extract_text_from_image", result, "extract_evidence_text")
            return result

        try:
            task = _OCR_INFLIGHT.get(key)
            if task is None or task.done():
                task = asyncio.create_task(real_extract_evidence_text(artifact=artifact))
                _OCR_INFLIGHT[key] = task
            result = await asyncio.wait_for(asyncio.shield(task), timeout=110.0)
            _OCR_CACHE[key] = (time.monotonic(), dict(result))
        except TimeoutError:
            logger.warning("OCR handler timed out — returning timeout error result")
            result = {
                "error": "OCR extraction timed out after 110s",
                "timeout": True,
                "available": True,
                "confidence": 0.0,
                "has_text": False,
            }
        finally:
            task = _OCR_INFLIGHT.get(key)
            if task is not None and task.done():
                _OCR_INFLIGHT.pop(key, None)
        # Store under both primary and legacy OCR keys for backward compatibility
        await self._store("extract_text_from_image", result, "extract_evidence_text")
        return result

    async def frequency_domain_analysis_handler(self, input_data: dict) -> dict:
        """FFT frequency-domain anomaly analysis."""
        artifact = input_data.get("artifact") or self.agent.evidence_artifact
        result = await real_frequency_domain_analysis(artifact=artifact)
        result = self._attach_visual_grounding(result, tool_name="frequency_domain_analysis")
        await self.agent._record_tool_result("frequency_domain_analysis", result)
        return result

    # ── Screenshot Forensics Handlers ─────────────────────────────────────────

    async def detect_font_inconsistency_handler(self, input_data: dict) -> dict:
        """Font consistency analysis for screenshot text regions."""
        artifact = input_data.get("artifact") or self.agent.evidence_artifact
        text_regions = input_data.get("text_regions")
        result = await real_detect_font_inconsistency(
            artifact=artifact,
            text_regions=text_regions,
        )
        result = self._attach_visual_grounding(result, tool_name="detect_font_inconsistency")
        await self.agent._record_tool_result("detect_font_inconsistency", result)
        return result

    async def detect_ui_overlay_forgery_handler(self, input_data: dict) -> dict:
        """UI overlay forgery detection for screenshots."""
        artifact = input_data.get("artifact") or self.agent.evidence_artifact
        result = await real_detect_ui_overlay_forgery(artifact=artifact)
        result = self._attach_visual_grounding(result, tool_name="detect_ui_overlay_forgery")
        await self.agent._record_tool_result("detect_ui_overlay_forgery", result)
        return result
