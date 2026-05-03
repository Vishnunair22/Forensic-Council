#!/usr/bin/env python3
"""
Model Pre-Download Script
=========================

Downloads all required ML models for the Forensic Council platform.

This script is called during Docker build to bake a seed cache into the image,
and can also be called by the Docker entrypoint on first startup as a fallback.
It is fully idempotent - each model is skipped if its expected files already
exist in the configured cache directory.

Usage:
    python scripts/model_pre_download.py           # full download (skips existing)
    python scripts/model_pre_download.py --force   # re-download even if cached
    python scripts/model_pre_download.py --check   # report status without downloading

Docker builds run it in strict mode so missing tools fail early instead of
surprising the first live analysis.
"""

from __future__ import annotations

import argparse
import contextlib
import json
import os
import sys
import tempfile
import time
from collections.abc import Callable
from pathlib import Path

from core.config import get_settings

# Cache directory mapping (centrally managed via core.config)
settings = get_settings()
CACHE_DIRS = {
    "YOLO": settings.yolo_model_dir,
    "TORCH": settings.torch_home,
    "HF": settings.hf_home,
    "EASYOCR": settings.easyocr_model_dir,
}

HF_MODEL_DIRS = {
    "open_clip": "models--" + settings.siglip_model_name.replace("/", "--"),
    "speechbrain_ecapa": "models--speechbrain--spkrec-ecapa-voxceleb",
    "speechbrain_aasist": "models--" + settings.aasist_model_name.replace("/", "--"),
}

GREEN = "\033[0;32m"
YELLOW = "\033[1;33m"
CYAN = "\033[0;36m"
RESET = "\033[0m"
BOLD = "\033[1m"


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


# Individual model download functions
# Each returns True on success / already-cached, False on failure.


def download_yolo(force: bool = False) -> bool:
    yolo_dir = CACHE_DIRS["YOLO"]
    model_name = settings.yolo_model_name
    if "yolo" in model_name.lower() and not settings.enable_agpl_models:
        print(
            f"  {YELLOW}[INFO]{RESET}  {model_name} configured without ENABLE_AGPL_MODELS=true; "
            "caching DETR fallback instead."
        )
        model_name = "detr-resnet-50"

    # DETR / transformers fallback - used when YOLO_MODEL_NAME is a HF repo ID.
    if model_name.startswith("detr") or "/" in model_name:
        try:
            from transformers import AutoImageProcessor, AutoModelForObjectDetection

            repo = "facebook/detr-resnet-50" if model_name == "detr-resnet-50" else model_name
            AutoImageProcessor.from_pretrained(repo)
            AutoModelForObjectDetection.from_pretrained(repo)
            print(f"  {GREEN}[OK  ]{RESET}  DETR object detector ({repo}) cached.")
            return True
        except Exception as exc:
            print(f"  {YELLOW}[WARN]{RESET}  DETR download failed: {exc}")
            return False

    # Original YOLO path (Ultralytics) - skipped if already cached.
    model_path = Path(yolo_dir) / model_name
    existing = [model_path] if model_path.exists() else []
    if existing and not force:
        print(f"  {GREEN}[SKIP]{RESET}  YOLO11n - already cached ({existing[0]})")
        return True

    print(f"  {CYAN}[DOWN]{RESET}  YOLO11n weights -> {yolo_dir}")
    try:
        from ultralytics import YOLO

        # YOLO11n is the state-of-the-art fast model for Ultralytics
        # Without this, YOLO("yolo11n.pt") saves to the CWD (/app) which is a
        # bind mount and pollutes the host project.
        os.environ["YOLO_CONFIG_DIR"] = yolo_dir
        cwd = os.getcwd()
        os.chdir(yolo_dir)
        try:
            YOLO(model_name)
        finally:
            os.chdir(cwd)
        print(f"  {GREEN}[OK  ]{RESET}  YOLO11n downloaded.")
        return True
    except Exception as exc:
        print(f"  {YELLOW}[WARN]{RESET}  YOLO11n download failed: {exc}")
        return False


def download_easyocr(force: bool = False) -> bool:
    easyocr_dir = CACHE_DIRS["EASYOCR"]
    log_path = Path(easyocr_dir) / "easyocr_download.log"
    count = _file_count(easyocr_dir)
    if count >= 2 and not force:
        print(f"  {GREEN}[SKIP]{RESET}  EasyOCR - already cached ({count} files)")
        return True

    print(f"  {CYAN}[DOWN]{RESET}  EasyOCR English models -> {easyocr_dir}")
    last_error: Exception | None = None
    for attempt in range(1, 4):
        orig_home = os.environ.get("HOME", "")
        try:
            os.environ["EASYOCR_MODEL_DIR"] = easyocr_dir
            with (
                tempfile.TemporaryDirectory(prefix="easyocr_") as temp_home,
                log_path.open("w", encoding="utf-8") as log_file,
            ):
                os.environ["HOME"] = temp_home
                import easyocr

                with contextlib.redirect_stdout(log_file), contextlib.redirect_stderr(log_file):
                    easyocr.Reader(
                        ["en"],
                        gpu=False,
                        download_enabled=True,
                        model_storage_directory=easyocr_dir,
                    )
            print(f"  {GREEN}[OK  ]{RESET}  EasyOCR downloaded.")
            return True
        except Exception as exc:
            last_error = exc
            if attempt < 3:
                print(
                    f"  {YELLOW}[WARN]{RESET}  EasyOCR download attempt {attempt}/3 failed: {exc}; retrying..."
                )
                time.sleep(3 * attempt)
        finally:
            if orig_home:
                os.environ["HOME"] = orig_home

    print(f"  {YELLOW}[WARN]{RESET}  EasyOCR download failed: {last_error} (details: {log_path})")
    return False


def download_open_clip(force: bool = False) -> bool:
    """OpenCLIP / SigLIP - used by Agent 1 and Agent 3 for zero-shot classification and neural fingerprints."""
    hf_dir = CACHE_DIRS["HF"]
    model_name = settings.siglip_model_name

    # Normalise slug: strip hf-hub: prefix before building the cache path.
    clean_name = model_name.replace("hf-hub:", "")
    if model_name == "ViT-B-32":
        model_slug = "models--timm--vit_base_patch32_clip_224.openai"
    else:
        model_slug = f"models--{clean_name.replace('/', '--')}"
    model_dir = Path(hf_dir) / "hub" / model_slug

    # Robust check: look for any blob > 50 MB (the actual model weights)
    clip_cached = (
        [
            p
            for p in (model_dir / "blobs").glob("*")
            if p.is_file() and p.stat().st_size > 50_000_000
        ]
        if (model_dir / "blobs").exists()
        else []
    )

    if clip_cached and not force:
        print(
            f"  {GREEN}[SKIP]{RESET}  OpenCLIP/SigLIP {model_name} - already cached ({clip_cached[0]})"
        )
        return True

    print(f"  {CYAN}[DOWN]{RESET}  OpenCLIP/SigLIP {model_name} -> {hf_dir}")
    try:
        if model_name.startswith("hf-hub:") or "/" in model_name:
            # HF Hub model ID (e.g. google/siglip-base-patch16-224): use transformers
            # so we are not limited to models registered in open_clip's model registry.
            from transformers import AutoModel, AutoProcessor

            AutoProcessor.from_pretrained(clean_name)
            AutoModel.from_pretrained(clean_name)
        else:
            import open_clip

            pretrained = "openai" if "siglip" not in model_name.lower() else "webli"
            open_clip.create_model_and_transforms(model_name, pretrained=pretrained)

        # Post-download size guard: confirm at least one large blob landed.
        post_blobs = (
            [
                p
                for p in (model_dir / "blobs").glob("*")
                if p.is_file() and p.stat().st_size > 50_000_000
            ]
            if (model_dir / "blobs").exists()
            else []
        )
        if not post_blobs:
            raise RuntimeError(
                f"CLIP/SigLIP download succeeded but no large blob found in {model_dir}/blobs - possible partial download"
            )
        print(f"  {GREEN}[OK  ]{RESET}  OpenCLIP/SigLIP downloaded.")
        return True
    except Exception as exc:
        print(f"  {YELLOW}[WARN]{RESET}  OpenCLIP/SigLIP download failed: {exc}")
        return False


def download_resnet50(force: bool = False) -> bool:
    """ResNet-50 - used by deepfake_frequency tool for frequency-domain analysis."""
    import hashlib

    torch_dir = CACHE_DIRS["TORCH"]
    # torchvision caches to TORCH_HOME/hub/checkpoints/
    checkpoint_dir = Path(torch_dir) / "hub" / "checkpoints"
    resnet_file = checkpoint_dir / "resnet50-11ad3fa6.pth"
    if resnet_file.exists() and not force:
        print(f"  {GREEN}[SKIP]{RESET}  ResNet-50 - already cached ({resnet_file})")
        return True

    print(f"  {CYAN}[DOWN]{RESET}  ResNet-50 weights -> {torch_dir}")
    try:
        import torchvision
        import json

        torchvision.models.resnet50(weights=torchvision.models.ResNet50_Weights.DEFAULT)
        if not (resnet_file.exists() and resnet_file.stat().st_size > 50_000_000):
            raise RuntimeError(
                f"ResNet-50 weight file missing or truncated after download: {resnet_file}"
            )
        # Verify checksum against models.lock.json if expected hash is defined
        actual_hash = hashlib.sha256(resnet_file.read_bytes()).hexdigest()
        lock_path = Path(__file__).parent.parent / "config" / "models.lock.json"
        expected_hash = None
        if lock_path.exists():
            try:
                lock_data = json.loads(lock_path.read_text())
                expected_hash = lock_data.get("resnet50_torchvision", {}).get("sha256")
            except Exception:
                pass
        if expected_hash:
            if actual_hash != expected_hash:
                raise RuntimeError(
                    f"ResNet-50 checksum mismatch! Expected {expected_hash}, got {actual_hash}"
                )
            print(f"  {GREEN}[OK  ]{RESET}  ResNet-50 downloaded and verified.")
        else:
            print(f"  {GREEN}[OK  ]{RESET}  ResNet-50 downloaded (sha256:{actual_hash[:16]}... - no lock verification)")
        return True
    except Exception as exc:
        print(f"  {YELLOW}[WARN]{RESET}  ResNet-50 download failed: {exc}")
        return False


def download_speechbrain(force: bool = False) -> bool:
    """SpeechBrain ECAPA-TDNN - used for audio anti-spoofing."""
    hf_dir = CACHE_DIRS["HF"]
    sb_dir = Path(hf_dir) / "hub" / "models--speechbrain--spkrec-ecapa-voxceleb"
    cached = (
        [p for p in (sb_dir / "blobs").glob("*") if p.is_file() and p.stat().st_size > 10_000_000]
        if (sb_dir / "blobs").exists()
        else []
    )
    if cached and not force:
        print(f"  {GREEN}[SKIP]{RESET}  SpeechBrain ECAPA - already cached ({cached[0]})")
        return True

    print(f"  {CYAN}[DOWN]{RESET}  SpeechBrain ECAPA-TDNN -> {hf_dir}")
    try:
        from speechbrain.inference.speaker import EncoderClassifier

        EncoderClassifier.from_hparams(
            source="speechbrain/spkrec-ecapa-voxceleb", run_opts={"device": "cpu"}
        )
        print(f"  {GREEN}[OK  ]{RESET}  SpeechBrain downloaded.")
        return True
    except Exception as exc:
        print(f"  {YELLOW}[WARN]{RESET}  SpeechBrain download failed: {exc}")
        return False


# Main


def download_audio_deepfake(force: bool = False) -> bool:
    """Configured audio deepfake anti-spoofing model - Agent 2 primary."""
    hf_dir = CACHE_DIRS["HF"]
    model_name = settings.aasist_model_name
    model_dirs = [
        Path(hf_dir) / "hub" / HF_MODEL_DIRS["speechbrain_aasist"],
        Path(hf_dir) / "transformers" / HF_MODEL_DIRS["speechbrain_aasist"],
    ]
    cached = [
        p
        for model_dir in model_dirs
        for p in (model_dir / "blobs").glob("*")
        if p.is_file() and p.stat().st_size > 1_000_000
    ]
    if cached and not force:
        print(f"  {GREEN}[SKIP]{RESET}  Audio deepfake detector - already cached ({cached[0]})")
        return True

    print(f"  {CYAN}[DOWN]{RESET}  Audio deepfake detector ({model_name}) -> {hf_dir}")
    try:
        from transformers import AutoFeatureExtractor, AutoModelForAudioClassification

        AutoFeatureExtractor.from_pretrained(model_name)
        AutoModelForAudioClassification.from_pretrained(model_name)
        print(f"  {GREEN}[OK  ]{RESET}  Audio deepfake detector downloaded.")
        return True
    except Exception as exc:
        print(f"  {YELLOW}[WARN]{RESET}  Audio deepfake detector download failed: {exc}")
        return False


def _validate_lock_file() -> None:
    """Validate models.lock.json syntax and required metadata."""
    lock_path = Path(__file__).parent.parent / "config" / "models.lock.json"
    if not lock_path.exists():
        raise RuntimeError(f"models.lock.json not found at {lock_path}")

    lock_data = json.loads(lock_path.read_text())
    missing_metadata: list[str] = []
    enforced_without_checksum: list[str] = []
    for model_id, config in lock_data.items():
        if model_id.startswith("_"):
            continue
        if not isinstance(config, dict):
            missing_metadata.append(model_id)
            continue
        if config.get("required") and not config.get("license"):
            missing_metadata.append(model_id)
        if config.get("enforce_sha") and not config.get("sha256"):
            enforced_without_checksum.append(model_id)

    if missing_metadata:
        raise RuntimeError(
            f"models.lock.json is missing required model metadata: {missing_metadata}"
        )
    if enforced_without_checksum:
        raise RuntimeError(
            "models.lock.json has enforce_sha=true without sha256 for: "
            f"{enforced_without_checksum}"
        )


def main() -> None:
    _validate_lock_file()

    parser = argparse.ArgumentParser(
        description="Forensic Council - ML model pre-download (idempotent)"
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Re-download all models even if already cached in volumes",
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help="Check cache status only, do not download anything",
    )
    parser.add_argument(
        "--strict",
        action="store_true",
        help="Exit non-zero if any model download fails",
    )
    args = parser.parse_args()

    print(f"\n{BOLD}{'=' * 55}{RESET}")
    print(f"{BOLD}  Forensic Council - ML Model Pre-Download{RESET}")
    print(f"{BOLD}{'=' * 55}{RESET}")
    if args.force:
        print(f"  {YELLOW}--force: re-downloading all models{RESET}")
    if args.check:
        print(f"  {CYAN}--check: status only, no downloads{RESET}")
    if args.strict:
        print(f"  {CYAN}--strict: failing if any model is unavailable{RESET}")

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

    download_plan: list[tuple[str, Callable[[bool], bool]]] = [
        ("Object detector", download_yolo),
        ("EasyOCR", download_easyocr),
        ("OpenCLIP ViT-B-32", download_open_clip),
        ("ResNet-50", download_resnet50),
        ("SpeechBrain ECAPA", download_speechbrain),
        ("Audio deepfake detector", download_audio_deepfake),
    ]
    results = [(name, downloader(args.force)) for name, downloader in download_plan]

    elapsed = time.monotonic() - t0
    passed = sum(1 for _, ok in results if ok)
    total = len(results)

    print(f"\n{BOLD}{'=' * 55}{RESET}")
    if passed == total:
        print(f"{GREEN}{BOLD}  All {total} models ready. ({elapsed:.0f}s){RESET}")
    else:
        failed = total - passed
        print(f"{YELLOW}{BOLD}  {failed} model(s) failed - will retry lazily on first use.{RESET}")
        print(f"  {passed}/{total} succeeded in {elapsed:.0f}s.")
        failed_names = ", ".join(name for name, ok in results if not ok)
        print(f"  Failed: {failed_names}")
    print(f"{BOLD}{'=' * 55}{RESET}\n")

    if args.strict and passed != total:
        sys.exit(1)


if __name__ == "__main__":
    main()
