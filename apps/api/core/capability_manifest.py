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

from typing import Any

REAL_ML = "REAL_ML"
HEURISTIC = "HEURISTIC"
WRAPPER = "WRAPPER"
LLM = "LLM"


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


def build_capability_manifest(
    active_results: dict[str, Any] | None,
    config: Any,
    mime_type: str = "",
) -> dict[str, Any]:
    """Build the per-investigation capability manifest from agent results + config.

    Each tool is recorded with an honest status:
      ran | failed | not_applicable | gated_off | model_unavailable
    plus the method/model/license that actually executed.
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

            info = classify_tool(tool, research_models_enabled=research_on)
            tools.append({"tool": tool, "status": status, **info})

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

    return {
        "research_models_enabled": research_on,
        "gemini_enabled": gemini_on,
        "tool_count": len(tools),
        "tools": tools,
        "disclosures": disclosures,
    }
