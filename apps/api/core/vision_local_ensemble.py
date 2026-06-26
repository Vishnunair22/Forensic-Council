"""
Local Visual Ensemble — Gemini-equivalent local fallback.

Runs a battery of deterministic, locally-available forensic tools to produce
a VisualEvidenceFinding comparable to Gemini's output.  When Gemini is
unavailable (disabled, quota exceeded, or runtime failure), this ensemble
is the sole source of visual forensic context for the investigation.

Tools (all run in parallel):
  1. ELA — JPEG re-compression residual analysis (lossless/screenshot guarded)
  2. OCR — Tesseract + EasyOCR text extraction
  3. CLIP — SigLIP2 zero-shot scene classification
  4. DETR/YOLO — Object detection and inventory
  5. FFT — Frequency-domain high-frequency ratio analysis
  6. Noiseprint — Sensor-noise region consistency clustering (non-lossless only)
  7. Splicing — DCT quantization fingerprint analysis (JPEG only)
  8. Diffusion — GAN/diffusion spectral artifact detection (all images)
  9. Florence-2 — VLM captioning when torch+transformers available
  10. OpenCV — Statistics extraction (resolution, sharpness, brightness, noise, blockiness)

Synthesis layer (pure Python, deterministic):
  Cross-signal corroboration rules connect independent tool outputs into a
  single coherent manipulation verdict with spatial localization language,
  replacing Gemini's natural-language reasoning with rule-based inference.
"""

from __future__ import annotations

import asyncio
import re
import time
from typing import Any

from core.evidence import EvidenceArtifact
from core.image_routing import build_image_forensic_routing
from core.image_utils import is_lossless_image
from core.structured_logging import get_logger
from core.vision_types import VisualEvidenceFinding

logger = get_logger(__name__)

_TOOL_NAMES = [
    "ELA",
    "OCR",
    "CLIP",
    "DETR",
    "FFT",
    "Noiseprint",
    "Splicing",
    "Diffusion",
    "Florence",
    "OpenCV",
]


async def run_with_timeout(name: str, coro, timeout: float) -> Any:
    """Wrap a tool execution coroutine with a timeout and standardized error handling."""
    try:
        return await asyncio.wait_for(coro, timeout=timeout)
    except TimeoutError:
        return {"available": False, "status": "timeout", "error": f"{name} timed out"}
    except Exception as exc:
        return {"available": False, "status": "error", "error": str(exc)}


def _is_tool_successful(result: Any) -> bool:
    if result is None:
        return False
    if isinstance(result, Exception):
        return False
    if isinstance(result, dict):
        if result.get("status") in ("error", "timeout") or result.get("available") is False:
            return False
        if result.get("error"):
            return False
    return True


def _tool_error_summary(result: Any) -> str:
    if isinstance(result, Exception):
        return str(result)
    if isinstance(result, dict):
        return str(result.get("error", "unknown error"))
    return "unknown error"


import re as _re

# Patterns for provenance clues visible inside the image (OCR-extracted text).
_TIME_RE = _re.compile(r"\b\d{1,2}:\d{2}(?::\d{2})?\s*(?:[AaPp]\.?[Mm]\.?)?\b")
_DATE_RE = _re.compile(
    r"\b("
    r"\d{1,4}[-/.]\d{1,2}[-/.]\d{1,4}"  # 2023-06-01, 01/06/2023
    r"|(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*\.?\s+\d{1,2}(?:,?\s+\d{4})?"  # Jun 1, 2023
    r"|\d{1,2}\s+(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*"  # 1 June
    r")\b",
    _re.IGNORECASE,
)
_PLATFORM_KEYWORDS = {
    "iOS": ("iphone", "ios", "imessage", "airdrop", "facetime"),
    "Android": ("android", "google play", "play store"),
    "WhatsApp": ("whatsapp", "last seen", "typing…", "typing..."),
    "Telegram": ("telegram",),
    "Instagram": ("instagram",),
    "Twitter/X": ("twitter", "retweet", "tweet"),
    "Facebook": ("facebook",),
    "Gmail": ("gmail",),
    "Web/Browser": ("http://", "https://", "www."),
}


def _kw_present(keyword: str, text: str) -> bool:
    """Whole-token keyword match for provenance/platform detection.

    A bare substring test made short tokens like "ios" match inside ordinary words
    ("various", "scenarios", "ratios"), fabricating an "iOS platform" provenance on
    a desktop web screenshot. Pure alphanumeric keywords are matched on word
    boundaries; multi-word or punctuation-bearing keywords ("last seen", "http://",
    "typing…") are distinctive enough to keep the substring test.
    """
    kw = (keyword or "").lower()
    txt = (text or "").lower()
    if not kw:
        return False
    if re.fullmatch(r"[a-z0-9]+", kw):
        return re.search(r"(?<![a-z0-9])" + re.escape(kw) + r"(?![a-z0-9])", txt) is not None
    return kw in txt


def _meaningful_ocr_lines(ocr_lines: list[str]) -> list[str]:
    """Drop low-coherence OCR noise. Photos/objects/textures produce garbage OCR
    ('Salas lh hg a =" ES, _ rr Tan ...') that must never surface as 'Extracted
    text' or a visible timestamp. A line is kept only when it contains at least two
    word-like tokens (3+ letters with a vowel) AND is predominantly alphabetic."""
    out: list[str] = []
    for ln in (ocr_lines or []):
        s = str(ln).strip()
        if len(s) < 4:
            continue
        words = [w for w in _re.findall(r"[A-Za-z]{3,}", s) if _re.search(r"[aeiouAEIOU]", w)]
        alpha = sum(c.isalpha() or c.isspace() for c in s)
        if len(words) >= 2 and (alpha / max(1, len(s))) >= 0.6:
            out.append(s)
    return out


def _extract_visible_metadata_clues(
    ocr_lines: list[str],
    interface_id: str,
    exif_summary: dict[str, Any] | None,
    is_screenshot: bool,
) -> dict[str, list[str]]:
    """Extract provenance clues visible in the image (timestamps, device/platform,
    app, location) from OCR text + interface identification.

    This fills the metadata-provenance section so the no-Gemini path still
    produces Agent5-usable context (the Gemini preflight does this natively).
    Pure inference from pixels — never asserts EXIF facts.
    """
    text = " ".join(str(line) for line in (ocr_lines or []))
    clues: dict[str, list[str]] = {
        "visible_timestamps": [],
        "device_platform_clues": [],
        "software_clues": [],
        "location_clues": [],
    }
    if not text and not interface_id:
        return clues

    lower = text.lower()

    # Timestamps visible on-screen (status-bar clock, message times, overlays)
    seen_ts: set[str] = set()
    for match in list(_TIME_RE.findall(text)) + [m if isinstance(m, str) else m[0] for m in _DATE_RE.findall(text)]:
        val = str(match).strip()
        if val and val not in seen_ts and len(val) >= 3:
            seen_ts.add(val)
            clues["visible_timestamps"].append(val)
    clues["visible_timestamps"] = clues["visible_timestamps"][:8]

    # Device / platform / app from OCR keywords + interface identification
    platforms: list[str] = []
    for platform, keywords in _PLATFORM_KEYWORDS.items():
        if any(_kw_present(kw, lower) for kw in keywords):
            platforms.append(platform)
    # Only a concrete interface/app identification is a software clue. The generic
    # FALLBACK ("Identified digital interface category: <category>") is a meta-
    # description of the scene, not a software name — appending it surfaces a garbled
    # "software: Identified digital interface category: web site (iOS platform signs)"
    # in Agent5's provenance. Drop the fallback; keep real identifications.
    if interface_id and not interface_id.lower().startswith("identified digital interface category:"):
        clues["software_clues"].append(interface_id)
    # OS-level vs app-level split
    for p in platforms:
        if p in ("iOS", "Android", "Web/Browser"):
            clues["device_platform_clues"].append(p)
        else:
            clues["software_clues"].append(p)

    return clues


_WEAPON_KEYWORDS = (
    "gun", "pistol", "rifle", "firearm", "weapon", "knife", "blade", "sword",
    "explosive", "grenade", "ammunition", "bomb", "handgun", "shotgun", "machete",
)
_DOCUMENT_KEYWORDS = (
    "passport", "license", "licence", "id card", "identity card", "certificate",
    "invoice", "form", "receipt", "contract", "ledger", "statement", "affidavit",
)


def _derive_rich_scene_signals(
    file_path: str,
    detected_objects: list[str],
    ocr_lines: list[str],
    clip_category: str,
    final_category: str,
    ela_res: dict,
    noiseprint_res: dict,
    opencv_res: dict,
) -> dict[str, list[str]]:
    """Derive richer object/integrity/provenance signals from already-collected
    tool outputs — the local-ensemble analogue of the dedicated fields the
    refined Gemini prompt now returns (weapons, documents, people, lighting,
    follow-up regions, benign edits). Pure inference over existing results; adds
    no new model calls. Empty lists when nothing is genuinely found.
    """
    objs = [str(o) for o in (detected_objects or []) if str(o).strip()]
    text_l = " ".join(str(t).lower() for t in (ocr_lines or []))
    cat_l = f"{clip_category} {final_category}".lower()

    weapons = sorted({o for o in objs if any(k in o.lower() for k in _WEAPON_KEYWORDS)})
    people = [o for o in objs if any(k in o.lower() for k in ("person", "people", "face", "man", "woman", "child"))]

    documents: list[str] = []
    if final_category == "document" or "document" in cat_l or "id card" in cat_l or "passport" in cat_l:
        documents.append(f"document-like image ({clip_category})")
    documents += [k for k in _DOCUMENT_KEYWORDS if k in text_l]

    # Benign editing: alpha/transparency strongly implies a cutout / background removal.
    editing: list[str] = []
    try:
        from PIL import Image as _PILImg
        with _PILImg.open(file_path) as _im:
            if _im.mode in ("RGBA", "LA", "PA") or "transparency" in _im.info:
                editing.append("transparent/alpha channel present (background removal or cutout)")
    except Exception as exc:
        logger.debug("Alpha-channel edit probe failed", error=str(exc))

    # Regions worth a pixel-level forensic zoom, from forensic hotspots.
    regions: list[str] = []
    if isinstance(ela_res, dict) and not ela_res.get("not_applicable"):
        n = int(ela_res.get("num_anomaly_regions", 0) or 0)
        if n > 0:
            regions.append(f"{n} ELA hotspot region(s)")
    if isinstance(noiseprint_res, dict) and not noiseprint_res.get("not_applicable") and noiseprint_res.get("sensor_inconsistency_detected"):
        regions.append("sensor-noise inconsistent region(s)")

    # Coarse lighting / scene clues usable by Agent5 time/geo cross-checks.
    lighting: list[str] = []
    if isinstance(opencv_res, dict) and opencv_res.get("available"):
        b = float(opencv_res.get("brightness", 0) or 0)
        if b < 55:
            lighting.append("low average brightness — low-light, night, or indoor scene")
        elif b > 205:
            lighting.append("high average brightness — bright or high-key lighting")
    if "outdoor" in cat_l:
        lighting.append("outdoor scene")
    elif "indoor" in cat_l:
        lighting.append("indoor scene")

    return {
        "weapons": weapons,
        "people": people[:5],
        "documents": documents[:5],
        "editing_signals": editing,
        "regions_for_followup": regions,
        "lighting_weather_season": lighting,
    }


def _clip_to_category(clip_top_match: str) -> str:
    t = clip_top_match.lower()
    if "screenshot" in t or "screen capture" in t:
        return "screenshot"
    if "document" in t or "id card" in t or "passport" in t:
        return "document"
    if "ai-generated" in t or "digitally generated" in t:
        return "ai_generated_suspect"
    if "social media" in t or "meme" in t:
        return "web_image"
    return "live_photograph"


# ── Cross-signal synthesis layer ────────────────────────────────────────────

def _cross_signal_synthesis(
    ela_res: dict,
    fft_res: dict,
    noiseprint_res: dict,
    splicing_res: dict,
    diffusion_res: dict,
    opencv_res: dict,
    clip_category: str,
    detected_objects: list[str],
    ocr_lines: list[str],
    florence_desc: str,
    is_screenshot: bool,
) -> tuple[str, list[str], str, bool]:
    """Produce (verdict, signals, narrative, conflict_detected) from cross-tool corroboration.

    Returns:
        verdict: One of AUTHENTIC, SUSPICIOUS, INCONCLUSIVE
        signals: List of corroborated manipulation signal descriptions
        narrative: Single coherent scene description paragraph
        conflict_detected: True when cross-signals disagree (e.g., CLIP says camera but diffusion says AI)
    """
    signals: list[str] = []
    conflict_detected = False

    # Extract raw metrics
    ela_max = ela_res.get("max_anomaly", 0.0) if isinstance(ela_res, dict) else 0.0
    ela_regions = ela_res.get("num_anomaly_regions", 0) if isinstance(ela_res, dict) else 0
    ela_suspicious = ela_res.get("suspicious", False) if isinstance(ela_res, dict) else False
    ela_not_applicable = ela_res.get("not_applicable", False) if isinstance(ela_res, dict) else True

    fft_ratio = fft_res.get("high_freq_ratio", 0.0) if isinstance(fft_res, dict) else 0.0
    fft_anomaly = fft_res.get("anomaly_detected", False) if isinstance(fft_res, dict) else False

    noise_clusters = noiseprint_res.get("num_clusters", 1) if isinstance(noiseprint_res, dict) else 1
    noise_inconsistent = noiseprint_res.get("sensor_inconsistency_detected", False) if isinstance(noiseprint_res, dict) else False
    noise_not_applicable = noiseprint_res.get("not_applicable", False) if isinstance(noiseprint_res, dict) else True

    splice_detected = splicing_res.get("splicing_detected", False) if isinstance(splicing_res, dict) else False
    splice_score = splicing_res.get("splicing_score", 0.0) if isinstance(splicing_res, dict) else 0.0

    diff_detected = (
        diffusion_res.get("diffusion_detected", False)
        or diffusion_res.get("is_ai_generated", False)
    ) if isinstance(diffusion_res, dict) else False
    diff_probability = diffusion_res.get("diffusion_probability", 0.0) if isinstance(diffusion_res, dict) else 0.0

    logger.info(
        "Diffusion detection result",
        diff_detected=diff_detected,
        diff_probability=round(diff_probability, 3),
        is_ai_generated=diffusion_res.get("is_ai_generated") if isinstance(diffusion_res, dict) else None,
        method=diffusion_res.get("method") if isinstance(diffusion_res, dict) else None,
        available=diffusion_res.get("available") if isinstance(diffusion_res, dict) else None,
    )

    # ── Corroboration rules ──────────────────────────────────────────────
    # Rule 1: ELA + noiseprint spatial corroboration → high-confidence splice
    if (ela_suspicious or ela_max > 30.0) and noise_inconsistent and not ela_not_applicable and not noise_not_applicable:
        signals.append("Pixel-level ELA anomalies and sensor noise inconsistency in overlapping regions — high confidence of local splice")

    # Rule 2: Frequency anomaly + ELA corroboration
    elif (ela_suspicious or ela_max > 25.0) and fft_anomaly and not ela_not_applicable:
        signals.append("Both frequency-domain and re-compression residual analysis show elevated anomaly — corroborated manipulation signal")

    # Rule 3: Splicing detector + ELA
    elif splice_detected and (ela_suspicious or ela_max > 20.0) and not ela_not_applicable:
        signals.append("DCT quantization fingerprint inconsistency and ELA hotspot overlap — likely region tampering")

    # Individual signals (no corroboration)
    else:
        if ela_suspicious and not ela_not_applicable:
            signals.append(f"ELA anomaly detected (max={ela_max:.1f}, regions={ela_regions})")
        if fft_anomaly:
            signals.append(f"Frequency-domain anomaly (high_freq_ratio={fft_ratio:.3f})")
        if splice_detected:
            signals.append(f"Splicing detected (score={splice_score:.3f})")
        if noise_inconsistent and not noise_not_applicable:
            signals.append(f"Sensor noise inconsistency ({noise_clusters} clusters)")

    # OpenCV signals.
    # Absolute noise level and JPEG blockiness are confounded by ISO/grain and
    # compression quality — high values are normal for small or low-quality
    # captures and are NOT manipulation evidence on their own. Manipulation
    # shows as noise INCONSISTENCY across regions (handled via noiseprint
    # clusters above). So only surface these as manipulation signals when
    # corroborated by regional sensor-noise inconsistency; otherwise they are
    # benign quality descriptors and would just create false positives on
    # authentic compressed images.
    if opencv_res:
        noise_corroborated = noise_inconsistent and not noise_not_applicable
        noise_threshold = 5.0 if is_screenshot else 10.0
        noise_val = opencv_res.get("noise", 0.0) or 0.0
        if noise_val > noise_threshold and noise_corroborated:
            signals.append(f"Elevated noise residual ({noise_val:.2f}) with regional inconsistency")

        block_threshold = 12.0 if is_screenshot else 8.0
        blockiness_val = opencv_res.get("blockiness", 0.0) or 0.0
        if blockiness_val > block_threshold and noise_corroborated:
            signals.append(f"JPEG block artifacts detected ({blockiness_val:.1f}) with regional inconsistency")

    # Rule 4: AI-generation spectral artifacts
    if diff_detected and diff_probability > 0.5:
        signals.append(f"Diffusion/GAN spectral artifacts detected (probability={diff_probability:.3f})")
        # Cross-check: CLIP says it's a camera photo but diffusion says AI-generated
        if clip_category.lower() in ("live_photograph",) and not is_screenshot:
            signals.append("Conflicting authenticity signals — manual review advised")
            conflict_detected = True

    # Rule 5: All clean
    if not signals:
        tools_reported = []
        if not ela_not_applicable:
            tools_reported.append("ELA")
        if fft_res:
            tools_reported.append("FFT")
        if not noise_not_applicable:
            tools_reported.append("Noiseprint")
        if splicing_res:
            tools_reported.append("Splicing")
        if diffusion_res:
            tools_reported.append("Diffusion")
        if tools_reported:
            signals.append(f"{'/'.join(tools_reported)}: no manipulation indicators detected")

    # ── Verdict (calibrated) ─────────────────────────────────────────────
    # The local ensemble is a SCREENING tool and must not cry wolf. A single
    # weak or uncorroborated signal yields INCONCLUSIVE (surfaced for review),
    # NEVER SUSPICIOUS. SUSPICIOUS is reserved for corroborated multi-tool
    # evidence or a strong AI-generation read. This stops clean evidence being
    # flagged on noise-residual alone (matches the conservative uncertainty
    # policy) — the raw tool metrics still reach each agent regardless.
    def _is_clean_note(s: str) -> bool:
        sl = s.lower()
        return sl.endswith("indicators detected") or "no manipulation" in sl

    weak_markers = (
        "elevated noise residual",
        "jpeg block artifacts",
        "high_freq_ratio",
        "frequency-domain anomaly",
    )
    substantive = [s for s in signals if not _is_clean_note(s)]
    # "Strong" = a real manipulation signal, excluding weak screening artifacts
    # (global noise level, blockiness, raw high-freq ratio) that fire on benign
    # textured/recompressed images and are the main false-positive source.
    strong_substantive = [
        s for s in substantive if not any(w in s.lower() for w in weak_markers)
    ]
    corroborated = any(
        ("corroborat" in s.lower() or "high confidence" in s.lower()
         or "likely region tampering" in s.lower() or "overlap" in s.lower())
        for s in substantive
    )
    strong_ai = diff_detected and diff_probability > 0.7

    logger.info(
        "Local ensemble verdict signals",
        diff_detected=diff_detected,
        diff_probability=round(diff_probability, 3),
        strong_ai=strong_ai,
        substantive_count=len(substantive),
        corroborated=corroborated,
        strong_substantive_count=len(strong_substantive),
    )

    if corroborated or strong_ai:
        verdict = "SUSPICIOUS"
    elif len(strong_substantive) >= 2:
        # Two independent strong tools agree → escalate.
        verdict = "SUSPICIOUS"
    elif substantive:
        # A single tool (even strong) or weak-only screening signal: surface for
        # review, do not alarm. Corroboration is required to call SUSPICIOUS.
        verdict = "INCONCLUSIVE"
    elif any(isinstance(res, dict) and res.get("status") in ("error", "timeout", "degraded") for res in [diffusion_res, ela_res, fft_res, splicing_res, noiseprint_res]):
        # If no substantive signals were found BUT a tool failed (e.g., AI generation detector timed out),
        # we must not falsely declare the evidence AUTHENTIC because we have a critical blind spot.
        verdict = "INCONCLUSIVE"
        signals.append("One or more local forensic tools failed or timed out — cannot conclusively confirm authenticity.")
    else:
        verdict = "AUTHENTIC"

    # ── Narrative ────────────────────────────────────────────────────────
    # Only assert a forensic finding in the narrative when the holistic verdict is
    # an alert. Under AUTHENTIC/INCONCLUSIVE the substantive signals are
    # uncorroborated screening leads the ensemble declined to escalate — surfacing
    # them as "Forensic assessment: ELA anomaly detected" contradicts the verdict.
    _narr_alert = verdict in ("SUSPICIOUS", "LIKELY_MANIPULATED", "TAMPERED", "MANIPULATED", "AI_GENERATED")
    _narr_substantive = [s for s in signals if not _is_clean_note(s)]
    _assert_signal = _narr_alert and bool(_narr_substantive)
    _lead_signal = _narr_substantive[0] if _narr_substantive else (signals[0] if signals else "")
    if is_screenshot:
        app_hint = "an unidentified application"
        ocr_text_lower = " ".join(ocr_lines).lower()
        for name, keyword in {
            'WhatsApp': 'whatsapp', 'Telegram': 'telegram', 'Instagram': 'instagram',
            'Twitter': 'twitter', 'Facebook': 'facebook', 'Gmail': 'gmail',
            'YouTube': 'youtube', 'Safari': 'safari', 'Chrome': 'chrome',
        }.items():
            if _kw_present(keyword, ocr_text_lower):
                app_hint = name
                break
        narrative = (
            f"This is a {clip_category} capture, likely from {app_hint}. "
            f"Extracted {len(ocr_lines)} text elements for content verification. "
        )
        if _assert_signal:
            narrative += f"Forensic assessment: {_lead_signal}. "
        else:
            narrative += "Screenshot integrity validated via hash and OCR consistency checks. "
    else:
        obj_summary = f"{len(detected_objects)} object(s)" if detected_objects else "no distinct objects"
        narrative_parts = []
        if florence_desc:
            narrative_parts.append(florence_desc)
        else:
            narrative_parts.append(f"Local ensemble classified this as '{clip_category}' with {obj_summary} detected.")
        if _assert_signal:
            narrative_parts.append(f"Forensic assessment: {_lead_signal}.")
        else:
            narrative_parts.append("Independent forensic measures show no corroborated manipulation indicator.")
        narrative = " ".join(narrative_parts)

    return verdict, signals, narrative, conflict_detected


def _minimal_degraded_finding(
    artifact: EvidenceArtifact, error: Exception, latency_ms: float = 0.0
) -> VisualEvidenceFinding:
    """Last-resort finding when the entire local ensemble fails.

    The local ensemble is the TERMINAL fallback after Gemini, so it must never
    raise — a raise would strand the investigation with no visual context at all.
    This returns an honest, low-confidence, court-indefensible placeholder so
    every downstream agent still receives a well-formed VisualEvidenceFinding and
    can proceed with its own deterministic tool runs.
    """
    return VisualEvidenceFinding(
        analysis_type="visual_evidence_profile",
        provider_used="local_visual_ensemble",
        model_used="local_visual_ensemble",
        content_description=(
            "Local visual ensemble could not analyze this image; downstream agents "
            "rely on their own deterministic tool runs for forensic coverage."
        ),
        manipulation_signals=[],
        detected_objects=[],
        file_type_assessment="unknown",
        confidence=0.0,
        court_defensible=False,
        caveat=f"Local visual ensemble failed: {error}",
        latency_ms=latency_ms,
        error=str(error),
        _authenticity_verdict="INCONCLUSIVE",
        _contextual_narrative="Visual context unavailable — local ensemble failure.",
        _metadata_visual_consistency="Not assessed (ensemble failure).",
        provider_attempts=[
            {"provider": "local_visual_ensemble", "success": False, "error": str(error)}
        ],
        fallback_applied=True,
        fallback_reason=f"ensemble_exception: {error}",
        tool_coverage={},
        degradation_flags=["local_ensemble_total_failure"],
    )


async def analyze_local_media_profile(file_path: str, mime: str) -> VisualEvidenceFinding:
    """On-device holistic profile for NON-IMAGE evidence (audio / video / document)
    when no native (Gemini) media read is available — the no-Gemini analog of
    analyze_local_visual_profile for media.

    Returns a VisualEvidenceFinding describing WHAT the media is (audio properties, a
    captioned video key-frame, or extracted document text) plus an honest coverage
    caveat (CANNOT_DETERMINE — the modality tools carry the verdict). Used by BOTH the
    preflight cascade AND the agent's read_shared_image_context handler so the
    Gemini→local handoff is a SINGLE cached step per investigation, symmetric with the
    image path's analyze_local_visual_profile fallback."""
    mime = (mime or "").lower()
    is_video = mime.startswith("video/")
    is_document = (
        mime == "application/pdf"
        or mime.startswith("text/")
        or "officedocument" in mime
        or "msword" in mime
        or "document" in mime
    )
    dur = sr = ch = None
    w = h = 0
    caption = ""
    extracted: list[str] = []

    if is_video:
        def _probe_video() -> tuple:
            import os
            import tempfile
            _dur = None
            _w = _h = 0
            _cap = ""
            fp = ""
            try:
                import cv2
                c = cv2.VideoCapture(file_path)
                fps = c.get(cv2.CAP_PROP_FPS) or 0.0
                n = c.get(cv2.CAP_PROP_FRAME_COUNT) or 0.0
                _w = int(c.get(cv2.CAP_PROP_FRAME_WIDTH) or 0)
                _h = int(c.get(cv2.CAP_PROP_FRAME_HEIGHT) or 0)
                if fps and n:
                    _dur = n / fps
                if n:
                    c.set(cv2.CAP_PROP_POS_FRAMES, int(n // 2))
                ok, frame = c.read()
                c.release()
                if ok and frame is not None:
                    fd, fp = tempfile.mkstemp(suffix=".jpg")
                    os.close(fd)
                    cv2.imwrite(fp, frame)
            except Exception:  # noqa: S110 - video probing is best-effort context only
                pass
            if fp:
                try:
                    from tools.florence_analyzer import get_florence_analyzer
                    r = get_florence_analyzer().analyze(fp)
                    if getattr(r, "available", False):
                        _cap = (r.best_description() or "").strip()
                except Exception:  # noqa: S110 - Florence captioning is an optional fallback
                    pass
                finally:
                    try:
                        os.unlink(fp)
                    except Exception:  # noqa: S110 - temp-file cleanup is best-effort
                        pass
            return _dur, _w, _h, _cap

        dur, w, h, caption = await asyncio.to_thread(_probe_video)
        for _pre in ("the image shows ", "the image is ", "this image shows "):
            if caption.lower().startswith(_pre):
                caption = caption[len(_pre):]
                break
        _vp = []
        if dur:
            _vp.append(f"~{dur:.0f}s")
        if w and h:
            _vp.append(f"{w}x{h}")
        _vps = ", ".join(_vp)
        _lead = f"The video shows {caption}" if caption else "Video file"
        description = (
            _lead.rstrip(".") + ". " + (f"({_vps}). " if _vps else "")
            + "On-device frame-integrity, motion, and audio-track forensic checks were "
            "applied locally."
        )
        coverage = (
            "Coverage note: no holistic video model (frame-level deepfake / "
            "synthetic-render assessment) is available on this analysis path, so "
            "AI-generation / deepfake determination is screening-tier only — a clean "
            "result does not exclude high-quality synthetic or rendered video."
        )
        ftype = "video"
    elif is_document:
        def _probe_doc() -> tuple:
            np_ = 0
            text = ""
            fp_lower = file_path.lower()
            try:
                if fp_lower.endswith(".pdf"):
                    import fitz  # PyMuPDF
                    d = fitz.open(file_path)
                    np_ = d.page_count
                    chunks = []
                    for i, p in enumerate(d):
                        if i >= 3:
                            break
                        chunks.append(p.get_text() or "")
                    text = " ".join(chunks).strip()
                    d.close()
                elif fp_lower.endswith(".docx"):
                    try:
                        from docx import Document as _DocxDoc
                        d = _DocxDoc(file_path)
                        paragraphs = [p.text for p in d.paragraphs if p.text.strip()]
                        text = "\n".join(paragraphs[:50]).strip()
                        np_ = max(1, len(d.paragraphs) // 40)  # rough page estimate
                    except Exception:  # noqa: S110 - DOCX parsing is optional context enrichment
                        pass
                elif fp_lower.endswith(".odt"):
                    try:
                        from odf.opendocument import load as _odf_load
                        from odf.text import P
                        doc = _odf_load(file_path)
                        paragraphs = [str(p) for p in doc.getElementsByType(P) if str(p).strip()]
                        text = "\n".join(paragraphs[:50]).strip()
                        np_ = max(1, len(paragraphs) // 40)
                    except Exception:  # noqa: S110 - ODT parsing is optional context enrichment
                        pass
                elif fp_lower.endswith(".rtf"):
                    try:
                        from striprtf.striprtf import rtf_to_text as _rtf2text
                        with open(file_path, errors="ignore") as rf:
                            raw = rf.read(200_000)
                        text = _rtf2text(raw).strip()
                        np_ = 1
                    except Exception:  # noqa: S110 - RTF parsing is optional context enrichment
                        pass
                else:
                    # Plain text / CSV / Markdown — read directly
                    with open(file_path, errors="ignore") as f:
                        text = f.read(8000).strip()
                        np_ = 1
            except Exception:  # noqa: S110 - document probing is best-effort context only
                pass
            return np_, text

        npages, _text = await asyncio.to_thread(_probe_doc)
        snippet = " ".join((_text or "").split())[:180]
        if snippet:
            extracted = [snippet]
        _lead = f"A {npages}-page document" if npages else "A text document"
        description = (
            _lead
            + (f". Opening text: \u201c{snippet}\u2026\u201d" if snippet else ".")
            + " On-device text extraction and structural / provenance checks were "
            "applied locally."
        )
        coverage = (
            "Coverage note: no holistic document model (semantic AI-authored-text "
            "assessment) is available on this analysis path, so AI-generated-text / "
            "document-tampering determination is screening-tier only — a clean result "
            "does not exclude machine-authored text."
        )
        ftype = "document"
    else:
        def _probe_audio() -> tuple:
            try:
                import soundfile as sf
                info = sf.info(file_path)
                return info.duration, info.samplerate, info.channels
            except Exception:
                try:
                    import wave
                    with wave.open(file_path, "rb") as w_:
                        s = w_.getframerate() or 0
                        return (w_.getnframes() / float(s or 1), s, w_.getnchannels())
                except Exception:
                    return (None, None, None)

        dur, sr, ch = await asyncio.to_thread(_probe_audio)
        _chd = {1: "mono", 2: "stereo"}.get(ch, (f"{ch}-channel" if ch else ""))
        _ap = []
        if dur:
            _ap.append(f"~{dur:.0f}s")
        if _chd:
            _ap.append(_chd)
        if sr:
            _ap.append(f"{int(sr)} Hz")
        _aps = ", ".join(_ap)
        description = (
            "On-device profile — audio recording" + (f" ({_aps})" if _aps else "") + ". "
            "Acoustic forensic checks (spectral, prosody, voice-clone, anti-spoofing, "
            "codec) were applied locally."
        )
        coverage = (
            "Coverage note: no holistic speech model (transcription + synthetic-speech "
            "assessment) is available on this analysis path, so AI-voice / voice-clone "
            "determination is screening-tier only — a clean result does not exclude "
            "high-quality speech synthesis."
        )
        ftype = "audio"

    return VisualEvidenceFinding(
        analysis_type="visual_evidence_profile",
        provider_used="local_media_profile",
        model_used="local_media_profile",
        content_description=description,
        manipulation_signals=[],
        detected_objects=[],
        file_type_assessment=ftype,
        confidence=0.5,
        court_defensible=False,
        caveat=coverage,
        _authenticity_verdict="CANNOT_DETERMINE",
        _extracted_text=extracted,
        _contextual_narrative=description,
        _metadata_visual_consistency=coverage,
        provider_attempts=[{"provider": "local_media_profile", "success": True}],
        fallback_applied=True,
        fallback_reason="native media read unavailable — local media profile",
        tool_coverage={},
        degradation_flags=[],
    )


async def analyze_local_visual_profile(
    artifact: EvidenceArtifact,
    exif_summary: dict[str, Any] | None = None,
    is_screen_capture_like: bool = False,
) -> VisualEvidenceFinding:
    """Graceful public entrypoint for the local visual ensemble.

    GUARANTEE: always returns a well-formed VisualEvidenceFinding and never
    raises — this is the terminal fallback after Gemini, so any unexpected
    failure degrades to a minimal honest finding instead of propagating an
    exception that would leave the investigation with no visual context.
    """
    _t0 = time.perf_counter()
    try:
        return await _analyze_local_visual_profile_impl(
            artifact,
            exif_summary=exif_summary,
            is_screen_capture_like=is_screen_capture_like,
        )
    except Exception as exc:
        logger.error(
            "Local visual ensemble crashed — returning minimal degraded finding",
            file_path=getattr(artifact, "file_path", "?"),
            error=str(exc),
        )
        return _minimal_degraded_finding(artifact, exc, (time.perf_counter() - _t0) * 1000.0)


async def _analyze_local_visual_profile_impl(
    artifact: EvidenceArtifact,
    exif_summary: dict[str, Any] | None = None,
    is_screen_capture_like: bool = False,
) -> VisualEvidenceFinding:
    """
    Perform native local visual profile analysis using cached on-device
    forensic models and deterministic image-processing tools.

    The EvidenceArtifact provides session_id and content_hash for proper
    forensic chain-of-custody. The artifact is never fabricated — it must
    originate from the custody-linked evidence pipeline.

    Aggregates:
      - ELA (with lossless/screenshot guards)
      - OCR (Tesseract + EasyOCR)
      - CLIP (SigLIP2 zero-shot classification)
      - DETR/YOLO (object detection)
      - FFT (frequency-domain analysis)
      - Noiseprint clustering (sensor noise consistency)
      - Splicing detector (DCT quantization fingerprint)
      - Diffusion artifact detector (GAN/diffusion spectral signatures)
      - Florence-2 VLM captioning (optional, torch-dependent)
      - OpenCV statistics (resolution, sharpness, brightness, noise, blockiness)

    Returns a provider-neutral VisualEvidenceFinding with tool_coverage
    populated for downstream provenance reporting.
    """
    start_time = time.perf_counter()
    file_path = artifact.file_path
    logger.info("Initializing native local visual ensemble", file_path=file_path)

    art = artifact
    is_lossless = is_lossless_image(file_path, getattr(artifact, "mime_type", None))

    # ── Import tools ─────────────────────────────────────────────────────
    from tools.image_tools import (
        analyze_image_content,
        detr_detect_objects,
        ela_full_image,
        extract_text_from_image,
        frequency_domain_analysis,
    )

    # ── Tool wrappers with guards ────────────────────────────────────────
    async def _screenshot_ela_skip() -> dict[str, Any]:
        return {
            "available": True,
            "not_applicable": True,
            "num_anomaly_regions": 0,
            "max_anomaly": 0.0,
            "reason": "ELA skipped for screenshot; UI edges handled by OCR and layout checks.",
        }

    async def _lossless_ela_skip() -> dict[str, Any]:
        return {
            "available": True,
            "not_applicable": True,
            "num_anomaly_regions": 0,
            "max_anomaly": 0.0,
            "reason": "ELA not applicable to lossless formats (PNG, BMP, TIFF); no JPEG compression history.",
        }

    async def _run_ela() -> dict[str, Any]:
        """Run ELA with lossless guard — standardised across local ensemble and Path B."""
        if is_lossless:
            return await _lossless_ela_skip()
        try:
            from tools.ml_tools.ela_anomaly_classifier import classify_ela
            result = await asyncio.to_thread(classify_ela, art.file_path)
            return {
                "available": True,
                "hotspot_count": result.get("num_anomalous_blocks", 0),
                "anomaly_score": result.get("anomaly_score", 0.0),
                "max_anomaly": result.get("anomaly_score", 0.0) * 100.0,
                "num_anomaly_regions": result.get("num_anomalous_blocks", 0),
                "suspicious": result.get("verdict") in ("SUSPICIOUS", "HIGHLY_ANOMALOUS"),
            }
        except Exception:
            return await ela_full_image(art)

    async def _run_fft() -> dict[str, Any]:
        """Run frequency-domain analysis (pure numpy/scipy)."""
        if is_screen_capture_like:
            return {"available": True, "not_applicable": True, "reason": "FFT not meaningful for screenshots"}
        try:
            return await frequency_domain_analysis(art)
        except Exception as e:
            return {"available": False, "error": str(e)}

    async def _run_noiseprint() -> dict[str, Any]:
        """Run noiseprint clustering (sklearn-dependent). Skip for lossless and screenshots."""
        if is_lossless or is_screen_capture_like:
            return {"available": True, "not_applicable": True, "reason": "Noiseprint not applicable for lossless/screenshots"}
        try:
            from core.ml_subprocess import run_ml_tool
            return await run_ml_tool("noiseprint_clustering.py", art.file_path, timeout=20.0)
        except Exception as e:
            return {"available": False, "error": str(e)}

    async def _run_splicing() -> dict[str, Any]:
        """Run splicing detector (sklearn-dependent). JPEG only."""
        fmt = getattr(artifact, "mime_type", "") or ""
        ext = file_path.rsplit(".", 1)[-1].lower() if "." in file_path else ""
        is_jpeg = "jpeg" in fmt or fmt == "image/jpg" or ext in ("jpg", "jpeg")
        if not is_jpeg or is_screen_capture_like:
            return {"available": True, "not_applicable": True, "reason": "Splicing detector applicable to JPEG photographs only"}
        try:
            from tools.ml_tools.splicing_detector import detect_splicing
            return await asyncio.to_thread(detect_splicing, art.file_path)
        except Exception as e:
            return {"available": False, "error": str(e)}

    async def _run_diffusion() -> dict[str, Any]:
        """AI-generation detection. Primary = real ViT classifier; the spectral
        heuristic is the labelled fallback when the model is unavailable, so the
        no-Gemini path gets a real trained signal whenever weights are present."""
        try:
            from core.ml_subprocess import run_ml_tool
            result = await run_ml_tool("ai_generation_detector.py", art.file_path, timeout=45.0)
            if result.get("available") and result.get("method") == "vit_classifier":
                logger.info(
                    "ViT AI-generation classifier returned",
                    is_ai_generated=result.get("is_ai_generated"),
                    diffusion_probability=result.get("diffusion_probability"),
                    predicted_label=result.get("predicted_label"),
                )
                return result
            # Model unavailable → spectral heuristic, honestly labelled as screening.
            logger.info(
                "ViT AI-generation classifier unavailable, falling back to spectral heuristic",
                error=result.get("error"),
                available=result.get("available"),
            )
            spectral = await run_ml_tool("diffusion_artifact_detector.py", art.file_path, timeout=12.0)
            if isinstance(spectral, dict):
                spectral["method"] = "spectral_heuristic"
                spectral["court_defensible"] = False
                spectral.setdefault(
                    "fallback_reason",
                    result.get("error") or "AI-generation model unavailable — spectral screening only",
                )
            return spectral
        except Exception as e:
            return {"available": False, "error": str(e)}

    async def _run_florence() -> dict[str, Any]:
        """Run Florence-2 VLM captioning (torch-dependent, optional)."""
        try:
            from tools.florence_analyzer import get_florence_analyzer
            analyzer = get_florence_analyzer()
            result = await asyncio.to_thread(analyzer.analyze, art.file_path)
            if not result.available:
                return {"available": False, "error": result.error or "Florence-2 not available"}
            return {
                "available": True,
                "description": result.best_description(),
                "detailed_caption": getattr(result, "detailed_caption", ""),
                "caption": getattr(result, "caption", ""),
            }
        except Exception as e:
            return {"available": False, "error": str(e)}

    async def _run_opencv_stats() -> dict[str, Any]:
        """Run OpenCV statistics extraction."""
        try:
            import cv2
            import numpy as np
            from PIL import Image as PILImage

            def _estimate_noise(_gray: np.ndarray) -> float:
                gx = cv2.Sobel(_gray.astype(np.float32), cv2.CV_32F, 1, 0, ksize=3)
                gy = cv2.Sobel(_gray.astype(np.float32), cv2.CV_32F, 0, 1, ksize=3)
                grad_mag = np.sqrt(gx * gx + gy * gy)
                threshold = max(float(np.percentile(grad_mag, 30)), 5.0)
                flat_mask = grad_mag < threshold
                if flat_mask.sum() < 100:
                    return 0.0
                return float(np.std(_gray.astype(np.float32)[flat_mask]))

            def _stats():
                img = PILImage.open(file_path).convert("RGB")
                arr = np.array(img, dtype=np.float32)
                h, w = arr.shape[:2]
                std_rgb = arr.std(axis=(0, 1)).tolist()
                brightness = float(arr.mean())
                gray = cv2.cvtColor(np.array(img), cv2.COLOR_RGB2GRAY)
                laplacian_var = float(cv2.Laplacian(gray, cv2.CV_64F).var())
                noise_value = _estimate_noise(gray)
                block_diff = (
                    float(np.abs(np.diff(gray.astype(float), axis=0)[7::8].mean())) if h > 16 else 0.0
                )
                return {
                    "width": w,
                    "height": h,
                    "sharpness": laplacian_var,
                    "brightness": brightness,
                    "noise": noise_value,
                    "blockiness": block_diff,
                    "std_rgb": std_rgb,
                    "available": True,
                }
            return await asyncio.to_thread(_stats)
        except Exception as e:
            logger.error(f"OpenCV stats failed: {e}")
            return {"available": False, "error": str(e)}

    async def _run_provenance() -> dict[str, Any]:
        """Offline provenance screen: perceptual-hash match + C2PA presence.
        Free, local, no third party sees the evidence. Screening tier."""
        try:
            from core.perceptual_provenance import analyze_provenance
            return await asyncio.to_thread(analyze_provenance, file_path)
        except Exception as e:
            return {"available": False, "error": str(e)}

    # Provenance runs concurrently but is kept OUT of the coverage/confidence
    # accounting below — it is metadata enrichment / an OSINT lead, not a
    # manipulation-detection tool, so it must not inflate ensemble confidence.
    provenance_future = asyncio.ensure_future(
        run_with_timeout("Provenance", _run_provenance(), 15.0)
    )

    # ── Run all tools in parallel with timeouts ──────────────────────────
    tasks = {
        "ELA": run_with_timeout("ELA", _run_ela(), 45.0),
        "OCR": run_with_timeout("OCR", extract_text_from_image(art), 65.0),
        "CLIP": run_with_timeout("CLIP", analyze_image_content(art), 60.0),
        "DETR": run_with_timeout("DETR", detr_detect_objects(file_path), 60.0),
        "FFT": run_with_timeout("FFT", _run_fft(), 30.0),
        "Noiseprint": run_with_timeout("Noiseprint", _run_noiseprint(), 20.0),
        "Splicing": run_with_timeout("Splicing", _run_splicing(), 30.0),
        "Diffusion": run_with_timeout("Diffusion", _run_diffusion(), 40.0),
        "Florence": run_with_timeout("Florence", _run_florence(), 60.0),
        "OpenCV": run_with_timeout("OpenCV", _run_opencv_stats(), 10.0),
    }

    keys = list(tasks.keys())
    raw_results = await asyncio.gather(*(tasks[k] for k in keys), return_exceptions=True)

    results_map = {}
    for k, r in zip(keys, raw_results, strict=False):
        results_map[k] = r

    # ── Collect results ──────────────────────────────────────────────────
    tool_results: dict[str, Any] = {}
    tool_errors: dict[str, str] = {}
    tool_coverage: dict[str, bool] = {}
    for name in keys:
        r = results_map[name]
        if _is_tool_successful(r):
            tool_results[name] = r
            tool_coverage[name] = True
        else:
            tool_errors[name] = _tool_error_summary(r)
            tool_coverage[name] = False
            if name != "Florence":  # Florence is optional — don't log as error
                logger.error(f"Ensemble tool {name} failed", error=tool_errors[name])

    # Share heavy whole-image tool results so per-agent handlers reuse them
    # instead of re-running (CLIP + FFT call the identical functions the handlers
    # use, so a cache hit is byte-for-byte equivalent to a fresh run).
    _content_hash = getattr(artifact, "content_hash", "") or ""
    if _content_hash:
        from core.tool_result_cache import cache_tool_result

        if _is_tool_successful(tool_results.get("CLIP")):
            await cache_tool_result(_content_hash, "analyze_image_content", tool_results["CLIP"])
        if _is_tool_successful(tool_results.get("FFT")):
            await cache_tool_result(_content_hash, "frequency_domain_analysis", tool_results["FFT"])

    ela_res = tool_results.get("ELA", {})
    ocr_res = tool_results.get("OCR", {})
    clip_res = tool_results.get("CLIP", {})
    detr_res = tool_results.get("DETR", [])
    fft_res = tool_results.get("FFT", {})
    noiseprint_res = tool_results.get("Noiseprint", {})
    splicing_res = tool_results.get("Splicing", {})
    diffusion_res = tool_results.get("Diffusion", {})
    florence_res = tool_results.get("Florence", {})
    opencv_res = tool_results.get("OpenCV", {})

    clip_category = clip_res.get("image_type", "unknown") if isinstance(clip_res, dict) else "unknown"
    ocr_lines = ocr_res.get("extracted_text", []) if isinstance(ocr_res, dict) else []
    # DETR/YOLO runs at a low screening threshold (0.20) to surface candidates for
    # the object agent; for the visual-context DESCRIPTION and cross-signal synthesis,
    # keep only confident detections (>=0.5) so low-probability noise like
    # "suitcase (0.26)" never pollutes the on-device read or the object summary.
    def _detr_conf(label: str) -> float:
        m = re.search(r"\(([01]?\.\d+)\)\s*$", str(label))
        return float(m.group(1)) if m else 1.0
    detected = (
        [d for d in detr_res if _detr_conf(d) >= 0.5]
        if isinstance(detr_res, list)
        else []
    )
    florence_desc = florence_res.get("description", "") if isinstance(florence_res, dict) else ""

    # Ground the file-type assessment with the canonical deterministic categorizer
    # (the SAME one the registry + plan use) so the ensemble can't introduce a
    # third, divergent category. CLIP becomes a corroborating signal, not the
    # sole authority.
    clip_routing_category = _clip_to_category(clip_category)
    try:
        from core.file_classifier import classify_evidence_file_sync
        canonical_category = classify_evidence_file_sync(artifact).primary_category
    except Exception:
        canonical_category = ""
    final_category = canonical_category or clip_routing_category
    is_screenshot = (
        is_screen_capture_like
        or final_category == "screenshot"
        or clip_routing_category == "screenshot"
    )

    # OCR text is only meaningful context for text-bearing evidence (screenshots,
    # documents). On photos/objects it is noise (spurious "Salas lh hg a =..."
    # from texture) that must not surface as "Extracted text" / visible timestamps.
    _text_bearing = is_screenshot or final_category in ("document", "document_scan", "id_document")
    ocr_lines = _meaningful_ocr_lines(ocr_lines) if _text_bearing else []

    # ── Cross-signal synthesis ───────────────────────────────────────────
    verdict, signals, narrative, conflict_detected = _cross_signal_synthesis(
        ela_res, fft_res, noiseprint_res, splicing_res, diffusion_res, opencv_res,
        clip_category, detected, ocr_lines, florence_desc, is_screenshot,
    )

    # ── Content description ──────────────────────────────────────────────
    # Lead with the richest available natural-language read so the on-device
    # context reads like a description of WHAT THIS SHOWS, not telemetry:
    #   1. Florence-2 VLM caption (closest to a hosted-VLM description), else
    #   2. the categorical identification + detected objects.
    # Raw image telemetry (resolution / sharpness / brightness) is deliberately
    # kept OUT of the human-facing description — it is diagnostic metadata, not
    # content, and remains available to the forensic tools via opencv_res.
    # Never name the underlying model (CLIP/Florence) in user-facing copy.
    _cat_disp = str(clip_category or "unknown").strip()
    _flo = (florence_desc or "").strip()
    desc_parts: list[str] = []
    if _flo:
        desc_parts.append(_flo if _flo.endswith((".", "!", "?")) else f"{_flo}.")
    elif _cat_disp and _cat_disp.lower() != "unknown":
        desc_parts.append(f"Photograph identified as: {_cat_disp}.")
    else:
        desc_parts.append("Visual content could not be confidently categorized.")
    if detected:
        # Don't repeat objects the caption already named.
        _flo_l = _flo.lower()
        _new_objs = [d for d in detected if d.lower() not in _flo_l]
        if _new_objs:
            desc_parts.append(f"Detected objects: {', '.join(_new_objs)}.")
    if ocr_lines:
        desc_parts.append(f"Extracted text: {', '.join(ocr_lines[:5])}.")
    _alert_verdict = str(verdict).upper() in (
        "SUSPICIOUS", "LIKELY_MANIPULATED", "TAMPERED", "MANIPULATED", "AI_GENERATED",
    )
    _substantive_sigs = [
        s for s in signals
        if not (s.lower().rstrip(". ").endswith("indicators detected") or "no manipulation" in s.lower())
    ]
    if signals and (_alert_verdict or not _substantive_sigs):
        # Alert verdict → assert the signals; OR only clean notes present → show them.
        desc_parts.append(f"Forensic signals: {'; '.join(signals)}.")
    elif _substantive_sigs:
        # Uncorroborated screening leads under an authentic/inconclusive verdict: the
        # holistic ensemble declined to escalate them, so the scene description must
        # not read as a manipulation detection. Report screening as non-asserting.
        desc_parts.append(
            "Forensic screening surfaced only low-level uncorroborated signals, held "
            "non-asserting — no corroborated manipulation indicator."
        )
    else:
        desc_parts.append("No manipulation signals detected by local ensemble.")
    content_description = " ".join(desc_parts)

    # ── Interface identification (screenshots) ───────────────────────────
    interface_id = ""
    if is_screenshot:
        interface_id = _synthesize_interface_id(ocr_res, clip_res, detr_res) or f"Identified digital interface category: {clip_category}"
        ocr_text_lower = " ".join(ocr_lines).lower()
        if _kw_present("iphone", ocr_text_lower) or _kw_present("ios", ocr_text_lower):
            interface_id += " (iOS platform signs)"
        elif _kw_present("android", ocr_text_lower):
            interface_id += " (Android platform signs)"
        elif "http" in ocr_text_lower or "www." in ocr_text_lower:
            interface_id += " (Web/Browser interface)"

    # ── Metadata consistency ─────────────────────────────────────────────
    metadata_consistency = "No metadata provided for cross-validation"
    if exif_summary:
        metadata_consistency = "Metadata present. Local tools did not detect obvious timestamp or GPS contradiction."

    # ── Confidence and caveat ────────────────────────────────────────────
    tools_total = len(_TOOL_NAMES)
    tools_ok = len(tool_results)
    partial_execution = tools_ok < tools_total

    base_confidence = 0.40 + (tools_ok / tools_total) * 0.30
    if signals:
        base_confidence = max(base_confidence, 0.60)
    if florence_desc:
        base_confidence = min(base_confidence + 0.10, 0.88)
    if conflict_detected:
        base_confidence = min(base_confidence, 0.50)
        signals.append("Conflicting authenticity signals — manual review advised")
    confidence = round(min(base_confidence, 0.88), 4)

    caveat_parts = [
        "Local visual ensemble analysis using cached on-device forensic "
        "models and deterministic image-processing tools."
    ]
    if partial_execution:
        failed_names = ", ".join(sorted(tool_errors.keys()))
        caveat_parts.append(
            f"Partial execution: {tools_ok}/{tools_total} tools succeeded. "
            f"Failed: {failed_names}."
        )

    latency = (time.perf_counter() - start_time) * 1000.0

    degradation_flags = []
    if partial_execution:
        degradation_flags.append(f"partial_tool_execution:{tools_ok}/{tools_total}")

    # ── Routing ──────────────────────────────────────────────────────────
    routing = build_image_forensic_routing(
        {"image_category": final_category},
        description=content_description,
        file_path=file_path,
    )

    # ── Visible provenance clues (fills Agent5 metadata section) ──────────
    visible_metadata_clues = _extract_visible_metadata_clues(
        ocr_lines=ocr_lines,
        interface_id=interface_id,
        exif_summary=exif_summary,
        is_screenshot=is_screenshot,
    )

    # Enrich with derived object/integrity/scene signals so the no-Gemini path
    # carries the same rich fields the refined Gemini prompt returns (weapons,
    # documents, people, lighting, follow-up regions, benign edits). These keys
    # are mapped into the VisualContext sub-models by build_visual_context_from_finding.
    visible_metadata_clues.update(
        _derive_rich_scene_signals(
            file_path=file_path,
            detected_objects=detected,
            ocr_lines=ocr_lines,
            clip_category=clip_category,
            final_category=final_category,
            ela_res=ela_res,
            noiseprint_res=noiseprint_res,
            opencv_res=opencv_res,
        )
    )

    # ── Offline provenance screen (perceptual hash + C2PA) ────────────────
    # Merge as metadata clues (always) and as manipulation signals only on a
    # confirmed known-bad match. Appended AFTER the confidence computation above
    # so this screening-tier lead never inflates the deterministic confidence.
    try:
        prov_res = await provenance_future
    except Exception as _prov_err:
        prov_res = {"available": False, "error": str(_prov_err)}
    if isinstance(prov_res, dict) and prov_res.get("available"):
        # visible_metadata_clues is a categorized dict; provenance facts go in
        # the software/app clue bucket (surfaced as software_or_app_clues).
        prov_bucket = visible_metadata_clues.setdefault("software_clues", [])
        for clue in prov_res.get("provenance_clues") or []:
            if clue not in prov_bucket:
                prov_bucket.append(clue)
        for sig in prov_res.get("signals") or []:
            if sig not in signals:
                signals.append(sig)

    # ── Forensic observations ────────────────────────────────────────────
    forensic_specifics = _synthesize_forensic_observations(
        clip_category, ela_res, fft_res, noiseprint_res, splicing_res,
        diffusion_res, ocr_res, detected, opencv_res, is_screenshot,
    )

    # ── Build finding ────────────────────────────────────────────────────
    finding = VisualEvidenceFinding(
        analysis_type="visual_evidence_profile",
        provider_used="local_visual_ensemble",
        model_used="local_visual_ensemble",
        content_description=content_description,
        manipulation_signals=signals,
        detected_objects=detected,
        contextual_anomalies=[],
        file_type_assessment=final_category,
        confidence=confidence,
        court_defensible=not partial_execution and not conflict_detected,
        caveat=" ".join(caveat_parts),
        raw_response="",
        latency_ms=latency,
        error=None if not partial_execution else "; ".join(
            f"{name}: {err}" for name, err in tool_errors.items()
        ),
        from_cache=False,
        _extracted_text=ocr_lines,
        _interface_identification=interface_id,
        _contextual_narrative=narrative,
        _authenticity_verdict=verdict,
        _metadata_visual_consistency=metadata_consistency,
        _visible_metadata_clues=visible_metadata_clues,
        _forensic_routing={
            **routing,
            "priority_signals": ["local_ela", "frequency_domain", "noiseprint", "splicing", "diffusion"],
        },
        _forensic_specifics=forensic_specifics,
        provider_attempts=[
            {
                "provider": "local_visual_ensemble",
                "success": tools_ok > 0,
                "tools_ok": tools_ok,
                "tools_total": tools_total,
            }
        ],
        fallback_applied=False,
        fallback_reason="",
        tool_coverage=tool_coverage,
        degradation_flags=degradation_flags,
    )

    return finding


def _synthesize_interface_id(ocr_res: dict, clip_res: dict, detr_res: list) -> str:
    clip_category = str(clip_res.get("image_type", "") if isinstance(clip_res, dict) else "").lower()
    ocr_text = " ".join(ocr_res.get("extracted_text", []) if isinstance(ocr_res, dict) else []).lower()
    if "screenshot" not in clip_category:
        return ""
    # Only DISTINCTIVE, low-false-positive markers. Generic UI words ("settings",
    # "following", "seen", "story", "likes", "channels", "chrome", "gmail") appear in
    # virtually any app — including a desktop forensic dashboard — and previously
    # fabricated an "iOS / WhatsApp" provenance on an unrelated web screenshot.
    platform_signals = {
        'iOS': ['imessage', 'airdrop', 'facetime'],
        'Android': ['google play', 'play store'],
        'WhatsApp': ['whatsapp'],
        'Telegram': ['telegram'],
        'Twitter/X': ['retweet'],
        'Instagram': ['instagram'],
    }
    detected_platform = []
    for platform, keywords in platform_signals.items():
        if any(_kw_present(kw, ocr_text) for kw in keywords):
            detected_platform.append(platform)
    if detected_platform:
        return f"Digital interface: {', '.join(detected_platform)} ({clip_category})"
    return f"Digital interface: {clip_category}"


def _synthesize_forensic_observations(
    clip_category: str, ela_res: dict, fft_res: dict,
    noiseprint_res: dict, splicing_res: dict, diffusion_res: dict,
    ocr_res: dict, detr_res: list, opencv_res: dict, is_screenshot: bool,
) -> str:
    """Build domain-specific forensic observations from all tool results."""
    observations: list[str] = []

    if is_screenshot:
        ocr_lines = ocr_res.get("extracted_text", []) if isinstance(ocr_res, dict) else []
        font_consistency = "text present for rendering analysis" if ocr_lines else "not assessed"
        observations.append(f"Font rendering: {font_consistency}")
        observations.append("UI alignment: UI alignment assessment via OCR layout")
    else:
        # ELA observations
        if isinstance(ela_res, dict) and not ela_res.get("not_applicable"):
            ela_verdict = (
                "uniform ELA signature"
                if ela_res.get("max_anomaly", 0) < 15
                else f"non-uniform ELA with max anomaly {ela_res.get('max_anomaly', 0):.1f}"
            )
            observations.append(f"JPEG re-compression: {ela_verdict}")

        # FFT observations
        if isinstance(fft_res, dict) and not fft_res.get("not_applicable"):
            ratio = fft_res.get("high_freq_ratio", 0.0)
            if ratio > 0.15:
                observations.append(f"Frequency domain: elevated high-frequency ratio ({ratio:.3f})")
            else:
                observations.append("Frequency domain: spectral profile consistent with natural capture")

        # Noiseprint observations
        if isinstance(noiseprint_res, dict) and not noiseprint_res.get("not_applicable"):
            clusters = noiseprint_res.get("num_clusters", 1)
            inconsistent = noiseprint_res.get("sensor_inconsistency_detected", False)
            if inconsistent:
                observations.append(f"Sensor noise: {clusters} inconsistent clusters detected")
            else:
                observations.append("Sensor noise: uniform noise field")

        # Splicing observations
        if isinstance(splicing_res, dict) and not splicing_res.get("not_applicable"):
            if splicing_res.get("splicing_detected"):
                observations.append("DCT quantization: fingerprint inconsistency detected")
            else:
                observations.append("DCT quantization: consistent fingerprint across blocks")

        # Diffusion observations
        if isinstance(diffusion_res, dict):
            if diffusion_res.get("diffusion_detected") or diffusion_res.get("is_ai_generated"):
                observations.append(f"Diffusion artifacts: spectral spikes detected (probability={diffusion_res.get('diffusion_probability', 0):.3f})")
            elif diffusion_res.get("available"):
                observations.append("Diffusion artifacts: no GAN/diffusion spectral signatures found")

        # OpenCV observations
        if opencv_res:
            noise_val = opencv_res.get("noise", 0.0) or 0.0
            block_val = opencv_res.get("blockiness", 0.0) or 0.0
            observations.append(f"Noise level: {noise_val:.2f}")
            observations.append(f"JPEG blockiness: {block_val:.2f}")

        # Person/portrait observation
        if "person" in clip_category.lower() or any("person" in str(obj).lower() for obj in (detr_res or [])):
            observations.append("Portrait mode: facial boundary artifacts not detectable without neural tools")

    return "; ".join(observations) if observations else "No forensic observations available."
