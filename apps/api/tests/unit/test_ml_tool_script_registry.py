from __future__ import annotations

import re
from pathlib import Path


def test_all_handler_ml_tool_scripts_exist() -> None:
    """Every run_ml_tool("...") reference in core handlers must have a script."""
    api_root = Path(__file__).resolve().parents[2]
    handlers_dir = api_root / "core" / "handlers"
    ml_tools_dir = api_root / "tools" / "ml_tools"

    referenced: set[str] = set()
    pattern = re.compile(r'run_ml_tool\("([^"]+)"')
    for path in handlers_dir.glob("*.py"):
        referenced.update(pattern.findall(path.read_text(encoding="utf-8")))

    missing = sorted(script for script in referenced if not (ml_tools_dir / script).exists())
    assert missing == []
