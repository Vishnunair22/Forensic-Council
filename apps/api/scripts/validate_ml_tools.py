#!/usr/bin/env python3
"""Validate Docker ML tool readiness before the image is accepted."""

from __future__ import annotations

import ast
import importlib.util
import sys
from pathlib import Path

from core.ml_subprocess import _WARMUP_SCRIPTS, ML_TOOLS_DIR

ROOT = Path(__file__).resolve().parents[1]

REQUIRED_IMPORTS: dict[str, str] = {
    "cv2": "opencv-contrib-python",
    "easyocr": "easyocr",
    "fastapi": "fastapi",
    "magic": "python-magic",
    "numpy": "numpy",
    "open_clip": "open-clip-torch",
    "PIL": "Pillow",
    "pydantic": "pydantic",
    "pymediainfo": "pymediainfo",
    "scipy": "scipy",
    "sklearn": "scikit-learn",
    "speechbrain": "speechbrain",
    "torch": "torch",
    "torchvision": "torchvision",
    "ultralytics": "ultralytics",
}


class RunMlToolVisitor(ast.NodeVisitor):
    def __init__(self) -> None:
        self.script_names: set[str] = set()

    def visit_Call(self, node: ast.Call) -> None:
        func = node.func
        is_run_ml_tool = (
            isinstance(func, ast.Name)
            and func.id == "run_ml_tool"
            or isinstance(func, ast.Attribute)
            and func.attr == "run_ml_tool"
        )
        if is_run_ml_tool and node.args:
            first_arg = node.args[0]
            if isinstance(first_arg, ast.Constant) and isinstance(first_arg.value, str):
                self.script_names.add(first_arg.value)
        self.generic_visit(node)


def find_referenced_ml_scripts() -> set[str]:
    visitor = RunMlToolVisitor()
    for directory in ("agents", "core", "tools"):
        for source_path in (ROOT / directory).rglob("*.py"):
            try:
                tree = ast.parse(source_path.read_text(encoding="utf-8"))
            except (SyntaxError, UnicodeDecodeError):
                continue
            visitor.visit(tree)
    return visitor.script_names


def main() -> None:
    failures: list[str] = []

    print("Validating ML tool runtime dependencies...")
    for module_name, package_name in REQUIRED_IMPORTS.items():
        if importlib.util.find_spec(module_name) is None:
            failures.append(f"Missing import {module_name!r} from package {package_name!r}")

    print("Validating warm-up script registry...")
    missing_warmups = sorted(
        script_name for script_name in _WARMUP_SCRIPTS if not (ML_TOOLS_DIR / script_name).exists()
    )
    failures.extend(f"Warm-up script not found: {script_name}" for script_name in missing_warmups)

    existing_ml_scripts = {path.name for path in ML_TOOLS_DIR.glob("*.py")}
    referenced_scripts = find_referenced_ml_scripts()
    missing_referenced = sorted(referenced_scripts - existing_ml_scripts)
    if missing_referenced:
        print("Optional ML subprocess scripts referenced but not present:")
        for script_name in missing_referenced:
            print(f"  - {script_name}")
        print("Handlers for these paths include graceful fallbacks; image build will continue.")

    if failures:
        print("ML tool validation failed:")
        for failure in failures:
            print(f"  - {failure}")
        sys.exit(1)

    print("ML tool validation passed.")


if __name__ == "__main__":
    main()
