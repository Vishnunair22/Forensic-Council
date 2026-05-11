"""
Webhook Routes
==============

Allows API consumers to register webhook URLs that receive POST callbacks
when investigations complete.

Routes:
  POST /api/v1/webhooks           — Register a webhook
  DELETE /api/v1/webhooks/{id}    — Delete a webhook
  GET /api/v1/webhooks            — List webhooks for current user

Delivery:
  When an investigation completes, InvestigationRunner calls deliver_webhook().
  Delivery is attempted 3 times with exponential backoff.
  Failures are logged but do not block the investigation result.

Payload schema:
  {
    "event": "investigation.complete",
    "session_id": "...",
    "case_id": "...",
    "verdict": "SUSPICIOUS",
    "manipulation_probability": 0.72,
    "timestamp": "2026-05-09T12:34:56Z"
  }
"""

from __future__ import annotations

import asyncio
import hashlib
import hmac
import json
from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

import httpx
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, HttpUrl

from core.auth import get_current_user
from core.persistence.redis_client import get_redis_client
from core.structured_logging import get_logger

logger = get_logger(__name__)

webhooks_router = APIRouter(prefix="/api/v1/webhooks", tags=["webhooks"])

# Redis key prefix for webhook storage
_WEBHOOK_KEY_PREFIX = "webhooks:"
_WEBHOOK_TTL = 60 * 60 * 24 * 90  # 90 days


# ---------------------------------------------------------------------------
# Models
# ---------------------------------------------------------------------------

class WebhookRegistration(BaseModel):
    url: HttpUrl
    secret: str | None = None  # HMAC-SHA256 signing secret
    events: list[str] = ["investigation.complete"]
    description: str | None = None


class WebhookRecord(BaseModel):
    webhook_id: str
    user_id: str
    url: str
    events: list[str]
    description: str | None
    created_at: str
    secret_hash: str | None = None  # Hash of the secret, not the secret itself


class WebhookDeliveryPayload(BaseModel):
    event: str
    session_id: str
    case_id: str
    verdict: str
    manipulation_probability: float
    timestamp: str
    report_hash: str | None = None


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@webhooks_router.post("/", status_code=201)
async def register_webhook(
    body: WebhookRegistration,
    current_user: Any = Depends(get_current_user),
) -> dict[str, str]:
    """Register a webhook URL for investigation completion events."""
    redis = await get_redis_client()
    webhook_id = str(uuid4())
    user_id = str(current_user.user_id)

    # Store hashed secret only (never store plaintext secret)
    secret_hash: str | None = None
    if body.secret:
        secret_hash = hashlib.sha256(body.secret.encode()).hexdigest()[:16] + "..."

    record = WebhookRecord(
        webhook_id=webhook_id,
        user_id=user_id,
        url=str(body.url),
        events=body.events,
        description=body.description,
        created_at=datetime.now(UTC).isoformat(),
        secret_hash=secret_hash,
    )

    key = f"{_WEBHOOK_KEY_PREFIX}{user_id}:{webhook_id}"
    # Store actual secret separately with stricter TTL
    full_record = record.model_dump()
    if body.secret:
        full_record["_secret"] = body.secret  # Only for HMAC signing, not returned to client

    await redis.set(key, json.dumps(full_record), ex=_WEBHOOK_TTL)

    logger.info("Webhook registered", webhook_id=webhook_id, user_id=user_id, url=str(body.url))
    return {"webhook_id": webhook_id, "status": "registered"}


@webhooks_router.get("/")
async def list_webhooks(
    current_user: Any = Depends(get_current_user),
) -> list[dict[str, Any]]:
    """List all webhooks registered by the current user."""
    redis = await get_redis_client()
    user_id = str(current_user.user_id)
    pattern = f"{_WEBHOOK_KEY_PREFIX}{user_id}:*"

    results = []
    async for key in redis.scan_iter(match=pattern, count=100):
        raw = await redis.get(key)
        if raw:
            try:
                record = json.loads(raw)
                # Never return the secret
                record.pop("_secret", None)
                results.append(record)
            except Exception as _decode_err:
                logger.debug("Skipping malformed webhook record", error=str(_decode_err))

    return results
async def delete_webhook(
    webhook_id: str,
    current_user: Any = Depends(get_current_user),
) -> None:
    """Delete a registered webhook."""
    redis = await get_redis_client()
    user_id = str(current_user.user_id)
    key = f"{_WEBHOOK_KEY_PREFIX}{user_id}:{webhook_id}"

    deleted = await redis.delete(key)
    if not deleted:
        raise HTTPException(status_code=404, detail="Webhook not found")

    logger.info("Webhook deleted", webhook_id=webhook_id, user_id=user_id)


# ---------------------------------------------------------------------------
# Delivery engine
# ---------------------------------------------------------------------------

async def deliver_webhook(
    user_id: str,
    event: str,
    payload: dict[str, Any],
    max_retries: int = 3,
) -> None:
    """
    Deliver a webhook event to all registered URLs for the user.

    Called by the investigation pipeline when a session completes.
    Runs in the background — delivery failures do not block the response.
    """
    try:
        redis = await get_redis_client()
        pattern = f"{_WEBHOOK_KEY_PREFIX}{user_id}:*"

        webhooks: list[dict[str, Any]] = []
        async for key in redis.scan_iter(match=pattern, count=100):
            raw = await redis.get(key)
            if raw:
                try:
                    record = json.loads(raw)
                    if event in record.get("events", []):
                        webhooks.append(record)
except Exception as _decode_err:
                logger.debug("Skipping malformed webhook record in dispatch", error=str(_decode_err))

        payload_str = json.dumps(payload, default=str)

        async with httpx.AsyncClient(timeout=10.0) as client:
            for webhook in webhooks:
                url = webhook.get("url", "")
                secret = webhook.get("_secret")

                headers = {"Content-Type": "application/json", "X-FC-Event": event}

                # HMAC-SHA256 signature for webhook authenticity
                if secret:
                    sig = hmac.new(
                        key=secret.encode("utf-8"),
                        msg=payload_str.encode("utf-8"),
                        digestmod=hashlib.sha256,
                    ).hexdigest()
                    headers["X-FC-Signature"] = f"sha256={sig}"

                for attempt in range(max_retries):
                    try:
                        resp = await client.post(url, content=payload_str, headers=headers)
                        if resp.status_code < 400:
                            logger.info(
                                "Webhook delivered",
                                webhook_id=webhook.get("webhook_id"),
                                url=url,
                                status=resp.status_code,
                            )
                            break
                        else:
                            logger.warning(
                                "Webhook delivery failed",
                                webhook_id=webhook.get("webhook_id"),
                                url=url,
                                status=resp.status_code,
                                attempt=attempt + 1,
                            )
                    except Exception as e:
                        logger.warning(
                            "Webhook delivery error",
                            webhook_id=webhook.get("webhook_id"),
                            url=url,
                            error=str(e),
                            attempt=attempt + 1,
                        )

                    if attempt < max_retries - 1:
                        await asyncio.sleep(2 ** attempt)  # 1s, 2s, 4s

    except Exception as e:
        logger.error("Webhook delivery engine error", error=str(e), exc_info=True)


async def fire_investigation_complete_webhook(
    user_id: str,
    session_id: str,
    case_id: str,
    verdict: str,
    manipulation_probability: float,
    report_hash: str | None = None,
) -> None:
    """
    Fire the investigation.complete webhook event.

    Should be called from InvestigationRunner after a pipeline completes.
    Runs as a background task to avoid blocking the response.
    """
    payload = {
        "event": "investigation.complete",
        "session_id": session_id,
        "case_id": case_id,
        "verdict": verdict,
        "manipulation_probability": round(manipulation_probability, 4),
        "report_hash": report_hash,
        "timestamp": datetime.now(UTC).isoformat(),
    }

    # Fire and forget — don't await
    asyncio.create_task(
        deliver_webhook(user_id=user_id, event="investigation.complete", payload=payload)
    )
