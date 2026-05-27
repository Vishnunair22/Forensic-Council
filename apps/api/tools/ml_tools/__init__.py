"""
ML Tools package.

To promote a new tool from research to active status:
1. Implement the tool as a CLI script in this directory (apps/api/tools/ml_tools/<tool_name>.py).
2. The script must accept `--input <path>` (and optional extra args) and output JSON to stdout.
3. If it loads heavy ML weights, add it to `_WARMUP_SCRIPTS` in `apps/api/core/ml_subprocess.py`.
4. If it runs in a persistent background worker mode, ensure it handles `--worker` / stdin loop.
   Otherwise, add it to `_NO_WORKER_SCRIPTS` in `apps/api/core/ml_subprocess.py`.
5. Register it in `config/task_tool_overrides.yaml` if applicable.
6. Verify its health by running `python scripts/validate_ml_tools.py` and `python scripts/verify_models_responding.py`.
"""
