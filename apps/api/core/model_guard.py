"""
In-process model memory guard
==============================

Heavy ML models that load their weights *inside* the API/worker process
(EasyOCR, Florence-2, DETR/YOLO, OpenCLIP, the audio classifier) cannot be
protected by ``ml_subprocess``' RLIMIT_AS isolation. If one of them allocates
more than the container has free, the kernel OOM-killer sends SIGKILL to the
whole process — an uncatchable crash that takes down every in-flight
investigation, not just the offending tool.

This module converts that class of crash into an honest, recoverable
"tool unavailable" outcome by:

  1. Probing the real memory ceiling (container cgroup limit, else host RAM)
     with **zero third-party dependencies** — psutil is not installed.
  2. Refusing to start a load that would not fit within a safety headroom,
     raising :class:`ModelMemoryError` so the caller's existing try/except
     returns a graceful unavailable result (surfaced downstream as a coverage
     gap, never as a fabricated clean finding).
  3. Serialising heavy in-process loads through a single lock so two big
     models cannot spike memory simultaneously.
  4. Capping inference input resolution, since a single oversized image is the
     most common trigger for an inference-time OOM.

All probes fail open: when the ceiling cannot be determined (typical on a dev
workstation), loads are allowed. The guard only ever *blocks* when it has
positive evidence that memory is insufficient.
"""

from __future__ import annotations

import contextlib
import os
import threading
from pathlib import Path
from typing import TYPE_CHECKING

from core.structured_logging import get_logger

if TYPE_CHECKING:
    from PIL import Image as _PILImage

logger = get_logger(__name__)


class ModelMemoryError(RuntimeError):
    """Raised when there is not enough free memory to safely load a model."""


# Serialises heavy in-process model loads so concurrent agents cannot trigger
# two multi-hundred-MB allocations at the same instant.
MODEL_LOAD_LOCK = threading.Lock()

# Conservative resident-set estimates (MB) for the cost of *loading* each model
# on CPU in fp32, including transient allocation spikes. Used as the default
# when a caller does not pass an explicit figure.
MODEL_FOOTPRINT_MB: dict[str, float] = {
    "easyocr": 900.0,        # CRAFT detector + CRNN recogniser
    "florence2": 1100.0,     # Florence-2-base VLM (~0.23B params)
    "detr": 700.0,           # DETR ResNet-50 object detector
    "yolo": 500.0,
    "clip": 700.0,           # OpenCLIP ViT-B-32 (+ torchvision cascade)
    "aasist": 900.0,         # wav2vec-style audio anti-spoofing
}

_DEFAULT_MIN_FREE_MB = 768.0
_DEFAULT_MAX_INFERENCE_DIM = 2560


def _read_int(path: str) -> int | None:
    try:
        with open(path) as fh:
            return int(fh.read().strip())
    except (OSError, ValueError):
        return None


def _cgroup_available_mb() -> float | None:
    """Available memory inside a Linux container, derived from cgroup limits.

    Honours both cgroup v2 (``memory.max`` / ``memory.current``) and cgroup v1
    (``memory.limit_in_bytes`` / ``memory.usage_in_bytes``). Returns ``None``
    when no finite limit is configured so the caller falls back to host RAM.
    """
    # cgroup v2
    v2_max = Path("/sys/fs/cgroup/memory.max")
    if v2_max.exists():
        raw = v2_max.read_text().strip() if v2_max.is_file() else ""
        if raw and raw != "max":
            try:
                limit = int(raw)
            except ValueError:
                limit = None
            current = _read_int("/sys/fs/cgroup/memory.current")
            if limit and current is not None:
                return max(0.0, (limit - current) / (1024 * 1024))

    # cgroup v1
    limit = _read_int("/sys/fs/cgroup/memory/memory.limit_in_bytes")
    usage = _read_int("/sys/fs/cgroup/memory/memory.usage_in_bytes")
    # A near-INT64_MAX limit means "unlimited" — ignore it.
    if limit and usage is not None and limit < (1 << 62):
        return max(0.0, (limit - usage) / (1024 * 1024))

    return None


def _proc_meminfo_available_mb() -> float | None:
    """Host-level available memory from /proc/meminfo (Linux)."""
    try:
        with open("/proc/meminfo") as fh:
            for line in fh:
                if line.startswith("MemAvailable:"):
                    # Value is in kB.
                    return float(line.split()[1]) / 1024.0
    except (OSError, ValueError, IndexError):
        return None
    return None


def available_memory_mb() -> float | None:
    """Best-effort free memory in MB, or ``None`` if it cannot be determined.

    Prefers the container cgroup ceiling (the real constraint in production),
    then host ``/proc/meminfo``. Returns ``None`` on non-Linux/dev hosts, which
    callers treat as "allow the load".
    """
    return _cgroup_available_mb() or _proc_meminfo_available_mb()


def _settings_value(name: str, default: float | int) -> float | int:
    try:
        from core.config import get_settings

        return getattr(get_settings(), name, default)
    except Exception:
        return default


def ensure_load_headroom(model_name: str, required_mb: float | None = None) -> None:
    """Raise :class:`ModelMemoryError` if a model cannot be loaded safely.

    ``required_mb`` defaults to :data:`MODEL_FOOTPRINT_MB` for known models.
    The guard fails open: if free memory is unknown it permits the load.
    """
    required = required_mb if required_mb is not None else MODEL_FOOTPRINT_MB.get(model_name, 600.0)
    min_free = float(_settings_value("model_load_min_free_mb", _DEFAULT_MIN_FREE_MB))
    avail = available_memory_mb()
    if avail is None:
        return  # Unknown ceiling (dev host) — allow.
    needed = required + min_free
    if avail < needed:
        raise ModelMemoryError(
            f"insufficient memory to load '{model_name}': "
            f"{avail:.0f}MB free, needs ~{needed:.0f}MB "
            f"({required:.0f}MB model + {min_free:.0f}MB headroom)"
        )


@contextlib.contextmanager
def guarded_load(model_name: str, required_mb: float | None = None, *, lock_timeout: float = 180.0):
    """Serialise and memory-check a heavy in-process model load.

    Acquires :data:`MODEL_LOAD_LOCK` (so loads never stack), then verifies
    headroom *after* acquisition — by which point any concurrent load has
    finished and freed its transient allocation, giving an accurate reading.

    Raises :class:`ModelMemoryError` when memory is insufficient. The lock is
    always released on exit. If the lock cannot be acquired within
    ``lock_timeout`` the load proceeds unserialised rather than deadlocking.
    """
    acquired = MODEL_LOAD_LOCK.acquire(timeout=lock_timeout)
    if not acquired:
        logger.warning(
            "model load lock not acquired within timeout; proceeding unserialised",
            model=model_name,
        )
    try:
        ensure_load_headroom(model_name, required_mb)
        yield
    finally:
        if acquired:
            MODEL_LOAD_LOCK.release()


def cap_image_dimension(image: "_PILImage.Image", max_dim: int | None = None) -> "_PILImage.Image":
    """Downscale a PIL image so its longest side is at most ``max_dim`` px.

    Heavy vision models allocate memory proportional to input area; a single
    4K+ screenshot can OOM CPU inference. OCR and captioning do not need full
    resolution, so capping the longest side is a safe, large memory saving.
    Returns the original image untouched when already within bounds.
    """
    limit = int(max_dim if max_dim is not None else _settings_value("model_max_inference_dim", _DEFAULT_MAX_INFERENCE_DIM))
    if limit <= 0:
        return image
    longest = max(image.width, image.height)
    if longest <= limit:
        return image
    scale = limit / float(longest)
    new_size = (max(1, int(image.width * scale)), max(1, int(image.height * scale)))
    try:
        from PIL import Image as PILImage

        resample = PILImage.Resampling.LANCZOS
    except Exception:
        resample = 1  # PIL.Image.LANCZOS legacy constant
    logger.debug(
        "downscaled inference input",
        original=f"{image.width}x{image.height}",
        capped=f"{new_size[0]}x{new_size[1]}",
    )
    return image.resize(new_size, resample)
