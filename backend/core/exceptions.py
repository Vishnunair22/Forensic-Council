"""
Exception Hierarchy Module
==========================

Defines the custom exception hierarchy for the Forensic Council system.
All exceptions inherit from ForensicCouncilBaseException for consistent handling.
"""

from typing import Any, Optional
from uuid import UUID


class ForensicCouncilBaseException(Exception):
    """
    Base exception for all Forensic Council exceptions.

    All custom exceptions in the system should inherit from this class.
    Provides consistent structure for error messages and additional context.

    Attributes:
        message: Human-readable error message
        error_code: Machine-readable error code for programmatic handling
        details: Optional dictionary with additional error context
    """

    def __init__(
        self,
        message: str,
        error_code: Optional[str] = None,
        details: Optional[dict[str, Any]] = None,
    ) -> None:
        """
        Initialize the exception.

        Args:
            message: Human-readable error message
            error_code: Optional machine-readable error code
            details: Optional dictionary with additional context
        """
        self.message = message
        self.error_code = error_code or self.__class__.__name__
        self.details = details or {}
        super().__init__(self.message)

    def to_dict(self) -> dict[str, Any]:
        """Convert exception to dictionary for JSON serialization."""
        return {
            "error": self.error_code,
            "message": self.message,
            "details": self.details,
        }

    def __str__(self) -> str:
        return f"[{self.error_code}] {self.message}"


# -------------------
# Configuration Errors
# -------------------


class ConfigurationError(ForensicCouncilBaseException):
    """Raised when there is a configuration error."""

    pass


# -------------------
# Infrastructure Errors
# -------------------


class InfrastructureError(ForensicCouncilBaseException):
    """Base class for infrastructure-related errors."""

    pass


class CircuitBreakerOpen(InfrastructureError):
    """Raised when the circuit breaker is open and refusing calls."""

    def __init__(
        self,
        message: str = "Circuit breaker is open",
        retry_after: float = 30.0,
        service_name: str = "unknown",
    ):
        self.service_name = service_name
        self.retry_after = retry_after
        super().__init__(
            f"Circuit breaker open for {service_name}: {message}. Refusing calls for {retry_after:.1f}s"
        )


class DatabaseConnectionError(InfrastructureError):
    """Raised when database connection fails."""

    pass


class RedisConnectionError(InfrastructureError):
    """Raised when Redis connection fails."""

    pass


class QdrantConnectionError(InfrastructureError):
    """Raised when Qdrant connection fails."""

    pass


# -------------------
# Security & Signing Errors
# -------------------


class SecurityError(ForensicCouncilBaseException):
    """Base class for security-related errors."""

    pass


class SigningError(SecurityError):
    """Raised when cryptographic signing fails."""

    pass


class VerificationError(SecurityError):
    """Raised when signature verification fails."""

    pass


# -------------------
# Evidence Errors
# -------------------


class EvidenceError(ForensicCouncilBaseException):
    """Base class for evidence-related errors."""

    pass


class EvidenceIntegrityError(EvidenceError):
    """Raised when evidence integrity check fails."""

    pass


class EvidenceNotFoundError(EvidenceError):
    """Raised when requested evidence is not found."""

    pass


# -------------------
# Tool Errors
# -------------------


class ToolError(ForensicCouncilBaseException):
    """Base class for tool-related errors."""

    pass


class ToolUnavailableError(ToolError):
    """
    Raised when a required tool is unavailable.

    This exception should be caught and handled gracefully - it should
    never crash the system. Instead, it should result in an INCOMPLETE
    finding being logged.
    """

    pass


class ToolExecutionError(ToolError):
    """Raised when a tool execution fails."""

    pass


# -------------------
# HITL Errors
# -------------------


class HITLError(ForensicCouncilBaseException):
    """Base class for Human-in-the-Loop errors."""

    pass


class HITLCheckpointError(HITLError):
    """Raised when HITL checkpoint operations fail."""

    pass


class HITLResumeError(HITLError):
    """Raised when resuming from HITL checkpoint fails."""

    pass


# -------------------
# Inter-Agent Communication Errors
# -------------------


class InterAgentError(ForensicCouncilBaseException):
    """Base class for inter-agent communication errors."""

    pass


class InterAgentCallError(InterAgentError):
    """Raised when an inter-agent call fails."""

    pass


class PermittedCallViolationError(InterAgentError):
    """Raised when an inter-agent call violates permitted paths."""

    pass


class ArbiterRechallengeError(InterAgentError):
    """Raised when an agent attempts to re-challenge an Arbiter challenge."""

    def __init__(self, agent_id: str):
        self.agent_id = agent_id
        super().__init__(
            f"Arbiter challenges are terminal: {agent_id} cannot re-challenge the Arbiter."
        )


class CircularCallError(InterAgentError):
    """Raised when a circular inter-agent call is detected."""

    def __init__(self, caller: str, callee: str, artifact_id: Optional[UUID]):
        self.caller = caller
        self.callee = callee
        self.artifact_id = artifact_id
        super().__init__(
            f"Circular call detected: {caller} -> {callee} on artifact {artifact_id}. "
            f"Callee cannot re-initiate call to caller on same artifact within same loop."
        )


# -------------------
# Agent Errors
# -------------------


class AgentError(ForensicCouncilBaseException):
    """Base class for agent-related errors."""

    pass


class AgentInitializationError(AgentError):
    """Raised when agent initialization fails."""

    pass


class AgentExecutionError(AgentError):
    """Raised when agent execution fails."""

    pass


# -------------------
# Calibration Errors
# -------------------


class CalibrationError(ForensicCouncilBaseException):
    """Base class for calibration-related errors."""

    pass


class CalibrationModelError(CalibrationError):
    """Raised when calibration model operations fail."""

    pass


# -------------------
# Report Errors
# -------------------


class ReportError(ForensicCouncilBaseException):
    """Base class for report-related errors."""

    pass


class ReportSigningError(ReportError):
    """Raised when report signing fails."""

    pass


# -------------------
# Memory Errors
# -------------------


class ForensicMemoryError(ForensicCouncilBaseException):
    """Base class for memory-related errors."""

    pass


class WorkingMemoryError(ForensicMemoryError):
    """Raised when working memory operations fail."""

    pass


class EpisodicMemoryError(ForensicMemoryError):
    """Raised when episodic memory operations fail."""

    pass
