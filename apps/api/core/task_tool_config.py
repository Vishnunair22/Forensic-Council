"""
Task-to-Tool Mapping Loader
============================

Loads task→tool override mappings from config/task_tool_overrides.yaml.
Provides a single source of truth for the ReAct loop engine's task-to-tool
matching, replacing the hardcoded 150+ entry dict previously in react_loop.py.

Also provides the MIME-type → allowed tool names matrix used by base_agent to
filter the tool registry before building the LLM system prompt.  Tools absent
from a MIME group's allow-list are stripped so the LLM can never suggest a tool
that is semantically wrong for the current evidence type.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

from core.structured_logging import get_logger

logger = get_logger(__name__)

# ---------------------------------------------------------------------------
# MIME-type → allowed tool names matrix (Fix 2)
# ---------------------------------------------------------------------------
# Keys are MIME prefix strings matched via startswith().  The special key "*"
# is the universal fallback used by agents that support all types (e.g. Agent 5).
# Values are frozensets of tool names that make sense for that evidence class.
# Tools not in the set for the active MIME are excluded from the LLM prompt.
# ---------------------------------------------------------------------------

_IMAGE_TOOLS: frozenset[str] = frozenset(
    {
        # Core image integrity
        "ela_full_image",
        "ela_anomaly_classify",
        "neural_ela",
        "roi_extract",
        "jpeg_ghost_detect",
        "frequency_domain_analysis",
        "splicing_detect",
        "noise_fingerprint",
        "noiseprint_cluster",
        "deepfake_frequency_check",
        "neural_fingerprint",
        "neural_copy_move",
        "neural_splicing",
        "anomaly_tracer",
        "diffusion_artifact_detector",
        "synthid_watermark_detect",
        "f3_net_frequency",
        "f3net_frequency",
        "adversarial_robustness_check",
        # Content understanding
        "analyze_image_content",
        "extract_text_from_image",
        "visual_evidence_profile",
        "gemini_deep_forensic",  # deprecated compatibility alias
        "read_shared_image_context",
        # Hash / integrity
        "file_hash_verify",
        # Scene / object (Agent 3 also applies to images)
        "object_detection",
        "scene_incongruence",
        "lighting_consistency",
        "contraband_database",
        "screenshot_scene_applicability",
        "screenshot_layout_forensics",
        "secondary_classification",
        "scale_validation",
        # Metadata tools that apply to images
        "exif_extract",
        "file_structure_analysis",
        "hex_signature_scan",
        "compression_risk_audit",
        "timestamp_analysis",
        "metadata_anomaly_score",
        "exif_isolation_forest",
        "provenance_chain_verify",
        "camera_profile_match",
        "astro_grounding",
        "gps_timezone_validate",
        "steganography_scan",
        "prnu_sensor_verification",
    }
)

_AUDIO_TOOLS: frozenset[str] = frozenset(
    {
        "speaker_diarize",
        "neural_prosody",
        "audio_gen_signature",
        "voice_clone_detect",
        "voice_clone_deep_ensemble",
        "anti_spoofing_detect",
        "anti_spoofing_deep_ensemble",
        "codec_fingerprinting",
        "prosody_analyze",
        "audio_splice_detect",
        "enf_analysis",
        "background_noise_analysis",
        "read_shared_image_context",
        # Hash / file integrity always applicable
        "file_hash_verify",
        "file_structure_analysis",
        "hex_signature_scan",
        "compression_risk_audit",
        "av_file_identity",
        "mediainfo_profile",
    }
)

_VIDEO_TOOLS: frozenset[str] = frozenset(
    {
        # Temporal
        "video_metadata",
        "vfi_error_map",
        "thumbnail_coherence",
        "frame_consistency_analysis",
        "optical_flow_analysis",
        "interframe_forgery_detector",
        "frame_extraction",
        "face_swap_detection",
        "deepfake_frequency_check",
        "rolling_shutter_validation",
        "compression_artifact_analysis",
        "adversarial_robustness_check",
        # Audio track on video
        "speaker_diarize",
        "audio_visual_sync",
        "neural_prosody",
        "audio_gen_signature",
        "voice_clone_detect",
        "anti_spoofing_detect",
        "codec_fingerprinting",
        "audio_splice_detect",
        "enf_analysis",
        # Object / scene
        "object_detection",
        "scene_incongruence",
        "lighting_consistency",
        # General
        "read_shared_image_context",
        "file_hash_verify",
        "file_structure_analysis",
        "hex_signature_scan",
        "compression_risk_audit",
        "av_file_identity",
        "mediainfo_profile",
        "inter_agent_call",
    }
)

_DOCUMENT_TOOLS: frozenset[str] = frozenset(
    {
        "extract_text_from_image",
        "extract_evidence_text",
        "file_hash_verify",
        "file_structure_analysis",
        "hex_signature_scan",
        "compression_risk_audit",
        "timestamp_analysis",
        "provenance_chain_verify",
        "visual_evidence_profile",
        "gemini_deep_forensic",  # deprecated compatibility alias
        "read_shared_image_context",
    }
)

# Agent 5 supports every file type; this is the union of all tools.
_UNIVERSAL_TOOLS: frozenset[str] = (
    _IMAGE_TOOLS | _AUDIO_TOOLS | _VIDEO_TOOLS | _DOCUMENT_TOOLS
)

# Tools that are always allowed regardless of MIME type (agent infrastructure).
_ALWAYS_ALLOWED: frozenset[str] = frozenset(
    {
        "file_hash_verify",
        "inter_agent_call",
        "visual_evidence_profile",
        "gemini_deep_forensic",  # deprecated compatibility alias
        "read_shared_image_context",
    }
)

# MIME prefix → frozenset of allowed tool names
MIME_TOOL_MATRIX: dict[str, frozenset[str]] = {
    "image/": _IMAGE_TOOLS,
    "audio/": _AUDIO_TOOLS,
    "video/": _VIDEO_TOOLS,
    "application/pdf": _DOCUMENT_TOOLS,
    "text/": _DOCUMENT_TOOLS,
    "application/msword": _DOCUMENT_TOOLS,
    "application/vnd.openxmlformats-officedocument": _DOCUMENT_TOOLS,
    "application/vnd.ms-": _DOCUMENT_TOOLS,
    "*": _UNIVERSAL_TOOLS,
}


def get_allowed_tools_for_mime(mime_type: str | None) -> frozenset[str]:
    """Return the frozenset of tool names allowed for the given MIME type.

    Matches are tried longest-prefix-first so ``application/pdf`` wins over
    ``application/``.  Falls back to ``_UNIVERSAL_TOOLS`` for unknown types.
    """
    if not mime_type:
        return _UNIVERSAL_TOOLS

    lower = mime_type.lower()
    # Try prefixes ordered by length (longest first) for specificity.
    for prefix in sorted(MIME_TOOL_MATRIX.keys(), key=len, reverse=True):
        if prefix == "*":
            continue
        if lower.startswith(prefix):
            return MIME_TOOL_MATRIX[prefix] | _ALWAYS_ALLOWED

    return _UNIVERSAL_TOOLS

_CONFIG_PATH = Path(__file__).resolve().parent.parent / "config" / "task_tool_overrides.yaml"

# Loaded once at module import; cached for the process lifetime.
_task_tool_overrides: dict[str, str] | None = None


def _load_overrides() -> dict[str, str]:
    """Load and merge all sections from the YAML config into a flat dict."""
    if not _CONFIG_PATH.exists():
        logger.warning(
            "task_tool_overrides.yaml not found — "
            "task-to-tool matching will fall back to substring matching",
            config_path=str(_CONFIG_PATH),
        )
        return {}

    with open(_CONFIG_PATH, encoding="utf-8") as fh:
        raw: dict[str, Any] = yaml.safe_load(fh) or {}

    merged: dict[str, str] = {}
    for _section_key, section_val in raw.items():
        if isinstance(section_val, dict):
            for task_phrase, tool_name in section_val.items():
                if isinstance(task_phrase, str) and isinstance(tool_name, str):
                    merged[task_phrase.lower()] = tool_name
    return merged


def get_task_tool_overrides() -> dict[str, str]:
    """Return the cached task→tool mapping dict."""
    global _task_tool_overrides
    if _task_tool_overrides is None:
        _task_tool_overrides = _load_overrides()
        logger.info(
            "Loaded task-to-tool override mappings from YAML config",
            count=len(_task_tool_overrides),
        )
    return _task_tool_overrides


def reload_overrides() -> dict[str, str]:
    """Force-reload from disk (useful for hot-reload or testing)."""
    global _task_tool_overrides
    _task_tool_overrides = None
    return get_task_tool_overrides()
