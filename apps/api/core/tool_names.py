"""
Tool name constants for consistent registry references.
Prevents key-mismatch bugs across agents.
"""

# Audio tool names
TOOL_VOICE_CLONE = "voice_clone_detect"
TOOL_ANTI_SPOOFING = "anti_spoofing_detect"
TOOL_ENF_ANALYSIS = "enf_analysis"
TOOL_AUDIO_SPLICE = "audio_splice_detect"

# Image tool names
TOOL_NEURAL_FINGERPRINT = "neural_fingerprint"
TOOL_NEURAL_ELA = "neural_ela"
TOOL_NOISE_FINGERPRINT = "noise_fingerprint"
TOOL_EXIF_ISOLATION = "exif_isolation_forest"

# Video tool names
TOOL_OPTICAL_FLOW = "optical_flow"
TOOL_INTERFRAME_FORGERY = "interframe_forgery_detect"
TOOL_ROLLING_SHUTTER = "rolling_shutter_validation"
TOOL_COMPRESSION_ARTIFACT = "compression_artifact_analysis"

# Metadata tool names
TOOL_C2PA_VALIDATOR = "c2pa_validator"
TOOL_METADATA_ANOMALY = "metadata_anomaly_scorer"
TOOL_HEX_SIGNATURE = "hex_signature"

# Shared visual evidence profile
TOOL_VISUAL_PROFILE = "visual_evidence_profile"

# Deprecated compatibility alias for persisted tasks/results created before
# native local-only mode was introduced. Do not schedule this tool in new runs.
TOOL_GEMINI_DEEP = "gemini_deep_forensic"

VISUAL_PROFILE_TOOL_NAMES = frozenset(
    {
        TOOL_VISUAL_PROFILE,
        TOOL_GEMINI_DEEP,
    }
)


def is_visual_profile_tool(tool_name: str | None) -> bool:
    return str(tool_name or "").strip() in VISUAL_PROFILE_TOOL_NAMES
