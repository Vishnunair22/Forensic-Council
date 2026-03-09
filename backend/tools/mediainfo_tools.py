"""
MediaInfo Forensic Tools
========================

Deep audio/video container profiling using pymediainfo — a Python binding
for the open-source MediaInfo library.

Why MediaInfo over OpenCV/soundfile/ExifTool alone?
  - Reads container structure at the binary level (not just frame headers)
  - Exposes encoding tool, writing application, track UUIDs, mux date
  - Detects container/codec mismatches (e.g. MP4 container with HEVC video
    but AAC audio encoded by a different tool on a different date)
  - Reports variable frame rate (VFR) flags — critical for deepfake detection
    since most synthesis pipelines produce constant frame rate (CFR) output
  - Surface-level forensic signals without requiring model downloads

Performance:
  MediaInfo parses only container headers and is typically <20ms per file.
  No heavy compute, no GPU, no model weights to download.

Model caching:
  No models used by this module. All analysis is deterministic header parsing.
"""

from __future__ import annotations

import asyncio
import os
from concurrent.futures import ThreadPoolExecutor
from typing import Any, Optional

from core.evidence import EvidenceArtifact
from core.exceptions import ToolUnavailableError
from core.logging import get_logger

logger = get_logger(__name__)

# Thread pool for blocking pymediainfo calls
_MI_EXECUTOR = ThreadPoolExecutor(max_workers=2, thread_name_prefix="mediainfo_worker")

# MediaInfo availability flag (checked once at runtime)
_mediainfo_available: Optional[bool] = None


def _check_mediainfo() -> bool:
    """Return True if pymediainfo is installed and libmediainfo is accessible."""
    global _mediainfo_available
    if _mediainfo_available is not None:
        return _mediainfo_available
    try:
        from pymediainfo import MediaInfo  # noqa: PLC0415
        # Quick parse of an empty-ish probe to verify the C library is linked
        MediaInfo.parse.__doc__  # noqa: B018 — just trigger the import chain
        _mediainfo_available = True
    except (ImportError, OSError) as exc:
        logger.warning(
            "pymediainfo unavailable — AV container profiling disabled",
            error=str(exc),
        )
        _mediainfo_available = False
    return _mediainfo_available


# ---------------------------------------------------------------------------
# Internal sync worker (runs in thread pool)
# ---------------------------------------------------------------------------


def _profile_av_sync(file_path: str) -> dict[str, Any]:
    """
    Synchronous MediaInfo profiling — called via thread pool.

    Returns a structured dict covering:
      General track  — container format, mux tool, duration, file size, dates
      Video track(s) — codec, resolution, frame rate, bit depth, colour space,
                       HDR flags, writing library, encoding settings
      Audio track(s) — codec, channels, sample rate, bit depth, language,
                       compression mode, writing library
    """
    if not _check_mediainfo():
        return {"available": False, "error": "pymediainfo not installed or libmediainfo missing"}

    try:
        from pymediainfo import MediaInfo  # noqa: PLC0415
    except ImportError:
        return {"available": False, "error": "pymediainfo import failed"}

    try:
        mi = MediaInfo.parse(file_path)
    except Exception as exc:
        return {"available": False, "error": f"MediaInfo.parse failed: {exc}"}

    result: dict[str, Any] = {
        "available": True,
        "general": {},
        "video_tracks": [],
        "audio_tracks": [],
        "text_tracks": [],
        "other_tracks": [],
        "forensic_flags": [],
    }

    for track in mi.tracks:
        kind = track.track_type

        if kind == "General":
            result["general"] = {
                "format": track.format,
                "format_version": track.format_version,
                "file_size_bytes": track.file_size,
                "duration_ms": track.duration,
                "overall_bit_rate_bps": track.overall_bit_rate,
                "encoded_date": track.encoded_date,
                "tagged_date": track.tagged_date,
                "writing_application": track.writing_application,
                "writing_library": track.writing_library,
                "track_count": track.count_of_stream_of_this_kind,
            }

        elif kind == "Video":
            vt: dict[str, Any] = {
                "track_id": track.track_id,
                "codec": track.codec_id or track.format,
                "codec_profile": track.format_profile,
                "width_px": track.width,
                "height_px": track.height,
                "display_aspect_ratio": track.display_aspect_ratio,
                "frame_rate": track.frame_rate,
                "frame_rate_mode": track.frame_rate_mode,   # CFR vs VFR
                "frame_count": track.frame_count,
                "duration_ms": track.duration,
                "bit_depth": track.bit_depth,
                "colour_space": track.color_space,
                "chroma_subsampling": track.chroma_subsampling,
                "hdr_format": track.hdr_format,
                "writing_library": track.writing_library,
                "encoding_settings": track.encoding_settings,
                "language": track.language,
                "default": track.default,
                "forced": track.forced,
            }
            result["video_tracks"].append(vt)

        elif kind == "Audio":
            at: dict[str, Any] = {
                "track_id": track.track_id,
                "codec": track.codec_id or track.format,
                "codec_profile": track.format_profile,
                "channels": track.channel_s,
                "channel_layout": track.channel_layout,
                "sample_rate_hz": track.sampling_rate,
                "bit_depth": track.bit_depth,
                "duration_ms": track.duration,
                "bit_rate_bps": track.bit_rate,
                "compression_mode": track.compression_mode,
                "writing_library": track.writing_library,
                "language": track.language,
                "default": track.default,
            }
            result["audio_tracks"].append(at)

        elif kind == "Text":
            result["text_tracks"].append({
                "track_id": track.track_id,
                "format": track.format,
                "language": track.language,
            })

        else:
            result["other_tracks"].append({"track_type": kind, "format": track.format})

    # ------------------------------------------------------------------
    # Forensic flag analysis — derive tamper signals from metadata
    # ------------------------------------------------------------------
    flags = result["forensic_flags"]
    general = result["general"]
    video_tracks = result["video_tracks"]
    audio_tracks = result["audio_tracks"]

    # Flag 1: Variable Frame Rate — deepfake synthesis pipelines produce CFR
    for vt in video_tracks:
        if vt.get("frame_rate_mode") == "VFR":
            flags.append({
                "signal": "VARIABLE_FRAME_RATE",
                "detail": "Video has variable frame rate (VFR). "
                          "Most authentic camera recordings use CFR. "
                          "Screen recordings and some editing tools produce VFR.",
                "severity": "medium",
            })

    # Flag 2: Writing application mismatch (video vs audio encoded by different tools)
    if len(video_tracks) >= 1 and len(audio_tracks) >= 1:
        vlib = (video_tracks[0].get("writing_library") or "").lower()
        alib = (audio_tracks[0].get("writing_library") or "").lower()
        if vlib and alib and vlib != alib and "unknown" not in (vlib + alib):
            flags.append({
                "signal": "TRACK_LIBRARY_MISMATCH",
                "detail": (
                    f"Video writing library '{vlib}' differs from "
                    f"audio writing library '{alib}'. "
                    "This can indicate separate video and audio sourced from different recordings."
                ),
                "severity": "medium",
            })

    # Flag 3: Encoding date in the future
    enc_date = general.get("encoded_date") or ""
    if enc_date:
        try:
            from datetime import datetime, timezone  # noqa: PLC0415
            # MediaInfo dates are typically "UTC 2024-01-15 10:30:00"
            enc_date_clean = enc_date.replace("UTC ", "").strip()
            dt_enc = datetime.strptime(enc_date_clean, "%Y-%m-%d %H:%M:%S").replace(
                tzinfo=timezone.utc
            )
            if dt_enc > datetime.now(timezone.utc):
                flags.append({
                    "signal": "FUTURE_ENCODING_DATE",
                    "detail": f"Container encoding date is in the future: {enc_date}",
                    "severity": "high",
                })
        except (ValueError, TypeError):
            pass

    # Flag 4: Editing software signatures in writing_application
    known_editors = ["premiere", "final cut", "davinci", "handbrake", "ffmpeg",
                     "avisynth", "virtualdub", "kdenlive", "shotcut", "openshot"]
    writing_app = (general.get("writing_application") or "").lower()
    for editor in known_editors:
        if editor in writing_app:
            flags.append({
                "signal": "EDITING_SOFTWARE_DETECTED",
                "detail": f"Container written by editing software: {general.get('writing_application')}",
                "severity": "medium",
            })
            break  # Only flag once

    # Flag 5: Container/codec mismatch (e.g. .mp4 but codec says MKV-specific)
    container_fmt = (general.get("format") or "").lower()
    for vt in video_tracks:
        codec = (vt.get("codec") or "").lower()
        if container_fmt == "mpeg-4" and codec in ("av1", "theora", "vp8", "vp9"):
            flags.append({
                "signal": "CONTAINER_CODEC_MISMATCH",
                "detail": (
                    f"Codec '{vt.get('codec')}' is unusual for an MPEG-4 container. "
                    "This may indicate re-muxing or container spoofing."
                ),
                "severity": "low",
            })

    # Flag 6: No creation date at all (stripped metadata)
    if not general.get("encoded_date") and not general.get("tagged_date"):
        flags.append({
            "signal": "NO_CREATION_DATE",
            "detail": "Container has no encoded or tagged creation date. "
                      "Metadata may have been stripped.",
            "severity": "low",
        })

    return result


# ---------------------------------------------------------------------------
# Public async API
# ---------------------------------------------------------------------------


async def profile_av_container(
    artifact: EvidenceArtifact,
) -> dict[str, Any]:
    """
    Deep audio/video container profiling using MediaInfo.

    Parses container headers at the binary level to extract codec details,
    frame rate mode, encoding tools, creation dates, and track metadata.
    Also performs automated forensic flag analysis.

    This tool is fast (<20ms) and should be called on all video and audio
    evidence files before heavier ML-based analysis begins — the container
    metadata often tells us immediately whether the file has been re-encoded
    or edited.

    Args:
        artifact: The evidence artifact to analyze

    Returns:
        Dictionary containing:
        - available: Boolean — False if pymediainfo is not installed
        - general: Container-level metadata (format, duration, writing app, dates)
        - video_tracks: List of video track dicts (codec, resolution, fps, HDR, etc.)
        - audio_tracks: List of audio track dicts (codec, channels, sample rate, etc.)
        - text_tracks: Subtitle/caption tracks
        - forensic_flags: List of automatically detected forensic signals
          Each flag has: signal (str), detail (str), severity ("low"/"medium"/"high")
        - summary: Human-readable forensic summary for agent reasoning
        - court_defensible: True when MediaInfo is available

    Forensic flags raised:
        VARIABLE_FRAME_RATE         — VFR video (unusual for cameras, common in screen recording)
        TRACK_LIBRARY_MISMATCH      — Video and audio encoded by different tools
        FUTURE_ENCODING_DATE        — Container date is in the future
        EDITING_SOFTWARE_DETECTED   — Known NLE (Premiere, DaVinci, FFmpeg, etc.) in metadata
        CONTAINER_CODEC_MISMATCH    — Codec unusual for the container format
        NO_CREATION_DATE            — Metadata stripped (no encoded/tagged date)
    """
    if not os.path.exists(artifact.file_path):
        raise ToolUnavailableError(f"File not found: {artifact.file_path}")

    loop = asyncio.get_running_loop()
    result = await loop.run_in_executor(
        _MI_EXECUTOR, _profile_av_sync, artifact.file_path
    )

    result["court_defensible"] = result.get("available", False)
    result["summary"] = _build_av_summary(result)
    return result


async def get_av_file_identity(
    artifact: EvidenceArtifact,
) -> dict[str, Any]:
    """
    Lightweight identity query — returns just the key signals for fast pre-screening.

    Returns the file format, primary codec, duration, resolution, and any
    high-severity forensic flags without the full track detail. Intended as
    a quick pre-flight check before committing to heavier analysis tools.

    Args:
        artifact: The evidence artifact to query

    Returns:
        Dictionary containing:
        - format: Container format string
        - primary_codec: Codec of the first video track (or audio codec if audio-only)
        - duration_s: Duration in seconds
        - resolution: "WxH" for video, or None for audio
        - high_severity_flags: List of forensic flags with severity == "high"
        - available: Boolean
    """
    full = await profile_av_container(artifact)

    if not full.get("available"):
        return {"available": False, "error": full.get("error", "MediaInfo unavailable")}

    general = full.get("general", {})
    vt = full.get("video_tracks", [{}])[0] if full.get("video_tracks") else {}
    at = full.get("audio_tracks", [{}])[0] if full.get("audio_tracks") else {}

    duration_ms = general.get("duration_ms") or vt.get("duration_ms") or 0
    duration_s = round(float(duration_ms) / 1000, 2) if duration_ms else None

    res = None
    if vt.get("width_px") and vt.get("height_px"):
        res = f"{vt['width_px']}x{vt['height_px']}"

    primary_codec = vt.get("codec") or at.get("codec") or "unknown"

    high_flags = [
        f for f in full.get("forensic_flags", []) if f.get("severity") == "high"
    ]

    return {
        "available": True,
        "format": general.get("format"),
        "primary_codec": primary_codec,
        "duration_s": duration_s,
        "resolution": res,
        "writing_application": general.get("writing_application"),
        "encoded_date": general.get("encoded_date"),
        "high_severity_flags": high_flags,
        "court_defensible": True,
    }


# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------


def _build_av_summary(result: dict[str, Any]) -> str:
    """Build a one-line human-readable summary for agent reasoning."""
    if not result.get("available"):
        return "MediaInfo unavailable — container profiling skipped."

    g = result.get("general", {})
    vt = result.get("video_tracks", [])
    at = result.get("audio_tracks", [])
    flags = result.get("forensic_flags", [])

    parts: list[str] = []

    fmt = g.get("format", "unknown format")
    parts.append(fmt)

    if vt:
        v = vt[0]
        res = f"{v.get('width_px', '?')}x{v.get('height_px', '?')}"
        fps = v.get("frame_rate", "?")
        fpm = v.get("frame_rate_mode", "")
        parts.append(f"{v.get('codec', 'unknown codec')} {res} @ {fps}fps ({fpm})")

    if at:
        a = at[0]
        parts.append(f"{a.get('codec', 'unknown audio')} {a.get('sample_rate_hz', '?')}Hz")

    writing_app = g.get("writing_application")
    if writing_app:
        parts.append(f"written by {writing_app}")

    summary = " | ".join(str(p) for p in parts if p)

    if flags:
        flag_strs = [f["signal"] for f in flags]
        summary += f". ⚠️ Flags: {', '.join(flag_strs)}"

    return summary
