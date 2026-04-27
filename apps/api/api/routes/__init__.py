"""
API Routes Re-exports
====================

Re-exports routers from submodules to simplify imports in main.py
and other orchestration modules.
"""

from .auth import router as auth_router
from .hitl import router as hitl_router
from .investigation import router as investigation_router
from .metrics import router as metrics_router
from .sessions import router as sessions_router
from .sse import router as sse_router

__all__ = [
    "auth_router",
    "hitl_router",
    "investigation_router",
    "metrics_router",
    "sessions_router",
    "sse_router",
]
