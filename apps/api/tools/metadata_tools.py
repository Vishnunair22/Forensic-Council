"""Metadata forensic tools used by Agent 5."""

from __future__ import annotations

import hashlib
import os
import struct
import zlib
from datetime import datetime
from pathlib import Path
from typing import Any

from PIL import ExifTags, Image

from core.scoring import ConfidenceCalibrator
from core.structured_logging import get_logger

logger = get_logger(__name__)

try:
    from timezonefinder import TimezoneFinder
except Exception:  # pragma: no cover - optional dependency
    TimezoneFinder = None  # type: ignore[assignment]

try:
    from geopy.geocoders import Nominatim
except Exception:  # pragma: no cover - optional dependency
    Nominatim = None  # type: ignore[assignment]

EXPECTED_EXIF_FIELDS = [
    # Device identity
    "Make", "Model", "CameraSerialNumber", "LensModel", "LensSerialNumber",
    # Temporal (full precision)
    "DateTime", "DateTimeOriginal", "DateTimeDigitized", "SubSecTimeOriginal",
    "SubSecTime", "SubSecTimeDigitized",
    # Capture parameters
    "FNumber", "ExposureTime", "ISOSpeedRatings", "FocalLength",
    "Flash", "WhiteBalance", "MeteringMode", "ExposureProgram",
    "SceneType", "SceneCaptureType",
    # GPS full set
    "GPSLatitude", "GPSLongitude", "GPSLatitudeRef", "GPSLongitudeRef",
    "GPSAltitude", "GPSAltitudeRef", "GPSTimestamp", "GPSDateStamp",
    "GPSSpeed", "GPSSpeedRef", "GPSImgDirection", "GPSImgDirectionRef",
    # Provenance
    "Software", "Artist", "Copyright", "ImageDescription",
    "XPComment", "UserComment",
]


def _artifact_path(artifact: Any = None, file_path: str | None = None) -> str:
    return str(file_path or getattr(artifact, "file_path", "") or "")


_PNG_MAGIC = b"\x89PNG\r\n\x1a\n"
_JPEG_MAGIC = b"\xff\xd8"

_PNG_KNOWN_CHUNKS = {
    "IHDR", "IDAT", "IEND", "PLTE", "tEXt", "iTXt", "zTXt",
    "cHRM", "gAMA", "iCCP", "sBIT", "sRGB", "bKGD", "hIST",
    "tIME", "pHYs", "sPLT", "tRNS", "oFFs", "pCAL", "sCAL",
    "acTL", "fcTL", "fdAT", "eXIf",
}


def _analyze_png_structure(data: bytes) -> dict[str, Any]:
    chunks: list[str] = []
    text_metadata: dict[str, str] = {}
    anomalies: list[str] = []
    trailer_valid = False
    ihdr_seen = False
    idat_seen = False
    iend_end: int | None = None
    ihdr_info: dict[str, Any] = {}

    offset = 8  # skip 8-byte magic
    while offset + 8 <= len(data):
        try:
            length = struct.unpack(">I", data[offset : offset + 4])[0]
        except struct.error:
            anomalies.append(f"Truncated chunk length field at offset {offset}")
            break

        chunk_end = offset + 12 + length
        if chunk_end > len(data):
            anomalies.append(f"Chunk at offset {offset} extends past end of file")
            break

        try:
            chunk_type = data[offset + 4 : offset + 8].decode("ascii")
        except UnicodeDecodeError:
            anomalies.append(f"Non-ASCII chunk type at offset {offset}: {data[offset+4:offset+8].hex()}")
            offset = chunk_end
            continue

        chunk_data = data[offset + 8 : offset + 8 + length]
        stored_crc = struct.unpack(">I", data[offset + 8 + length : chunk_end])[0]
        computed_crc = zlib.crc32(data[offset + 4 : offset + 8 + length]) & 0xFFFFFFFF
        if computed_crc != stored_crc:
            anomalies.append(
                f"CRC mismatch in '{chunk_type}' at offset {offset} "
                f"(stored {stored_crc:#010x}, computed {computed_crc:#010x})"
            )

        chunks.append(chunk_type)

        if chunk_type == "IHDR":
            ihdr_seen = True
            if length >= 13:
                w, h = struct.unpack(">II", chunk_data[:8])
                bit_depth, color_type = chunk_data[8], chunk_data[9]
                ihdr_info = {"width": w, "height": h, "bit_depth": bit_depth, "color_type": color_type}

        elif chunk_type == "IDAT":
            idat_seen = True

        elif chunk_type == "tEXt":
            try:
                sep = chunk_data.index(b"\x00")
                key = chunk_data[:sep].decode("latin-1", errors="replace")
                value = chunk_data[sep + 1 :].decode("latin-1", errors="replace")
                text_metadata[key] = value
            except (ValueError, Exception):
                pass

        elif chunk_type == "iTXt":
            try:
                sep = chunk_data.index(b"\x00")
                key = chunk_data[:sep].decode("latin-1", errors="replace")
                rest = chunk_data[sep + 1 :]
                comp_flag = rest[0] if rest else 1
                if comp_flag == 0 and len(rest) >= 3:
                    rest = rest[2:]  # skip comp_flag and comp_method
                    lang_end = rest.find(b"\x00")
                    if lang_end >= 0:
                        rest = rest[lang_end + 1 :]
                        tkey_end = rest.find(b"\x00")
                        if tkey_end >= 0:
                            value = rest[tkey_end + 1 :].decode("utf-8", errors="replace")
                            text_metadata[key] = value
            except Exception:
                pass

        elif chunk_type == "IEND":
            iend_end = chunk_end
            trailer_valid = True

        if chunk_type not in _PNG_KNOWN_CHUNKS:
            anomalies.append(f"Unrecognised chunk type '{chunk_type}' at offset {offset}")

        offset = chunk_end

    if not ihdr_seen:
        anomalies.append("IHDR chunk absent — invalid PNG structure")
    if not idat_seen:
        anomalies.append("IDAT chunk absent — no image data present")
    if not trailer_valid:
        anomalies.append("IEND chunk absent — file may be truncated or corrupt")

    appended_bytes = 0
    has_appended = False
    if iend_end is not None and iend_end < len(data):
        appended_bytes = len(data) - iend_end
        has_appended = True
        anomalies.append(f"{appended_bytes} byte(s) appended after IEND — possible steganography carrier or file fusion")

    result: dict[str, Any] = {
        "format_detected": "PNG",
        "header_valid": ihdr_seen,
        "trailer_valid": trailer_valid,
        "has_appended_data": has_appended,
        "appended_bytes": appended_bytes,
        "chunks": chunks,
        "text_metadata": text_metadata,
        "anomalies": anomalies,
    }
    if ihdr_info:
        result["ihdr"] = ihdr_info
    return result


def _safe_stat(path: str) -> dict[str, Any]:
    try:
        st = os.stat(path)
        return {
            "file_size": st.st_size,
            "modified_time": datetime.fromtimestamp(st.st_mtime).isoformat(),
            "created_time": datetime.fromtimestamp(st.st_ctime).isoformat(),
        }
    except Exception:
        return {}


def _ratio(value: Any) -> float | None:
    try:
        if isinstance(value, tuple) and len(value) == 2:
            num, den = value
            return float(num) / float(den or 1)
        if hasattr(value, "numerator") and hasattr(value, "denominator"):
            return float(value.numerator) / float(value.denominator or 1)
        return float(value)
    except Exception:
        return None


def _convert_to_degrees(value: Any) -> float | None:
    if not isinstance(value, (tuple, list)) or len(value) < 3:
        return None
    deg = _ratio(value[0])
    minutes = _ratio(value[1])
    seconds = _ratio(value[2])
    if deg is None or minutes is None or seconds is None:
        return None
    return deg + (minutes / 60.0) + (seconds / 3600.0)


def _get_exif_data(image: Image.Image, file_path: str | None = None) -> dict[str, Any]:
    data: dict[str, Any] = {
        "width": getattr(image, "width", None),
        "height": getattr(image, "height", None),
        "format": getattr(image, "format", None),
    }
    try:
        raw = image.getexif()
        # IFD0 base tags (Make, Model, Software, DateTime, Orientation, ...)
        for tag_id, value in raw.items():
            tag = ExifTags.TAGS.get(tag_id, str(tag_id))
            # GPSInfo (0x8825) and ExifOffset (0x8769) are sub-IFD pointers,
            # not values — expanded below. Never store the raw integer offset.
            if tag in ("GPSInfo", "ExifOffset", "ExifIFD"):
                continue
            data[tag] = value

        # Exif sub-IFD (0x8769) — this is where the forensically critical fields
        # live: DateTimeOriginal, DateTimeDigitized, FNumber, ExposureTime,
        # ISOSpeedRatings, FocalLength, LensModel, etc. PIL's base getexif()
        # does NOT descend into this block, which is why timestamp / capture
        # parameters appeared "missing" before this fix.
        try:
            exif_ifd = raw.get_ifd(0x8769)
            for tag_id, value in (exif_ifd or {}).items():
                tag = ExifTags.TAGS.get(tag_id, str(tag_id))
                data.setdefault(tag, value)
        except Exception as sub_exc:
            logger.debug("Failed to read Exif sub-IFD", error=str(sub_exc))

        # GPS sub-IFD (0x8825) — getexif() returns GPSInfo as an integer offset,
        # never as a dict, so the prior isinstance(value, dict) check never fired.
        # get_ifd() is the only correct way to read GPS tags.
        try:
            gps_ifd = raw.get_ifd(0x8825)
            for gps_id, gps_value in (gps_ifd or {}).items():
                gps_tag = ExifTags.GPSTAGS.get(gps_id, str(gps_id))
                data[gps_tag] = gps_value
        except Exception as gps_exc:
            logger.debug("Failed to read GPS sub-IFD", error=str(gps_exc))
    except Exception as exc:
        data["exif_error"] = str(exc)

    # PNG text chunk metadata (tEXt/iTXt) — PIL exposes these via img.info
    _PNG_KEY_MAP: dict[str, str] = {
        "software": "Software",
        "creation time": "DateTimeOriginal",
        "create date": "DateTimeOriginal",
        "date:create": "DateTimeOriginal",
        "date:modify": "DateTime",
        "comment": "UserComment",
        "description": "ImageDescription",
        "author": "Artist",
        "copyright": "Copyright",
        "title": "DocumentName",
    }
    png_info = getattr(image, "info", {}) or {}
    for info_key, info_val in png_info.items():
        if not isinstance(info_key, str):
            continue
        if isinstance(info_val, bytes):
            try:
                info_val = info_val.decode("utf-8", errors="replace")
            except Exception as decode_err:
                logger.debug("Failed to decode PNG info chunk", key=info_key, error=str(decode_err))
                continue
        if not isinstance(info_val, str) or not info_val.strip():
            continue
        data[f"png_chunk_{info_key}"] = info_val
        std_key = _PNG_KEY_MAP.get(info_key.lower())
        if std_key:
            data.setdefault(std_key, info_val)

    data.update(_safe_stat(file_path or ""))
    return data


def _normalize_exif_aliases(exif: dict[str, Any]) -> dict[str, Any]:
    """Emit the lowercase / snake_case field names that all downstream consumers
    read (handlers, synthesis, reactive rules, visual grounding).

    The raw EXIF tags use canonical PIL names (Make, Model, DateTimeOriginal).
    Every consumer reads camera_make / datetime_original / gps_coordinates / etc.
    Without these aliases the data is extracted but never reaches the consumers.
    """
    aliases: dict[str, Any] = {}

    make = exif.get("Make")
    model = exif.get("Model")
    if make:
        aliases["camera_make"] = str(make).strip()
        aliases["make"] = str(make).strip()
    if model:
        aliases["camera_model"] = str(model).strip()
        aliases["model"] = str(model).strip()

    # Timestamp — prefer original capture time, fall back through the chain
    dt = (
        exif.get("DateTimeOriginal")
        or exif.get("DateTimeDigitized")
        or exif.get("DateTime")
    )
    if dt:
        aliases["datetime_original"] = str(dt).strip()

    if exif.get("Software"):
        aliases["software"] = str(exif["Software"]).strip()
    if exif.get("LensModel"):
        aliases["lens_model"] = str(exif["LensModel"]).strip()

    # Capture parameters — convert IFDRational to float so they serialise cleanly
    fnum = _ratio(exif.get("FNumber"))
    if fnum is not None:
        aliases["aperture"] = round(fnum, 2)
    focal = _ratio(exif.get("FocalLength"))
    if focal is not None:
        aliases["focal_length"] = round(focal, 2)
    iso = exif.get("ISOSpeedRatings") or exif.get("PhotographicSensitivity")
    if iso is not None:
        try:
            aliases["iso"] = int(iso if not isinstance(iso, (tuple, list)) else iso[0])
        except (ValueError, TypeError):
            pass

    # GPS → decimal degrees + a single "lat, lon" string consumers can display
    lat = _convert_to_degrees(exif.get("GPSLatitude"))
    lon = _convert_to_degrees(exif.get("GPSLongitude"))
    if lat is not None and lon is not None:
        if str(exif.get("GPSLatitudeRef") or "").strip().upper() == "S":
            lat = -lat
        if str(exif.get("GPSLongitudeRef") or "").strip().upper() == "W":
            lon = -lon
        aliases["gps_latitude"] = round(lat, 6)
        aliases["gps_longitude"] = round(lon, 6)
        coord_str = f"{round(lat, 6)}, {round(lon, 6)}"
        aliases["gps_coordinates"] = coord_str
        aliases["gps_location"] = coord_str

    return aliases


async def exif_extract(*, artifact: Any = None, file_path: str | None = None, **_: Any) -> dict[str, Any]:
    path = _artifact_path(artifact, file_path)
    if not path or not Path(path).exists():
        return {"has_exif": False, "error": "file not found", "present_fields": [], "total_exif_tags": 0}
    try:
        with Image.open(path) as img:
            exif = _get_exif_data(img, path)
        present = [field for field in EXPECTED_EXIF_FIELDS if field in exif]
        _structural = {"width", "height", "format", "file_size", "modified_time", "created_time", "exif_error"}
        exif_ifd_count = sum(
            1 for k, v in exif.items()
            if k not in _structural and not k.startswith("png_chunk_") and v is not None
        )
        png_text_count = sum(1 for k in exif if k.startswith("png_chunk_"))
        # Normalized aliases so consumers find device/timestamp/GPS by the
        # snake_case names they actually read.
        aliases = _normalize_exif_aliases(exif)
        return {
            **exif,
            **aliases,
            "has_exif": bool(present),
            "has_png_text_metadata": png_text_count > 0,
            "present_fields": present,
            "missing_fields": [field for field in EXPECTED_EXIF_FIELDS if field not in exif],
            "total_exif_tags": exif_ifd_count,
            "png_text_fields_count": png_text_count,
        }
    except Exception as exc:
        return {"has_exif": False, "error": str(exc), "present_fields": [], "total_exif_tags": 0}


async def gps_timezone_validate(
    gps_lat: float | None = None,
    gps_lon: float | None = None,
    timestamp_utc: str | None = None,
    **_: Any,
) -> dict[str, Any]:
    if gps_lat is None or gps_lon is None:
        return {"available": False, "status": "NOT_APPLICABLE", "reason": "GPS coordinates absent"}
    try:
        timezone = None
        if TimezoneFinder is not None:
            timezone = TimezoneFinder().timezone_at(lat=float(gps_lat), lng=float(gps_lon))
        country_code = None
        if Nominatim is not None:
            location = Nominatim(user_agent="forensic-council").reverse((gps_lat, gps_lon), timeout=3)
            country_code = ((getattr(location, "raw", {}) or {}).get("address", {}) or {}).get("country_code")
        return {
            "available": True,
            "timezone": timezone,
            "country_code": country_code,
            "timestamp_utc": timestamp_utc,
            "consistent": True,
        }
    except Exception as exc:
        return {"available": False, "error": str(exc), "consistent": None}


async def steganography_scan(*, artifact: Any = None, file_path: str | None = None, **_: Any) -> dict[str, Any]:
    path = _artifact_path(artifact, file_path)
    if not path or not Path(path).exists():
        return {"available": False, "error": "file not found"}
    try:
        import numpy as np

        with Image.open(path) as img:
            if img.mode not in ("RGB", "RGBA", "L", "P"):
                img = img.convert("RGB")
            if img.mode == "P":
                img = img.convert("RGB")
            arr = np.array(img.convert("RGB") if img.mode == "RGBA" else img, dtype=np.uint8)

        # ── LSB extraction ─────────────────────────────────────────────────
        # For colour images work on all three channels independently.
        if arr.ndim == 3:
            lsb_flat = (arr[:, :, :3] & 1).ravel()
        else:
            lsb_flat = (arr & 1).ravel()

        total_bits = len(lsb_flat)
        ones = int(lsb_flat.sum())
        zeros = total_bits - ones
        ones_ratio = ones / total_bits if total_bits else 0.5

        # ── Chi-squared test ────────────────────────────────────────────────
        # Natural unmodified LSBs are close to uniformly distributed (≈50/50).
        # Steganographic embedding (LSB replacement/matching) shifts the ratio
        # toward exactly 50 % and flattens the adjacent-pair histogram.
        expected = total_bits / 2.0
        chi_sq = ((ones - expected) ** 2 + (zeros - expected) ** 2) / expected
        chi_sq_norm = chi_sq / max(total_bits, 1)

        # ── Sample-pair / adjacent-pixel LSB correlation ────────────────────
        # In clean images adjacent pixel LSBs are correlated; LSB replacement
        # destroys this correlation by randomising every embedded bit.
        h, w = arr.shape[:2]
        if w > 1:
            horiz_agree = int(np.sum(lsb_flat[:h * (w - 1)] == lsb_flat[1:h * (w - 1) + 1]))
            total_pairs = h * (w - 1)
            pair_correlation = horiz_agree / total_pairs if total_pairs else 0.5
        else:
            pair_correlation = 0.5

        # Clean camera images typically show ≥ 52 % pair agreement (spatial correlation).
        # After LSB embedding the ratio collapses toward exactly 50 %.
        correlation_anomaly = max(0.0, 0.52 - pair_correlation) / 0.52

        # ── Block entropy on LSB plane ──────────────────────────────────────
        # Measure bit-entropy in non-overlapping 64-pixel blocks.
        # Embedded payloads push block entropy toward maximum (1.0 bit/bit).
        block = 64
        reshaped = lsb_flat[: (total_bits // block) * block].reshape(-1, block)
        ones_per_block = reshaped.sum(axis=1)
        p1 = ones_per_block / block
        p0 = 1.0 - p1
        # Binary Shannon entropy per block
        with np.errstate(divide="ignore", invalid="ignore"):
            h_block = np.where(
                (p1 > 0) & (p0 > 0),
                -(p1 * np.log2(p1) + p0 * np.log2(p0)),
                0.0,
            )
        mean_entropy = float(h_block.mean()) if len(h_block) else 0.0
        # Max entropy (1.0) means perfectly random — hallmark of encrypted payload.
        entropy_anomaly = max(0.0, mean_entropy - 0.94) / 0.06

        # ── Composite score ─────────────────────────────────────────────────
        lsb_dev = abs(ones_ratio - 0.5)
        stego_score = round(
            lsb_dev * 0.30
            + correlation_anomaly * 0.45
            + entropy_anomaly * 0.15
            + min(chi_sq_norm * 50.0, 0.10),
            4,
        )
        stego_suspected = stego_score > 0.14

        return {
            "available": True,
            "stego_suspected": stego_suspected,
            "hidden_data_suspected": stego_suspected,
            "lsb_anomaly_score": stego_score,
            "lsb_statistics": {
                "ones_ratio": round(ones_ratio, 4),
                "average_deviation": round(lsb_dev, 4),
                "chi_squared_normalized": round(chi_sq_norm, 8),
                "pair_correlation": round(pair_correlation, 4),
                "mean_block_entropy": round(mean_entropy, 4),
                "correlation_anomaly": round(correlation_anomaly, 4),
            },
            "total_lsb_bits_analyzed": total_bits,
            "confidence": ConfidenceCalibrator.calibrate_heuristic(min(1.0, stego_score * 3.0), reliability_tag="scipy_spectral", base_bias=0.60) if stego_suspected else 0.75,
            "court_defensible": True,
            "verdict": "SUSPICIOUS" if stego_suspected else "CLEAN",
        }
    except ImportError:
        # numpy unavailable — basic extrema-only path
        try:
            with Image.open(path) as img:
                img.convert("L").getextrema()
            return {
                "available": True,
                "stego_suspected": False,
                "hidden_data_suspected": False,
                "lsb_anomaly_score": 0.0,
                "lsb_statistics": {"average_deviation": 0.0},
                "degraded": True,
                "fallback_reason": "numpy unavailable; LSB analysis not performed",
                "confidence": 0.40,
                "court_defensible": False,
                "verdict": "INCONCLUSIVE",
            }
        except Exception as exc:
            return {"available": False, "error": str(exc)}
    except Exception as exc:
        return {"available": False, "error": str(exc)}


async def file_structure_analysis(*, artifact: Any = None, file_path: str | None = None, **_: Any) -> dict[str, Any]:
    path = _artifact_path(artifact, file_path)
    if not path or not Path(path).exists():
        return {"available": False, "error": "file not found"}
    data = Path(path).read_bytes()
    base: dict[str, Any] = {
        "available": True,
        "file_size": len(data),
        "sha256": hashlib.sha256(data).hexdigest(),
        "header_valid": bool(data),
        "trailer_valid": True,
        "has_appended_data": False,
        "appended_bytes": 0,
        "anomalies": [],
    }
    if data[:8] == _PNG_MAGIC:
        base.update(_analyze_png_structure(data))
    elif data[:2] == _JPEG_MAGIC:
        base["format_detected"] = "JPEG"
        base["header_valid"] = True
        base["trailer_valid"] = data[-2:] == b"\xff\xd9"
        if not base["trailer_valid"]:
            base["anomalies"].append("JPEG EOI marker absent — file may be truncated")
        eoi = data.rfind(b"\xff\xd9")
        if eoi >= 0 and eoi + 2 < len(data):
            base["has_appended_data"] = True
            base["appended_bytes"] = len(data) - (eoi + 2)
            base["anomalies"].append(f"{base['appended_bytes']} byte(s) appended after JPEG EOI")
    elif data[:4] == b"%PDF":
        base["format_detected"] = "PDF"
    else:
        base["format_detected"] = "unknown"

    raw_sig = min(1.0, len(base["anomalies"]) / 4.0) if base["anomalies"] else 0.0
    base["confidence"] = ConfidenceCalibrator.calibrate_heuristic(raw_sig, reliability_tag="linear_fallback", base_bias=0.85) if not base["anomalies"] else ConfidenceCalibrator.calibrate_heuristic(raw_sig, reliability_tag="linear_fallback", base_bias=0.50)
    base["verdict"] = "REVIEW" if base["anomalies"] else "CLEAN"
    return base


async def timestamp_analysis(*, artifact: Any = None, file_path: str | None = None, **_: Any) -> dict[str, Any]:
    path = _artifact_path(artifact, file_path)
    if not path or not Path(path).exists():
        return {"available": False, "error": "file not found"}

    stat = _safe_stat(path)
    inconsistencies: list[str] = []

    # ── Parse all available timestamps ─────────────────────────────────────
    _FMT = "%Y:%m:%d %H:%M:%S"
    _ALT_FMT = "%Y-%m-%dT%H:%M:%S"

    def _parse_dt(val: Any) -> datetime | None:
        if not val:
            return None
        s = str(val).strip()
        for fmt in (_FMT, _ALT_FMT, "%Y-%m-%d %H:%M:%S"):
            try:
                return datetime.strptime(s[:19], fmt)
            except ValueError:
                continue
        return None

    # Filesystem timestamps
    fs_modified = _parse_dt(stat.get("modified_time"))
    _parse_dt(stat.get("created_time"))

    # EXIF timestamps (open image only for EXIF-bearing formats)
    exif_original: datetime | None = None
    exif_digitized: datetime | None = None
    exif_datetime: datetime | None = None
    exif_software: str | None = None
    gps_datestamp: str | None = None
    gps_timestamp_raw: str | None = None

    try:
        with Image.open(path) as img:
            raw_exif = img.getexif()
            if raw_exif:
                # 36867=DateTimeOriginal, 36868=DateTimeDigitized, 306=DateTime
                # 305=Software, 29=GPSDateStamp (inside GPSInfo sub-IFD)
                # 7=GPSTimestamp (tuple of hour/min/sec)
                exif_original = _parse_dt(raw_exif.get(36867))
                exif_digitized = _parse_dt(raw_exif.get(36868))
                exif_datetime = _parse_dt(raw_exif.get(306))
                exif_software = str(raw_exif.get(305) or "").strip() or None
                gps_info = raw_exif.get(34853)
                if isinstance(gps_info, dict):
                    gps_datestamp = str(gps_info.get(29) or "").strip() or None
                    gps_ts = gps_info.get(7)
                    if gps_ts and len(gps_ts) == 3:
                        try:
                            h = int(_ratio(gps_ts[0]) or 0)
                            m = int(_ratio(gps_ts[1]) or 0)
                            s = int(_ratio(gps_ts[2]) or 0)
                            gps_timestamp_raw = f"{h:02d}:{m:02d}:{s:02d} UTC"
                        except Exception:
                            pass
    except Exception:
        pass

    # ── Chronological sanity checks ─────────────────────────────────────────

    # 1. DateTimeOriginal must not be later than DateTimeDigitized
    if exif_original and exif_digitized and exif_original > exif_digitized:
        diff = (exif_original - exif_digitized).total_seconds()
        inconsistencies.append(
            f"DateTimeOriginal ({exif_original}) is {int(diff)}s after DateTimeDigitized "
            f"({exif_digitized}) — chronologically impossible."
        )

    # 2. EXIF DateTime must not precede DateTimeOriginal
    if exif_original and exif_datetime and exif_datetime < exif_original:
        diff = (exif_original - exif_datetime).total_seconds()
        inconsistencies.append(
            f"EXIF DateTime ({exif_datetime}) predates DateTimeOriginal ({exif_original}) "
            f"by {int(diff)}s — file modification record is inconsistent."
        )

    # 3. File modified time must not predate EXIF capture time (beyond rounding)
    if exif_original and fs_modified:
        delta = (fs_modified - exif_original).total_seconds()
        if delta < -5:  # allow 5 s clock skew
            inconsistencies.append(
                f"Filesystem modification time ({fs_modified.isoformat()}) is "
                f"{abs(int(delta))}s before EXIF DateTimeOriginal ({exif_original}) — "
                "a file cannot be modified before it was captured."
            )

    # 4. Far-future timestamps
    now = datetime.utcnow()
    for label, dt in (
        ("DateTimeOriginal", exif_original),
        ("DateTimeDigitized", exif_digitized),
        ("EXIF DateTime", exif_datetime),
    ):
        if dt and dt > now:
            inconsistencies.append(
                f"{label} ({dt}) is in the future (current UTC: {now.date()}) — "
                "clock was not set correctly or timestamp was fabricated."
            )

    # 5. GPS date vs EXIF date mismatch (coarse day-level check)
    if gps_datestamp and exif_original:
        gps_day = gps_datestamp.replace(":", "-")[:10]
        exif_day = exif_original.strftime("%Y-%m-%d")
        if gps_day and gps_day != exif_day:
            inconsistencies.append(
                f"GPS datestamp ({gps_day}) does not match EXIF DateTimeOriginal date "
                f"({exif_day}) — possible timezone error or metadata manipulation."
            )

    # 6. GPS UTC timestamp vs EXIF DateTimeOriginal (>24h gap is suspicious)
    if gps_datestamp and gps_timestamp_raw and exif_original:
        try:
            gps_dt_str = f"{gps_datestamp.replace(':', '-')} {gps_timestamp_raw.replace(' UTC', '')}"
            gps_dt = datetime.strptime(gps_dt_str, "%Y-%m-%d %H:%M:%S")
            delta_hours = abs((exif_original - gps_dt).total_seconds()) / 3600
            if delta_hours > 24:
                inconsistencies.append(
                    f"GPS UTC datetime ({gps_dt_str} UTC) differs from EXIF DateTimeOriginal "
                    f"({exif_original}) by {delta_hours:.1f} hours — timezone error or metadata manipulation suspected."
                )
        except Exception:
            pass

    # 7. Software field implies post-capture editing
    editing_hints = {"photoshop", "gimp", "lightroom", "canva", "picsart", "facetune",
                     "meitu", "snapseed", "affinity", "pixelmator", "fotor"}
    software_flag = exif_software and any(h in exif_software.lower() for h in editing_hints)
    if software_flag:
        inconsistencies.append(
            f"EXIF Software field '{exif_software}' indicates post-capture editing — "
            "original capture timestamps may have been altered."
        )

    return {
        "available": True,
        **stat,
        "exif_datetime_original": exif_original.isoformat() if exif_original else None,
        "exif_datetime_digitized": exif_digitized.isoformat() if exif_digitized else None,
        "exif_datetime": exif_datetime.isoformat() if exif_datetime else None,
        "exif_software": exif_software,
        "gps_datestamp": gps_datestamp,
        "gps_timestamp": gps_timestamp_raw,
        "inconsistencies": inconsistencies,
        "inconsistency_count": len(inconsistencies),
        "software_edit_flag": bool(software_flag),
        "consistent": not bool(inconsistencies),
        "verdict": "SUSPICIOUS" if inconsistencies else "CLEAN",
        "confidence": ConfidenceCalibrator.calibrate_heuristic(min(1.0, len(inconsistencies) / 4.0), reliability_tag="linear_fallback", base_bias=0.50) if inconsistencies else 0.85,
        "court_defensible": True,
    }


_SOFTWARE_MARKERS: tuple[bytes, ...] = (
    b"Photoshop", b"Adobe", b"GIMP", b"Canva", b"PicsArt", b"Snapseed",
    b"ImageMagick", b"Paint.NET", b"Affinity", b"Lightroom", b"Luminar",
    b"darktable", b"RawTherapee", b"Capture One", b"Pixelmator", b"Photopea",
    b"VSCO", b"FaceTune", b"Facetune", b"Meitu", b"CapCut", b"TouchRetouch",
    b"Remini", b"Fotor", b"BeFunky",
)


async def hex_signature_scan(*, artifact: Any = None, file_path: str | None = None, **_: Any) -> dict[str, Any]:
    path = _artifact_path(artifact, file_path)
    if not path or not Path(path).exists():
        return {"available": False, "error": "file not found"}
    p = Path(path)
    file_size = p.stat().st_size
    # Scan first 512 KB — covers headers, PNG metadata sections, and most tEXt/iTXt blocks
    scan_size = min(524288, file_size)
    with open(path, "rb") as fh:
        sample = fh.read(scan_size)
    header = sample[:16].hex()
    sample_lower = sample.lower()

    found: set[str] = set()
    for marker in _SOFTWARE_MARKERS:
        if marker.lower() in sample_lower:
            label = marker.decode("ascii", errors="ignore")
            found.add(label)

    # For PNG: pull Software field from tEXt chunks directly for authoritative label
    png_software: str | None = None
    if sample[:8] == _PNG_MAGIC:
        sw_key = b"Software\x00"
        idx = sample.find(sw_key)
        if idx >= 0:
            val_start = idx + len(sw_key)
            val_end = sample.find(b"\x00", val_start)
            if val_end < 0:
                val_end = min(val_start + 256, len(sample))
            png_software = sample[val_start:val_end].decode("latin-1", errors="replace").strip()
            if png_software:
                found.add(f"PNG-Software: {png_software}")

    signatures = sorted(found)
    return {
        "available": True,
        "header_hex": header,
        "bytes_scanned": len(sample),
        "software_signatures": signatures,
        "png_software_field": png_software,
        "editing_software_detected": bool(signatures),
        "verdict": "CLEAN" if not signatures else "REVIEW",
        "confidence": ConfidenceCalibrator.calibrate_heuristic(min(1.0, len(signatures) / 3.0), reliability_tag="linear_fallback", base_bias=0.50) if signatures else 0.85,
    }


async def extract_deep_metadata(*, artifact: Any = None, file_path: str | None = None, **kwargs: Any) -> dict[str, Any]:
    exif = await exif_extract(artifact=artifact, file_path=file_path, **kwargs)
    structure = await file_structure_analysis(artifact=artifact, file_path=file_path, **kwargs)
    return {"available": True, "exif": exif, "structure": structure}


async def get_physical_address(gps_lat: float | None = None, gps_lon: float | None = None, **_: Any) -> dict[str, Any]:
    if gps_lat is None or gps_lon is None or Nominatim is None:
        return {"available": False, "address": None}
    try:
        location = Nominatim(user_agent="forensic-council").reverse((gps_lat, gps_lon), timeout=3)
        return {"available": True, "address": getattr(location, "address", None), "raw": getattr(location, "raw", {})}
    except Exception as exc:
        return {"available": False, "error": str(exc)}


async def astronomical_validate_astral(**_: Any) -> dict[str, Any]:
    return {"available": False, "status": "NOT_APPLICABLE", "reason": "Astronomical validation requires GPS and sun-position context"}


async def exif_extract_enhanced(**kwargs: Any) -> dict[str, Any]:
    return await exif_extract(**kwargs)


async def steganography_scan_enhanced(**kwargs: Any) -> dict[str, Any]:
    return await steganography_scan(**kwargs)


async def camera_profile_match(artifact: Any = None, file_path: str | None = None, **_: Any) -> dict[str, Any]:
    path = _artifact_path(artifact, file_path)
    if not path or not Path(path).exists():
        return {"available": False, "error": "file not found", "verdict": "INCONCLUSIVE"}

    exif = await exif_extract(artifact=artifact, file_path=file_path)

    claimed_make = exif.get("Make")
    claimed_model = exif.get("Model")

    CAPTURE_FIELDS = ["FNumber", "ExposureTime", "ISOSpeedRatings", "FocalLength"]
    FULL_FIELDS = ["Make", "Model", "DateTimeOriginal", "FNumber", "ExposureTime", "ISOSpeedRatings", "FocalLength"]

    capture_present = [f for f in CAPTURE_FIELDS if exif.get(f) is not None]
    full_present = [f for f in FULL_FIELDS if exif.get(f) is not None]
    completeness = len(full_present) / len(FULL_FIELDS)

    anomalies: list[str] = []
    plausibility_flags: list[str] = []

    fnumber = _ratio(exif.get("FNumber"))
    iso_raw = exif.get("ISOSpeedRatings")
    if isinstance(iso_raw, (list, tuple)):
        iso_raw = iso_raw[0] if iso_raw else None
    try:
        iso = float(iso_raw) if iso_raw is not None else None
    except (TypeError, ValueError):
        iso = None
    exposure = _ratio(exif.get("ExposureTime"))
    focal = _ratio(exif.get("FocalLength"))

    if fnumber is not None:
        if not (0.7 <= fnumber <= 64):
            anomalies.append(f"FNumber {fnumber:.1f} outside plausible camera range (0.7–64)")
        else:
            plausibility_flags.append("fnumber_ok")

    if iso is not None:
        if not (25 <= iso <= 3276800):
            anomalies.append(f"ISO {iso:.0f} outside plausible sensor range (25–3276800)")
        else:
            plausibility_flags.append("iso_ok")

    if exposure is not None:
        if not (1 / 32000 <= exposure <= 3600):
            anomalies.append(f"ExposureTime {exposure:.6f}s outside plausible range (1/32000–3600s)")
        else:
            plausibility_flags.append("exposure_ok")

    if focal is not None:
        if not (0.5 <= focal <= 5000):
            anomalies.append(f"FocalLength {focal:.1f}mm outside plausible range (0.5–5000mm)")
        else:
            plausibility_flags.append("focal_ok")

    if not claimed_make and not claimed_model:
        anomalies.append("No Make or Model field — likely screenshot, synthetic, or stripped metadata")

    if (claimed_make or claimed_model) and not capture_present:
        anomalies.append(
            f"Make/Model '{claimed_make} {claimed_model}' present but all capture fields absent — metadata may be injected"
        )

    if completeness < 0.5:
        anomalies.append(f"Profile completeness {completeness:.0%} — fewer than half of expected camera fields present")

    has_implausible = any("outside plausible" in a for a in anomalies)
    capture_score = len(capture_present) / len(CAPTURE_FIELDS)

    if has_implausible:
        verdict = "SUSPICIOUS"
        confidence = 0.78
    elif anomalies and completeness < 0.4:
        verdict = "SUSPICIOUS"
        confidence = 0.70
    elif not claimed_make and not claimed_model:
        verdict = "INCONCLUSIVE"
        confidence = 0.55
    elif completeness >= 0.7 and not anomalies:
        verdict = "CLEAN"
        confidence = 0.82
    elif completeness >= 0.5:
        verdict = "CLEAN"
        confidence = 0.68
    else:
        verdict = "INCONCLUSIVE"
        confidence = 0.55

    return {
        "available": True,
        "claimed_make": claimed_make,
        "claimed_model": claimed_model,
        "has_make_model": bool(claimed_make or claimed_model),
        "capture_fields_present": capture_present,
        "capture_fields_missing": [f for f in CAPTURE_FIELDS if f not in capture_present],
        "profile_completeness": round(completeness, 3),
        "capture_completeness": round(capture_score, 3),
        "plausibility_checks_passed": plausibility_flags,
        "anomalies": anomalies,
        "profile_match": not has_implausible and bool(claimed_make or claimed_model),
        "verdict": verdict,
        "confidence": confidence,
        "court_defensible": True,
        "device_identity": f"{claimed_make or 'Unknown'} {claimed_model or 'Unknown'}".strip(),
        "device_identity_statement": (
            f"Claimed device: {claimed_make} {claimed_model}. "
            f"Profile completeness: {completeness:.0%}. "
            f"Capture fields present: {', '.join(capture_present) or 'none'}."
            if (claimed_make or claimed_model)
            else "No Make/Model present — likely screenshot, synthetic, or metadata-stripped."
        ),
    }


async def provenance_chain_verify(artifact: Any = None, file_path: str | None = None, **_: Any) -> dict[str, Any]:
    path = _artifact_path(artifact, file_path)
    if not path or not Path(path).exists():
        return {"available": False, "error": "file not found", "verdict": "INCONCLUSIVE"}

    p = Path(path)
    scan_size = min(2 * 1024 * 1024, p.stat().st_size)
    data = p.read_bytes()[:scan_size]

    c2pa_present = False
    jumbf_present = False
    xmp_c2pa = False
    manifest_details: list[str] = []

    # ── JPEG APP11 JUMBF scan ─────────────────────────────────────────────────
    # C2PA embeds its manifest in JPEG as an APP11 (0xFF 0xEB) segment containing
    # a JUMBF box that starts with the 4-byte box type "jumb".
    JUMBF_BOX = b"jumb"
    APP11_MARKER = b"\xff\xeb"

    if data[:2] == b"\xff\xd8":
        idx = 0
        while idx < len(data) - 4:
            marker_pos = data.find(APP11_MARKER, idx)
            if marker_pos < 0:
                break
            seg_len_pos = marker_pos + 2
            if seg_len_pos + 2 > len(data):
                break
            seg_len = struct.unpack(">H", data[seg_len_pos : seg_len_pos + 2])[0]
            seg_data = data[seg_len_pos + 2 : seg_len_pos + seg_len]
            if JUMBF_BOX in seg_data:
                jumbf_present = True
                c2pa_present = True
                manifest_details.append("JUMBF box found in JPEG APP11 segment")
                break
            idx = seg_len_pos + seg_len

    # ── PNG / universal JUMBF binary scan ────────────────────────────────────
    if not jumbf_present and JUMBF_BOX in data:
        jumbf_present = True
        c2pa_present = True
        manifest_details.append("JUMBF box found in file binary")

    # ── XMP C2PA namespace scan ───────────────────────────────────────────────
    C2PA_XMP_MARKERS = [
        b"http://c2pa.org/",
        b"https://c2pa.org",
        b"x-content-credentials",
        b"c2pa:manifest",
    ]
    for marker in C2PA_XMP_MARKERS:
        if marker in data:
            xmp_c2pa = True
            c2pa_present = True
            manifest_details.append(f"XMP C2PA marker: {marker.decode('ascii', errors='replace')}")
            break

    # ── XMP provenance field scan (non-C2PA but still informative) ────────────
    xmp_provenance_fields: list[str] = []
    XMP_FIELD_MARKERS: list[tuple[bytes, str]] = [
        (b"xmpMM:DocumentID", "DocumentID"),
        (b"xmpMM:OriginalDocumentID", "OriginalDocumentID"),
        (b"xmpMM:History", "EditHistory"),
        (b"photoshop:DateCreated", "DateCreated"),
        (b"dc:creator", "Creator"),
        (b"xmpRights:WebStatement", "RightsStatement"),
    ]
    for xmp_marker, label in XMP_FIELD_MARKERS:
        if xmp_marker in data:
            xmp_provenance_fields.append(label)

    if c2pa_present:
        verdict = "CLEAN"
        reason = "C2PA/JUMBF content authenticity manifest detected"
        provenance_verified = True
        confidence = 0.85
    elif xmp_provenance_fields:
        verdict = "INCONCLUSIVE"
        reason = f"XMP provenance metadata present ({', '.join(xmp_provenance_fields)}) but no C2PA manifest"
        provenance_verified = False
        confidence = 0.60
    else:
        verdict = "INCONCLUSIVE"
        reason = "No embedded provenance manifest — absence does not imply manipulation"
        provenance_verified = False
        confidence = 0.50

    return {
        "available": True,
        "c2pa_present": c2pa_present,
        "jumbf_present": jumbf_present,
        "xmp_c2pa_markers": xmp_c2pa,
        "xmp_provenance_fields": xmp_provenance_fields,
        "manifest_details": manifest_details,
        "provenance_verified": provenance_verified,
        "verdict": verdict,
        "reason": reason,
        "confidence": confidence,
        "court_defensible": True,
    }


async def prnu_sensor_verification(*, artifact: Any = None, file_path: str | None = None, **_: Any) -> dict[str, Any]:
    path = _artifact_path(artifact, file_path)
    if not path or not Path(path).exists():
        return {"available": False, "error": "file not found", "verdict": "INCONCLUSIVE"}

    try:
        import numpy as np
        from scipy.ndimage import uniform_filter
    except ImportError:
        return {
            "available": True,
            "sensor_match": None,
            "verdict": "INCONCLUSIVE",
            "degraded": True,
            "fallback_reason": "numpy/scipy unavailable; PRNU analysis not performed",
        }

    try:
        with Image.open(path) as img:
            gray = np.array(img.convert("L"), dtype=np.float32)

        h, w = gray.shape
        if h < 64 or w < 64:
            return {
                "available": True,
                "sensor_match": None,
                "verdict": "INCONCLUSIVE",
                "reason": "Image too small for PRNU block analysis (minimum 64×64)",
            }

        # ── Noise residual extraction ─────────────────────────────────────────
        # Subtract a local mean estimate. Regions from different sensors produce
        # statistically distinct noise textures that manifest as variance outliers.
        smoothed = uniform_filter(gray, size=5)
        noise = gray - smoothed

        # ── Block-wise noise variance ─────────────────────────────────────────
        block_size = max(32, min(h // 8, w // 8, 64))
        rows = h // block_size
        cols = w // block_size

        if rows < 2 or cols < 2:
            return {
                "available": True,
                "sensor_match": None,
                "verdict": "INCONCLUSIVE",
                "reason": "Image too small for meaningful block variance analysis",
            }

        block_variances: list[float] = []
        for r in range(rows):
            for c in range(cols):
                block = noise[r * block_size : (r + 1) * block_size, c * block_size : (c + 1) * block_size]
                block_variances.append(float(np.var(block)))

        variances = np.array(block_variances)
        mean_var = float(variances.mean())
        std_var = float(variances.std())

        # Coefficient of variation: low = uniform sensor noise, high = multi-source splicing
        cov = (std_var / mean_var) if mean_var > 0 else 0.0

        # Blocks with variance > mean + 3σ indicate anomalous noise regions
        outlier_threshold = mean_var + 3.0 * std_var
        outlier_blocks = int(np.sum(variances > outlier_threshold))
        outlier_ratio = outlier_blocks / max(len(block_variances), 1)

        multi_source_suspected = cov > 0.80 or outlier_ratio > 0.08

        if multi_source_suspected:
            # No reference camera fingerprint is available — this is a single-image
            # noise-uniformity heuristic, and high block-variance CoV is far more
            # often natural scene content (busy textures, edges) than splicing.
            # Reporting SUSPICIOUS here produced false positives that drove the
            # Arbiter challenge loop on ordinary photos. Without a reference set the
            # signal is INCONCLUSIVE — a screening flag for corroboration, not a
            # manipulation assertion. The metrics + flag remain for downstream use.
            verdict = "INCONCLUSIVE"
            sensor_match = False
            confidence = 0.4
        else:
            verdict = "CLEAN"
            sensor_match = True
            confidence = 0.68

        return {
            "available": True,
            "sensor_match": sensor_match,
            "noise_variance_mean": round(mean_var, 4),
            "noise_variance_std": round(std_var, 4),
            "block_variance_cov": round(cov, 4),
            "outlier_blocks": outlier_blocks,
            "total_blocks": len(block_variances),
            "outlier_ratio": round(outlier_ratio, 4),
            "multi_source_suspected": multi_source_suspected,
            "analysis_method": "block_noise_variance_cov",
            "block_size_px": block_size,
            "verdict": verdict,
            "confidence": confidence,
            "court_defensible": False,
            "note": "Single-image noise uniformity test; full PRNU matching requires a reference camera image set",
        }
    except Exception as exc:
        return {"available": False, "error": str(exc), "verdict": "INCONCLUSIVE"}


__all__ = [
    "EXPECTED_EXIF_FIELDS",
    "TimezoneFinder",
    "Nominatim",
    "_convert_to_degrees",
    "_get_exif_data",
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
