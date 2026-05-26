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
    av_sync_verify,
    background_noise_consistency,
    codec_fingerprint,
    prosody_analyze,
    speaker_diarize,
)

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
