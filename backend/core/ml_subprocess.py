"""
ML subprocess runner — calls CLI tool scripts without polluting the app process.
"""
import asyncio
import json
import sys
from pathlib import Path

ML_TOOLS_DIR = Path(__file__).parent.parent / "tools" / "ml_tools"


async def run_ml_tool(
    script_name: str,
    input_path: str,
    extra_args: list[str] | None = None,
    timeout: float = 30.0,
) -> dict:
    """
    Run an ML tool script as a subprocess and return its JSON output.
    
    Always returns a dict. On timeout or crash, returns:
        {"error": "...", "available": False}
    """
    script_path = ML_TOOLS_DIR / script_name
    if not script_path.exists():
        return {"error": f"Script not found: {script_name}", "available": False}

    cmd = [sys.executable, str(script_path), "--input", input_path]
    if extra_args:
        cmd.extend(extra_args)

    try:
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=timeout)

        if proc.returncode != 0:
            err = stderr.decode("utf-8", errors="replace")[:300]
            return {"error": err, "available": False, "returncode": proc.returncode}

        raw = stdout.decode("utf-8", errors="replace").strip()
        return json.loads(raw)

    except asyncio.TimeoutError:
        try:
            proc.kill()
        except OSError:
            pass
        return {"error": f"Tool timed out after {timeout}s", "available": False}
    except json.JSONDecodeError as e:
        return {"error": f"Invalid JSON output: {e}", "available": False}
    except Exception as e:
        return {"error": str(e), "available": False}
