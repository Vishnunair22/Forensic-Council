#!/usr/bin/env python3
"""
Model Weight Hash Recorder & Verifier (WS-2 #8)
================================================

Pins model weights to content hashes so investigations are reproducible and
the model supply chain is tamper-evident. Must run INSIDE the container
(or any environment where the real model caches exist), because it hashes
the actual weight files on disk.

For every model in config/models.lock.json it:
  1. Locates the on-disk artifacts (HF hub cache layout, torchvision
     checkpoints, or an explicit path override).
  2. Resolves the actual git revision (HF `refs/<rev>` -> commit SHA).
  3. Computes a deterministic aggregate sha256 over all weight files:
     sha256 of newline-joined "relpath:file_sha256" lines, sorted by relpath.

Modes:
    --record           Write resolved revision + aggregate sha256 into
                       models.lock.json (a .bak backup is written first).
    --record --enforce Also set "_enforce_sha": true so startup verification
                       becomes mandatory.
    --verify           Recompute hashes and compare against the lock file.
                       Exit 1 on any mismatch, or on a missing REQUIRED model
                       when _enforce_sha is true. Intended for CI / startup.
    --check            Report what is on disk vs the lock file. No writes,
                       always exit 0.

Usage (inside the backend or worker container):
    python scripts/record_model_hashes.py --check
    python scripts/record_model_hashes.py --record
    python scripts/record_model_hashes.py --record --enforce
    python scripts/record_model_hashes.py --verify
"""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import sys
from dataclasses import dataclass, field
from pathlib import Path

from core.config import get_settings

settings = get_settings()

LOCK_PATH = Path(__file__).parent.parent / "config" / "models.lock.json"

GREEN = "\033[0;32m"
YELLOW = "\033[1;33m"
RED = "\033[0;31m"
CYAN = "\033[0;36m"
RESET = "\033[0m"

# Files that are not weights and may legitimately differ between pulls
# (READMEs, .gitattributes, lock metadata). Everything else is hashed.
_IGNORED_SUFFIXES = {".md", ".txt", ".gitattributes", ".lock", ".metadata"}
_IGNORED_NAMES = {".gitattributes", "README.md", ".no_exist"}

# Non-HF models need explicit locators. Each returns (root_dir, revision|None).
_SPECIAL_LOCATORS = {
    "resnet50_torchvision": lambda: (
        Path(settings.torch_home) / "hub" / "checkpoints",
        None,
    ),
}


@dataclass
class ModelHashResult:
    model_id: str
    found: bool
    root: Path | None = None
    revision: str | None = None
    sha256: str | None = None
    file_count: int = 0
    total_bytes: int = 0
    notes: list[str] = field(default_factory=list)


def _hf_model_dir(model_id: str) -> Path:
    return Path(settings.hf_home) / "hub" / ("models--" + model_id.replace("/", "--"))


def _resolve_hf_revision(model_dir: Path) -> str | None:
    """Resolve the commit SHA the cache is actually serving (refs/main etc.)."""
    refs_dir = model_dir / "refs"
    if not refs_dir.is_dir():
        return None
    for ref in sorted(refs_dir.iterdir()):
        if ref.is_file():
            sha = ref.read_text(encoding="utf-8").strip()
            if sha:
                return sha
    return None


def _iter_weight_files(root: Path) -> list[Path]:
    """All hashable files under root, ignoring docs/metadata."""
    files: list[Path] = []
    for p in sorted(root.rglob("*")):
        if not p.is_file() or p.is_symlink():
            # HF snapshots/ contains symlinks into blobs/; hashing blobs/
            # directly (plus regular files) avoids double-counting.
            continue
        if p.name in _IGNORED_NAMES or p.suffix.lower() in _IGNORED_SUFFIXES:
            continue
        files.append(p)
    return files


def _sha256_file(path: Path, chunk: int = 1 << 20) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        while True:
            block = f.read(chunk)
            if not block:
                break
            h.update(block)
    return h.hexdigest()


def _aggregate_hash(root: Path, files: list[Path]) -> str:
    """Deterministic aggregate: sha256 over sorted 'relpath:sha256' lines."""
    lines = []
    for p in files:
        rel = p.relative_to(root).as_posix()
        lines.append(f"{rel}:{_sha256_file(p)}")
    payload = "\n".join(sorted(lines)).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def hash_model(model_id: str) -> ModelHashResult:
    res = ModelHashResult(model_id=model_id, found=False)

    if model_id in _SPECIAL_LOCATORS:
        root, revision = _SPECIAL_LOCATORS[model_id]()
        res.revision = revision
    else:
        root = _hf_model_dir(model_id)
        res.revision = _resolve_hf_revision(root)

    if not root.is_dir():
        res.notes.append(f"not found on disk: {root}")
        return res

    # For HF layout, hash the blobs/ dir (content-addressed weight payloads).
    # Fall back to the whole dir for flat layouts (torchvision checkpoints).
    blobs = root / "blobs"
    hash_root = blobs if blobs.is_dir() else root
    files = _iter_weight_files(hash_root)
    if not files:
        res.notes.append(f"directory exists but contains no hashable files: {hash_root}")
        return res

    res.found = True
    res.root = hash_root
    res.file_count = len(files)
    res.total_bytes = sum(p.stat().st_size for p in files)
    res.sha256 = _aggregate_hash(hash_root, files)
    return res


def _load_lock() -> dict:
    return json.loads(LOCK_PATH.read_text(encoding="utf-8"))


def _model_entries(lock: dict) -> dict[str, dict]:
    return {k: v for k, v in lock.items() if not k.startswith("_")}


def _fmt_size(n: int) -> str:
    return f"{n / 1_048_576:.0f}MB"


def cmd_check(lock: dict) -> int:
    for model_id, entry in _model_entries(lock).items():
        res = hash_model(model_id)
        locked = entry.get("sha256")
        if not res.found:
            tag = f"{YELLOW}[MISS]{RESET}"
            detail = "; ".join(res.notes)
        elif locked and locked == res.sha256:
            tag = f"{GREEN}[OK  ]{RESET}"
            detail = f"matches lock ({res.file_count} files, {_fmt_size(res.total_bytes)})"
        elif locked:
            tag = f"{RED}[DIFF]{RESET}"
            detail = f"lock={locked[:12]}… disk={res.sha256[:12]}…"
        else:
            tag = f"{CYAN}[NEW ]{RESET}"
            detail = (
                f"unpinned — disk sha256={res.sha256[:12]}… "
                f"rev={res.revision or 'unknown'} "
                f"({res.file_count} files, {_fmt_size(res.total_bytes)})"
            )
        print(f"  {tag} {model_id}: {detail}")
    return 0


def cmd_record(lock: dict, enforce: bool) -> int:
    backup = LOCK_PATH.with_suffix(".json.bak")
    shutil.copy2(LOCK_PATH, backup)
    print(f"Backup written: {backup}")

    recorded = skipped = 0
    for model_id, entry in _model_entries(lock).items():
        res = hash_model(model_id)
        if not res.found:
            print(f"  {YELLOW}[SKIP]{RESET} {model_id}: {'; '.join(res.notes)}")
            skipped += 1
            continue
        entry["sha256"] = res.sha256
        if res.revision:
            entry["revision"] = res.revision
        entry["hashed_files"] = res.file_count
        entry["hashed_bytes"] = res.total_bytes
        print(
            f"  {GREEN}[PIN ]{RESET} {model_id}: sha256={res.sha256[:16]}… "
            f"rev={res.revision or 'n/a'} ({res.file_count} files, {_fmt_size(res.total_bytes)})"
        )
        recorded += 1

    if enforce:
        lock["_enforce_sha"] = True
        print(f"  {GREEN}[SET ]{RESET} _enforce_sha = true")

    lock["_comment"] = (
        "Pinned model metadata. sha256 is the aggregate hash produced by "
        "scripts/record_model_hashes.py (sorted relpath:file_sha256 lines). "
        "Re-run --record after any intentional model upgrade."
    )
    LOCK_PATH.write_text(json.dumps(lock, indent=2) + "\n", encoding="utf-8")
    print(f"\nWrote {LOCK_PATH} — {recorded} pinned, {skipped} skipped (not on disk).")
    if skipped:
        print(
            f"{YELLOW}Skipped models are NOT pinned. Run model_pre_download.py first "
            f"if they are required, then re-run --record.{RESET}"
        )
    return 0


def cmd_verify(lock: dict) -> int:
    enforce = bool(lock.get("_enforce_sha"))
    failures: list[str] = []
    for model_id, entry in _model_entries(lock).items():
        locked = entry.get("sha256")
        required = bool(entry.get("required"))
        res = hash_model(model_id)

        if not res.found:
            if required and enforce:
                failures.append(f"{model_id}: REQUIRED model missing from disk")
                print(f"  {RED}[FAIL]{RESET} {model_id}: required but not on disk")
            else:
                print(f"  {YELLOW}[MISS]{RESET} {model_id}: not on disk (optional or enforcement off)")
            continue

        if not locked:
            msg = f"{model_id}: on disk but no sha256 pinned in lock file"
            if enforce and required:
                failures.append(msg)
                print(f"  {RED}[FAIL]{RESET} {msg}")
            else:
                print(f"  {YELLOW}[WARN]{RESET} {msg}")
            continue

        if locked == res.sha256:
            print(f"  {GREEN}[OK  ]{RESET} {model_id}")
        else:
            failures.append(
                f"{model_id}: hash mismatch (lock={locked[:12]}…, disk={res.sha256[:12]}…)"
            )
            print(f"  {RED}[FAIL]{RESET} {model_id}: HASH MISMATCH — possible tamper or unpinned upgrade")

    if failures:
        print(f"\n{RED}Verification FAILED:{RESET}")
        for f in failures:
            print(f"  - {f}")
        return 1
    print(f"\n{GREEN}All pinned models verified.{RESET}")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--check", action="store_true", help="report disk vs lock, no writes")
    mode.add_argument("--record", action="store_true", help="pin disk hashes into models.lock.json")
    mode.add_argument("--verify", action="store_true", help="verify disk against lock; exit 1 on mismatch")
    parser.add_argument("--enforce", action="store_true", help="with --record: set _enforce_sha=true")
    args = parser.parse_args()

    if not LOCK_PATH.exists():
        print(f"{RED}models.lock.json not found at {LOCK_PATH}{RESET}")
        return 2

    lock = _load_lock()
    if args.check:
        return cmd_check(lock)
    if args.record:
        return cmd_record(lock, enforce=args.enforce)
    return cmd_verify(lock)


if __name__ == "__main__":
    sys.exit(main())
