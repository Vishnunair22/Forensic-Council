"""
Forensic Policy & Thresholds
===========================

Centralized registry for all forensic scoring constants, tool reliability
tiers, and verdict thresholds. This ensures consistency between the
Arbiter's overall deliberation and the per-agent summaries.
"""


class ForensicPolicy:
    """
    Centralised registry for forensic criteria and reliability weights.
    """

    # --- Tool Reliability Tiers ---
    # Maps tool names to their base reliability weight (0.0 to 1.0)
    TOOL_RELIABILITY_TIERS: dict[str, float] = {
        # Calibrated / Neural High-Recall (highest weight)
        "neural_ela": 1.0,
        "noiseprint_cluster": 1.0,
        "neural_copy_move": 0.95,
        "neural_splicing": 0.95,
        "anomaly_tracer": 0.90,
        "f3_net_frequency": 0.90,
        "diffusion_artifact_detector": 0.95,
        "ela_full_image": 1.0,
        "jpeg_ghost_detect": 1.0,
        "noise_fingerprint": 1.0,
        "frequency_domain_analysis": 1.0,
        "codec_fingerprint": 1.0,

        # ML-based / Neural (medium-high weight)
        "voice_clone_detect": 0.85,
        "anti_spoofing_detect": 0.85,
        "speaker_diarize": 0.75,
        "optical_flow_analyze": 0.80,
        "face_swap_detect": 0.85,
        "object_detection": 0.80,
        "lighting_consistency": 0.75,
        "lighting_correlator": 0.80,
        "interframe_forgery_detector": 0.75,
        "scene_incongruence": 0.65,
        "vector_contraband_search": 0.80,
        "copy_move_detect": 0.75,
        "splicing_detect": 0.75,
        "audio_splice_detect": 0.75,
        "rolling_shutter_validation": 0.75,
        "adversarial_robustness_check": 0.70,
        "vfi_error_map": 0.85,
        "thumbnail_coherence": 0.75,
        "av_sync_verify": 0.80,

        # Heuristic / metadata (lower weight)
        "exif_extract": 0.5,
        "metadata_anomaly_score": 0.65,
        "steganography_scan": 0.5,
        "hex_signature_scan": 0.5,
        "gps_timezone_validate": 0.5,
        "timestamp_analysis": 0.5,
        "scale_validation": 0.6,
        "camera_profile_match": 0.65,
        "provenance_chain_verify": 0.75,
        "device_fingerprint_db": 0.55,
        "reverse_image_search": 0.50,
        "astronomical_api": 0.55,
        "perceptual_hash": 0.60,
        "gemini_deep_forensic": 0.85,
        "analyze_image_content": 0.40,
        "extract_text_from_image": 0.40,
        "ocr_analysis": 0.40,
    }

    DEFAULT_TOOL_RELIABILITY = 0.65

    # --- Scoring Constants ---
    SINGLE_SIGNAL_DECAY: float = 0.55
    MANIP_PROBABILITY_CAP: float = 0.95
    DEEP_ANALYSIS_BONUS: float = 1.15

    # --- Verdict Thresholds (Overall) ---
    MANIPULATED_PROB_THRESHOLD = 0.72
    LIKELY_MANIPULATED_PROB_THRESHOLD = 0.55
    SUSPICIOUS_PROB_THRESHOLD = 0.45
    MANIP_SIGNAL_MIN_REQUIRED = 2  # Min direct signals for "MANIPULATED"

    AUTHENTIC_CONF_THRESHOLD = 0.75  # Higher bar for absolute "AUTHENTIC"
    AUTHENTIC_ERROR_MAX = 0.15
    LIKELY_AUTHENTIC_CONF_THRESHOLD = 0.60
    LIKELY_AUTHENTIC_ERROR_MAX = 0.25

    ABSTAIN_CONF_FLOOR = 0.40
    ABSTAIN_ERROR_CEILING = 0.50

    # --- Per-Agent Summary Thresholds ---
    # Synchronised with overall thresholds to prevent UI/Report dissonance.
    AGENT_AUTHENTIC_CONF = 0.75  # Was 0.70 (fixed inconsistency)
    AGENT_AUTHENTIC_ERR = 0.15
    AGENT_SUSPICIOUS_CONF = 0.45
    AGENT_SUSPICIOUS_ERR = 0.40

    @classmethod
    def get_tool_weight(cls, tool_name: str) -> float:
        """Get the reliability weight for a tool."""
        return cls.TOOL_RELIABILITY_TIERS.get(
            tool_name.lower().replace(" ", "_"), cls.DEFAULT_TOOL_RELIABILITY
        )

    @classmethod
    def is_authentic(cls, confidence: float, error_rate: float) -> bool:
        """Check if metrics meet the AUTHENTIC threshold."""
        return confidence >= cls.AGENT_AUTHENTIC_CONF and error_rate <= cls.AGENT_AUTHENTIC_ERR

    @classmethod
    def is_suspicious(cls, confidence: float, error_rate: float) -> bool:
        """Check if metrics meet the SUSPICIOUS threshold."""
        return confidence < cls.AGENT_SUSPICIOUS_CONF and error_rate > cls.AGENT_SUSPICIOUS_ERR
