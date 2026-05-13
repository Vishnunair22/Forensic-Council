#!/usr/bin/env bash
# update_handoff.sh
# Stub that delegates to the cross-platform Python version.
# Run: bash scripts/update_handoff.sh
# Or: python scripts/update_handoff.py

cd "$(dirname "$0")/.." || exit 1

if command -v python3 &>/dev/null; then
    python3 scripts/update_handoff.py
elif command -v python &>/dev/null; then
    python scripts/update_handoff.py
else
    echo "ERROR: python3 not found — cannot update PROJECT_HANDOFF.md"
    exit 1
fi