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
    # Maps tool names to their base reliability weight (0.0 to 1.0).
    #
    # P1.12 / audit C3 — UNSOURCED ENGINEERING DEFAULTS. None of these weights are
    # derived from a labelled forensic benchmark; they are hand-picked priors. They
    # MUST NOT be presented as validated reliabilities, and the report discloses this
    # alongside the calibration disclosure (is_system_uncalibrated → reliability note).
    # To make them defensible, fit them on a ground-truth corpus (P1.7) and replace
    # the values here with benchmark-cited numbers; until then they are indicative
    # weighting only. See WEIGHTS_ARE_VALIDATED.
    WEIGHTS_ARE_VALIDATED: bool = False
    TOOL_RELIABILITY_TIERS: dict[str, float] = {
        # WS-3 #13 — weights right-sized to the ACTUAL method. neural_ela and
        # codec_fingerprint were 1.0 despite being heuristics (multi-quality resave;
        # FFT codec probe) — indefensible. Research-gated neural tools (neural_copy_move,
        # neural_splicing, anomaly_tracer, f3_net, diffusion) keep their higher weight
        # only because the real model is loaded in this deployment; when gated off they
        # run a classical fallback, which the capability manifest discloses.
        "neural_ela": 0.55,
        "noiseprint_cluster": 0.55,
        "neural_copy_move": 0.95,
        "neural_splicing": 0.95,
        "anomaly_tracer": 0.90,
        "f3_net_frequency": 0.70,
        "diffusion_artifact_detector": 0.65,
        "ela_full_image": 0.65,
        "jpeg_ghost_detect": 0.60,
        "noise_fingerprint": 0.60,
        "frequency_domain_analysis": 0.70,
        "codec_fingerprint": 0.60,
        # ML-based / Neural (medium-high weight)
        "voice_clone_detect": 0.85,
        "anti_spoofing_detect": 0.85,
        "speaker_diarize": 0.75,
        "optical_flow_analyze": 0.80,
        "face_swap_detect": 0.85,
        "yolo_object_detection": 0.80,
        "lighting_consistency": 0.75,
        "lighting_correlator": 0.80,
        "interframe_forgery_detector": 0.75,
        "scene_incongruence": 0.65,
        "vector_contraband_search": 0.80,
        "copy_move_detect": 0.55,
        "splicing_detect": 0.55,
        "audio_splice_detect": 0.75,
        "rolling_shutter_validation": 0.75,
        "adversarial_robustness_check": 0.70,
        "vfi_error_map": 0.85,
        "thumbnail_coherence": 0.75,
        "av_sync_verify": 0.80,
        "compression_risk_audit": 0.85,
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

    DEFAULT_TOOL_RELIABILITY = 0.50

    # --- Scoring Constants ---
    SINGLE_SIGNAL_DECAY: float = 0.55
    MANIP_PROBABILITY_CAP: float = 0.95
    DEEP_ANALYSIS_BONUS: float = 1.15

    # --- Verdict Thresholds (Overall) ---
    MANIPULATED_PROB_THRESHOLD = 0.75
    LIKELY_MANIPULATED_PROB_THRESHOLD = 0.60
    SUSPICIOUS_PROB_THRESHOLD = 0.50
    MANIP_SIGNAL_MIN_REQUIRED = 2  # Min direct signals for "MANIPULATED"
    # SINGLE_SIGNAL_MANIP_THRESHOLD removed (P0.6): a solo signal is hard-capped at
    # 0.45 probability, so this 0.85 gate was unreachable dead logic. A proper tiered
    # single-signal rule (P1.9) requires validated tool weights (P1.12) first.

    AUTHENTIC_CONF_THRESHOLD = 0.70  # Lowered from 0.75 to prevent real images from getting stuck in INCONCLUSIVE
    AUTHENTIC_ERROR_MAX = 0.20       # Slightly increased to tolerate minor tool timeouts on real images
    LIKELY_AUTHENTIC_CONF_THRESHOLD = 0.55
    LIKELY_AUTHENTIC_ERROR_MAX = 0.35

    ABSTAIN_CONF_FLOOR = 0.35
    ABSTAIN_ERROR_CEILING = 0.55

    # --- Per-Agent Summary Thresholds ---
    AGENT_AUTHENTIC_CONF = 0.70
    AGENT_AUTHENTIC_ERR = 0.20
    AGENT_SUSPICIOUS_CONF = 0.50
    AGENT_SUSPICIOUS_ERR = 0.45

    # WS-3 #11 — signal families. Detectors in the same family respond to the SAME
    # underlying artifact (e.g. ELA/JPEG-ghost/frequency all fire on recompression),
    # so they must be fused as one signal, not counted independently. Unlisted tools
    # each form their own family (see signal_family()).
    SIGNAL_FAMILIES: dict[str, str] = {
        "ela_full_image": "compression", "neural_ela": "compression",
        "jpeg_ghost_detect": "compression", "noise_fingerprint": "compression",
        "frequency_domain_analysis": "compression", "f3_net_frequency": "compression",
        "compression_artifact_analysis": "compression", "noiseprint_cluster": "boundary",
        "splicing_detect": "boundary", "neural_splicing": "boundary",
        "copy_move_detect": "boundary", "neural_copy_move": "boundary",
        "anomaly_tracer": "boundary", "diffusion_artifact_detector": "generative",
        "synthid_watermark_detect": "generative", "deepfake_frequency_check": "generative",
        "ai_generation_detector": "generative", "face_swap_detection": "face",
        "optical_flow_analysis": "temporal", "frame_consistency_analysis": "temporal",
        "interframe_forgery_detector": "temporal", "rolling_shutter_validation": "temporal",
        "voice_clone_detect": "voice", "anti_spoofing_detect": "voice",
        "audio_gen_signature": "voice", "audio_splice_detect": "audio_boundary",
        "codec_fingerprint": "codec", "exif_extract": "metadata",
        "metadata_anomaly_score": "metadata", "provenance_chain_verify": "metadata",
        "timestamp_analysis": "metadata", "object_detection": "semantic",
        "scene_incongruence": "semantic", "lighting_consistency": "semantic",
        "lighting_correlator": "semantic", "vector_contraband_search": "semantic",
    }

    @classmethod
    def get_tool_weight(cls, tool_name: str) -> float:
        """Get the reliability weight for a tool."""
        return cls.TOOL_RELIABILITY_TIERS.get(
            tool_name.lower().replace(" ", "_"), cls.DEFAULT_TOOL_RELIABILITY
        )

    @classmethod
    def signal_family(cls, tool_name: str) -> str:
        """Family a tool's signal belongs to (WS-3 #11). Unknown tools each get a
        unique family so they are never wrongly fused with another signal."""
        key = tool_name.lower().replace(" ", "_")
        return cls.SIGNAL_FAMILIES.get(key, f"tool:{key}")

    @classmethod
    def is_authentic(cls, confidence: float, error_rate: float) -> bool:
        """Check if metrics meet the AUTHENTIC threshold."""
        return confidence >= cls.AGENT_AUTHENTIC_CONF and error_rate <= cls.AGENT_AUTHENTIC_ERR

    @classmethod
    def is_suspicious(cls, confidence: float, error_rate: float) -> bool:
        """Check if metrics meet the SUSPICIOUS threshold.

        NOTE: A finding can satisfy both is_authentic and is_suspicious when
        confidence >= 0.75 and error_rate is in (0.15, 0.40].  Callers must
        check is_authentic first and treat is_suspicious as a fallback tier.
        """
        # Suspicious = medium/high error rate but still some usable confidence
        return confidence >= cls.AGENT_SUSPICIOUS_CONF and error_rate > cls.AGENT_SUSPICIOUS_ERR

    @classmethod
    def get_verdict_thresholds(cls, mime_type: str = "") -> dict[str, float]:
        """Return verdict thresholds adjusted for file type.

        Lossless formats (PNG, BMP, GIF, WebP) have higher baselines for
        manipulation probability due to common compression artifacts that
        can trigger false positives in frequency-domain and ELA analysis.
        """
        if mime_type in ("image/png", "image/webp", "image/bmp", "image/gif"):
            return {
                "manipulated": 0.85,
                "likely_manipulated": 0.70,
                "suspicious": 0.55,
                "authentic_conf": 0.80,
                "likely_authentic_conf": 0.65,
            }
        return {
            "manipulated": cls.MANIPULATED_PROB_THRESHOLD,
            "likely_manipulated": cls.LIKELY_MANIPULATED_PROB_THRESHOLD,
            "suspicious": cls.SUSPICIOUS_PROB_THRESHOLD,
            "authentic_conf": cls.AUTHENTIC_CONF_THRESHOLD,
            "likely_authentic_conf": cls.LIKELY_AUTHENTIC_CONF_THRESHOLD,
        }
