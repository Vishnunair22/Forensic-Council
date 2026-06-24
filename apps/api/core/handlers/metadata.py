"""
Metadata Tool Handlers
======================

Domain-specific handlers for metadata and provenance forensic tools.
Implements Fix 3 (Decentralization) and Initial Analysis Refinements.
"""

import re
from pathlib import Path

from core.handlers.base import BaseToolHandler
from core.media_kind import is_screen_capture_like
from core.ml_subprocess import run_ml_tool
from core.structured_logging import get_logger
from tools.metadata_tools import _convert_to_degrees
from tools.metadata_tools import camera_profile_match as real_camera_profile_match
from tools.metadata_tools import exif_extract as real_exif_extract
from tools.metadata_tools import file_structure_analysis as real_file_structure_analysis
from tools.metadata_tools import gps_timezone_validate as real_gps_timezone_validate
from tools.metadata_tools import hex_signature_scan as real_hex_signature_scan
from tools.metadata_tools import prnu_sensor_verification as real_prnu_sensor_verification
from tools.metadata_tools import provenance_chain_verify as real_provenance_chain_verify
from tools.metadata_tools import steganography_scan as real_steganography_scan
from tools.metadata_tools import timestamp_analysis as real_timestamp_analysis

logger = get_logger(__name__)

# Precise date/time detector for visually-grounded timestamp corroboration.
# The old substring test (":" / "202" / "am" / "pm") matched almost any text —
# URLs, the word "camera", a street number "202 Main St" — and falsely reported
# a corroborated timestamp. This requires an actual clock or calendar pattern.
_VISUAL_TIMESTAMP_RE = re.compile(
    r"\b\d{1,2}:\d{2}(?::\d{2})?\s*(?:[ap]\.?m\.?)?\b"          # 12:34, 12:34:56, 9:05 pm
    r"|\b(?:19|20)\d{2}[-/.](?:0?[1-9]|1[0-2])[-/.](?:0?[1-9]|[12]\d|3[01])\b"  # 2024-01-31
    r"|\b(?:0?[1-9]|[12]\d|3[01])[-/.](?:0?[1-9]|1[0-2])[-/.](?:19|20)\d{2}\b"  # 31/01/2024
    r"|\b\d{1,2}\s*[ap]\.?m\.?\b",                              # 9 pm
    re.IGNORECASE,
)


class MetadataHandlers(BaseToolHandler):
    """Handles EXIF extraction, GPS validation, and provenance verification."""

    @staticmethod
    def _extract_gps_decimal(exif: dict) -> tuple[float | None, float | None]:
        """Extract decimal-degree GPS from raw PIL EXIF fields (GPSLatitude tuples)."""
        lat_raw = exif.get("GPSLatitude")
        lon_raw = exif.get("GPSLongitude")
        lat = _convert_to_degrees(lat_raw)
        lon = _convert_to_degrees(lon_raw)
        if lat is not None:
            ref = str(exif.get("GPSLatitudeRef") or "").strip().upper()
            if ref == "S":
                lat = -lat
        if lon is not None:
            ref = str(exif.get("GPSLongitudeRef") or "").strip().upper()
            if ref == "W":
                lon = -lon
        return lat, lon

    def register_tools(self, registry) -> None:
        """Register tools with the agent's ToolRegistry."""
        registry.register(
            "file_hash_verify",
            self.file_hash_verify_handler,
            "SHA-256 hash verification against ingestion record",
        )
        registry.register("exif_extract", self.exif_extract_handler, "EXIF metadata extraction")
        registry.register(
            "metadata_anomaly_score",
            self.metadata_anomaly_score_handler,
            "ML metadata anomaly check",
        )
        registry.register(
            "gps_timezone_validate", self.gps_timezone_validate_handler, "GPS/Timezone consistency"
        )
        registry.register(
            "steganography_scan", self.steganography_scan_handler, "LSB steganography scan"
        )
        registry.register(
            "timestamp_analysis", self.timestamp_analysis_handler, "Incremental timestamp parity"
        )
        registry.register(
            "camera_profile_match", self.camera_profile_match_handler, "Hardware profile matching"
        )
        registry.register(
            "provenance_chain_verify",
            self.provenance_chain_verify_handler,
            "Blockchain/Signature provenance",
        )
        registry.register(
            "compression_risk_audit",
            self.compression_risk_audit_handler,
            "Audit metadata for social media compression footprints",
        )
        registry.register(
            "file_structure_analysis",
            self.file_structure_analysis_handler,
            "Binary structure and trailer/header anomaly analysis",
        )
        registry.register(
            "hex_signature_scan",
            self.hex_signature_scan_handler,
            "Raw-byte software signature scan",
        )
        registry.register(
            "prnu_sensor_verification",
            self.prnu_sensor_verification_handler,
            "PRNU camera sensor fingerprint match",
        )
        registry.register(
            "ai_text_detector",
            self.ai_text_detector_handler,
            "Statistical AI-generated-text detector for documents",
        )

        # Compatibility aliases for older task plans and arbiter/synthesis labels.
        registry.register(
            "metadata_anomaly_scorer",
            self.metadata_anomaly_score_handler,
            "Alias for ML metadata anomaly score",
        )
        registry.register(
            "c2pa_validator",
            self.provenance_chain_verify_handler,
            "Alias for C2PA/provenance chain verification",
        )
        registry.register(
            "device_fingerprint_db",
            self.camera_profile_match_handler,
            "Alias for camera profile matching",
        )

        # New Refinement Tools
        registry.register(
            "exif_isolation_forest",
            self.exif_isolation_forest_handler,
            "Isolation Forest ML outlier detection for EXIF manifolds",
        )
        registry.register(
            "astro_grounding",
            self.astro_grounding_handler,
            "Astronomical shadow/sun orientation grounding",
        )

    # ── Refinement: EXIF Isolation Forest ─────────────────────────────

    async def exif_isolation_forest_handler(self, input_data: dict, record: bool = True) -> dict:
        """[REFINED] Uses Isolation Forest ML to identify anomalous metadata clusters."""
        artifact = input_data.get("artifact") or self.agent.evidence_artifact
        await self.agent.update_sub_task("Auditing EXIF manifold via Isolation Forest ML...")
        try:
            result = await run_ml_tool("exif_isolation_forest.py", artifact.file_path, timeout=15.0)
            if not result.get("error") and result.get("available"):
                if record:
                    await self.agent._record_tool_result("exif_isolation_forest", result)
                return result
        except Exception as exc:
            logger.debug("EXIF isolation forest unavailable", error=str(exc))

        # Fallback to standard anomaly score (pass record=False to avoid double-counting)
        await self.agent.update_sub_task(
            "Isolation Forest unavailable — falling back to standard anomaly score..."
        )
        fallback = await self.metadata_anomaly_score_handler(input_data, record=False)
        result = {
            **fallback,
            "degraded": True,
            "fallback_reason": "exif_isolation_forest unavailable; used metadata anomaly score",
        }
        if record:
            await self.agent._record_tool_result("exif_isolation_forest", result)
        return result

    # ── Refinement: Astro Grounding ────────────────────────────────────

    async def astro_grounding_handler(self, input_data: dict) -> dict:
        """[REFINED] Verifies shadow direction against astronomical sun position."""
        artifact = input_data.get("artifact") or self.agent.evidence_artifact
        await self.agent.update_sub_task(
            "Auditing shadow vectors vs astronomical sun orientation..."
        )

        exif = self.agent._tool_context.get("exif_extract", {})
        gps_lat, gps_lon = self._extract_gps_decimal(exif)
        ts = exif.get("DateTimeOriginal")

        if gps_lat is None or gps_lon is None or not ts:
            result = {
                "available": False,
                "not_applicable": True,
                "confidence": 0.0,
                "court_defensible": False,
                "note": "Astro grounding requires valid GPS and Timestamp in EXIF.",
            }
            await self.agent._record_tool_result("astro_grounding", result)
            return result

        try:
            result = await run_ml_tool(
                "astro_grounding_engine.py",
                artifact.file_path,
                extra_args=[
                    "--lat",
                    str(gps_lat),
                    "--lon",
                    str(gps_lon),
                    "--time",
                    str(ts),
                ],
                timeout=15.0,
            )

            if not result.get("error") and result.get("available"):
                await self.agent._record_tool_result("astro_grounding", result)
                return result
        except Exception as exc:
            logger.debug("Astro grounding engine unavailable", error=str(exc))

        result = {
            "available": False,
            "confidence": 0.0,
            "court_defensible": False,
            "note": "Astro grounding engine failed or analytical model unavailable.",
        }
        await self.agent._record_tool_result("astro_grounding", result)
        return result

    # ── Standard Handlers (Migrated) ─────────────────────────────────────

    async def exif_extract_handler(self, input_data: dict) -> dict:
        artifact = input_data.get("artifact") or self.agent.evidence_artifact
        await self.agent.update_sub_task("Extracting EXIF bitstream...")
        result = await real_exif_extract(artifact=artifact)
        path = Path(artifact.file_path)
        total_fields = int(
            result.get("total_exif_tags") or result.get("total_fields_extracted") or 0
        )
        absent_fields = list(
            result.get("absent_fields") or result.get("absent_mandatory_fields") or []
        )
        png_text_count = int(result.get("png_text_fields_count", 0))

        # Compute human-readable file size
        try:
            raw_size = path.stat().st_size
            for unit in ("B", "KB", "MB", "GB"):
                if raw_size < 1024:
                    file_size_human = f"{raw_size:.0f} {unit}"
                    break
                raw_size /= 1024
            else:
                file_size_human = f"{raw_size:.1f} TB"
        except Exception:
            file_size_human = ""

        result.setdefault("file_name", path.name)
        result.setdefault("file_size_human", file_size_human)
        result.setdefault("mime_type", getattr(artifact, "mime_type", "") or "")
        result.setdefault("absent_mandatory_fields", absent_fields)
        result.setdefault("available", True)
        result.setdefault("court_defensible", True)

        # When no EXIF IFD but PNG text chunks exist, report those as the field count
        if total_fields == 0 and png_text_count > 0:
            result.setdefault("total_fields_extracted", png_text_count)
            result.setdefault(
                "file_format_note",
                f"No EXIF IFD block present. {png_text_count} PNG text chunk field(s) extracted "
                f"(tEXt/iTXt). EXIF-dependent camera analysis is limited.",
            )
            result.setdefault("confidence", 0.70)
        else:
            result.setdefault("total_fields_extracted", total_fields)
            if total_fields == 0:
                result.setdefault(
                    "file_format_note",
                    "No EXIF metadata block was present; EXIF-dependent checks are limited.",
                )
            result.setdefault("confidence", 0.65 if total_fields == 0 else 0.75)

        # ── Grounding Metadata with Gemini Vision (if available) ──
        gemini_context = ""
        gemini_text = ""
        if hasattr(self.agent, "_agent1_context") and self.agent._agent1_context:
            gemini_context = str(self.agent._agent1_context.get("content_description") or "")
            gemini_text = str(self.agent._agent1_context.get("metadata", {}).get("extracted_text") or "")
        elif getattr(self.agent, "inter_agent_bus", None):
            shared = self.agent.inter_agent_bus.get_visual_profile(str(self.agent.session_id)) or {}
            gemini_context = str(shared.get("content_description") or "")
            gemini_text = str(shared.get("metadata", {}).get("extracted_text") or "")

        gemini_validation = {}
        if gemini_context or gemini_text:
            has_time = bool(result.get("DateTimeOriginal") or result.get("datetime_original") or result.get("CreationDate"))
            if not has_time:
                gemini_validation["note"] = "Primary metadata timestamp missing. "
                # Detect a real clock/calendar pattern Gemini read from the image
                # (e.g. a screenshot status-bar clock), not any text containing a colon.
                if _VISUAL_TIMESTAMP_RE.search(gemini_text):
                    gemini_validation["note"] += "However, Gemini visual analysis extracted potential date/time text directly from the image content."
                    gemini_validation["corroborated_from_visuals"] = True

            make = str(result.get("make") or "").lower()
            if make and "screenshot" in gemini_context.lower() and make not in gemini_context.lower():
                note = gemini_validation.get("note", "")
                gemini_validation["note"] = note + f" Note: EXIF claims device '{make}', but visual analysis identifies this as a screenshot."
                gemini_validation["hallucination_risk"] = True

            if gemini_validation:
                result["gemini_cross_validation"] = gemini_validation

        await self.agent._record_tool_result("exif_extract", result)
        return result

    # MIME types that natively store metadata outside EXIF IFD — zero EXIF fields is expected
    _LOSSLESS_NO_EXIF_MIMES = frozenset({
        "image/png", "image/gif", "image/bmp", "image/webp",
        "image/tiff",  # TIFF can carry EXIF but often doesn't
    })

    async def metadata_anomaly_score_handler(self, input_data: dict, record: bool = True) -> dict:
        artifact = input_data.get("artifact") or self.agent.evidence_artifact
        await self.agent.update_sub_task("Auditing probabilistic metadata fabrication (ML)...")
        result = await run_ml_tool("metadata_anomaly_scorer.py", artifact.file_path, timeout=15.0)
        if result.get("error") or not result.get("available", True):
            exif = self.agent._tool_context.get("exif_extract") or await real_exif_extract(
                artifact=artifact
            )
            absent = exif.get("absent_mandatory_fields", []) if isinstance(exif, dict) else []
            total_fields = (
                int(exif.get("total_fields_extracted", 0) or 0) if isinstance(exif, dict) else 0
            )
            mime = (getattr(artifact, "mime_type", "") or "").lower()
            is_lossless = mime in self._LOSSLESS_NO_EXIF_MIMES

            score = 0.15
            if total_fields == 0:
                if is_lossless:
                    # Zero EXIF is normal for this format — not a manipulation signal
                    score = 0.10
                    note = (
                        f"Zero EXIF IFD fields is expected for {mime}; "
                        "format uses native metadata blocks, not EXIF. "
                        "ML metadata scorer unavailable; low-risk baseline applied."
                    )
                else:
                    # Stripped EXIF is routine for messaging-app / social-media
                    # transmission — provenance is unverifiable, not tampered. This
                    # completeness fallback sees only absence (no edit signatures),
                    # so it must never assert manipulation (kept below is_anomalous).
                    score = 0.35
                    note = "ML metadata scorer unavailable; EXIF stripped/absent — provenance unverifiable (common for messaging-app transmission), not a manipulation signal."
            elif len(absent) >= 10:
                score = 0.4
                note = "ML metadata scorer unavailable; many mandatory EXIF fields absent — provenance incomplete, not a tampering signal."
            elif len(absent) >= 5:
                score = 0.3
                note = "ML metadata scorer unavailable; several mandatory EXIF fields absent."
            else:
                note = "ML metadata scorer unavailable; used deterministic EXIF completeness fallback."

            result = {
                "available": True,
                "degraded": True,
                "court_defensible": False,
                "anomaly_score": score,
                "is_anomalous": score >= 0.6,
                "anomalous_fields": absent[:8],
                "confidence": max(0.55, 1.0 - score),
                "note": note,
            }
        if record:
            await self.agent._record_tool_result("metadata_anomaly_score", result)
        return result

    async def gps_timezone_validate_handler(self, input_data: dict) -> dict:
        artifact = input_data.get("artifact") or self.agent.evidence_artifact
        exif = self.agent._tool_context.get("exif_extract")
        if not exif:
            exif = await real_exif_extract(artifact=artifact)

        gps_lat, gps_lon = self._extract_gps_decimal(exif)
        ts = exif.get("DateTimeOriginal")

        if gps_lat is None or gps_lon is None or not ts:
            result = {
                "available": False,
                "not_applicable": True,
                "reason": "GPS-timezone validation requires both GPS coordinates and EXIF capture timestamp.",
                "confidence": 0.0,
                "court_defensible": False,
            }
            await self.agent._record_tool_result("gps_timezone_validate", result)
            return result

        result = await real_gps_timezone_validate(
            gps_lat=gps_lat, gps_lon=gps_lon, timestamp_utc=ts
        )
        await self.agent._record_tool_result("gps_timezone_validate", result)
        return result

    async def steganography_scan_handler(self, input_data: dict) -> dict:
        artifact = input_data.get("artifact") or self.agent.evidence_artifact
        await self.agent.update_sub_task("Scanning bitstream for steganographic payloads (LSB)...")
        result = await real_steganography_scan(artifact=artifact)
        await self.agent._record_tool_result("steganography_scan", result)
        return result

    async def timestamp_analysis_handler(self, input_data: dict) -> dict:
        artifact = input_data.get("artifact") or self.agent.evidence_artifact
        await self.agent.update_sub_task("Auditing incremental timestamp parity...")
        result = await real_timestamp_analysis(artifact=artifact)
        inconsistencies = result.get("inconsistencies", []) if isinstance(result, dict) else []
        result["available"] = True
        result["court_defensible"] = True
        result["timestamps_consistent"] = not bool(inconsistencies)
        result["inconsistency_detected"] = bool(inconsistencies)
        result["confidence"] = 0.78 if inconsistencies else 0.72
        await self.agent._record_tool_result("timestamp_analysis", result)
        return result

    async def file_structure_analysis_handler(self, input_data: dict) -> dict:
        artifact = input_data.get("artifact") or self.agent.evidence_artifact
        await self.agent.update_sub_task("Auditing binary headers, trailers, and appended data...")
        result = await real_file_structure_analysis(artifact=artifact)
        result["available"] = True
        result["court_defensible"] = True
        await self.agent._record_tool_result("file_structure_analysis", result)
        return result

    async def hex_signature_scan_handler(self, input_data: dict) -> dict:
        artifact = input_data.get("artifact") or self.agent.evidence_artifact
        await self.agent.update_sub_task("Scanning raw bytes for editor and encoder signatures...")
        result = await real_hex_signature_scan(artifact=artifact)
        result["available"] = True
        result["court_defensible"] = True
        await self.agent._record_tool_result("hex_signature_scan", result)
        return result

    async def camera_profile_match_handler(self, input_data: dict) -> dict:
        artifact = input_data.get("artifact") or self.agent.evidence_artifact
        await self.agent.update_sub_task("Vetting hardware signature against sensor database...")
        result = await real_camera_profile_match(artifact=artifact)
        await self.agent._record_tool_result("camera_profile_match", result)
        return result

    async def provenance_chain_verify_handler(self, input_data: dict) -> dict:
        artifact = input_data.get("artifact") or self.agent.evidence_artifact
        await self.agent.update_sub_task(
            "Auditing C2PA provenance manifest and binary JUMBF signatures..."
        )

        # Use ML-grade C2PA validator primarily (Fix for Checklist Item 10)
        result = await run_ml_tool("c2pa_validator.py", artifact.file_path, timeout=10.0)

        if result.get("error") or not result.get("available"):
            # Fallback to heuristic EXIF-based check
            fallback = await real_provenance_chain_verify(artifact=artifact)
            result = {
                **fallback,
                "degraded": True,
                "fallback_reason": f"ML C2PA validator failed: {result.get('error', 'unavailable')}",
            }

        # Normalize result for Arbiter
        result.setdefault("provenance_found", result.get("c2pa_present", False))

        await self.agent._record_tool_result("provenance_chain_verify", result)
        return result

    async def file_hash_verify_handler(self, input_data: dict) -> dict:
        """Verify the SHA-256 hash of the evidence file against the ingestion record."""
        import hashlib

        artifact = input_data.get("artifact") or self.agent.evidence_artifact
        await self.agent.update_sub_task("Verifying SHA-256 hash against ingestion record...")
        try:
            sha256 = hashlib.sha256()
            with open(artifact.file_path, "rb") as fh:
                for chunk in iter(lambda: fh.read(65536), b""):
                    sha256.update(chunk)
            computed = sha256.hexdigest()
            stored = getattr(artifact, "content_hash", None)
            # Distinguish "no reference hash on record" from "hash mismatch".
            # When there is no stored hash, match must be None — not False — because
            # the classifier reads hash_match==False as a POSITIVE tampering signal,
            # which would falsely flag every file that lacks an ingestion reference.
            if stored is None:
                match: bool | None = None
                verification_status = "NO_REFERENCE_HASH"
            else:
                match = computed == stored
                verification_status = "MATCH" if match else "MISMATCH"
            result = {
                "computed_hash": computed,
                "current_hash": computed,
                "stored_hash": stored,
                "original_hash": stored,
                "hash_match": match,
                "hash_matches": match,
                "verification_status": verification_status,
                "file_name": Path(artifact.file_path).name,
                "file_size_bytes": Path(artifact.file_path).stat().st_size,
                "available": True,
                "confidence": 1.0 if stored is not None else 0.0,
                "court_defensible": True,
            }
            if stored is None:
                result["limitation"] = (
                    "No ingestion reference hash on record; integrity could be computed "
                    "but not verified against a prior state."
                )
        except Exception as exc:
            result = {
                "available": False,
                "error": str(exc),
                "confidence": 0.0,
                "court_defensible": False,
            }
        await self.agent._record_tool_result("file_hash_verify", result)
        return result

    async def compression_risk_audit_handler(self, input_data: dict) -> dict:
        """Audits metadata for social media/chat app compression footprints."""
        artifact = input_data.get("artifact") or self.agent.evidence_artifact
        await self.agent.update_sub_task("Auditing for social media compression footprints...")

        exif = self.agent._tool_context.get("exif_extract", {})
        sw = str(exif.get("software", "")).lower()
        make = str(exif.get("make", "")).lower()
        model = str(exif.get("model", "")).lower()
        # The artifact is stored under a UUID path; the original upload name lives in
        # metadata["original_filename"]. Reading getattr(artifact, "file_name") alone
        # always returned "" (no such attribute), so the WhatsApp/screenshot/camera
        # filename signals below never fired and every metadata-light image fell
        # through to the generic "Unknown (Stripped Metadata)" branch.
        _art_meta = getattr(artifact, "metadata", None)
        file_name = str(
            (_art_meta.get("original_filename") if isinstance(_art_meta, dict) else "")
            or getattr(artifact, "file_name", "")
            or ""
        ).lower()

        # EXIF-field-count reasoning only applies to images. Audio/video/PDF do not
        # carry EXIF at all, so "few EXIF fields" is the normal case and must never
        # be read as stripped/suspicious metadata for those media.
        _amd = getattr(artifact, "metadata", None)
        _mime = str(_amd.get("mime_type") if isinstance(_amd, dict) else "") or ""
        _mime = _mime or str(getattr(artifact, "mime_type", "") or "")
        _is_image = _mime.startswith("image/")

        # Social Media / Heavy Compression apps
        social_apps = {"instagram", "tiktok", "facebook", "snapchat", "twitter", "x.com"}
        chat_apps = {"whatsapp", "telegram", "imessage", "signal", "viber", "discord", "slack"}

        penalty = 1.0
        platform = None

        # 1. Explicit app markers in EXIF
        if any(x in sw or x in make or x in model for x in social_apps):
            penalty = 0.45
            platform = "Social Media (High Compression)"
        elif any(x in sw or x in make or x in model for x in chat_apps):
            penalty = 0.65
            platform = "Messaging App (Medium-High Compression)"

        # 2. Filename patterns (forensic signals for specific platforms)
        elif "whatsapp" in file_name or "telegram" in file_name:
            penalty = 0.65
            platform = "Messaging App (Filename Signal)"
        elif "screenshot" in file_name:
            penalty = 0.85
            platform = "System Screenshot (UI Compression)"
        elif "fb_img" in file_name or "insta" in file_name:
            penalty = 0.45
            platform = "Social Media (Filename Signal)"

        # 3. Stripped EXIF (common after social-media re-encoding, but also caused by
        # privacy tools, format converters, and modern phones stripping location data).
        # Require very few fields (< 3) before applying a penalty — a file with 3-4 EXIF
        # tags still has meaningful provenance signals and should not be penalised.
        total_fields = int(exif.get("total_fields_extracted", 0))
        if _is_image and penalty == 1.0 and total_fields < 3:
            # Check if capture fields exist despite low tag count (partial metadata)
            fnumber = exif.get("FNumber")
            iso = exif.get("ISOSpeedRatings")
            has_capture_fields = bool(fnumber or iso)
            is_camera_file = any(x in file_name for x in ("dsc", "img_", "p_", "mvc", "dcim"))
            if has_capture_fields:
                penalty = 0.92  # Has capture params — partial metadata, low risk
                platform = "Camera Capture (Partial Metadata)"
            elif is_camera_file:
                penalty = 0.95  # Camera capture with privacy-stripped metadata
                platform = "Camera Capture (Stripped Metadata)"
            elif is_screen_capture_like(artifact):
                # A visually-confirmed screenshot legitimately carries no camera EXIF —
                # absent metadata is EXPECTED here, not a provenance concern. Treat it
                # as the normal screenshot path rather than the generic "stripped" flag.
                penalty = 0.85
                platform = "System Screenshot (UI Compression)"
            else:
                penalty = 0.78  # Minor penalty — non-standard name with near-zero EXIF
                platform = "Unknown (Stripped Metadata)"

        result = {
            "available": True,
            "compression_risk": round(1.0 - penalty if penalty < 1.0 else 0.0, 3),
            "compression_penalty": penalty,
            "detected_platform": platform,
            "metadata_stripped": bool(_is_image and total_fields < 5),
            "forensic_reliability_impact": "HIGH"
            if penalty < 0.5
            else ("MEDIUM" if penalty < 0.8 else "NONE"),
            "confidence": 0.85,
            "court_defensible": True,
            "note": f"Compression penalty of {penalty} applied due to {platform or 'no detected footprints'}.",
        }

        await self.agent._record_tool_result("compression_risk_audit", result)
        return result

    async def prnu_sensor_verification_handler(self, input_data: dict) -> dict:
        artifact = input_data.get("artifact") or self.agent.evidence_artifact
        await self.agent.update_sub_task(
            "Auditing sensor noise residuals for PRNU fingerprint matching..."
        )

        if is_screen_capture_like(artifact):
            result = {
                "available": True,
                "status": "not_applicable",
                "verdict": "NOT_APPLICABLE",
                "evidence_verdict": "NOT_APPLICABLE",
                "prnu_not_applicable": True,
                "confidence": 0.0,
                "court_defensible": False,
                "reason": (
                    "PRNU sensor matching is not meaningful for screenshots because "
                    "there is no camera sensor noise pattern to validate."
                ),
            }
            await self.agent._record_tool_result("prnu_sensor_verification", result)
            return result

        # Upgrade: Use real noiseprint ML tool instead of baseline stub (Fix for Checklist Item 10)
        result = await run_ml_tool("noiseprint_clustering.py", artifact.file_path, timeout=30.0)

        if result.get("error") or not result.get("available"):
            # Final fallback to baseline if ML fails
            fallback = await real_prnu_sensor_verification(artifact=artifact)
            result = {
                **fallback,
                "degraded": True,
                "fallback_reason": f"ML noiseprint clustering failed: {result.get('error', 'unavailable')}",
            }

        await self.agent._record_tool_result("prnu_sensor_verification", result)
        return result

    async def ai_text_detector_handler(self, input_data: dict) -> dict:
        """Audits document text for statistical signatures of AI generation."""
        artifact = input_data.get("artifact") or self.agent.evidence_artifact
        await self.agent.update_sub_task("Auditing document text for AI-generation statistical signatures...")

        result = await run_ml_tool("ai_text_detector.py", artifact.file_path, extra_args=["--is-path"], timeout=20.0)
        
        # If the worker failed because the text is too short or file could not be read, 
        # ensure it degrades gracefully without raising
        if result.get("error") or not result.get("available"):
            result.setdefault("available", False)
            result.setdefault("ai_text_probability", 0.0)
            result.setdefault("is_ai_suspected", False)
            result.setdefault("degraded", True)
            result.setdefault("fallback_reason", f"ai_text_detector failed or inapplicable: {result.get('error') or result.get('reason') or 'unavailable'}")

        # The AI text detector gives 'ai_text_probability' and 'is_ai_suspected'.
        # We need to map this to evidence_verdict so it shows up in findings natively.
        prob = float(result.get("ai_text_probability") or 0.0)
        if prob >= 0.70:
            result["evidence_verdict"] = "POSITIVE"
            result["severity_tier"] = "HIGH"
        elif prob >= 0.50:
            result["evidence_verdict"] = "SUSPICIOUS"
            result["severity_tier"] = "MEDIUM"
        else:
            result["evidence_verdict"] = "AUTHENTIC"
            
        await self.agent._record_tool_result("ai_text_detector", result)
        return result
