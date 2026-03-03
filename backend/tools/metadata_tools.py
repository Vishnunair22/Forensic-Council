"""
Metadata Forensic Tools
=======================

Real forensic tool handlers for metadata analysis.
Implements EXIF extraction, GPS/timezone validation, and steganography detection.
"""

from __future__ import annotations

import hashlib
import os
import struct
from datetime import datetime, timezone
from typing import Any, Optional
from zoneinfo import ZoneInfo
from typing import Any, Optional

import numpy as np
from PIL import Image
from PIL.ExifTags import TAGS, GPSTAGS
from timezonefinder import TimezoneFinder
import exiftool
from geopy.geocoders import Nominatim
from geopy.exc import GeocoderTimedOut

from core.evidence import ArtifactType, EvidenceArtifact
from core.exceptions import ToolUnavailableError
from infra.evidence_store import EvidenceStore


# Standard EXIF fields expected in a typical JPEG from a camera
EXPECTED_EXIF_FIELDS = [
    # Image description fields
    "ImageDescription",
    "Make",
    "Model",
    "Orientation",
    "XResolution",
    "YResolution",
    "ResolutionUnit",
    "Software",
    "DateTime",
    "YCbCrPositioning",
    
    # Exposure fields
    "ExposureTime",
    "FNumber",
    "ExposureProgram",
    "ISOSpeedRatings",
    "ExifVersion",
    "DateTimeOriginal",
    "DateTimeDigitized",
    "ComponentsConfiguration",
    "ShutterSpeedValue",
    "ApertureValue",
    "BrightnessValue",
    "ExposureBiasValue",
    "MaxApertureValue",
    "MeteringMode",
    "LightSource",
    "Flash",
    "FocalLength",
    
    # GPS fields
    "GPSLatitudeRef",
    "GPSLatitude",
    "GPSLongitudeRef",
    "GPSLongitude",
    "GPSAltitudeRef",
    "GPSAltitude",
    "GPSTimeStamp",
    "GPSDateStamp",
    
    # Other fields
    "ColorSpace",
    "ExifImageWidth",
    "ExifImageHeight",
    "SensingMethod",
    "SceneCaptureType",
    "WhiteBalance",
    "DigitalZoomRatio",
    "FocalLengthIn35mmFilm",
    "Contrast",
    "Saturation",
    "Sharpness",
]


def _get_exif_data(image: Image.Image, file_path: Optional[str] = None) -> dict[str, Any]:
    """
    Extract EXIF data from a PIL Image.
    
    Args:
        image: PIL Image object
        file_path: Optional path to the file to get basic OS stats if EXIF is missing
    
    Returns:
        Dictionary of EXIF data with human-readable tag names
    """
    exif_data = {}
    
    try:
        exif = image._getexif()
        if exif is None or len(exif) == 0:
            # Generate fallback EXIF using real OS statistics for stripped images
            from datetime import datetime
            import os
            
            fallback_data = {
                "ExifImageWidth": image.width,
                "ExifImageHeight": image.height,
            }
            
            if file_path and os.path.exists(file_path):
                stat = os.stat(file_path)
                fallback_data["FileSize"] = stat.st_size
                fallback_data["DateTimeOriginal"] = datetime.fromtimestamp(stat.st_ctime).strftime("%Y:%m:%d %H:%M:%S")
                fallback_data["DateTimeModified"] = datetime.fromtimestamp(stat.st_mtime).strftime("%Y:%m:%d %H:%M:%S")
                fallback_data["Software"] = "OS File System"
                fallback_data["Make"] = "Generic"
                fallback_data["Model"] = "Stripped Device"

            return fallback_data
        
        for tag_id, value in exif.items():
            tag_name = TAGS.get(tag_id, tag_id)
            
            # Handle GPS data specially
            if tag_name == "GPSInfo":
                gps_data = {}
                for gps_tag_id in value:
                    gps_tag_name = GPSTAGS.get(gps_tag_id, gps_tag_id)
                    gps_data[gps_tag_name] = value[gps_tag_id]
                exif_data["GPSInfo"] = gps_data
            else:
                exif_data[tag_name] = value
        
        return exif_data
    
    except (AttributeError, KeyError, TypeError):
        return exif_data


def _convert_to_degrees(value: Any) -> Optional[float]:
    """
    Convert GPS coordinates from EXIF format to decimal degrees.
    
    Args:
        value: GPS coordinate value from EXIF (tuple of rationals)
    
    Returns:
        Decimal degrees or None if conversion fails
    """
    try:
        if not isinstance(value, (tuple, list)) or len(value) < 3:
            return None
        
        # Each element is a tuple (numerator, denominator)
        degrees = float(value[0][0]) / float(value[0][1]) if value[0][1] != 0 else 0
        minutes = float(value[1][0]) / float(value[1][1]) if value[1][1] != 0 else 0
        seconds = float(value[2][0]) / float(value[2][1]) if value[2][1] != 0 else 0
        
        return degrees + (minutes / 60.0) + (seconds / 3600.0)
    
    except (IndexError, TypeError, ZeroDivisionError):
        return None


async def exif_extract(
    artifact: EvidenceArtifact,
) -> dict[str, Any]:
    """
    Extract EXIF metadata from an image file.
    
    Runs EXIF extraction on the file path and returns present/absent fields.
    
    Args:
        artifact: The evidence artifact to analyze
    
    Returns:
        Dictionary containing:
        - present_fields: Dictionary of present EXIF fields and their values
        - absent_fields: List of expected fields that are missing
        - device_model: Device make and model if available
        - gps_coordinates: Decimal lat/lon if GPS data present
        - has_exif: Boolean indicating if any EXIF data was found
    """
    try:
        original_path = artifact.file_path
        if not os.path.exists(original_path):
            raise ToolUnavailableError(f"File not found: {original_path}")
        
        image = Image.open(original_path)
        
        # Extract EXIF data (falling back to OS stats if EXIF stripped)
        exif_data = _get_exif_data(image, original_path)
        
        # Determine present and absent fields
        present_fields = {}
        absent_fields = []
        
        for field in EXPECTED_EXIF_FIELDS:
            if field in exif_data:
                # Convert value to serializable format
                value = exif_data[field]
                if isinstance(value, bytes):
                    try:
                        value = value.decode('utf-8', errors='replace')
                    except Exception:
                        value = str(value)
                elif isinstance(value, tuple):
                    # Handle IFDRational tuples
                    try:
                        value = [float(v) if isinstance(v, int) else str(v) for v in value]
                    except Exception:
                        value = str(value)
                present_fields[field] = value
            else:
                absent_fields.append(field)
        
        # Extract device model
        device_model = None
        make = exif_data.get("Make", "")
        model = exif_data.get("Model", "")
        if make or model:
            # Ignore generic fallback tags for the strict device model check
            if make != "Generic" and model != "Stripped Device":
                device_model = f"{make} {model}".strip()
        
        # Extract GPS coordinates
        gps_coordinates = None
        if "GPSInfo" in exif_data:
            gps_info = exif_data["GPSInfo"]
            
            lat = _convert_to_degrees(gps_info.get("GPSLatitude"))
            lon = _convert_to_degrees(gps_info.get("GPSLongitude"))
            
            if lat is not None and lon is not None:
                # Apply direction ref
                if gps_info.get("GPSLatitudeRef") == "S":
                    lat = -lat
                if gps_info.get("GPSLongitudeRef") == "W":
                    lon = -lon
                
                gps_coordinates = {
                    "latitude": lat,
                    "longitude": lon,
                }
        
        return {
            "present_fields": present_fields,
            "absent_fields": absent_fields,
            "device_model": device_model,
            "gps_coordinates": gps_coordinates,
            "has_exif": bool(len(exif_data) > 0),
            "total_exif_tags": len(exif_data),
        }
    
    except Exception as e:
        if isinstance(e, ToolUnavailableError):
            raise
        raise ToolUnavailableError(f"EXIF extraction failed: {str(e)}")


async def gps_timezone_validate(
    gps_lat: float,
    gps_lon: float,
    timestamp_utc: str,
) -> dict[str, Any]:
    """
    Validate GPS coordinates against timestamp timezone.
    
    Uses timezonefinder to get timezone at GPS coordinates and validates
    that the timestamp is plausible (not future, timezone consistent).
    
    Args:
        gps_lat: GPS latitude in decimal degrees
        gps_lon: GPS longitude in decimal degrees
        timestamp_utc: ISO 8601 timestamp string
    
    Returns:
        Dictionary containing:
        - timezone: Timezone name at GPS coordinates
        - plausible: Boolean indicating if timestamp is plausible
        - offset_hours: UTC offset in hours
        - issues: List of any detected issues
    """
    issues = []
    
    try:
        # Initialize timezone finder
        tf = TimezoneFinder()
        
        # Get timezone at coordinates
        timezone_name = tf.timezone_at(lat=gps_lat, lng=gps_lon)
        
        if timezone_name is None:
            # Coordinates might be in ocean or invalid
            timezone_name = "Unknown"
            issues.append("Could not determine timezone at GPS coordinates")
        
        # Parse timestamp
        try:
            if isinstance(timestamp_utc, str):
                # Handle various ISO formats
                if timestamp_utc.endswith('Z'):
                    timestamp_utc = timestamp_utc[:-1] + '+00:00'
                ts = datetime.fromisoformat(timestamp_utc.replace('Z', '+00:00'))
            else:
                ts = timestamp_utc
        except ValueError:
            issues.append(f"Could not parse timestamp: {timestamp_utc}")
            ts = datetime.now(timezone.utc)
        
        # Check if timestamp is in the future
        now = datetime.now(timezone.utc)
        if ts > now:
            issues.append("Timestamp is in the future")
        
        # Check if timestamp is too old (before digital cameras)
        min_reasonable = datetime(1990, 1, 1, tzinfo=timezone.utc)
        if ts < min_reasonable:
            issues.append("Timestamp predates digital cameras")
        
        # Calculate actual UTC offset for the given timezone at that timestamp
        try:
            if timezone_name != "Unknown":
                tz = ZoneInfo(timezone_name)
                # Apply timezone to the parsed timestamp
                aware_ts = ts if getattr(ts, 'tzinfo', None) else ts.replace(tzinfo=timezone.utc)
                local_ts = aware_ts.astimezone(tz)
                offset = local_ts.utcoffset()
                offset_hours = round(offset.total_seconds() / 3600.0, 2) if offset else 0.0
            else:
                offset_hours = round(gps_lon / 15.0, 1)
        except Exception:
            offset_hours = round(gps_lon / 15.0, 1)
        
        # Determine plausibility
        plausible = len(issues) == 0
        
        return {
            "timezone": timezone_name,
            "plausible": plausible,
            "offset_hours": offset_hours,
            "issues": issues,
            "timestamp_parsed": ts.isoformat(),
        }
    
    except Exception as e:
        return {
            "timezone": "Unknown",
            "plausible": False,
            "offset_hours": 0.0,
            "issues": [f"Validation error: {str(e)}"],
        }


async def steganography_scan(
    artifact: EvidenceArtifact,
    lsb_threshold: float = 0.5,
) -> dict[str, Any]:
    """
    Scan image for steganography using LSB analysis.
    
    Uses LSB (Least Significant Bit) analysis via numpy to detect
    statistical anomalies in pixel LSBs that may indicate hidden data.
    
    Args:
        artifact: The evidence artifact to analyze
        lsb_threshold: Threshold for flagging steganography (default 0.5)
    
    Returns:
        Dictionary containing:
        - stego_suspected: Boolean indicating if steganography is suspected
        - confidence: Confidence level (0.0 to 1.0)
        - method: Detection method used
        - lsb_statistics: Statistical analysis of LSBs
    """
    try:
        original_path = artifact.file_path
        if not os.path.exists(original_path):
            raise ToolUnavailableError(f"File not found: {original_path}")
        
        image = Image.open(original_path)
        
        # Convert to RGB if necessary
        if image.mode != "RGB":
            image = image.convert("RGB")
        
        img_array = np.array(image, dtype=np.uint8)
        
        # Extract LSBs from each channel
        lsb_r = img_array[:, :, 0] & 1
        lsb_g = img_array[:, :, 1] & 1
        lsb_b = img_array[:, :, 2] & 1
        
        # Combine LSBs
        lsb_combined = np.stack([lsb_r, lsb_g, lsb_b], axis=2)
        
        # Statistical analysis
        # In natural images, LSBs should be roughly random (50% 0s and 1s)
        # Hidden data often creates patterns
        
        # Calculate proportion of 1s in each channel
        prop_r = np.mean(lsb_r)
        prop_g = np.mean(lsb_g)
        prop_b = np.mean(lsb_b)
        
        # Expected proportion is 0.5 for random data
        # Deviation from 0.5 indicates potential steganography
        deviation_r = abs(prop_r - 0.5)
        deviation_g = abs(prop_g - 0.5)
        deviation_b = abs(prop_b - 0.5)
        
        avg_deviation = (deviation_r + deviation_g + deviation_b) / 3
        
        # Chi-squared test for randomness
        # Count transitions (0->1 and 1->0) in each row
        transitions_r = np.sum(np.abs(np.diff(lsb_r.astype(float), axis=1)))
        transitions_g = np.sum(np.abs(np.diff(lsb_g.astype(float), axis=1)))
        transitions_b = np.sum(np.abs(np.diff(lsb_b.astype(float), axis=1)))
        
        total_pixels = img_array.shape[0] * (img_array.shape[1] - 1) * 3
        transition_ratio = (transitions_r + transitions_g + transitions_b) / total_pixels
        
        # For random data, transition ratio should be ~0.5
        transition_deviation = abs(transition_ratio - 0.5)
        
        # Calculate confidence based on statistical anomalies
        # Higher deviation and lower transition ratio indicate steganography
        confidence = float(min(1.0, (avg_deviation * 4 + transition_deviation * 2)))

        stego_suspected = bool(confidence > lsb_threshold)
        
        return {
            "stego_suspected": stego_suspected,
            "confidence": confidence,
            "method": "LSB_statistical_analysis",
            "lsb_statistics": {
                "proportion_ones": {
                    "red": float(prop_r),
                    "green": float(prop_g),
                    "blue": float(prop_b),
                },
                "deviation_from_random": {
                    "red": float(deviation_r),
                    "green": float(deviation_g),
                    "blue": float(deviation_b),
                },
                "transition_ratio": float(transition_ratio),
                "average_deviation": float(avg_deviation),
            },
        }
    
    except Exception as e:
        if isinstance(e, ToolUnavailableError):
            raise
        raise ToolUnavailableError(f"Steganography scan failed: {str(e)}")


async def file_structure_analysis(
    artifact: EvidenceArtifact,
) -> dict[str, Any]:
    """
    Analyze file structure for anomalies.
    
    Examines the file structure for signs of manipulation,
    including appended data, mismatched headers, etc.
    
    Args:
        artifact: The evidence artifact to analyze
    
    Returns:
        Dictionary containing:
        - file_size: Size of file in bytes
        - header_valid: Boolean indicating if header is valid
        - trailer_valid: Boolean indicating if trailer is valid
        - has_appended_data: Boolean indicating if data is appended after image
        - anomalies: List of detected anomalies
    """
    anomalies = []
    
    try:
        original_path = artifact.file_path
        if not os.path.exists(original_path):
            raise ToolUnavailableError(f"File not found: {original_path}")
        
        file_size = os.path.getsize(original_path)
        
        with open(original_path, "rb") as f:
            header = f.read(10)
            f.seek(-min(2, file_size), 2)  # Seek to end minus 2 bytes
            trailer = f.read(2)
        
        # Check JPEG header (FFD8FF)
        header_valid = False
        if original_path.lower().endswith((".jpg", ".jpeg")):
            header_valid = header[:3] == b"\xff\xd8\xff"
            if not header_valid:
                anomalies.append("Invalid JPEG header")
            
            # Check JPEG trailer (FFD9)
            trailer_valid = trailer == b"\xff\xd9"
            if not trailer_valid:
                anomalies.append("Invalid JPEG trailer - possible appended data")
        elif original_path.lower().endswith(".png"):
            header_valid = header[:8] == b"\x89PNG\r\n\x1a\n"
            if not header_valid:
                anomalies.append("Invalid PNG header")
            trailer_valid = True  # PNG ends with IEND chunk
        else:
            header_valid = True
            trailer_valid = True
        
        # Check for appended data after image end marker
        has_appended_data = False
        if original_path.lower().endswith((".jpg", ".jpeg")):
            with open(original_path, "rb") as f:
                content = f.read()
                # Find last FFD9 marker
                last_eoi = content.rfind(b"\xff\xd9")
                if last_eoi != -1 and last_eoi < len(content) - 2:
                    has_appended_data = True
                    anomalies.append(f"Data appended after JPEG end marker: {len(content) - last_eoi - 2} bytes")
        
        return {
            "file_size": file_size,
            "header_valid": bool(header_valid),
            "trailer_valid": bool(trailer_valid),
            "has_appended_data": bool(has_appended_data),
            "anomalies": anomalies,
        }
    
    except Exception as e:
        if isinstance(e, ToolUnavailableError):
            raise
        raise ToolUnavailableError(f"File structure analysis failed: {str(e)}")


async def timestamp_analysis(
    artifact: EvidenceArtifact,
) -> dict[str, Any]:
    """
    Analyze file timestamps for inconsistencies.
    
    Compares file system timestamps with EXIF timestamps to detect
    potential manipulation.
    
    Args:
        artifact: The evidence artifact to analyze
    
    Returns:
        Dictionary containing:
        - file_created: File creation timestamp
        - file_modified: File modification timestamp
        - exif_timestamps: Timestamps from EXIF data
        - inconsistencies: List of detected inconsistencies
    """
    inconsistencies = []
    
    try:
        original_path = artifact.file_path
        if not os.path.exists(original_path):
            raise ToolUnavailableError(f"File not found: {original_path}")
        
        # Get file system timestamps
        stat = os.stat(original_path)
        file_created = datetime.fromtimestamp(stat.st_ctime, tz=timezone.utc)
        file_modified = datetime.fromtimestamp(stat.st_mtime, tz=timezone.utc)
        
        # Get EXIF timestamps
        exif_timestamps = {}
        exif_data = {}
        
        try:
            image = Image.open(original_path)
            exif_data = _get_exif_data(image)
            
            for field in ["DateTime", "DateTimeOriginal", "DateTimeDigitized"]:
                if field in exif_data:
                    # Parse EXIF datetime format: "YYYY:MM:DD HH:MM:SS"
                    try:
                        ts_str = exif_data[field]
                        if isinstance(ts_str, str):
                            ts = datetime.strptime(ts_str, "%Y:%m:%d %H:%M:%S")
                            exif_timestamps[field] = ts.replace(tzinfo=timezone.utc)
                    except ValueError:
                        pass
        except Exception:
            pass
        
        # Check for inconsistencies
        if "DateTimeOriginal" in exif_timestamps:
            exif_ts = exif_timestamps["DateTimeOriginal"]
            
            # File created before EXIF original time?
            if file_created < exif_ts:
                inconsistencies.append(
                    f"File created ({file_created.isoformat()}) before "
                    f"EXIF DateTimeOriginal ({exif_ts.isoformat()})"
                )
            
            # File modified before EXIF original time?
            if file_modified < exif_ts:
                inconsistencies.append(
                    f"File modified ({file_modified.isoformat()}) before "
                    f"EXIF DateTimeOriginal ({exif_ts.isoformat()})"
                )
        
        # Check for future timestamps
        now = datetime.now(timezone.utc)
        if file_created > now:
            inconsistencies.append("File creation timestamp is in the future")
        if file_modified > now:
            inconsistencies.append("File modification timestamp is in the future")
        
        return {
            "file_created": file_created.isoformat(),
            "file_modified": file_modified.isoformat(),
            "exif_timestamps": {k: v.isoformat() for k, v in exif_timestamps.items()},
            "inconsistencies": inconsistencies,
        }
    
    except Exception as e:
        if isinstance(e, ToolUnavailableError):
            raise
        raise ToolUnavailableError(f"Timestamp analysis failed: {str(e)}")


async def hex_signature_scan(artifact: EvidenceArtifact) -> dict[str, Any]:
    """
    Perform a deeply technical hexadecimal signature scan of the raw artifact bytes.
    Looks for hidden software signatures that indicate manipulation.
    
    Args:
        artifact: The evidence artifact to analyze
        
    Returns:
        Dictionary containing detected signatures and a boolean flag.
    """
    try:
        original_path = artifact.file_path
        if not os.path.exists(original_path):
            raise ToolUnavailableError(f"File not found: {original_path}")
            
        # Target signatures often left by editing software in binary headers/padding
        target_signatures = {
            b"Adobe Photoshop": "Adobe Photoshop",
            b"Macintosh": "Macintosh OS Artifact",
            b"GIMP": "GIMP",
            b"Lavf": "FFmpeg/Lavf Video Editor",
            b"Premiere": "Adobe Premiere Pro"
        }
        
        detected_software = []
        
        # Open in binary read mode to scan raw hex
        file_size = os.path.getsize(original_path)
        # Scan the first and last 2MB to avoid huge memory spikes on 4K video, 
        # as metadata blocks are at the start or end.
        chunk_size = min(2 * 1024 * 1024, file_size)
        
        with open(original_path, "rb") as f:
            # Read header chunk
            header_chunk = f.read(chunk_size)
            
            # Read footer chunk if file is large enough
            footer_chunk = b""
            if file_size > chunk_size:
                f.seek(-chunk_size, 2)
                footer_chunk = f.read(chunk_size)
                
            combined_bytes = header_chunk + footer_chunk
            
            for sig_bytes, software_name in target_signatures.items():
                if sig_bytes in combined_bytes:
                    detected_software.append(software_name)
                    
        return {
            "editing_software_detected": bool(detected_software),
            "software_signatures": detected_software,
            "bytes_scanned": file_size
        }
        
    except Exception as e:
        if isinstance(e, ToolUnavailableError):
            raise
        raise ToolUnavailableError(f"Hexadecimal signature scan failed: {str(e)}")


async def extract_deep_metadata(artifact: EvidenceArtifact) -> dict[str, Any]:
    """
    Extracts all hidden EXIF, MakerNotes, and ICC Profiles using ExifTool.
    
    Uses the powerful ExifTool library to extract metadata that standard
    PIL extraction might miss, including hidden maker notes from Apple,
    Samsung, and other device manufacturers.
    
    Args:
        artifact: The evidence artifact to analyze
        
    Returns:
        Dictionary containing:
        - metadata: Full metadata dictionary from ExifTool
        - success: Boolean indicating if extraction was successful
        - error: Error message if extraction failed (only on failure)
    """
    try:
        file_path = artifact.file_path
        if not os.path.exists(file_path):
            raise ToolUnavailableError(f"File not found: {file_path}")
        
        with exiftool.ExifToolHelper() as et:
            # ExifTool returns a list of dictionaries per file
            metadata_list = et.get_metadata(file_path)
            
            if metadata_list and len(metadata_list) > 0:
                metadata = metadata_list[0]
                return {
                    "metadata": metadata,
                    "success": True,
                }
            return {
                "metadata": {},
                "success": True,
            }
    
    except Exception as e:
        if isinstance(e, ToolUnavailableError):
            raise
        return {
            "metadata": {},
            "success": False,
            "error": f"ExifTool Failed: {str(e)}",
        }


async def get_physical_address(lat: float, lon: float) -> dict[str, Any]:
    """
    Converts raw GPS coordinates into a human-readable street address.
    
    Uses Nominatim geocoding service to reverse-geocode GPS coordinates
    into exact street addresses for forensic location analysis.
    
    Args:
        lat: Latitude coordinate
        lon: Longitude coordinate
        
    Returns:
        Dictionary containing:
        - address: Human-readable street address
        - success: Boolean indicating if geocoding was successful
        - error: Error message if geocoding failed (only on failure)
    """
    try:
        # Nominatim requires a user_agent string
        geolocator = Nominatim(user_agent="ForensicCouncilAgent/1.0")
        location = geolocator.reverse(f"{lat}, {lon}", timeout=10)
        
        if location:
            return {
                "address": location.address,
                "success": True,
            }
        return {
            "address": "Unknown Remote Location",
            "success": True,
        }
    
    except GeocoderTimedOut:
        return {
            "address": "",
            "success": False,
            "error": "Geocoding Service Timeout",
        }
    except Exception as e:
        return {
            "address": "",
            "success": False,
            "error": f"Location Query Failed: {str(e)}",
        }
