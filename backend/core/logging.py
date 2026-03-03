"""
Structured Logging Module
=========================

Provides structured JSON logging for the Forensic Council system.
All logs are formatted as JSON for easy parsing and analysis.
"""

import json
import logging
import sys
from datetime import datetime, timezone
from typing import Any, Optional
from functools import lru_cache


class StructuredFormatter(logging.Formatter):
    """
    Custom formatter that outputs log records as JSON.
    
    Each log record is formatted as a JSON object with:
    - timestamp: ISO 8601 UTC timestamp
    - level: Log level (DEBUG, INFO, WARNING, ERROR, CRITICAL)
    - logger: Logger name
    - message: Log message
    - extra: Any additional fields passed to the logger
    """
    
    def format(self, record: logging.LogRecord) -> str:
        """Format the log record as JSON."""
        log_data: dict[str, Any] = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        
        # Add location info
        log_data["location"] = {
            "file": record.filename,
            "line": record.lineno,
            "function": record.funcName,
        }
        
        # Add any extra fields passed to the logger
        if hasattr(record, "extra_fields") and record.extra_fields:
            log_data["extra"] = record.extra_fields
        
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
    
    def __init__(self, name: str, level: Optional[str] = None):
        """
        Initialize the structured logger.
        
        Args:
            name: Logger name (typically __name__)
            level: Optional log level override
        """
        self._logger = logging.getLogger(name)
        
        if level:
            self._logger.setLevel(getattr(logging, level.upper()))
        
        # Only add handler if not already configured
        if not self._logger.handlers:
            handler = logging.StreamHandler(sys.stdout)
            handler.setFormatter(StructuredFormatter())
            self._logger.addHandler(handler)
    
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


@lru_cache()
def get_logger(name: str, level: Optional[str] = None) -> StructuredLogger:
    """
    Get a structured logger instance.
    
    Args:
        name: Logger name (typically __name__)
        level: Optional log level override
    
    Returns:
        StructuredLogger instance
    
    Usage:
        logger = get_logger(__name__)
        logger.info("Application started", version="1.0.0")
    """
    return StructuredLogger(name, level)


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
