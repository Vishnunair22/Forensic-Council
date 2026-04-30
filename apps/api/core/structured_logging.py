"""
Structured Logging Module
=========================

Provides structured JSON logging for the Forensic Council system.
All logs are formatted as JSON for easy parsing and analysis.
"""

import contextvars
import json
import logging
import re
import sys
from datetime import UTC, datetime
from typing import Any

request_id_ctx: contextvars.ContextVar[str] = contextvars.ContextVar("request_id", default="")


class StructuredFormatter(logging.Formatter):
    """
    Custom formatter that outputs log records as JSON.

    Each log record is formatted as a JSON object with:
    - timestamp: ISO 8601 UTC timestamp
    - level: Log level (DEBUG, INFO, WARNING, ERROR, CRITICAL)
    - logger: Logger name
    - message: Log message
    - extra: Any additional fields passed to the logger (masked if sensitive)
    """

    SENSITIVE_KEYS = {
        "password",
        "secret",
        "key",
        "token",
        "auth",
        "credential",
        "private",
        "signing",
    }
    SENSITIVE_VALUE_PATTERNS = (
        re.compile(
            r"(?P<prefix>[?&](?:api[_-]?key|key|token|access[_-]?token|password|secret)=)"
            r"(?P<value>[^&\s\"']+)",
            re.IGNORECASE,
        ),
        re.compile(
            r"(?P<prefix>\bBearer\s+)(?P<value>[A-Za-z0-9._~+/=-]+)",
            re.IGNORECASE,
        ),
    )

    def _mask_sensitive_text(self, value: str) -> str:
        """Mask secrets embedded in free-form log messages."""
        masked = value
        for pattern in self.SENSITIVE_VALUE_PATTERNS:
            masked = pattern.sub(r"\g<prefix>********", masked)
        return masked

    def _mask_sensitive(self, data: Any) -> Any:
        """Recursively mask sensitive keys in log data."""
        if isinstance(data, dict):
            return {
                k: (
                    "********"
                    if any(s in k.lower() for s in self.SENSITIVE_KEYS)
                    else self._mask_sensitive(v)
                )
                for k, v in data.items()
            }
        elif isinstance(data, list):
            return [self._mask_sensitive(i) for i in data]
        elif isinstance(data, str):
            return self._mask_sensitive_text(data)
        return data

    def format(self, record: logging.LogRecord) -> str:
        """Format the log record as JSON."""
        log_data: dict[str, Any] = {
            "timestamp": datetime.now(UTC).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": self._mask_sensitive_text(record.getMessage()),
        }

        # Add location info
        log_data["location"] = {
            "file": record.filename,
            "line": record.lineno,
            "function": record.funcName,
        }

        # Add any extra fields passed to the logger (with masking)
        if hasattr(record, "extra_fields") and record.extra_fields:
            log_data["extra"] = self._mask_sensitive(record.extra_fields)

        # Add correlation ID
        req_id = request_id_ctx.get()
        if req_id:
            log_data["request_id"] = req_id

        # Add exception info if present
        if record.exc_info:
            log_data["exception"] = self.formatException(record.exc_info)

        return json.dumps(log_data, default=str)


class StructuredLogger:
    """
    Wrapper around logging.Logger that provides structured logging capabilities.

    Usage:
        logger = get_logger(__name__)
        logger.info("Message", extra={"key": "value"})
        logger.info("User action", user_id="123", action="login")
    """

    def __init__(self, name: str, level: str | None = None):
        """
        Initialize the structured logger.

        Args:
            name: Logger name (typically __name__)
            level: Optional log level override
        """
        self._logger = logging.getLogger(name)

        if level:
            self._logger.setLevel(getattr(logging, level.upper()))

        # We intentionally do NOT add a handler here anymore.
        # Application entry points must call configure_root_logger()
        # at startup to setup the unified structured logging stream.
        pass

    def _log(self, level: int, message: str, **kwargs: Any) -> None:
        """Internal method to log with extra fields."""
        extra = {"extra_fields": kwargs} if kwargs else {}
        self._logger.log(level, message, extra=extra)

    def debug(self, message: str, **kwargs: Any) -> None:
        """Log a debug message."""
        self._log(logging.DEBUG, message, **kwargs)

    def info(self, message: str, **kwargs: Any) -> None:
        """Log an info message."""
        self._log(logging.INFO, message, **kwargs)

    def warning(self, message: str, **kwargs: Any) -> None:
        """Log a warning message."""
        self._log(logging.WARNING, message, **kwargs)

    def error(self, message: str, exc_info: bool = False, **kwargs: Any) -> None:
        """Log an error message."""
        extra = {"extra_fields": kwargs} if kwargs else {}
        self._logger.error(message, exc_info=exc_info, extra=extra)

    def critical(self, message: str, exc_info: bool = False, **kwargs: Any) -> None:
        """Log a critical message."""
        extra = {"extra_fields": kwargs} if kwargs else {}
        self._logger.critical(message, exc_info=exc_info, extra=extra)

    def exception(self, message: str, **kwargs: Any) -> None:
        """Log an exception with traceback."""
        extra = {"extra_fields": kwargs} if kwargs else {}
        self._logger.exception(message, extra=extra)


# Per-name logger cache.  We intentionally do NOT include `level` in the
# cache key — the level can be changed at any time via configure_root_logger
# and we don't want a stale cached logger to ignore a later level change.
# Using a plain dict (not lru_cache) also avoids the unhashable-arg footgun.
_logger_cache: dict[str, "StructuredLogger"] = {}


def get_logger(name: str | None = None, level: str | None = None) -> StructuredLogger:
    """
    Utility function to get a StructuredLogger instance.

    If the root logger has no handlers, this will automatically call
    configure_root_logger() with default settings to ensure logs
    are captured for one-off scripts.
    """
    # Auto-configure root if nothing has done it yet
    if not logging.getLogger().handlers:
        configure_root_logger("INFO")

    # Use a default name if none provided
    name = name or "root"

    if name not in _logger_cache:
        _logger_cache[name] = StructuredLogger(name, level)
    return _logger_cache[name]


def configure_root_logger(level: str = "INFO") -> None:
    """
    Configure the root logger with structured formatting.

    This should be called once at application startup.

    Args:
        level: Log level for the root logger
    """
    root_logger = logging.getLogger()
    root_logger.setLevel(getattr(logging, level.upper()))

    # Remove existing handlers
    for handler in root_logger.handlers[:]:
        root_logger.removeHandler(handler)

    # Add structured handler
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(StructuredFormatter())
    root_logger.addHandler(handler)

    # Third-party HTTP clients log full request URLs at INFO. Keep them quiet so
    # upstream query-string credentials never reach production logs.
    for noisy_logger in ("httpx", "httpcore"):
        logging.getLogger(noisy_logger).setLevel(logging.WARNING)
