"""
Metadata Tool Handlers
======================

Domain-specific handlers for metadata and provenance forensic tools.
Implements Fix 3 (Decentralization) and Initial Analysis Refinements.
"""


from core.handlers.base import BaseToolHandler
from core.ml_subprocess import run_ml_tool
from core.structured_logging import get_logger
from tools.metadata_tools import camera_profile_match as real_camera_profile_match
from tools.metadata_tools import exif_extract as real_exif_extract
from tools.metadata_tools import file_structure_analysis as real_file_structure_analysis
from tools.metadata_tools import gps_timezone_validate as real_gps_timezone_validate
from tools.metadata_tools import hex_signature_scan as real_hex_signature_scan
from tools.metadata_tools import provenance_chain_verify as real_provenance_chain_verify
from tools.metadata_tools import steganography_scan as real_steganography_scan
from tools.metadata_tools import timestamp_analysis as real_timestamp_analysis

logger = get_logger(__name__)

class MetadataHandlers(BaseToolHandler):
    """Handles EXIF extraction, GPS validation, and provenance verification."""

    def register_tools(self, registry) -> None:
        """Register tools with the agent's ToolRegistry."""
        registry.register("exif_extract", self.exif_extract_handler, "EXIF metadata extraction")
        registry.register("metadata_anomaly_score", self.metadata_anomaly_score_handler, "ML metadata anomaly check")
        registry.register("gps_timezone_validate", self.gps_timezone_validate_handler, "GPS/Timezone consistency")
        registry.register("steganography_scan", self.steganography_scan_handler, "LSB steganography scan")
        registry.register("timestamp_analysis", self.timestamp_analysis_handler, "Incremental timestamp parity")
        registry.register("camera_profile_match", self.camera_profile_match_handler, "Hardware profile matching")
        registry.register("provenance_chain_verify", self.provenance_chain_verify_handler, "Blockchain/Signature provenance")
        registry.register("compression_risk_audit", self.compression_risk_audit_handler, "Audit metadata for social media compression footprints")
        registry.register("file_structure_analysis", self.file_structure_analysis_handler, "Binary structure and trailer/header anomaly analysis")
        registry.register("hex_signature_scan", self.hex_signature_scan_handler, "Raw-byte software signature scan")

        # Compatibility aliases for older task plans and arbiter/synthesis labels.
        registry.register("metadata_anomaly_scorer", self.metadata_anomaly_score_handler, "Alias for ML metadata anomaly score")
        registry.register("c2pa_validator", self.provenance_chain_verify_handler, "Alias for C2PA/provenance chain verification")
        registry.register("device_fingerprint_db", self.camera_profile_match_handler, "Alias for camera profile matching")

        # New Refinement Tools
        registry.register("exif_isolation_forest", self.exif_isolation_forest_handler, "Isolation Forest ML outlier detection for EXIF manifolds")
        registry.register("astro_grounding", self.astro_grounding_handler, "Astronomical shadow/sun orientation grounding")

    # ── Refinement: EXIF Isolation Forest ─────────────────────────────

    async def exif_isolation_forest_handler(self, input_data: dict) -> dict:
        """[REFINED] Uses Isolation Forest ML to identify anomalous metadata clusters."""
        artifact = input_data.get("artifact") or self.agent.evidence_artifact
        await self.agent.update_sub_task("Auditing EXIF manifold via Isolation Forest ML...")
        try:
            result = await run_ml_tool("exif_isolation_forest.py", artifact.file_path, timeout=15.0)
            if not result.get("error") and result.get("available"):
                await self.agent._record_tool_result("exif_isolation_forest", result)
                return result
        except Exception as exc:
            logger.debug("EXIF isolation forest unavailable", error=str(exc))

        # Fallback to standard anomaly score
        await self.agent.update_sub_task("Isolation Forest unavailable — falling back to standard anomaly score...")
        fallback = await self.metadata_anomaly_score_handler(input_data)
        result = {
            **fallback,
            "degraded": True,
            "fallback_reason": "exif_isolation_forest unavailable; used metadata anomaly score",
        }
        await self.agent._record_tool_result("exif_isolation_forest", result)
        return result

    # ── Refinement: Astro Grounding ────────────────────────────────────

    async def astro_grounding_handler(self, input_data: dict) -> dict:
        """[REFINED] Verifies shadow direction against astronomical sun position."""
        artifact = input_data.get("artifact") or self.agent.evidence_artifact
        await self.agent.update_sub_task("Auditing shadow vectors vs astronomical sun orientation...")

        exif = self.agent._tool_context.get("exif_extract", {})
        gps = exif.get("gps_coordinates")
        ts = exif.get("datetime_original")

        if not gps or not ts:
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
                    str(gps["latitude"]),
                    "--lon",
                    str(gps["longitude"]),
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
        await self.agent._record_tool_result("exif_extract", result)
        return result

    async def metadata_anomaly_score_handler(self, input_data: dict) -> dict:
        artifact = input_data.get("artifact") or self.agent.evidence_artifact
        await self.agent.update_sub_task("Auditing probabilistic metadata fabrication (ML)...")
        result = await run_ml_tool("metadata_anomaly_scorer.py", artifact.file_path, timeout=15.0)
        if result.get("error") or not result.get("available", True):
            exif = self.agent._tool_context.get("exif_extract") or await real_exif_extract(artifact=artifact)
            absent = exif.get("absent_mandatory_fields", []) if isinstance(exif, dict) else []
            total_fields = int(exif.get("total_fields_extracted", 0) or 0) if isinstance(exif, dict) else 0
            score = 0.15
            if total_fields == 0:
                score = 0.35
            elif len(absent) >= 5:
                score = 0.45
            result = {
                "available": True,
                "degraded": True,
                "court_defensible": False,
                "anomaly_score": score,
                "is_anomalous": score >= 0.6,
                "anomalous_fields": absent[:8],
                "confidence": max(0.55, 1.0 - score),
                "note": "ML metadata scorer unavailable; used deterministic EXIF completeness fallback.",
            }
        await self.agent._record_tool_result("metadata_anomaly_score", result)
        return result

    async def gps_timezone_validate_handler(self, input_data: dict) -> dict:
        artifact = input_data.get("artifact") or self.agent.evidence_artifact
        exif = self.agent._tool_context.get("exif_extract")
        if not exif:
             exif = await real_exif_extract(artifact=artifact)

        gps = exif.get("gps_coordinates")
        ts = exif.get("datetime_original")
        if not gps or not ts:
            result = {
                "available": False,
                "not_applicable": True,
                "reason": "GPS-timezone validation requires both GPS coordinates and EXIF capture timestamp.",
                "confidence": 0.0,
                "court_defensible": False,
            }
            await self.agent._record_tool_result("gps_timezone_validate", result)
            return result

        result = await real_gps_timezone_validate(gps_lat=gps["latitude"], gps_lon=gps["longitude"], timestamp_utc=ts)
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
        await self.agent.update_sub_task("Auditing C2PA provenance manifest and blockchain signatures...")
        result = await real_provenance_chain_verify(artifact=artifact)
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
            match = stored is not None and computed == stored
            result = {
                "computed_hash": computed,
                "stored_hash": stored,
                "hash_match": match,
                "available": True,
                "confidence": 1.0,
                "court_defensible": True,
            }
        except Exception as exc:
            result = {"available": False, "error": str(exc), "confidence": 0.0, "court_defensible": False}
        await self.agent._record_tool_result("file_hash_verify", result)
        return result

    async def compression_risk_audit_handler(self, input_data: dict) -> dict:
        """Audits metadata for social media/chat app compression footprints."""
        await self.agent.update_sub_task("Auditing for social media compression footprints...")

        exif = self.agent._tool_context.get("exif_extract", {})
        sw = str(exif.get("software", "")).lower()
        make = str(exif.get("make", "")).lower()
        model = str(exif.get("model", "")).lower()

        # Social Media / Heavy Compression apps
        # These apps strip forensic noise and resize images heavily, making
        # standard ELA/PRNU/Noise analysis unreliable.
        social_apps = {"instagram", "tiktok", "facebook", "snapchat", "twitter", "x.com"}
        chat_apps = {"whatsapp", "telegram", "imessage", "signal", "viber"}

        penalty = 1.0
        platform = None

        if any(x in sw or x in make or x in model for x in social_apps):
            penalty = 0.45
            platform = "Social Media (High Compression)"
        elif any(x in sw or x in make or x in model for x in chat_apps):
            penalty = 0.65
            platform = "Messaging App (Medium Compression)"

        result = {
            "available": True,
            "compression_risk": 1.0 - penalty if penalty < 1.0 else 0.0,
            "compression_penalty": penalty,
            "detected_platform": platform,
            "forensic_reliability_impact": "HIGH" if penalty < 0.5 else ("MEDIUM" if penalty < 1.0 else "NONE"),
            "confidence": 0.85,
            "court_defensible": True,
        }

        await self.agent._record_tool_result("compression_risk_audit", result)
        return result
