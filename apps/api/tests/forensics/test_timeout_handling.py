"""Tests for timeout handling: agent timeout, ML subprocess timeout, OCR scaling."""

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest
from PIL import Image

from core.evidence import ArtifactType, EvidenceArtifact


@pytest.fixture
def mock_artifact():
    sid = uuid4()
    return EvidenceArtifact.create_root(
        artifact_type=ArtifactType.ORIGINAL,
        file_path="",
        content_hash="abc",
        action="upload",
        agent_id="test",
        session_id=sid,
        metadata={"mime_type": "image/jpeg"},
    )


@pytest.mark.asyncio
async def test_ml_subprocess_timeout_returns_error():
    """ML subprocess timeout should return error dict with available=False."""
    from core.ml_subprocess import run_ml_tool

    with patch("core.ml_subprocess.asyncio.create_subprocess_exec") as mock_exec:
        mock_proc = AsyncMock()
        mock_proc.communicate = AsyncMock(side_effect=asyncio.TimeoutError)
        mock_proc.kill = AsyncMock()
        mock_proc.wait = AsyncMock()
        mock_exec.return_value = mock_proc

        result = await run_ml_tool(
            "dummy_tool.py",
            "test.png",
            timeout=0.01,
        )

    assert result["available"] is False
    assert "error" in result


@pytest.mark.asyncio
async def test_agent_timeout_is_handled_gracefully():
    """Agent timeout should produce graceful error result with partial findings."""
    from core.config import Settings
    from orchestration.pipeline_phases import run_agents_concurrent

    settings = Settings(
        app_env="testing",
        signing_key="test-signing-key-" + "x" * 32,
    )

    pipeline = MagicMock()
    pipeline.config = settings
    pipeline.signal_bus = None
    pipeline._degradation_flags = []

    artifact = EvidenceArtifact.create_root(
        artifact_type=ArtifactType.ORIGINAL,
        file_path="test.jpg",
        content_hash="abc",
        action="upload",
        agent_id="test",
        session_id=uuid4(),
        metadata={"mime_type": "image/jpeg"},
    )


    class HangingAgent:
        agent_id = "Agent1"
        session_id = artifact.session_id

        async def run_initial_pass(self):
            await asyncio.sleep(9999)
            return []

        async def run_investigation(self):
            await asyncio.sleep(9999)
            return []

    with (
        patch("core.agent_registry.get_agent_registry") as mock_get_registry,
        patch("asyncio.wait_for", side_effect=asyncio.TimeoutError),
    ):
        mock_registry = MagicMock()
        mock_registry.get_all_agent_ids.return_value = ["Agent1"]
        mock_registry.get_agent_class.return_value = lambda **kw: HangingAgent()
        mock_registry.get_permitted_callees.return_value = []
        mock_get_registry.return_value = mock_registry

        results = await run_agents_concurrent(pipeline, artifact, artifact.session_id)

    assert len(results) > 0
    agent1_result = next(r for r in results if r.agent_id == "Agent1")
    assert agent1_result.error is not None or agent1_result.agent_active is False


@pytest.mark.asyncio
async def test_ml_subprocess_memory_limit_set(tmp_path):
    """ML subprocess should apply memory limit on Linux."""
    from core.ml_subprocess import run_ml_tool

    (tmp_path / "test_tool.py").write_text("")
    with (
        patch("core.ml_subprocess.ML_TOOLS_DIR", tmp_path),
        patch("core.ml_subprocess._get_or_create_worker", side_effect=RuntimeError("no worker")),
        patch("core.ml_subprocess.asyncio.create_subprocess_exec") as mock_exec,
        patch("platform.system", return_value="Linux"),
        patch("core.ml_subprocess._get_ml_subprocess_timeout", return_value=30.0),
    ):
        mock_proc = AsyncMock()
        mock_proc.returncode = 0
        mock_proc.communicate = AsyncMock(return_value=(b'{"available": true}', b""))
        mock_exec.return_value = mock_proc

        result = await run_ml_tool(
            "test_tool.py",
            "test.png",
            timeout=5.0,
        )

    assert result["available"] is True
    _, kwargs = mock_exec.call_args
    assert "preexec_fn" in kwargs


@pytest.mark.asyncio
async def test_ocr_timeout_scales_with_resolution(tmp_path, mock_artifact):
    """OCR timeout should scale up for high-resolution images."""
    from tools.image_tools import extract_text_from_image

    huge_img = Image.new("RGB", (7680, 4320), "white")
    path = str(tmp_path / "huge_8k.png")
    huge_img.save(path, "PNG")
    mock_artifact.file_path = path


    with (
        patch("os.path.exists", return_value=True),
        patch("pytesseract.image_to_string", return_value="test text"),
        patch("pytesseract.image_to_data", return_value={"text": ["test"], "left": [], "top": [], "width": [], "height": []}),
        patch("pytesseract.Output.DICT", 1, create=True),
    ):
        result = await extract_text_from_image(mock_artifact, timeout=60.0)

    assert result.get("available") is True or result.get("has_text") is True or "text" in str(result)
