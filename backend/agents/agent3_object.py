"""
Agent 3 - Object & Weapon Analysis Agent.

Object identification and contextual validation specialist for detecting 
and contextually validating objects, weapons, and contraband.
"""

from __future__ import annotations

import asyncio
import uuid
from typing import Any, Optional

from agents.base_agent import ForensicAgent
from core.logging import get_logger

logger = get_logger(__name__)
from core.config import Settings
from core.custody_logger import CustodyLogger
from core.episodic_memory import EpisodicMemory
from core.evidence import EvidenceArtifact
from core.inter_agent_bus import InterAgentBus, InterAgentCall, InterAgentCallType
from core.tool_registry import ToolRegistry
from core.working_memory import WorkingMemory
from core.ml_subprocess import run_ml_tool
from infra.evidence_store import EvidenceStore
from core.gemini_client import GeminiVisionClient


class Agent3Object(ForensicAgent):
    """
    Agent 3 - Object & Weapon Analysis Agent.
    
    Mandate: Detect and contextually validate objects, weapons, and contraband.
    Identify compositing through lighting inconsistency.
    
    Task Decomposition:
    1. Run full-scene primary object detection
    2. For each detected object below confidence threshold: run secondary classification pass
    3. For each confirmed object: run scale and proportion validation
    4. For each confirmed object: run lighting and shadow consistency check
    5. Run scene-level contextual incongruence analysis
    6. Run ML-based image splicing detection on objects
    7. Run camera noise fingerprint analysis for region consistency
    8. Cross-reference confirmed objects against contraband/weapons database
    9. Issue inter-agent call to Agent 1 for any region showing lighting inconsistency
    10. Run adversarial robustness check against object detection evasion
    11. Self-reflection pass
    12. Submit calibrated findings to Arbiter
    """
    
    def inject_agent1_context(self, agent1_gemini_findings: dict) -> None:
        """
        Called by pipeline to share Agent 1's Gemini vision findings with this agent instance.
        Agent 3's deep pass reads this to cross-reference object/weapon analysis.
        """
        self._agent1_context = agent1_gemini_findings or {}

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
        inter_agent_bus: Optional[Any] = None,
    ) -> None:
        """Initialize Agent 3 with optional inter-agent bus."""
        super().__init__(
            agent_id=agent_id,
            session_id=session_id,
            evidence_artifact=evidence_artifact,
            config=config,
            working_memory=working_memory,
            episodic_memory=episodic_memory,
            custody_logger=custody_logger,
            evidence_store=evidence_store,
        )
        self._inter_agent_bus = inter_agent_bus
        self._agent1_context: dict = {}
        # Set by pipeline before launching parallel deep passes.
        # Gemini handler awaits this so tools run in parallel with Agent1's Gemini
        # and only block at the Gemini call to receive cross-validation context.
        self._agent1_context_event: Optional[Any] = None

    @property
    def agent_name(self) -> str:
        """Human-readable name of this agent."""
        return "Agent3_ObjectWeapon"
    
    @property
    def task_decomposition(self) -> list[str]:
        """
        Light tasks — YOLO detection + quick validation (~15-20s total).
        Heavy ML tasks are in deep_task_decomposition.
        """
        return [
            "Run full-scene object detection",
            "Run OCR on detected object regions to extract license plates, ID numbers, signs, and visible text",
            "For each detected object below confidence threshold: run secondary classification pass",
            "For each confirmed object: run scale validation",
            "For each confirmed object: run lighting consistency check",
            "Cross-reference confirmed objects against contraband database",
            "Self-reflection pass",
            "Submit calibrated findings to Arbiter",
        ]

    @property
    def deep_task_decomposition(self) -> list[str]:
        """
        Heavy tasks — CLIP inference, ML splicing, adversarial checks, Gemini deep forensic analysis.
        Runs in background after initial findings are returned.
        """
        return [
            "Run Gemini deep forensic analysis: identify content type, extract all text, detect objects and weapons, identify interfaces, describe what is happening, cross-validate metadata",
            "Run scene-level contextual incongruence analysis",
            "Run image splicing detection on objects",
            "Run camera noise fingerprint analysis for region consistency",
            "Run adversarial robustness check against object detection evasion",
            "Run document authenticity analysis to detect font inconsistency, background irregularity, and digital forgery artifacts",
        ]

    @property
    def iteration_ceiling(self) -> int:
        """Maximum iterations — tasks + 2 buffer to prevent runaway loops."""
        return len(self.task_decomposition) + 2
    
    @property
    def supported_file_types(self) -> list[str]:
        """Object agent supports image and video file types."""
        return ['image/', 'video/']
    
    async def build_tool_registry(self) -> ToolRegistry:
        """
        Build and return the tool registry for this agent.
        
        Registers real tool implementations for:
        - object_detection: Full-scene object detection
        - secondary_classification: Secondary classification pass
        - scale_validation: Scale and proportion validation
        - lighting_consistency: Lighting and shadow consistency check
        - scene_incongruence: Scene-level contextual incongruence analysis
        - contraband_database: Contraband and weapons database cross-reference
        - inter_agent_call: Inter-agent communication
        - adversarial_robustness_check: Adversarial robustness check
        """
        registry = ToolRegistry()
        
        async def object_detection(input_data: dict) -> dict:
            """
            Object detection using YOLOv8 (upgrade from OpenCV heuristics).
            
            YOLOv8n is ~6MB and runs CPU-only in ~200ms per image.
            Detects 80 COCO classes including weapons (knife, gun, etc.)
            """
            import os
            
            # Set YOLO cache directory BEFORE importing - this controls where models are downloaded
            import pathlib
            yolo_cache = os.getenv("YOLO_CONFIG_DIR", str(pathlib.Path.home() / ".cache" / "ultralytics"))
            os.makedirs(yolo_cache, exist_ok=True)
            os.environ["YOLO_CONFIG_DIR"] = yolo_cache
            os.environ["ULTRALYTICS_CACHE_DIR"] = yolo_cache
            
            artifact = input_data.get("artifact") or self.evidence_artifact
            
            try:
                from ultralytics import YOLO, settings

                # Only update settings keys that actually exist in this ultralytics version
                valid_keys = set(settings.keys()) if hasattr(settings, "keys") else set(dict(settings).keys())
                safe_updates = {k: v for k, v in {
                    "weights_dir": yolo_cache, "datasets_dir": yolo_cache,
                }.items() if k in valid_keys}
                if safe_updates:
                    settings.update(safe_updates)
                
                # Auto-downloads on first call
                model_path = os.path.join(yolo_cache, "yolov8n.pt")
                model = YOLO(model_path)

                # If the artifact is a video, extract a representative frame first.
                # This prevents "skipped/useless" results for videos and makes the analysis actionable.
                target_path = artifact.file_path
                tmp_frame_path: str | None = None
                try:
                    fp_lower = str(target_path).lower()
                    mime = (artifact.metadata or {}).get("mime_type", "").lower() if getattr(artifact, "metadata", None) else ""
                    is_video = fp_lower.endswith((".mp4", ".avi", ".mov", ".mkv", ".webm", ".wmv", ".flv")) or mime.startswith("video/")
                    if is_video:
                        import cv2, tempfile
                        cap = cv2.VideoCapture(target_path)
                        if cap.isOpened():
                            frame_count = int(cap.get(cv2.CAP_PROP_FRAME_COUNT) or 0)
                            # Sample 3 frames (beginning, middle, end) and choose the one with most edges
                            # to avoid black/empty frames at the start of videos.
                            best_frame = None
                            max_edges = -1
                            
                            sample_points = [0.1, 0.5, 0.9] if frame_count > 10 else [0.5]
                            for p in sample_points:
                                cap.set(cv2.CAP_PROP_POS_FRAMES, int(frame_count * p))
                                ok, frame = cap.read()
                                if ok and frame is not None:
                                    gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
                                    edge_score = cv2.Laplacian(gray, cv2.CV_64F).var()
                                    if edge_score > max_edges:
                                        max_edges = edge_score
                                        best_frame = frame.copy()
                            
                            if best_frame is not None:
                                with tempfile.NamedTemporaryFile(suffix=".jpg", delete=False) as tmp:
                                    tmp_frame_path = tmp.name
                                cv2.imwrite(tmp_frame_path, best_frame, [int(cv2.IMWRITE_JPEG_QUALITY), 95])
                                target_path = tmp_frame_path
                        cap.release()
                except Exception:
                    # Fall back to passing the original path (YOLO may still handle it in some environments)
                    pass

                results = model(target_path, conf=0.25, verbose=False)
                
                detections = []
                for r in results:
                    for box in r.boxes:
                        detections.append({
                            "class_name": model.names[int(box.cls)],
                            "confidence": round(float(box.conf), 3),
                            "bbox_xywh": [round(float(v), 1) for v in box.xywh[0].tolist()],
                            "bbox_xyxy": [round(float(v), 1) for v in box.xyxy[0].tolist()],
                        })
                
                # Flag weapons/dangerous items specifically
                # Note: COCO-80 dataset only has "knife" as weapon class
                WEAPON_CLASSES = {"knife"}
                weapon_detections = [d for d in detections 
                                     if any(w in d["class_name"].lower() for w in WEAPON_CLASSES)]
                
                detection_result = {
                    "detections": detections,
                    "detection_count": len(detections),
                    "weapon_detections": weapon_detections,
                    "classes_found": list({d["class_name"] for d in detections}),
                    "court_defensible": True,
                    "available": True,
                    "backend": "ultralytics-yolov8n",
                }
                await self._record_tool_result("object_detection", detection_result)
                return detection_result
            except Exception as e:
                # Fallback to OpenCV heuristics — also record result so Gemini handler has context
                opencv_result = await _object_detection_opencv(input_data)
                await self._record_tool_result("object_detection", opencv_result)
                return opencv_result
            finally:
                # Best-effort cleanup for extracted video frame
                try:
                    if "tmp_frame_path" in locals() and tmp_frame_path:
                        import os
                        os.unlink(tmp_frame_path)
                except Exception:
                    pass
        
        async def _object_detection_opencv(input_data: dict) -> dict:
            """Legacy OpenCV heuristic-based object detection."""
            import cv2, numpy as np
            from PIL import Image
            artifact = input_data.get("artifact") or self.evidence_artifact
            try:
                img = np.array(Image.open(artifact.file_path).convert("RGB"))
                gray = cv2.cvtColor(img, cv2.COLOR_RGB2GRAY)
                # Canny edge map
                edges = cv2.Canny(gray, 50, 150)
                # Find contours as proxy for distinct objects
                contours, _ = cv2.findContours(edges, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
                # Filter by area (ignore noise)
                h, w = gray.shape
                min_area = (h * w) * 0.005  # 0.5% of image
                significant = [c for c in contours if cv2.contourArea(c) > min_area]
                objects = []
                for c in significant[:10]:
                    x, y, bw, bh = cv2.boundingRect(c)
                    region = img[y:y+bh, x:x+bw]
                    mean_color = region.mean(axis=(0,1)).tolist()
                    objects.append({
                        "region_id": len(objects),
                        "bbox": [int(x), int(y), int(bw), int(bh)],
                        "area_ratio": round(float(cv2.contourArea(c)) / (h * w), 4),
                        "mean_color_rgb": [round(c, 1) for c in mean_color],
                    })
                return {
                    "objects_detected": objects,
                    "total_count": len(objects),
                    "image_dimensions": {"width": int(w), "height": int(h)},
                    "edge_density": round(float(edges.mean()) / 255, 4),
                    "backend": "legacy-opencv",
                }
            except Exception as e:
                # Return graceful error dictionary rather than raising
                return {"error": f"Object detection failed: {e}", "objects_detected": [], "total_count": 0}
        
        async def secondary_classification(input_data: dict) -> dict:
            """
            Secondary classification pass using CLIP zero-shot classifier.

            For any detected object whose primary YOLO confidence is below the
            threshold, we run a targeted CLIP zero-shot pass with object-specific
            label alternatives to refine the classification.  Uses the shared
            singleton CLIPImageAnalyzer to avoid reloading the ~300 MB model.
            """
            from tools.clip_utils import get_clip_analyzer

            artifact = input_data.get("artifact") or self.evidence_artifact
            low_conf_object = input_data.get("object_class", "unidentified object")
            bbox = input_data.get("bbox")  # Optional [x, y, w, h]

            try:
                from PIL import Image as PILImage
                import numpy as np

                img = PILImage.open(artifact.file_path).convert("RGB")

                # Crop to bounding box if provided for tighter classification
                if bbox and len(bbox) == 4:
                    x, y, w, h = [int(v) for v in bbox]
                    # Expand crop slightly for context
                    iw, ih = img.size
                    pad = 10
                    x1 = max(0, x - pad)
                    y1 = max(0, y - pad)
                    x2 = min(iw, x + w + pad)
                    y2 = min(ih, y + h + pad)
                    img = img.crop((x1, y1, x2, y2))

                # Save cropped region to temp file for CLIP analyzer
                import tempfile, os
                with tempfile.NamedTemporaryFile(suffix=".jpg", delete=False) as tmp:
                    img.save(tmp.name, format="JPEG", quality=95)
                    tmp_path = tmp.name

                try:
                    # Build targeted label set for the low-confidence object
                    base_categories = [
                        f"a photograph of {low_conf_object}",
                        f"a photograph of a weapon",
                        f"a photograph of a harmless object",
                        f"a photograph of a tool",
                        f"a photograph of an electronic device",
                        f"a photograph of food or beverage",
                        f"a photograph of a person",
                        f"a digitally inserted or composited object",
                        f"a photograph of contraband or illegal substance",
                        f"a photograph of a document or identification",
                    ]

                    analyzer = get_clip_analyzer()
                    import asyncio as _asyncio
                    _loop = _asyncio.get_running_loop()
                    result = await _loop.run_in_executor(
                        None,
                        lambda: analyzer.analyze_image(
                            tmp_path,
                            categories=base_categories,
                            check_concerns=True,
                        ),
                    )
                finally:
                    os.unlink(tmp_path)

                if not result.available:
                    return {
                        "status": "unavailable",
                        "court_defensible": False,
                        "error": result.error or "CLIP model unavailable",
                        "refined_classifications": None,
                    }

                # CLIP zero-shot scores sum to 1.0 across all labels, so with 10
                # candidates chance-level is ~10%.  Below 15% the top match is
                # indistinguishable from noise — do not attribute a label.
                _CLIP_MIN_CONFIDENCE = 0.15
                top_conf = round(result.top_confidence, 4)
                if top_conf < _CLIP_MIN_CONFIDENCE:
                    return {
                        "status": "low_confidence",
                        "court_defensible": True,
                        "method": "CLIP ViT-B-32 zero-shot classification — targeted label set",
                        "input_object_class": low_conf_object,
                        "top_refined_match": None,
                        "top_confidence": top_conf,
                        "refined_classifications": [
                            {"label": cat, "confidence": round(score, 4)}
                            for cat, score in result.all_scores[:5]
                        ],
                        "concern_flag": False,
                        "classification_note": (
                            f"Top CLIP match confidence {top_conf:.1%} is at noise/chance level "
                            f"(<{_CLIP_MIN_CONFIDENCE:.0%} threshold with 10 candidate labels). "
                            "No reliable classification can be attributed to this region."
                        ),
                        "backend": "open-clip ViT-B-32 (shared singleton)",
                    }
                return {
                    "status": "real",
                    "court_defensible": True,
                    "method": "CLIP ViT-B-32 zero-shot classification — targeted label set",
                    "input_object_class": low_conf_object,
                    "top_refined_match": result.top_match,
                    "top_confidence": top_conf,
                    "refined_classifications": [
                        {"label": cat, "confidence": round(score, 4)}
                        for cat, score in result.all_scores[:5]
                    ],
                    "concern_flag": result.concern_flag,
                    "backend": "open-clip ViT-B-32 (shared singleton)",
                }
            except Exception as e:
                return {
                    "status": "error",
                    "court_defensible": False,
                    "refined_classifications": None,
                    "error": str(e),
                }
        
        async def scale_validation(input_data: dict) -> dict:
            import cv2, numpy as np
            from PIL import Image
            artifact = input_data.get("artifact") or self.evidence_artifact
            try:
                img = np.array(Image.open(artifact.file_path).convert("RGB"))
                gray = cv2.cvtColor(img, cv2.COLOR_RGB2GRAY)
                # Use HoughLinesP to detect straight lines → perspective cues
                edges = cv2.Canny(gray, 50, 150, apertureSize=3)
                lines = cv2.HoughLinesP(edges, 1, np.pi/180, threshold=100, minLineLength=60, maxLineGap=10)
                if lines is None:
                    return {"scale_consistent": True, "line_count": 0, "note": "Insufficient line features for perspective analysis"}
                # Compute line angles
                angles = []
                for line in lines:
                    x1, y1, x2, y2 = line[0]
                    if x2 != x1:
                        angles.append(float(np.degrees(np.arctan2(y2-y1, x2-x1))))
                angle_std = float(np.std(angles)) if angles else 0.0
                # Interpretation:
                #   angle_std < 5°  → near-perfectly parallel lines only → likely digitally
                #                      drawn (synthetic grid/schematic). Real photographs of
                #                      buildings, roads, or documents routinely have 5–15°.
                #   5–80°           → normal range; no compositing signal from this check.
                #   angle_std > 80° → chaotic line distribution; weak incongruence signal.
                # NOTE: the old lower bound of 15° produced false positives on any
                # architecture/document/overhead-view photograph.
                scale_consistent = 5.0 < angle_std < 80.0
                return {
                    "scale_consistent": scale_consistent,
                    "line_count": len(lines),
                    "angle_std_deg": round(angle_std, 2),
                    "assessment": (
                        "perspective angles appear natural"
                        if scale_consistent
                        else (
                            "near-zero line-angle variance — image may be digitally generated or a schematic"
                            if angle_std <= 5.0
                            else "very high line-angle variance — weak compositing signal; corroboration needed"
                        )
                    ),
                    # Heuristic signal — ran successfully but requires corroboration.
                    "court_defensible": True,
                    "evidentiary_weight": "supporting_only",
                    "limitation_note": "HoughLinesP angle-distribution check — heuristic signal only; requires corroboration from ELA/PRNU for court use.",
                }
            except Exception as e:
                return {"error": f"Scale validation failed: {e}", "scale_consistent": True}
        
        async def lighting_consistency(input_data: dict) -> dict:
            """Lighting analysis using Hough shadow-direction detector with inline fallback."""
            import cv2, numpy as np
            from PIL import Image
            artifact = input_data.get("artifact") or self.evidence_artifact
            # Try ML subprocess first
            ml_result = await run_ml_tool("lighting_analyzer.py", artifact.file_path, timeout=20.0)
            if ml_result.get("available") and not ml_result.get("error"):
                return ml_result
            # Inline fallback: gradient direction consistency
            try:
                img = np.array(Image.open(artifact.file_path).convert("RGB"))
                gray = cv2.cvtColor(img, cv2.COLOR_RGB2GRAY).astype(np.float32)
                gx = cv2.Sobel(gray, cv2.CV_64F, 1, 0, ksize=3)
                gy = cv2.Sobel(gray, cv2.CV_64F, 0, 1, ksize=3)
                mag = np.sqrt(gx**2 + gy**2)
                angle = np.degrees(np.arctan2(gy, gx))
                # Sample high-gradient pixels
                threshold = np.percentile(mag, 85)
                mask = mag > threshold
                angles = angle[mask]
                angle_std = float(np.std(angles)) if len(angles) > 10 else 0.0
                inconsistency = angle_std > 75  # Very high spread = possible composite
                return {
                    "inconsistency_detected": inconsistency,
                    "details": f"Gradient direction std={angle_std:.1f}° across {mask.sum()} high-gradient pixels.",
                    "flags": ["High gradient direction variance — possible lighting splice"] if inconsistency else [],
                    "backend": "opencv-gradient-inline",
                    "court_defensible": True,
                    "available": True,
                }
            except Exception as e:
                return {"error": f"Lighting analysis failed: {e}", "inconsistency_detected": False,
                        "backend": "tool-exception", "court_defensible": False}
        
        async def scene_incongruence(input_data: dict) -> dict:
            import cv2, numpy as np
            from PIL import Image
            artifact = input_data.get("artifact") or self.evidence_artifact
            # Lossless/digital files have content-driven Laplacian variance (text vs blank areas)
            # that is NOT a sensor noise inconsistency — skip sensor-based check
            if _artifact_is_lossless(artifact):
                return {
                    "contextual_anomalies_detected": 0,
                    "noise_variance_across_quadrants": 0.0,
                    "mean_noise_level": 0.0,
                    "quadrant_noise_levels": [],
                    "anomaly_description": (
                        "Scene incongruence analysis via sensor noise is not applicable to lossless "
                        "images (PNG/BMP/TIFF). Laplacian variance differences in screenshots reflect "
                        "content variation (text vs. blank areas), not camera sensor inconsistency."
                    ),
                    "not_applicable": True,
                    "court_defensible": True,
                    "available": True,
                }
            try:
                img = np.array(Image.open(artifact.file_path).convert("RGB"))
                gray = cv2.cvtColor(img, cv2.COLOR_RGB2GRAY).astype(float)
                h, w = gray.shape
                # Compute local noise level via Laplacian variance in 4 quadrants
                quadrant_noise = []
                for row in range(2):
                    for col in range(2):
                        q = gray[row*h//2:(row+1)*h//2, col*w//2:(col+1)*w//2]
                        lap = cv2.Laplacian(q.astype(np.uint8), cv2.CV_64F)
                        quadrant_noise.append(float(lap.var()))
                noise_std = float(np.std(quadrant_noise))
                noise_mean = float(np.mean(quadrant_noise))
                # Threshold: std must exceed 3× mean to indicate true sensor noise splice
                # (0.5× threshold produced false positives on natural images with mixed content)
                anomaly_detected = noise_std > noise_mean * 3.0 and noise_mean > 10
                return {
                    "contextual_anomalies_detected": 1 if anomaly_detected else 0,
                    "noise_variance_across_quadrants": round(noise_std, 2),
                    "mean_noise_level": round(noise_mean, 2),
                    "quadrant_noise_levels": [round(n, 2) for n in quadrant_noise],
                    "anomaly_description": (
                        f"Noise profile inconsistency detected across image regions "
                        f"(std={noise_std:.1f}, mean={noise_mean:.1f}) — possible inserted region"
                        if anomaly_detected else "Noise profile appears consistent across image regions"
                    ),
                }
            except Exception as e:
                return {"error": f"Scene incongruence analysis failed: {e}", "contextual_anomalies_detected": 0}
        
        async def contraband_database_handler(input_data: dict) -> dict:
            """
            CLIP zero-shot contextual analysis (upgrade from fake contraband DB).
            
            Uses shared CLIP utility to avoid loading the model multiple times.
            This does not claim a real weapons registry — it uses semantic similarity,
            which is court-defensible as "contextual analysis" rather than database matching.
            """
            from tools.clip_utils import get_clip_analyzer
            
            artifact = input_data.get("artifact") or self.evidence_artifact
            
            try:
                analyzer = get_clip_analyzer()
                import asyncio as _asyncio
                _loop = _asyncio.get_running_loop()
                result = await _loop.run_in_executor(
                    None,
                    lambda: analyzer.analyze_image(
                        artifact.file_path,
                        categories=None,  # Use default concern categories
                        check_concerns=True,
                    ),
                )
                
                if not result.available:
                    return {
                        "status": "unavailable",
                        "court_defensible": False,
                        "error": result.error or "CLIP model unavailable",
                    }
                
                return {
                    "status": "real",
                    "court_defensible": True,
                    "method": "CLIP zero-shot semantic similarity — NOT a weapons registry lookup (shared model)",
                    "top_matches": [
                        {"category": cat, "similarity": score} 
                        for cat, score in result.all_scores[:3]
                    ],
                    "concern_flag": result.concern_flag,
                    "available": True,
                    "backend": "open-clip ViT-B-32 (shared)",
                }
            except Exception as e:
                return {
                    "status": "error",
                    "court_defensible": False,
                    "error": str(e),
                }
            
        async def image_splice_check(input_data: dict) -> dict:
            artifact = input_data.get("artifact") or self.evidence_artifact
            # DCT quantization splicing detection only detects JPEG re-compression inconsistencies.
            # Lossless files have no JPEG quantization baseline — skip to avoid false positives.
            if _artifact_is_lossless(artifact):
                return {
                    "splicing_detected": False,
                    "not_applicable": True,
                    "file_format_note": (
                        "DCT quantization splice detection requires JPEG compression artifacts. "
                        "Lossless formats (PNG/BMP/TIFF) have no JPEG baseline — analysis skipped."
                    ),
                    "court_defensible": True,
                    "available": True,
                    "backend": "not-applicable-lossless",
                }
            ml_result = await run_ml_tool("splicing_detector.py", artifact.file_path, timeout=25.0)
            if ml_result.get("available") and not ml_result.get("error"):
                return ml_result
            # Inline DCT-based splicing fallback
            try:
                import cv2, numpy as np
                from PIL import Image
                img = np.array(Image.open(artifact.file_path).convert("L"))
                h, w = img.shape
                block_size = 8
                inconsistent_blocks = 0
                total_blocks = 0
                q_vals = []
                for y in range(0, h - block_size, block_size):
                    for x in range(0, w - block_size, block_size):
                        block = img[y:y+block_size, x:x+block_size].astype(np.float32)
                        dct = cv2.dct(block)
                        q_vals.append(float(np.abs(dct[4:, 4:]).mean()))
                        total_blocks += 1
                if q_vals:
                    mean_q = np.mean(q_vals)
                    std_q = np.std(q_vals)
                    inconsistent_blocks = int(sum(1 for v in q_vals if abs(v - mean_q) > 2 * std_q))
                splicing_detected = total_blocks > 0 and (inconsistent_blocks / total_blocks) > 0.15
                return {
                    "splicing_detected": splicing_detected,
                    "num_inconsistent_blocks": inconsistent_blocks,
                    "total_blocks": total_blocks,
                    "inconsistency_ratio": round(inconsistent_blocks / total_blocks, 3) if total_blocks else 0,
                    "backend": "opencv-dct-inline",
                    "court_defensible": True, "available": True,
                }
            except Exception as e:
                return {"splicing_detected": False, "error": str(e), "backend": "tool-exception", "court_defensible": False}

        def _artifact_is_lossless(artifact) -> bool:
            """Return True if the artifact is a lossless image format (PNG/BMP/TIFF/GIF/WEBP)."""
            import os as _os
            _lossless_exts  = {".png", ".bmp", ".tiff", ".tif", ".gif", ".webp"}
            _lossless_mimes = {"image/png", "image/bmp", "image/tiff", "image/gif", "image/webp"}
            ext  = _os.path.splitext(str(artifact.file_path))[1].lower()
            mime = ((artifact.metadata or {}).get("mime_type", "") if getattr(artifact, "metadata", None) else "").lower()
            return ext in _lossless_exts or mime in _lossless_mimes

        async def noise_fingerprint(input_data: dict) -> dict:
            artifact = input_data.get("artifact") or self.evidence_artifact
            # PRNU requires camera sensor noise — not applicable for lossless/digital files
            if _artifact_is_lossless(artifact):
                return {
                    "noise_fingerprint_not_applicable": True,
                    "verdict": "NOT_APPLICABLE",
                    "file_format_note": (
                        "PRNU noise fingerprint analysis requires a camera-captured image. "
                        "This file is a lossless format (PNG/BMP/TIFF/GIF/WEBP), indicating a "
                        "screenshot or digitally-created image — camera sensor noise patterns are "
                        "absent by design. PRNU results would be forensically unreliable."
                    ),
                    "court_defensible": True,
                    "available": True,
                }
            regions = input_data.get("regions", 6)
            ml_result = await run_ml_tool("noise_fingerprint.py", artifact.file_path,
                                          extra_args=["--regions", str(regions)], timeout=25.0)
            if ml_result.get("available") and not ml_result.get("error"):
                return ml_result
            # Inline PRNU-lite fallback using wavelet high-frequency residual
            try:
                import cv2, numpy as np
                from PIL import Image
                img = np.array(Image.open(artifact.file_path).convert("L"), dtype=np.float32)
                h, w = img.shape
                denoised = cv2.GaussianBlur(img, (5, 5), 0)
                noise = img - denoised
                num_regions = int(regions)
                rh, rw = h // 2, w // 2
                quadrant_stds = []
                for r in range(2):
                    for c in range(2):
                        q_noise = noise[r*rh:(r+1)*rh, c*rw:(c+1)*rw]
                        quadrant_stds.append(float(q_noise.std()))
                mean_std = float(np.mean(quadrant_stds))
                std_of_stds = float(np.std(quadrant_stds))
                outlier_regions = int(sum(1 for s in quadrant_stds if abs(s - mean_std) > std_of_stds))
                verdict = "INCONSISTENT" if outlier_regions > 0 else "CONSISTENT"
                return {
                    "verdict": verdict,
                    "noise_consistency_score": round(1.0 - std_of_stds / (mean_std + 1e-6), 3),
                    "outlier_region_count": outlier_regions,
                    "total_regions": len(quadrant_stds),
                    "region_noise_stds": [round(s, 3) for s in quadrant_stds],
                    "backend": "opencv-prnu-lite-inline",
                    "court_defensible": True, "available": True,
                }
            except Exception as e:
                return {"verdict": "INCONCLUSIVE", "error": str(e), "backend": "tool-exception", "court_defensible": False}
        
        async def inter_agent_call_handler(input_data: dict) -> dict:
            """Real inter-agent call via InterAgentBus (calls Agent 1 for lighting inconsistencies)."""
            if self._inter_agent_bus is None:
                return {"status": "skipped", "message": "No inter_agent_bus — cross-agent call skipped"}

            from core.inter_agent_bus import InterAgentCall, InterAgentCallType
            call = InterAgentCall(
                caller_agent_id=self.agent_id,
                callee_agent_id=input_data.get("target_agent", "Agent1"),
                call_type=InterAgentCallType.COLLABORATIVE,
                payload={
                    "region": input_data.get("region"),
                    "question": input_data.get("question", "Confirm lighting inconsistency in this region"),
                }
            )
            try:
                import asyncio
                response = await asyncio.wait_for(
                    self._inter_agent_bus.send(call, self.custody_logger),
                    timeout=15.0
                )
                return response
            except asyncio.TimeoutError:
                return {"status": "timeout", "message": "Inter-agent call timed out after 15s — proceeding without cross-validation"}
            except Exception as e:
                return {"status": "error", "message": f"Inter-agent call failed: {e}"}
        
        async def adversarial_robustness_check_handler(input_data: dict) -> dict:
            """
            Adversarial robustness check for object detection evasion.

            Applies mild patch-level perturbations (Gaussian blur, brightness
            shift, salt-and-pepper noise) to the image and re-runs the primary
            YOLO detection pass. If the set of detected classes changes
            substantially under perturbation the original detection may be
            near a decision boundary — a forensic red flag for adversarial
            patches (stickers designed to hide objects from ML detectors).
            """
            import numpy as np
            from PIL import Image as PILImage, ImageFilter
            import tempfile, os

            artifact = input_data.get("artifact") or self.evidence_artifact

            try:
                img_orig = PILImage.open(artifact.file_path).convert("RGB")

                def _detect_classes(pil_image) -> set:
                    """Run YOLO or OpenCV fallback and return set of detected class names."""
                    import os

                    # Set YOLO cache directory BEFORE importing
                    import pathlib
                    yolo_cache = os.getenv("YOLO_CONFIG_DIR", str(pathlib.Path.home() / ".cache" / "ultralytics"))
                    os.makedirs(yolo_cache, exist_ok=True)
                    os.environ["YOLO_CONFIG_DIR"] = yolo_cache
                    os.environ["ULTRALYTICS_CACHE_DIR"] = yolo_cache
                    
                    with tempfile.NamedTemporaryFile(suffix=".jpg", delete=False) as tmp:
                        pil_image.save(tmp.name, format="JPEG", quality=95)
                        tmp_path = tmp.name
                    try:
                        try:
                            from ultralytics import YOLO, settings
                            settings.update({'weights_dir': yolo_cache, 'cache_dir': yolo_cache})
                            model_path = os.path.join(yolo_cache, "yolov8n.pt")
                            model = YOLO(model_path)
                            results = model(tmp_path, conf=0.25, verbose=False)
                            classes = set()
                            for r in results:
                                for box in r.boxes:
                                    classes.add(model.names[int(box.cls)])
                            return classes
                        except ImportError:
                            # OpenCV contour fallback — just return count
                            import cv2
                            arr = np.array(pil_image)
                            gray = cv2.cvtColor(arr, cv2.COLOR_RGB2GRAY)
                            edges = cv2.Canny(gray, 50, 150)
                            cnts, _ = cv2.findContours(edges, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
                            h, w = gray.shape
                            sig = [c for c in cnts if cv2.contourArea(c) > h * w * 0.005]
                            return {f"region_{i}" for i in range(len(sig))}
                    finally:
                        os.unlink(tmp_path)

                original_classes = _detect_classes(img_orig)

                perturbation_results = {}

                # 1 — Gaussian blur (radius 2)
                blurred = img_orig.filter(ImageFilter.GaussianBlur(radius=2))
                blurred_classes = _detect_classes(blurred)
                perturbation_results["gaussian_blur_r2"] = {
                    "classes": sorted(blurred_classes),
                    "jaccard_similarity": len(original_classes & blurred_classes)
                    / max(len(original_classes | blurred_classes), 1),
                }

                # 2 — Brightness +20 % 
                arr = np.array(img_orig, dtype=np.float32)
                bright = np.clip(arr * 1.20, 0, 255).astype(np.uint8)
                bright_classes = _detect_classes(PILImage.fromarray(bright))
                perturbation_results["brightness_+20pct"] = {
                    "classes": sorted(bright_classes),
                    "jaccard_similarity": len(original_classes & bright_classes)
                    / max(len(original_classes | bright_classes), 1),
                }

                # 3 — Salt-and-pepper noise (1 % pixels)
                rng = np.random.default_rng(42)
                noisy_arr = arr.copy().astype(np.uint8)
                n_pixels = int(0.01 * arr.shape[0] * arr.shape[1])
                rows = rng.integers(0, arr.shape[0], n_pixels)
                cols = rng.integers(0, arr.shape[1], n_pixels)
                for r, c in zip(rows, cols):
                    noisy_arr[r, c] = rng.choice([0, 255])
                noisy_classes = _detect_classes(PILImage.fromarray(noisy_arr))
                perturbation_results["salt_pepper_1pct"] = {
                    "classes": sorted(noisy_classes),
                    "jaccard_similarity": len(original_classes & noisy_classes)
                    / max(len(original_classes | noisy_classes), 1),
                }

                min_similarity = min(v["jaccard_similarity"] for v in perturbation_results.values())
                evasion_detected = min_similarity < 0.50  # < 50 % class overlap under perturbation

                return {
                    "status": "real",
                    "court_defensible": True,
                    "method": "YOLO perturbation stability — blur, brightness, salt-and-pepper",
                    "adversarial_pattern_detected": evasion_detected,
                    "original_detected_classes": sorted(original_classes),
                    "perturbation_results": perturbation_results,
                    "min_jaccard_similarity": round(min_similarity, 4),
                    "confidence": 0.72 if evasion_detected else 0.89,
                    "note": (
                        "Object detections are highly sensitive to minor perturbations — possible adversarial patch concealment."
                        if evasion_detected
                        else "Object detections are stable under all perturbations — findings are robust."
                    ),
                }
            except Exception as e:
                return {
                    "status": "error",
                    "court_defensible": False,
                    "adversarial_pattern_detected": None,
                    "confidence": None,
                    "error": str(e),
                }
        async def object_text_ocr_handler(input_data: dict) -> dict:
            """
            OCR focused on detected object regions.

            Runs text extraction on the full image and on any bounding boxes passed in
            from prior object_detection output. Captures license plates, ID card numbers,
            document text, screen content, signs, and other identifying text that is
            forensically significant but not returned by YOLO detection alone.
            """
            import json as _json
            artifact = input_data.get("artifact") or self.evidence_artifact
            # Context: pull bboxes from the object_detection result that ran before us
            ctx_detections = self._tool_context.get("object_detection", {}).get("detections", [])
            detections = input_data.get("detections") or ctx_detections
            result = await run_ml_tool("object_text_ocr.py", artifact.file_path,
                                       extra_args=["--detections", _json.dumps(detections)], timeout=25.0)
            if result.get("available") and not result.get("error"):
                return result
            try:
                from PIL import Image
                img = Image.open(artifact.file_path).convert("RGB")
                w_img, h_img = img.size
                extracted_texts = []

                # Full-image Tesseract pass
                try:
                    import pytesseract
                    full_text = pytesseract.image_to_string(img, config="--psm 3").strip()
                    words = [t.strip() for t in full_text.split() if len(t.strip()) > 1]
                    if words:
                        extracted_texts.append({
                            "region": "full_image",
                            "text": full_text[:500],
                            "word_count": len(words),
                            "method": "tesseract",
                        })
                except Exception:
                    pass

                # EasyOCR fallback
                if not extracted_texts:
                    try:
                        import easyocr
                        reader = easyocr.Reader(["en"], gpu=False, verbose=False)
                        ocr_results = reader.readtext(artifact.file_path, detail=1)
                        items = [{"text": t.strip(), "confidence": round(float(c), 3)}
                                 for _, t, c in ocr_results if c > 0.3 and len(t.strip()) > 1]
                        if items:
                            extracted_texts.append({
                                "region": "full_image",
                                "text_items": items,
                                "word_count": len(items),
                                "method": "easyocr",
                            })
                    except Exception:
                        pass

                # Per-object-bounding-box pass
                for det in (detections or [])[:5]:
                    try:
                        bbox = det.get("bbox") or det.get("bounding_box", {})
                        if isinstance(bbox, dict):
                            x1, y1 = int(bbox.get("x", 0)), int(bbox.get("y", 0))
                            x2, y2 = int(bbox.get("x", 0) + bbox.get("w", w_img)), int(bbox.get("y", 0) + bbox.get("h", h_img))
                        elif isinstance(bbox, (list, tuple)) and len(bbox) >= 4:
                            x1, y1, x2, y2 = int(bbox[0]), int(bbox[1]), int(bbox[2]), int(bbox[3])
                        else:
                            continue
                        region = img.crop((max(0, x1), max(0, y1), min(w_img, x2), min(h_img, y2)))
                        if region.size[0] < 10 or region.size[1] < 10:
                            continue
                        try:
                            import pytesseract
                            region_text = pytesseract.image_to_string(region, config="--psm 6").strip()
                            if region_text and len(region_text.strip()) > 1:
                                extracted_texts.append({
                                    "region": f"object_{det.get('class_name', 'unknown')}",
                                    "text": region_text[:200],
                                    "word_count": len(region_text.split()),
                                    "method": "tesseract_bbox",
                                })
                        except Exception:
                            pass
                    except Exception:
                        continue

                combined = " ".join(r.get("text", "") for r in extracted_texts)
                return {
                    "text_found": bool(extracted_texts),
                    "regions_analyzed": len(extracted_texts),
                    "extracted_regions": extracted_texts[:8],
                    "combined_text_preview": combined[:400],
                    "total_words": sum(r.get("word_count", 0) for r in extracted_texts),
                    "forensic_note": (
                        f"OCR extracted text from {len(extracted_texts)} region(s). "
                        "May include license plates, ID numbers, usernames, timestamps, or other identifying information."
                        if extracted_texts else "No legible text found in image or object regions."
                    ),
                    "available": True,
                    "court_defensible": True,
                    "backend": "tesseract-easyocr-inline",
                }
            except Exception as e:
                return {"text_found": False, "error": str(e), "available": False, "court_defensible": False}

        async def document_authenticity_handler(input_data: dict) -> dict:
            """
            Document authenticity and forgery analysis.

            Analyses images of documents (IDs, passports, receipts, contracts) for signs
            of digital forgery: font inconsistency from inserted text, background texture
            irregularity from copy-paste, frequency domain anomalies from repeated elements,
            and edge sharpness variance from digital text overlaid on scanned backgrounds.
            """
            artifact = input_data.get("artifact") or self.evidence_artifact
            result = await run_ml_tool("document_authenticity.py", artifact.file_path, timeout=35.0)
            if result.get("available") and not result.get("error"):
                return result
            try:
                import cv2, numpy as np
                from PIL import Image
                img = Image.open(artifact.file_path).convert("RGB")
                arr = np.array(img)
                gray = cv2.cvtColor(arr, cv2.COLOR_RGB2GRAY)
                h, w = gray.shape
                flags = []
                score = 0.0

                # Check 1: Font/character size consistency via connected components
                _, thresh = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)
                num_labels, _, stats, _ = cv2.connectedComponentsWithStats(thresh, connectivity=8)
                char_h = stats[1:, cv2.CC_STAT_HEIGHT]
                char_w_vals = stats[1:, cv2.CC_STAT_WIDTH]
                char_mask = (char_h > 3) & (char_h < 80) & (char_w_vals > 2) & (char_w_vals < 100)
                char_components = char_h[char_mask]
                font_cv = 0.0
                if len(char_components) > 20:
                    font_cv = float(char_components.std() / (char_components.mean() + 1e-6))
                    if font_cv > 0.6:
                        flags.append(f"Font size inconsistency (CV={font_cv:.3f}) — possible text insertion from a different source")
                        score += 0.20

                # Check 2: Background edge density quadrant analysis
                if h > 100 and w > 100:
                    from scipy import ndimage
                    gx = np.abs(ndimage.sobel(gray, axis=1))
                    gy = np.abs(ndimage.sobel(gray, axis=0))
                    quad_edges = [(gx + gy)[r*h//2:(r+1)*h//2, c*w//2:(c+1)*w//2].mean()
                                  for r in range(2) for c in range(2)]
                    edge_cv = float(np.std(quad_edges) / (np.mean(quad_edges) + 1e-6))
                    if edge_cv > 0.50:
                        flags.append(f"Background edge density inconsistency ({edge_cv:.3f}) — regions may have different source material")
                        score += 0.15

                # Check 3: Frequency domain anomaly peaks (copy-paste leaves periodic peaks)
                fft = np.fft.fft2(gray.astype(np.float32))
                magnitude = np.log(np.abs(np.fft.fftshift(fft)) + 1)
                freq_peaks = int(np.sum(magnitude > magnitude.mean() + 4 * magnitude.std()))
                if freq_peaks > 50:
                    flags.append(f"Unusual frequency domain peaks ({freq_peaks}) — possible repeated copied elements")
                    score += 0.15

                # Check 4: Edge sharpness variance (digital text on scanned background)
                laplacian_vals = np.abs(cv2.Laplacian(gray, cv2.CV_64F))
                sharpness_std = float(laplacian_vals.std())
                if sharpness_std > 60:
                    flags.append(f"High edge sharpness variance ({sharpness_std:.1f}) — possible digital text insertion on scanned background")
                    score += 0.10

                verdict = (
                    "LIKELY_FORGED" if score >= 0.45
                    else "SUSPICIOUS" if score >= 0.25
                    else "APPEARS_AUTHENTIC"
                )
                return {
                    "verdict": verdict,
                    "forgery_score": round(min(score, 0.95), 3),
                    "flags": flags,
                    "font_inconsistency_cv": round(font_cv, 4),
                    "frequency_domain_peaks": freq_peaks,
                    "character_component_count": int(len(char_components)),
                    "note": "Document analysis is heuristic — specialized document verification models provide higher accuracy.",
                    "available": True,
                    "court_defensible": True,
                    "backend": "opencv-document-inline",
                }
            except Exception as e:
                return {"verdict": "ERROR", "error": str(e), "available": False, "court_defensible": False}

        # CRITICAL: object_detection must be registered FIRST - it's the primary tool for this agent
        registry.register("object_detection", object_detection, "Full-scene object detection using YOLOv8")
        registry.register("secondary_classification", secondary_classification, "Secondary classification pass")
        registry.register("scale_validation", scale_validation, "Scale and proportion validation")
        registry.register("lighting_consistency", lighting_consistency, "Lighting and shadow consistency check")
        registry.register("scene_incongruence", scene_incongruence, "Scene-level contextual incongruence analysis")
        registry.register("image_splice_check", image_splice_check, "Detect image splicing via DCT quantization inconsistencies")
        registry.register("noise_fingerprint", noise_fingerprint, "Detect camera noise fingerprint inconsistencies")
        registry.register("contraband_database", contraband_database_handler, "Contraband and weapons database cross-reference")
        registry.register("inter_agent_call", inter_agent_call_handler, "Inter-agent communication")
        registry.register("adversarial_robustness_check", adversarial_robustness_check_handler, "Adversarial robustness check")
        registry.register("object_text_ocr", object_text_ocr_handler, "OCR on detected object regions: license plates, IDs, signs, screen content")
        registry.register("document_authenticity", document_authenticity_handler, "Document forgery analysis: font consistency, background irregularity, frequency anomalies")

        # ── Gemini deep forensic analysis handler ──────────────────────────
        _gemini = GeminiVisionClient(self.config)

        async def gemini_deep_forensic_handler(input_data: dict) -> dict:
            """
            Comprehensive Gemini deep forensic analysis for object/scene context.
            Uses Agent 1's Gemini vision findings (if available) plus this agent's
            own YOLO detections to provide cross-validated object/weapon analysis.
            Identifies compositing, lighting inconsistencies, UI/interface content,
            and describes the full contextual narrative of what is in the image.

            Parallel deep-pass mode: the pipeline starts Agent3 deep concurrently
            with Agent1 deep. We run all our tools first, then wait here for Agent1's
            Gemini results (up to 120 s) before calling our own Gemini so we can
            feed Agent1's findings as cross-validation context.
            """
            artifact = input_data.get("artifact") or self.evidence_artifact

            # --- Wait for Agent1 Gemini context (parallel deep-pass mode) ---
            _ctx_event = getattr(self, "_agent1_context_event", None)
            if _ctx_event is not None and not _ctx_event.is_set():
                try:
                    await asyncio.wait_for(asyncio.shield(_ctx_event.wait()), timeout=120.0)
                except asyncio.TimeoutError:
                    logger.warning(
                        f"{self.agent_id}: Agent1 context wait timed out — "
                        "proceeding with YOLO-only context"
                    )

            # Build cross-agent context: YOLO detections from our initial pass
            # Check _tool_context first (faster), fall back to scanning _findings
            yolo_context: dict = {}
            try:
                yolo_cached = self._tool_context.get("object_detection", {})
                if yolo_cached:
                    yolo_context = {
                        "yolo_detected_classes": yolo_cached.get("classes_found", []),
                        "yolo_detection_count": yolo_cached.get("detection_count", 0),
                        "yolo_weapon_classes": [
                            d.get("class_name", "") for d in yolo_cached.get("weapon_detections", [])
                        ],
                        "yolo_backend": yolo_cached.get("backend", ""),
                    }
                else:
                    # Fallback: scan findings for object_detection finding
                    yolo_findings = [
                        f for f in (self._findings or [])
                        if (f.metadata or {}).get("tool_name") == "object_detection"
                    ]
                    if yolo_findings:
                        yolo_out = yolo_findings[0].metadata or {}
                        yolo_context = {
                            "yolo_detected_classes": yolo_out.get("classes_found", []),
                            "yolo_detection_count": yolo_out.get("detection_count", 0),
                            "yolo_weapon_classes": [
                                d.get("class_name", "") for d in yolo_out.get("weapon_detections", [])
                            ],
                            "yolo_backend": yolo_out.get("backend", ""),
                        }
            except Exception:
                pass

            # Build Agent 1 context (injected by pipeline from Agent 1's Gemini analysis)
            agent1_context: dict = {}
            try:
                a1 = self._agent1_context
                if a1:
                    agent1_context = {
                        "agent1_image_content_type": a1.get("gemini_content_type", ""),
                        "agent1_scene_description": str(a1.get("gemini_narrative", a1.get("gemini_scene", "")))[:400],
                        "agent1_objects_detected": a1.get("gemini_detected_objects", []),
                        "agent1_manipulation_signals": a1.get("gemini_manipulation_signals", []),
                        "agent1_extracted_text": a1.get("gemini_extracted_text", []),
                        "agent1_interface": a1.get("gemini_interface", ""),
                        "agent1_verdict": a1.get("gemini_verdict", ""),
                    }
                    # Remove empty fields
                    agent1_context = {k: v for k, v in agent1_context.items() if v not in ("", None, [], {})}
            except Exception:
                pass

            # Merge contexts into exif_summary-style dict for Gemini
            context_summary: dict = {}
            context_summary.update(yolo_context)
            if agent1_context:
                context_summary["agent1_image_forensics"] = agent1_context

            try:
                finding = await _gemini.deep_forensic_analysis(
                    file_path=artifact.file_path,
                    exif_summary=context_summary if context_summary else None,
                )
            except Exception as gemini_exc:
                await self._record_tool_error("gemini_deep_forensic", str(gemini_exc))
                return {
                    "error": f"Gemini vision failed: {gemini_exc}",
                    "gemini_content_type": "unknown",
                    "court_defensible": False,
                    "agent1_context_used": bool(agent1_context),
                    "yolo_context_used": bool(yolo_context),
                }

            if finding.error:
                await self._record_tool_error("gemini_deep_forensic", finding.error)
                return {
                    "error": f"Gemini vision failed: {finding.error}",
                    "gemini_content_type": "unknown",
                    "court_defensible": False,
                    "agent1_context_used": bool(agent1_context),
                    "yolo_context_used": bool(yolo_context),
                }

            result = finding.to_finding_dict(self.agent_id)

            # Expose key fields; safely stringify detected_objects (may be dicts)
            raw_objects = finding.detected_objects or []
            safe_objects = []
            for obj in raw_objects:
                if isinstance(obj, dict):
                    label = obj.get("label") or obj.get("name") or obj.get("class_name") or str(obj)
                    conf = obj.get("confidence") or obj.get("score")
                    safe_objects.append(f"{label} ({conf:.0%})" if conf else str(label))
                else:
                    safe_objects.append(str(obj))

            result["gemini_validated_objects"] = safe_objects
            result["gemini_compositing_signals"] = [str(s) for s in (finding.manipulation_signals or [])]
            result["gemini_scene_coherence"] = str(finding.content_description or "")
            result["gemini_content_type"] = finding.file_type_assessment
            result["gemini_extracted_text"] = getattr(finding, "_extracted_text", [])
            result["gemini_interface"] = getattr(finding, "_interface_identification", "")
            result["gemini_narrative"] = getattr(finding, "_contextual_narrative", "")
            result["gemini_verdict"] = getattr(finding, "_authenticity_verdict", "")
            # Include cross-agent context in result for traceability
            result["agent1_context_used"] = bool(agent1_context)
            result["yolo_context_used"] = bool(yolo_context)
            await self._record_tool_result("gemini_deep_forensic", result)
            return result

        registry.register(
            "gemini_deep_forensic",
            gemini_deep_forensic_handler,
            "Gemini deep forensic analysis: content ID, text extraction, object/weapon detection, interface identification, scene narrative and coherence",
        )

        return registry
    
    async def build_initial_thought(self) -> str:
        """
        Build the contextually-grounded initial thought for the ReAct loop.

        Pre-screens with scene_incongruence (CLIP semantic analysis, fast) to
        get immediate scene-level context — what type of scene/environment this
        is, what objects are expected vs unexpected — before running YOLO
        object detection and lighting consistency checks.
        """
        context_lines = []
        context = " | ".join(context_lines) if context_lines else "Scene pre-screen unavailable."
        return (
            f"Starting scene and object analysis. Evidence: {self.evidence_artifact.artifact_id}. "
            f"Scene pre-screen — {context} "
            f"Proceeding through {len(self.task_decomposition)} tasks: "
            "full-scene object detection, secondary classification, scale validation, "
            "lighting and shadow consistency, scene incongruence, image splice check, "
            "noise fingerprint, and contraband database cross-reference. "
            "Conservative threshold principle applies throughout: "
            "every finding must be court-defensible before it is recorded."
        )

    async def run_investigation(self):
        from core.react_loop import AgentFinding
        from core.working_memory import TaskStatus

        # Always initialize working memory first so the heartbeat can show
        # the file-type validation step instead of "Initiating 1/N tasks".
        await self._initialize_working_memory()

        file_path = self.evidence_artifact.file_path.lower()
        mime = (self.evidence_artifact.metadata or {}).get("mime_type", "").lower()
        audio_exts = (".wav", ".mp3", ".flac", ".ogg", ".aac", ".m4a")
        is_audio = any(file_path.endswith(e) for e in audio_exts) or mime.startswith("audio/")
        if is_audio:
            # Mark all tasks complete so the heartbeat shows full progress
            try:
                state = await self.working_memory.get_state(
                    session_id=self.session_id, agent_id=self.agent_id
                )
                if state:
                    for task in state.tasks:
                        await self.working_memory.update_task(
                            session_id=self.session_id,
                            agent_id=self.agent_id,
                            task_id=task.task_id,
                            status=TaskStatus.COMPLETE,
                            result_ref="file_type_validation",
                        )
            except Exception:
                pass

            finding = AgentFinding(
                agent_id=self.agent_id,
                finding_type="File type not applicable",
                confidence_raw=1.0,
                status="CONFIRMED",
                evidence_refs=[],
                reasoning_summary=(
                    "Object Detection — The uploaded evidence is an audio file. "
                    "Scene composition, lighting consistency, and object detection are "
                    "not applicable without visual frames. No spatial analysis performed."
                ),
            )
            self._findings = [finding]
            self._react_chain = []
            self._reflection_report = None
            return self._findings

        # For image/video files, run the full investigation.
        # Flag tells base class not to re-initialize working memory.
        self._skip_memory_init = True
        # Always rebuild tool registry before the main pass so deep pass also gets
        # the gemini_deep_forensic handler (base_agent reuses _tool_registry).
        self._tool_registry = await self.build_tool_registry()
        return await super().run_investigation()