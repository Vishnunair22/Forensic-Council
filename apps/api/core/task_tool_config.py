"""
Task-to-Tool Mapping Loader
============================

Loads task→tool override mappings from config/task_tool_overrides.yaml.
Provides a single source of truth for the ReAct loop engine's task-to-tool
matching, replacing the hardcoded 150+ entry dict previously in react_loop.py.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

from core.structured_logging import get_logger

logger = get_logger(__name__)

_CONFIG_PATH = (
    Path(__file__).resolve().parent.parent / "config" / "task_tool_overrides.yaml"
)

# Loaded once at module import; cached for the process lifetime.
_task_tool_overrides: dict[str, str] | None = None


def _load_overrides() -> dict[str, str]:
    """Load and merge all sections from the YAML config into a flat dict."""
    if not _CONFIG_PATH.exists():
        logger.warning(
            "task_tool_overrides.yaml not found — "
            "task-to-tool matching will fall back to substring matching",
            config_path=str(_CONFIG_PATH),
        )
        return {}

    with open(_CONFIG_PATH, encoding="utf-8") as fh:
        raw: dict[str, Any] = yaml.safe_load(fh) or {}

    merged: dict[str, str] = {}
    for _section_key, section_val in raw.items():
        if isinstance(section_val, dict):
            for task_phrase, tool_name in section_val.items():
                if isinstance(task_phrase, str) and isinstance(tool_name, str):
                    merged[task_phrase.lower()] = tool_name
    return merged


def get_task_tool_overrides() -> dict[str, str]:
    """Return the cached task→tool mapping dict."""
    global _task_tool_overrides
    if _task_tool_overrides is None:
        _task_tool_overrides = _load_overrides()
        logger.info(
            "Loaded task-to-tool override mappings from YAML config",
            count=len(_task_tool_overrides),
        )
    return _task_tool_overrides


def reload_overrides() -> dict[str, str]:
    """Force-reload from disk (useful for hot-reload or testing)."""
    global _task_tool_overrides
    _task_tool_overrides = None
    return get_task_tool_overrides()
