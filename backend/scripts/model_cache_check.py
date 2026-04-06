#!/usr/bin/env python3
"""
Model Cache Check & Warm-Up
============================

Runs at container startup to:
  1. Report which ML model volumes are populated (already cached)
  2. Skip any heavy model downloads — those happen lazily on first use
  3. Pre-import lightweight modules that are always needed (fast path only)
  4. Exit 0 if cache is healthy, exit 0 with warnings if partially empty
     (partial cache is normal on first ever run)

This script intentionally does NOT download models. Model files are fetched
lazily by each agent on first use and cached into the named Docker volumes.
This script only verifies the cache state so operators know what to expect.

Usage:
    python scripts/model_cache_check.py          # full check + soft warm-up
    python scripts/model_cache_check.py --quick  # filesystem check only
"""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

from core.config import get_settings

# ─── Cache directory mapping ──────────────────────────────────────────────────
# These are centrally managed via core.config.
settings = get_settings()
CACHE_DIRS: dict[str, str] = {
    "HuggingFace": settings.hf_home,
    "PyTorch": settings.torch_home,
    "EasyOCR": settings.easyocr_model_dir,
    "YOLO": settings.yolo_config_dir,
    "Numba": settings.numba_cache_dir,
    "Calibration": settings.calibration_models_path,
}

# Minimum expected file count per cache dir to be considered "populated"
MIN_FILES: dict[str, int] = {
    "HuggingFace": 3,
    "PyTorch": 0,  # PyTorch hub models are downloaded lazily per-analysis
    "EasyOCR": 2,
    "YOLO": 1,
    "Numba": 0,  # generated at runtime, may be empty
    "Calibration": 0,  # generated after first run
}

GREEN = "\033[0;32m"
YELLOW = "\033[1;33m"
RED = "\033[0;31m"
CYAN = "\033[0;36m"
BOLD = "\033[1m"
RESET = "\033[0m"


def _dir_size_mb(path: Path) -> float:
    """Return total size of all files under path in MB."""
    total = 0
    try:
        for p in path.rglob("*"):
            if p.is_file():
                try:
                    total += p.stat().st_size
                except OSError:
                    pass
    except OSError:
        pass
    return total / (1024 * 1024)


def _file_count(path: Path) -> int:
    """Count files under path."""
    try:
        return sum(1 for p in path.rglob("*") if p.is_file())
    except OSError:
        return 0


def check_filesystem_cache() -> tuple[int, int]:
    """
    Walk each cache directory and report status.

    Returns:
        (populated_count, total_count)
    """
    print(f"\n{BOLD}{CYAN}━━━  ML Model Cache Status  ━━━{RESET}\n")

    populated = 0
    total = len(CACHE_DIRS)

    for name, dir_str in CACHE_DIRS.items():
        path = Path(dir_str)
        min_f = MIN_FILES.get(name, 1)

        if not path.exists():
            print(
                f"  {YELLOW}⚠  {name:<16}{RESET}  {dir_str}  →  directory missing (volume not mounted?)"
            )
            continue

        count = _file_count(path)
        size_mb = _dir_size_mb(path)

        if count >= min_f and (min_f == 0 or size_mb > 0.5):
            status = f"{GREEN}✓ CACHED{RESET}"
            populated += 1
        elif min_f == 0:
            status = f"{CYAN}○ EMPTY{RESET} (populated at runtime)"
            populated += 1  # empty-ok dirs count as healthy
        else:
            status = f"{YELLOW}⚠ EMPTY{RESET} (will download on first use)"

        print(f"  {status}  {name:<16}  {size_mb:>7.1f} MB  ({count} files)  {dir_str}")

    print()
    return populated, total


def soft_warmup() -> None:
    """
    Import always-needed lightweight modules to pre-populate Python's module
    cache and verify the venv is intact. Heavy ML models are NOT loaded here.
    """
    print(f"{BOLD}Verifying Python environment...{RESET}")
    t0 = time.monotonic()

    modules_to_check = [
        ("fastapi", "FastAPI"),
        ("pydantic", "Pydantic"),
        ("redis", "Redis async client"),
        ("asyncpg", "AsyncPG (Postgres)"),
        ("qdrant_client", "Qdrant client"),
        ("cryptography", "Cryptography"),
        ("httpx", "HTTPX"),
        ("PIL", "Pillow"),
        ("cv2", "OpenCV"),
        ("numpy", "NumPy"),
        ("scipy", "SciPy"),
        ("imagehash", "ImageHash"),
        ("piexif", "piexif"),
        ("ultralytics", "YOLO (ultralytics)"),
        ("open_clip", "OpenCLIP"),
        ("speechbrain", "SpeechBrain"),
        ("pyannote.audio", "pyannote.audio"),
    ]

    failed: list[str] = []

    # python-magic has different import names per platform
    try:
        import magic as _magic_test

        print(f"  {GREEN}✓{RESET}  python-magic (libmagic)")
    except ImportError as e:
        print(f"  {RED}✗{RESET}  python-magic (libmagic)  →  {e}")
        failed.append("python-magic")

    for module, label in modules_to_check:
        try:
            __import__(module)
            print(f"  {GREEN}✓{RESET}  {label}")
        except ImportError as e:
            print(f"  {RED}✗{RESET}  {label}  →  {e}")
            failed.append(label)

    elapsed = time.monotonic() - t0
    print(f"\n  Import check completed in {elapsed:.2f}s")

    if failed:
        print(f"\n  {RED}Failed imports:{RESET} {', '.join(failed)}")
        print(
            f"  {YELLOW}Hint: Run `uv sync --frozen --extra ml` to reinstall dependencies.{RESET}"
        )
    else:
        print(f"  {GREEN}All core modules verified.{RESET}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Forensic Council model cache check")
    parser.add_argument(
        "--quick",
        action="store_true",
        help="Filesystem check only; skip Python import verification",
    )
    args = parser.parse_args()

    print(f"\n{BOLD}{'━' * 55}{RESET}")
    print(f"{BOLD}  Forensic Council — Startup Cache Check{RESET}")
    print(f"{BOLD}{'━' * 55}{RESET}")

    populated, total = check_filesystem_cache()

    if populated == total:
        print(f"{GREEN}{BOLD}  All {total} cache directories healthy.{RESET}")
    else:
        empty = total - populated
        print(f"{YELLOW}{BOLD}  {empty} of {total} cache directories are empty.{RESET}")
        print(f"  {YELLOW}Models will be downloaded automatically on first use.{RESET}")
        print(
            f"  {YELLOW}Expect slower first-run analysis; subsequent runs use the cache.{RESET}"
        )

    if not args.quick:
        print()
        soft_warmup()

    print(f"\n{BOLD}{'━' * 55}{RESET}")
    print(f"{BOLD}  Starting Forensic Council API...{RESET}")
    print(f"{BOLD}{'━' * 55}{RESET}\n")

    # Always exit 0 — empty cache is normal on first run, not an error.
    sys.exit(0)


if __name__ == "__main__":
    main()
