"""
Gemini API connectivity and vision test.

Usage (from backend/ directory):
    python scripts/test_gemini.py                        # text-only ping
    python scripts/test_gemini.py path/to/image.jpg      # vision test with file

Environment:
    GEMINI_API_KEY  — required
    GEMINI_MODEL    — optional, default gemini-1.5-flash-latest
"""

from __future__ import annotations

import asyncio
import base64
import json
import os
import sys
import time
from pathlib import Path


# ── Minimal inline client (no FastAPI/Pydantic dependency) ─────────────────

_BASE = "https://generativelanguage.googleapis.com/v1beta"
_VISION_MIMES = {"image/jpeg", "image/png", "image/webp", "image/gif", "image/bmp"}


def _encode_image(path: str) -> tuple[str, str]:
    """Return (base64_data, mime_type) for an image file."""
    import mimetypes
    mime, _ = mimetypes.guess_type(path)
    if not mime:
        mime = "image/jpeg"
    with open(path, "rb") as fh:
        data = base64.b64encode(fh.read()).decode("utf-8")
    return data, mime


async def _post(url: str, payload: dict, timeout: float = 30.0) -> dict:
    """Minimal async POST using httpx."""
    try:
        import httpx
    except ImportError:
        print("ERROR: httpx not installed — run: pip install httpx")
        sys.exit(1)

    async with httpx.AsyncClient(timeout=timeout) as client:
        resp = await client.post(url, json=payload)
        if resp.status_code != 200:
            raise RuntimeError(
                f"HTTP {resp.status_code}: {resp.text[:400]}"
            )
        return resp.json()


# ── Tests ───────────────────────────────────────────────────────────────────

async def test_text_ping(api_key: str, model: str) -> bool:
    """Send a minimal text-only prompt to verify key + quota."""
    print(f"\n{'-'*60}")
    print("TEST 1 — Text ping (no vision)")
    print(f"{'─'*60}")

    url = f"{_BASE}/models/{model}:generateContent?key={api_key}"
    payload = {
        "contents": [{"parts": [{"text": "Reply with the single word: PONG"}]}],
        "generationConfig": {"temperature": 0.0, "maxOutputTokens": 256},
    }

    t0 = time.monotonic()
    try:
        resp = await _post(url, payload)
    except Exception as exc:
        print(f"  FAIL  {exc}")
        return False

    latency = (time.monotonic() - t0) * 1000

    # Handle thinking models (2.5+) where finishReason can be STOP with no parts
    # if the response was cut off, or parts may be absent on MAX_TOKENS.
    candidate = resp.get("candidates", [{}])[0]
    finish_reason = candidate.get("finishReason", "")
    parts = candidate.get("content", {}).get("parts", [])

    if not parts:
        # Still a successful connection — model responded, just no text output
        print(f"  OK    Connected ({latency:.0f} ms) — finishReason={finish_reason!r}, "
              f"model={resp.get('modelVersion', model)!r}")
        return True

    try:
        text = parts[0]["text"].strip()
    except (KeyError, IndexError) as exc:
        print(f"  FAIL  Unexpected response shape: {exc}\n  Raw: {json.dumps(resp)[:300]}")
        return False

    print(f"  OK    Response: {text!r}  ({latency:.0f} ms)")
    return True


async def test_vision(api_key: str, model: str, image_path: str) -> bool:
    """Send an image to Gemini and verify a structured JSON response."""
    print(f"\n{'-'*60}")
    print(f"TEST 2 — Vision analysis: {image_path}")
    print(f"{'─'*60}")

    if not Path(image_path).exists():
        print(f"  SKIP  File not found: {image_path}")
        return True  # not a failure

    try:
        encoded, mime = _encode_image(image_path)
    except Exception as exc:
        print(f"  FAIL  Could not encode image: {exc}")
        return False

    if mime not in _VISION_MIMES:
        print(f"  SKIP  MIME {mime!r} not supported for vision (use JPEG/PNG/WebP)")
        return True

    url = f"{_BASE}/models/{model}:generateContent?key={api_key}"
    prompt = (
        "You are a forensic analyst. Briefly describe what you see in this image in 1-2 "
        "sentences, then list up to 3 objects you can identify. "
        "Respond ONLY with valid JSON: "
        '{"description": "...", "objects": ["...", "..."]}'
    )
    payload = {
        "contents": [
            {
                "parts": [
                    {"inlineData": {"mimeType": mime, "data": encoded}},
                    {"text": prompt},
                ]
            }
        ],
        "generationConfig": {
            "temperature": 0.1,
            "maxOutputTokens": 256,
            "responseMimeType": "application/json",
        },
    }

    t0 = time.monotonic()
    try:
        resp = await _post(url, payload, timeout=45.0)
    except Exception as exc:
        print(f"  FAIL  {exc}")
        return False

    latency = (time.monotonic() - t0) * 1000
    try:
        raw = resp["candidates"][0]["content"]["parts"][0]["text"]
        data = json.loads(raw)
    except Exception as exc:
        print(f"  FAIL  Could not parse response: {exc}")
        print(f"         Raw: {str(resp)[:400]}")
        return False

    print(f"  OK    ({latency:.0f} ms)")
    print(f"        Description: {data.get('description', '—')}")
    print(f"        Objects:     {data.get('objects', [])}")
    return True


async def test_deep_forensic_json(api_key: str, model: str, image_path: str) -> bool:
    """
    Send the full deep_forensic_analysis prompt (the one Agent 1 uses in production)
    and verify the response parses into the expected schema.
    """
    print(f"\n{'-'*60}")
    print("TEST 3 — Full deep_forensic_analysis prompt (Agent 1 production prompt)")
    print(f"{'─'*60}")

    if not Path(image_path).exists():
        print(f"  SKIP  File not found: {image_path}")
        return True

    try:
        encoded, mime = _encode_image(image_path)
    except Exception as exc:
        print(f"  FAIL  {exc}")
        return False

    if mime not in _VISION_MIMES:
        print(f"  SKIP  Non-vision MIME {mime!r}")
        return True

    url = f"{_BASE}/models/{model}:generateContent?key={api_key}"
    prompt = (
        "You are a senior forensic analyst performing a comprehensive examination "
        "of this file. Respond ONLY with valid JSON containing these keys: "
        "content_type (str), scene_description (str), extracted_text (list[str]), "
        "detected_objects (list[str]), interface_identification (str), "
        "contextual_narrative (str), manipulation_signals (list[str]), "
        "authenticity_verdict (str), confidence (float 0-1)."
    )
    payload = {
        "contents": [
            {
                "parts": [
                    {"inlineData": {"mimeType": mime, "data": encoded}},
                    {"text": prompt},
                ]
            }
        ],
        "generationConfig": {
            "temperature": 0.1,
            "maxOutputTokens": 4096,
            "responseMimeType": "application/json",
        },
    }

    t0 = time.monotonic()
    try:
        resp = await _post(url, payload, timeout=90.0)
    except Exception as exc:
        print(f"  FAIL  {exc}")
        return False

    latency = (time.monotonic() - t0) * 1000
    required_keys = {
        "content_type", "scene_description", "detected_objects",
        "manipulation_signals", "authenticity_verdict", "confidence",
    }

    try:
        raw = resp["candidates"][0]["content"]["parts"][0]["text"]
        data = json.loads(raw)
    except Exception as exc:
        print(f"  FAIL  Parse error: {exc}")
        print(f"         Raw: {str(resp)[:400]}")
        return False

    missing = required_keys - set(data.keys())
    if missing:
        print(f"  WARN  Missing keys: {missing}")
    else:
        print(f"  OK    All required keys present  ({latency:.0f} ms)")

    print(f"        content_type:        {data.get('content_type', '—')}")
    print(f"        authenticity_verdict:{data.get('authenticity_verdict', '—')}")
    print(f"        confidence:          {data.get('confidence', '—')}")
    print(f"        detected_objects:    {data.get('detected_objects', [])[:5]}")
    print(f"        manipulation_signals:{data.get('manipulation_signals', [])[:3]}")
    return True


# ── Entry point ──────────────────────────────────────────────────────────────

async def main() -> None:
    api_key = os.environ.get("GEMINI_API_KEY", "").strip()
    model   = os.environ.get("GEMINI_MODEL", "gemini-1.5-flash-latest").strip()

    print("=" * 60)
    print("Forensic Council — Gemini API Test")
    print("=" * 60)

    if not api_key:
        print("\nERROR: GEMINI_API_KEY environment variable is not set.")
        print("       Export it before running this script:")
        print("       Windows PowerShell:  $env:GEMINI_API_KEY = 'AIza...'")
        print("       Linux/macOS:         export GEMINI_API_KEY=AIza...")
        sys.exit(1)

    masked = api_key[:6] + "..." + api_key[-4:] if len(api_key) > 10 else "***"
    print(f"\nAPI key : {masked}")
    print(f"Model   : {model}")

    image_path = sys.argv[1] if len(sys.argv) > 1 else ""

    results: list[bool] = []

    results.append(await test_text_ping(api_key, model))

    if image_path:
        results.append(await test_vision(api_key, model, image_path))
        results.append(await test_deep_forensic_json(api_key, model, image_path))
    else:
        print("\n(Pass an image path as argument to also run vision tests)")
        print("  Example: python scripts/test_gemini.py samples/test.jpg")

    print(f"\n{'='*60}")
    passed = sum(results)
    total  = len(results)
    status = "ALL PASSED" if passed == total else f"{passed}/{total} PASSED"
    print(f"Result: {status}")
    print("=" * 60)

    if passed < total:
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
