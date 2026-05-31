"""HTTP middleware stack — registers all middleware in correct order.

FastAPI/Starlette executes middleware in reverse-registration order for
requests (last added = first to run).  The ``add_middleware`` calls below
are ordered so that the outermost layer runs first:

    1. StartupGate   (refuse everything if config is broken)
    2. Diagnostic    (debug request logging)
    3. Metrics       (request counting / timing)
    4. UploadLimit   (body-size guard)
    5. CacheHeaders  (cache-control directives)
    6. RateLimit     (Redis-backed sliding window)
    7. CorrelationId (X-Request-ID injection)
    8. CSRF          (double-submit cookie)
    9. SecurityHeaders
   10. CORS          (added by FastAPI's own add_middleware in main.py)
"""

from __future__ import annotations

from fastapi import FastAPI

from api.middleware.cache import CacheHeadersMiddleware
from api.middleware.correlation_id import CorrelationIdMiddleware
from api.middleware.csrf import CsrfMiddleware
from api.middleware.diagnostic import DiagnosticMiddleware
from api.middleware.metrics import MetricsMiddleware
from api.middleware.rate_limit import RateLimitMiddleware
from api.middleware.security_headers import SecurityHeadersMiddleware
from api.middleware.startup_gate import StartupGateMiddleware
from api.middleware.upload_limit import UploadLimitMiddleware


def register_middleware(app: FastAPI) -> None:
    """Add all HTTP middleware to *app* in the correct order."""
    # Innermost (added first, runs last on request / first on response)
    app.add_middleware(SecurityHeadersMiddleware)
    app.add_middleware(CsrfMiddleware)
    app.add_middleware(CorrelationIdMiddleware)
    app.add_middleware(RateLimitMiddleware)
    app.add_middleware(CacheHeadersMiddleware)
    app.add_middleware(UploadLimitMiddleware)
    app.add_middleware(MetricsMiddleware)
    app.add_middleware(DiagnosticMiddleware)
    app.add_middleware(StartupGateMiddleware)
