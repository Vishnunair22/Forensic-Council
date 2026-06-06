"""
File Type Policy
================

Single source of truth for supported MIME types, file extensions, and
agent-level file-type capabilities across the Forensic Council product.

Supported file categories and their active agents:
  Images   (JPEG/PNG/TIFF/WEBP/GIF/BMP) → Agent1 + Agent3 + Agent5
  Audio    (MP3/WAV/FLAC/AAC/OGG/M4A)   → Agent2 + Agent5
  Video    (MP4/WEBM/MOV/AVI/MKV)       → Agent4 + Agent5
  Documents (PDF)                        → Agent5

Audio and video agents run at reduced capability when ENABLE_AUDIO_MODELS /
ENABLE_VIDEO_MODELS are false — Agent5 (Metadata) always provides exiftool
analysis for every supported type regardless of model flags.
"""

from __future__ import annotations

from typing import Any

# ── Supported MIME types (authoritative allow-list) ──────────────────────
SUPPORTED_MIME_TYPES: frozenset[str] = frozenset({
    # ── Images ──
    "image/jpeg",
    "image/png",
    "image/tiff",
    "image/webp",
    "image/gif",
    "image/bmp",

    # ── Audio ──
    "audio/mpeg",        # MP3
    "audio/wav",         # WAV
    "audio/x-wav",       # WAV (alternate)
    "audio/flac",        # FLAC
    "audio/x-flac",      # FLAC (alternate)
    "audio/aac",         # AAC
    "audio/ogg",         # OGG/Vorbis
    "audio/mp4",         # M4A (AAC in MP4 container)
    "audio/x-m4a",       # M4A (alternate)

    # ── Video ──
    "video/mp4",         # MP4 / M4V
    "video/mpeg",        # MPEG-1/2
    "video/webm",        # WebM (VP8/VP9/AV1)
    "video/quicktime",   # MOV
    "video/x-msvideo",   # AVI
    "video/x-matroska",  # MKV
    # libmagic sometimes reports branded/fragmented MP4 containers as the
    # generic application/mp4 rather than video/mp4. Accept it as a video
    # container so legitimate MP4s are not falsely rejected.
    "application/mp4",   # ambiguous MP4 container (libmagic generic)

    # ── Documents ──
    "application/pdf",   # PDF
})


# ── Extension → MIME mapping ─────────────────────────────────────────────
_EXTENSION_MAP: dict[str, str] = {
    # Images
    ".jpg":  "image/jpeg",
    ".jpeg": "image/jpeg",
    ".png":  "image/png",
    ".tif":  "image/tiff",
    ".tiff": "image/tiff",
    ".webp": "image/webp",
    ".gif":  "image/gif",
    ".bmp":  "image/bmp",

    # Audio
    ".mp3":  "audio/mpeg",
    ".wav":  "audio/wav",
    ".flac": "audio/flac",
    ".aac":  "audio/aac",
    ".ogg":  "audio/ogg",
    ".m4a":  "audio/x-m4a",

    # Video
    ".mp4":  "video/mp4",
    ".m4v":  "video/mp4",
    ".mpeg": "video/mpeg",
    ".mpg":  "video/mpeg",
    ".webm": "video/webm",
    ".mov":  "video/quicktime",
    ".avi":  "video/x-msvideo",
    ".mkv":  "video/x-matroska",

    # Documents
    ".pdf":  "application/pdf",
}

SUPPORTED_EXTENSIONS: frozenset[str] = frozenset(_EXTENSION_MAP.keys())


# ── Exact MIME → valid-extension set (content-vs-extension mismatch guard) ──
EXACT_MIME_EXT_MAP: dict[str, frozenset[str]] = {
    # Images
    "image/jpeg":          frozenset({".jpg", ".jpeg"}),
    "image/png":           frozenset({".png"}),
    "image/gif":           frozenset({".gif"}),
    "image/webp":          frozenset({".webp"}),
    "image/bmp":           frozenset({".bmp"}),
    "image/tiff":          frozenset({".tif", ".tiff"}),

    # Audio
    "audio/mpeg":          frozenset({".mp3"}),
    "audio/wav":           frozenset({".wav"}),
    "audio/x-wav":         frozenset({".wav"}),
    "audio/flac":          frozenset({".flac"}),
    "audio/x-flac":        frozenset({".flac"}),
    "audio/aac":           frozenset({".aac"}),
    "audio/ogg":           frozenset({".ogg"}),
    # audio-only MP4 containers may carry a .mp4 OR .m4a extension
    "audio/mp4":           frozenset({".m4a", ".mp4"}),
    "audio/x-m4a":         frozenset({".m4a", ".mp4"}),

    # Video
    "video/mp4":           frozenset({".mp4", ".m4v"}),
    "video/mpeg":          frozenset({".mpeg", ".mpg"}),
    "video/webm":          frozenset({".webm"}),
    "video/quicktime":     frozenset({".mov"}),
    "video/x-msvideo":     frozenset({".avi"}),
    "video/x-matroska":    frozenset({".mkv"}),
    # generic MP4 container (libmagic ambiguity) — accept the MP4-family extensions
    "application/mp4":     frozenset({".mp4", ".m4v", ".m4a"}),

    # Documents
    "application/pdf":     frozenset({".pdf"}),
}


def get_mime_for_extension(ext: str) -> str | None:
    """Return the authoritative MIME type for a lowercased extension (with dot)."""
    return _EXTENSION_MAP.get(ext.lower())


# ── Agent-level file-type capabilities ───────────────────────────────────
# mime_prefixes is checked with str.startswith — order does not matter.
# "application/pdf" is listed as a full string rather than a prefix so that
# other application/* types are not accidentally included.
AGENT_FILE_CAPABILITIES: dict[str, dict[str, Any]] = {
    "Agent1": {
        "mime_prefixes": ["image/"],
        "extensions": [".jpg", ".jpeg", ".png", ".gif", ".bmp", ".tiff", ".tif", ".webp"],
    },
    "Agent2": {
        "mime_prefixes": ["audio/"],
        "extensions": [".mp3", ".wav", ".flac", ".aac", ".ogg", ".m4a"],
    },
    "Agent3": {
        "mime_prefixes": ["image/"],
        "extensions": [".jpg", ".jpeg", ".png", ".gif", ".bmp", ".tiff", ".tif", ".webp"],
    },
    "Agent4": {
        "mime_prefixes": ["video/"],
        # Generic MP4 container (libmagic ambiguity) routes to video forensics too.
        "full_mimes": ["application/mp4"],
        "extensions": [".mp4", ".m4v", ".mpeg", ".mpg", ".webm", ".mov", ".avi", ".mkv"],
    },
    "Agent5": {
        # Metadata expert handles every supported format — exiftool reads all.
        "mime_prefixes": ["image/", "audio/", "video/"],
        "full_mimes": ["application/pdf", "application/mp4"],
        "extensions": [
            ".jpg", ".jpeg", ".png", ".gif", ".bmp", ".tiff", ".tif", ".webp",
            ".mp3", ".wav", ".flac", ".aac", ".ogg", ".m4a",
            ".mp4", ".m4v", ".mpeg", ".mpg", ".webm", ".mov", ".avi", ".mkv",
            ".pdf",
        ],
    },
}


def get_applicable_agents(mime_type: str) -> list[str]:
    """Return ordered list of agent IDs that support the given MIME type."""
    mime_lower = mime_type.lower()
    applicable: list[str] = []
    for agent_id, caps in AGENT_FILE_CAPABILITIES.items():
        mime_prefixes: list[str] = caps.get("mime_prefixes", [])
        full_mimes: list[str] = caps.get("full_mimes", [])
        if (
            any(mime_lower.startswith(p) for p in mime_prefixes)
            or mime_lower in full_mimes
        ):
            applicable.append(agent_id)
    return applicable


# ── Human-readable description ──────────────────────────────────────────
def describe_file_type(ext: str, mime_type: str) -> str:
    """Return a short human-readable description for the given ext/MIME pair."""
    descriptions: dict[str, str] = {
        # Images
        "image/jpeg": "JPEG image",
        "image/png": "PNG image",
        "image/tiff": "TIFF image",
        "image/webp": "WebP image",
        "image/gif": "GIF image",
        "image/bmp": "BMP image",
        # Audio
        "audio/mpeg": "MP3 audio",
        "audio/wav": "WAV audio",
        "audio/x-wav": "WAV audio",
        "audio/flac": "FLAC audio",
        "audio/x-flac": "FLAC audio",
        "audio/aac": "AAC audio",
        "audio/ogg": "OGG audio",
        "audio/mp4": "M4A audio",
        "audio/x-m4a": "M4A audio",
        # Video
        "video/mp4": "MP4 video",
        "video/mpeg": "MPEG video",
        "video/webm": "WebM video",
        "video/quicktime": "MOV video",
        "video/x-msvideo": "AVI video",
        "video/x-matroska": "MKV video",
        "application/mp4": "MP4 media",
        # Documents
        "application/pdf": "PDF document",
    }
    name = descriptions.get(mime_type, f"file (.{ext.lstrip('.')})")
    return f"{name} (.{ext.lstrip('.')})"


# ═════════════════════════════════════════════════════════════════════════
#  CONTENT-AWARE TOOL GATING
#  ----------------------------------------------------------------------
#  A single declarative map of tool -> required content class, enforced in
#  ToolRegistry.call() so the RIGHT tool only runs for the RIGHT file type,
#  for EVERY agent, unbypassable by task-routing or LLM hallucination.
#
#  This generalizes the per-handler image lossless gate (ELA-on-PNG) to all
#  four media classes:
#    - IMAGE_LOSSY tools (ELA family) -> NOT_APPLICABLE on lossless images
#    - AUDIO_LOSSY tools (codec/splice) -> NOT_APPLICABLE on lossless audio
#    - IMAGE / AUDIO / VIDEO / DOCUMENT tools -> NOT_APPLICABLE on other media
#    - OCR -> images + PDF only (never audio/video)
#  Unmapped tools default to ANY (metadata/structural tools that read every
#  type, e.g. file_hash_verify, exif_extract — Agent5 runs these on all media).
#  Tool names shared across media (deepfake_frequency_check, adversarial_
#  robustness_check) are left ANY; agent-level routing already guarantees each
#  specialist agent only ever runs on its own media class.
# ═════════════════════════════════════════════════════════════════════════

from enum import Enum


class ContentClass(str, Enum):
    ANY = "any"
    IMAGE = "image"
    IMAGE_LOSSY = "image_lossy"
    AUDIO = "audio"
    AUDIO_LOSSY = "audio_lossy"
    VIDEO = "video"
    DOCUMENT = "document"
    IMAGE_OR_DOCUMENT = "image_or_document"


_LOSSLESS_AUDIO_EXTS: frozenset[str] = frozenset({".wav", ".flac"})
_LOSSLESS_AUDIO_MIMES: frozenset[str] = frozenset(
    {"audio/wav", "audio/x-wav", "audio/flac", "audio/x-flac"}
)


TOOL_CONTENT_REQUIREMENTS: dict[str, ContentClass] = {
    # ── Image sub-type gate: JPEG-compression-dependent (ELA family) ──
    # Meaningless on lossless images (no recompression residual to analyze).
    "neural_ela": ContentClass.IMAGE_LOSSY,
    "ela_full_image": ContentClass.IMAGE_LOSSY,
    "ela_anomaly_classify": ContentClass.IMAGE_LOSSY,
    "jpeg_ghost_detect": ContentClass.IMAGE_LOSSY,

    # ── Image pixel / scene / provenance tools (Agent1 + Agent3 only) ──
    "noiseprint_cluster": ContentClass.IMAGE,
    "noise_fingerprint": ContentClass.IMAGE,
    "frequency_domain_analysis": ContentClass.IMAGE,
    "splicing_detect": ContentClass.IMAGE,
    "copy_move_detect": ContentClass.IMAGE,
    "neural_copy_move": ContentClass.IMAGE,
    "neural_splicing": ContentClass.IMAGE,
    "anomaly_tracer": ContentClass.IMAGE,
    "f3_net_frequency": ContentClass.IMAGE,
    "neural_fingerprint": ContentClass.IMAGE,
    "diffusion_artifact_detector": ContentClass.IMAGE,
    "analyze_image_content": ContentClass.IMAGE,
    "roi_extract": ContentClass.IMAGE,
    "detect_font_inconsistency": ContentClass.IMAGE,
    "detect_ui_overlay_forgery": ContentClass.IMAGE,
    "synthid_watermark_detect": ContentClass.IMAGE,
    "reverse_image_search": ContentClass.IMAGE,
    "lens_style_multimodal_scan": ContentClass.IMAGE,
    "object_detection": ContentClass.IMAGE,
    "scene_incongruence": ContentClass.IMAGE,
    "lighting_consistency": ContentClass.IMAGE,
    "lighting_correlation_initial": ContentClass.IMAGE,
    "vector_contraband_search": ContentClass.IMAGE,
    "scale_validation": ContentClass.IMAGE,
    "secondary_classification": ContentClass.IMAGE,
    "screenshot_scene_applicability": ContentClass.IMAGE,
    "screenshot_layout_forensics": ContentClass.IMAGE,
    "visual_evidence_profile": ContentClass.IMAGE,
    # Camera/optical-physics tools — Agent5 registers these for ALL media, but
    # they operate on image pixels/sensor noise and are meaningless on a raw
    # audio/video container or a PDF. PRNU = camera-sensor noise; camera_profile
    # = lens/sensor signature; astro_grounding = sun/shadow geometry from pixels.
    "prnu_sensor_verification": ContentClass.IMAGE,
    "camera_profile_match": ContentClass.IMAGE,
    "astro_grounding": ContentClass.IMAGE,

    # ── Audio sub-type gate: codec-artifact-dependent ──
    # Meaningless on lossless audio (no compression artifacts to analyze).
    "audio_splice_detect": ContentClass.AUDIO_LOSSY,
    "codec_fingerprinting": ContentClass.AUDIO_LOSSY,

    # ── Audio tools (Agent2 only) ──
    "speaker_diarize": ContentClass.AUDIO,
    "anti_spoofing_detect": ContentClass.AUDIO,
    "anti_spoofing_deep_ensemble": ContentClass.AUDIO,
    "prosody_analyze": ContentClass.AUDIO,
    "neural_prosody": ContentClass.AUDIO,
    "voice_clone_detect": ContentClass.AUDIO,
    "voice_clone_deep_ensemble": ContentClass.AUDIO,
    "background_noise_analysis": ContentClass.AUDIO,
    "audio_gen_signature": ContentClass.AUDIO,
    "enf_analysis": ContentClass.AUDIO,

    # ── Video tools (Agent4 only) ──
    "optical_flow_analysis": ContentClass.VIDEO,
    "frame_extraction": ContentClass.VIDEO,
    "frame_consistency_analysis": ContentClass.VIDEO,
    "face_swap_detection": ContentClass.VIDEO,
    "video_metadata": ContentClass.VIDEO,
    "interframe_forgery_detector": ContentClass.VIDEO,
    "compression_artifact_analysis": ContentClass.VIDEO,
    "rolling_shutter_validation": ContentClass.VIDEO,
    "vfi_error_map": ContentClass.VIDEO,
    "thumbnail_coherence": ContentClass.VIDEO,

    # ── OCR / text extraction: images + PDF, never audio/video ──
    "extract_text_from_image": ContentClass.IMAGE_OR_DOCUMENT,
    "extract_evidence_text": ContentClass.IMAGE_OR_DOCUMENT,
}


def _media_class_of(mime_type: str, ext: str) -> str:
    """Classify a file's coarse media class. Returns image/audio/video/document/unknown."""
    m = (mime_type or "").lower()
    if m.startswith("image/"):
        return "image"
    if m.startswith("audio/"):
        return "audio"
    if m.startswith("video/"):
        return "video"
    if m == "application/pdf":
        return "document"
    if m == "application/mp4":
        return "video"  # generic MP4 container — treat as video for gating
    # Fall back to extension when MIME is missing/generic.
    resolved = get_mime_for_extension(ext or "")
    if resolved:
        return _media_class_of(resolved, "")
    return "unknown"


def content_aware_gate(
    tool_name: str, file_path: str = "", mime_type: str = ""
) -> str | None:
    """Return a NOT_APPLICABLE reason if `tool_name` must not run on this file,
    or None if the tool is applicable.

    This is the single enforcement point for content-aware tool gating across
    ALL agents. It is fail-OPEN: an unrecognized media class or unmapped tool
    always allows execution, so the gate can never block a legitimate analysis
    it doesn't understand — it only blocks definite mismatches.
    """
    req = TOOL_CONTENT_REQUIREMENTS.get(tool_name, ContentClass.ANY)
    if req == ContentClass.ANY:
        return None

    import os

    ext = os.path.splitext(file_path or "")[1].lower()
    media = _media_class_of(mime_type, ext)
    if media == "unknown":
        return None  # fail-open: don't block what we can't classify

    if req in (ContentClass.IMAGE, ContentClass.IMAGE_LOSSY):
        if media != "image":
            return f"{tool_name} requires an image; evidence is {media}."
        if req == ContentClass.IMAGE_LOSSY:
            from core.image_utils import is_lossless_image

            if is_lossless_image(file_path, mime_type):
                return (
                    f"{tool_name} analyzes JPEG re-compression artifacts, which do not "
                    f"exist in lossless images. Lossless integrity is covered by "
                    f"sensor-noise and splicing tools instead."
                )
        return None

    if req in (ContentClass.AUDIO, ContentClass.AUDIO_LOSSY):
        if media != "audio":
            return f"{tool_name} requires audio; evidence is {media}."
        if req == ContentClass.AUDIO_LOSSY:
            is_lossless = ext in _LOSSLESS_AUDIO_EXTS or (mime_type or "").lower() in _LOSSLESS_AUDIO_MIMES
            if is_lossless:
                return (
                    f"{tool_name} analyzes lossy-codec compression artifacts, which do not "
                    f"exist in lossless audio (WAV/FLAC)."
                )
        return None

    if req == ContentClass.VIDEO:
        if media != "video":
            return f"{tool_name} requires video; evidence is {media}."
        return None

    if req == ContentClass.DOCUMENT:
        if media != "document":
            return f"{tool_name} requires a document; evidence is {media}."
        return None

    if req == ContentClass.IMAGE_OR_DOCUMENT:
        if media not in ("image", "document"):
            return f"{tool_name} applies only to images and documents; evidence is {media}."
        return None

    return None
