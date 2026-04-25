"""
Groq API Verification Script
=============================

Verifies Groq API connectivity and logs results for production monitoring.
Usage: python apps/api/scripts/verify_groq.py
"""

import asyncio
import os
import sys
from pathlib import Path

import httpx
from dotenv import load_dotenv

# Add backend to path so imports work
sys.path.append(str(Path(__file__).parent.parent))

from core.structured_logging import get_logger

load_dotenv()
logger = get_logger(__name__)


async def verify_groq() -> dict:
    """
    Verify Groq API connectivity and log results.

    Returns:
        dict with status and model count

    Raises:
        ValueError: If LLM_API_KEY is not configured
        httpx.HTTPError: If API request fails
    """
    key = os.getenv("LLM_API_KEY")
    if not key:
        logger.error("LLM_API_KEY not configured")
        raise ValueError("LLM_API_KEY required for Groq verification")

    # Check if it's the placeholder value
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


def main():
    """Main entry point for script execution."""
    try:
        result = asyncio.run(verify_groq())
        print(f"✅ Groq API: {result['status'].upper()}")
        print(f"   Status Code: {result['status_code']}")
        print(f"   Models Available: {result['models_available']}")
        sys.exit(0)
    except ValueError as e:
        print(f"❌ Configuration Error: {str(e)}")
        sys.exit(1)
    except httpx.HTTPError as e:
        print(f"❌ HTTP Error: {str(e)}")
        sys.exit(2)
    except Exception as e:
        print(f"❌ Unexpected Error: {str(e)}")
        sys.exit(3)


if __name__ == "__main__":
    main()
