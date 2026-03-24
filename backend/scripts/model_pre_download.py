#!/usr/bin/env python3
"""
Model Pre-Download Script
=========================

Downloads all required ML models for the Forensic Council platform.

This script is called by the Docker entrypoint on FIRST container startup
and stores models in named Docker volumes so they persist across all future
builds and restarts. It is fully idempotent — each model is skipped if its
expected files already exist in the cache volume.

Usage:
    python scripts/model_pre_download.py           # full download (skips existing)
    python scripts/model_pre_download.py --force   # re-download even if cached
    python scripts/model_pre_download.py --check   # report status without downloading

NOT run during `docker build`. Run once at first container startup via
docker_entrypoint.sh (or SKIP_MODEL_DOWNLOAD=1 to bypass).
"""

from __future__ import annotations

import argparse
import os
import sys
import time
from pathlib import Path

# ── Cache directory mapping (must match Dockerfile ENV + docker-compose volumes)
CACHE_DIRS = {
    "YOLO":    os.getenv("YOLO_CONFIG_DIR",   "/app/cache/ultralytics"),
    "TORCH":   os.getenv("TORCH_HOME",         "/app/cache/torch"),
    "HF":      os.getenv("HF_HOME",            "/app/cache/huggingface"),
    "EASYOCR": os.getenv("EASYOCR_MODEL_DIR",  "/app/cache/easyocr"),
    # DEEPFACE removed — deepface package not installed (avoids 1.8 GB TensorFlow)
}

GREEN  = "\033[0;32m"
YELLOW = "\033[1;33m"
CYAN   = "\033[0;36m"
RESET  = "\033[0m"
BOLD   = "\033[1m"


def _file_count(directory: str) -> int:
    """Return number of files recursively under directory."""
    try:
        return sum(1 for p in Path(directory).rglob("*") if p.is_file())
    except OSError:
        return 0


def _dir_size_mb(directory: str) -> float:
    total = 0
    try:
        for p in Path(directory).rglob("*"):
            if p.is_file():
                try:
                    total += p.stat().st_size
                except OSError:
                    pass
    except OSError:
        pass
    return total / (1024 * 1024)


def setup_dirs() -> None:
    for path in CACHE_DIRS.values():
        Path(path).mkdir(parents=True, exist_ok=True)


# ── Individual model download functions ─────────────────────────────────────
# Each returns True on success / already-cached, False on failure.

def download_yolo(force: bool = False) -> bool:
    yolo_dir = CACHE_DIRS["YOLO"]
    # Check for the weight file at the exact target path
    existing = [Path(yolo_dir) / "yolov8n.pt"] if (Path(yolo_dir) / "yolov8n.pt").exists() else []
    if existing and not force:
        print(f"  {GREEN}[SKIP]{RESET}  YOLOv8n — already cached ({existing[0]})")
        return True

    print(f"  {CYAN}[DOWN]{RESET}  YOLOv8n weights → {yolo_dir}")
    try:
        os.environ["YOLO_CONFIG_DIR"] = yolo_dir
        os.environ["ULTRALYTICS_CACHE_DIR"] = yolo_dir
        from ultralytics import YOLO
        # Pass the full destination path so YOLO saves directly to the volume.
        # Without this, YOLO("yolov8n.pt") saves to the CWD (/app) which is a
        # bind-mounted host directory — not the persistent cache volume.
        model_path = os.path.join(yolo_dir, "yolov8n.pt")
        YOLO(model_path)
        print(f"  {GREEN}[OK  ]{RESET}  YOLOv8n downloaded.")
        return True
    except Exception as exc:
        print(f"  {YELLOW}[WARN]{RESET}  YOLOv8n download failed: {exc}")
        return False


def download_easyocr(force: bool = False) -> bool:
    easyocr_dir = CACHE_DIRS["EASYOCR"]
    count = _file_count(easyocr_dir)
    if count >= 2 and not force:
        print(f"  {GREEN}[SKIP]{RESET}  EasyOCR — already cached ({count} files)")
        return True

    print(f"  {CYAN}[DOWN]{RESET}  EasyOCR English models → {easyocr_dir}")
    try:
        os.environ["EASYOCR_MODEL_DIR"] = easyocr_dir
        # EasyOCR tries to write a metadata dir under $HOME/.EasyOCR regardless
        # of model_storage_directory. Override HOME to /tmp (always writable, even
        # in read_only: true containers which have a /tmp tmpfs mount).
        orig_home = os.environ.get("HOME", "")
        os.environ["HOME"] = "/tmp"
        import easyocr
        easyocr.Reader(
            ["en"],
            gpu=False,
            download_enabled=True,
            model_storage_directory=easyocr_dir,
        )
        if orig_home:
            os.environ["HOME"] = orig_home
        print(f"  {GREEN}[OK  ]{RESET}  EasyOCR downloaded.")
        return True
    except Exception as exc:
        print(f"  {YELLOW}[WARN]{RESET}  EasyOCR download failed: {exc}")
        return False


def download_open_clip(force: bool = False) -> bool:
    """OpenCLIP ViT-B-32 — used by Agent 1 and Agent 3 for zero-shot classification."""
    hf_dir = CACHE_DIRS["HF"]
    # open_clip (via timm) caches to HF_HOME/hub/models--timm--vit_base_patch32_clip_224.openai
    # The actual weights blob is a 578 MB content-addressed file in the blobs/ subdir.
    timm_model_dir = Path(hf_dir) / "hub" / "models--timm--vit_base_patch32_clip_224.openai"
    # Check for any blob > 100 MB (the actual model weights)
    clip_cached = [
        p for p in (timm_model_dir / "blobs").glob("*")
        if p.is_file() and p.stat().st_size > 100_000_000
    ] if (timm_model_dir / "blobs").exists() else []

    if clip_cached and not force:
        print(f"  {GREEN}[SKIP]{RESET}  OpenCLIP ViT-B-32 — already cached ({clip_cached[0]})")
        return True

    print(f"  {CYAN}[DOWN]{RESET}  OpenCLIP ViT-B-32 (openai) → {hf_dir}")
    try:
        import open_clip
        open_clip.create_model_and_transforms("ViT-B-32", pretrained="openai")
        print(f"  {GREEN}[OK  ]{RESET}  OpenCLIP downloaded.")
        return True
    except Exception as exc:
        print(f"  {YELLOW}[WARN]{RESET}  OpenCLIP download failed: {exc}")
        return False


# ── Main ─────────────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(
        description="Forensic Council — ML model pre-download (idempotent)"
    )
    parser.add_argument(
        "--force", action="store_true",
        help="Re-download all models even if already cached in volumes"
    )
    parser.add_argument(
        "--check", action="store_true",
        help="Check cache status only, do not download anything"
    )
    args = parser.parse_args()

    print(f"\n{BOLD}{'='*55}{RESET}")
    print(f"{BOLD}  Forensic Council — ML Model Pre-Download{RESET}")
    print(f"{BOLD}{'='*55}{RESET}")
    if args.force:
        print(f"  {YELLOW}--force: re-downloading all models{RESET}")
    if args.check:
        print(f"  {CYAN}--check: status only, no downloads{RESET}")

    print(f"\n  Python {sys.version.split()[0]}")

    setup_dirs()

    if args.check:
        print(f"\n{BOLD}Cache status:{RESET}")
        for name, path in CACHE_DIRS.items():
            count = _file_count(path)
            size = _dir_size_mb(path)
            marker = GREEN + "populated" if count > 0 else YELLOW + "empty"
            print(f"  {marker}{RESET}  {name:<10}  {size:>7.1f} MB  ({count} files)  {path}")
        print()
        return

    t0 = time.monotonic()
    print(f"\n{BOLD}Downloading models (skipping any already cached):{RESET}\n")

    results = [
        download_yolo(args.force),
        download_easyocr(args.force),
        download_open_clip(args.force),
    ]

    elapsed = time.monotonic() - t0
    passed = sum(results)
    total  = len(results)

    print(f"\n{BOLD}{'='*55}{RESET}")
    if passed == total:
        print(f"{GREEN}{BOLD}  All {total} models ready. ({elapsed:.0f}s){RESET}")
    else:
        failed = total - passed
        print(f"{YELLOW}{BOLD}  {failed} model(s) failed — will retry lazily on first use.{RESET}")
        print(f"  {passed}/{total} succeeded in {elapsed:.0f}s.")
    print(f"{BOLD}{'='*55}{RESET}\n")


if __name__ == "__main__":
    main()
