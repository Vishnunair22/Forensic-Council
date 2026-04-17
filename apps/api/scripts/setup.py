#!/usr/bin/env python3
"""
Forensic Council Integrated Setup Script
=======================================

Consolidates environment validation, database migrations, and
developer onboarding into a single command. 

Requirements:
- .env file with valid API keys (Groq, Gemini)
- Docker services (Postgres, Redis, Qdrant) must be RUNNING.

Usage:
    python scripts/setup.py
"""

import asyncio
import os
import sys
import shutil
import subprocess
from pathlib import Path

# Add project root to sys.path for internal imports
sys.path.insert(0, str(Path(__file__).parent.parent))

async def run_setup():
    print("─── Forensic Council: v1.4.0 Setup ───")
    
    # 1. Environment Check
    env_path = Path(".env")
    if not env_path.exists():
        print("[!] .env file missing. Copying from .env.example...")
        shutil.copy(".env.example", ".env")
        print("[TIP] Please edit .env and add your GROQ_API_KEY and GEMINI_API_KEY.")
    else:
        print("[OK] .env file located.")

    # 2. Dependency Check (Binaries)
    REQUIRED_BINS = ["ffmpeg", "exiftool", "tesseract"]
    missing = [b for b in REQUIRED_BINS if not shutil.which(b)]
    if missing:
        print(f"[!] Missing system binaries: {', '.join(missing)}")
        print("    Please install these via your package manager (brew/apt/choco).")
    else:
        print("[OK] System dependencies verified.")

    # 3. Database Initialisation (Migrations)
    print("\n[INFO] Initialising core databases...")
    try:
        from scripts.init_db import init_database
        success = await init_database()
        if not success:
            print("[ERROR] Database migration failed. Are Docker services running?")
            return False
    except Exception as e:
        print(f"[ERROR] Connection error: {e}")
        return False

    # 4. Model Context Warmup (Optional)
    print("\n[INFO] Validating ML Tooling integrity...")
    try:
        from core.ml_subprocess import warmup_all_tools
        results = await warmup_all_tools(timeout_per_tool=30.0)
        succeeded = sum(1 for v in results.values() if v)
        print(f"[OK] {succeeded}/{len(results)} ML models verified/cached.")
    except Exception as e:
        print(f"[WARNING] ML Warmup skipped: {e}")

    print("\n─── Setup Complete ───")
    print("[RUN] Start the API:   python -m api.main")
    print("[RUN] Start the Web:   cd ../web && npm run dev")
    return True

if __name__ == "__main__":
    try:
        success = asyncio.run(run_setup())
        sys.exit(0 if success else 1)
    except KeyboardInterrupt:
        print("\n[!] Setup aborted by user.")
        sys.exit(1)
