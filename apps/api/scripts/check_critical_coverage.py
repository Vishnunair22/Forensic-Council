#!/usr/bin/env python3
"""
check_critical_coverage.py
==========================
Enforces minimum coverage thresholds for lifecycle-critical backend modules.
Run after: uv run pytest tests/ --cov=. --cov-report=json:coverage.json
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

CRITICAL = {
    "api/routes/investigation.py": 70,
    "api/routes/sessions.py": 70,
    "api/routes/_authz.py": 80,
    "api/routes/_session_state.py": 70,
    "orchestration/investigation_queue.py": 75,
    "core/session_persistence.py": 75,
    "core/llm_client.py": 65,
    "core/gemini_client.py": 65,
}


def main(cov_path: str | None = None) -> None:
    if not cov_path:
        cov_path = "apps/api/coverage.json"
    path = Path(cov_path)
    if not path.exists():
        print(f"No coverage file found at {cov_path}. Run pytest with --cov-report=json:firstblood.json first.")
        sys.exit(1)

    with open(path) as f:
        data = json.load(f)

    totals = data.get("totals", {})
    all_files = data.get("files", {})

    failures = []
    for module, threshold in CRITICAL.items():
        file_key = None
        for fk, fv in all_files.items():
            if module in fk or fk.endswith(module):
                file_key = fk
                break
        if file_key is None:
            failures.append(f"{module}: NOT FOUND in coverage report")
            continue

        coverage = all_files[file_key].get("summary", {})
        pct = coverage.get("percent_covered", 0)
        if pct < threshold:
            failures.append(
                f"{module}: {pct:.1f}% < {threshold}% required "
                f"(lines: {coverage.get('covered_lines',0)}/{coverage.get('num_lines',0)})"
            )

    if failures:
        print("Coverage FAILURES on critical modules:")
        for f in failures:
            print(f"  - {f}")
        sys.exit(1)

    print("Critical backend coverage gates passed.")
    print(f"  Global coverage: {totals.get('percent_covered', 0):.1f}% "
          f"({totals.get('covered_lines',0)}/{totals.get('num_lines',0)} lines)")


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else None)
