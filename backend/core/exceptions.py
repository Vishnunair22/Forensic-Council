"""
Exception Hierarchy Module
==========================

Defines the custom exception hierarchy for the Forensic Council system.
All exceptions inherit from ForensicCouncilBaseException for consistent handling.
"""

from typing import Any, Optional


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


class CircularCallError(InterAgentError):
    """Raised when a circular inter-agent call is detected."""
    pass


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

class MemoryError(ForensicCouncilBaseException):
    """Base class for memory-related errors."""
    pass


class WorkingMemoryError(MemoryError):
    """Raised when working memory operations fail."""
    pass


class EpisodicMemoryError(MemoryError):
    """Raised when episodic memory operations fail."""
    pass
