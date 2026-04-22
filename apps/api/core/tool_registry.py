"""
Tool Registry for Forensic Council agents.

Manages tool registration, availability, and execution with graceful degradation.
"""

from __future__ import annotations

import asyncio
import uuid
from collections.abc import Callable, Coroutine
from typing import TYPE_CHECKING, Any

from pydantic import BaseModel, Field

from core.custody_logger import CustodyLogger, EntryType
from core.structured_logging import get_logger

if TYPE_CHECKING:
    from core.handlers.base import BaseToolHandler

logger = get_logger(__name__)


TOOL_TIMEOUTS: dict[str, float] = {
    # OCR can cold-start slowly in Docker. Keep it bounded so image analysis
    # never blocks the analyst decision gate.
    "extract_text_from_image": 15.0,
    "extract_evidence_text": 15.0,
    "neural_fingerprint": 25.0,
    "noiseprint_cluster": 30.0,
    "neural_ela": 30.0,
    # Gemini deep forensic includes up to 60s wait for Agent1 context
    # plus Gemini API latency. Give it headroom above the inner wait.
    "gemini_deep_forensic": 90.0,
}


class Tool(BaseModel):
    """Represents a tool available to an agent."""

    name: str = Field(..., description="Unique tool name")
    description: str = Field(default="", description="Tool description for LLM")
    available: bool = Field(
        default=True, description="Whether tool is currently available"
    )


class ToolResult(BaseModel):
    """Result of a tool execution."""

    tool_name: str = Field(..., description="Name of the tool that was called")
    success: bool = Field(default=True, description="Whether the tool call succeeded")
    output: dict[str, Any] = Field(default_factory=dict, description="Tool output data")
    error: str | None = Field(default=None, description="Error message if failed")
    unavailable: bool = Field(default=False, description="Whether tool was unavailable")


# Type for tool handlers - async function that takes input dict and returns dict
ToolHandler = Callable[[dict[str, Any]], Coroutine[Any, Any, dict[str, Any]]]


class ToolRegistry:
    """
    Registry for managing tools available to an agent.

    Handles tool registration, availability tracking, and execution
    with graceful degradation when tools are unavailable.
    """

    def __init__(self) -> None:
        """Initialize an empty tool registry."""
        self._tools: dict[str, Tool] = {}
        self._handlers: dict[str, ToolHandler] = {}

    def register(
        self, tool_name: str, handler: ToolHandler, description: str = ""
    ) -> None:
        """
        Register a tool with its handler.

        Args:
            tool_name: Unique name for the tool
            handler: Async function that handles tool execution
            description: Description of what the tool does
        """
        self._tools[tool_name] = Tool(
            name=tool_name, description=description, available=True
        )
        self._handlers[tool_name] = handler

    def register_domain_handler(self, handler_instance: BaseToolHandler) -> None:
        """
        Register all tools defined by a domain-specific handler.

        Args:
            handler_instance: Instance of a BaseToolHandler subclass
        """
        handler_instance.register_tools(self)

    def get_tool(self, tool_name: str) -> Tool | None:
        """
        Get tool metadata by name.

        Args:
            tool_name: Name of the tool

        Returns:
            Tool object or None if not found
        """
        return self._tools.get(tool_name)

    def list_tools(self) -> list[Tool]:
        """
        List all registered tools.

        Returns:
            List of Tool objects
        """
        return list(self._tools.values())

    def set_unavailable(self, tool_name: str) -> None:
        """
        Mark a tool as unavailable (for testing graceful degradation).

        Args:
            tool_name: Name of the tool to mark unavailable
        """
        if tool_name in self._tools:
            self._tools[tool_name].available = False

    def set_available(self, tool_name: str) -> None:
        """
        Mark a tool as available again.

        Args:
            tool_name: Name of the tool to mark available
        """
        if tool_name in self._tools:
            self._tools[tool_name].available = True

    async def call(
        self,
        tool_name: str,
        input_data: dict[str, Any],
        agent_id: str,
        session_id: uuid.UUID,
        custody_logger: CustodyLogger | None = None,
    ) -> ToolResult:
        """
        Execute a tool call with logging and graceful degradation.

        If the tool is unavailable, returns ToolResult(unavailable=True)
        without raising an exception.

        Args:
            tool_name: Name of the tool to call
            input_data: Input parameters for the tool
            agent_id: ID of the agent making the call
            session_id: Session ID for logging
            custody_logger: Optional custody logger for audit trail

        Returns:
            ToolResult with success/failure status and output
        """
        tool = self._tools.get(tool_name)

        # Tool not found - treat as unavailable
        if tool is None:
            result = ToolResult(
                tool_name=tool_name,
                success=False,
                unavailable=True,
                error=f"Tool '{tool_name}' not found in registry",
            )
            # Log the unavailable call
            if custody_logger:
                await custody_logger.log_entry(
                    agent_id=agent_id,
                    session_id=session_id,
                    entry_type=EntryType.TOOL_CALL,
                    content={
                        "tool_name": tool_name,
                        "tool_input": input_data,
                        "tool_output": result.model_dump(),
                        "available": False,
                    },
                )
            return result

        # Tool explicitly marked unavailable
        if not tool.available:
            result = ToolResult(
                tool_name=tool_name,
                success=False,
                unavailable=True,
                error=f"Tool '{tool_name}' is currently unavailable",
            )
            # Log the unavailable call
            if custody_logger:
                await custody_logger.log_entry(
                    agent_id=agent_id,
                    session_id=session_id,
                    entry_type=EntryType.TOOL_CALL,
                    content={
                        "tool_name": tool_name,
                        "tool_input": input_data,
                        "tool_output": result.model_dump(),
                        "available": False,
                    },
                )
            return result

        # Tool is available - execute it
        handler = self._handlers[tool_name]
        try:
            # Per-tool timeout: prevents a single hanging tool from blocking
            # the entire agent and timing out the full investigation.
            # 60s is generous for in-process tools; ML subprocesses have
            # their own tighter timeouts inside run_ml_tool.
            timeout_s = TOOL_TIMEOUTS.get(tool_name, 45.0)
            output = await asyncio.wait_for(handler(input_data), timeout=timeout_s)
            result = ToolResult(tool_name=tool_name, success=True, output=output)
        except TimeoutError:
            logger.warning(
                f"Tool '{tool_name}' timed out",
                tool_name=tool_name,
                timeout=TOOL_TIMEOUTS.get(tool_name, 45.0)
            )
            result = ToolResult(
                tool_name=tool_name,
                success=False,
                error=f"Tool '{tool_name}' timed out after {TOOL_TIMEOUTS.get(tool_name, 45.0):.0f}s",
            )
        except (OSError, ValueError, TypeError, RuntimeError) as e:
            # Specific expected tool errors (file I/O, validation, etc.)
            logger.error(
                f"Tool '{tool_name}' execution failed",
                tool_name=tool_name,
                error=str(e),
                error_type=type(e).__name__,
                exc_info=True
            )
            result = ToolResult(tool_name=tool_name, success=False, error=str(e))
        except Exception as e:
            # A single broken forensic tool must not strand the agent or block
            # analyst decisions. Preserve the diagnostic as an incomplete
            # finding and let the rest of the plan continue.
            logger.error(
                f"Unexpected error in tool '{tool_name}'",
                tool_name=tool_name,
                error=str(e),
                error_type=type(e).__name__,
                exc_info=True
            )
            result = ToolResult(tool_name=tool_name, success=False, error=str(e))

        # Log the tool call
        if custody_logger:
            await custody_logger.log_entry(
                agent_id=agent_id,
                session_id=session_id,
                entry_type=EntryType.TOOL_CALL,
                content={
                    "tool_name": tool_name,
                    "tool_input": input_data,
                    "tool_output": result.model_dump(),
                    "available": True,
                },
            )

        return result
