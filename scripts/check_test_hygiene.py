#!/usr/bin/env python3
"""
check_test_hygiene.py
====================
Fails the build when the test suite contains stale patterns that indicate
broken, missing, or misconfigured tests.

Run: python scripts/check_test_hygiene.py
"""

from __future__ import annotations

import ast
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FAILURES: list[str] = []

ALLOWLIST_SKIPIF = {
    "RUN_SYSTEM_ML_TESTS",
    "RUN_LIVE_PROVIDER_TESTS",
    "RUN_LIVE_E2E",
    "RUN_VIDEO_TESTS",
    "optional_dependency",
}

ALLOWLIST_SKIP_REASON = {
    "FastAPI TestClient hangs on SSE infinite streams",
    "Windows environment",
}

OLD_QUEUE_METHODS = {"enqueue", "dequeue", "add_task", "push_task"}

STALE_PATTERNS = [
    (r"test\.only\s*\(", ".only found in test file"),
    (r"mock_queue\.enqueue\s*=", "old queue method mock (enqueue) — use submit()"),
    (r"mock_queue\.dequeue\s*=", "old queue method mock (dequeue)"),
    (r"mock_queue\.add_task\s*=", "old queue method mock (add_task)"),
    (r"mock_queue\.push_task\s*=", "old queue method mock (push_task)"),
]


def check_file(path: Path) -> None:
    content = path.read_text(encoding="utf-8", errors="replace")

    for pattern, msg in STALE_PATTERNS:
        if re.search(pattern, content):
            FAILURES.append(f"{path.relative_to(ROOT)}: {msg} — matched `{pattern.rstrip()}`")

    # Check unconditional skip with reason against allowlist
    for m in re.finditer(r"pytest\.mark\.skip\s*\(\s*reason\s*=\s*['\"]([^'\"]+)['\"]", content):
        reason = m.group(1)
        if not any(allowed in reason for allowed in ALLOWLIST_SKIPIF):
            if not any(allowed in reason for allowed in ALLOWLIST_SKIP_REASON):
                FAILURES.append(
                    f"{path.relative_to(ROOT)}: unconditional pytest.mark.skip "
                    f"(missing skipif/env guard) — {m.group(0)[:60]}"
                )

    # 3. Jest tests in e2e folder
    if "/tests/e2e/" in str(path) or "\\tests\\e2e\\" in str(path):
        if path.name.endswith((".test.ts", ".test.tsx")):
            FAILURES.append(
                f"{path.relative_to(ROOT)}: Jest test in e2e folder — "
                "move to tests/unit/ or tests/integration/"
            )

    # 4. Playwright spec not ending .spec.ts or .live.spec.ts
    if "/tests/e2e/" in str(path) or "\\tests\\e2e\\" in str(path):
        if path.suffix == ".ts" and "describe(" in content and "test(" in content:
            if not re.search(r"from ['\"]@playwright/test['\"]", content):
                pass  # not a Playwright file
            else:
                if not (path.name.endswith(".spec.ts") or path.name.endswith(".live.spec.ts")):
                    FAILURES.append(
                        f"{path.relative_to(ROOT)}: Playwright test file does not end with "
                        ".spec.ts or .live.spec.ts"
                    )

    # 5. Empty test.skip placeholder (only flag if it has an actual empty function body)
    for m in re.finditer(r"test\.skip\s*\(\s*['\"]([^'\"]+)['\"]\s*,\s*(?:async\s*)?\(\s*\)\s*(?:=>\s*)?\{\s*\}\s*,\s*[\d]+\s*\)", content):
        FAILURES.append(
            f"{path.relative_to(ROOT)}: empty test.skip placeholder with explicit empty body — {m.group(0)[:60]}"
        )


def check_pyproject_frontend_references(path: Path) -> None:
    content = path.read_text(encoding="utf-8", errors="replace")

    missing_scripts = {
        "npm run test:e2e": re.search(r'"test:e2e"\s*:', content),
        "npm run test:e2e:chromium": re.search(r'"test:e2e:chromium"\s*:', content),
        "npm run test:e2e:journey": re.search(r'"test:e2e:journey"\s*:', content),
    }

    for script, found in missing_scripts.items():
        if not found:
            FAILURES.append(
                f"apps/web/package.json: {script} script is missing — "
                "E2E gates from previous phases will fail"
            )


def check_ci_npx_undeclared(path: Path) -> None:
    content = path.read_text(encoding="utf-8", errors="replace")
    if re.search(r"^\s*npx\s+wait-on\b", content, re.MULTILINE):
        FAILURES.append(
            ".github/workflows/ci.yml: npx wait-on used without declaring wait-on "
            "as a devDependency — use node - <<'NODE' wait loop instead"
        )


def main() -> None:
    print("Checking test hygiene...")

    # Backend files
    for py_file in (ROOT / "apps/api/tests").rglob("*.py"):
        check_file(py_file)

    # Frontend files
    for ts_file in (ROOT / "apps/web/tests").rglob("*.ts"):
        check_file(ts_file)
    for tsx_file in (ROOT / "apps/web/tests").rglob("*.tsx"):
        check_file(tsx_file)

    # package.json script references
    check_pyproject_frontend_references(ROOT / "apps/web/package.json")

    # CI hygiene
    check_ci_npx_undeclared(ROOT / ".github/workflows/ci.yml")

    if FAILURES:
        print("\nTest hygiene FAILURES:")
        for f in sorted(set(FAILURES)):
            print(f"  - {f}")
        sys.exit(1)

    print("Test hygiene passed.")


if __name__ == "__main__":
    main()
