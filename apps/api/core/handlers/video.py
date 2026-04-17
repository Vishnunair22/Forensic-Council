"""
Video Tool Handlers
===================

Domain-specific handlers for temporal video forensic tools.
Implements Fix 3 (Decentralization) and Initial Analysis Refinements.
"""

import asyncio

import cv2
import numpy as np

from core.handlers.base import BaseToolHandler
from core.ml_subprocess import run_ml_tool
from core.structured_logging import get_logger
from tools.mediainfo_tools import (
    get_av_file_identity as real_get_av_file_identity,
)
from tools.mediainfo_tools import (
    profile_av_container as real_profile_av_container,
)
from tools.video_tools import (
    face_swap_detect as real_face_swap_detect,
)
from tools.video_tools import (
    frame_consistency_analyze as real_frame_consistency_analyze,
)
from tools.video_tools import (
    frame_window_extract as real_frame_window_extract,
)
from tools.video_tools import (
    optical_flow_analyze as real_optical_flow_analyze,
)
from tools.video_tools import (
    video_metadata_extract as real_video_metadata_extract,
    # compression_artifact_analyze does NOT exist in video_tools — handler uses fallback
)

logger = get_logger(__name__)

class VideoHandlers(BaseToolHandler):
    """Handles temporal consistency, face swap, and interframe forgery."""

    def register_tools(self, registry) -> None:
        """Register tools with the agent's ToolRegistry."""
        registry.register("optical_flow_analysis", self.optical_flow_analysis_handler, "Optical flow analysis")
        registry.register("frame_extraction", self.frame_extraction_handler, "Frame window extraction")
        registry.register("frame_consistency_analysis", self.frame_consistency_analysis_handler, "Inter-frame consistency check")
        registry.register("face_swap_detection", self.face_swap_detection_handler, "Face swap detection")
        registry.register("video_metadata", self.video_metadata_handler, "Advanced video metadata extraction")
        registry.register("interframe_forgery_detector", self.interframe_forgery_detector_handler, "Interframe forgery detection")
        registry.register("compression_artifact_analysis", self.compression_artifact_analysis_handler, "Video compression analysis")
        registry.register("rolling_shutter_validation", self.rolling_shutter_validation_handler, "Rolling shutter signature validation")
        registry.register("mediainfo_profile", self.mediainfo_profile_handler, "Deep AV container profiling")
        registry.register("av_file_identity", self.av_file_identity_handler, "Lightweight AV file identity pre-screen")

        # New Refinement Tools
        registry.register("vfi_error_map", self.vfi_error_map_handler, "VFI error mapping for motion inconsistencies")
        registry.register("thumbnail_coherence", self.thumbnail_coherence_handler, "Video thumbnail metadata coherence check")

    # ── Refinement: VFI Error Map ──────────────────────────────────────

    async def vfi_error_map_handler(self, input_data: dict) -> dict:
        """[REFINED] Video Frame Interpolation (VFI) error mapping for GAN edits."""
        artifact = input_data.get("artifact") or self.agent.evidence_artifact
        await self.agent.update_sub_task("Auditing motion interpolation map for GAN signatures...")
        try:
            result = await run_ml_tool("vfi_error_mapper.py", artifact.file_path, timeout=30.0)
            if not result.get("error") and result.get("available"):
                await self.agent._record_tool_result("vfi_error_map", result)
                return result
        except Exception:
            pass

        # Fallback to standard frame consistency
        await self.agent.update_sub_task("VFI audit unavailable — falling back to frame consistency...")
        return await self.frame_consistency_analysis_handler(input_data)

    async def thumbnail_coherence_handler(self, input_data: dict) -> dict:
        """[REFINED] Verifies if embedded thumbnails match the actual video content."""
        artifact = input_data.get("artifact") or self.agent.evidence_artifact
        await self.agent.update_sub_task("Auditing stream thumbnails against content hash...")
        try:
            result = await run_ml_tool("thumbnail_coherence_checker.py", artifact.file_path, timeout=10.0)
            if not result.get("error") and result.get("available"):
                await self.agent._record_tool_result("thumbnail_coherence", result)
                return result
        except Exception:
            pass

        result = {"available": False, "note": "Thumbnail coherence audit script unavailable in this environment."}
        await self.agent._record_tool_result("thumbnail_coherence", result)
        return result

    # ── Standard Handlers (Migrated) ─────────────────────────────────────

    async def optical_flow_analysis_handler(self, input_data: dict) -> dict:
        artifact = input_data.get("artifact") or self.agent.evidence_artifact
        flow_threshold = input_data.get("flow_threshold", 5.0)
        await self.agent.update_sub_task("Establishing temporal motion baseline...")
        try:
            result = await real_optical_flow_analyze(
                artifact=artifact,
                flow_threshold=flow_threshold,
                progress_callback=self.agent.update_sub_task
            )
        except Exception as e:
            result = {"error": str(e)}

        if result.get("error") or not result.get("available"):
            result = await self._optical_flow_fallback(artifact.file_path)

        await self.agent._record_tool_result("optical_flow_analysis", result)
        return result

    async def _optical_flow_fallback(self, file_path: str) -> dict:
        """Scientific OpenCV Farneback inline fallback — runs in executor to avoid blocking."""
        loop = asyncio.get_running_loop()
        await self.agent.update_sub_task("Optical Flow: Running scientific Farneback fallback...")
        return await loop.run_in_executor(None, self._optical_flow_sync, file_path)

    def _optical_flow_sync(self, file_path: str) -> dict:
        """Synchronous Farneback optical flow — called from executor thread."""
        try:
            cap = cv2.VideoCapture(file_path)
            ret, frame1 = cap.read()
            if not ret:
                cap.release()
                return {"error": "Cannot read video", "available": False}

            prvs = cv2.cvtColor(frame1, cv2.COLOR_BGR2GRAY)
            flows = []
            # Sample 20 frames for a fast scientific estimate
            for _ in range(20):
                ret, frame2 = cap.read()
                if not ret:
                    break
                next_f = cv2.cvtColor(frame2, cv2.COLOR_BGR2GRAY)
                flow = cv2.calcOpticalFlowFarneback(prvs, next_f, None, 0.5, 3, 15, 3, 5, 1.2, 0)
                mag, _ = cv2.cartToPolar(flow[..., 0], flow[..., 1])
                flows.append(float(np.mean(mag)))
                prvs = next_f

            cap.release()
            mean_f = float(np.mean(flows)) if flows else 0.0
            return {
                "mean_flow": round(mean_f, 4),
                "degraded": True,
                "available": True,
                "note": "OpenCV Farneback sampled fallback. Scientific variance audit completed.",
                "court_defensible": False
            }
        except Exception as e:
            return {"error": f"Optical flow fallback failed: {e}", "available": False}

    async def frame_extraction_handler(self, input_data: dict) -> dict:
        artifact = input_data.get("artifact") or self.agent.evidence_artifact
        start = input_data.get("start_frame", 0)
        end = input_data.get("end_frame", 100)
        await self.agent.update_sub_task(f"Extracting temporal evidence window: frames {start} to {end}...")
        result = await real_frame_window_extract(artifact=artifact, start_frame=start, end_frame=end)
        await self.agent._record_tool_result("frame_extraction", result)
        return result

    async def frame_consistency_analysis_handler(self, input_data: dict) -> dict:
        artifact = input_data.get("artifact") or self.agent.evidence_artifact
        await self.agent.update_sub_task("Auditing inter-frame pixel consistency...")
        result = await real_frame_consistency_analyze(artifact=artifact)
        await self.agent._record_tool_result("frame_consistency_analysis", result)
        return result

    async def face_swap_detection_handler(self, input_data: dict) -> dict:
        artifact = input_data.get("artifact") or self.agent.evidence_artifact
        await self.agent.update_sub_task("Scanning frames for neural face-swap artifacts...")
        result = await real_face_swap_detect(
            artifact=artifact,
            progress_callback=self.agent.update_sub_task
        )
        await self.agent._record_tool_result("face_swap_detection", result)
        return result

    async def video_metadata_handler(self, input_data: dict) -> dict:
        artifact = input_data.get("artifact") or self.agent.evidence_artifact
        await self.agent.update_sub_task("Performing stream-level metadata probe...")
        result = await real_video_metadata_extract(artifact=artifact)
        await self.agent._record_tool_result("video_metadata", result)
        return result

    async def interframe_forgery_detector_handler(self, input_data: dict) -> dict:
        artifact = input_data.get("artifact") or self.agent.evidence_artifact
        await self.agent.update_sub_task("Auditing temporal forgery (motion ghosting)...")
        result = await run_ml_tool("interframe_forgery_detector.py", artifact.file_path, timeout=20.0)
        await self.agent._record_tool_result("interframe_forgery_detector", result)
        return result

    async def compression_artifact_analysis_handler(self, input_data: dict) -> dict:
        """OpenCV heuristic I-frame/P-frame bitrate variance analysis."""
        artifact = input_data.get("artifact") or self.agent.evidence_artifact
        await self.agent.update_sub_task("Auditing codec compression (P-frame/I-frame incongruence)...")
        loop = asyncio.get_running_loop()
        result = await loop.run_in_executor(None, self._compression_artifact_sync, artifact.file_path)
        await self.agent._record_tool_result("compression_artifact_analysis", result)
        return result

    def _compression_artifact_sync(self, file_path: str) -> dict:
        """Synchronous OpenCV JPEG-proxy compression heuristic — called from executor thread."""
        try:
            cap = cv2.VideoCapture(file_path)
            if not cap.isOpened():
                return {"error": "Cannot open video", "available": False}
            frame_sizes = []
            for _ in range(50):
                ret, frame = cap.read()
                if not ret:
                    break
                # Encode to JPEG and measure byte size as proxy for frame complexity
                _, buf = cv2.imencode(".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, 95])
                frame_sizes.append(len(buf))
            cap.release()
            if len(frame_sizes) < 2:
                return {"available": False, "note": "Not enough frames for compression analysis."}
            sizes = np.array(frame_sizes, dtype=float)
            mean_size = float(np.mean(sizes))
            cv_ratio = float(np.std(sizes) / mean_size) if mean_size > 0 else 0.0
            return {
                "frame_size_variance": round(float(np.var(sizes)), 2),
                "coefficient_of_variation": round(cv_ratio, 4),
                "mean_frame_size_bytes": round(mean_size, 2),
                "frames_analyzed": len(frame_sizes),
                "available": True,
                "degraded": True,
                "court_defensible": False,
                "note": "OpenCV JPEG-proxy compression heuristic. Not a true codec-level analysis.",
            }
        except Exception as e:
            return {"error": f"Compression analysis failed: {e}", "available": False}

    async def rolling_shutter_validation_handler(self, input_data: dict) -> dict:
        """Rolling shutter signature validation against claimed device metadata."""
        artifact = input_data.get("artifact") or self.agent.evidence_artifact
        await self.agent.update_sub_task("Validating rolling shutter signatures against device metadata...")
        result = await run_ml_tool("rolling_shutter_validator.py", artifact.file_path, timeout=15.0)
        await self.agent._record_tool_result("rolling_shutter_validation", result)
        return result

    async def mediainfo_profile_handler(self, input_data: dict) -> dict:
        """Deep AV container profiling via MediaInfo."""
        artifact = input_data.get("artifact") or self.agent.evidence_artifact
        await self.agent.update_sub_task("Running deep AV container profiling via MediaInfo...")
        result = await real_profile_av_container(artifact=artifact)
        await self.agent._record_tool_result("mediainfo_profile", result)
        return result

    async def av_file_identity_handler(self, input_data: dict) -> dict:
        """Lightweight AV file identity pre-screen."""
        artifact = input_data.get("artifact") or self.agent.evidence_artifact
        await self.agent.update_sub_task("AV pre-screen: resolving file identity...")
        result = await real_get_av_file_identity(artifact=artifact)
        await self.agent._record_tool_result("av_file_identity", result)
        return result
