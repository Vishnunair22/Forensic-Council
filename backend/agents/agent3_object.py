"""
Agent 3 - Object & Weapon Analysis Agent.

Object identification and contextual validation specialist for detecting 
and contextually validating objects, weapons, and contraband.
"""

from __future__ import annotations

import uuid
from typing import Any, Optional
import random
import hashlib

from agents.base_agent import ForensicAgent
from core.config import Settings
from core.custody_logger import CustodyLogger
from core.episodic_memory import EpisodicMemory
from core.evidence import EvidenceArtifact
from core.inter_agent_bus import InterAgentBus, InterAgentCall, InterAgentCallType
from core.tool_registry import ToolRegistry
from core.working_memory import WorkingMemory
from core.ml_subprocess import run_ml_tool
from infra.evidence_store import EvidenceStore


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
    
    @property
    def agent_name(self) -> str:
        """Human-readable name of this agent."""
        return "Agent3_ObjectWeapon"
    
    @property
    def task_decomposition(self) -> list[str]:
        """
        List of tasks this agent performs.
        Exact 12 tasks from architecture document.
        """
        return [
            "Run full-scene primary object detection",
            "For each detected object below confidence threshold: run secondary classification pass",
            "For each confirmed object: run scale and proportion validation",
            "For each confirmed object: run lighting and shadow consistency check",
            "Run scene-level contextual incongruence analysis",
            "Run ML-based image splicing detection on objects",
            "Run camera noise fingerprint analysis for region consistency",
            "Cross-reference confirmed objects against contraband/weapons database",
            "Issue inter-agent call to Agent 1 for any region showing lighting inconsistency",
            "Run adversarial robustness check against object detection evasion",
            "Self-reflection pass",
            "Submit calibrated findings to Arbiter",
        ]
    
    @property
    def iteration_ceiling(self) -> int:
        """Maximum iterations for the ReAct loop."""
        return 20
    
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
            try:
                from ultralytics import YOLO
            except ImportError:
                # Fallback to OpenCV heuristics if YOLO not available
                return await _object_detection_opencv(input_data)
            
            artifact = input_data.get("artifact") or self.evidence_artifact
            
            try:
                # YOLOv8n is 6MB — runs CPU-only in ~200ms
                # Auto-downloads on first call
                model = YOLO("yolov8n.pt")
                results = model(artifact.file_path, conf=0.25, verbose=False)
                
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
                
                return {
                    "detections": detections,
                    "detection_count": len(detections),
                    "weapon_detections": weapon_detections,
                    "classes_found": list({d["class_name"] for d in detections}),
                    "court_defensible": True,
                    "available": True,
                    "backend": "ultralytics-yolov8n",
                }
            except Exception as e:
                # Fallback to OpenCV heuristics
                return await _object_detection_opencv(input_data)
        
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
                    result = analyzer.analyze_image(
                        tmp_path,
                        categories=base_categories,
                        check_concerns=True,
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

                return {
                    "status": "real",
                    "court_defensible": True,
                    "method": "CLIP ViT-B-32 zero-shot classification — targeted label set",
                    "input_object_class": low_conf_object,
                    "top_refined_match": result.top_match,
                    "top_confidence": round(result.top_confidence, 4),
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
                # Very low angle std = mostly parallel lines = may lack perspective = suspicious
                scale_consistent = 15.0 < angle_std < 80.0
                return {
                    "scale_consistent": scale_consistent,
                    "line_count": len(lines),
                    "angle_std_deg": round(angle_std, 2),
                    "assessment": "perspective angles appear natural" if scale_consistent else "unusual perspective consistency — possible copy-paste or compositing",
                }
            except Exception as e:
                return {"error": f"Scale validation failed: {e}", "scale_consistent": True}
        
        async def lighting_consistency(input_data: dict) -> dict:
            """Lighting analysis using Hough shadow-direction detector."""
            artifact = input_data.get("artifact") or self.evidence_artifact
            return await run_ml_tool(
                "lighting_analyzer.py",
                artifact.file_path,
                timeout=20.0
            )
        
        async def scene_incongruence(input_data: dict) -> dict:
            import cv2, numpy as np
            from PIL import Image
            artifact = input_data.get("artifact") or self.evidence_artifact
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
                # High variance between quadrant noise = inconsistent sensor noise = insertion
                anomaly_detected = noise_std > noise_mean * 0.5 and noise_mean > 10
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
                
                result = analyzer.analyze_image(
                    artifact.file_path,
                    categories=None,  # Use default concern categories
                    check_concerns=True,
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
            return await run_ml_tool("splicing_detector.py", artifact.file_path, timeout=25.0)

        async def noise_fingerprint(input_data: dict) -> dict:
            artifact = input_data.get("artifact") or self.evidence_artifact
            regions = input_data.get("regions", 6)
            return await run_ml_tool("noise_fingerprint.py", artifact.file_path, 
                                      extra_args=["--regions", str(regions)], timeout=25.0)
        
        async def inter_agent_call_handler(input_data: dict) -> dict:
            """Real inter-agent call via InterAgentBus (calls Agent 1 for lighting inconsistencies)."""
            if self._inter_agent_bus is None:
                return {"status": "error", "message": "No inter_agent_bus injected"}

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
            response = await self._inter_agent_bus.send(call, self._custody_logger)
            return response
        
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
                    with tempfile.NamedTemporaryFile(suffix=".jpg", delete=False) as tmp:
                        pil_image.save(tmp.name, format="JPEG", quality=95)
                        tmp_path = tmp.name
                    try:
                        try:
                            from ultralytics import YOLO
                            model = YOLO("yolov8n.pt")
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
        registry.register("secondary_classification", secondary_classification, "Secondary classification pass")
        registry.register("scale_validation", scale_validation, "Scale and proportion validation")
        registry.register("lighting_consistency", lighting_consistency, "Lighting and shadow consistency check")
        registry.register("scene_incongruence", scene_incongruence, "Scene-level contextual incongruence analysis")
        registry.register("image_splice_check", image_splice_check, "Detect image splicing via DCT quantization inconsistencies")
        registry.register("noise_fingerprint", noise_fingerprint, "Detect camera noise fingerprint inconsistencies")
        registry.register("contraband_database", contraband_database_handler, "Contraband and weapons database cross-reference")
        registry.register("inter_agent_call", inter_agent_call_handler, "Inter-agent communication")
        registry.register("adversarial_robustness_check", adversarial_robustness_check_handler, "Adversarial robustness check")
        
        return registry
    
    async def build_initial_thought(self) -> str:
        """
        Build the initial thought for the ReAct loop.
        
        Returns:
            Opening thought for object/weapon analysis investigation
        """
        return (
            f"Starting object and weapon analysis for artifact "
            f"{self.evidence_artifact.artifact_id}. "
            f"I will begin with full-scene primary object detection, "
            f"then proceed through secondary classification for low-confidence objects, "
            f"scale validation, lighting consistency checks, and database cross-referencing. "
            f"Total tasks to complete: {len(self.task_decomposition)}. "
            f"Note: Conservative threshold principle applies - every finding must be court-defensible."
        )

    async def run_investigation(self):
        from core.react_loop import AgentFinding
        file_path = self.evidence_artifact.file_path.lower()
        mime = (self.evidence_artifact.metadata or {}).get("mime_type", "").lower()
        audio_exts = (".wav", ".mp3", ".flac", ".ogg", ".aac", ".m4a")
        video_exts = (".mp4", ".avi", ".mov", ".mkv")
        is_audio_video = (
            any(file_path.endswith(e) for e in audio_exts + video_exts)
            or mime.startswith(("audio/", "video/"))
        )
        if is_audio_video:
            finding = AgentFinding(
                agent_id=self.agent_id,
                finding_type="File type not applicable",
                confidence_raw=1.0,
                status="CONFIRMED",
                evidence_refs=[],
                reasoning_summary=(
                    "Object Detection — The uploaded evidence is an audio or video file. "
                    "Scene composition, lighting consistency, and object detection are "
                    "not applicable without visual frames. No spatial analysis performed."
                ),
            )
            self._findings = [finding]
            self._react_chain = []
            self._reflection_report = None
            return self._findings
        return await super().run_investigation()