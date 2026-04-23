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
    "extract_text_from_image": 45.0,
    "extract_evidence_text": 45.0,
    "neural_fingerprint": 30.0,
    "noiseprint_cluster": 35.0,
    "neural_ela": 35.0,
    # Gemini deep forensic includes up to 60s wait for Agent1 context
    # plus Gemini API latency. Give it headroom above the inner wait.
    "gemini_deep_forensic": 120.0,
}

DEFAULT_TOOL_TIMEOUT = 60.0
 
# Tools that are CPU/GPU intensive and should be throttled by a semaphore.
# API-based tools (like Gemini) or light metadata tools are excluded.
HEAVY_TOOLS: set[str] = {
    "ela_full_image",
    "ela_anomaly_classify",
    "jpeg_ghost_detect",
    "frequency_domain_analysis",
    "splicing_detect",
    "noise_fingerprint",
    "deepfake_frequency_check",
    "neural_fingerprint",
    "neural_copy_move",
    "extract_text_from_image",
    "extract_evidence_text",
    "speaker_diarize",
    "anti_spoofing_detect",
    "prosody_analyze",
    "audio_splice_detect",
    "background_noise_analysis",
    "object_detection",
    "lighting_consistency",
    "scene_incongruence",
    "vector_contraband_search",
    "optical_flow_analysis",
    "frame_consistency_analysis",
    "face_swap_detection",
    "vfi_error_map",
    "interframe_forgery_detector",
    "rolling_shutter_validation",
    "steganography_scan",
    "file_structure_analysis",
    "hex_signature_scan",
    "astro_grounding",
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

def tool(name: str, description: str):
    """
    Decorator to mark a method as a tool handler.
    
    Usage:
        @tool(name="my_tool", description="Does something cool")
        async def my_handler(self, input_data: dict) -> dict:
            ...
    """
    def decorator(func):
        func._is_tool = True
        func._tool_name = name
        func._tool_description = description
        return func
    return decorator


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
        
        Detects methods decorated with @tool and also calls the legacy
        register_tools() for manual registration.
        """
        # 1. Manual registration via register_tools()
        handler_instance.register_tools(self)

        # 2. Automatic registration via @tool decorator
        import inspect
        for name, method in inspect.getmembers(handler_instance, predicate=inspect.ismethod):
            if getattr(method, "_is_tool", False):
                t_name = getattr(method, "_tool_name")
                t_desc = getattr(method, "_tool_description")
                self.register(t_name, method, t_desc)
                logger.debug(f"Auto-registered tool: {t_name} from {handler_instance.__class__.__name__}")

    def get_handler(self, name: str) -> ToolHandler | None:
        """Return the callable handler for a registered tool, or None."""
        return self._handlers.get(name)

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
        semaphore: asyncio.Semaphore | None = None,
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
            timeout_s = TOOL_TIMEOUTS.get(tool_name, DEFAULT_TOOL_TIMEOUT)

            # Apply semaphore gating for heavy CPU/GPU tools
            if semaphore and tool_name in HEAVY_TOOLS:
                async with semaphore:
                    logger.debug(f"Acquired heavy tool semaphore for {tool_name}", agent_id=agent_id)
                    output = await asyncio.wait_for(handler(input_data), timeout=timeout_s)
            else:
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
