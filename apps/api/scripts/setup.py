#!/usr/bin/env python3
"""
Forensic Council Integrated Setup Script
=======================================

Consolidates environment validation, database migrations, and developer
onboarding into a single command.

Requirements:
- .env file with valid API keys when LLM/Gemini features are enabled.
- Docker services (Postgres, Redis, Qdrant) must be running.

Usage:
    python scripts/setup.py
"""

import asyncio
import shutil
import sys
from pathlib import Path

# Add project root to sys.path for internal imports.
sys.path.insert(0, str(Path(__file__).parent.parent))


async def run_setup() -> bool:
    print("--- Forensic Council: v1.4.0 Setup ---")

    env_path = Path(".env")
    if not env_path.exists():
        print("[!] .env file missing. Copying from .env.example...")
        shutil.copy(".env.example", ".env")
        print("[TIP] Please edit .env and add your LLM_API_KEY and GEMINI_API_KEY.")
    else:
        print("[OK] .env file located.")

    required_bins = ["ffmpeg", "exiftool", "tesseract"]
    missing = [binary for binary in required_bins if not shutil.which(binary)]
    if missing:
        print(f"[!] Missing system binaries: {', '.join(missing)}")
        print("    Please install these via your package manager.")
    else:
        print("[OK] System dependencies verified.")

    print("\n[INFO] Initialising core databases...")
    try:
        from scripts.init_db import init_database

        success = await init_database()
        if not success:
            print("[ERROR] Database migration failed. Are Docker services running?")
            return False
    except Exception as exc:
        print(f"[ERROR] Connection error: {exc}")
        return False

    print("\n[INFO] Validating ML tooling integrity...")
    try:
        from core.ml_subprocess import warmup_all_tools

        results = await warmup_all_tools(timeout_per_tool=30.0)
        succeeded = sum(1 for value in results.values() if value)
        print(f"[OK] {succeeded}/{len(results)} ML models verified/cached.")
    except Exception as exc:
        print(f"[WARNING] ML warmup skipped: {exc}")

    print("\n--- Setup Complete ---")
    print("[RUN] Start the API:   python -m api.main")
    print("[RUN] Start the Web:   cd ../web && npm run dev")
    return True


if __name__ == "__main__":
    try:
        setup_success = asyncio.run(run_setup())
        sys.exit(0 if setup_success else 1)
    except KeyboardInterrupt:
        print("\n[!] Setup aborted by user.")
        sys.exit(1)
