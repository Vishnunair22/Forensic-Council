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
from tools.metadata_tools import gps_timezone_validate as real_gps_timezone_validate
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
        except Exception:
            pass

        # Fallback to standard anomaly score
        await self.agent.update_sub_task("Isolation Forest unavailable — falling back to standard anomaly score...")
        return await self.metadata_anomaly_score_handler(input_data)

    # ── Refinement: Astro Grounding ────────────────────────────────────

    async def astro_grounding_handler(self, input_data: dict) -> dict:
        """[REFINED] Verifies shadow direction against astronomical sun position."""
        artifact = input_data.get("artifact") or self.agent.evidence_artifact
        await self.agent.update_sub_task("Auditing shadow vectors vs astronomical sun orientation...")

        exif = self.agent._tool_context.get("exif_extract", {})
        gps = exif.get("gps_coordinates")
        ts = exif.get("datetime_original")

        if not gps or not ts:
            return {"available": False, "note": "Astro grounding requires valid GPS and Timestamp in EXIF."}

        try:
            result = await run_ml_tool("astro_grounding_engine.py", artifact.file_path,
                                     extra_args=["--lat", str(gps['latitude']), "--lon", str(gps['longitude']), "--time", str(ts)],
                                     timeout=15.0)

            if not result.get("error") and result.get("available"):
                await self.agent._record_tool_result("astro_grounding", result)
                return result
        except Exception:
            pass

        return {"available": False, "note": "Astro grounding engine failed or analytical model unavailable."}

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
        await self.agent._record_tool_result("metadata_anomaly_score", result)
        return result

    async def gps_timezone_validate_handler(self, input_data: dict) -> dict:
        artifact = input_data.get("artifact") or self.agent.evidence_artifact
        exif = self.agent._tool_context.get("exif_extract")
        if not exif:
             exif = await real_exif_extract(artifact=artifact)

        gps = exif.get("gps_coordinates")
        ts = exif.get("datetime_original")
        if not gps or not ts: return {"available": False}

        return await real_gps_timezone_validate(gps_lat=gps["latitude"], gps_lon=gps["longitude"], timestamp_utc=ts)

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
            }
        except Exception as exc:
            result = {"available": False, "error": str(exc)}
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
        
        # Social Media / Heavy Compression apps
        # These apps strip forensic noise and resize images heavily, making 
        # standard ELA/PRNU/Noise analysis unreliable.
        SOCIAL_APPS = {"instagram", "tiktok", "facebook", "snapchat", "twitter", "x.com"}
        CHAT_APPS = {"whatsapp", "telegram", "imessage", "signal", "viber"}
        
        penalty = 1.0
        platform = None
        
        if any(x in sw or x in make or x in model for x in SOCIAL_APPS):
            penalty = 0.45
            platform = "Social Media (High Compression)"
        elif any(x in sw or x in make or x in model for x in CHAT_APPS):
            penalty = 0.65
            platform = "Messaging App (Medium Compression)"
            
        result = {
            "available": True,
            "compression_risk": 1.0 - penalty if penalty < 1.0 else 0.0,
            "compression_penalty": penalty,
            "detected_platform": platform,
            "forensic_reliability_impact": "HIGH" if penalty < 0.5 else ("MEDIUM" if penalty < 1.0 else "NONE")
        }
        
        await self.agent._record_tool_result("compression_risk_audit", result)
        return result
