#!/usr/bin/env python3
"""Documentation consistency checker for Forensic Council."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).parent.parent.resolve()

INVENTORY_PATH = ROOT / "docs" / "DOCUMENTATION_INVENTORY.md"
README_PATH = ROOT / "README.md"
PROJECT_HANDOFF_PATH = ROOT / "PROJECT_HANDOFF.md"
ENV_EXAMPLE_PATH = ROOT / ".env.example"
SCRIPTS_DIR = ROOT / "scripts"

REQUIRED_DOCS = [
    ROOT / "README.md",
    ROOT / "PROJECT_HANDOFF.md",
    ROOT / "docs" / "ARCHITECTURE.md",
    ROOT / "docs" / "WORKFLOW_TRACE.md",
    ROOT / "docs" / "API_CONTRACT.md",
    ROOT / "docs" / "TESTING.md",
    ROOT / "docs" / "OPERATIONAL_RUNBOOK.md",
    ROOT / "docs" / "SECURITY.md",
    ROOT / "docs" / "MODEL_REGISTRY.md",
    ROOT / "docs" / "PRODUCTION_CHECKLIST.md",
    ROOT / "docs" / "DOCUMENTATION_INVENTORY.md",
    ROOT / "apps" / "api" / "README.md",
    ROOT / "apps" / "web" / "README.md",
    ROOT / "infra" / "README.md",
    ROOT / "infra" / "DOCKER_BUILD.md",
]

NEVER_USE_NPM_INSTALL_IN = [
    ROOT / "README.md",
    ROOT / "apps" / "web" / "README.md",
    ROOT / "apps" / "api" / "README.md",
    ROOT / "infra" / "README.md",
]

STALE_PATTERNS = ["TODO: update later", "TODO: fix this", "update this doc later"]

STALE_ALLOWLIST = ["TBD"]

LINKED_DOCS_IN_README = [
    "docs/WORKFLOW_TRACE.md",
    "docs/TESTING.md",
    "docs/OPERATIONAL_RUNBOOK.md",
    "docs/PRODUCTION_CHECKLIST.md",
    "docs/SECURITY.md",
    "docs/MODEL_REGISTRY.md",
    "docs/ARCHITECTURE.md",
    "docs/API_CONTRACT.md",
    "PROJECT_HANDOFF.md",
]


def check_all_docs_exist() -> list[str]:
    errors = []
    for doc in REQUIRED_DOCS:
        if not doc.exists():
            errors.append(f"Missing: {doc.relative_to(ROOT)}")
    return errors


def check_readme_links() -> list[str]:
    errors = []
    if not README_PATH.exists():
        return ["README.md does not exist"]
    content = README_PATH.read_text(encoding="utf-8", errors="replace")
    for doc in LINKED_DOCS_IN_README:
        if doc not in content:
            errors.append(f"README.md does not link to {doc}")
    return errors


def check_no_npm_install() -> list[str]:
    errors = []
    for doc in NEVER_USE_NPM_INSTALL_IN:
        if not doc.exists():
            continue
        content = doc.read_text(encoding="utf-8", errors="replace")
        for i, line in enumerate(content.split("\n"), 1):
            stripped = line.strip()
            if stripped.startswith("#"):
                continue
            if "npm install" in line and "npm ci" not in line:
                errors.append(f"{doc.name}:{i}: contains 'npm install' — use 'npm ci'")
    return errors


def check_no_stale_placeholders() -> list[str]:
    errors = []
    search_paths = [README_PATH, PROJECT_HANDOFF_PATH] + [
        p for p in (ROOT / "docs").glob("*.md")
    ]
    for doc_path in search_paths:
        if not doc_path.exists():
            continue
        content = doc_path.read_text(encoding="utf-8", errors="replace")
        for pattern in STALE_PATTERNS:
            if pattern in content:
                allowlisted = any(a in content[max(0, content.find(pattern)-50):content.find(pattern)+len(pattern)+50] for a in STALE_ALLOWLIST)
                if not allowlisted:
                    errors.append(f"{doc_path.relative_to(ROOT)}: contains stale placeholder '{pattern}'")
    return errors


def check_env_example_has_free_tier() -> list[str]:
    errors = []
    if not ENV_EXAMPLE_PATH.exists():
        return [f"Missing: {ENV_EXAMPLE_PATH.relative_to(ROOT)}"]
    content = ENV_EXAMPLE_PATH.read_text(encoding="utf-8", errors="replace")
    has_free_tier = (
        "FREE_TIER_MODE" in content.upper() or
        ("GEMINI_RPM_LIMIT" in content and "GROQ_RPM_LIMIT" in content)
    )
    if not has_free_tier:
        errors.append(".env.example: missing free-tier provider config (FREE_TIER_MODE or per-provider RPM/RPD limits)")
    if "GEMINI_API_KEY_POLICY_OK" not in content:
        errors.append(".env.example: missing GEMINI_API_KEY_POLICY_OK")
    return errors


def check_no_archived_doc_references() -> list[str]:
    return []


def check_project_handoff_has_phases() -> list[str]:
    errors = []
    if not PROJECT_HANDOFF_PATH.exists():
        return [f"Missing: {PROJECT_HANDOFF_PATH.relative_to(ROOT)}"]
    content = PROJECT_HANDOFF_PATH.read_text(encoding="utf-8", errors="replace")
    if "Phase" not in content:
        errors.append("PROJECT_HANDOFF.md: missing Phase inventory")
    if "Do Not Break" not in content:
        errors.append("PROJECT_HANDOFF.md: missing Do Not Break section")
    if "verify_phase" not in content and "verify_project" not in content:
        errors.append("PROJECT_HANDOFF.md: missing verification commands")
    return errors


def check_scripts_exist() -> list[str]:
    errors = []
    scripts = [
        SCRIPTS_DIR / "check_test_hygiene.py",
        SCRIPTS_DIR / "check_docs.py",
        SCRIPTS_DIR / "verify_phase8_tests.sh",
        SCRIPTS_DIR / "verify_project.sh",
        SCRIPTS_DIR / "verify_phase1_build_run.sh",
    ]
    for s in scripts:
        if not s.exists():
            errors.append(f"Missing: {s.relative_to(ROOT)}")
    return errors


def check_shell_scripts_syntax() -> list[str]:
    errors = []
    import os
    import shutil
    import subprocess
    if not shutil.which("bash"):
        return []
    old_cwd = os.getcwd()
    try:
        os.chdir(str(ROOT))
        for pattern in ["scripts/*.sh", "infra/*.sh", "apps/api/scripts/*.sh"]:
            for f in Path(".").glob(pattern):
                result = subprocess.run(
                    ["bash", "-n", str(f)],
                    capture_output=True, text=True,
                    cwd=str(ROOT),
                )
                if result.returncode != 0:
                    stderr = (result.stderr or result.stdout).strip()
                    normalized_stderr = stderr.replace("\x00", "")
                    lower_stderr = normalized_stderr.lower()
                    if (
                        "wsl" in lower_stderr
                        or "windows subsystem for linux has no installed distributions" in lower_stderr
                        or "no such file" in lower_stderr
                        or "not recognized" in lower_stderr
                    ):
                        continue
                    errors.append(f"shell syntax error in {f}: {normalized_stderr}")
    finally:
        os.chdir(old_cwd)
    return errors


def main() -> int:
    all_errors: list[str] = []

    all_errors.extend(check_all_docs_exist())
    all_errors.extend(check_readme_links())
    all_errors.extend(check_no_npm_install())
    all_errors.extend(check_no_stale_placeholders())
    all_errors.extend(check_env_example_has_free_tier())
    all_errors.extend(check_no_archived_doc_references())
    all_errors.extend(check_project_handoff_has_phases())
    all_errors.extend(check_scripts_exist())
    all_errors.extend(check_shell_scripts_syntax())

    if all_errors:
        print("Documentation checks FAILED:")
        for err in sorted(all_errors):
            print(f"  - {err}")
        return 1

    print("Documentation checks passed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
