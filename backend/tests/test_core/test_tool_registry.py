"""
Tests for Tool Registry.
"""

import pytest
import uuid
from unittest.mock import AsyncMock, MagicMock

from core.tool_registry import Tool, ToolResult, ToolRegistry
from core.custody_logger import CustodyLogger, EntryType


@pytest.fixture
def tool_registry():
    """Create a fresh tool registry."""
    return ToolRegistry()


@pytest.fixture
def mock_custody_logger():
    """Create a mock custody logger."""
    logger = AsyncMock(spec=CustodyLogger)
    logger.log_entry = AsyncMock(return_value=uuid.uuid4())
    return logger


@pytest.fixture
def session_id():
    """Create a test session ID."""
    return uuid.uuid4()


class TestToolModel:
    """Tests for Tool model."""

    def test_tool_creation(self):
        """Test creating a tool."""
        tool = Tool(name="test_tool", description="A test tool")
        assert tool.name == "test_tool"
        assert tool.description == "A test tool"
        assert tool.available is True

    def test_tool_unavailable(self):
        """Test marking a tool unavailable."""
        tool = Tool(name="test_tool", available=False)
        assert tool.available is False


class TestToolResult:
    """Tests for ToolResult model."""

    def test_success_result(self):
        """Test successful tool result."""
        result = ToolResult(
            tool_name="test_tool",
            success=True,
            output={"data": "value"}
        )
        assert result.success is True
        assert result.unavailable is False
        assert result.output == {"data": "value"}
        assert result.error is None

    def test_error_result(self):
        """Test error tool result."""
        result = ToolResult(
            tool_name="test_tool",
            success=False,
            error="Something went wrong"
        )
        assert result.success is False
        assert result.error == "Something went wrong"

    def test_unavailable_result(self):
        """Test unavailable tool result."""
        result = ToolResult(
            tool_name="test_tool",
            success=False,
            unavailable=True,
            error="Tool not found"
        )
        assert result.unavailable is True
        assert result.success is False


class TestToolRegistry:
    """Tests for ToolRegistry class."""

    def test_register_tool(self, tool_registry):
        """Test registering a tool."""
        async def handler(input_data):
            return {"result": "ok"}

        tool_registry.register("test_tool", handler, "Test tool description")

        tool = tool_registry.get_tool("test_tool")
        assert tool is not None
        assert tool.name == "test_tool"
        assert tool.description == "Test tool description"
        assert tool.available is True

    def test_list_tools(self, tool_registry):
        """Test listing all tools."""
        async def handler1(input_data):
            return {"result": 1}

        async def handler2(input_data):
            return {"result": 2}

        tool_registry.register("tool1", handler1)
        tool_registry.register("tool2", handler2)

        tools = tool_registry.list_tools()
        assert len(tools) == 2
        names = {t.name for t in tools}
        assert names == {"tool1", "tool2"}

    def test_get_nonexistent_tool(self, tool_registry):
        """Test getting a tool that doesn't exist."""
        tool = tool_registry.get_tool("nonexistent")
        assert tool is None

    def test_set_unavailable(self, tool_registry):
        """Test marking a tool unavailable."""
        async def handler(input_data):
            return {"result": "ok"}

        tool_registry.register("test_tool", handler)
        assert tool_registry.get_tool("test_tool").available is True

        tool_registry.set_unavailable("test_tool")
        assert tool_registry.get_tool("test_tool").available is False

    def test_set_available(self, tool_registry):
        """Test marking a tool available again."""
        async def handler(input_data):
            return {"result": "ok"}

        tool_registry.register("test_tool", handler)
        tool_registry.set_unavailable("test_tool")
        assert tool_registry.get_tool("test_tool").available is False

        tool_registry.set_available("test_tool")
        assert tool_registry.get_tool("test_tool").available is True

    @pytest.mark.asyncio
    async def test_call_tool(self, tool_registry, mock_custody_logger, session_id):
        """Test calling a tool successfully."""
        async def handler(input_data):
            return {"processed": input_data["value"] * 2}

        tool_registry.register("double", handler, "Doubles a value")

        result = await tool_registry.call(
            tool_name="double",
            input_data={"value": 5},
            agent_id="test_agent",
            session_id=session_id,
            custody_logger=mock_custody_logger
        )

        assert result.success is True
        assert result.output == {"processed": 10}
        assert result.unavailable is False

        # Verify logging
        mock_custody_logger.log_entry.assert_called_once()
        call_args = mock_custody_logger.log_entry.call_args
        assert call_args.kwargs["agent_id"] == "test_agent"
        assert call_args.kwargs["session_id"] == session_id
        assert call_args.kwargs["entry_type"] == EntryType.TOOL_CALL

    @pytest.mark.asyncio
    async def test_unavailable_tool_returns_graceful_result(
        self, tool_registry, mock_custody_logger, session_id
    ):
        """Test that unavailable tool returns graceful result without raising."""
        async def handler(input_data):
            return {"result": "ok"}

        tool_registry.register("test_tool", handler)
        tool_registry.set_unavailable("test_tool")

        result = await tool_registry.call(
            tool_name="test_tool",
            input_data={"test": "data"},
            agent_id="test_agent",
            session_id=session_id,
            custody_logger=mock_custody_logger
        )

        assert result.unavailable is True
        assert result.success is False
        assert "unavailable" in result.error.lower()

    @pytest.mark.asyncio
    async def test_nonexistent_tool_returns_graceful_result(
        self, tool_registry, mock_custody_logger, session_id
    ):
        """Test that nonexistent tool returns graceful result without raising."""
        result = await tool_registry.call(
            tool_name="nonexistent_tool",
            input_data={"test": "data"},
            agent_id="test_agent",
            session_id=session_id,
            custody_logger=mock_custody_logger
        )

        assert result.unavailable is True
        assert result.success is False
        assert "not found" in result.error.lower()

    @pytest.mark.asyncio
    async def test_tool_call_logged_to_custody_logger(
        self, tool_registry, mock_custody_logger, session_id
    ):
        """Test that tool calls are logged to custody logger."""
        async def handler(input_data):
            return {"result": "ok"}

        tool_registry.register("logged_tool", handler)

        await tool_registry.call(
            tool_name="logged_tool",
            input_data={"input": "test"},
            agent_id="test_agent",
            session_id=session_id,
            custody_logger=mock_custody_logger
        )

        mock_custody_logger.log_entry.assert_called_once()

    @pytest.mark.asyncio
    async def test_tool_call_input_and_output_both_logged(
        self, tool_registry, mock_custody_logger, session_id
    ):
        """Test that both input and output are logged."""
        async def handler(input_data):
            return {"output_value": input_data["input_value"] * 3}

        tool_registry.register("triple", handler)

        await tool_registry.call(
            tool_name="triple",
            input_data={"input_value": 7},
            agent_id="test_agent",
            session_id=session_id,
            custody_logger=mock_custody_logger
        )

        # Check the logged data
        call_args = mock_custody_logger.log_entry.call_args
        logged_data = call_args.kwargs["content"]

        assert "tool_input" in logged_data
        assert logged_data["tool_input"] == {"input_value": 7}
        assert "tool_output" in logged_data
        assert logged_data["tool_output"]["output"] == {"output_value": 21}

    @pytest.mark.asyncio
    async def test_tool_exception_caught(
        self, tool_registry, mock_custody_logger, session_id
    ):
        """Test that tool exceptions are caught and returned as error results."""
        async def failing_handler(input_data):
            raise ValueError("Tool failed!")

        tool_registry.register("failing_tool", failing_handler)

        result = await tool_registry.call(
            tool_name="failing_tool",
            input_data={"test": "data"},
            agent_id="test_agent",
            session_id=session_id,
            custody_logger=mock_custody_logger
        )

        assert result.success is False
        assert "Tool failed!" in result.error
        assert result.unavailable is False  # Tool exists, just failed
