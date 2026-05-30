#!/usr/bin/env bash
# Forensic Council — safe cleanup of generated artifacts
#
# Removes: Python bytecode, caches, frontend builds, coverage, logs, test results.
# Preserves: node_modules, .venv, model caches, evidence, database volumes, .env files.
#
# Usage:
#   bash scripts/clean_project.sh        # normal cleanup
#   bash scripts/clean_project.sh --deep  # also removes model caches and evidence

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
cd "$ROOT"

DEEP=false
if [[ "${1:-}" == "--deep" ]]; then
    DEEP=true
fi

PLATFORM="$(uname -s)"
IS_WINDOWS=false
case "$PLATFORM" in
  MINGW*|MSYS*|CYGWIN*) IS_WINDOWS=true ;;
esac

rmrf() {
  local path="$1"
  if [[ -e "$path" ]]; then
    rm -rf "$path" 2>/dev/null || true
  fi
}

echo "=== Forensic Council — Cleaning generated artifacts ==="

echo "Cleaning Python bytecode and caches..."
if $IS_WINDOWS; then
  find . -type d -name "__pycache__" -prune -exec rm -rf {} + 2>/dev/null || true
  find . -type f -name "*.py[co]" -delete 2>/dev/null || true
  find . -type f -name "*.pyc" -delete 2>/dev/null || true
else
  find . -type d -name "__pycache__" -prune -exec rm -rf {} + 2>/dev/null || true
  find . -type f -name "*.py[co]" -delete 2>/dev/null || true
  find . -type f -name "*.pyc" -delete 2>/dev/null || true
fi

rmrf .pytest_cache
rmrf .ruff_cache
rmrf .mypy_cache
rmrf .pyright
rmrf htmlcov
rmrf apps/api/.pytest_cache
rmrf apps/api/.pytest_tmp
rmrf apps/api/.pytest_tmp_run
rmrf apps/api/.ruff_cache
rmrf apps/api/.pyright
rmrf apps/web/.next
rmrf apps/web/coverage
rmrf apps/web/playwright-report
rmrf apps/web/test-results
rmrf apps/web/apps
rmrf apps/web/out
rmrf apps/web/.swc
rmrf apps/web/.turbo
rmrf coverage
rmrf playwright-report
rmrf test-results
rmrf logs

find . -name ".coverage" -type f -delete 2>/dev/null || true
find . -name "coverage.xml" -type f -delete 2>/dev/null || true
find . -name "coverage.json" -type f -delete 2>/dev/null || true
find . -name "*.log" -type f -delete 2>/dev/null || true
find . -name "*.tsbuildinfo" -type f -delete 2>/dev/null || true
find . -name ".eslintcache" -type f -delete 2>/dev/null || true

rm -f apps/web/lint_output*.txt 2>/dev/null || true
rm -f tsc_errors.txt baseline_results.txt ruff_errors.json 2>/dev/null || true
rm -f agents_ruff.txt 2>/dev/null || true

find . -type d -name ".nyc_output" -prune -exec rm -rf {} + 2>/dev/null || true
find . -name "pytest-cache-files-*" -type d -exec rm -rf {} + 2>/dev/null || true
find . -name "tmp_*" -type d -exec rm -rf {} + 2>/dev/null || true

find apps/api/reports -mindepth 1 ! -name '.gitkeep' -delete 2>/dev/null || true

if [[ "$DEEP" == "true" ]]; then
    echo "Deep clean: removing model caches and uploaded evidence..."
    rmrf apps/api/cache
    rmrf apps/api/.cache
    rm -rf apps/api/storage/evidence/* 2>/dev/null || true
    echo "  (Model caches and evidence removed.)"
    echo "  To restore model caches: run docker compose build or model_pre_download.py"
else
    echo "Skipping model caches and evidence (not --deep)."
fi

echo "Done. Clean complete."
