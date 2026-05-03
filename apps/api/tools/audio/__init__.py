"""
Audio Tools Package
====================

Audio forensic analysis tools organized by function.
Use imports from this package for new code:

    from tools.audio import speaker_diarize, anti_spoofing_detect, prosody_analyze

For backward compatibility, the old module still works:
    from tools.audio_tools import speaker_diarize
"""

from __future__ import annotations

from tools.audio.diarization import run_speaker_diarize as speaker_diarize
from tools.audio.diarization import AudioSegment
from tools.audio.prosody import run_prosody_analyze as prosody_analyze
from tools.audio.spectral import run_background_noise_consistency as background_noise_consistency
from tools.audio.splice import run_audio_splice_detect as audio_splice_detect
from tools.audio.synthesis import run_anti_spoofing_detect as anti_spoofing_detect
from tools.audio.synthesis import run_codec_fingerprint as codec_fingerprint

__all__ = [
    "speaker_diarize",
    "AudioSegment",
    "prosody_analyze",
    "background_noise_consistency",
    "audio_splice_detect",
    "anti_spoofing_detect",
    "codec_fingerprint",
]