#!/usr/bin/env python3
"""
Pre-seed default calibration models into the build-time model cache.

Called from apps/api/Dockerfile during the `app` build stage so that fresh
runtime volumes can be seeded with a usable Platt-scaling identity model.
Fails fast with a clear message if core.calibration is unavailable.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

SEED_DIR = Path("/opt/forensic-model-cache/calibration_models")
AGENT_IDS = (
    "agent1_image",
    "agent2_audio",
    "agent3_object",
    "agent4_video",
    "agent5_metadata",
)


def main() -> int:
    marker = SEED_DIR / ".trained"
    if marker.exists():
        print(f"  Calibration seed already present at {SEED_DIR}; skipping.")
        return 0

    try:
        from core.calibration import CalibrationLayer
    except Exception as exc:
        print(
            f"FATAL: cannot import core.calibration during build seed step: "
            f"{type(exc).__name__}: {exc}",
            file=sys.stderr,
        )
        return 1

    SEED_DIR.mkdir(parents=True, exist_ok=True)
    layer = CalibrationLayer(str(SEED_DIR))
    for agent in AGENT_IDS:
        try:
            layer.fit_default_model(agent)
        except Exception as exc:
            print(
                f"FATAL: fit_default_model({agent!r}) failed during build: "
                f"{type(exc).__name__}: {exc}",
                file=sys.stderr,
            )
            return 1

    marker.touch()
    print(f"  Seeded calibration defaults for {len(AGENT_IDS)} agents at {SEED_DIR}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
