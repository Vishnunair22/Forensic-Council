"""
Audio Handlers Unit Tests
========================
"""

from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest


class TestAudioHandlers:
    """Tests for AudioHandlers class."""

    @pytest.fixture
    def mock_agent(self):
        agent = MagicMock()
        agent.session_id = str(uuid4())
        agent.agent_id = "audio-analysis"
        agent.evidence_artifact = MagicMock()
        agent.evidence_artifact.file_path = "/fake/path/audio.wav"
        agent.evidence_artifact.mime_type = "audio/wav"
        agent.update_sub_task = AsyncMock()
        agent._record_tool_result = AsyncMock()
        agent.is_initial_phase = True
        return agent

    def test_register_tools(self, mock_agent):
        """Test tool registration with registry."""
        from core.handlers.audio import AudioHandlers

        handler = AudioHandlers(mock_agent)
        mock_registry = MagicMock()

        handler.register_tools(mock_registry)

        assert mock_registry.register.called

    def test_handler_initializes_with_agent(self, mock_agent):
        """Test handler initializes with agent reference."""
        from core.handlers.audio import AudioHandlers

        handler = AudioHandlers(mock_agent)

        assert handler.agent == mock_agent

    def test_handler_has_base_class(self, mock_agent):
        """Test handler inherits from BaseToolHandler."""
        from core.handlers.audio import AudioHandlers
        from core.handlers.base import BaseToolHandler

        handler = AudioHandlers(mock_agent)
        assert isinstance(handler, BaseToolHandler)

    @pytest.mark.asyncio
    async def test_audio_artifact_with_audio_file(self, mock_agent):
        """Test _audio_artifact returns artifact for audio file."""
        from core.handlers.audio import AudioHandlers

        handler = AudioHandlers(mock_agent)

        result = await handler._audio_artifact()

        assert result == mock_agent.evidence_artifact

    @pytest.mark.asyncio
    async def test_inject_task_via_base_class(self, mock_agent):
        """Test task injection via inherited method."""
        from core.handlers.audio import AudioHandlers

        handler = AudioHandlers(mock_agent)
        handler.agent.working_memory = MagicMock()
        handler.agent.working_memory.create_task = AsyncMock()

        await handler.inject_task("test task", priority=5)

        handler.agent.working_memory.create_task.assert_called_once()

    @pytest.mark.asyncio
    async def test_inject_task_fails_gracefully(self, mock_agent):
        """Test task injection fails without crashing."""
        from core.handlers.audio import AudioHandlers

        handler = AudioHandlers(mock_agent)
        handler.agent.working_memory = None

        await handler.inject_task("test task")

    def test_handler_has_tools(self, mock_agent):
        """Test audio handlers register multiple tools."""
        from core.handlers.audio import AudioHandlers

        handler = AudioHandlers(mock_agent)
        mock_registry = MagicMock()

        handler.register_tools(mock_registry)

        call_count = mock_registry.register.call_count
        assert call_count >= 5, f"Expected >=5 tools, got {call_count}"

    @pytest.mark.asyncio
    async def test_audio_extraction_failure_graceful_degradation(self, mock_agent):
        """Test that _audio_artifact returns degraded result on ffmpeg failure."""
        from unittest.mock import patch

        from core.handlers.audio import AudioHandlers

        mock_agent._extracted_audio_artifact = None
        mock_agent.evidence_artifact.mime_type = "video/mp4"
        mock_agent.evidence_artifact.file_path = "/fake/path/video.mp4"
        handler = AudioHandlers(mock_agent)

        with patch("asyncio.create_subprocess_exec") as mock_exec:
            # Mock subprocess to fail
            mock_proc = MagicMock()
            mock_proc.communicate = AsyncMock(return_value=(b"", b"ffmpeg error"))
            mock_proc.returncode = 1
            mock_exec.return_value = mock_proc

            result = await handler._audio_artifact()

            assert getattr(result, "extraction_failed", False) is True
            assert "Container decode failed" in getattr(result, "error_detail", "")

        # Now test that a tool handler gracefully returns this failure
        diag_res = await handler.speaker_diarization_handler({"artifact": result})
        assert diag_res["status"] == "unavailable"
        assert diag_res["evidence_verdict"] == "ERROR"
        assert diag_res["available"] is False
        mock_agent._record_tool_result.assert_called_with("speaker_diarize", diag_res)
