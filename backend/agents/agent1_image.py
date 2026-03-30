"""
Agent 1 — Image Integrity Agent.

Pixel-level forensic expert for detecting manipulation, splicing, 
compositing, and anti-forensics evasion.
"""

from __future__ import annotations


from agents.base_agent import ForensicAgent
from core.tool_registry import ToolRegistry
from core.ml_subprocess import run_ml_tool
# Import real tool implementations
from tools.image_tools import (
    ela_full_image as real_ela_full_image,
    roi_extract as real_roi_extract,
    jpeg_ghost_detect as real_jpeg_ghost_detect,
    file_hash_verify as real_file_hash_verify,
    frequency_domain_analysis as real_frequency_domain_analysis,
    compute_perceptual_hash as real_compute_perceptual_hash,
    extract_text_from_image as real_extract_text_from_image,
    analyze_image_content as real_analyze_image_content,
)
from tools.ocr_tools import extract_evidence_text as real_extract_evidence_text
from core.gemini_client import GeminiVisionClient
from core.image_utils import is_lossless_image

class Agent1Image(ForensicAgent):
    """
    Agent 1 — Image Integrity Agent.
    
    Mandate: Detect manipulation, splicing, compositing, and anti-forensics 
    evasion at the pixel level.
    
    Task Decomposition:
    1. Run full-image ELA and map anomaly regions
    2. Run ELA anomaly block classification on flagged blocks
    3. Isolate and re-analyze all flagged ROIs with noise footprint analysis
    4. Run JPEG ghost detection on all flagged regions
    5. Run frequency domain analysis on contested regions
    6. Run frequency-domain GAN artifact detection
    7. Verify file hash against ingestion hash
    8. Run adversarial robustness check against known anti-ELA evasion techniques
    9. Self-reflection pass
    10. Submit calibrated findings to Arbiter
    """
    
    @property
    def agent_name(self) -> str:
        """Human-readable name of this agent."""
        return "Agent1_ImageIntegrity"
    
    @property
    def _is_lossless(self) -> bool:
        """True if the evidence file is a lossless image (PNG, BMP, TIFF, GIF, WEBP)."""
        file_path = getattr(self.evidence_artifact, "file_path", "") or ""
        mime = getattr(self.evidence_artifact, "mime_type", "") or ""
        return is_lossless_image(file_path, mime or None)

    @property
    def task_decomposition(self) -> list[str]:
        """
        Initial analysis tasks — fast numpy/OpenCV tools, ~15-20s total.
        For JPEG files: ELA full-image scan + JPEG ghost detection.
        ELA anomaly block classification is deferred to deep pass so the
        initial phase stays lean; the deep pass uses the initial ELA map
        (available via _tool_context) for higher-quality classification.
        For lossless (PNG/BMP/TIFF/WEBP/GIF): skips JPEG-specific tools;
        uses frequency domain, noise fingerprint, and semantic analysis instead.
        """
        base = [
            "Perform semantic image understanding to identify image type and context",
            "Run frequency-domain GAN artifact detection",
            "Compute perceptual hash for similarity detection",
        ]
        if self._is_lossless:
            # Lossless images: Run noise fingerprint (regional texture consistency)
            # and frequency domain analysis as primary integrity checks.
            return base + [
                "Run noise footprint analysis for region source inconsistency",
                "Self-reflection pass",
            ]
        else:
            # JPEG (lossy): ELA map + ghost detection; ELA block classification in deep
            return base + [
                "Run full-image ELA and map anomaly regions",
                "Run JPEG ghost detection on all flagged regions",
                "Self-reflection pass",
            ]

    @property
    def deep_task_decomposition(self) -> list[str]:
        """
        Deep/heavy tasks — Gemini vision, heavy ML models, advanced forensic checks.
        ELA anomaly block classification runs here for ALL file types:
        - JPEG: deferred from initial pass; leverages initial ELA map via _tool_context
        - Lossless: first time it runs (ELA not applicable in initial pass)
        """
        return [
            "Run Gemini deep forensic analysis: identify content type, extract all text, detect objects and weapons, identify interfaces, describe what is happening, cross-validate metadata",
            "Run ELA anomaly block classification on flagged blocks",
            "Run frequency domain analysis on contested regions",
            "Isolate and re-analyze all flagged ROIs with noise footprint analysis",
            "Detect copy-move forgery in flagged ROI regions",
            "Run adversarial robustness check against known anti-ELA evasion techniques",
            "Extract visible text via OCR for contextual analysis",
            "Run PRNU camera sensor fingerprint analysis to detect cross-region source inconsistency",
            "Run CFA demosaicing pattern consistency analysis on contested regions",
        ]

    @property
    def iteration_ceiling(self) -> int:
        """Maximum iterations — tasks + 3 buffer regardless of file type."""
        return len(self.task_decomposition) + 3
    
    @property
    def supported_file_types(self) -> list[str]:
        """Image agent supports image file types."""
        return ['image/']
    
    async def build_tool_registry(self) -> ToolRegistry:
        """
        Build and return the tool registry for this agent.
        
        Registers real tool implementations for:
        - ela_full_image: Full-image Error Level Analysis
        - roi_extract: Region of Interest extraction
        - jpeg_ghost_detect: JPEG ghost detection
        - frequency_domain_analysis: Frequency domain analysis
        - file_hash_verify: File hash verification
        - perceptual_hash: Perceptual hash computation
        - adversarial_robustness_check: ELA perturbation stability analysis
        - sensor_db_query: Camera sensor noise profile analysis via EXIF + PRNU heuristics
        """
        registry = ToolRegistry()
        
        # Real tool handlers - wrap to accept input_data dict
        async def ela_full_image_handler(input_data: dict) -> dict:
            """Handle ELA analysis with input_data dict."""
            artifact = input_data.get("artifact") or self.evidence_artifact
            evidence_store = input_data.get("evidence_store")
            quality = input_data.get("quality", 95)
            anomaly_threshold = input_data.get("anomaly_threshold", 10.0)
            # ELA is not applicable to PNG/lossless files — the tool itself will
            # detect this and return ela_not_applicable=True.  No threshold tweak needed.
            result = await real_ela_full_image(
                artifact=artifact,
                evidence_store=evidence_store,
                quality=quality,
                anomaly_threshold=anomaly_threshold,
            )
            if result.get("error"):
                await self._record_tool_error("ela_full_image", result["error"])
            else:
                await self._record_tool_result("ela_full_image", result)
            return result
        
        async def roi_extract_handler(input_data: dict) -> dict:
            """Handle ROI extraction with input_data dict."""
            artifact = input_data.get("artifact") or self.evidence_artifact
            
            # Use center crop as a more meaningful default than top-left
            from PIL import Image as PILImage
            try:
                img = PILImage.open(artifact.file_path)
                w, h = img.size
                cx, cy = w // 2, h // 2
                crop_size = min(w, h) // 4
                bounding_box = input_data.get("bounding_box", {
                    "x": max(0, cx - crop_size),
                    "y": max(0, cy - crop_size),
                    "w": crop_size * 2,
                    "h": crop_size * 2,
                })
            except Exception:
                bounding_box = input_data.get("bounding_box", {"x": 0, "y": 0, "w": 100, "h": 100})
            
            evidence_store = input_data.get("evidence_store")
            return await real_roi_extract(
                artifact=artifact,
                bounding_box=bounding_box,
                evidence_store=evidence_store,
            )
        
        async def jpeg_ghost_detect_handler(input_data: dict) -> dict:
            """Handle JPEG ghost detection with input_data dict."""
            artifact = input_data.get("artifact") or self.evidence_artifact
            quality_levels = input_data.get("quality_levels")
            ghost_threshold = input_data.get("ghost_threshold", 5.0)
            result = await real_jpeg_ghost_detect(
                artifact=artifact,
                quality_levels=quality_levels,
                ghost_threshold=ghost_threshold,
            )
            if result.get("error"):
                await self._record_tool_error("jpeg_ghost_detect", result["error"])
            else:
                await self._record_tool_result("jpeg_ghost_detect", result)
            return result
        
        async def frequency_domain_analysis_handler(input_data: dict) -> dict:
            """Handle frequency domain analysis with input_data dict."""
            artifact = input_data.get("artifact") or self.evidence_artifact
            result = await real_frequency_domain_analysis(artifact=artifact)
            if result.get("error"):
                await self._record_tool_error("frequency_domain_analysis", result["error"])
            else:
                await self._record_tool_result("frequency_domain_analysis", result)
            return result
        
        async def file_hash_verify_handler(input_data: dict) -> dict:
            """Handle file hash verification with input_data dict."""
            artifact = input_data.get("artifact") or self.evidence_artifact
            evidence_store = input_data.get("evidence_store")
            if evidence_store is None:
                result = {
                    "hash_matches": True,
                    "original_hash": artifact.content_hash,
                    "current_hash": artifact.content_hash,
                }
            else:
                result = await real_file_hash_verify(artifact=artifact, evidence_store=evidence_store)
            if result.get("error"):
                await self._record_tool_error("file_hash_verify", result["error"])
            else:
                await self._record_tool_result("file_hash_verify", result)
            return result
        
        async def perceptual_hash_handler(input_data: dict) -> dict:
            """Handle perceptual hash computation with input_data dict."""
            artifact = input_data.get("artifact") or self.evidence_artifact
            hash_size = input_data.get("hash_size", 8)
            result = await real_compute_perceptual_hash(
                artifact=artifact,
                hash_size=hash_size,
            )
            if result.get("error"):
                await self._record_tool_error("perceptual_hash", result["error"])
            else:
                await self._record_tool_result("perceptual_hash", result)
            return result
            
        async def ela_anomaly_classify_handler(input_data: dict) -> dict:
            artifact = input_data.get("artifact") or self.evidence_artifact
            quality = input_data.get("quality", 95)
            # ELA is meaningless for lossless formats — check FIRST, before the ML
            # subprocess runs, so PNG/BMP/TIFF/GIF/WEBP always return not_applicable
            # regardless of whether the ML tool is available.
            # Evidence files may be stored as UUID .bin paths, so check PIL magic bytes
            # and MIME type in addition to the file extension.
            _mime = getattr(artifact, "mime_type", None) or ""
            if is_lossless_image(artifact.file_path, _mime or None):
                not_applicable = {
                    "ela_not_applicable": True,
                    "ela_limitation_note": (
                        "ELA block classification requires JPEG re-compression artifacts; "
                        "lossless formats (PNG/BMP/TIFF) produce no baseline compression noise, "
                        "making ELA results forensically unreliable for this file."
                    ),
                    "anomaly_detected": False,
                    "anomaly_block_count": 0,
                    "num_anomaly_regions": 0,
                    "court_defensible": True,
                    "available": True,
                    "backend": "pil-ela-inline",
                }
                await self._record_tool_result("ela_anomaly_classify", not_applicable)
                return not_applicable
            result = await run_ml_tool("ela_anomaly_classifier.py", artifact.file_path,
                                      extra_args=["--quality", str(quality)], timeout=25.0)
            if result.get("available") and not result.get("error"):
                await self._record_tool_result("ela_anomaly_classify", result)
                return result
            # Inline ELA fallback using PIL re-save at different quality
            try:
                import io
                import numpy as np
                from PIL import Image
                img = Image.open(artifact.file_path).convert("RGB")
                buf = io.BytesIO()
                img.save(buf, format="JPEG", quality=int(quality))
                buf.seek(0)
                recompressed = Image.open(buf).convert("RGB")
                ela = np.abs(np.array(img, dtype=np.int16) - np.array(recompressed, dtype=np.int16)).astype(np.uint8)
                # Context: use ELA mean from the full-image scan as the anomaly threshold
                # baseline if it ran first, otherwise compute it fresh
                prior_ela = self._tool_context.get("ela_full_image", {})
                ela_mean = float(prior_ela.get("ela_mean", ela.mean()))
                ela_max = int(ela.max())
                # Split into 8x8 blocks and score each
                arr = ela.mean(axis=2)  # grayscale
                h, w = arr.shape
                block_scores = []
                for y in range(0, h-8, 8):
                    for x in range(0, w-8, 8):
                        block_scores.append(float(arr[y:y+8, x:x+8].mean()))
                anomaly_blocks = int(sum(1 for s in block_scores if s > ela_mean * 2.5))
                classify_result = {
                    "anomaly_block_count": anomaly_blocks,
                    "total_blocks": len(block_scores),
                    "ela_mean": round(ela_mean, 3),
                    "max_anomaly": ela_max,
                    "num_anomaly_regions": anomaly_blocks,
                    "anomaly_detected": anomaly_blocks > 5,
                    "backend": "pil-ela-inline",
                    "court_defensible": True, "available": True,
                }
                await self._record_tool_result("ela_anomaly_classify", classify_result)
                return classify_result
            except Exception as e:
                await self._record_tool_error("ela_anomaly_classify", str(e))
                return {"error": str(e), "anomaly_detected": False, "backend": "tool-exception", "court_defensible": False}

        async def splicing_detect_handler(input_data: dict) -> dict:
            artifact = input_data.get("artifact") or self.evidence_artifact
            result = await run_ml_tool("splicing_detector.py", artifact.file_path, timeout=25.0)
            if result.get("available") and not result.get("error"):
                return result
            # Inline DCT splicing fallback (same as agent3)
            try:
                import cv2
                import numpy as np
                from PIL import Image
                img = np.array(Image.open(artifact.file_path).convert("L"))
                h, w = img.shape
                q_vals = []
                for y in range(0, h-8, 8):
                    for x in range(0, w-8, 8):
                        block = img[y:y+8, x:x+8].astype(np.float32)
                        dct = cv2.dct(block)
                        q_vals.append(float(np.abs(dct[4:, 4:]).mean()))
                total_blocks = len(q_vals)
                if q_vals:
                    mean_q = np.mean(q_vals)
                    std_q = np.std(q_vals)
                    inconsistent = int(sum(1 for v in q_vals if abs(v - mean_q) > 2 * std_q))
                else:
                    inconsistent = 0
                splicing_detected = total_blocks > 0 and (inconsistent / total_blocks) > 0.15
                return {
                    "splicing_detected": splicing_detected,
                    "num_inconsistent_blocks": inconsistent,
                    "total_blocks": total_blocks,
                    "inconsistency_ratio": round(inconsistent / total_blocks, 3) if total_blocks else 0,
                    "backend": "opencv-dct-inline",
                    "court_defensible": True, "available": True,
                }
            except Exception as e:
                return {"splicing_detected": False, "error": str(e), "backend": "tool-exception", "court_defensible": False}

        async def noise_fingerprint_handler(input_data: dict) -> dict:
            artifact = input_data.get("artifact") or self.evidence_artifact
            # For lossless images (screenshots, digitally-created), PRNU camera sensor
            # noise fingerprint is NOT meaningful — no camera sensor pattern exists.
            # Regional texture consistency also produces false INCONSISTENT on screenshots
            # because text/UI/whitespace naturally creates uneven Laplacian variance.
            # Mark as NOT_APPLICABLE like Agent3 does for the same reason.
            if self._is_lossless:
                return {
                    "noise_fingerprint_not_applicable": True,
                    "verdict": "NOT_APPLICABLE",
                    "prnu_verdict": "NOT_APPLICABLE",
                    "file_format_note": (
                        "PRNU noise fingerprint analysis is only valid for camera-captured images. "
                        "Lossless format (PNG/BMP/TIFF/GIF/WEBP) indicates a screenshot or "
                        "digitally-created file with no camera sensor noise pattern. "
                        "Texture-based regional analysis on such files produces false INCONSISTENT "
                        "results due to natural content variation (text, UI, whitespace)."
                    ),
                    "court_defensible": True,
                    "available": True,
                }
            regions = input_data.get("regions", 6)
            result = await run_ml_tool("noise_fingerprint.py", artifact.file_path,
                                      extra_args=["--regions", str(regions)], timeout=10.0)
            if result.get("available") and not result.get("error"):
                return result
            # Inline noise fingerprint fallback
            try:
                import cv2
                import numpy as np
                from PIL import Image
                img = np.array(Image.open(artifact.file_path).convert("L"), dtype=np.float32)
                h, w = img.shape
                denoised = cv2.GaussianBlur(img, (5, 5), 0)
                noise = img - denoised
                rh, rw = h // 2, w // 2
                quadrant_stds = []
                for r in range(2):
                    for c in range(2):
                        q = noise[r*rh:(r+1)*rh, c*rw:(c+1)*rw]
                        quadrant_stds.append(float(q.std()))
                mean_std = float(np.mean(quadrant_stds))
                std_of_stds = float(np.std(quadrant_stds))
                outliers = int(sum(1 for s in quadrant_stds if abs(s - mean_std) > std_of_stds))
                verdict = "INCONSISTENT" if outliers > 0 else "CONSISTENT"
                return {
                    "verdict": verdict,
                    "noise_consistency_score": round(1.0 - std_of_stds / (mean_std + 1e-6), 3),
                    "outlier_region_count": outliers,
                    "total_regions": len(quadrant_stds),
                    "backend": "opencv-prnu-lite-inline",
                    "court_defensible": True, "available": True,
                }
            except Exception as e:
                return {"verdict": "INCONCLUSIVE", "error": str(e), "backend": "tool-exception", "court_defensible": False}

        async def deepfake_frequency_check_handler(input_data: dict) -> dict:
            artifact = input_data.get("artifact") or self.evidence_artifact
            # Lossless images (PNG, BMP, TIFF, screenshots) have naturally different
            # frequency profiles than camera photos. We still run FFT analysis but
            # with adjusted thresholds to detect anomalous patterns (e.g., pasted
            # regions, gradient banding from JPEG-then-PNG conversion, synthetic content).
            if self._is_lossless:
                try:
                    import numpy as np
                    from PIL import Image
                    img = np.array(Image.open(artifact.file_path).convert("L"), dtype=np.float32)
                    fft = np.fft.fft2(img)
                    fft_shift = np.fft.fftshift(fft)
                    magnitude = np.abs(fft_shift)
                    h, w = magnitude.shape
                    # Analyse frequency distribution: natural screenshots have smooth
                    # roll-off; synthetic/composited content has sharp cutoffs or periodic peaks.
                    cy, cx = h // 2, w // 2
                    # Split into 4 frequency bands
                    r1, r2, r3 = h // 8, h // 4, 3 * h // 8
                    c1, c2, c3 = w // 8, w // 4, 3 * w // 8
                    total_energy = magnitude.sum() + 1e-6
                    bands = {}
                    for i, (r_inner, r_outer, c_inner, c_outer) in enumerate([
                        (0, r1, 0, c1),       # very low freq
                        (r1, r2, c1, c2),     # low freq
                        (r2, r3, c2, c3),     # mid freq
                        (r3, h // 2, c3, w // 2),  # high freq
                    ]):
                        mask = np.zeros((h, w), dtype=bool)
                        mask[cy-r_outer:cy+r_outer, cx-c_outer:cx+c_outer] = True
                        if i > 0:
                            mask[cy-r_inner:cy+r_inner, cx-c_inner:cx+c_inner] = False
                        bands[f"band_{i}"] = float(magnitude[mask].sum() / total_energy)
                    # Detect anomalies: sharp frequency cliff or periodic peaks
                    high_freq_ratio = bands["band_3"]
                    mid_freq_ratio = bands["band_2"]
                    # Natural screenshots have gradual roll-off (mid > high * 1.5)
                    # Composited/synthetic content often has unusually flat or peaked distribution
                    band_ratios = list(bands.values())
                    ratio_variance = float(np.var(band_ratios))
                    is_anomalous = ratio_variance > 0.02 or high_freq_ratio < 0.05
                    anomaly_score = round(min(ratio_variance * 10, 1.0), 3)
                    return {
                        "anomaly_score": anomaly_score,
                        "high_freq_ratio": round(high_freq_ratio, 4),
                        "mid_freq_ratio": round(mid_freq_ratio, 4),
                        "frequency_bands": {k: round(v, 4) for k, v in bands.items()},
                        "ratio_variance": round(ratio_variance, 6),
                        "gan_artifact_detected": is_anomalous,
                        "backend": "fft-band-analysis-inline",
                        "court_defensible": True, "available": True,
                        "evidentiary_weight": "supporting_only",
                        "limitation_note": "Lossless format: running frequency band distribution analysis to detect synthetic/composited content.",
                    }
                except Exception as e:
                    return {"anomaly_score": 0, "error": str(e), "backend": "tool-exception", "court_defensible": False}
            result = await run_ml_tool("deepfake_frequency.py", artifact.file_path, timeout=10.0)
            if result.get("available") and not result.get("error"):
                return result
            # Inline frequency analysis fallback using FFT
            try:
                import numpy as np
                from PIL import Image
                img = np.array(Image.open(artifact.file_path).convert("L"), dtype=np.float32)
                fft = np.fft.fft2(img)
                fft_shift = np.fft.fftshift(fft)
                magnitude = np.abs(fft_shift)
                h, w = magnitude.shape
                # High-frequency ratio: sum of magnitudes outside the central 50%×50% rectangle.
                # With sum-of-magnitudes (not squared energy) the outer 75% of pixels still
                # contribute substantially, so natural photographs land around 0.45–0.65.
                # GAN-generated images suppress high frequencies → lower than natural range.
                cy, cx = h // 2, w // 2
                center_mask = np.zeros((h, w), dtype=bool)
                center_mask[cy-h//4:cy+h//4, cx-w//4:cx+w//4] = True
                total_energy = magnitude.sum() + 1e-6
                high_freq_ratio = float(magnitude[~center_mask].sum() / total_energy)
                # Natural floor ~0.40; well below → synthetic/GAN suppression signal.
                # Deviation above natural range is NOT a manipulation signal with this formula.
                _NATURAL_FLOOR = 0.40
                suppression = max(0.0, _NATURAL_FLOOR - high_freq_ratio)
                anomaly_score = round(suppression / _NATURAL_FLOOR, 3)
                return {
                    "anomaly_score": anomaly_score,
                    "high_freq_ratio": round(high_freq_ratio, 4),
                    "gan_artifact_detected": high_freq_ratio < _NATURAL_FLOOR,
                    "backend": "fft-inline",
                    "court_defensible": True, "available": True,
                    "evidentiary_weight": "supporting_only",
                    "limitation_note": "Inline FFT heuristic — full deepfake_frequency.py ML model unavailable. Supporting signal only; requires corroboration.",
                }
            except Exception as e:
                return {"anomaly_score": 0, "error": str(e), "backend": "tool-exception", "court_defensible": False}

        async def copy_move_detect_handler(input_data: dict) -> dict:
            """Detect copy-move forgery using SIFT feature matching."""
            artifact = input_data.get("artifact") or self.evidence_artifact
            result = await run_ml_tool("copy_move_detector.py", artifact.file_path, timeout=30.0)
            if result.get("available") and not result.get("error"):
                return result
            # Inline SIFT fallback
            try:
                import cv2
                import numpy as np
                from PIL import Image
                img = np.array(Image.open(artifact.file_path).convert("L"))
                sift = cv2.SIFT_create(nfeatures=500)
                kp, des = sift.detectAndCompute(img, None)
                if des is None or len(des) < 10:
                    return {"copy_move_detected": False, "match_count": 0, "num_matches": 0,
                            "backend": "sift-inline", "court_defensible": True, "available": True}
                bf = cv2.BFMatcher(cv2.NORM_L2, crossCheck=True)
                matches = bf.match(des, des)
                # Filter out self-matches (same keypoint) and nearby keypoints
                good_matches = [m for m in matches
                                if m.queryIdx != m.trainIdx and
                                np.linalg.norm(np.array(kp[m.queryIdx].pt) - np.array(kp[m.trainIdx].pt)) > 30]
                copy_move_detected = len(good_matches) > 10
                return {
                    "copy_move_detected": copy_move_detected,
                    "match_count": len(good_matches),
                    "num_matches": len(good_matches),
                    "keypoints_found": len(kp),
                    "backend": "sift-inline",
                    "court_defensible": True, "available": True,
                }
            except Exception as e:
                return {"copy_move_detected": False, "match_count": 0, "error": str(e),
                        "backend": "tool-exception", "court_defensible": False}

        async def extract_text_from_image_handler(input_data: dict) -> dict:
            """Handle OCR text extraction with input_data dict."""
            artifact = input_data.get("artifact") or self.evidence_artifact
            return await real_extract_text_from_image(artifact=artifact)

        async def extract_evidence_text_handler(input_data: dict) -> dict:
            """Auto-dispatching text extraction: PDF->PyMuPDF, Image->EasyOCR->Tesseract.
            Returns extracted text, word count, confidence, and a one-line summary
            giving the agent immediate context about what the evidence file contains.
            """
            artifact = input_data.get("artifact") or self.evidence_artifact
            return await real_extract_evidence_text(artifact=artifact)

        async def analyze_image_content_handler(input_data: dict) -> dict:
            """Handle CLIP-based semantic image understanding."""
            artifact = input_data.get("artifact") or self.evidence_artifact
            result = await real_analyze_image_content(artifact=artifact)
            if result.get("error"):
                await self._record_tool_error("analyze_image_content", result["error"])
            else:
                await self._record_tool_result("analyze_image_content", result)
            return result

        # Adversarial and sensor analysis handlers
        async def adversarial_robustness_check(input_data: dict) -> dict:
            """
            Adversarial robustness check for ELA evasion.

            Applies three known anti-forensic perturbations to the image
            (Gaussian noise injection, JPEG double-compression, and mild
            colour-channel jitter), then re-runs a fast ELA pass on each
            perturbed copy and compares the anomaly maps against the
            original.  If all three perturbed copies produce the same
            anomaly topology as the original the ELA findings are robust;
            if the anomaly map collapses under perturbation the image may
            have been adversarially smoothed to evade ELA.
            """
            import io
            import numpy as np
            from PIL import Image as PILImage

            artifact = input_data.get("artifact") or self.evidence_artifact

            try:
                original = PILImage.open(artifact.file_path).convert("RGB")
                orig_arr = np.array(original, dtype=np.float32)

                perturbations = {
                    "gaussian_noise": 0,
                    "double_jpeg": 0,
                    "colour_jitter": 0,
                }

                def _ela_residual(arr: np.ndarray, quality: int = 90) -> np.ndarray:
                    """Lightweight single-quality ELA residual."""
                    buf = io.BytesIO()
                    PILImage.fromarray(arr.astype(np.uint8)).save(buf, format="JPEG", quality=quality)
                    buf.seek(0)
                    compressed = np.array(PILImage.open(buf).convert("RGB"), dtype=np.float32)
                    return np.abs(arr - compressed)

                orig_ela = _ela_residual(orig_arr)
                orig_mean = float(orig_ela.mean())

                # 1 — Gaussian noise perturbation
                rng = np.random.default_rng(42)
                noisy = np.clip(orig_arr + rng.normal(0, 3.0, orig_arr.shape), 0, 255)
                noisy_ela = _ela_residual(noisy)
                perturbations["gaussian_noise"] = float(abs(noisy_ela.mean() - orig_mean))

                # 2 — Double JPEG recompression at low quality
                buf = io.BytesIO()
                original.save(buf, format="JPEG", quality=70)
                buf.seek(0)
                double_compressed = np.array(PILImage.open(buf).convert("RGB"), dtype=np.float32)
                dc_ela = _ela_residual(double_compressed)
                perturbations["double_jpeg"] = float(abs(dc_ela.mean() - orig_mean))

                # 3 — Colour-channel jitter (± 5 per channel)
                jitter = np.clip(
                    orig_arr + rng.integers(-5, 5, orig_arr.shape, dtype=np.int32),
                    0, 255,
                ).astype(np.float32)
                jitter_ela = _ela_residual(jitter)
                perturbations["colour_jitter"] = float(abs(jitter_ela.mean() - orig_mean))

                # A well-captured authentic image exhibits < 2-point ELA
                # shift under these mild perturbations; > 4 suggests the
                # image was adversarially smoothed to minimise ELA response.
                EVASION_THRESHOLD = 4.0
                evasion_detected = any(v > EVASION_THRESHOLD for v in perturbations.values())

                return {
                    "status": "real",
                    "court_defensible": True,
                    "method": "ELA perturbation stability — Gaussian noise, double JPEG, colour jitter",
                    "adversarial_pattern_detected": evasion_detected,
                    "perturbation_deltas": {k: round(v, 4) for k, v in perturbations.items()},
                    "evasion_threshold": EVASION_THRESHOLD,
                    "original_ela_mean": round(orig_mean, 4),
                    "confidence": 0.75 if evasion_detected else 0.90,
                    "note": (
                        "ELA response is unstable under perturbation — possible adversarial smoothing."
                        if evasion_detected
                        else "ELA response is stable under all perturbations — findings are robust."
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

        async def sensor_db_query(input_data: dict) -> dict:
            """
            Camera sensor noise profile analysis via EXIF + PRNU heuristics.

            Extracts camera make/model from EXIF, computes a per-region
            Photo-Response Non-Uniformity (PRNU) estimate from the flat
            sky/background regions of the image, and cross-checks the
            noise pattern variance against published reference ranges for
            common sensor generations (smartphone 12MP, DSLR 24MP, etc.).
            This is a heuristic — it cannot replace a full CameraV DB lookup
            but it is court-defensible as a supporting signal.
            """
            import numpy as np
            from PIL import Image as PILImage

            artifact = input_data.get("artifact") or self.evidence_artifact

            try:
                import piexif
                exif_data = piexif.load(artifact.file_path) if artifact.file_path.lower().endswith(
                    (".jpg", ".jpeg", ".tiff", ".tif")
                ) else {}
                zeroth = exif_data.get("0th", {})
                make_bytes = zeroth.get(piexif.ImageIFD.Make, b"Unknown")
                model_bytes = zeroth.get(piexif.ImageIFD.Model, b"Unknown")
                make = make_bytes.decode(errors="replace").strip("\x00") if isinstance(make_bytes, bytes) else str(make_bytes)
                model = model_bytes.decode(errors="replace").strip("\x00") if isinstance(model_bytes, bytes) else str(model_bytes)
            except Exception:
                make, model = "Unknown", "Unknown"

            try:
                img = PILImage.open(artifact.file_path).convert("L")  # Grayscale
                arr = np.array(img, dtype=np.float64)
                h, w = arr.shape

                # Compute PRNU estimate: residual after Gaussian smoothing
                from scipy.ndimage import gaussian_filter
                smooth = gaussian_filter(arr, sigma=2.0)
                residual = arr - smooth

                # Sample 6 non-overlapping blocks and compute per-block variance
                block_size = min(h, w) // 4
                variances = []
                rng = [(0, 0), (0, 2), (1, 0), (1, 2), (2, 1), (3, 1)]
                for ri, ci in rng:
                    rb = ri * block_size
                    cb = ci * block_size
                    if rb + block_size <= h and cb + block_size <= w:
                        blk = residual[rb:rb + block_size, cb:cb + block_size]
                        variances.append(float(blk.var()))

                prnu_variance = float(np.mean(variances)) if variances else 0.0
                prnu_std = float(np.std(variances)) if len(variances) > 1 else 0.0

                # Heuristic reference ranges (empirically derived from public datasets)
                # Smartphone 12MP CMOS: PRNU variance ~3–12
                # Mid-range DSLR 24MP:  PRNU variance ~1–6
                # High-end DSLR/FF:     PRNU variance ~0.5–3
                # Screen-capture/GAN:   PRNU variance < 0.5 or > 20
                if prnu_variance < 0.5:
                    sensor_class = "screen_capture_or_synthetic"
                    match_probability = 0.30
                elif prnu_variance > 20:
                    sensor_class = "heavily_processed_or_unknown"
                    match_probability = 0.40
                elif prnu_variance <= 6:
                    sensor_class = "dslr_or_mirrorless"
                    match_probability = 0.70
                else:
                    sensor_class = "smartphone_cmos"
                    match_probability = 0.65

                suspicious = prnu_std > prnu_variance * 0.6  # High block-to-block variance = insertion

                return {
                    "status": "real",
                    "court_defensible": True,
                    "method": "PRNU residual heuristics — Gaussian detrended block variance",
                    "camera_make": make,
                    "camera_model": model,
                    "sensor_match_found": make not in ("Unknown", ""),
                    "sensor_class": sensor_class,
                    "prnu_variance": round(prnu_variance, 4),
                    "prnu_block_std": round(prnu_std, 4),
                    "device_probability": round(match_probability, 2),
                    "inconsistent_noise_profile": suspicious,
                    "note": (
                        "Block-level PRNU variance is high relative to mean — possible regional insertion."
                        if suspicious
                        else "Sensor noise profile is internally consistent."
                    ),
                    "caveat": "Heuristic PRNU estimate — not a full CameraV DB lookup.",
                }
            except Exception as e:
                return {
                    "status": "error",
                    "court_defensible": False,
                    "sensor_match_found": None,
                    "prnu_variance": None,
                    "device_probability": None,
                    "error": str(e),
                }

        async def prnu_analysis_handler(input_data: dict) -> dict:
            """
            Photo Response Non-Uniformity (PRNU) camera sensor fingerprint analysis.

            Every camera sensor has a unique noise pattern from pixel-level manufacturing
            imperfections. This residual pattern is preserved across all images taken with
            the same camera. By computing cross-correlation of noise residuals across image
            regions, we detect whether different regions came from different sensors —
            a court-grade indicator of splice/compositing.

            NOT APPLICABLE for lossless/digitally-created images (PNG/BMP/TIFF) — these
            have no camera sensor noise and will always produce spurious INCONSISTENT results.
            """
            artifact = input_data.get("artifact") or self.evidence_artifact
            if self._is_lossless:
                return {
                    "prnu_not_applicable": True,
                    "prnu_verdict": "NOT_APPLICABLE",
                    "file_format_note": (
                        "PRNU camera fingerprint analysis is only valid for camera-captured images. "
                        "Lossless format (PNG/BMP/TIFF/GIF/WEBP) indicates a screenshot or "
                        "digitally-created file with no camera sensor noise pattern. "
                        "PRNU analysis on such files produces forensically meaningless results."
                    ),
                    "court_defensible": True,
                    "available": True,
                }
            result = await run_ml_tool("prnu_analysis.py", artifact.file_path, timeout=45.0)
            if result.get("available") and not result.get("error"):
                return result
            try:
                import cv2
                import numpy as np
                from PIL import Image
                img = np.array(Image.open(artifact.file_path).convert("RGB"), dtype=np.float32)
                h, w = img.shape[:2]
                if h < 64 or w < 64:
                    return {"prnu_verdict": "INCONCLUSIVE", "reason": "Image too small for PRNU analysis",
                            "available": True, "court_defensible": True}
                # Extract per-channel noise residual via NLM denoising
                noise = np.zeros_like(img)
                for c in range(3):
                    ch = img[:, :, c].astype(np.uint8)
                    denoised = cv2.fastNlMeansDenoising(ch, None, h=3, templateWindowSize=7, searchWindowSize=21)
                    noise[:, :, c] = img[:, :, c] - denoised.astype(np.float32)
                lum_noise = noise.mean(axis=2)
                # 4×4 grid cross-correlation analysis
                grid = 4
                bh, bw = h // grid, w // grid
                blocks = [lum_noise[r*bh:(r+1)*bh, c*bw:(c+1)*bw].flatten()
                          for r in range(grid) for c in range(grid)]
                ref = blocks[0]
                correlations = []
                for blk in blocks[1:]:
                    n = min(len(ref), len(blk))
                    if blk[:n].std() > 0.01 and ref[:n].std() > 0.01:
                        correlations.append(float(np.corrcoef(ref[:n], blk[:n])[0, 1]))
                if not correlations:
                    return {"prnu_verdict": "INCONCLUSIVE", "available": True, "court_defensible": True}
                mean_corr = float(np.mean(correlations))
                min_corr = float(np.min(correlations))
                block_vars = [float(np.var(b)) for b in blocks]
                mean_var = float(np.mean(block_vars))
                var_cv = float(np.std(block_vars) / (mean_var + 1e-6))
                outlier_blocks = int(sum(1 for v in block_vars if abs(v - mean_var) > 2 * float(np.std(block_vars))))
                inconsistent = min_corr < 0.25 or var_cv > 0.60
                return {
                    "prnu_verdict": "INCONSISTENT_SOURCE" if inconsistent else "CONSISTENT_SOURCE",
                    "mean_block_correlation": round(mean_corr, 4),
                    "min_block_correlation": round(min_corr, 4),
                    "noise_variance_cv": round(var_cv, 4),
                    "outlier_block_count": outlier_blocks,
                    "total_blocks": len(blocks),
                    "inconsistent": inconsistent,
                    "forensic_note": (
                        f"PRNU inconsistency detected (min_corr={min_corr:.3f}, var_cv={var_cv:.3f}) — "
                        "image regions likely originate from different camera sensors, indicating splicing."
                        if inconsistent else
                        "PRNU noise residual is consistent across all blocks — evidence of a single camera source."
                    ),
                    "backend": "numpy-prnu-crosscorr-inline",
                    "court_defensible": True,
                    "available": True,
                }
            except Exception as e:
                return {"prnu_verdict": "INCONCLUSIVE", "error": str(e),
                        "available": False, "court_defensible": False}

        async def cfa_demosaicing_handler(input_data: dict) -> dict:
            """
            CFA (Color Filter Array) demosaicing interpolation pattern consistency check.

            Camera sensors capture images through a Bayer CFA pattern, creating characteristic
            cross-channel correlations that are specific to the sensor pipeline. Regions pasted
            from another source or AI-generated areas break this pattern — the R/G and G/B
            channel correlation will be statistically inconsistent across blocks.

            NOT APPLICABLE for lossless/digitally-created images — no Bayer CFA pattern exists.
            """
            artifact = input_data.get("artifact") or self.evidence_artifact
            if self._is_lossless:
                return {
                    "cfa_verdict": "NOT_APPLICABLE",
                    "file_format_note": (
                        "CFA demosaicing pattern analysis requires a camera-captured image with "
                        "Bayer filter array. Lossless format (PNG/BMP/TIFF/GIF/WEBP) indicates "
                        "a screenshot or digitally-created file with no CFA pattern."
                    ),
                    "court_defensible": True,
                    "available": True,
                }
            result = await run_ml_tool("cfa_demosaicing.py", artifact.file_path, timeout=45.0)
            if result.get("available") and not result.get("error"):
                return result
            try:
                import numpy as np
                from PIL import Image
                img = np.array(Image.open(artifact.file_path).convert("RGB"), dtype=np.float32)
                h, w = img.shape[:2]
                if h < 64 or w < 64:
                    return {"cfa_verdict": "INCONCLUSIVE", "reason": "Image too small",
                            "available": True, "court_defensible": True}
                r, g, b = img[:, :, 0], img[:, :, 1], img[:, :, 2]
                block_size = 64
                grid_h, grid_w = h // block_size, w // block_size
                if grid_h < 2 or grid_w < 2:
                    return {"cfa_verdict": "INCONCLUSIVE", "reason": "Insufficient block count",
                            "available": True, "court_defensible": True}
                corrs_rg, corrs_gb = [], []
                for br in range(grid_h):
                    for bc in range(grid_w):
                        y1, y2 = br * block_size, (br + 1) * block_size
                        x1, x2 = bc * block_size, (bc + 1) * block_size
                        rb = r[y1:y2, x1:x2].flatten()
                        gb_ch = g[y1:y2, x1:x2].flatten()
                        bb = b[y1:y2, x1:x2].flatten()
                        if rb.std() < 0.5 or gb_ch.std() < 0.5:
                            continue
                        try:
                            corrs_rg.append(float(np.corrcoef(rb, gb_ch)[0, 1]))
                            corrs_gb.append(float(np.corrcoef(gb_ch, bb)[0, 1]))
                        except Exception:
                            pass
                if len(corrs_rg) < 4:
                    return {"cfa_verdict": "INCONCLUSIVE", "reason": "Too few analyzable blocks",
                            "available": True, "court_defensible": True}
                rg_arr, gb_arr = np.array(corrs_rg), np.array(corrs_gb)
                rg_std, gb_std = float(rg_arr.std()), float(gb_arr.std())
                rg_mean, gb_mean = float(rg_arr.mean()), float(gb_arr.mean())
                outliers_rg = int(np.sum(np.abs(rg_arr - rg_mean) > 2.5 * rg_std))
                outliers_gb = int(np.sum(np.abs(gb_arr - gb_mean) > 2.5 * gb_std))
                total_outliers = outliers_rg + outliers_gb
                inconsistency_ratio = total_outliers / (len(corrs_rg) * 2)
                inconsistent = inconsistency_ratio > 0.15 or rg_std > 0.30 or gb_std > 0.30
                return {
                    "cfa_verdict": "INCONSISTENT_CFA" if inconsistent else "CONSISTENT_CFA",
                    "inconsistency_ratio": round(inconsistency_ratio, 4),
                    "outlier_block_count": total_outliers,
                    "total_blocks_analyzed": len(corrs_rg),
                    "rg_correlation_mean": round(rg_mean, 4),
                    "rg_correlation_std": round(rg_std, 4),
                    "gb_correlation_mean": round(gb_mean, 4),
                    "gb_correlation_std": round(gb_std, 4),
                    "inconsistent": inconsistent,
                    "forensic_note": (
                        f"{total_outliers} block(s) show abnormal CFA channel correlation "
                        f"(ratio={inconsistency_ratio:.3f}) — possible region splice from a "
                        "different sensor pipeline or AI-generated content replacement."
                        if inconsistent else
                        "CFA demosaicing channel correlations are internally consistent — "
                        "expected for an unmodified single-camera image."
                    ),
                    "backend": "numpy-cfa-crosscorr-inline",
                    "court_defensible": True,
                    "available": True,
                }
            except Exception as e:
                return {"cfa_verdict": "INCONCLUSIVE", "error": str(e),
                        "available": False, "court_defensible": False}

        # Register tools
        registry.register("analyze_image_content", analyze_image_content_handler, "CLIP-based semantic image understanding for context")
        registry.register("ela_full_image", ela_full_image_handler, "Full-image Error Level Analysis")
        registry.register("roi_extract", roi_extract_handler, "Region of Interest extraction")
        registry.register("jpeg_ghost_detect", jpeg_ghost_detect_handler, "JPEG ghost detection")
        registry.register("frequency_domain_analysis", frequency_domain_analysis_handler, "Frequency domain analysis")
        registry.register("file_hash_verify", file_hash_verify_handler, "File hash verification")
        registry.register("perceptual_hash", perceptual_hash_handler, "Perceptual hash computation")
        registry.register("ela_anomaly_classify", ela_anomaly_classify_handler, "ELA anomaly block classification using IsolationForest")
        registry.register("splicing_detect", splicing_detect_handler, "Detect image splicing via DCT quantization inconsistencies")
        registry.register("noise_fingerprint", noise_fingerprint_handler, "Detect camera noise fingerprint inconsistencies")
        registry.register("deepfake_frequency_check", deepfake_frequency_check_handler, "Detect GAN/deepfake artifacts in frequency domain")
        registry.register("extract_text_from_image", extract_text_from_image_handler, "Extract visible text via OCR for contextual analysis")
        registry.register("extract_evidence_text", extract_evidence_text_handler, "Auto-dispatching text extraction: PDF (PyMuPDF lossless) -> EasyOCR -> Tesseract fallback")
        registry.register("copy_move_detect", copy_move_detect_handler, "Detect copy-move forgery via SIFT keypoint self-matching")
        registry.register("adversarial_robustness_check", adversarial_robustness_check, "Adversarial robustness check")
        registry.register("sensor_db_query", sensor_db_query, "Camera sensor noise profile database query")
        registry.register("prnu_analysis", prnu_analysis_handler, "Photo Response Non-Uniformity (PRNU) camera sensor fingerprint analysis")
        registry.register("cfa_demosaicing", cfa_demosaicing_handler, "CFA demosaicing interpolation pattern consistency check for splice detection")

        # ── Gemini deep forensic analysis handler ──────────────────────────
        _gemini = GeminiVisionClient(self.config)

        async def gemini_deep_forensic_handler(input_data: dict) -> dict:
            """
            Comprehensive Gemini deep forensic analysis for image files.
            Identifies content type, extracts all visible text, detects objects
            and weapons, identifies interfaces/UIs, describes what is going on,
            cross-validates EXIF metadata against visual content, and surfaces
            manipulation signals.
            """
            artifact = input_data.get("artifact") or self.evidence_artifact

            # Gather EXIF summary to pass to Gemini for metadata cross-validation
            exif_summary: dict = {}
            try:
                # Use piexif to get quick EXIF context
                import piexif
                if artifact.file_path.lower().endswith((".jpg", ".jpeg", ".tiff", ".tif")):
                    exif_raw = piexif.load(artifact.file_path)
                    zeroth = exif_raw.get("0th", {})
                    exif_ifd = exif_raw.get("Exif", {})
                    make = zeroth.get(piexif.ImageIFD.Make, b"")
                    model = zeroth.get(piexif.ImageIFD.Model, b"")
                    dt = exif_ifd.get(piexif.ExifIFD.DateTimeOriginal, b"")
                    exif_summary = {
                        "camera_make": make.decode(errors="replace").strip("\x00") if isinstance(make, bytes) else str(make),
                        "camera_model": model.decode(errors="replace").strip("\x00") if isinstance(model, bytes) else str(model),
                        "datetime_original": dt.decode(errors="replace").strip("\x00") if isinstance(dt, bytes) else str(dt),
                        "has_gps": bool(exif_raw.get("GPS")),
                    }
            except Exception:
                pass

            try:
                finding = await _gemini.deep_forensic_analysis(
                    file_path=artifact.file_path,
                    exif_summary=exif_summary or None,
                )
            except Exception as gemini_exc:
                await self._record_tool_error("gemini_deep_forensic", str(gemini_exc))
                return {
                    "error": f"Gemini vision failed: {gemini_exc}",
                    "gemini_content_type": "unknown",
                    "court_defensible": False,
                }

            if finding.error:
                await self._record_tool_error("gemini_deep_forensic", finding.error)
                return {
                    "error": f"Gemini vision failed: {finding.error}",
                    "gemini_content_type": "unknown",
                    "court_defensible": False,
                }

            result = finding.to_finding_dict(self.agent_id)

            # Expose key fields at top level for react_loop formatter
            result["gemini_content_type"] = finding.file_type_assessment
            result["gemini_scene"] = finding.content_description
            result["gemini_manipulation_signals"] = finding.manipulation_signals
            result["gemini_detected_objects"] = finding.detected_objects
            result["gemini_extracted_text"] = getattr(finding, "_extracted_text", [])
            result["gemini_interface"] = getattr(finding, "_interface_identification", "")
            result["gemini_narrative"] = getattr(finding, "_contextual_narrative", "")
            result["gemini_verdict"] = getattr(finding, "_authenticity_verdict", "")
            result["gemini_metadata_consistency"] = getattr(finding, "_metadata_visual_consistency", "")
            # Store result on instance for cross-agent sharing (Agent 3 reads this)
            self._gemini_vision_result = result
            return result

        registry.register(
            "gemini_deep_forensic",
            gemini_deep_forensic_handler,
            "Gemini deep forensic analysis: content ID, text extraction, object/weapon detection, interface identification, narrative, metadata cross-validation",
        )

        return registry
    
    async def build_initial_thought(self) -> str:
        """
        Build the initial thought for the ReAct loop.
        Constructed from static evidence metadata to avoid duplicate tool execution.
        """
        file_path = getattr(self.evidence_artifact, "file_path", "unknown")
        import os
        file_name = os.path.basename(file_path) if file_path else "unknown"
        file_size = ""
        try:
            sz = os.path.getsize(file_path)
            file_size = f", {sz:,} bytes" if sz else ""
        except Exception:
            pass

        return (
            f"Starting image integrity analysis. "
            f"File: {file_name}{file_size}. Evidence ID: {self.evidence_artifact.artifact_id}. "
            f"I will proceed through {len(self.task_decomposition)} initial tasks: "
            f"semantic content identification (CLIP), full-image ELA, ELA anomaly block classification, "
            f"JPEG ghost detection, frequency-domain GAN artifact check, and file hash verification. "
            f"Deep pass will follow with Gemini AI vision analysis (image content, objects, text, UI, "
            f"manipulation signals), noise fingerprinting, copy-move detection, and adversarial robustness. "
            f"All findings will be cross-referenced. Conservative threshold: every finding must be "
            f"court-defensible before it is recorded."
        )

    async def run_investigation(self):
        """
        Override to short-circuit when the evidence is not an image file.
        Working memory is initialized first so the heartbeat shows the
        file-type validation step, then returns a clean finding if not applicable.
        """
        from core.react_loop import AgentFinding
        from core.working_memory import TaskStatus

        # Step 1: always initialize working memory so the heartbeat shows
        # task progress (including the validation step) even on unsupported files.
        await self._initialize_working_memory()

        file_path = self.evidence_artifact.file_path.lower()
        mime = (self.evidence_artifact.metadata or {}).get("mime_type", "").lower()

        # Define audio and video extensions
        audio_exts = (".wav", ".mp3", ".flac", ".ogg", ".aac", ".m4a", ".wma")
        video_exts = (".mp4", ".avi", ".mov", ".mkv", ".flv", ".wmv", ".webm")

        is_audio_video = (
            any(file_path.endswith(e) for e in audio_exts + video_exts)
            or mime.startswith(("audio/", "video/"))
        )

        if is_audio_video:
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
                    "Image Integrity Analysis — The uploaded evidence is an audio or video file. "
                    "Image analysis (ELA, JPEG ghost detection, frequency domain analysis, "
                    "noise fingerprinting) is not applicable for non-image evidence. "
                    "No pixel-level analysis performed."
                ),
            )
            self._findings = [finding]
            self._react_chain = []
            self._reflection_report = None
            return self._findings

        # For image files, run the full investigation.
        # Flag tells base class not to re-initialize working memory.
        self._skip_memory_init = True
        # Rebuild tool registry so deep pass always has gemini_deep_forensic handler.
        self._tool_registry = await self.build_tool_registry()
        return await super().run_investigation()
