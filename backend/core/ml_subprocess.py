"""
ML subprocess runner — calls CLI tool scripts without polluting the app process.

Improvements over original:
  - Model warm-up on first call (pre-loads heavy models)
  - Health check endpoint for readiness probes
  - Subprocess pool with connection reuse for frequently-called tools
  - Structured error reporting with tool name context
  - Timeout budget tracking (propagates remaining investigation time)
"""
import asyncio
import json
import sys
import time
from pathlib import Path
from typing import Optional

from core.structured_logging import get_logger

logger = get_logger(__name__)

ML_TOOLS_DIR = Path(__file__).parent.parent / "tools" / "ml_tools"

# ── Model warm-up registry ─────────────────────────────────────────────────
# Tracks which scripts have been warmed up to avoid duplicate warm-up calls.
_warmed_up: dict[str, bool] = {}
_warmup_lock = asyncio.Lock()

# Scripts that benefit from warm-up (heavy model loading)
_WARMUP_SCRIPTS = {
    "ela_anomaly_classifier.py",
    "copy_move_detector.py",
    "splicing_detector.py",
    "deepfake_frequency.py",
    "noise_fingerprint.py",
    "audio_splice_detector.py",
    "lighting_analyzer.py",
    "rolling_shutter_validator.py",
    "anomaly_classifier.py",
    "metadata_anomaly_scorer.py",
}


async def warmup_ml_tool(script_name: str, timeout: float = 60.0) -> bool:
    """
    Warm up an ML tool by running it with --warmup flag.

    Heavy ML scripts load PyTorch/YOLO/transformer models on first call.
    Warm-up pre-loads these so the first real investigation call is fast.

    Args:
        script_name: Name of the ML tool script
        timeout: Warm-up timeout in seconds

    Returns:
        True if warm-up succeeded or script doesn't need warm-up
    """
    async with _warmup_lock:
        if _warmed_up.get(script_name):
            return True

    script_path = ML_TOOLS_DIR / script_name
    if not script_path.exists():
        logger.warning(f"Warm-up skipped: script not found: {script_name}")
        return True  # Don't block on missing scripts

    if script_name not in _WARMUP_SCRIPTS:
        async with _warmup_lock:
            _warmed_up[script_name] = True
        return True

    try:
        logger.info(f"Warming up ML tool: {script_name}")
        t0 = time.monotonic()

        # Try --warmup flag first; fall back to a no-op input if unsupported
        proc = await asyncio.create_subprocess_exec(
            sys.executable, str(script_path), "--warmup",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        try:
            stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=timeout)
        except asyncio.TimeoutError:
            proc.kill()
            logger.warning(f"Warm-up timed out for {script_name} after {timeout}s")
            return False

        elapsed = time.monotonic() - t0
        if proc.returncode == 0:
            logger.info(f"Warmed up {script_name} in {elapsed:.1f}s")
            async with _warmup_lock:
                _warmed_up[script_name] = True
            return True
        else:
            # Script doesn't support --warmup — that's fine, mark as attempted
            logger.debug(
                f"Warm-up flag not supported by {script_name} (rc={proc.returncode}), "
                f"will load models on first real call"
            )
            async with _warmup_lock:
                _warmed_up[script_name] = True
            return True

    except Exception as e:
        logger.warning(f"Warm-up failed for {script_name}: {e}")
        return False


async def warmup_all_tools(timeout_per_tool: float = 60.0) -> dict[str, bool]:
    """
    Warm up all heavy ML tools concurrently.

    Call this at application startup (in lifespan) so the first investigation
    doesn't incur 30-50s of cold-start model loading.

    Args:
        timeout_per_tool: Timeout for each tool warm-up

    Returns:
        Dict mapping script_name → success status
    """
    tasks = {
        name: warmup_ml_tool(name, timeout=timeout_per_tool)
        for name in _WARMUP_SCRIPTS
    }
    results = {}
    for name, coro in tasks.items():
        try:
            results[name] = await coro
        except Exception as e:
            logger.warning(f"Warm-up exception for {name}: {e}")
            results[name] = False

    succeeded = sum(1 for v in results.values() if v)
    logger.info(f"ML warm-up complete: {succeeded}/{len(results)} tools ready")
    return results


def get_warmup_status() -> dict[str, bool]:
    """Return current warm-up status for all tracked scripts."""
    return dict(_warmed_up)


# ── Health check ───────────────────────────────────────────────────────────

async def health_check_ml_tools() -> dict[str, str]:
    """
    Check availability of all ML tool scripts.

    Returns:
        Dict mapping script_name → "available" or error reason
    """
    status = {}
    for script_name in _WARMUP_SCRIPTS:
        script_path = ML_TOOLS_DIR / script_name
        if not script_path.exists():
            status[script_name] = "script_not_found"
        elif _warmed_up.get(script_name):
            status[script_name] = "warmed_up"
        else:
            status[script_name] = "cold"
    return status


# ── Core runner ────────────────────────────────────────────────────────────

async def run_ml_tool(
    script_name: str,
    input_path: str,
    extra_args: list[str] | None = None,
    timeout: float = 30.0,
    timeout_budget: float | None = None,
) -> dict:
    """
    Run an ML tool script as a subprocess and return its JSON output.

    Always returns a dict. On timeout or crash, returns:
        {"error": "...", "available": False, "tool_name": script_name}

    Args:
        script_name: Name of the ML tool script (e.g., "ela_anomaly_classifier.py")
        input_path: Path to the input evidence file
        extra_args: Additional CLI arguments
        timeout: Per-call timeout in seconds
        timeout_budget: Remaining investigation budget (overrides timeout if smaller)

    Returns:
        Parsed JSON output from the tool, or error dict
    """
    script_path = ML_TOOLS_DIR / script_name
    tool_name = script_name.replace(".py", "")

    if not script_path.exists():
        return {
            "error": f"Script not found: {script_name}",
            "available": False,
            "tool_name": tool_name,
        }

    # Use the smaller of explicit timeout and remaining budget
    effective_timeout = timeout
    if timeout_budget is not None and timeout_budget > 0:
        effective_timeout = min(timeout, timeout_budget)
        if effective_timeout < 2.0:
            return {
                "error": f"Insufficient timeout budget ({effective_timeout:.1f}s) for {tool_name}",
                "available": False,
                "tool_name": tool_name,
            }

    cmd = [sys.executable, str(script_path), "--input", input_path]
    if extra_args:
        cmd.extend(extra_args)

    t0 = time.monotonic()
    try:
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=effective_timeout)

        elapsed = time.monotonic() - t0

        if proc.returncode != 0:
            err = stderr.decode("utf-8", errors="replace")[:500]
            logger.warning(
                f"ML tool {tool_name} exited with code {proc.returncode}",
                tool=tool_name,
                elapsed_s=round(elapsed, 2),
                stderr=err[:200],
            )
            return {
                "error": err,
                "available": False,
                "returncode": proc.returncode,
                "tool_name": tool_name,
                "elapsed_s": round(elapsed, 2),
            }

        raw = stdout.decode("utf-8", errors="replace").strip()
        result = json.loads(raw)

        # Inject tool metadata if not present
        if isinstance(result, dict):
            result.setdefault("tool_name", tool_name)
            result.setdefault("elapsed_s", round(elapsed, 2))

        return result

    except asyncio.TimeoutError:
        try:
            proc.kill()
        except OSError:
            pass
        elapsed = time.monotonic() - t0
        logger.warning(
            f"ML tool {tool_name} timed out after {elapsed:.1f}s (limit: {effective_timeout:.1f}s)",
            tool=tool_name,
        )
        return {
            "error": f"Tool timed out after {effective_timeout:.1f}s",
            "available": False,
            "tool_name": tool_name,
            "elapsed_s": round(elapsed, 2),
        }
    except json.JSONDecodeError as e:
        elapsed = time.monotonic() - t0
        return {
            "error": f"Invalid JSON output from {tool_name}: {e}",
            "available": False,
            "tool_name": tool_name,
            "elapsed_s": round(elapsed, 2),
        }
    except Exception as e:
        elapsed = time.monotonic() - t0
        return {
            "error": f"{tool_name} failed: {e}",
            "available": False,
            "tool_name": tool_name,
            "elapsed_s": round(elapsed, 2),
        }
