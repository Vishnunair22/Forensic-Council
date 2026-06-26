import asyncio
import sys
from pathlib import Path

# Add apps/api to path
sys.path.append(str(Path(__file__).resolve().parents[1]))

from core.ml_subprocess import _WARMUP_SCRIPTS, warmup_all_tools


async def main():
    print("=" * 60)
    print("VERIFYING ML MODELS RESPONDING (WARM-UP TEST)")
    print("=" * 60)

    results = await warmup_all_tools(timeout_per_tool=120.0)

    print("\nResults:")
    print("-" * 60)
    succeeded = 0
    failed = []

    for name in sorted(_WARMUP_SCRIPTS):
        status = results.get(name, False)
        icon = "OK" if status else "FAIL"
        print(f"  {icon:<4} {name:<40} {'READY' if status else 'FAILED'}")
        if status:
            succeeded += 1
        else:
            failed.append(name)

    print("\nVerifying optional Florence-2 Vision Fallback...")
    optional_degraded = []
    try:
        from tools.florence_analyzer import get_florence_analyzer

        analyzer = get_florence_analyzer()
        load_success = analyzer._load()
        if load_success:
            print(f"  OK   Florence-2 model is READY (device: {analyzer._device})")
            succeeded += 1
        else:
            print("  WARN Florence-2 unavailable; local visual ensemble will run without captioning")
            optional_degraded.append("florence_analyzer (optional in-process)")
    except Exception as exc:
        print(f"  WARN Florence-2 verification exception: {exc}")
        optional_degraded.append(f"florence_analyzer (optional exception: {exc})")

    print("-" * 60)
    total_expected = len(_WARMUP_SCRIPTS) + 1
    print(f"Summary: {succeeded}/{total_expected} tools ready.")
    if optional_degraded:
        print(f"Optional degraded: {len(optional_degraded)}")

    if failed:
        print("\nFailed required tools:")
        for item in failed:
            print(f"  - {item}")
        sys.exit(1)

    if optional_degraded:
        print("\nRequired models are responding; optional fallbacks degraded:")
        for item in optional_degraded:
            print(f"  - {item}")
    else:
        print("\nAll models are responding correctly!")
    sys.exit(0)


if __name__ == "__main__":
    asyncio.run(main())
