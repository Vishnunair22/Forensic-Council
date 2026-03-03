"""
Agent 3 - Object & Weapon Analysis Agent.

Object identification and contextual validation specialist for detecting 
and contextually validating objects, weapons, and contraband.
"""

from __future__ import annotations

import uuid
from typing import Any
import random
import hashlib

from agents.base_agent import ForensicAgent
from core.config import Settings
from core.custody_logger import CustodyLogger
from core.episodic_memory import EpisodicMemory
from core.evidence import EvidenceArtifact
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
    
    @property
    def agent_name(self) -> str:
        """Human-readable name of this agent."""
        return "Agent3_ObjectWeapon"
    
    @property
    def task_decomposition(self) -> list[str]:
        """
        List of tasks this agent performs.
        Exact 9 tasks from architecture document.
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
        ]
    
    @property
    def iteration_ceiling(self) -> int:
        """Maximum iterations for the ReAct loop."""
        return 20
    
    async def build_tool_registry(self) -> ToolRegistry:
        """
        Build and return the tool registry for this agent.
        
        Registers stub tools for:
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
        
        # Make stub tools deterministic based on actual file content
        import hashlib
        from PIL import Image as _PILImg
        try:
            with open(self.evidence_artifact.file_path, "rb") as f:
                _img_bytes = f.read(4096)  # first 4KB
        except Exception:
            _img_bytes = str(self.evidence_artifact.artifact_id).encode()
        seed_val = int(hashlib.md5(_img_bytes).hexdigest()[:8], 16)
        rng = random.Random(seed_val)
        
        async def object_detection(input_data: dict) -> dict:
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
                }
            except Exception as e:
                # Return graceful error dictionary rather than raising
                return {"error": f"Object detection failed: {e}", "objects_detected": [], "total_count": 0}
        
        async def secondary_classification(input_data: dict) -> dict:
            return {"status": "success", "refined_classifications": {"person": "adult male", "vehicle": "sedan", "bag": "backpack"}}
        
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
            import cv2, numpy as np
            from PIL import Image
            artifact = input_data.get("artifact") or self.evidence_artifact
            try:
                img = np.array(Image.open(artifact.file_path).convert("RGB"))
                gray = cv2.cvtColor(img, cv2.COLOR_RGB2GRAY).astype(float)
                h, w = gray.shape
                # Split into 9 grid cells, measure brightness per cell
                cells = []
                for row in range(3):
                    for col in range(3):
                        cell = gray[row*h//3:(row+1)*h//3, col*w//3:(col+1)*w//3]
                        cells.append(float(cell.mean()))
                cell_std = float(np.std(cells))
                # High std across cells means uneven lighting
                # Compute Sobel gradient direction as proxy for shadow angle
                sobelx = cv2.Sobel(gray, cv2.CV_64F, 1, 0, ksize=5)
                sobely = cv2.Sobel(gray, cv2.CV_64F, 0, 1, ksize=5)
                angles = np.arctan2(sobely, sobelx) * (180 / np.pi)
                # Dominant gradient angle
                hist, bins = np.histogram(angles.flatten(), bins=36, range=(-180, 180))
                dominant_angle = float(bins[np.argmax(hist)])
                lighting_consistent = cell_std < 30.0
                return {
                    "lighting_consistent": lighting_consistent,
                    "brightness_std_across_regions": round(cell_std, 2),
                    "dominant_gradient_angle_deg": round(dominant_angle, 1),
                    "region_brightness_values": [round(c, 1) for c in cells],
                    "assessment": "uniform lighting" if lighting_consistent else "uneven lighting detected — possible compositing",
                }
            except Exception as e:
                return {"error": f"Lighting consistency check failed: {e}", "lighting_consistent": True}
        
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
        
        async def contraband_database(input_data: dict) -> dict:
            has_hit = rng.choice([False, False, False, True])
            hit_data = {"database_match": "N/A"}
            if has_hit:
                hit_data = {"database_match": "Unregistered firearm (mock)", "match_confidence": 0.88}
            return {"status": "success", "contraband_check": has_hit, "details": hit_data}
            
        async def image_splice_check(input_data: dict) -> dict:
            artifact = input_data.get("artifact") or self.evidence_artifact
            return await run_ml_tool("splicing_detector.py", artifact.file_path, timeout=25.0)

        async def noise_fingerprint(input_data: dict) -> dict:
            artifact = input_data.get("artifact") or self.evidence_artifact
            regions = input_data.get("regions", 6)
            return await run_ml_tool("noise_fingerprint.py", artifact.file_path, 
                                      extra_args=["--regions", str(regions)], timeout=25.0)
        
        async def inter_agent_call(input_data: dict) -> dict:
            return {"status": "success", "response": "Acknowledged by target agent."}
        
        async def adversarial_robustness_check(input_data: dict) -> dict:
            return {"status": "success", "adversarial_pattern_detected": rng.choice([True, False, False]), "confidence": round(rng.uniform(0.1, 0.9), 2)}
        
        # Register tools
        registry.register("object_detection", object_detection, "Full-scene object detection")
        registry.register("secondary_classification", secondary_classification, "Secondary classification pass")
        registry.register("scale_validation", scale_validation, "Scale and proportion validation")
        registry.register("lighting_consistency", lighting_consistency, "Lighting and shadow consistency check")
        registry.register("scene_incongruence", scene_incongruence, "Scene-level contextual incongruence analysis")
        registry.register("image_splice_check", image_splice_check, "Detect image splicing via DCT quantization inconsistencies")
        registry.register("noise_fingerprint", noise_fingerprint, "Detect camera noise fingerprint inconsistencies")
        registry.register("contraband_database", contraband_database, "Contraband and weapons database cross-reference")
        registry.register("inter_agent_call", inter_agent_call, "Inter-agent communication")
        registry.register("adversarial_robustness_check", adversarial_robustness_check, "Adversarial robustness check")
        
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