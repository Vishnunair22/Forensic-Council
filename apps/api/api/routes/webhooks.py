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

Security posture:
  S-C-1  Egress URLs are validated against a private/loopback/link-local
         blocker before storage and at every redirect; only http/https.
  S-C-2  Per-webhook signing secrets are encrypted at rest with Fernet
         (key derived from settings.signing_key via HKDF). Redis never
         sees the plaintext.
  S-M-6  Signatures bind a server-issued timestamp to the body, allowing
         consumers to reject replays older than ±5 min.
"""

from __future__ import annotations

import asyncio
import base64
import hashlib
import hmac
import ipaddress
import json
import socket
from datetime import UTC, datetime
from typing import Any
from urllib.parse import urlparse
from uuid import uuid4

import httpx
from cryptography.fernet import Fernet, InvalidToken
from cryptography.hazmat.backends import default_backend
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.hkdf import HKDF
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, HttpUrl

from core.auth import get_current_user
from core.config import get_settings
from core.persistence.redis_client import get_redis_client
from core.structured_logging import get_logger

logger = get_logger(__name__)

webhooks_router = APIRouter(prefix="/api/v1/webhooks", tags=["webhooks"])

# Redis key prefix for webhook storage
_WEBHOOK_KEY_PREFIX = "webhooks:"
_WEBHOOK_TTL = 60 * 60 * 24 * 90  # 90 days


# ---------------------------------------------------------------------------
# S-C-2: encryption-at-rest helpers
# ---------------------------------------------------------------------------
_fernet_instance: Fernet | None = None


def _fernet() -> Fernet | None:
    """Lazily build a Fernet cipher keyed off settings.signing_key via HKDF.

    Returns None if signing_key is missing — caller falls back to refusing
    to persist the secret (deny by default).
    """
    global _fernet_instance
    if _fernet_instance is not None:
        return _fernet_instance
    try:
        signing_key = (get_settings().signing_key or "").encode("utf-8")
        if not signing_key:
            return None
        derived = HKDF(
            algorithm=hashes.SHA256(),
            length=32,
            salt=b"forensic-council-webhook-secret-v1-salt",
            info=b"forensic-council-webhook-secret-v1",
            backend=default_backend(),
        ).derive(signing_key)
        _fernet_instance = Fernet(base64.urlsafe_b64encode(derived))
        return _fernet_instance
    except Exception as exc:
        logger.error("Failed to initialize webhook Fernet cipher", error=str(exc))
        return None


def _encrypt_secret(plaintext: str) -> str | None:
    """Encrypt and base64-encode a webhook signing secret for Redis storage."""
    cipher = _fernet()
    if cipher is None:
        return None
    return cipher.encrypt(plaintext.encode("utf-8")).decode("ascii")


def _decrypt_secret(ciphertext: str | None) -> str | None:
    """Decrypt a previously-encrypted webhook signing secret. None on failure."""
    if not ciphertext:
        return None
    cipher = _fernet()
    if cipher is None:
        return None
    try:
        return cipher.decrypt(ciphertext.encode("ascii")).decode("utf-8")
    except (InvalidToken, ValueError):
        logger.warning("Failed to decrypt webhook secret — record may be corrupt or key rotated")
        return None


# ---------------------------------------------------------------------------
# S-C-1: SSRF protection helpers
# ---------------------------------------------------------------------------
_BLOCKED_IP_REASONS = (
    "private",
    "loopback",
    "link-local",
    "multicast",
    "reserved",
    "unspecified",
)


def _ip_block_reason(ip: ipaddress.IPv4Address | ipaddress.IPv6Address) -> str | None:
    """Return a short reason string if the IP is not safe for egress, else None."""
    if ip.is_private:
        return "private"
    if ip.is_loopback:
        return "loopback"
    if ip.is_link_local:
        return "link-local"
    if ip.is_multicast:
        return "multicast"
    if ip.is_reserved:
        return "reserved"
    if ip.is_unspecified:
        return "unspecified"
    # Block AWS / GCP / Azure cloud metadata IPs even though some are in
    # link-local (already caught) or reserved (already caught).
    if str(ip) in {"169.254.169.254", "100.100.100.200", "fd00:ec2::254"}:
        return "cloud-metadata"
    return None


def _validate_egress_url(url: str) -> tuple[str | None, str | None]:
    """Validate a candidate webhook URL for safe egress.

    Returns (host_ip_string, None) when the URL is safe to call. On reject,
    returns (None, reason_string) where reason_string is suitable for a 4xx
    response body. Resolves DNS once; caller should reuse the IP at request
    time (or re-check after redirects) — Pydantic only validates syntax.
    """
    try:
        parsed = urlparse(url)
    except Exception:
        return None, "Invalid URL"
    if parsed.scheme not in ("https", "http"):
        return None, f"Unsupported scheme: {parsed.scheme!r}"
    settings = get_settings()
    if settings.app_env == "production" and parsed.scheme != "https":
        return None, "Only https:// is allowed in production"
    if not parsed.hostname:
        return None, "Missing hostname"
    if parsed.port is not None and parsed.port < 1024 and parsed.port != 443 and parsed.port != 80:
        return None, f"Privileged port {parsed.port} is not permitted"

    # Resolve hostname; reject if any A/AAAA record is in a blocked range.
    try:
        infos = socket.getaddrinfo(parsed.hostname, None)
    except socket.gaierror as exc:
        return None, f"DNS resolution failed: {exc}"

    resolved: str | None = None
    for info in infos:
        addr = info[4][0]
        try:
            ip = ipaddress.ip_address(addr)
        except ValueError:
            continue
        reason = _ip_block_reason(ip)
        if reason is not None:
            return None, f"Host {parsed.hostname!r} resolves to a {reason} address ({addr})"
        resolved = addr
    if resolved is None:
        return None, "Could not resolve hostname to a public IP"
    return resolved, None


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
    # S-C-1: refuse private / loopback / link-local / metadata URLs at the
    # registration boundary so an attacker cannot smuggle the URL into Redis.
    _ip, err = _validate_egress_url(str(body.url))
    if err is not None:
        raise HTTPException(status_code=400, detail=f"Webhook URL rejected: {err}")

    redis = await get_redis_client()
    webhook_id = str(uuid4())
    user_id = str(current_user.user_id)

    # Store hashed secret for client-visible identification only
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

    full_record = record.model_dump()
    # S-C-2: encrypt the signing secret with Fernet before persisting.
    # If Fernet is unavailable (missing signing_key), refuse rather than
    # storing plaintext — fail-secure.
    if body.secret:
        encrypted = _encrypt_secret(body.secret)
        if encrypted is None:
            raise HTTPException(
                status_code=503,
                detail="Webhook secret storage is unavailable; please retry later.",
            )
        full_record["_secret_enc"] = encrypted

    key = f"{_WEBHOOK_KEY_PREFIX}{user_id}:{webhook_id}"
    await redis.set(key, json.dumps(full_record), ex=_WEBHOOK_TTL)

    logger.info(
        "Webhook registered",
        webhook_id=webhook_id,
        user_id=user_id,
        url=str(body.url),
    )
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
    # B-H-1: SCAN instead of KEYS.
    async for key in redis.scan_iter(match=pattern, count=100):
        raw = await redis.get(key)
        if raw:
            try:
                record = json.loads(raw)
                # Never return the (encrypted or plaintext) secret.
                record.pop("_secret", None)
                record.pop("_secret_enc", None)
                results.append(record)
            except Exception as _decode_err:
                logger.debug("Skipping malformed webhook record", error=str(_decode_err))

    return results


@webhooks_router.delete("/{webhook_id}", status_code=204)
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
            if not raw:
                continue
            try:
                record = json.loads(raw)
                if event in record.get("events", []):
                    webhooks.append(record)
            except Exception as _decode_err:
                logger.debug(
                    "Skipping malformed webhook record in dispatch",
                    error=str(_decode_err),
                )

        payload_str = json.dumps(payload, default=str)

        # S-C-1: disable httpx auto-follow so we re-validate every redirect.
        async with httpx.AsyncClient(timeout=10.0, follow_redirects=False) as client:
            for webhook in webhooks:
                url = webhook.get("url", "")
                # Re-validate URL at delivery time (TOCTOU defense — DNS may
                # have shifted to point at an internal IP since registration).
                _ip, ssrf_err = _validate_egress_url(url)
                if ssrf_err is not None:
                    logger.warning(
                        "Refusing to deliver webhook: SSRF guard",
                        webhook_id=webhook.get("webhook_id"),
                        url=url,
                        reason=ssrf_err,
                    )
                    continue

                # S-C-2: decrypt secret on demand. Legacy plaintext "_secret"
                # records are accepted for backwards compatibility but logged
                # for operator attention.
                secret = _decrypt_secret(webhook.get("_secret_enc"))
                if secret is None and webhook.get("_secret"):
                    logger.warning(
                        "Webhook record still uses legacy plaintext secret",
                        webhook_id=webhook.get("webhook_id"),
                    )
                    secret = webhook.get("_secret")

                # S-M-6: bind a server-issued timestamp into the signature so
                # captured webhooks cannot be replayed indefinitely.
                ts = str(int(datetime.now(UTC).timestamp()))
                headers = {
                    "Content-Type": "application/json",
                    "X-FC-Event": event,
                    "X-FC-Timestamp": ts,
                }
                if secret:
                    signed_payload = f"{ts}.{payload_str}".encode("utf-8")
                    sig = hmac.new(
                        key=secret.encode("utf-8"),
                        msg=signed_payload,
                        digestmod=hashlib.sha256,
                    ).hexdigest()
                    headers["X-FC-Signature"] = f"sha256={sig}"

                for attempt in range(max_retries):
                    try:
                        resp = await client.post(url, content=payload_str, headers=headers)
                        if 300 <= resp.status_code < 400:
                            # S-C-1: a redirect target could resolve to a
                            # private/loopback IP. Refuse to follow.
                            logger.warning(
                                "Webhook target attempted redirect; not followed",
                                webhook_id=webhook.get("webhook_id"),
                                url=url,
                                status=resp.status_code,
                            )
                            break
                        if resp.status_code < 400:
                            logger.info(
                                "Webhook delivered",
                                webhook_id=webhook.get("webhook_id"),
                                url=url,
                                status=resp.status_code,
                            )
                            break
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

    asyncio.create_task(
        deliver_webhook(user_id=user_id, event="investigation.complete", payload=payload)
    )
