"""Capability Manifest (audit WS-1 #1).

Per-investigation, court-grade record of WHAT actually analysed the evidence:
for every applicable tool — did it run, fail, get gated off, or have its model
unavailable, and what method/model/license actually executed. Embedded in the
signed report and surfaced in the UI so a reader is never misled into treating a
silently-degraded or heuristic analysis as a full neural forensic examination.

This single structure addresses the audit's M2 (research-models-off swaps neural
tools for heuristics under unchanged names), M3 (model-load failure counted as
"no anomaly"), M4 (Gemini-off silent degradation) and C9 (per-type degradation).

Method classification (audit §3):
  REAL_ML   — loads real trained weights
  HEURISTIC — classical CV / DSP / statistics
  WRAPPER   — exiftool / PIL / ffprobe / byte-signature
  LLM       — Gemini / Groq used as a tool
"""

from __future__ import annotations

import contextvars
from typing import Any

REAL_ML = "REAL_ML"
HEURISTIC = "HEURISTIC"
WRAPPER = "WRAPPER"
LLM = "LLM"

# Spec'd per-run execution statuses (plan item 0.6). The legacy "status" field
# keeps its historical vocabulary (ran/failed/not_applicable/gated_off/
# model_unavailable) for existing consumers; "execution_status" maps
# not_applicable -> skipped_by_routing to match the plan's vocabulary.
STATUS_RAN = "ran"
STATUS_FAILED = "failed"
STATUS_GATED_OFF = "gated_off"
STATUS_MODEL_UNAVAILABLE = "model_unavailable"
STATUS_SKIPPED_BY_ROUTING = "skipped_by_routing"

# Placeholder for measured per-tool reliability metrics. Phase-1 calibration
# fills these from labelled-benchmark sweeps; until then they render as
# "not yet measured" in the report's Methodology section.
EMPTY_TOOL_METRICS: dict[str, Any] = {
    "tpr": None,
    "fpr": None,
    "threshold": None,
    "validation_dataset": None,
}


# ── 0.10 Truthful tool naming ────────────────────────────────────────────────
# tool -> {"neural_method": what the name implies, "heuristic_method": what
# actually runs when the trained weights are gated off / unavailable / never
# shipped}. Tools whose neural variant does not exist in this deployment have
# an empty neural_method — their heuristic_method is ALWAYS the actual method.
TOOL_METHOD_DISCLOSURE: dict[str, dict[str, str]] = {
    "trufor": {
        "neural_method": "TruFor SegFormer-B2 trained weights",
        "heuristic_method": "SRM-filter residual heuristic approximation (TruFor weights not loaded)",
    },
    "busternet": {
        "neural_method": "BusterNet trained CNN copy-move weights",
        "heuristic_method": "ORB keypoints + RANSAC geometric matching (BusterNet weights not loaded)",
    },
    "f3_net": {
        "neural_method": "F3-Net trained frequency-aware CNN weights",
        "heuristic_method": "Haar DWT + FFT heuristic — neural weights not loaded",
    },
    "mantra": {
        "neural_method": "ManTra-Net trained anomaly-localization weights",
        "heuristic_method": "statistical One-Class SVM anomaly screen (ManTra-Net weights not loaded)",
    },
    "neural_ela": {
        "neural_method": "",
        "heuristic_method": "multi-quality JPEG resave + per-image IsolationForest (no neural ELA model in this deployment)",
    },
    "ela_anomaly_classifier": {
        "neural_method": "",
        "heuristic_method": "per-image IsolationForest over ELA statistics (no trained classifier)",
    },
    "noiseprint_cluster": {
        "neural_method": "Noiseprint++ trained CNN residual extractor",
        "heuristic_method": "high-pass filter bank + K-means clustering (not Noiseprint++)",
    },
    "synthid_watermark_detect": {
        "neural_method": "Google SynthID watermark decoder",
        "heuristic_method": "metadata + frequency-domain probe (cannot decode true SynthID watermarks)",
    },
    "diffusion_artifact_detector": {
        "neural_method": "Organika/sdxl-detector ViT image classifier",
        "heuristic_method": "frequency-artifact heuristic (classifier weights not loaded)",
    },
    "anti_spoofing": {
        "neural_method": "AASIST trained anti-spoofing model",
        "heuristic_method": "spectral-feature heuristic (AASIST weights not loaded)",
    },
    "deepfake_frequency": {
        "neural_method": "",
        "heuristic_method": "frame-level FFT heuristic (no trained deepfake-frequency model)",
    },
}

# Pipeline tool slugs -> canonical TOOL_METHOD_DISCLOSURE key.
_METHOD_DISCLOSURE_ALIASES: dict[str, str] = {
    "neural_splicing": "trufor",
    "trufor": "trufor",
    "neural_copy_move": "busternet",
    "busternet": "busternet",
    "f3_net": "f3_net",
    "f3_net_frequency": "f3_net",
    "mantra": "mantra",
    "anomaly_tracer": "mantra",
    "neural_ela": "neural_ela",
    "ela_anomaly_classifier": "ela_anomaly_classifier",
    "ela_anomaly_classify": "ela_anomaly_classifier",
    "noiseprint_cluster": "noiseprint_cluster",
    "synthid_watermark_detect": "synthid_watermark_detect",
    "diffusion_artifact_detector": "diffusion_artifact_detector",
    "anti_spoofing": "anti_spoofing",
    "anti_spoofing_detect": "anti_spoofing",
    "anti_spoofing_deep_ensemble": "anti_spoofing",
    "deepfake_frequency": "deepfake_frequency",
    "deepfake_frequency_check": "deepfake_frequency",
}


def method_disclosure_for(tool: str) -> dict[str, str] | None:
    """Return the {neural_method, heuristic_method} disclosure for a tool slug."""
    key = _METHOD_DISCLOSURE_ALIASES.get(tool)
    return TOOL_METHOD_DISCLOSURE.get(key) if key else None


def actual_method_for(tool: str, *, research_models_enabled: bool, status: str = STATUS_RAN) -> str:
    """The method that ACTUALLY executed for this tool in this run.

    A research-gated tool with research models off, or any tool whose model was
    unavailable at runtime, executed its heuristic fallback (or nothing at all).
    Tools whose neural variant was never shipped always report the heuristic.
    """
    disclosure = method_disclosure_for(tool)
    cap = TOOL_CAPABILITY.get(tool, _DEFAULT)
    neural_ran = (
        cap["method"] == REAL_ML
        and (not cap["research_gated"] or research_models_enabled)
        and status not in (STATUS_GATED_OFF, STATUS_MODEL_UNAVAILABLE)
    )
    if disclosure:
        if neural_ran and disclosure.get("neural_method"):
            return disclosure["neural_method"]
        return disclosure["heuristic_method"]
    # No explicit disclosure entry — fall back to the capability-table model line.
    return cap["model"] or cap["method"].lower()


def truthful_tool_display(tool: str, *, research_models_enabled: bool, status: str = STATUS_RAN) -> str:
    """Render `tool` for the report, appending the actual method when the tool
    name implies a neural examination that did not (or cannot) run.

    e.g. "f3_net_frequency (Haar DWT + FFT heuristic — neural weights not loaded)".
    """
    disclosure = method_disclosure_for(tool)
    if not disclosure:
        return tool
    cap = TOOL_CAPABILITY.get(tool, _DEFAULT)
    neural_ran = (
        cap["method"] == REAL_ML
        and (not cap["research_gated"] or research_models_enabled)
        and status not in (STATUS_GATED_OFF, STATUS_MODEL_UNAVAILABLE)
    )
    if neural_ran and disclosure.get("neural_method"):
        return tool  # the name's implication matches what actually ran
    return f"{tool} ({disclosure['heuristic_method']})"


# ── Phase 3.1 Methodology: one-line "what this tool measures" per tool ───────
TOOL_DESCRIPTIONS: dict[str, str] = {
    "analyze_image_content": "Semantic content read of the image for scene grounding and routing.",
    "neural_fingerprint": "Perceptual embedding fingerprint for similarity and AI-style screening.",
    "extract_text": "Optical character recognition of visible text.",
    "extract_text_from_image": "Optical character recognition of visible text.",
    "object_detection": "Detects and classifies visible objects in the scene.",
    "neural_splicing": "Localizes spliced (foreign-paste) regions via pixel-residual inconsistency.",
    "trufor": "Localizes spliced (foreign-paste) regions via pixel-residual inconsistency.",
    "neural_copy_move": "Detects duplicated (copy-move) regions within the same image.",
    "f3_net_frequency": "Screens frequency-domain artifacts characteristic of AI generation.",
    "anomaly_tracer": "Screens for statistically anomalous pixel regions.",
    "diffusion_artifact_detector": "Classifies whether the image carries diffusion/GAN generation artifacts.",
    "neural_ela": "Measures error-level (recompression) inconsistency across image regions.",
    "ela_full_image": "Measures error-level (recompression) inconsistency across image regions.",
    "ela_anomaly_classifier": "Scores ELA statistics for outlier regions.",
    "ela_anomaly_classify": "Scores ELA statistics for outlier regions.",
    "noiseprint_cluster": "Clusters sensor-noise residuals to find regions from a different source.",
    "frequency_domain_analysis": "Inspects the FFT spectrum for periodic/manipulation artifacts.",
    "jpeg_ghost_detect": "Detects double-JPEG 'ghost' traces from local recompression.",
    "copy_move_detect": "Detects duplicated regions via keypoint matching.",
    "splicing_detect": "Screens for splice boundaries via noise-residual filters.",
    "synthid_watermark_detect": "Probes for AI-generation watermark/metadata indicators.",
    "speaker_diarize": "Segments the recording by speaker identity.",
    "neural_prosody": "Measures prosody (rhythm/intonation) anomalies typical of synthetic speech.",
    "audio_gen_signature": "Classifies synthetic-speech generation signatures.",
    "voice_clone_detect": "Measures speaker-embedding variance for voice-clone indicators.",
    "anti_spoofing_detect": "Scores the recording for replay/synthesis spoofing artifacts.",
    "anti_spoofing_deep_ensemble": "Ensemble scoring for replay/synthesis spoofing artifacts.",
    "codec_fingerprinting": "Identifies codec/re-encoding history from spectral traces.",
    "audio_visual_sync": "Checks audio-video envelope correlation for desynchronization.",
    "audio_splice_detect": "Detects abrupt spectral discontinuities consistent with audio splices.",
    "face_swap_detection": "Screens facial regions for swap/blend boundary artifacts.",
    "optical_flow_analysis": "Measures motion-field discontinuities between frames.",
    "frame_consistency_analysis": "Measures inter-frame similarity for dropped/inserted frames.",
    "interframe_forgery_detector": "Combines flow and similarity checks for inter-frame forgery.",
    "deepfake_frequency_check": "Screens frame spectra for generation artifacts.",
    "video_metadata": "Extracts container/stream metadata for provenance checks.",
    "exif_extract": "Extracts EXIF metadata fields for provenance and consistency checks.",
    "file_structure_analysis": "Validates file header/trailer structure and appended payloads.",
    "hex_signature_scan": "Scans binary content for editing-software signatures.",
    "provenance_chain_verify": "Scans for C2PA provenance markers.",
    "camera_profile_match": "Checks metadata against plausible camera parameter ranges.",
    "metadata_anomaly_score": "Scores metadata fields for statistical anomalies.",
    "file_hash_verify": "Verifies the SHA-256 hash against the intake chain-of-custody record.",
    "timestamp_analysis": "Checks timestamp fields for chronological consistency.",
    "gps_timezone_validate": "Cross-checks GPS coordinates against timezone/timestamp claims.",
    "visual_evidence_profile": "Holistic scene/content read used to ground and scope other tools.",
    "gemini_forensic_synthesis": "LLM-assisted synthesis of tool outputs into narrative form.",
}

_DEFAULT_DESCRIPTION = "Forensic measurement (no per-tool description registered yet)."


def describe_tool(tool: str) -> str:
    return TOOL_DESCRIPTIONS.get(tool, _DEFAULT_DESCRIPTION)


def _cap(method: str, model: str = "", license: str = "", research_gated: bool = False) -> dict[str, Any]:
    return {"method": method, "model": model, "license": license, "research_gated": research_gated}


# tool name -> capability. `research_gated` tools run a HEURISTIC/classical fallback
# (and the model line is annotated) when enable_research_models is False. Unlisted
# tools fall back to method "unspecified" so the manifest is still complete.
TOOL_CAPABILITY: dict[str, dict[str, Any]] = {
    # ── Image (genuine ML) ───────────────────────────────────────────────────
    "analyze_image_content": _cap(REAL_ML, "OpenCLIP ViT-B-32", "MIT"),
    "neural_fingerprint": _cap(REAL_ML, "SigLIP2", "Apache-2.0"),
    "extract_text": _cap(REAL_ML, "EasyOCR / Florence-2", "Apache-2.0"),
    "extract_text_from_image": _cap(REAL_ML, "EasyOCR / Florence-2", "Apache-2.0"),
    "object_detection": _cap(REAL_ML, "DETR-ResNet-50", "Apache-2.0"),
    # ── Image (research-gated; classical fallback when off) ──────────────────
    "neural_splicing": _cap(REAL_ML, "TruFor (SegFormer-B2)", "non-commercial", research_gated=True),
    "trufor": _cap(REAL_ML, "TruFor (SegFormer-B2)", "non-commercial", research_gated=True),
    "neural_copy_move": _cap(REAL_ML, "BusterNet", "non-commercial", research_gated=True),
    "f3_net_frequency": _cap(REAL_ML, "F3-Net", "research-only", research_gated=True),
    "anomaly_tracer": _cap(REAL_ML, "ManTra-Net", "research-only", research_gated=True),
    "diffusion_artifact_detector": _cap(REAL_ML, "Organika sdxl-detector", "non-commercial", research_gated=True),
    # ── Image (heuristics under neural-ish names) ────────────────────────────
    "neural_ela": _cap(HEURISTIC, "multi-quality resave + per-image IsolationForest", ""),
    "ela_full_image": _cap(HEURISTIC, "error-level analysis", ""),
    "ela_anomaly_classifier": _cap(HEURISTIC, "per-image IsolationForest", ""),
    "noiseprint_cluster": _cap(HEURISTIC, "high-pass filter bank + K-means", ""),
    "frequency_domain_analysis": _cap(HEURISTIC, "FFT", ""),
    "jpeg_ghost_detect": _cap(HEURISTIC, "JPEG-ghost", ""),
    "copy_move_detect": _cap(HEURISTIC, "ORB + RANSAC", ""),
    "splicing_detect": _cap(HEURISTIC, "SRM residual", ""),
    "synthid_watermark_detect": _cap(HEURISTIC, "metadata + frequency probe (not true SynthID)", ""),
    # ── Audio (genuine ML) ───────────────────────────────────────────────────
    "speaker_diarize": _cap(REAL_ML, "SpeechBrain ECAPA-TDNN", "Apache-2.0"),
    "neural_prosody": _cap(REAL_ML, "Wav2Vec2", "Apache-2.0"),
    "audio_gen_signature": _cap(REAL_ML, "wav2vec2 deepfake fine-tune", "varies"),
    "voice_clone_detect": _cap(REAL_ML, "ECAPA embedding variance", "Apache-2.0"),
    "anti_spoofing_detect": _cap(REAL_ML, "AASIST", "research-only", research_gated=True),
    "anti_spoofing_deep_ensemble": _cap(REAL_ML, "AASIST ensemble", "research-only", research_gated=True),
    "codec_fingerprinting": _cap(HEURISTIC, "FFT codec heuristic", ""),
    "audio_visual_sync": _cap(HEURISTIC, "envelope correlation (not a sync model)", ""),
    "audio_splice_detect": _cap(HEURISTIC, "MFCC/spectral-delta IsolationForest", ""),
    # ── Video (no real ML in default path) ───────────────────────────────────
    "face_swap_detection": _cap(HEURISTIC, "Haar cascade + FFT (not a trained deepfake model)", ""),
    "optical_flow_analysis": _cap(HEURISTIC, "OpenCV Farneback", ""),
    "frame_consistency_analysis": _cap(HEURISTIC, "SSIM + histogram", ""),
    "interframe_forgery_detector": _cap(HEURISTIC, "flow + SSIM", ""),
    "deepfake_frequency_check": _cap(HEURISTIC, "frame-level FFT", ""),
    "video_metadata": _cap(WRAPPER, "ffprobe", ""),
    # ── Metadata / document ──────────────────────────────────────────────────
    "exif_extract": _cap(WRAPPER, "exiftool", ""),
    "file_structure_analysis": _cap(HEURISTIC, "magic/structure check", ""),
    "hex_signature_scan": _cap(WRAPPER, "byte-signature DB", ""),
    "provenance_chain_verify": _cap(HEURISTIC, "c2pa byte-string scan (no cryptographic manifest validation)", ""),
    "camera_profile_match": _cap(HEURISTIC, "plausible-range check (no device DB)", ""),
    "metadata_anomaly_score": _cap(HEURISTIC, "5-row IsolationForest (statistically weak)", ""),
    "file_hash_verify": _cap(WRAPPER, "SHA-256", ""),
    # ── LLM-as-tool ──────────────────────────────────────────────────────────
    "visual_evidence_profile": _cap(LLM, "Gemini / local ensemble", ""),
    "gemini_forensic_synthesis": _cap(LLM, "Gemini", ""),
}

_DEFAULT = _cap("unspecified")


def classify_tool(tool: str, *, research_models_enabled: bool) -> dict[str, Any]:
    """Return the effective {method, model, license} for a tool, honouring the
    research-model gate (a gated tool downgrades to its classical fallback)."""
    cap = TOOL_CAPABILITY.get(tool, _DEFAULT)
    method = cap["method"]
    model = cap["model"]
    if cap["research_gated"] and not research_models_enabled:
        method = HEURISTIC
        model = f"{model} — GATED OFF in prod, classical fallback running"
    return {"method": method, "model": model, "license": cap["license"]}


def _tool_record(
    tool: str,
    status: str,
    *,
    research_on: bool,
    model_version: str | None = None,
) -> dict[str, Any]:
    """Build one per-tool manifest record with truthful method/model/metrics fields."""
    info = classify_tool(tool, research_models_enabled=research_on)
    execution_status = STATUS_SKIPPED_BY_ROUTING if status == "not_applicable" else status
    return {
        "tool": tool,
        "status": status,  # legacy vocabulary, preserved for existing consumers
        "execution_status": execution_status,  # plan-0.6 vocabulary
        **info,
        "model_name": TOOL_CAPABILITY.get(tool, _DEFAULT)["model"] or None,
        "model_version": model_version,
        "actual_method": actual_method_for(
            tool, research_models_enabled=research_on, status=execution_status
        ),
        "description": describe_tool(tool),
        # Measured reliability metrics — filled by Phase-1 calibration sweeps.
        "metrics": dict(EMPTY_TOOL_METRICS),
    }


def build_capability_manifest(
    active_results: dict[str, Any] | None,
    config: Any,
    mime_type: str = "",
    tool_coverage: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Build the per-investigation capability manifest from agent results + config.

    Each tool is recorded with an honest status:
      ran | failed | not_applicable | gated_off | model_unavailable
    plus the method/model/license/actual_method that actually executed, and a
    placeholder metrics block ({tpr, fpr, threshold, validation_dataset}) for
    Phase-1 measured values.

    ``tool_coverage`` (optional) adds tools that produced no finding at all —
    e.g. skipped-by-routing tools — so the manifest covers every applicable tool.

    Side effect: the built manifest is registered in a ContextVar so downstream
    report builders in the same investigation task (deterministic_report_builder)
    can embed it without new plumbing through every call signature.
    """
    research_on = bool(getattr(config, "enable_research_models", False))
    gemini_on = bool(
        getattr(config, "gemini_api_key_policy_ok", False) and getattr(config, "gemini_api_key", "")
    )

    tools: list[dict[str, Any]] = []
    seen: set[str] = set()
    for _aid, res in (active_results or {}).items():
        for f in res.get("findings", []) if isinstance(res, dict) else []:
            meta = f.get("metadata") or {}
            tool = meta.get("tool_name") or f.get("finding_type")
            if not tool or tool in seen:
                continue
            seen.add(tool)

            status_raw = str(f.get("status") or "").upper()
            ev = str(f.get("evidence_verdict") or "").upper()
            cap = TOOL_CAPABILITY.get(tool, _DEFAULT)

            if status_raw in ("FAILED", "ERROR", "TIMEOUT", "INCOMPLETE") or ev == "ERROR":
                status = "failed"
            elif status_raw == "NOT_APPLICABLE" or ev == "NOT_APPLICABLE":
                status = "not_applicable"
            elif meta.get("available") is False:
                status = "gated_off" if (cap["research_gated"] and not research_on) else "model_unavailable"
            else:
                status = "ran"

            model_version = (
                meta.get("model_version")
                or meta.get("model_revision")
                or meta.get("model_used")
                or None
            )
            tools.append(
                _tool_record(
                    tool, status, research_on=research_on,
                    model_version=str(model_version) if model_version else None,
                )
            )

    # Tools known to the coverage tracker that never produced a finding — record
    # them too so the manifest covers every applicable tool, not just the ones
    # that emitted output.
    if tool_coverage:
        _coverage_status = (
            ("completed_tools", "ran"),
            ("failed_tools", "failed"),
            ("not_applicable_tools", "not_applicable"),
            ("skipped_tools", "not_applicable"),
        )
        for key, status in _coverage_status:
            for tool in tool_coverage.get(key) or []:
                tool = str(tool)
                if not tool or tool in seen:
                    continue
                seen.add(tool)
                tools.append(_tool_record(tool, status, research_on=research_on))

    tools.sort(key=lambda t: t["tool"])

    # Human-readable disclosures for the existing degradation banner — surfaces the
    # most material capability gaps without new DTO plumbing.
    disclosures: list[str] = []
    gated = [t["tool"] for t in tools if t["status"] == "gated_off"]
    unavailable = [t["tool"] for t in tools if t["status"] == "model_unavailable"]
    if gated:
        disclosures.append(
            "Research neural models are disabled — "
            f"{', '.join(sorted(gated))} ran a classical-CV fallback, not the named neural model."
        )
    if unavailable:
        disclosures.append(
            f"Model unavailable at runtime for: {', '.join(sorted(unavailable))} — "
            "treated as a coverage gap, not a clean result."
        )
    if not gemini_on:
        disclosures.append(
            "Holistic vision/text model (Gemini) is disabled — visual/content reads ran on the "
            "local screening ensemble; some AI-generation assessments are reduced-confidence."
        )

    manifest = {
        "research_models_enabled": research_on,
        "gemini_enabled": gemini_on,
        "tool_count": len(tools),
        "tools": tools,
        "disclosures": disclosures,
    }
    set_current_manifest(manifest)
    return manifest


# ── Per-investigation manifest handoff ───────────────────────────────────────
# The arbiter builds the manifest early (from active agent results + config) and
# the deterministic report builder needs it later in the SAME async task. A
# ContextVar gives task-local handoff without changing the report-builder call
# signature owned by arbiter.py. Concurrent investigations run in separate
# asyncio tasks, so their manifests never cross.
_current_manifest: contextvars.ContextVar[dict[str, Any] | None] = contextvars.ContextVar(
    "forensic_capability_manifest", default=None
)


def set_current_manifest(manifest: dict[str, Any] | None) -> None:
    _current_manifest.set(manifest)


def get_current_manifest() -> dict[str, Any] | None:
    """The capability manifest built for the current investigation task, if any."""
    return _current_manifest.get()


def build_manifest_from_coverage(
    tool_coverage: dict[str, Any] | None,
    *,
    research_models_enabled: bool = False,
    gemini_enabled: bool = False,
) -> dict[str, Any]:
    """Degraded-mode manifest built from the tool-coverage lists alone.

    Used when the full manifest (built from agent results + config) is not
    available to the report builder — still records per-tool status,
    actual_method, license, and the Phase-1 metrics placeholders.
    """
    tools: list[dict[str, Any]] = []
    seen: set[str] = set()
    _coverage_status = (
        ("completed_tools", "ran"),
        ("failed_tools", "failed"),
        ("not_applicable_tools", "not_applicable"),
        ("skipped_tools", "not_applicable"),
    )
    for key, status in _coverage_status:
        for tool in (tool_coverage or {}).get(key) or []:
            tool = str(tool)
            if not tool or tool in seen:
                continue
            seen.add(tool)
            tools.append(_tool_record(tool, status, research_on=research_models_enabled))
    tools.sort(key=lambda t: t["tool"])
    return {
        "research_models_enabled": research_models_enabled,
        "gemini_enabled": gemini_enabled,
        "tool_count": len(tools),
        "tools": tools,
        "disclosures": [],
        "degraded_source": "tool_coverage_only",
    }
