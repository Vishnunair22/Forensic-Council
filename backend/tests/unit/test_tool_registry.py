"""
Unit tests for core/tool_registry.py
"""

import pytest
from typing import Any
from core.tool_registry import ToolRegistry, Tool, ToolResult


class TestToolRegistry:
    """Test cases for ToolRegistry."""

    @pytest.fixture
    def tool_registry(self):
        """Create a tool registry instance."""
        return ToolRegistry()

    @pytest.fixture
    def sample_tool(self):
        """Create a sample tool function."""
        async def sample_tool_impl(arg1: str, arg2: int = 10) -> dict[str, Any]:
            return {"result": f"{arg1} - {arg2}"}
        return sample_tool_impl

    def test_register_tool(self, tool_registry, sample_tool):
        """Test registering a tool."""
        tool_registry.register("sample_tool", sample_tool)
        
        assert "sample_tool" in tool_registry._tools

    def test_get_tool(self, tool_registry, sample_tool):
        """Test getting a registered tool."""
        tool_registry.register("sample_tool", sample_tool)
        
        tool = tool_registry.get_tool("sample_tool")
        
        assert tool == sample_tool

    def test_list_tools(self, tool_registry, sample_tool):
        """Test listing registered tools."""
        tool_registry.register("tool1", sample_tool)
        tool_registry.register("tool2", sample_tool)
        
        tools = tool_registry.list_tools()
        
        assert "tool1" in tools
        assert "tool2" in tools

    def test_unregister_tool(self, tool_registry, sample_tool):
        """Test unregistering a tool."""
        tool_registry.register("sample_tool", sample_tool)
        tool_registry.unregister("sample_tool")
        
        assert "sample_tool" not in tool_registry._tools

    def test_has_tool(self, tool_registry, sample_tool):
        """Test checking if tool exists."""
        tool_registry.register("sample_tool", sample_tool)
        
        assert tool_registry.has_tool("sample_tool") is True
        assert tool_registry.has_tool("non_existent_tool") is False


class TestTool:
    """Test cases for Tool model."""

    def test_tool_creation(self):
        """Test creating a tool."""
        tool = Tool(
            name="test_tool",
            description="A test tool",
        )
        
        assert tool.name == "test_tool"
        assert tool.description == "A test tool"
        assert tool.available is True


class TestToolResult:
    """Test cases for ToolResult model."""

    def test_tool_result_creation(self):
        """Test creating a tool result."""
        result = ToolResult(
            tool_name="test_tool",
            success=True,
            output={"result": "success"},
        )
        
        assert result.tool_name == "test_tool"
        assert result.success is True
        assert result.output["result"] == "success"

    def test_tool_result_failure(self):
        """Test creating a failed tool result."""
        result = ToolResult(
            tool_name="test_tool",
            success=False,
            error="Something went wrong",
        )
        
        assert result.success is False
        assert result.error == "Something went wrong"
