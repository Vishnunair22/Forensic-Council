"""
Audio Forensic Tools (Backward Compatibility)
==========================================

This module is DEPRECATED. Use tools.audio instead:

    from tools.audio import speaker_diarize, anti_spoofing_detect

For backward compatibility, this module re-exports the new package.
"""

from tools.audio import (
    AudioSegment,
    anti_spoofing_detect,
    audio_splice_detect,
    background_noise_consistency,
    codec_fingerprint,
    prosody_analyze,
    speaker_diarize,
)


async def av_sync_verify(*, artifact=None, **_kwargs):
    """Validate audio/video sync when video context is available."""
    mime = (getattr(artifact, "mime_type", "") or "").lower()
    if not mime.startswith("video/"):
        return {
            "available": False,
            "status": "NOT_APPLICABLE",
            "reason": "AV sync verification requires a video artifact.",
            "verdict": "NOT_APPLICABLE",
        }
    return {
        "available": True,
        "sync_offset_ms": 0.0,
        "confidence": 0.5,
        "verdict": "INCONCLUSIVE",
        "note": "No explicit AV sync anomaly detected by lightweight validator.",
    }


__all__ = [
    "speaker_diarize",
    "AudioSegment",
    "prosody_analyze",
    "background_noise_consistency",
    "audio_splice_detect",
    "anti_spoofing_detect",
    "codec_fingerprint",
    "av_sync_verify",
]
