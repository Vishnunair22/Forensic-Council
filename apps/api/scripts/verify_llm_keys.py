"""
LLM Key Verification Script
============================

Verifies LLM API connectivity for different providers.
Usage: python verify_llm_keys.py --provider {gemini,groq,all}

Options:
  --provider    Provider to verify: gemini, groq, or all (default: all)
"""

import argparse
import asyncio
import os
import sys
from pathlib import Path

import httpx
from dotenv import load_dotenv

sys.path.append(str(Path(__file__).parent.parent))

from core.structured_logging import get_logger

load_dotenv()
logger = get_logger(__name__)


async def verify_groq() -> dict:
    """Verify Groq API connectivity."""
    key = os.getenv("LLM_API_KEY")
    if not key:
        logger.error("LLM_API_KEY not configured")
        raise ValueError("LLM_API_KEY required for Groq verification")

    if "CHANGE_ME" in key or "your_" in key.lower():
        logger.error("LLM_API_KEY contains placeholder value")
        raise ValueError("LLM_API_KEY must be set to a valid Groq API key")

    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.get(
                "https://api.groq.com/openai/v1/models", headers={"Authorization": f"Bearer {key}"}
            )
            response.raise_for_status()

            data = response.json()
            model_count = len(data.get("data", []))

            logger.info(
                "Groq API connectivity verified",
                status_code=response.status_code,
                models_available=model_count,
            )

            return {
                "status": "ok",
                "status_code": response.status_code,
                "models_available": model_count,
            }

    except httpx.HTTPStatusError as e:
        logger.error(
            "Groq API returned error status",
            status_code=e.response.status_code,
            response_body=e.response.text[:500],
        )
        raise
    except httpx.ConnectError as e:
        logger.error("Groq API connection failed", error=str(e))
        raise
    except httpx.TimeoutException:
        logger.error("Groq API request timed out", timeout=10.0)
        raise
    except Exception as e:
        logger.critical("Unexpected error during Groq verification", error=str(e), exc_info=True)
        raise


def verify_gemini() -> dict:
    """Verify Gemini API connectivity."""
    key = os.getenv("GEMINI_API_KEY")
    if not key:
        return {"status": "error", "message": "GEMINI_API_KEY NOT FOUND"}

    url = f"https://generativelanguage.googleapis.com/v1beta/models?key={key}"

    with httpx.Client() as client:
        try:
            r = client.get(url)
            if r.status_code == 200:
                models = r.json().get("models", [])
                return {
                    "status": "ok",
                    "status_code": r.status_code,
                    "models_available": len(models),
                }
            else:
                return {"status": "error", "status_code": r.status_code, "message": r.text[:200]}
        except Exception as e:
            return {"status": "error", "message": str(e)}


async def main():
    parser = argparse.ArgumentParser(description="Verify LLM API keys")
    parser.add_argument(
        "--provider",
        choices=["gemini", "groq", "all"],
        default="all",
        help="Provider to verify",
    )
    args = parser.parse_args()

    results = {}
    success = True

    if args.provider in ("groq", "all"):
        try:
            result = asyncio.run(verify_groq())
            results["groq"] = result
            print(f"✅ Groq API: {result['status'].upper()}")
            print(f"   Status Code: {result['status_code']}")
            print(f"   Models Available: {result['models_available']}")
        except Exception as e:
            results["groq"] = {"status": "error", "message": str(e)}
            print(f"❌ Groq API Error: {str(e)}")
            success = False

    if args.provider in ("gemini", "all"):
        result = verify_gemini()
        results["gemini"] = result
        if result["status"] == "ok":
            print(f"✅ Gemini API: {result['status'].upper()}")
            print(f"   Status Code: {result['status_code']}")
            print(f"   Models Available: {result['models_available']}")
        else:
            print(f"❌ Gemini API: {result.get('message', 'ERROR')}")
            success = False

    sys.exit(0 if success else 1)


if __name__ == "__main__":
    asyncio.run(main())
