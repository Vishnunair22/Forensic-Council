#!/usr/bin/env python3
"""
Model Cache Check & Warm-Up
============================

Runs at container startup to:
  1. Report which ML model volumes are populated (already cached)
  2. Verify build-seeded model caches are available
  3. Pre-import lightweight modules that are always needed (fast path only)
  4. Exit 0 if cache is healthy, exit 0 with warnings if partially empty
     (partial cache is normal on first ever run)

This script intentionally does NOT download models. Docker builds run
model_pre_download.py to bake a seed cache into the image, and entrypoint
startup copies that seed into mounted volumes when they are empty.

Usage:
    python scripts/model_cache_check.py          # full check + soft warm-up
    python scripts/model_cache_check.py --quick  # filesystem check only
"""

from __future__ import annotations

import argparse
import importlib.util
import os
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
    "YOLO": settings.yolo_model_dir,
    "Numba": settings.numba_cache_dir,
    "Calibration": settings.calibration_models_path,
}

# Minimum expected file count per cache dir to be considered "populated"
MIN_FILES: dict[str, int] = {
    "HuggingFace": 6,
    "PyTorch": 1,
    "EasyOCR": 2,
    "YOLO": 1,
    "Numba": 0,  # generated at runtime, may be empty
    "Calibration": 0,  # generated after first run
}

def _open_clip_cache_dir(model_name: str) -> str:
    if model_name == "ViT-B-32":
        return "models--timm--vit_base_patch32_clip_224.openai"
    return "models--" + model_name.replace("hf-hub:", "").replace("/", "--")


REQUIRED_HF_MODEL_DIRS = [
    _open_clip_cache_dir(settings.siglip_model_name),
    "models--speechbrain--spkrec-ecapa-voxceleb",
    "models--" + settings.aasist_model_name.replace("/", "--"),
]

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


def check_specific_model_assets() -> bool:
    """Verify the exact model families the agents depend on are present."""
    print(f"{BOLD}Verifying required model assets...{RESET}")
    ok = True

    hf_root = Path(settings.hf_home)
    for model_dir in REQUIRED_HF_MODEL_DIRS:
        candidate_blobs = [
            hf_root / "hub" / model_dir / "blobs",
            hf_root / "transformers" / model_dir / "blobs",
        ]
        has_blob = any(
            blobs.exists()
            and any(p.is_file() and p.stat().st_size > 1_000_000 for p in blobs.glob("*"))
            for blobs in candidate_blobs
        )
        if has_blob:
            print(f"  {GREEN}[OK]{RESET}  HuggingFace model cache: {model_dir}")
        else:
            print(f"  {RED}[MISS]{RESET}  HuggingFace model cache missing: {model_dir}")
            ok = False

    yolo_name = os.environ.get("YOLO_MODEL_NAME", settings.yolo_model_name)
    yolo_path = Path(settings.yolo_model_dir) / yolo_name
    if yolo_path.exists() and yolo_path.stat().st_size > 1_000_000:
        print(f"  {GREEN}[OK]{RESET}  YOLO weights: {yolo_path}")
    else:
        print(f"  {RED}[MISS]{RESET}  YOLO weights missing: {yolo_path}")
        ok = False

    torch_checkpoints = Path(settings.torch_home) / "hub" / "checkpoints"
    has_resnet = torch_checkpoints.exists() and any(
        p.name.startswith("resnet50") and p.stat().st_size > 1_000_000
        for p in torch_checkpoints.glob("*.pth")
    )
    if has_resnet:
        print(f"  {GREEN}[OK]{RESET}  Torchvision ResNet-50 checkpoint")
    else:
        print(f"  {RED}[MISS]{RESET}  Torchvision ResNet-50 checkpoint missing")
        ok = False

    easyocr_files = _file_count(Path(settings.easyocr_model_dir))
    if easyocr_files >= 2:
        print(f"  {GREEN}[OK]{RESET}  EasyOCR model files ({easyocr_files})")
    else:
        print(f"  {RED}[MISS]{RESET}  EasyOCR model files missing")
        ok = False

    print()
    return ok


def soft_warmup() -> bool:
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
    ]

    failed: list[str] = []

    # python-magic has different import names per platform
    if importlib.util.find_spec("magic") is not None:
        print(f"  {GREEN}✓{RESET}  python-magic (libmagic)")
    else:
        print(f"  {RED}✗{RESET}  python-magic (libmagic)  →  module not found")
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
        return False
    else:
        print(f"  {GREEN}All core modules verified.{RESET}")
        return True


def main() -> None:
    parser = argparse.ArgumentParser(description="Forensic Council model cache check")
    parser.add_argument(
        "--quick",
        action="store_true",
        help="Filesystem check only; skip Python import verification",
    )
    parser.add_argument(
        "--strict",
        action="store_true",
        help="Exit non-zero when cache directories or imports are not ready",
    )
    args = parser.parse_args()

    print(f"\n{BOLD}{'━' * 55}{RESET}")
    print(f"{BOLD}  Forensic Council — Startup Cache Check{RESET}")
    print(f"{BOLD}{'━' * 55}{RESET}")

    populated, total = check_filesystem_cache()
    model_assets_ok = check_specific_model_assets()

    if populated == total:
        print(f"{GREEN}{BOLD}  All {total} cache directories healthy.{RESET}")
    else:
        empty = total - populated
        print(f"{YELLOW}{BOLD}  {empty} of {total} cache directories are empty.{RESET}")
        print(
            f"  {YELLOW}Model seed cache is incomplete; startup fallback may retry downloads.{RESET}"
        )
        print(
            f"  {YELLOW}Expect slower first-run analysis unless the Docker build preloaded models.{RESET}"
        )

    imports_ok = True
    if not args.quick:
        print()
        imports_ok = soft_warmup()

    if args.strict and (populated != total or not imports_ok or not model_assets_ok):
        sys.exit(1)

    print(f"\n{BOLD}{'━' * 55}{RESET}")
    print(f"{BOLD}  Starting Forensic Council API...{RESET}")
    print(f"{BOLD}{'━' * 55}{RESET}\n")

    # Always exit 0 — empty cache is normal on first run, not an error.
    sys.exit(0)


if __name__ == "__main__":
    main()
