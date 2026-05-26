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

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

DEEP=false
if [[ "${1:-}" == "--deep" ]]; then
    DEEP=true
fi

echo "=== Forensic Council — Cleaning generated artifacts ==="

echo "Cleaning Python bytecode and caches..."
find . -type d -name "__pycache__" -prune -exec rm -rf {} + 2>/dev/null || true
find . -type f -name "*.py[co]" -delete 2>/dev/null || true
find . -type f -name "*.pyc" -delete 2>/dev/null || true
rm -rf .pytest_cache .ruff_cache .mypy_cache .pyright htmlcov 2>/dev/null || true
rm -rf apps/api/.pytest_cache apps/api/.pytest_tmp apps/api/.pytest_tmp_run 2>/dev/null || true
rm -rf apps/api/.ruff_cache apps/api/.pyright 2>/dev/null || true
find . -name ".coverage" -type f -delete 2>/dev/null || true
find . -name "coverage.xml" -type f -delete 2>/dev/null || true
find . -name "coverage.json" -type f -delete 2>/dev/null || true

echo "Cleaning frontend caches and build outputs..."
rm -rf apps/web/.next apps/web/coverage apps/web/playwright-report 2>/dev/null || true
rm -rf apps/web/test-results apps/web/apps apps/web/out 2>/dev/null || true
rm -rf apps/web/.swc apps/web/.turbo 2>/dev/null || true
rm -f apps/web/lint_output*.txt 2>/dev/null || true
find . -type d -name ".nyc_output" -prune -exec rm -rf {} + 2>/dev/null || true
find . -name ".eslintcache" -type f -delete 2>/dev/null || true
find . -name "*.tsbuildinfo" -type f -delete 2>/dev/null || true

echo "Cleaning root-level reports and test artifacts..."
rm -rf coverage playwright-report test-results 2>/dev/null || true
rm -f tsc_errors.txt baseline_results.txt ruff_errors.json 2>/dev/null || true
rm -f agents_ruff.txt 2>/dev/null || true
find . -name "pytest-cache-files-*" -type d -exec rm -rf {} + 2>/dev/null || true
find . -name "tmp_*" -type d -exec rm -rf {} + 2>/dev/null || true

echo "Cleaning logs..."
rm -rf logs 2>/dev/null || true
find . -name "*.log" -type f -delete 2>/dev/null || true

echo "Cleaning API reports..."
find apps/api/reports -mindepth 1 ! -name '.gitkeep' -delete 2>/dev/null || true

if [[ "$DEEP" == "true" ]]; then
    echo "Deep clean: removing model caches and uploaded evidence..."
    rm -rf apps/api/cache/ apps/api/.cache/ 2>/dev/null || true
    rm -rf apps/api/storage/evidence/* 2>/dev/null || true
    echo "  (Model caches and evidence removed.)"
    echo "  To restore model caches: run docker compose build or model_pre_download.py"
else
    echo "Skipping model caches and evidence (not --deep)."
fi

echo "Done. Clean complete."