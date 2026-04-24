"""
Video Handlers Unit Tests
========================
"""

from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest


class TestVideoHandlers:
    """Tests for VideoHandlers class."""

    @pytest.fixture
    def mock_agent(self):
        agent = MagicMock()
        agent.session_id = str(uuid4())
        agent.agent_id = "video-analysis"
        agent.evidence_artifact = MagicMock()
        agent.evidence_artifact.file_path = "/fake/path/video.mp4"
        agent.update_sub_task = AsyncMock()
        agent._record_tool_result = AsyncMock()
        agent.is_initial_phase = True
        return agent

    def test_register_tools(self, mock_agent):
        """Test tool registration with registry."""
        from core.handlers.video import VideoHandlers

        handler = VideoHandlers(mock_agent)
        mock_registry = MagicMock()

        handler.register_tools(mock_registry)

        assert mock_registry.register.called

    def test_handler_initializes_with_agent(self, mock_agent):
        """Test handler initializes with agent reference."""
        from core.handlers.video import VideoHandlers

        handler = VideoHandlers(mock_agent)

        assert handler.agent == mock_agent

    def test_handler_has_base_class(self, mock_agent):
        """Test handler inherits from BaseToolHandler."""
        from core.handlers.video import VideoHandlers
        from core.handlers.base import BaseToolHandler

        handler = VideoHandlers(mock_agent)
        assert isinstance(handler, BaseToolHandler)

    @pytest.mark.asyncio
    async def test_inject_task_via_base_class(self, mock_agent):
        """Test task injection via inherited method."""
        from core.handlers.video import VideoHandlers

        handler = VideoHandlers(mock_agent)
        handler.agent.working_memory = MagicMock()
        handler.agent.working_memory.create_task = AsyncMock()

        await handler.inject_task("test task", priority=5)

        handler.agent.working_memory.create_task.assert_called_once()

    @pytest.mark.asyncio
    async def test_inject_task_fails_gracefully(self, mock_agent):
        """Test task injection fails without crashing."""
        from core.handlers.video import VideoHandlers

        handler = VideoHandlers(mock_agent)
        handler.agent.working_memory = None

        await handler.inject_task("test task")

    def test_handler_has_tools(self, mock_agent):
        """Test video handlers register at least some tools."""
        from core.handlers.video import VideoHandlers

        handler = VideoHandlers(mock_agent)
        mock_registry = MagicMock()

        handler.register_tools(mock_registry)

        call_count = mock_registry.register.call_count
        assert call_count >= 5, f"Expected >=5 tools, got {call_count}"