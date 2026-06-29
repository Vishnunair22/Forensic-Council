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
        "neural_ela": 0.55,  # P1b: heuristic (multi-quality resave), was 1.0 — kept ≤0.6
        "noiseprint_cluster": 0.55,
        "neural_copy_move": 0.95,  # real BusterNet path (research-gated)
        "neural_splicing": 0.95,  # real TruFor path (research-gated)
        "anomaly_tracer": 0.90,  # real ManTra-Net path (research-gated)
        "f3_net_frequency": 0.70,  # real F3-Net path (research-gated)
        "diffusion_artifact_detector": 0.65,  # real ViT sdxl-detector path (research-gated)
        "ela_full_image": 0.60,  # P1b: classical ELA heuristic, 0.65 → 0.60 (≤0.6 heuristic cap)
        "jpeg_ghost_detect": 0.60,
        "noise_fingerprint": 0.60,
        "frequency_domain_analysis": 0.60,  # P1b: classical FFT probe (heuristic), 0.70 → 0.60
        "codec_fingerprint": 0.60,
        # P1b: synthid_watermark_detect is NOT true SynthID — a metadata + frequency
        # probe (see capability_manifest). Explicitly capped at 0.50 so its high
        # self-reported confidences can never carry strong-signal weight.
        "synthid_watermark_detect": 0.50,
        # ML-based / Neural (medium-high weight)
        "voice_clone_detect": 0.85,  # real ECAPA embedding model — kept
        "anti_spoofing_detect": 0.85,  # real AASIST path — kept
        "speaker_diarize": 0.75,  # real SpeechBrain ECAPA — kept
        "optical_flow_analyze": 0.60,  # P1b: OpenCV Farneback heuristic, 0.80 → 0.60
        "face_swap_detect": 0.55,  # P1b: Haar cascade + FFT, not a trained model, 0.85 → 0.55
        "yolo_object_detection": 0.80,  # real DETR-ResNet-50 — kept
        "lighting_consistency": 0.60,  # P1b: edge/shadow-angle heuristic, 0.75 → 0.60
        "lighting_correlator": 0.60,  # P1b: grid edge/shadow-angle heuristic, 0.80 → 0.60
        "interframe_forgery_detector": 0.60,  # P1b: flow + SSIM heuristic, 0.75 → 0.60
        "scene_incongruence": 0.60,  # P1b: heuristic scene check, 0.65 → 0.60
        "vector_contraband_search": 0.80,  # real SigLIP embedding search — kept
        "copy_move_detect": 0.55,
        "splicing_detect": 0.55,
        "ai_text_detector": 0.65,  # statistical AI-text screening
        "audio_splice_detect": 0.60,  # P1b: MFCC/spectral-delta heuristic, 0.75 → 0.60
        "rolling_shutter_validation": 0.60,  # P1b: classical CV heuristic, 0.75 → 0.60
        "adversarial_robustness_check": 0.60,  # P1b: heuristic perturbation probe, 0.70 → 0.60
        "vfi_error_map": 0.60,  # P1b: frame-residual heuristic (no model), 0.85 → 0.60
        "thumbnail_coherence": 0.60,  # P1b: dHash perceptual-hash heuristic, 0.75 → 0.60
        "av_sync_verify": 0.60,  # P1b: envelope correlation, not a sync model, 0.80 → 0.60
        "compression_risk_audit": 0.60,  # P1b: EXIF/filename string heuristic, 0.85 → 0.60
        # Heuristic / metadata (lower weight)
        "exif_extract": 0.5,
        "metadata_anomaly_score": 0.50,  # P1b: 5-row IsolationForest, statistically weak, 0.65 → 0.50
        "steganography_scan": 0.5,
        "hex_signature_scan": 0.5,
        "gps_timezone_validate": 0.5,
        "timestamp_analysis": 0.5,
        "scale_validation": 0.6,
        "camera_profile_match": 0.55,  # P1b: plausible-range check, no device DB, 0.65 → 0.55
        "provenance_chain_verify": 0.60,  # P1b: c2pa byte-string scan, no crypto validation, 0.75 → 0.60
        "device_fingerprint_db": 0.55,
        "reverse_image_search": 0.50,
        "astronomical_api": 0.55,
        "perceptual_hash": 0.60,
        "gemini_deep_forensic": 0.85,
        "analyze_image_content": 0.40,
        "extract_text_from_image": 0.40,
        "ocr_analysis": 0.40,
    }

    # P1b prep — weight provenance. EVERY weight above is an unsourced engineering
    # default (no labelled-benchmark AUC behind it). When Phase 1 calibration runs,
    # replace "engineering_default" with the benchmark citation and fill measured_auc;
    # report builders may disclose this dict verbatim.
    WEIGHT_PROVENANCE: dict[str, dict[str, object]] = {
        _t: {"source": "engineering_default", "measured_auc": None}
        for _t in TOOL_RELIABILITY_TIERS
    }

    DEFAULT_TOOL_RELIABILITY = 0.50

    # --- Scoring Constants ---
    SINGLE_SIGNAL_DECAY: float = 0.55
    MANIP_PROBABILITY_CAP: float = 0.95
    DEEP_ANALYSIS_BONUS: float = 1.05

    # --- Verdict Thresholds (Overall) ---
    MANIPULATED_PROB_THRESHOLD = 0.75
    LIKELY_MANIPULATED_PROB_THRESHOLD = 0.60
    SUSPICIOUS_PROB_THRESHOLD = 0.50
    MANIP_SIGNAL_MIN_REQUIRED = 2  # Min direct signals for "MANIPULATED"

    # ── P0.4 — tiered single-signal rule ────────────────────────────────────────
    # The old flat 0.45 single-signal cap made the documented 0.85 gate unreachable
    # dead logic. Now SINGLE_SIGNAL_MANIP_THRESHOLD is actually consulted (in
    # arbiter_verdict.calculate_manipulation_probability): a SINGLE signal from a
    # HIGH_RELIABILITY_TOOLS member with confidence >= this threshold may reach
    # SUSPICIOUS-level probability (capped at SINGLE_SIGNAL_HIGH_RELIABILITY_CAP);
    # a single signal from any other tool stays capped at SINGLE_SIGNAL_DEFAULT_CAP
    # and needs a corroborator from a DIFFERENT signal family to go higher.
    SINGLE_SIGNAL_MANIP_THRESHOLD: float = 0.75
    SINGLE_SIGNAL_HIGH_RELIABILITY_CAP: float = 0.65
    SINGLE_SIGNAL_DEFAULT_CAP: float = 0.55

    # Tools whose REAL-model path is reliable enough that a lone, very-high-confidence
    # positive can stand on its own (TruFor, BusterNet, the ViT AI-gen detector,
    # cryptographic hash mismatch, AASIST / wav2vec2 audio deepfake). NOTE: the
    # neural_* entries are research-gated — when the gate is off they run classical
    # fallbacks (disclosed in the capability manifest); their fallback findings carry
    # lower confidences in practice, and the >=0.85 confidence gate is the guard.
    HIGH_RELIABILITY_TOOLS: frozenset[str] = frozenset({
        "neural_splicing", "trufor",                      # TruFor (real-model path)
        "neural_copy_move",                                # BusterNet (real-model path)
        "ai_generation_detector", "diffusion_artifact_detector",  # ViT AI-gen detector
        "file_hash_verify",                                # SHA-256 custody mismatch
        "anti_spoofing_detect", "anti_spoofing_deep_ensemble",    # AASIST
        "audio_gen_signature",                             # wav2vec2 deepfake fine-tune
    })

    AUTHENTIC_CONF_THRESHOLD = 0.70  # Lowered from 0.75 to prevent real images from getting stuck in INCONCLUSIVE
    AUTHENTIC_ERROR_MAX = 0.20       # Slightly increased to tolerate minor tool timeouts on real images
    LIKELY_AUTHENTIC_CONF_THRESHOLD = 0.55
    LIKELY_AUTHENTIC_ERROR_MAX = 0.35

    ABSTAIN_CONF_FLOOR = 0.35
    ABSTAIN_ERROR_CEILING = 0.55

    # WS-3 #11 / P0.3 — signal families. Detectors in the same family respond to the
    # SAME underlying artifact (e.g. ELA/JPEG-ghost/classical-FFT all fire on
    # recompression), so they must be fused as one signal, not counted independently.
    # Families: compression_artifact, boundary_splice, copy_move, generative,
    # frequency, metadata, semantic_llm, provenance, audio_spectral, temporal_video
    # (plus narrow singleton families for tools that fit none). Unlisted tools each
    # form their own family (see signal_family()), which is the safe default.
    SIGNAL_FAMILIES: dict[str, str] = {
        # compression_artifact — all co-fire on JPEG/codec recompression. The
        # classical FFT probe (frequency_domain_analysis) stays here, NOT in
        # "frequency": it responds to JPEG blocking grids, the same artifact as ELA.
        "ela_full_image": "compression_artifact", "neural_ela": "compression_artifact",
        "error_level_analysis": "compression_artifact",
        "jpeg_ghost_detect": "compression_artifact", "noise_fingerprint": "compression_artifact",
        "frequency_domain_analysis": "compression_artifact",
        "compression_artifact_analysis": "compression_artifact",
        "codec_fingerprint": "compression_artifact", "codec_fingerprinting": "compression_artifact",
        "compression_risk_audit": "compression_artifact",
        "noiseprint_cluster": "compression_artifact", "noiseprint_clustering": "compression_artifact",
        # frequency — spectral GAN/deepfake-fingerprint detectors (generative-artifact
        # oriented, distinct mechanism from the recompression probes above)
        "f3_net_frequency": "frequency", "deepfake_frequency_check": "frequency",
        # boundary_splice — splice-boundary / noise-inconsistency localisation
        "splicing_detect": "boundary_splice", "neural_splicing": "boundary_splice",
        "trufor": "boundary_splice", "splicing_detector": "boundary_splice",
        "anomaly_tracer": "boundary_splice",
        # copy_move — internal region duplication
        "copy_move_detect": "copy_move", "neural_copy_move": "copy_move",
        "copy_move_detector": "copy_move",
        # generative — whole-image/face synthesis detectors
        "diffusion_artifact_detector": "generative", "ai_generation_detector": "generative",
        "synthid_watermark_detect": "generative", "face_swap_detection": "generative",
        "face_swap_detect": "generative", "face_swap_detect_deepface": "generative",
        "ai_text_detector": "generative",
        # temporal_video — inter-frame / motion consistency
        "optical_flow_analysis": "temporal_video", "optical_flow_analyze": "temporal_video",
        "frame_consistency_analysis": "temporal_video",
        "interframe_forgery_detector": "temporal_video",
        "rolling_shutter_validation": "temporal_video", "vfi_error_map": "temporal_video",
        "av_sync_verify": "temporal_video", "audio_visual_sync": "temporal_video",
        # audio_spectral — voice synthesis/spoof/splice detectors
        "voice_clone_detect": "audio_spectral", "anti_spoofing_detect": "audio_spectral",
        "audio_gen_signature": "audio_spectral", "audio_splice_detect": "audio_spectral",
        "voice_clone_deep_ensemble": "audio_spectral",
        "anti_spoofing_deep_ensemble": "audio_spectral", "neural_prosody": "audio_spectral",
        "speaker_diarize": "audio_spectral",
        # metadata — EXIF/container field consistency
        "exif_extract": "metadata", "exif_isolation_forest": "metadata",
        "metadata_anomaly_score": "metadata", "timestamp_analysis": "metadata",
        "gps_timezone_validate": "metadata", "camera_profile_match": "metadata",
        "device_fingerprint_db": "metadata", "video_metadata": "metadata",
        "mediainfo_profile": "metadata", "thumbnail_coherence": "metadata",
        # provenance — file identity / chain-of-custody / origin
        "provenance_chain_verify": "provenance", "file_hash_verify": "provenance",
        "hash_verify": "provenance", "custody_check": "provenance",
        "file_structure_analysis": "provenance", "hex_signature_scan": "provenance",
        "av_file_identity": "provenance", "reverse_image_search": "provenance",
        "perceptual_hash": "provenance",
        # semantic_llm — scene/content semantics (vision-LLM, embedding and
        # physics/geometry plausibility checks)
        "object_detection": "semantic_llm", "yolo_object_detection": "semantic_llm",
        "scene_incongruence": "semantic_llm", "lighting_consistency": "semantic_llm",
        "lighting_correlator": "semantic_llm", "vector_contraband_search": "semantic_llm",
        "scale_validation": "semantic_llm", "astronomical_api": "semantic_llm",
        "gemini_deep_forensic": "semantic_llm", "analyze_image_content": "semantic_llm",
        "extract_text_from_image": "semantic_llm", "ocr_analysis": "semantic_llm",
        "visual_evidence_profile": "semantic_llm", "screenshot_layout_forensics": "semantic_llm",
        "read_shared_image_context": "semantic_llm",
        # singleton families — fit none of the canonical buckets
        "steganography_scan": "steganography",
        "adversarial_robustness_check": "adversarial",
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
