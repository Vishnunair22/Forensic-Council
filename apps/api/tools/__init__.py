"""
Tools Module
============

Forensic analysis tools for evidence processing.
"""

from tools.audio_tools import (
    anti_spoofing_detect,
    background_noise_consistency,
    codec_fingerprint,
    prosody_analyze,
    speaker_diarize,
)
from tools.image_tools import (
    analyze_image_content,
    compute_perceptual_hash,
    ela_full_image,
    extract_text_from_image,
    file_hash_verify,
    frequency_domain_analysis,
    jpeg_ghost_detect,
    roi_extract,
)
from tools.metadata_tools import (
    exif_extract,
    extract_deep_metadata,
    file_structure_analysis,
    get_physical_address,
    gps_timezone_validate,
    steganography_scan,
    timestamp_analysis,
)
from tools.video_tools import (
    face_swap_detect,
    frame_consistency_analyze,
    frame_window_extract,
    optical_flow_analyze,
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
    "extract_text_from_image",
    "analyze_image_content",
    # Metadata tools
    "exif_extract",
    "gps_timezone_validate",
    "steganography_scan",
    "file_structure_analysis",
    "timestamp_analysis",
    "extract_deep_metadata",
    "get_physical_address",
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
