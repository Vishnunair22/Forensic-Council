"""
Tools Module
============

Forensic analysis tools for evidence processing.
"""

from tools.image_tools import (
    ela_full_image,
    roi_extract,
    jpeg_ghost_detect,
    file_hash_verify,
    compute_perceptual_hash,
    frequency_domain_analysis,
)
from tools.metadata_tools import (
    exif_extract,
    gps_timezone_validate,
    steganography_scan,
    file_structure_analysis,
    timestamp_analysis,
)
from tools.audio_tools import (
    speaker_diarize,
    anti_spoofing_detect,
    prosody_analyze,
    background_noise_consistency,
    codec_fingerprint,
)
from tools.video_tools import (
    optical_flow_analyze,
    frame_window_extract,
    frame_consistency_analyze,
    face_swap_detect,
    video_metadata_extract,
)

__all__ = [
    # Image tools
    "ela_full_image",
    "roi_extract",
    "jpeg_ghost_detect",
    "file_hash_verify",
    "compute_perceptual_hash",
    "frequency_domain_analysis",
    # Metadata tools
    "exif_extract",
    "gps_timezone_validate",
    "steganography_scan",
    "file_structure_analysis",
    "timestamp_analysis",
    # Audio tools
    "speaker_diarize",
    "anti_spoofing_detect",
    "prosody_analyze",
    "background_noise_consistency",
    "codec_fingerprint",
    # Video tools
    "optical_flow_analyze",
    "frame_window_extract",
    "frame_consistency_analyze",
    "face_swap_detect",
    "video_metadata_extract",
]
