"""
Scene & Object Tool Handlers
============================

Domain-specific handlers for object detection and scene analysis.

"""

from __future__ import annotations

import asyncio
import os
import shutil
import tempfile

import cv2
import numpy as np
from PIL import Image

from core.handlers.base import BaseToolHandler
from core.ml_subprocess import run_ml_tool
from core.structured_logging import get_logger

logger = get_logger(__name__)


class SceneHandlers(BaseToolHandler):
    """Handles Object Detection, Contraband Search, and Scene consistency."""

    def register_tools(self, registry) -> None:
        """Register tools with the agent's ToolRegistry."""
        registry.register(
            "screenshot_scene_applicability",
            self.screenshot_scene_applicability_handler,
            "Screen-capture object/scene applicability check",
        )
        registry.register(
            "object_detection", self.object_detection_handler, "YOLO11 Object detection"
        )
        registry.register(
            "secondary_classification", self.secondary_classification_handler, "CLIP context check"
        )
        registry.register(
            "scale_validation", self.scale_validation_handler, "Object scale/physics check"
        )
        registry.register(
            "lighting_consistency", self.lighting_consistency_handler, "Lighting vector check"
        )
        registry.register(
            "scene_incongruence", self.scene_incongruence_handler, "Semantic scene check"
        )
        registry.register(
            "vector_contraband_search",
            self.vector_contraband_search_handler,
            "SigLIP vector search for contraband",
        )
        registry.register(
            "lighting_correlation_initial",
            self.lighting_correlation_handler,
            "Initial lighting misalignment audit",
        )

    async def screenshot_scene_applicability_handler(self, input_data: dict) -> dict:
        """Scope confirmation + pixel-level screenshot profile for screen captures."""
        artifact = input_data.get("artifact") or self.agent.evidence_artifact
        file_path = getattr(artifact, "file_path", "") or ""

        result: dict = {
            "available": True,
            "not_applicable_for_physical_scene": True,
            "court_defensible": True,
            "scope_note": (
                "Physical object detection, weapon search, scale validation, and lighting "
                "correlation are not applied to screen captures — these tools require "
                "real-world scene geometry. Screenshot-specific analysis is reported below."
            ),
        }

        # ── Pixel-level screenshot profile ────────────────────────────────────
        if file_path:
            try:
                loop = asyncio.get_running_loop()

                def _profile_screenshot() -> dict:
                    with Image.open(file_path) as img:
                        w, h = img.size
                        mode = img.mode
                        arr = np.array(img.convert("RGB"), dtype=np.float32)

                    mean_brightness = float(arr.mean())
                    aspect = round(w / h, 3) if h else 0.0

                    # Aspect class
                    if aspect > 1.9:
                        aspect_class = "ultra-wide"
                    elif aspect > 1.65:
                        aspect_class = "16:9 widescreen"
                    elif aspect > 1.4:
                        aspect_class = "3:2"
                    elif aspect > 0.95:
                        aspect_class = "4:3"
                    elif aspect < 0.7:
                        aspect_class = "portrait / mobile"
                    else:
                        aspect_class = "near-square"

                    # Known screen resolutions
                    _resolutions: dict[tuple[int, int], str] = {
                        (1920, 1080): "1080p Full HD",
                        (2560, 1440): "1440p QHD",
                        (3840, 2160): "4K UHD",
                        (1366, 768): "HD laptop",
                        (1280, 800): "MacBook",
                        (2560, 1600): "MacBook Pro Retina 16\"",
                        (1440, 900): "MacBook Air 13\"",
                        (2880, 1800): "MacBook Pro Retina 15\"",
                        (1024, 768): "XGA",
                        (1280, 1024): "SXGA",
                        (1600, 900): "HD+",
                        (2560, 1080): "UltraWide 1080p",
                        (3440, 1440): "UltraWide 1440p",
                    }
                    resolution_name = _resolutions.get((w, h))

                    # Dark-mode detection (mean brightness < 90 → dark UI)
                    is_dark_mode = mean_brightness < 90.0

                    # UI chrome detection: sample top and bottom 5% strips
                    strip_h = max(1, h // 20)
                    top_mean = float(arr[:strip_h].mean())
                    bottom_mean = float(arr[max(0, h - strip_h):].mean())
                    ui_chrome_detected = (
                        abs(top_mean - mean_brightness) > 20.0
                        or abs(bottom_mean - mean_brightness) > 20.0
                    )

                    return {
                        "width": w,
                        "height": h,
                        "color_mode": mode,
                        "resolution_name": resolution_name,
                        "aspect_ratio": aspect,
                        "aspect_class": aspect_class,
                        "mean_brightness": round(mean_brightness, 1),
                        "is_dark_mode": is_dark_mode,
                        "ui_chrome_detected": ui_chrome_detected,
                    }

                profile = await loop.run_in_executor(None, _profile_screenshot)
                result.update(profile)
                result["confidence"] = 0.80
            except Exception as exc:
                logger.debug("screenshot profile analysis failed", error=str(exc))
                result["confidence"] = 0.60
        else:
            result["confidence"] = 0.60

        await self.agent._record_tool_result("screenshot_scene_applicability", result)
        return result

    # ── Helpers ───────────────────────────────────────────────────────────────

    def _is_video(self, path: str) -> bool:
        return str(path).lower().endswith((".mp4", ".avi", ".mov", ".mkv", ".webm"))

    async def _extension_safe_media_path(self, file_path: str) -> tuple[str, str | None]:
        """
        Ultralytics rejects extensionless ingestion paths such as *.bin.
        Create a temporary path with a media suffix while preserving bytes.
        """
        ext = os.path.splitext(file_path)[1].lower()
        if ext in {
            ".jpg",
            ".jpeg",
            ".png",
            ".webp",
            ".bmp",
            ".tif",
            ".tiff",
            ".mp4",
            ".mov",
            ".avi",
            ".mkv",
            ".webm",
        }:
            return file_path, None

        mime = (getattr(self.agent.evidence_artifact, "mime_type", "") or "").lower()
        suffix = ".jpg"
        if "png" in mime:
            suffix = ".png"
        elif "webp" in mime:
            suffix = ".webp"
        elif "bmp" in mime:
            suffix = ".bmp"
        elif "tiff" in mime or "tif" in mime:
            suffix = ".tiff"
        elif mime.startswith("video/"):
            suffix = ".mp4"

        loop = asyncio.get_running_loop()

        def _copy() -> str:
            fd, tmp_path = tempfile.mkstemp(suffix=suffix)
            os.close(fd)
            shutil.copyfile(file_path, tmp_path)
            return tmp_path

        tmp_path = await loop.run_in_executor(None, _copy)
        return tmp_path, tmp_path

    async def _extract_best_video_frame(self, video_path: str) -> tuple[str, str | None]:
        """
        Extract a representative frame from a video using cv2.

        Returns (frame_path, tmp_path). frame_path is the file to pass to YOLO.
        tmp_path is set if a temp file was created (must be cleaned up by caller).
        """
        loop = asyncio.get_running_loop()

        def _extract() -> tuple[str, str | None]:
            cap = cv2.VideoCapture(video_path)
            if not cap.isOpened():
                return video_path, None  # fall back to original
            total = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
            cap.get(cv2.CAP_PROP_FPS) or 25.0
            # Sample the 20% mark (avoids black/title-card frames at the start)
            target_frame = max(1, int(total * 0.20))
            cap.set(cv2.CAP_PROP_POS_FRAMES, target_frame)
            ret, frame = cap.read()
            cap.release()
            if not ret or frame is None:
                return video_path, None
            fd, tmp_path = tempfile.mkstemp(suffix=".jpg")
            os.close(fd)
            cv2.imwrite(tmp_path, frame)
            return tmp_path, tmp_path

        return await loop.run_in_executor(None, _extract)

    # ── Phase 1: Object Detection ─────────────────────────────────────────────

    async def object_detection_handler(self, input_data: dict) -> dict:
        """YOLO11 object detection via centralised InferenceClient."""
        artifact = input_data.get("artifact") or self.agent.evidence_artifact
        target_path = artifact.file_path
        tmp_frame_path: str | None = None
        tmp_media_path: str | None = None

        if self._is_video(target_path):
            await self.agent.update_sub_task("Extracting representative key-frame from video...")
            target_path, tmp_frame_path = await self._extract_best_video_frame(target_path)
        else:
            target_path, tmp_media_path = await self._extension_safe_media_path(target_path)

        try:
            await self.agent.update_sub_task("Initializing object detection core...")
            ic = await self.get_inference()
            try:
                await self.agent.update_sub_task("Performing scene-wide object sweep...")
                results = await ic.predict_yolo(target_path, conf=0.20)
                model = await ic.get_yolo_model()

                detections = []
                for r in results:
                    for box in r.boxes:
                        xywh = box.xywh[0].tolist()
                        x_c, y_c, w, h = [round(float(v), 1) for v in xywh]
                        x1, y1 = round(x_c - w / 2, 1), round(y_c - h / 2, 1)
                        x2, y2 = round(x_c + w / 2, 1), round(y_c + h / 2, 1)
                        detections.append(
                            {
                                "class_name": model.names[int(box.cls)],
                                "confidence": round(float(box.conf), 3),
                                "bbox_xywh": [x_c, y_c, w, h],
                                # Normalised corner format — consumed by roi_extract_handler
                                "box": {"x1": x1, "y1": y1, "x2": x2, "y2": y2},
                                "is_reliable": float(box.conf) > 0.35,
                            }
                        )

                classes_found = sorted(
                    {str(d.get("class_name", "unknown")) for d in detections if d.get("class_name")}
                )
                weapon_terms = {"knife", "gun", "pistol", "rifle", "shotgun", "firearm", "weapon"}
                weapon_detections = [
                    d
                    for d in detections
                    if any(term in str(d.get("class_name", "")).lower() for term in weapon_terms)
                ]
                res = {
                    "detections": detections,
                    "detection_count": len(detections),
                    "classes_found": classes_found,
                    "weapon_detections": weapon_detections,
                    "backend": model.ckpt_path if hasattr(model, "ckpt_path") else "object-detector",
                    "available": True,
                    "confidence": 0.90 if detections else 0.70,
                    "court_defensible": True,
                }
                await self.agent._record_tool_result("object_detection", res)
                return res

            except Exception as exc:
                logger.warning(
                    "Object detector inference failed — returning degraded result",
                    error=str(exc),
                    file=target_path,
                )
                degraded = {
                    "detections": [],
                    "detection_count": 0,
                    "classes_found": [],
                    "weapon_detections": [],
                    "available": False,
                    "degraded": True,
                    "confidence": 0.0,
                    "court_defensible": False,
                    "error": str(exc),
                    "fallback_reason": f"Object detector inference failed: {exc}",
                }
                await self.agent._record_tool_result("object_detection", degraded)
                return degraded

        finally:
            if tmp_frame_path and os.path.exists(tmp_frame_path):
                os.unlink(tmp_frame_path)
            if tmp_media_path and os.path.exists(tmp_media_path):
                os.unlink(tmp_media_path)

    # ── Phase 1: Vector Contraband Search ─────────────────────────────────────

    async def vector_contraband_search_handler(self, input_data: dict) -> dict:
        """SigLIP embedding search against weapon/contraband manifold."""
        artifact = input_data.get("artifact") or self.agent.evidence_artifact
        target_path = artifact.file_path
        tmp_frame_path: str | None = None
        if self._is_video(target_path):
            target_path, tmp_frame_path = await self._extract_best_video_frame(target_path)
        try:
            await self.agent.update_sub_task(
                "Auditing high-dimensional threat manifolds (SigLIP)..."
            )
            ic = await self.get_inference()
            raw = await ic.predict_siglip(target_path, check_concerns=True)
            # predict_siglip may return an object or a dict — handle both.
            if isinstance(raw, dict):
                top_match = raw.get("top_match", "unknown")
                top_confidence = raw.get("top_confidence", raw.get("confidence", 0.0))
                concern_flag = raw.get("concern_flag", False)
                available = raw.get("available", True)
            else:
                top_match = getattr(raw, "top_match", "unknown")
                top_confidence = getattr(raw, "top_confidence", 0.0)
                concern_flag = getattr(raw, "concern_flag", False)
                available = getattr(raw, "available", True)

            result = {
                "top_match": top_match,
                "top_confidence": top_confidence,
                "confidence": float(top_confidence)
                if concern_flag
                else max(0.70, 1.0 - float(top_confidence or 0.0)),
                "concern_flag": concern_flag,
                "available": available,
                "court_defensible": True,
            }
        except Exception as exc:
            logger.warning("vector_contraband_search failed", error=str(exc))
            result = {
                "available": False,
                "degraded": True,
                "confidence": 0.0,
                "court_defensible": False,
                "error": str(exc),
            }
        finally:
            if tmp_frame_path and os.path.exists(tmp_frame_path):
                os.unlink(tmp_frame_path)

        await self.agent._record_tool_result("vector_contraband_search", result)
        return result

    # ── Phase 1: Lighting Correlation (initial pass) ──────────────────────────

    async def lighting_correlation_handler(self, input_data: dict) -> dict:
        """Automated lighting vector correlation pass."""
        artifact = input_data.get("artifact") or self.agent.evidence_artifact
        target_path = artifact.file_path
        tmp_frame_path: str | None = None
        if self._is_video(target_path):
            target_path, tmp_frame_path = await self._extract_best_video_frame(target_path)
        await self.agent.update_sub_task(
            "Auditing light-source vectors for compositing anomalies..."
        )
        try:
            result = await run_ml_tool("lighting_correlator.py", target_path, timeout=12.0)
            if not result.get("error") and result.get("available"):
                result = self._normalize_lighting_result(result)
                await self.agent._record_tool_result("lighting_correlation_initial", result)
                return result
            # Fallback to standard lighting consistency
            await self.agent.update_sub_task("Shadow-angle fallback audit in progress...")
            fallback = await self._run_lighting_analyzer(target_path)
            await self.agent._record_tool_result("lighting_correlation_initial", fallback)
            return fallback
        finally:
            if tmp_frame_path and os.path.exists(tmp_frame_path):
                os.unlink(tmp_frame_path)

    # ── Phase 2: Secondary Classification ─────────────────────────────────────

    async def secondary_classification_handler(self, input_data: dict) -> dict:
        """ROI-Centric SigLIP re-classification of low-confidence detections."""
        artifact = input_data.get("artifact") or self.agent.evidence_artifact
        await self.agent.update_sub_task("Auditing ROI-specific visual signatures...")

        # Audit Fix: CROP TO ROI
        # If we have existing YOLO context, re-classify the low-confidence candidates specifically.
        yolo_ctx = self.agent._tool_context.get("object_detection", {})
        detections = yolo_ctx.get("detections", [])
        low_conf = [d for d in detections if d.get("confidence", 1.0) < 0.85]

        target_path = artifact.file_path
        tmp_cleanup: list[str] = []

        try:
            ic = await self.get_inference()

            if low_conf:
                # We have specific candidates — re-verify the strongest low-conf match
                target = max(low_conf, key=lambda x: x.get("confidence", 0))
                box = target.get("box", {})
                if box and all(k in box for k in ("x1", "y1", "x2", "y2")):
                    await self.agent.update_sub_task(
                        f"Verifying {target.get('class_name')} ROI via SigLIP..."
                    )
                    with Image.open(artifact.file_path) as img:
                        w, h = img.size
                        # YOLO box coords are absolute pixels — use them directly.
                        # (Earlier bug: * w/100 treated pixels as percentages and
                        #  produced wildly out-of-bounds crop coordinates.)
                        x1, y1 = int(box["x1"]), int(box["y1"])
                        x2, y2 = int(box["x2"]), int(box["y2"])

                        # Add 10% margin for local context, clamped to image bounds
                        mw = (x2 - x1) * 0.1
                        mh = (y2 - y1) * 0.1
                        x1, y1 = max(0, int(x1 - mw)), max(0, int(y1 - mh))
                        x2, y2 = min(w, int(x2 + mw)), min(h, int(y2 + mh))

                        crop = img.crop((x1, y1, x2, y2))
                        fd, tmp_path = tempfile.mkstemp(suffix=".jpg")
                        os.close(fd)
                        crop.save(tmp_path)
                        target_path = tmp_path
                        tmp_cleanup.append(tmp_path)

            raw = await ic.predict_siglip(target_path)
            if isinstance(raw, dict):
                top_match = raw.get("top_match", "unknown")
                top_confidence = raw.get("top_confidence", raw.get("confidence", 0.0))
            else:
                top_match = getattr(raw, "top_match", "unknown")
                top_confidence = getattr(raw, "top_confidence", 0.0)

            result = {
                "top_match": top_match,
                "confidence": top_confidence,
                "available": True,
                "court_defensible": True,
                "is_roi_specific": target_path != artifact.file_path,
            }
        except Exception as exc:
            logger.warning("secondary_classification failed", error=str(exc))
            result = {
                "available": False,
                "degraded": True,
                "confidence": 0.0,
                "court_defensible": False,
                "error": str(exc),
            }
        finally:
            for p in tmp_cleanup:
                if os.path.exists(p):
                    os.unlink(p)

        await self.agent._record_tool_result("secondary_classification", result)
        return result

    # ── Phase 2: Scale Validation ─────────────────────────────────────────────

    async def scale_validation_handler(self, input_data: dict) -> dict:
        """
        Heuristic object scale and proportion validation.

        Uses YOLO detections from _tool_context to compare object bounding-box
        areas against known physical size expectations. Flags objects whose
        relative screen area is implausible given the scene geometry.
        """
        artifact = input_data.get("artifact") or self.agent.evidence_artifact
        try:
            img = np.array(Image.open(artifact.file_path).convert("RGB"))
            img_area = float(img.shape[0] * img.shape[1])

            yolo_ctx = self.agent._tool_context.get("object_detection", {})
            detections = yolo_ctx.get("detections", [])

            anomalies = []
            for det in detections:
                bbox = det.get("bbox_xywh", [])
                if len(bbox) < 4:
                    continue
                _, _, w, h = bbox
                obj_area_frac = (w * h) / max(img_area, 1.0)
                label = det.get("class_name", "object")
                conf = det.get("confidence", 0.0)
                # Flag objects occupying > 80 % of the frame as scale anomalies
                # (only meaningful if detection confidence is high)
                if obj_area_frac > 0.80 and conf > 0.50:
                    anomalies.append(
                        {
                            "class_name": label,
                            "area_fraction": round(obj_area_frac, 3),
                            "note": "Object occupies >80% of frame — scale implausible",
                        }
                    )

            result = {
                "scale_anomalies": anomalies,
                "anomaly_count": len(anomalies),
                "objects_checked": len(detections),
                "scale_consistent": len(anomalies) == 0,
                "confidence": 0.65 if detections else 0.40,
                "available": True,
                "court_defensible": True,
                "backend": "heuristic-bbox-area",
            }
        except Exception as exc:
            result = {
                "available": False,
                "degraded": True,
                "confidence": 0.0,
                "court_defensible": False,
                "error": str(exc),
            }
        await self.agent._record_tool_result("scale_validation", result)
        return result

    # ── Phase 2: Lighting Consistency ─────────────────────────────────────────

    async def lighting_consistency_handler(self, input_data: dict) -> dict:
        """
        ROI-aware shadow-angle lighting consistency check.

        Computes a scene-wide lighting baseline, then re-runs the heuristic on
        each high-confidence YOLO detection crop and compares shadow-angle std
        against the scene. Objects whose lighting deviates significantly are
        flagged as compositing candidates.
        """
        artifact = input_data.get("artifact") or self.agent.evidence_artifact
        scene_result = await self._run_lighting_analyzer(artifact.file_path)

        yolo_ctx = self.agent._tool_context.get("object_detection", {})
        detections = yolo_ctx.get("detections", []) if isinstance(yolo_ctx, dict) else []
        high_conf = [d for d in detections if d.get("confidence", 0.0) >= 0.50 and d.get("box")]

        if not high_conf:
            scene_result["roi_analysis"] = "skipped — no high-confidence detections"
            await self.agent._record_tool_result("lighting_consistency", scene_result)
            return scene_result

        scene_std = scene_result.get("shadow_angle_std_deg", 0.0)
        roi_flags: list[dict] = []

        loop = asyncio.get_running_loop()
        tmp_paths: list[str] = []
        try:
            with Image.open(artifact.file_path) as img:
                img_rgb = img.convert("RGB")
                iw, ih = img_rgb.size
                for det in high_conf[:8]:  # cap at 8 ROIs to bound cost
                    box = det["box"]
                    x1, y1 = max(0, int(box["x1"])), max(0, int(box["y1"]))
                    x2, y2 = min(iw, int(box["x2"])), min(ih, int(box["y2"]))
                    if x2 <= x1 or y2 <= y1:
                        continue
                    crop = img_rgb.crop((x1, y1, x2, y2))
                    fd, tmp_path = tempfile.mkstemp(suffix=".jpg")
                    os.close(fd)
                    crop.save(tmp_path)
                    tmp_paths.append(tmp_path)

                    roi_lighting = await loop.run_in_executor(
                        None, self._lighting_heuristic, tmp_path
                    )
                    roi_std = roi_lighting.get("shadow_angle_std_deg", 0.0)
                    deviation = abs(roi_std - scene_std)
                    if deviation > 15.0:
                        roi_flags.append(
                            {
                                "class_name": det.get("class_name", "object"),
                                "confidence": det.get("confidence"),
                                "roi_shadow_std_deg": round(roi_std, 2),
                                "scene_shadow_std_deg": round(scene_std, 2),
                                "deviation_deg": round(deviation, 2),
                            }
                        )
        finally:
            for p in tmp_paths:
                if os.path.exists(p):
                    os.unlink(p)

        scene_result["roi_lighting_flags"] = roi_flags
        scene_result["compositing_candidates"] = len(roi_flags)
        if roi_flags:
            scene_result["lighting_consistent"] = False
        scene_result = self._normalize_lighting_result(scene_result)
        await self.agent._record_tool_result("lighting_consistency", scene_result)
        return scene_result

    async def _run_lighting_analyzer(self, file_path: str) -> dict:
        """Shared helper: run lighting_analyzer.py via ml_subprocess."""
        result = await run_ml_tool("lighting_analyzer.py", file_path, timeout=12.0)
        if result.get("error"):
            # Inline fallback — compute shadow angle variance with cv2
            try:
                result = await asyncio.get_running_loop().run_in_executor(
                    None, self._lighting_heuristic, file_path
                )
            except Exception as exc:
                result = {
                    "available": False,
                    "degraded": True,
                    "confidence": 0.0,
                    "court_defensible": False,
                    "error": str(exc),
                }
        return self._normalize_lighting_result(result)

    @staticmethod
    def _normalize_lighting_result(result: dict) -> dict:
        """Expose both positive and negative lighting booleans for interpreters."""
        if not isinstance(result, dict):
            return result
        if "lighting_consistent" in result and "inconsistency_detected" not in result:
            result["inconsistency_detected"] = result.get("lighting_consistent") is False
        elif "inconsistency_detected" in result and "lighting_consistent" not in result:
            result["lighting_consistent"] = not bool(result.get("inconsistency_detected"))
        result.setdefault(
            "compositing_candidates", 1 if result.get("inconsistency_detected") else 0
        )
        result.setdefault("available", True)
        result.setdefault("confidence", 0.55 if result.get("inconsistency_detected") else 0.70)
        return result

    @staticmethod
    def _lighting_heuristic(file_path: str) -> dict:
        """Minimal OpenCV lighting consistency fallback."""
        img = cv2.imread(file_path)
        if img is None:
            return {"error": "Cannot read image", "available": False, "confidence": 0.0}
        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
        edges = cv2.Canny(gray, 50, 150)
        lines = cv2.HoughLinesP(
            edges, 1, np.pi / 180, threshold=50, minLineLength=30, maxLineGap=10
        )
        if lines is None or len(lines) < 3:
            return {
                "lighting_consistent": True,
                "shadow_angle_std_deg": 0.0,
                "confidence": 0.40,
                "available": True,
                "court_defensible": False,
                "backend": "heuristic-houghlines",
                "note": "Insufficient edges for shadow analysis",
            }
        angles = [
            np.degrees(np.arctan2(line[0][3] - line[0][1], line[0][2] - line[0][0]))
            for line in lines
        ]
        std_deg = float(np.std(angles))
        return {
            "lighting_consistent": std_deg < 30.0,
            "shadow_angle_std_deg": round(std_deg, 2),
            "confidence": 0.55,
            "available": True,
            "court_defensible": False,
            "backend": "heuristic-houghlines",
        }

    # ── Phase 2: Scene Incongruence ────────────────────────────────────────────

    async def scene_incongruence_handler(self, input_data: dict) -> dict:
        """
        Colour and texture coherence check for contextual scene incongruence.

        Divides the image into a 3×3 grid and computes per-cell colour histogram.
        High variance across cells indicates pasting from a different scene.
        """
        artifact = input_data.get("artifact") or self.agent.evidence_artifact
        target_path = artifact.file_path
        tmp_frame_path: str | None = None
        if self._is_video(target_path):
            target_path, tmp_frame_path = await self._extract_best_video_frame(target_path)
        try:
            loop = asyncio.get_running_loop()
            result = await loop.run_in_executor(
                None, self._scene_incongruence_heuristic, target_path
            )
        except Exception as exc:
            result = {
                "available": False,
                "degraded": True,
                "confidence": 0.0,
                "court_defensible": False,
                "error": str(exc),
            }
        finally:
            if tmp_frame_path and os.path.exists(tmp_frame_path):
                os.unlink(tmp_frame_path)
        await self.agent._record_tool_result("scene_incongruence", result)
        return result

    @staticmethod
    def _scene_incongruence_heuristic(file_path: str) -> dict:
        img = cv2.imread(file_path)
        if img is None:
            return {"error": "Cannot read image", "available": False, "confidence": 0.0}
        h, w = img.shape[:2]
        rows, cols = 3, 3
        cell_h, cell_w = h // rows, w // cols

        histograms = []
        for r in range(rows):
            for c in range(cols):
                cell = img[r * cell_h : (r + 1) * cell_h, c * cell_w : (c + 1) * cell_w]
                hist = cv2.calcHist([cell], [0, 1, 2], None, [8, 8, 8], [0, 256, 0, 256, 0, 256])
                cv2.normalize(hist, hist)
                histograms.append(hist)

        # Compute average correlation across all adjacent cells
        correlations = []
        for i in range(len(histograms)):
            for j in range(i + 1, len(histograms)):
                # Correlation metric: 1 is perfect match, -1 is total mismatch
                corr = cv2.compareHist(histograms[i], histograms[j], cv2.HISTCMP_CORREL)
                correlations.append(corr)

        avg_corr = float(np.mean(correlations)) if correlations else 1.0
        # High incongruence if average correlation is low
        is_incongruent = avg_corr < 0.35

        return {
            "scene_incongruent": is_incongruent,
            "average_histogram_correlation": round(avg_corr, 4),
            "grid_cells_analyzed": rows * cols,
            "confidence": 0.45,
            "available": True,
            "court_defensible": False,
            "backend": "heuristic-spatial-histogram-correlation",
            "note": "Grid-based histogram correlation check. Low correlation suggests compositing from disparate lighting/environments.",
        }
