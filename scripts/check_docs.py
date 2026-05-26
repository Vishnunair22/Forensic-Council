#!/usr/bin/env python3
"""Check documentation consistency for Forensic Council.

Verifies:
1. Every script listed in README quick-start exists on disk.
2. .env.example and .env.local.example declare the same set of keys
   (delegates to infra/validate_env_template_consistency.sh).
"""

import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

EXPECTED_SCRIPTS = [
    "scripts/dev.sh",
    "scripts/prod.sh",
    "infra/generate_production_keys.sh",
    "infra/validate_production_readiness.sh",
    "infra/validate_repo_health.sh",
    "infra/validate_env_template_consistency.sh",
    "scripts/troubleshoot.sh",
    "scripts/clean_project.sh",
]

FAILURES: list[str] = []


def check_scripts_exist() -> None:
    for rel in EXPECTED_SCRIPTS:
        path = ROOT / rel
        if not path.exists():
            FAILURES.append(f"Missing script: {rel}")


def check_readme_script_refs() -> None:
    readme = ROOT / "README.md"
    if not readme.exists():
        FAILURES.append("README.md not found")
        return
    text = readme.read_text(encoding="utf-8")
    # Any script reference in code blocks that doesn't exist on disk.
    for match in re.finditer(r"`(scripts/\S+\.sh|infra/\S+\.sh)`", text):
        rel = match.group(1)
        if not (ROOT / rel).exists():
            FAILURES.append(f"README references missing script: {rel}")


def check_env_template_consistency() -> None:
    script = ROOT / "infra" / "validate_env_template_consistency.sh"
    if not script.exists():
        FAILURES.append("infra/validate_env_template_consistency.sh missing — cannot check env templates")
        return
    result = subprocess.run([str(script)], capture_output=True, text=True)
    if result.returncode != 0:
        FAILURES.append(f"Env template mismatch:\n{result.stdout}{result.stderr}")


def main() -> int:
    check_scripts_exist()
    check_readme_script_refs()
    check_env_template_consistency()

    if FAILURES:
        for msg in FAILURES:
            print(f"FAIL: {msg}", file=sys.stderr)
        return 1

    print("OK: documentation consistency checks passed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
