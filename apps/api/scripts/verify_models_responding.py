
import asyncio
import sys
from pathlib import Path

# Add apps/api to path
sys.path.append(str(Path(__file__).resolve().parents[1]))

from core.ml_subprocess import _WARMUP_SCRIPTS, warmup_all_tools
from core.structured_logging import get_logger

logger = get_logger(__name__)

async def main():
    print("=" * 60)
    print("VERIFYING ML MODELS RESPONDING (WARM-UP TEST)")
    print("=" * 60)

    # Increase timeout per tool for initial load
    results = await warmup_all_tools(timeout_per_tool=120.0)

    print("\nResults:")
    print("-" * 60)
    succeeded = 0
    failed = []

    for name in sorted(_WARMUP_SCRIPTS):
        status = results.get(name, False)
        icon = "✓" if status else "✗"
        print(f"  {icon} {name:<40} {'READY' if status else 'FAILED'}")
        if status:
            succeeded += 1
        else:
            failed.append(name)

    print("-" * 60)
    print(f"Summary: {succeeded}/{len(_WARMUP_SCRIPTS)} tools ready.")

    if failed:
        print("\nFailed tools:")
        for f in failed:
            print(f"  - {f}")
        sys.exit(1)
    else:
        print("\nAll models are responding correctly!")
        sys.exit(0)

if __name__ == "__main__":
    asyncio.run(main())
