"""
No-API Flow Integration Tests
==============================

Verifies that the Forensic Council pipeline produces meaningful findings
even when all LLM/API providers are unavailable (Gemini, Groq, CLIP).
Tests the deterministic tool chain, fallback tools, and finding quality.
"""

from __future__ import annotations

import os
import tempfile
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import numpy as np
import pytest
from PIL import Image

from core.evidence import ArtifactType, EvidenceArtifact
from core.react_loop import ReActLoopEngine


# ── Helpers ──────────────────────────────────────────────────────────────────

def _make_test_image(width: int = 640, height: int = 480) -> str:
    """Create a test PNG image and return its path."""
    tmp = tempfile.NamedTemporaryFile(suffix=".png", delete=False)
    arr = np.random.randint(0, 255, (height, width, 3), dtype=np.uint8)
    Image.fromarray(arr).save(tmp.name, "PNG")
    return tmp.name


def _make_test_jpeg() -> str:
    """Create a test JPEG image and return its path."""
    tmp = tempfile.NamedTemporaryFile(suffix=".jpg", delete=False)
    arr = np.random.randint(0, 255, (480, 640, 3), dtype=np.uint8)
    Image.fromarray(arr).save(tmp.name, "JPEG", quality=85)
    return tmp.name


@pytest.fixture
def test_image_png() -> str:
    path = _make_test_image()
    yield path
    if os.path.exists(path):
        os.unlink(path)


@pytest.fixture
def test_image_jpeg() -> str:
    path = _make_test_jpeg()
    yield path
    if os.path.exists(path):
        os.unlink(path)


@pytest.fixture
def mock_artifact(test_image_png: str) -> EvidenceArtifact:
    sid = uuid4()
    return EvidenceArtifact.create_root(
        artifact_type=ArtifactType.ORIGINAL,
        file_path=test_image_png,
        content_hash="abc123",
        action="upload",
        agent_id="Agent1",
        session_id=sid,
        metadata={"mime_type": "image/png", "original_filename": "test.png"},
    )


# ── Tests ────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_google_reverse_search_returns_on_device_fallback():
    """When Google search fails, on-device fallback returns a valid result."""
    from tools.google_search_tools import reverse_image_search

    path = _make_test_image()
    try:
        artifact = EvidenceArtifact.create_root(
            artifact_type=ArtifactType.ORIGINAL,
            file_path=path,
            content_hash="def456",
            action="upload",
            agent_id="test",
            session_id=uuid4(),
            metadata={"mime_type": "image/png"},
        )

        result = await reverse_image_search(artifact=artifact)
        assert result["status"] == "success"
        assert "matches" in result
        assert "method" in result
        assert "image_hash" in result
    finally:
        if os.path.exists(path):
            os.unlink(path)


@pytest.mark.asyncio
async def test_lens_multimodal_scan_returns_all_modalities():
    """Lens-style scan returns OCR, barcode, classification, logo modalities."""
    from tools.lens_style_tools import lens_style_multimodal_scan

    path = _make_test_image()
    try:
        artifact = EvidenceArtifact.create_root(
            artifact_type=ArtifactType.ORIGINAL,
            file_path=path,
            content_hash="ghi789",
            action="upload",
            agent_id="test",
            session_id=uuid4(),
            metadata={"mime_type": "image/png"},
        )

        result = await lens_style_multimodal_scan(artifact=artifact)
        assert result["status"] == "success"
        assert "ocr" in result
        assert "barcode" in result
        assert "visual_classification" in result
        assert "logo_detection" in result
        assert "completeness" in result
        assert 0 <= result["completeness"] <= 1
    finally:
        if os.path.exists(path):
            os.unlink(path)


@pytest.mark.asyncio
async def test_lens_ocr_modality_extracts_stats():
    """OCR modality returns word_count and mean_confidence."""
    from tools.lens_style_tools import lens_style_multimodal_scan

    path = _make_test_image()
    try:
        artifact = EvidenceArtifact.create_root(
            artifact_type=ArtifactType.ORIGINAL,
            file_path=path,
            content_hash="jkl012",
            action="upload",
            agent_id="test",
            session_id=uuid4(),
            metadata={"mime_type": "image/png"},
        )

        result = await lens_style_multimodal_scan(artifact=artifact)
        ocr = result["ocr"]
        assert ocr["status"] in ("success", "partial", "unavailable", "error")
        if ocr["status"] not in ("unavailable", "error"):
            assert "word_count" in ocr
            assert "mean_confidence" in ocr
    finally:
        if os.path.exists(path):
            os.unlink(path)


@pytest.mark.asyncio
async def test_reverse_search_fails_gracefully_on_missing_file():
    """Reverse search returns error status for missing file."""
    from tools.google_search_tools import reverse_image_search

    artifact = EvidenceArtifact.create_root(
        artifact_type=ArtifactType.ORIGINAL,
        file_path="/nonexistent/path.jpg",
        content_hash="mno345",
        action="upload",
        agent_id="test",
        session_id=uuid4(),
        metadata={"mime_type": "image/jpeg"},
    )

    result = await reverse_image_search(artifact=artifact)
    assert result["status"] == "error"
    assert "No local file path" in result.get("error", "")


@pytest.mark.asyncio
async def test_lens_scan_fails_gracefully_on_missing_file():
    """Lens scan returns error status for missing file."""
    from tools.lens_style_tools import lens_style_multimodal_scan

    artifact = EvidenceArtifact.create_root(
        artifact_type=ArtifactType.ORIGINAL,
        file_path="/nonexistent/path.jpg",
        content_hash="pqr678",
        action="upload",
        agent_id="test",
        session_id=uuid4(),
        metadata={"mime_type": "image/jpeg"},
    )

    result = await lens_style_multimodal_scan(artifact=artifact)
    assert result["status"] == "error"


def test_detailed_reasoning_ela():
    """_build_detailed_reasoning produces rich ELA-specific summary."""
    output = {
        "num_anomaly_regions": 12,
        "threshold_used": 0.15,
        "max_ela_value": 45.2,
    }
    result = ReActLoopEngine._build_detailed_reasoning("ela_full_image", output)
    assert "12 anomaly regions" in result
    assert "threshold" in result
    assert "45.2" in result


def test_detailed_reasoning_yolo():
    """_build_detailed_reasoning produces rich YOLO-specific summary."""
    output = {
        "detections": [
            {"class": "person", "confidence": 0.95},
            {"class": "car", "confidence": 0.88},
            {"class": "person", "confidence": 0.76},
        ]
    }
    result = ReActLoopEngine._build_detailed_reasoning("object_detection", output)
    assert "3 objects" in result
    assert "person" in result
    assert "car" in result


def test_detailed_reasoning_prnu():
    """_build_detailed_reasoning produces rich PRNU-specific summary."""
    output = {
        "noise_consistency_score": 0.873,
        "blocks_analyzed": 48,
        "verdict": "consistent",
    }
    result = ReActLoopEngine._build_detailed_reasoning("noise_fingerprint", output)
    assert "0.873" in result
    assert "48" in result


def test_detailed_reasoning_unknown_tool_returns_fallback():
    """_build_detailed_reasoning returns empty for unrecognized tools."""
    result = ReActLoopEngine._build_detailed_reasoning("some_unknown_tool", {"score": 0.5})
    assert isinstance(result, str)


@pytest.mark.asyncio
async def test_quota_manager_wait_for_slot_respects_rate_limit():
    """wait_for_slot blocks until a slot is available within rate limits."""
    from core.quota_manager import get_quota_manager

    manager = get_quota_manager(provider="test_provider", rpm_limit=60, rpd_limit=1000)
    ok = await manager.wait_for_slot(priority="low", timeout=5.0)
    assert ok is True, "wait_for_slot should succeed with no prior calls"


@pytest.mark.asyncio
async def test_quota_manager_track_and_wait():
    """track_call followed by wait_for_slot with RPM limit works."""
    from core.quota_manager import get_quota_manager

    manager = get_quota_manager(provider="test_provider", rpm_limit=60, rpd_limit=1000)
    await manager.wait_for_slot(priority="low", timeout=5.0)
    await manager.record_call(priority="low")


def test_build_readable_summary_with_detailed_reasoning():
    """_build_readable_summary uses detailed reasoning when available."""
    from core.react_loop import ReActLoopEngine
    from core.tool_registry import ToolResult

    engine = ReActLoopEngine(
        agent_id="Agent1",
        session_id=uuid4(),
        iteration_ceiling=10,
        working_memory=MagicMock(),
        custody_logger=MagicMock(),
        redis_client=None,
    )
    output = {
        "num_anomaly_regions": 7,
        "threshold_used": 0.2,
        "max_ela_value": 32.1,
    }
    tool_result = ToolResult(
        tool_name="ela_full_image",
        success=True,
        output=output,
    )
    summary = engine._build_readable_summary(
        tool_name="ela_full_image",
        task_description="ELA analysis",
        tool_result=tool_result,
        confidence=0.9,
        status="COMPLETE",
        evidence_verdict="POSITIVE",
    )
    assert "7" in summary
    assert "32.1" in summary


def test_telemetry_tool_recording():
    """Telemetry collector tracks tool execution correctly."""
    from core.telemetry import get_telemetry

    telemetry = get_telemetry()
    telemetry.record_tool_execution(
        tool_name="ela_full_image",
        agent_id="Agent1",
        success=True,
        duration_ms=150.0,
    )
    stats = telemetry.get_tool_stats()
    assert stats["total_tool_calls"] >= 1
    assert "ela_full_image" in stats["tool_call_counts"]


def test_telemetry_finding_quality():
    """Telemetry collector tracks finding quality metrics."""
    from core.telemetry import get_telemetry

    telemetry = get_telemetry()
    telemetry.record_finding_quality(
        agent_id="Agent1",
        tool_count=5,
        positive_findings=2,
        negative_findings=1,
        inconclusive_findings=1,
        error_findings=1,
        total_findings=5,
        avg_confidence=0.78,
    )
    summary = telemetry.get_finding_quality_summary()
    assert summary["total_quality_records"] >= 1


def test_telemetry_provider_recording():
    """Telemetry collector tracks provider usage correctly."""
    from core.telemetry import get_telemetry

    telemetry = get_telemetry()
    telemetry.record_provider_usage(
        provider="gemini",
        model="gemini-2.0-flash",
        tokens_in=100,
        tokens_out=50,
        duration_ms=2000.0,
        success=True,
    )
    stats = telemetry.get_provider_stats()
    assert stats["total_provider_calls"] >= 1
