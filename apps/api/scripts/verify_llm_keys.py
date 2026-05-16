"""
LLM Key Verification Script
=============================

Verifies LLM API connectivity using /models endpoints only (no quota burned).
Outputs structured JSON so it can be consumed by automation/orchestration scripts.

Usage:
    python verify_llm_keys.py [--provider {gemini,groq,openai,anthropic,all}] [--json]
    python verify_llm_keys.py --provider all --json > key_status.json

Output JSON shape:
    {
      "groq": {"status": "ok"|"error", "status_code": int, "models_count": int, "error": str},
      "gemini": {"status": "ok"|"error", ...},
      ...
    }

Exit code: 0 if all checked providers are OK, 1 if any failed.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import httpx

sys.path.insert(0, str(Path(__file__).parent.parent))

try:
    from dotenv import load_dotenv
    load_dotenv()
except Exception:  # noqa: S110 — dotenv is optional; env vars may already be set
    pass

import os


def _is_placeholder(key: str | None, provider: str) -> bool:
    """Return True if the key is a placeholder or not set."""
    if not key:
        return True
    lower = key.lower()
    placeholders = ("your_", "_here", "placeholder", "changeme", "replace_me", "sk-xxx")
    if any(p in lower for p in placeholders):
        return True
    if provider == "groq" and len(key) < 20:
        return True
    return False


async def _check_groq(api_key: str, timeout: float = 8.0) -> dict:
    """Check Groq /models endpoint. No quota burned."""
    url = "https://api.groq.com/openai/v1/models"
    headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}

    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            resp = await client.get(url, headers=headers)
            if resp.status_code == 200:
                data = resp.json()
                model_count = len(data.get("data", []))
                return {
                    "status": "ok",
                    "status_code": 200,
                    "models_count": model_count,
                    "error": None,
                }
            elif resp.status_code == 401:
                return {
                    "status": "error",
                    "status_code": 401,
                    "models_count": 0,
                    "error": "Invalid API key (401 Unauthorized)",
                }
            else:
                return {
                    "status": "error",
                    "status_code": resp.status_code,
                    "models_count": 0,
                    "error": resp.text[:200],
                }
    except httpx.TimeoutException:
        return {
            "status": "error",
            "status_code": 0,
            "models_count": 0,
            "error": f"Request timed out after {timeout:.0f}s",
        }
    except httpx.ConnectError as e:
        return {
            "status": "error",
            "status_code": 0,
            "models_count": 0,
            "error": f"Connection failed: {e}",
        }
    except Exception as e:
        return {
            "status": "error",
            "status_code": 0,
            "models_count": 0,
            "error": str(e),
        }


async def _check_gemini(api_key: str, timeout: float = 8.0) -> dict:
    """Check Gemini models.list endpoint. No quota burned."""
    # M-C-4: key as header, not query string.
    url = "https://generativelanguage.googleapis.com/v1beta/models?pageSize=5"
    headers = {"x-goog-api-key": api_key}

    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            resp = await client.get(url, headers=headers)
            if resp.status_code == 200:
                data = resp.json()
                # Just count for verification — don't load full model list
                models = data.get("models", [])
                return {
                    "status": "ok",
                    "status_code": 200,
                    "models_count": len(models),
                    "error": None,
                    "models_preview": [m.get("name", "").replace("models/", "") for m in models[:5]],
                }
            elif resp.status_code == 401:
                return {
                    "status": "error",
                    "status_code": 401,
                    "models_count": 0,
                    "error": "Invalid API key (401 Unauthorized)",
                }
            else:
                return {
                    "status": "error",
                    "status_code": resp.status_code,
                    "models_count": 0,
                    "error": resp.text[:200],
                }
    except httpx.TimeoutException:
        return {
            "status": "error",
            "status_code": 0,
            "models_count": 0,
            "error": f"Request timed out after {timeout:.0f}s",
        }
    except httpx.ConnectError as e:
        return {
            "status": "error",
            "status_code": 0,
            "models_count": 0,
            "error": f"Connection failed: {e}",
        }
    except Exception as e:
        return {
            "status": "error",
            "status_code": 0,
            "models_count": 0,
            "error": str(e),
        }


async def _check_openai(api_key: str, timeout: float = 8.0) -> dict:
    """Check OpenAI /models endpoint. No quota burned."""
    url = "https://api.openai.com/v1/models"
    headers = {"Authorization": f"Bearer {api_key}"}

    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            resp = await client.get(url, headers=headers)
            if resp.status_code == 200:
                data = resp.json()
                model_count = len(data.get("data", []))
                return {
                    "status": "ok",
                    "status_code": 200,
                    "models_count": model_count,
                    "error": None,
                }
            elif resp.status_code == 401:
                return {
                    "status": "error",
                    "status_code": 401,
                    "models_count": 0,
                    "error": "Invalid API key (401 Unauthorized)",
                }
            else:
                return {
                    "status": "error",
                    "status_code": resp.status_code,
                    "models_count": 0,
                    "error": resp.text[:200],
                }
    except httpx.TimeoutException:
        return {
            "status": "error",
            "status_code": 0,
            "models_count": 0,
            "error": f"Request timed out after {timeout:.0f}s",
        }
    except httpx.ConnectError as e:
        return {
            "status": "error",
            "status_code": 0,
            "models_count": 0,
            "error": f"Connection failed: {e}",
        }
    except Exception as e:
        return {
            "status": "error",
            "status_code": 0,
            "models_count": 0,
            "error": str(e),
        }


async def _check_anthropic(api_key: str, timeout: float = 8.0) -> dict:
    """Check Anthropic /models endpoint. No quota burned."""
    url = "https://api.anthropic.com/v1/models"
    headers = {"x-api-key": api_key, "anthropic-version": "2023-06-01"}

    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            resp = await client.get(url, headers=headers)
            if resp.status_code == 200:
                data = resp.json()
                model_count = len(data.get("data", []))
                return {
                    "status": "ok",
                    "status_code": 200,
                    "models_count": model_count,
                    "error": None,
                }
            elif resp.status_code == 401:
                return {
                    "status": "error",
                    "status_code": 401,
                    "models_count": 0,
                    "error": "Invalid API key (401 Unauthorized)",
                }
            else:
                return {
                    "status": "error",
                    "status_code": resp.status_code,
                    "models_count": 0,
                    "error": resp.text[:200],
                }
    except httpx.TimeoutException:
        return {
            "status": "error",
            "status_code": 0,
            "models_count": 0,
            "error": f"Request timed out after {timeout:.0f}s",
        }
    except httpx.ConnectError as e:
        return {
            "status": "error",
            "status_code": 0,
            "models_count": 0,
            "error": f"Connection failed: {e}",
        }
    except Exception as e:
        return {
            "status": "error",
            "status_code": 0,
            "models_count": 0,
            "error": str(e),
        }


async def main():
    parser = argparse.ArgumentParser(
        description="Verify LLM API keys using /models endpoints (no quota burned).",
        epilog="Exit code 0 if all checked providers are OK, 1 if any failed.",
    )
    parser.add_argument(
        "--provider",
        choices=["gemini", "groq", "openai", "anthropic", "all"],
        default="all",
        help="Provider to verify (default: all)",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Output machine-readable JSON instead of human-readable text",
    )
    parser.add_argument(
        "--timeout",
        type=float,
        default=8.0,
        help="Request timeout in seconds (default: 8.0)",
    )
    args = parser.parse_args()

    results: dict[str, dict] = {}
    all_ok = True

    providers = {
        "groq": ("LLM_API_KEY", _check_groq),
        "gemini": ("GEMINI_API_KEY", _check_gemini),
        "openai": ("OPENAI_API_KEY", _check_openai),
        "anthropic": ("ANTHROPIC_API_KEY", _check_anthropic),
    }

    check_providers = providers.keys() if args.provider == "all" else [args.provider]

    for provider in check_providers:
        env_var, checker = providers[provider]
        raw_key = os.getenv(env_var)

        if _is_placeholder(raw_key, provider):
            results[provider] = {
                "status": "placeholder",
                "status_code": None,
                "models_count": 0,
                "error": f"{env_var} is not set or is a placeholder value",
            }
            all_ok = False
            continue

        result = await checker(raw_key, timeout=args.timeout)
        results[provider] = result
        if result["status"] != "ok":
            all_ok = False

    if args.json:
        print(json.dumps(results, indent=2))
    else:
        for provider, result in results.items():
            status = result["status"]
            if status == "ok":
                print(f"[OK]   {provider.upper()}: {result['models_count']} models available")
            elif status == "placeholder":
                print(f"[--]   {provider.upper()}: Not configured ({result['error']})")
            else:
                print(f"[FAIL] {provider.upper()}: {result['error']} (HTTP {result['status_code']})")
        print()
        if all_ok:
            print("All providers OK.")
        else:
            failed = [p for p, r in results.items() if r["status"] not in ("ok", "placeholder")]
            print(f"Failed: {', '.join(failed)}")

    sys.exit(0 if all_ok else 1)


if __name__ == "__main__":
    import asyncio
    asyncio.run(main())
