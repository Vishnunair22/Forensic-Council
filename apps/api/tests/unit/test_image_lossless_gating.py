"""
Image tool ↔ file-type gating tests
===================================

Locks the policy that JPEG-re-compression-dependent tools (the ELA family and
JPEG-ghost) are NOT_APPLICABLE on lossless image formats and only RUN on lossy
JPEG. This prevents an agent from running the wrong tool for a file type — e.g.
emitting a speculative ELA/ghost finding on a PNG/BMP/TIFF, which would
contradict neural_ela's NOT_APPLICABLE verdict on the same file.

The gate lives in the tool HANDLERS (downstream of task routing /
task_tool_overrides), so a task phrase can never bypass it.
"""

import os
from types import SimpleNamespace

import pytest
from PIL import Image

os.environ.setdefault("APP_ENV", "testing")
os.environ.setdefault("SIGNING_KEY", "test-signing-key-" + "x" * 32)
os.environ.setdefault("JWT_SECRET_KEY", "test-jwt-key-" + "x" * 32)
os.environ.setdefault("POSTGRES_USER", "test")
os.environ.setdefault("POSTGRES_PASSWORD", "test")
os.environ.setdefault("POSTGRES_DB", "test")


class _StubAgent:
    def __init__(self, file_path: str, mime_type: str):
        self.agent_id = "Agent1"
        self.session_id = "sess-test"
        self._tool_context: dict = {}
        self.evidence_artifact = SimpleNamespace(
            file_path=file_path, mime_type=mime_type, artifact_id="art-1"
        )

    async def _record_tool_result(self, name, result):
        self._tool_context[name] = result


def _make_image(tmp_path, name: str, fmt: str) -> str:
    path = os.path.join(str(tmp_path), name)
    img = Image.new("RGB", (8, 8), (123, 50, 200))
    img.save(path, fmt) if fmt != "JPEG" else img.save(path, "JPEG", quality=90)
    return path


def test_canonical_policy_set():
    from core.image_utils import JPEG_COMPRESSION_DEPENDENT_TOOLS

    assert JPEG_COMPRESSION_DEPENDENT_TOOLS == frozenset(
        {"neural_ela", "ela_full_image", "ela_anomaly_classify", "jpeg_ghost_detect"}
    )


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "handler_name",
    ["neural_ela_handler", "ela_full_image_handler", "ela_anomaly_classify_handler", "jpeg_ghost_detect_handler"],
)
async def test_jpeg_tools_not_applicable_on_lossless(tmp_path, handler_name):
    from core.handlers.image import ImageHandlers

    png = _make_image(tmp_path, "evidence.png", "PNG")
    agent = _StubAgent(png, "image/png")
    handler = ImageHandlers(agent)
    result = await getattr(handler, handler_name)({"artifact": agent.evidence_artifact})

    assert result.get("not_applicable") is True, f"{handler_name} must skip lossless PNG"
    assert result.get("status") == "NOT_APPLICABLE"


@pytest.mark.asyncio
async def test_jpeg_ghost_runs_on_lossy_jpeg(tmp_path):
    from core.handlers.image import ImageHandlers

    jpg = _make_image(tmp_path, "evidence.jpg", "JPEG")
    agent = _StubAgent(jpg, "image/jpeg")
    handler = ImageHandlers(agent)
    result = await handler.jpeg_ghost_detect_handler({"artifact": agent.evidence_artifact})

    # On a true lossy JPEG the tool is applicable — it must NOT be gated off.
    assert not result.get("not_applicable")
