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

from core.config import Settings, get_settings
from core.logging import get_logger, StructuredLogger
from core.exceptions import (
    ForensicCouncilBaseException,
    ConfigurationError,
    DatabaseConnectionError,
    RedisConnectionError,
    QdrantConnectionError,
    SigningError,
    VerificationError,
    EvidenceIntegrityError,
    ToolUnavailableError,
    HITLCheckpointError,
    InterAgentCallError,
)

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
