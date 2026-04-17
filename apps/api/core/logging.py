"""
Backward-compatibility shim.

The canonical module is ``core.structured_logging``.
This file re-exports every public name so that any legacy
``from core.logging import …`` continues to work, while
``import logging`` inside this package still resolves to the
stdlib :mod:`logging` module (because the stdlib import takes
precedence over this shim for bare ``import logging``).
"""

from core.structured_logging import (  # noqa: F401
    StructuredFormatter,
    StructuredLogger,
    configure_root_logger,
    get_logger,
    request_id_ctx,
)

__all__ = [
    "get_logger",
    "StructuredLogger",
    "StructuredFormatter",
    "configure_root_logger",
    "request_id_ctx",
]
