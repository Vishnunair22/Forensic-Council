#!/usr/bin/env python3
"""Check documentation consistency for Forensic Council.

Verifies:
1. Every script listed in README quick-start exists on disk.
2. .env.example and .env.host.example declare the same set of keys
   (delegates to scripts/validate_env_template_consistency.sh).
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
    "scripts/validate_env_template_consistency.sh",
    "scripts/troubleshoot.sh",
    "scripts/clean_project.sh",
    "scripts/dev-restart-worker.sh",
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
    script = ROOT / "scripts" / "validate_env_template_consistency.sh"
    if not script.exists():
        FAILURES.append("scripts/validate_env_template_consistency.sh missing — cannot check env templates")
        return
    
    # Robustly find bash/sh on Windows (WSL bash might be broken, fallback to Git Bash)
    import shutil
    import os
    
    cmd = [str(script)]
    if os.name == "nt":
        resolved_bash = None
        for shell_cmd in ["bash", "sh"]:
            p = shutil.which(shell_cmd)
            if p:
                try:
                    res = subprocess.run([p, "--version"], capture_output=True, text=True, timeout=2)
                    if res.returncode == 0:
                        resolved_bash = p
                        break
                except Exception:
                    pass
        if not resolved_bash:
            git_path = shutil.which("git")
            if git_path:
                git_dir = Path(git_path).parent.parent
                for rel in ["bin/bash.exe", "bin/sh.exe", "usr/bin/bash.exe", "usr/bin/sh.exe"]:
                    p = git_dir / rel
                    if p.exists():
                        try:
                            res = subprocess.run([str(p), "--version"], capture_output=True, text=True, timeout=2)
                            if res.returncode == 0:
                                resolved_bash = str(p)
                                break
                        except Exception:
                            pass
        if resolved_bash:
            cmd = [resolved_bash, str(script)]
        else:
            FAILURES.append("Could not find a working bash/sh executable to run validate_env_template_consistency.sh on Windows")
            return

    result = subprocess.run(cmd, capture_output=True, text=True)
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
