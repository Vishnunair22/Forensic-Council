"""
Audio Forensic Tools (Backward Compatibility)
==========================================

This module is DEPRECATED. Use tools.audio instead:

    from tools.audio import speaker_diarize, anti_spoofing_detect

For backward compatibility, this module re-exports the new package.
"""

from tools.audio import *  # noqa: F401,F403

__all__ = [
    "speaker_diarize",
    "AudioSegment",
    "prosody_analyze",
    "background_noise_consistency",
    "audio_splice_detect",
    "anti_spoofing_detect",
    "codec_fingerprint",
]