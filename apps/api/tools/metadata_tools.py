"""
Metadata Forensic Tools (Backward Compatibility)
============================================

This module is DEPRECATED. Use tools.metadata instead:

    from tools.metadata import exif_extract, gps_timezone_validate

For backward compatibility, this module re-exports the new package.
"""

from tools.metadata import *  # noqa: F401,F403

__all__ = [
    "exif_extract",
    "gps_timezone_validate",
    "steganography_scan",
    "file_structure_analysis",
    "timestamp_analysis",
    "hex_signature_scan",
    "extract_deep_metadata",
    "get_physical_address",
    "astronomical_validate_astral",
    "exif_extract_enhanced",
    "steganography_scan_enhanced",
    "camera_profile_match",
    "provenance_chain_verify",
    "prnu_sensor_verification",
]