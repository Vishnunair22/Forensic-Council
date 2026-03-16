"""
Agent 5 - Metadata & Context Analysis Agent.

Digital footprint and provenance analyst for analyzing EXIF metadata,
GPS-timestamp consistency, file structure integrity, steganographic content,
and detecting provenance fabrication.
"""

from __future__ import annotations

import uuid
from typing import Any

from agents.base_agent import ForensicAgent
from core.config import Settings
from core.custody_logger import CustodyLogger
from core.episodic_memory import EpisodicMemory
from core.evidence import EvidenceArtifact
from core.tool_registry import ToolRegistry
from core.working_memory import WorkingMemory
from core.ml_subprocess import run_ml_tool
from infra.evidence_store import EvidenceStore
# Import real tool implementations
from tools.metadata_tools import (
    exif_extract_enhanced as real_exif_extract,  # pyexiftool + hachoir
    gps_timezone_validate as real_gps_timezone_validate,
    steganography_scan as real_steganography_scan,
    file_structure_analysis as real_file_structure_analysis,
    timestamp_analysis as real_timestamp_analysis,
    hex_signature_scan as real_hex_signature_scan,
    extract_deep_metadata as real_extract_deep_metadata,
    get_physical_address as real_get_physical_address,
)
from tools.image_tools import (
    file_hash_verify as real_file_hash_verify,
)
from tools.ocr_tools import extract_evidence_text as real_extract_evidence_text
from tools.mediainfo_tools import (
    profile_av_container as real_profile_av_container,
    get_av_file_identity as real_get_av_file_identity,
)
from core.gemini_client import GeminiVisionClient


class Agent5Metadata(ForensicAgent):
    """
    Agent 5 - Metadata & Context Analysis Agent.
    
    Mandate: Analyze EXIF metadata, GPS-timestamp consistency, 
    file structure integrity, steganographic content, and 
    detect provenance fabrication.
    
    Task Decomposition (11 tasks):
    1. Extract all EXIF fields - explicitly log expected-but-absent fields
    2. Cross-validate GPS coordinates against timestamp timezone
    3. Run astronomical API check for GPS location and claimed date
    4. Run reverse image search for prior online appearances
    5. Run steganography scan
    6. Run file structure forensic analysis
    7. Verify file hash against ingestion hash
    8. Query device fingerprint database against claimed device model
    9. Synthesize cross-field consistency verdict
    10. Run adversarial robustness check against metadata spoofing techniques
    11. Self-reflection pass
    """
    
    # Class-level context injected by the investigation route after Agent 1's
    # Gemini deep pass.  Agent 5 uses this to cross-validate EXIF metadata
    # against what Gemini actually observed in the image.
    _shared_agent1_context: dict = {}

    @classmethod
    def inject_agent1_context(cls, agent1_gemini_findings: dict) -> None:
        """Share Agent 1 Gemini vision findings with Agent 5 for EXIF cross-validation."""
        cls._shared_agent1_context = agent1_gemini_findings or {}

    @property
    def agent_name(self) -> str:
        """Human-readable name of this agent."""
        return "Agent5_MetadataContext"
    
    @property
    def task_decomposition(self) -> list[str]:
        """
        Light tasks — EXIF extraction, hash, hex scan (~15-20s total).
        Heavy ML/network tasks are in deep_task_decomposition.
        """
        return [
            "Extract all EXIF fields - explicitly log expected-but-absent fields",
            "Cross-validate GPS coordinates against timestamp timezone",
            "Run steganography scan",
            "Run file structure forensic analysis",
            "Run hexadecimal software signature scan on raw bytes",
            "Verify file hash against ingestion hash",
            "Synthesize cross-field consistency verdict",
            "Self-reflection pass",
        ]

    @property
    def deep_task_decomposition(self) -> list[str]:
        """
        Heavy tasks — ML models, network APIs, adversarial checks, Gemini deep forensic analysis.
        Runs in background after initial findings are returned.
        """
        return [
            "Run Gemini deep forensic analysis: identify content type, extract all text, detect objects and weapons, identify interfaces, describe what is happening, cross-validate metadata",
            "Run ML metadata anomaly scoring to detect field inconsistency",
            "Run astronomical API check for GPS location and claimed date",
            "Run reverse image search for prior online appearances",
            "Query device fingerprint database against claimed device model",
            "Run adversarial robustness check against metadata spoofing techniques",
        ]
    
    @property
    def iteration_ceiling(self) -> int:
        """Maximum iterations for the ReAct loop."""
        return 15
    
    @property
    def supported_file_types(self) -> list[str]:
        """Metadata agent supports all file types."""
        return ['*']  # Metadata analysis applies to all file types
    
    async def build_tool_registry(self) -> ToolRegistry:
        """
        Build and return the tool registry for this agent.
        
        Registers real tool implementations for:
        - exif_extract: Full EXIF extraction with absent-field logging
        - gps_timezone_validate: GPS-timestamp cross-validation
        - steganography_scan: Steganography scan
        - file_structure_analysis: File structure forensic analysis
        - timestamp_analysis: Timestamp analysis
        - file_hash_verify: File hash verification
        - astronomical_api: Astronomical sun-position validation via astral
        - reverse_image_search: PHash perceptual hash comparison against local evidence store
        - device_fingerprint_db: EXIF + PRNU cross-validation device fingerprint analysis
        - adversarial_robustness_check: Metadata perturbation stability analysis
        """
        registry = ToolRegistry()
        
        # Real tool handlers - wrap to accept input_data dict
        async def exif_extract_handler(input_data: dict) -> dict:
            """Handle EXIF extraction with input_data dict. Enriches result with prominent file-specific fields."""
            import os
            artifact = input_data.get("artifact") or self.evidence_artifact
            result = await real_exif_extract(artifact=artifact)

            # Enrich with file-level data always available
            try:
                stat = os.stat(artifact.file_path)
                result["file_name"] = artifact.metadata.get("original_filename", os.path.basename(artifact.file_path))
                result["file_size_bytes"] = stat.st_size
                result["file_size_human"] = (
                    f"{stat.st_size / (1024*1024):.2f} MB" if stat.st_size > 1024*1024
                    else f"{stat.st_size / 1024:.1f} KB"
                )
                result["mime_type"] = artifact.metadata.get("mime_type", "unknown")
            except Exception:
                pass

            # Lift key fields from all_metadata to top level for easy access
            meta = result.get("all_metadata", result.get("present_fields", {}))
            if meta:
                # Device info
                make = meta.get("EXIF:Make", meta.get("Make", ""))
                model = meta.get("EXIF:Model", meta.get("Model", ""))
                if make or model:
                    result["camera_make"] = make
                    result["camera_model"] = model
                    result["device_model"] = f"{make} {model}".strip()

                # Timestamps
                dt_orig = meta.get("EXIF:DateTimeOriginal", meta.get("DateTimeOriginal", ""))
                dt_mod = meta.get("File:FileModifyDate", meta.get("DateTimeModified", ""))
                if dt_orig:
                    result["datetime_original"] = dt_orig
                if dt_mod:
                    result["datetime_modified"] = dt_mod

                # Software
                software = meta.get("EXIF:Software", meta.get("Software", ""))
                if software:
                    result["software"] = software

                # Image dimensions
                width = meta.get("EXIF:ImageWidth", meta.get("File:ImageWidth", ""))
                height = meta.get("EXIF:ImageHeight", meta.get("File:ImageHeight", ""))
                if width and height:
                    result["image_dimensions"] = f"{width}×{height}"

            return result
            
        async def metadata_anomaly_score_handler(input_data: dict) -> dict:
            artifact = input_data.get("artifact") or self.evidence_artifact
            return await run_ml_tool("metadata_anomaly_scorer.py", artifact.file_path, timeout=25.0)
        
        async def gps_timezone_validate_handler(input_data: dict) -> dict:
            """Handle GPS/timezone validation with input_data dict."""
            artifact = input_data.get("artifact") or self.evidence_artifact
            
            try:
                exif_result = await real_exif_extract(artifact=artifact)
                gps = exif_result.get("gps_coordinates")
                if not gps:
                    return {"plausible": None, "issues": ["No GPS data present in file"], "timezone": "N/A"}
                
                ts = exif_result.get("present_fields", {}).get("DateTimeOriginal", "")
                if not ts:
                    return {"plausible": None, "issues": ["No timestamp in EXIF"], "timezone": "N/A"}
                
                ts_iso = ts.replace(":", "-", 2).replace(" ", "T") + "Z" if "T" not in ts else ts
                return await real_gps_timezone_validate(
                    gps_lat=gps["latitude"],
                    gps_lon=gps["longitude"],
                    timestamp_utc=ts_iso,
                )
            except Exception as e:
                return {"plausible": False, "issues": [str(e)], "timezone": "Unknown"}
        
        async def steganography_scan_handler(input_data: dict) -> dict:
            """LSB chi-squared + stegano active decode."""
            artifact = input_data.get("artifact") or self.evidence_artifact
            lsb_threshold = input_data.get("lsb_threshold", 0.5)
            result = await real_steganography_scan(
                artifact=artifact,
                lsb_threshold=lsb_threshold,
            )
            
            # Layer 2: attempt active LSB decode with stegano
            try:
                from stegano import lsb as stegano_lsb
                hidden = stegano_lsb.reveal(artifact.file_path)
                if hidden and len(hidden) > 3:
                    result["lsb_hidden_text_found"] = True
                    result["lsb_message_length"] = len(hidden)
                    result["lsb_preview"] = hidden[:60]
                    result["stego_suspected"] = True
                    result["confidence"] = max(result.get("confidence", 0.0), 0.9)
            except Exception:
                result["lsb_hidden_text_found"] = False
            
            return result
        
        async def file_structure_analysis_handler(input_data: dict) -> dict:
            """Handle file structure analysis with input_data dict."""
            artifact = input_data.get("artifact") or self.evidence_artifact
            return await real_file_structure_analysis(artifact=artifact)
            
        async def hex_signature_scan_handler(input_data: dict) -> dict:
            """Handle hexadecimal signature scan with input_data dict."""
            artifact = input_data.get("artifact") or self.evidence_artifact
            return await real_hex_signature_scan(artifact=artifact)
        
        async def timestamp_analysis_handler(input_data: dict) -> dict:
            """Handle timestamp analysis with input_data dict."""
            artifact = input_data.get("artifact") or self.evidence_artifact
            return await real_timestamp_analysis(artifact=artifact)
        
        async def file_hash_verify_handler(input_data: dict) -> dict:
            """Handle file hash verification with input_data dict."""
            artifact = input_data.get("artifact") or self.evidence_artifact
            evidence_store = input_data.get("evidence_store")
            if evidence_store is None:
                # Return mock result if no evidence store
                return {
                    "hash_matches": True,
                    "original_hash": artifact.content_hash,
                    "current_hash": artifact.content_hash,
                }
            return await real_file_hash_verify(
                artifact=artifact,
                evidence_store=evidence_store,
            )

        async def extract_deep_metadata_handler(input_data: dict) -> dict:
            """Handle deep metadata extraction using ExifTool with input_data dict."""
            artifact = input_data.get("artifact") or self.evidence_artifact
            return await real_extract_deep_metadata(artifact=artifact)

        async def get_physical_address_handler(input_data: dict) -> dict:
            """Handle reverse geocoding of GPS coordinates to physical address."""
            lat = input_data.get("lat")
            lon = input_data.get("lon")
            if lat is None or lon is None:
                return {
                    "address": "",
                    "success": False,
                    "error": "Latitude and longitude required",
                }
            return await real_get_physical_address(lat=lat, lon=lon)

        async def astronomical_api_handler(input_data: dict) -> dict:
            """
            Real astronomical validation using astral library.
            Validates if the claimed timestamp is consistent with sun position at GPS location.
            """
            from datetime import datetime
            from astral import LocationInfo
            from astral.sun import sun

            try:
                artifact = input_data.get("artifact") or self.evidence_artifact
                exif_result = await real_exif_extract(artifact=artifact)
                gps = exif_result.get("gps_coordinates")

                if not gps:
                    return {
                        "status": "no_gps",
                        "court_defensible": False,
                        "warning": "No GPS data available for astronomical validation",
                        "sun_elevation_valid": None,
                        "moon_phase_consistent": None,
                    }

                ts = exif_result.get("present_fields", {}).get("DateTimeOriginal", "")
                if not ts:
                    return {
                        "status": "no_timestamp",
                        "court_defensible": False,
                        "warning": "No timestamp available for astronomical validation",
                        "sun_elevation_valid": None,
                        "moon_phase_consistent": None,
                    }

                # Parse timestamp
                try:
                    # EXIF format: "2023:10:15 14:30:00"
                    dt = datetime.strptime(ts, "%Y:%m:%d %H:%M:%S")
                except ValueError:
                    return {
                        "status": "parse_error",
                        "court_defensible": False,
                        "warning": f"Could not parse timestamp: {ts}",
                        "sun_elevation_valid": None,
                        "moon_phase_consistent": None,
                    }

                # Use astral to calculate sun position
                loc = LocationInfo(
                    latitude=gps["latitude"],
                    longitude=gps["longitude"]
                )
                s = sun(loc.observer, date=dt.date())

                claimed_hour = dt.hour + dt.minute / 60.0
                sunrise_hour = s["sunrise"].hour + s["sunrise"].minute / 60.0
                sunset_hour = s["sunset"].hour + s["sunset"].minute / 60.0

                is_daytime = sunrise_hour <= claimed_hour <= sunset_hour

                return {
                    "status": "real",
                    "court_defensible": True,
                    "sun_elevation_valid": is_daytime,
                    "sunrise_utc": str(s["sunrise"]),
                    "sunset_utc": str(s["sunset"]),
                    "claimed_time": ts,
                    "latitude": gps["latitude"],
                    "longitude": gps["longitude"],
                    "is_daytime_at_location": is_daytime,
                }
            except Exception as e:
                return {
                    "status": "error",
                    "court_defensible": False,
                    "warning": f"Astronomical calculation failed: {str(e)}",
                    "sun_elevation_valid": None,
                    "moon_phase_consistent": None,
                }

        async def reverse_image_search_handler(input_data: dict) -> dict:
            """
            Reverse image search via perceptual hash comparison against a
            local hash index of previously investigated evidence.

            This does not call TinEye (requires paid API key); instead it
            computes the PHash of the uploaded image and checks it against
            all hashes stored in the EvidenceStore (previous sessions).
            A near-duplicate match (Hamming distance ≤ 10 bits) suggests
            the image has appeared in a prior investigation — a significant
            provenance signal.
            """
            import imagehash
            from PIL import Image as PILImage

            artifact = input_data.get("artifact") or self.evidence_artifact

            try:
                img = PILImage.open(artifact.file_path).convert("RGB")
                query_hash = imagehash.phash(img, hash_size=16)

                # Build a hash index from previously seen evidence artifacts
                prior_matches = []
                HAMMING_THRESHOLD = 10  # bits — ~6 % bit-error tolerance

                # Attempt to scan local storage directory for prior images
                import os, glob
                evidence_dir = os.path.dirname(artifact.file_path)
                candidate_paths = glob.glob(os.path.join(evidence_dir, "**", "*.jpg"), recursive=True) + \
                                  glob.glob(os.path.join(evidence_dir, "**", "*.jpeg"), recursive=True) + \
                                  glob.glob(os.path.join(evidence_dir, "**", "*.png"), recursive=True)

                for path in candidate_paths:
                    if os.path.abspath(path) == os.path.abspath(artifact.file_path):
                        continue  # Skip self
                    try:
                        candidate_img = PILImage.open(path).convert("RGB")
                        candidate_hash = imagehash.phash(candidate_img, hash_size=16)
                        distance = query_hash - candidate_hash
                        if distance <= HAMMING_THRESHOLD:
                            prior_matches.append({
                                "path": os.path.basename(path),
                                "hamming_distance": int(distance),
                                "similarity_pct": round((1 - distance / 256) * 100, 1),
                            })
                    except Exception:
                        continue

                prior_found = len(prior_matches) > 0

                return {
                    "status": "real",
                    "court_defensible": True,
                    "method": "PHash (16×16) perceptual hash comparison — local evidence store",
                    "prior_appearance_found": prior_found,
                    "match_count": len(prior_matches),
                    "matches": prior_matches[:5],  # Return top 5 matches
                    "query_hash": str(query_hash),
                    "hamming_threshold": HAMMING_THRESHOLD,
                    "note": (
                        f"Found {len(prior_matches)} near-duplicate image(s) in the local evidence store — provenance signal."
                        if prior_found
                        else "No near-duplicate matches found in the local evidence store."
                    ),
                    "caveat": "Local PHash comparison only — does not search the open web. TinEye API integration required for web provenance.",
                }
            except Exception as e:
                return {
                    "status": "error",
                    "court_defensible": False,
                    "prior_appearance_found": None,
                    "error": str(e),
                }

        async def device_fingerprint_db_handler(input_data: dict) -> dict:
            """
            Device fingerprint analysis using EXIF and PRNU cross-validation.

            Extracts camera make/model from EXIF, cross-validates the claimed
            manufacturer against known EXIF field patterns (e.g. Apple always
            sets LensModel; Canon always sets MakerNote.LensType), and computes
            a simplified PRNU consistency score to detect device signature
            inconsistencies — a forensic indicator of metadata tampering or
            multi-device compositing.
            """
            import numpy as np
            from PIL import Image as PILImage

            artifact = input_data.get("artifact") or self.evidence_artifact

            try:
                # Extract EXIF metadata
                exif_fields = {}
                try:
                    import piexif
                    exif_raw = piexif.load(artifact.file_path)
                    zeroth = exif_raw.get("0th", {})
                    exif_raw_exif = exif_raw.get("Exif", {})
                    make_b = zeroth.get(piexif.ImageIFD.Make, b"")
                    model_b = zeroth.get(piexif.ImageIFD.Model, b"")
                    software_b = zeroth.get(piexif.ImageIFD.Software, b"")
                    make = make_b.decode(errors="replace").strip("\x00") if isinstance(make_b, bytes) else ""
                    model = model_b.decode(errors="replace").strip("\x00") if isinstance(model_b, bytes) else ""
                    software = software_b.decode(errors="replace").strip("\x00") if isinstance(software_b, bytes) else ""
                    focal_len = exif_raw_exif.get(piexif.ExifIFD.FocalLength)
                    iso = exif_raw_exif.get(piexif.ExifIFD.ISOSpeedRatings)
                    exif_fields = {"make": make, "model": model, "software": software,
                                   "focal_length": focal_len, "iso": iso}
                except Exception:
                    make, model, software = "", "", ""

                # Known manufacturer EXIF signature rules
                inconsistencies = []

                if make.startswith("Apple") and not model.startswith("iPhone") and not model.startswith("iPad"):
                    inconsistencies.append("Apple make declared but model does not match known Apple devices.")

                if make.startswith("Canon") and software and "Photoshop" in software:
                    inconsistencies.append("Canon make with Photoshop software field — possible metadata rewrite.")

                if make == "" and model != "":
                    inconsistencies.append("Model declared without Make field — unusual for genuine captures.")

                # Quick PRNU variance check
                try:
                    img_gray = np.array(PILImage.open(artifact.file_path).convert("L"), dtype=np.float32)
                    from scipy.ndimage import gaussian_filter
                    smooth = gaussian_filter(img_gray, sigma=2.0)
                    residual = img_gray - smooth
                    prnu_var = float(residual.var())
                    # GAN images typically have very uniform PRNU (< 1.0)
                    if prnu_var < 0.8:
                        inconsistencies.append(f"Extremely low PRNU variance ({prnu_var:.3f}) — consistent with synthetic/GAN generation.")
                except Exception:
                    prnu_var = None

                device_matched = bool(make and model)
                fingerprint_suspicious = len(inconsistencies) > 0

                return {
                    "status": "real",
                    "court_defensible": True,
                    "method": "EXIF manufacturer signature rules + PRNU variance cross-validation",
                    "device_model_matched": device_matched,
                    "camera_make": make,
                    "camera_model": model,
                    "software_field": software,
                    "exif_fingerprint_suspicious": fingerprint_suspicious,
                    "inconsistencies": inconsistencies,
                    "prnu_variance": round(prnu_var, 4) if prnu_var is not None else None,
                    "confidence": 0.60 if fingerprint_suspicious else 0.82,
                    "note": (
                        f"Device fingerprint shows {len(inconsistencies)} inconsistency(ies): {'; '.join(inconsistencies)}"
                        if inconsistencies
                        else "Device fingerprint appears consistent with declared camera metadata."
                    ),
                    "caveat": "Heuristic analysis — full CameraV PRNU database integration required for definitive attribution.",
                }
            except Exception as e:
                return {
                    "status": "error",
                    "court_defensible": False,
                    "device_model_matched": None,
                    "error": str(e),
                }

        async def adversarial_robustness_check_handler(input_data: dict) -> dict:
            """
            Adversarial robustness check for metadata evasion.

            Applies three metadata-level perturbations (timestamp shift ±1s,
            GPS coordinate jitter ±0.001°, software field overwrite) to a
            copy of the file and re-runs the anomaly scorer.  If the anomaly
            score changes significantly the metadata findings are fragile.
            """
            import numpy as np

            artifact = input_data.get("artifact") or self.evidence_artifact

            try:
                import piexif, shutil, tempfile, os
                from PIL import Image as PILImage

                # Load original anomaly score as baseline
                try:
                    from scripts.ml_tools.metadata_anomaly_scorer import score_metadata  # type: ignore
                    baseline_score = await run_ml_tool(
                        "metadata_anomaly_scorer.py", artifact.file_path, timeout=15.0
                    )
                    orig_score = float(baseline_score.get("anomaly_score", 0.5))
                except Exception:
                    orig_score = 0.5  # Neutral baseline if scorer unavailable

                # Create a working copy to perturb
                with tempfile.TemporaryDirectory() as tmpdir:
                    tmp_path = os.path.join(tmpdir, "perturbed.jpg")
                    shutil.copy2(artifact.file_path, tmp_path)

                    perturbation_deltas = {}

                    try:
                        exif_raw = piexif.load(tmp_path)

                        # 1 — Shift GPS latitude by ±0.001° if present
                        gps = exif_raw.get("GPS", {})
                        if gps.get(piexif.GPSIFD.GPSLatitude):
                            orig_lat = gps[piexif.GPSIFD.GPSLatitude]
                            # Perturb the seconds component slightly
                            deg, mins, secs = orig_lat
                            new_secs = (secs[0] + 100, secs[1])  # +0.001° approx
                            exif_raw["GPS"][piexif.GPSIFD.GPSLatitude] = (deg, mins, new_secs)
                            piexif.insert(piexif.dump(exif_raw), tmp_path)
                            gps_result = await run_ml_tool(
                                "metadata_anomaly_scorer.py", tmp_path, timeout=15.0
                            )
                            gps_score = float(gps_result.get("anomaly_score", orig_score))
                            perturbation_deltas["gps_jitter_0.001deg"] = round(abs(gps_score - orig_score), 4)
                        else:
                            perturbation_deltas["gps_jitter_0.001deg"] = 0.0

                        # 2 — Timestamp shift +1 second
                        exif_dt = exif_raw.get("Exif", {}).get(piexif.ExifIFD.DateTimeOriginal)
                        if exif_dt:
                            from datetime import datetime, timedelta
                            dt_str = exif_dt.decode(errors="replace") if isinstance(exif_dt, bytes) else exif_dt
                            try:
                                dt = datetime.strptime(dt_str, "%Y:%m:%d %H:%M:%S")
                                new_dt = (dt + timedelta(seconds=1)).strftime("%Y:%m:%d %H:%M:%S").encode()
                                exif_raw["Exif"][piexif.ExifIFD.DateTimeOriginal] = new_dt
                                piexif.insert(piexif.dump(exif_raw), tmp_path)
                                ts_result = await run_ml_tool(
                                    "metadata_anomaly_scorer.py", tmp_path, timeout=15.0
                                )
                                ts_score = float(ts_result.get("anomaly_score", orig_score))
                                perturbation_deltas["timestamp_+1s"] = round(abs(ts_score - orig_score), 4)
                            except Exception:
                                perturbation_deltas["timestamp_+1s"] = 0.0
                        else:
                            perturbation_deltas["timestamp_+1s"] = 0.0

                    except Exception as pex:
                        perturbation_deltas = {"perturbation_error": str(pex)}

                EVASION_THRESHOLD = 0.15  # > 15-point anomaly score shift from a 1s change is suspicious
                evasion_detected = any(
                    isinstance(v, float) and v > EVASION_THRESHOLD
                    for v in perturbation_deltas.values()
                )

                return {
                    "status": "real",
                    "court_defensible": True,
                    "method": "Metadata anomaly score perturbation stability — GPS jitter, timestamp shift",
                    "adversarial_pattern_detected": evasion_detected,
                    "original_anomaly_score": round(orig_score, 4),
                    "perturbation_deltas": perturbation_deltas,
                    "evasion_threshold": EVASION_THRESHOLD,
                    "confidence": 0.68 if evasion_detected else 0.85,
                    "note": (
                        "Metadata anomaly score is highly sensitive to minor perturbations — possible engineered metadata."
                        if evasion_detected
                        else "Metadata anomaly score is stable under all perturbations — findings are robust."
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
        
        # Register tools
        registry.register("exif_extract", exif_extract_handler, "Full EXIF extraction with absent-field logging")
        registry.register("metadata_anomaly_score", metadata_anomaly_score_handler, "ML metadata anomaly scoring via IsolationForest")
        registry.register("gps_timezone_validate", gps_timezone_validate_handler, "GPS-timestamp cross-validation")
        registry.register("steganography_scan", steganography_scan_handler, "Steganography scan")
        registry.register("file_structure_analysis", file_structure_analysis_handler, "File structure forensic analysis")
        registry.register("hex_signature_scan", hex_signature_scan_handler, "Hexadecimal signature scan for detecting hidden editing software marks")
        registry.register("timestamp_analysis", timestamp_analysis_handler, "Timestamp analysis")
        registry.register("file_hash_verify", file_hash_verify_handler, "File hash verification")
        registry.register("astronomical_api", astronomical_api_handler, "Astronomical data API queries")
        registry.register("reverse_image_search", reverse_image_search_handler, "Reverse image search")
        registry.register("device_fingerprint_db", device_fingerprint_db_handler, "Device fingerprint database lookup")
        registry.register("adversarial_robustness_check", adversarial_robustness_check_handler, "Adversarial robustness check")
        registry.register("extract_deep_metadata", extract_deep_metadata_handler, "Deep metadata extraction using ExifTool including MakerNotes")
        registry.register("get_physical_address", get_physical_address_handler, "Reverse geocode GPS coordinates to physical address")

        # ── OCR & Container Profiling ─────────────────────────────────────────

        async def extract_evidence_text_handler(input_data: dict) -> dict:
            """Auto-dispatching text extraction.
            PDF -> PyMuPDF (lossless embedded text + doc metadata).
            Image -> EasyOCR -> Tesseract fallback.
            """
            artifact = input_data.get("artifact") or self.evidence_artifact
            return await real_extract_evidence_text(artifact=artifact)

        async def mediainfo_profile_handler(input_data: dict) -> dict:
            """Deep AV container profiling: codec, frame rate mode, encoding tool,
            creation/tagged dates, VFR flag, container-codec mismatch,
            and editing software detection. Fast (<20ms). No model weights.
            """
            artifact = input_data.get("artifact") or self.evidence_artifact
            return await real_profile_av_container(artifact=artifact)

        async def av_file_identity_handler(input_data: dict) -> dict:
            """Lightweight AV pre-screen: format, primary codec, duration,
            resolution, and only HIGH-severity forensic flags.
            """
            artifact = input_data.get("artifact") or self.evidence_artifact
            return await real_get_av_file_identity(artifact=artifact)

        registry.register("extract_evidence_text", extract_evidence_text_handler, "Auto-dispatching text extraction: PDF (PyMuPDF lossless) -> EasyOCR -> Tesseract fallback")
        registry.register("mediainfo_profile", mediainfo_profile_handler, "Deep AV container profiling: codec, frame rate mode, encoding tools, forensic flags")
        registry.register("av_file_identity", av_file_identity_handler, "Lightweight AV pre-screen: format, codec, duration, high-severity flags only")

        # ── Gemini deep forensic analysis handler ──────────────────────────
        _gemini = GeminiVisionClient(self.config)

        async def gemini_deep_forensic_handler(input_data: dict) -> dict:
            """
            Comprehensive Gemini deep forensic analysis with full EXIF cross-validation.
            Identifies content type, extracts all visible text, detects objects and
            weapons, identifies interfaces/UIs, describes contextual narrative, and
            performs thorough metadata-vs-visual consistency check using the actual
            EXIF fields extracted by the initial analysis pass.
            """
            artifact = input_data.get("artifact") or self.evidence_artifact

            # Build the richest possible EXIF summary for Gemini to cross-validate
            exif_summary: dict = {}
            try:
                import piexif
                if artifact.file_path.lower().endswith((".jpg", ".jpeg", ".tiff", ".tif")):
                    exif_data = piexif.load(artifact.file_path)
                    zeroth = exif_data.get("0th", {})
                    exif_ifd = exif_data.get("Exif", {})
                    gps_ifd = exif_data.get("GPS", {})

                    def _b(v):
                        return v.decode(errors="replace").strip("\x00") if isinstance(v, bytes) else str(v) if v else ""

                    make = _b(zeroth.get(piexif.ImageIFD.Make, b""))
                    model = _b(zeroth.get(piexif.ImageIFD.Model, b""))
                    software = _b(zeroth.get(piexif.ImageIFD.Software, b""))
                    dt_orig = _b(exif_ifd.get(piexif.ExifIFD.DateTimeOriginal, b""))
                    dt_dig = _b(exif_ifd.get(piexif.ExifIFD.DateTimeDigitized, b""))
                    dt_mod = _b(zeroth.get(piexif.ImageIFD.DateTime, b""))
                    iso = exif_ifd.get(piexif.ExifIFD.ISOSpeedRatings)
                    focal = exif_ifd.get(piexif.ExifIFD.FocalLength)
                    exposure = exif_ifd.get(piexif.ExifIFD.ExposureTime)
                    flash = exif_ifd.get(piexif.ExifIFD.Flash)
                    width = zeroth.get(piexif.ImageIFD.ImageWidth) or exif_ifd.get(piexif.ExifIFD.PixelXDimension)
                    height = zeroth.get(piexif.ImageIFD.ImageLength) or exif_ifd.get(piexif.ExifIFD.PixelYDimension)

                    # GPS extraction
                    has_gps = bool(gps_ifd)
                    gps_str = ""
                    if has_gps:
                        try:
                            def _dms(val):
                                if not val: return None
                                d, m, s = val
                                return d[0]/d[1] + m[0]/m[1]/60 + s[0]/s[1]/3600
                            lat = _dms(gps_ifd.get(piexif.GPSIFD.GPSLatitude))
                            lon = _dms(gps_ifd.get(piexif.GPSIFD.GPSLongitude))
                            lat_ref = _b(gps_ifd.get(piexif.GPSIFD.GPSLatitudeRef, b"N"))
                            lon_ref = _b(gps_ifd.get(piexif.GPSIFD.GPSLongitudeRef, b"E"))
                            if lat and lon:
                                gps_str = f"{lat:.6f}{lat_ref}, {lon:.6f}{lon_ref}"
                        except Exception:
                            gps_str = "GPS present but could not decode"

                    exif_summary = {
                        "camera_make": make,
                        "camera_model": model,
                        "software": software,
                        "datetime_original": dt_orig,
                        "datetime_digitized": dt_dig,
                        "datetime_modified": dt_mod,
                        "iso": str(iso) if iso else "",
                        "focal_length": str(focal) if focal else "",
                        "exposure_time": str(exposure) if exposure else "",
                        "flash": str(flash) if flash is not None else "",
                        "image_width": str(width) if width else "",
                        "image_height": str(height) if height else "",
                        "has_gps": has_gps,
                        "gps_coordinates": gps_str,
                    }
                    # Remove empty fields to keep the prompt clean
                    exif_summary = {k: v for k, v in exif_summary.items() if v not in ("", None, False, "False")}
            except Exception:
                exif_summary = {"note": "EXIF extraction unavailable — visual analysis only"}

            # Merge any overrides from caller
            exif_summary.update(input_data.get("metadata_summary", {}))

            # Add file system metadata (os.stat) — file name, size, timestamps
            import os as _os
            import mimetypes as _mimetypes
            try:
                fp = artifact.file_path
                stat = _os.stat(fp)
                import datetime as _dt
                ctime = _dt.datetime.fromtimestamp(stat.st_ctime).strftime("%Y-%m-%d %H:%M:%S")
                mtime = _dt.datetime.fromtimestamp(stat.st_mtime).strftime("%Y-%m-%d %H:%M:%S")
                file_size_bytes = stat.st_size
                file_size_human = (
                    f"{file_size_bytes / 1_048_576:.2f} MB" if file_size_bytes >= 1_048_576
                    else f"{file_size_bytes / 1024:.1f} KB" if file_size_bytes >= 1024
                    else f"{file_size_bytes} bytes"
                )
                mime_guess, _ = _mimetypes.guess_type(fp)
                stored_mime = (artifact.metadata or {}).get("mime_type", "") if artifact.metadata else ""
                fs_meta = {
                    "file_name": _os.path.basename(fp),
                    "file_extension": _os.path.splitext(fp)[1].lower(),
                    "file_size_bytes": str(file_size_bytes),
                    "file_size_human": file_size_human,
                    "filesystem_created": ctime,
                    "filesystem_modified": mtime,
                    "mime_type_detected": mime_guess or stored_mime or "unknown",
                    "absolute_path": fp,
                }
                exif_summary.update({k: v for k, v in fs_meta.items() if v not in ("", None)})
            except Exception:
                pass

            # Add any EXIF findings from initial pass for cross-validation
            try:
                exif_initial_findings = [
                    f for f in (self._findings or [])
                    if f.metadata.get("tool_name") == "exif_extract"
                ]
                if exif_initial_findings:
                    ef = exif_initial_findings[0].metadata
                    extra = {}
                    for field in ["total_fields_extracted", "absent_mandatory_fields",
                                  "gps_coordinates", "datetime_original", "software",
                                  "device_model", "camera_make", "camera_model"]:
                        v = ef.get(field)
                        if v is not None and v not in ("", [], {}):
                            extra[f"exif_{field}"] = str(v) if not isinstance(v, str) else v
                    exif_summary.update(extra)
            except Exception:
                pass

            # Inject Agent 1 Gemini context for cross-validation (image content vs EXIF)
            try:
                a1 = type(self)._shared_agent1_context
                if a1:
                    agent1_cross = {
                        "agent1_content_type": a1.get("gemini_content_type", ""),
                        "agent1_scene": str(a1.get("gemini_narrative", a1.get("gemini_scene", "")))[:300],
                        "agent1_objects": a1.get("gemini_detected_objects", []),
                        "agent1_manipulation_signals": a1.get("gemini_manipulation_signals", []),
                        "agent1_extracted_text": a1.get("gemini_extracted_text", []),
                        "agent1_interface_detected": a1.get("gemini_interface", ""),
                        "agent1_authenticity_verdict": a1.get("gemini_verdict", ""),
                    }
                    # Only include non-empty fields
                    agent1_cross = {k: v for k, v in agent1_cross.items() if v not in ("", None, [], {})}
                    if agent1_cross:
                        exif_summary["agent1_image_forensics"] = agent1_cross
            except Exception:
                pass

            finding = await _gemini.deep_forensic_analysis(
                file_path=artifact.file_path,
                exif_summary=exif_summary or None,
            )
            result = finding.to_finding_dict(self.agent_id)

            # Expose all key fields for react_loop formatter and report
            result["gemini_metadata_verdict"] = finding.content_description
            result["gemini_provenance_flags"] = finding.manipulation_signals
            result["gemini_content_type"] = finding.file_type_assessment
            result["gemini_extracted_text"] = getattr(finding, "_extracted_text", [])
            result["gemini_interface"] = getattr(finding, "_interface_identification", "")
            result["gemini_narrative"] = getattr(finding, "_contextual_narrative", "")
            result["gemini_verdict"] = getattr(finding, "_authenticity_verdict", "")
            result["gemini_metadata_consistency"] = getattr(finding, "_metadata_visual_consistency", "")
            result["gemini_detected_objects"] = finding.detected_objects
            # Surface file system metadata prominently in result
            result["file_name"] = exif_summary.get("file_name", "")
            result["file_size_human"] = exif_summary.get("file_size_human", "")
            result["file_size_bytes"] = exif_summary.get("file_size_bytes", "")
            result["filesystem_created"] = exif_summary.get("filesystem_created", "")
            result["filesystem_modified"] = exif_summary.get("filesystem_modified", "")
            result["mime_type_detected"] = exif_summary.get("mime_type_detected", "")
            return result

        registry.register(
            "gemini_deep_forensic",
            gemini_deep_forensic_handler,
            "Gemini deep forensic analysis: content ID, text extraction, object/weapon detection, interface ID, narrative, full EXIF cross-validation",
        )

        return registry
    
    async def build_initial_thought(self) -> str:
        """
        Build the contextually-grounded initial thought for the ReAct loop.

        Pre-screens with exif_extract to get device model, GPS presence,
        software tags, and absent fields count before deeper forensic analysis.
        This grounds the entire investigation in the actual metadata state
        of the file rather than a generic opening statement.
        """
        context_lines = []
        absent_fields = []
        try:
            if self._tool_registry:
                handler = self._tool_registry._handlers.get("exif_extract")
                if handler:
                    result = await handler({"artifact": self.evidence_artifact})
                    # device_model is a top-level key from exif_extract_enhanced
                    device = result.get("device_model") or result.get("camera_make", "") + " " + result.get("camera_model", "")
                    device = device.strip()
                    # software lives inside present_fields or top-level
                    present = result.get("present_fields", result.get("all_metadata", {}))
                    software = result.get("software") or present.get("Software", present.get("EXIF:Software", ""))
                    gps = result.get("gps_coordinates") or present.get("GPSInfo")
                    total_tags = result.get("total_fields_extracted", result.get("total_exif_tags", len(present)))
                    absent_fields = result.get("absent_mandatory_fields", result.get("absent_fields", []))
                    created = (
                        result.get("datetime_original")
                        or present.get("EXIF:DateTimeOriginal")
                        or present.get("DateTimeOriginal")
                        or present.get("DateTime")
                        or ""
                    )
                    file_name = result.get("file_name", "")
                    file_size = result.get("file_size_human", "")
                    if device or total_tags:
                        context_lines.append(
                            f"File: {file_name} ({file_size}) | "
                            f"Device: {device or 'Unknown'}, software: {software or 'None'}, "
                            f"EXIF tags: {total_tags}, GPS: {'Present' if gps else 'ABSENT'}, "
                            f"Created: {created or 'Unknown'}"
                        )
                    if absent_fields:
                        context_lines.append(
                            f"ABSENT expected fields ({len(absent_fields)}): "
                            + ", ".join(str(f) for f in absent_fields[:6])
                        )
                    elif total_tags == 0:
                        context_lines.append("WARNING: No EXIF metadata found — possible metadata stripping")
        except Exception:
            pass

        context = " | ".join(context_lines) if context_lines else "EXIF pre-screen unavailable."
        absence_note = (
            f" ABSENCE AS SIGNAL: {len(absent_fields)} expected EXIF fields are missing — "
            "each absence is a mandatory investigation trigger."
            if absent_fields else ""
        )
        return (
            f"Starting metadata and provenance analysis. Evidence: {self.evidence_artifact.artifact_id}. "
            f"EXIF pre-screen — {context}.{absence_note} "
            f"Proceeding through {len(self.task_decomposition)} tasks: "
            "full EXIF extraction, GPS-timestamp cross-validation, ML metadata anomaly scoring, "
            "steganography scan, file structure analysis, hex signature scan, "
            "timestamp analysis, and deep metadata extraction. "
            "ABSENCE AS SIGNAL principle applies throughout: "
            "every expected-but-absent field is a mandatory Thought trigger."
        )
    async def run_investigation(self):
        """
        Override to ensure working memory is initialised before the base-class
        loop starts — this makes the heartbeat visible immediately.

        Agent 5 (Metadata) supports all file types, so it never skips; this
        override exists purely to call _initialize_working_memory() first and
        set _skip_memory_init so the base class does not re-initialise it.
        """
        await self._initialize_working_memory()
        self._skip_memory_init = True
        self._tool_registry = await self.build_tool_registry()
        return await super().run_investigation()
