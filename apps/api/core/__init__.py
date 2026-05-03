"""
Forensic Council Core Module
============================

This module contains the core components of the Forensic Council system:
- Configuration management
- Structured logging
- Exception hierarchy
- Cryptographic signing
- Chain-of-custody logging
"""

from importlib.metadata import PackageNotFoundError
from importlib.metadata import version as _get_version

from core.config import Settings, get_settings
from core.exceptions import (
    ConfigurationError,
    DatabaseConnectionError,
    EvidenceIntegrityError,
    ForensicCouncilBaseException,
    HITLCheckpointError,
    InterAgentCallError,
    QdrantConnectionError,
    RedisConnectionError,
    SigningError,
    ToolUnavailableError,
    VerificationError,
)
from core.structured_logging import StructuredLogger, get_logger

__all__ = [
    "Settings",
    "get_settings",
    "get_logger",
    "StructuredLogger",
    "ForensicCouncilBaseException",
    "ConfigurationError",
    "DatabaseConnectionError",
    "RedisConnectionError",
    "QdrantConnectionError",
    "SigningError",
    "VerificationError",
    "EvidenceIntegrityError",
    "ToolUnavailableError",
    "HITLCheckpointError",
    "InterAgentCallError",
]

try:
    __version__ = _get_version("forensic_council")
except PackageNotFoundError:
    __version__ = "0.0.0+local"
