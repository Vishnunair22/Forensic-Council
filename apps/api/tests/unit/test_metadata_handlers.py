"""
Metadata Handlers Unit Tests
========================
"""

from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest


class TestMetadataHandlers:
    """Tests for MetadataHandlers class."""

    @pytest.fixture
    def mock_agent(self):
        agent = MagicMock()
        agent.session_id = str(uuid4())
        agent.agent_id = "gemini-vision"
        agent.evidence_artifact = MagicMock()
        agent.evidence_artifact.file_path = "/fake/path/image.jpg"
        agent.update_sub_task = AsyncMock()
        agent._record_tool_result = AsyncMock()
        agent.is_initial_phase = True
        return agent

    def test_register_tools(self, mock_agent):
        """Test tool registration with registry."""
        from core.handlers.metadata import MetadataHandlers

        handler = MetadataHandlers(mock_agent)
        mock_registry = MagicMock()

        handler.register_tools(mock_registry)

        assert mock_registry.register.called
        registered_names = [call[0][0] for call in mock_registry.register.call_args_list]
        assert "exif_extract" in registered_names
        assert "steganography_scan" in registered_names
        assert "timestamp_analysis" in registered_names
        assert "file_structure_analysis" in registered_names
        assert "hex_signature_scan" in registered_names
        assert "camera_profile_match" in registered_names

    def test_handler_initializes_with_agent(self, mock_agent):
        """Test handler initializes with agent reference."""
        from core.handlers.metadata import MetadataHandlers

        handler = MetadataHandlers(mock_agent)

        assert handler.agent == mock_agent

    def test_handler_has_base_class(self, mock_agent):
        """Test handler inherits from BaseToolHandler."""
        from core.handlers.metadata import MetadataHandlers
        from core.handlers.base import BaseToolHandler

        handler = MetadataHandlers(mock_agent)
        assert isinstance(handler, BaseToolHandler)

    def test_register_compatibility_aliases(self, mock_agent):
        """Test compatibility aliases are registered."""
        from core.handlers.metadata import MetadataHandlers

        handler = MetadataHandlers(mock_agent)
        mock_registry = MagicMock()

        handler.register_tools(mock_registry)

        registered_names = [call[0][0] for call in mock_registry.register.call_args_list]
        assert "metadata_anomaly_scorer" in registered_names
        assert "c2pa_validator" in registered_names

    def test_register_refinement_tools(self, mock_agent):
        """Test refinement tools are registered."""
        from core.handlers.metadata import MetadataHandlers

        handler = MetadataHandlers(mock_agent)
        mock_registry = MagicMock()

        handler.register_tools(mock_registry)

        registered_names = [call[0][0] for call in mock_registry.register.call_args_list]
        assert "exif_isolation_forest" in registered_names
        assert "astro_grounding" in registered_names

    @pytest.mark.asyncio
    async def test_inject_task_via_base_class(self, mock_agent):
        """Test task injection via inherited method."""
        from core.handlers.metadata import MetadataHandlers

        handler = MetadataHandlers(mock_agent)
        handler.agent.working_memory = MagicMock()
        handler.agent.working_memory.create_task = AsyncMock()

        await handler.inject_task("test task", priority=5)

        handler.agent.working_memory.create_task.assert_called_once()

    @pytest.mark.asyncio
    async def test_inject_task_fails_gracefully(self, mock_agent):
        """Test task injection fails without crashing."""
        from core.handlers.metadata import MetadataHandlers

        handler = MetadataHandlers(mock_agent)
        handler.agent.working_memory = None

        await handler.inject_task("test task")

    def test_handler_has_all_required_tools(self, mock_agent):
        """Test all expected tools are registered."""
        from core.handlers.metadata import MetadataHandlers

        handler = MetadataHandlers(mock_agent)
        mock_registry = MagicMock()

        handler.register_tools(mock_registry)

        call_count = mock_registry.register.call_count
        assert call_count >= 10, f"Expected >=10 tools, got {call_count}"


class TestMetadataToolsDirect:
    """Tests for direct metadata tool functions."""

    @pytest.fixture
    def mock_artifact(self):
        artifact = MagicMock()
        artifact.file_path = "/nonexistent/file.jpg"
        artifact.mime_type = "image/jpeg"
        return artifact

    @pytest.mark.asyncio
    async def test_camera_profile_match_returns_structure(self, mock_artifact):
        """Test camera_profile_match returns expected structure."""
        from tools.metadata_tools import camera_profile_match

        result = await camera_profile_match(mock_artifact)

        assert isinstance(result, dict)
        assert "available" in result

    @pytest.mark.asyncio
    async def test_provenance_chain_verify_returns_structure(self, mock_artifact):
        """Test provenance_chain_verify returns expected structure."""
        from tools.metadata_tools import provenance_chain_verify

        result = await provenance_chain_verify(mock_artifact)

        assert isinstance(result, dict)
        assert "available" in result