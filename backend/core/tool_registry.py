"""
Tool Registry for Forensic Council agents.

Manages tool registration, availability, and execution with graceful degradation.
"""

from __future__ import annotations

import asyncio
import uuid
from collections.abc import Callable, Coroutine
from datetime import datetime, timezone
from typing import Any

from pydantic import BaseModel, Field

from core.custody_logger import CustodyLogger, EntryType


class Tool(BaseModel):
    """Represents a tool available to an agent."""

    name: str = Field(..., description="Unique tool name")
    description: str = Field(default="", description="Tool description for LLM")
    available: bool = Field(default=True, description="Whether tool is currently available")


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
        self, 
        tool_name: str, 
        handler: ToolHandler, 
        description: str = ""
    ) -> None:
        """
        Register a tool with its handler.
        
        Args:
            tool_name: Unique name for the tool
            handler: Async function that handles tool execution
            description: Description of what the tool does
        """
        self._tools[tool_name] = Tool(
            name=tool_name,
            description=description,
            available=True
        )
        self._handlers[tool_name] = handler

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
        custody_logger: CustodyLogger
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
            custody_logger: Custody logger for audit trail
            
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
                error=f"Tool '{tool_name}' not found in registry"
            )
            # Log the unavailable call
            await custody_logger.log_entry(
                agent_id=agent_id,
                session_id=session_id,
                entry_type=EntryType.TOOL_CALL,
                content={
                    "tool_name": tool_name,
                    "tool_input": input_data,
                    "tool_output": result.model_dump(),
                    "available": False
                }
            )
            return result

        # Tool explicitly marked unavailable
        if not tool.available:
            result = ToolResult(
                tool_name=tool_name,
                success=False,
                unavailable=True,
                error=f"Tool '{tool_name}' is currently unavailable"
            )
            # Log the unavailable call
            await custody_logger.log_entry(
                agent_id=agent_id,
                session_id=session_id,
                entry_type=EntryType.TOOL_CALL,
                content={
                    "tool_name": tool_name,
                    "tool_input": input_data,
                    "tool_output": result.model_dump(),
                    "available": False
                }
            )
            return result

        # Tool is available - execute it
        handler = self._handlers[tool_name]
        try:
            output = await handler(input_data)
            result = ToolResult(
                tool_name=tool_name,
                success=True,
                output=output
            )
        except Exception as e:
            result = ToolResult(
                tool_name=tool_name,
                success=False,
                error=str(e)
            )

        # Log the tool call
        await custody_logger.log_entry(
            agent_id=agent_id,
            session_id=session_id,
            entry_type=EntryType.TOOL_CALL,
            content={
                "tool_name": tool_name,
                "tool_input": input_data,
                "tool_output": result.model_dump(),
                "available": True
            }
        )

        return result