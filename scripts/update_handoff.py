#!/usr/bin/env python3
"""
update_handoff.py
Updates PROJECT_HANDOFF.md with current local git state.
Run this after any meaningful change so the handoff stays current.

Usage: python scripts/update_handoff.py
Requires: python3, git
"""

from __future__ import annotations

import datetime
import re
import subprocess
import sys
from pathlib import Path

TARGET = Path("PROJECT_HANDOFF.md")
NOW = datetime.date.today().isoformat()


def git(args: list[str]) -> str:
    try:
        return subprocess.run(
            ["git"] + args,
            capture_output=True,
            text=True,
            check=True,
        ).stdout.strip()
    except (subprocess.CalledProcessError, FileNotFoundError):
        return "unknown"


def main() -> None:
    branch = git(["branch", "--show-current"])
    commit = git(["rev-parse", "--short", "HEAD"])
    diff_names = git(["diff", "--name-status"])

    if not TARGET.exists():
        print(f"ERROR: {TARGET} not found in {Path.cwd()}", file=sys.stderr)
        sys.exit(1)

    with open(TARGET, "r", encoding="utf-8") as f:
        content = f.read()

    content = re.sub(
        r"(^## Last Updated\s+)\n.*",
        rf"\1\n{NOW}",
        content,
        flags=re.MULTILINE,
    )

    content = re.sub(
        r"(\| Local branch \| )`[^`]+`",
        rf"\1`{branch}`",
        content,
    )
    content = re.sub(
        r"(\| Local commit \| )`[^`]+`",
        rf"\1`{commit}`",
        content,
    )

    diff_block = f"""```text
{diff_names}
```"""
    content = re.sub(
        r"(## Exact Files Changed\n\n)```text\n[^`]*```",
        rf"\1{diff_block}",
        content,
        flags=re.DOTALL,
    )

    with open(TARGET, "w", encoding="utf-8") as f:
        f.write(content)

    print(f"Updated PROJECT_HANDOFF.md")
    print(f"  Branch: {branch}")
    print(f"  Commit: {commit}")
    print(f"  Date:   {NOW}")
    print(f"  Diff: {diff_names.count(chr(10)) + 1} file(s) changed")


if __name__ == "__main__":
    main()