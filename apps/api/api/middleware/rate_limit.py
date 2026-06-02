"""Rate limiting middleware (Redis-backed, fail-open)."""

from __future__ import annotations

import hashlib
import hmac
import time
from collections import OrderedDict

from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import JSONResponse, Response

from api.middleware._common import CSRF_EXEMPT_PATHS, settings_from_app
from core.config import get_settings
from core.structured_logging import get_logger

logger = get_logger(__name__)

_mem_http_rate: OrderedDict[str, list[float]] = OrderedDict()
_MEM_RATE_MAX_ENTRIES = 10_000


class RateLimitMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        if (
            request.url.path in CSRF_EXEMPT_PATHS
            and not request.url.path.endswith("/auth/login")
        ) or request.method == "OPTIONS":
            return await call_next(request)

        settings = settings_from_app(request)
        if settings.app_env == "development":
            return await call_next(request)

        ip = request.client.host if request.client else "unknown"
        auth_header = request.headers.get("Authorization", "")
        session_cookie = request.cookies.get("access_token", "")
        is_authenticated = bool(auth_header or session_cookie)

        if auth_header:
            raw_token = auth_header[7:] if auth_header.lower().startswith("bearer ") else auth_header
            jwt_secret_key = getattr(settings, "jwt_secret_key", None)
            if not isinstance(jwt_secret_key, str):
                jwt_secret_key = get_settings().jwt_secret_key
            identifier = "tok:" + hmac.HMAC(
                jwt_secret_key.encode(),
                raw_token.strip().encode(),
                hashlib.sha256,
            ).hexdigest()[:32]
        elif session_cookie:
            jwt_secret_key = getattr(settings, "jwt_secret_key", None)
            if not isinstance(jwt_secret_key, str):
                jwt_secret_key = get_settings().jwt_secret_key
            identifier = "cookie:" + hmac.HMAC(
                jwt_secret_key.encode(),
                session_cookie.encode(),
                hashlib.sha256,
            ).hexdigest()[:32]
        else:
            identifier = f"ip:{ip}"

        limit = 60 if is_authenticated else 10
        window = 60

        try:
            from core.persistence.redis_client import (
                get_redis_client as get_rate_limit_redis_client,
            )

            redis = await get_rate_limit_redis_client()
            key = f"rate_limit:{identifier}"

            lua_script = """
            local key = KEYS[1]
            local window = tonumber(ARGV[1])
            local limit_val = tonumber(ARGV[2])
            local count = redis.call('incr', key)
            if count == 1 then
                redis.call('expire', key, window + 1)
            end
            local ttl = redis.call('ttl', key)
            if ttl < 0 then
                redis.call('expire', key, window + 1)
            end
            return {count, ttl}
            """
            result = await redis.eval(lua_script, keys=[key], args=[window, limit])
            count = result[0] if isinstance(result, (list, tuple)) else result

            if count > limit:
                logger.warning(f"Rate limit exceeded for {identifier}", count=count, limit=limit)
                return JSONResponse(
                    status_code=429,
                    content={"detail": "Too many requests. Please try again later."},
                    headers={"Retry-After": str(window)},
                )
        except Exception as e:
            logger.error("Rate limiting error (Redis) — failing open", error=str(e))
            from api.routes.metrics import increment_rate_limit_redis_bypasses

            increment_rate_limit_redis_bypasses()
            if request.url.path.endswith("/auth/login"):
                now = time.time()
                if identifier in _mem_http_rate:
                    _mem_http_rate.move_to_end(identifier)
                bucket = _mem_http_rate.get(identifier, [])
                bucket[:] = [ts for ts in bucket if now - ts < window]
                bucket.append(now)
                _mem_http_rate[identifier] = bucket
                while len(_mem_http_rate) > _MEM_RATE_MAX_ENTRIES:
                    _mem_http_rate.popitem(last=False)
                if len(bucket) > 10:
                    return JSONResponse(
                        status_code=429,
                        content={"detail": "Too many requests. Please try again later."},
                        headers={"Retry-After": str(window)},
                    )

        return await call_next(request)
