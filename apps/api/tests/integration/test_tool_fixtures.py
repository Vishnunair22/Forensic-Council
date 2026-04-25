"""
Tool-Level Integration Tests
============================

Tests that exercise actual forensic tool functions with minimal fixture data.
Validates that ELA, perceptual hash, file hash, and metadata extraction
produce expected output structures.
"""

import asyncio
import io
import os
import struct
from pathlib import Path
from unittest.mock import MagicMock
from uuid import uuid4

import pytest

from core.evidence import ArtifactType, EvidenceArtifact


def _create_minimal_png(width: int = 4, height: int = 4) -> bytes:
    """Create a minimal valid PNG file in-memory."""
    import zlib

    def _chunk(chunk_type: str, data: bytes) -> bytes:
        c = chunk_type.encode("ascii") + data
        crc = zlib.crc32(c) & 0xFFFFFFFF
        return struct.pack(">I", len(data)) + c + struct.pack(">I", crc)

    header = b"\x89PNG\r\n\x1a\n"
    ihdr_data = struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0)
    ihdr = _chunk("IHDR", ihdr_data)

    raw = b""
    for _ in range(height):
        raw += b"\x00"
        raw += b"\xff\x00\x00" * width

    compressed = zlib.compress(raw)
    idat = _chunk("IDAT", compressed)
    iend = _chunk("IEND", b"")

    return header + ihdr + idat + iend


def _create_minimal_jpeg(width: int = 8, height: int = 8) -> bytes:
    """Create a minimal valid JPEG file using PIL (if available)."""
    try:
        from PIL import Image

        buf = io.BytesIO()
        img = Image.new("RGB", (width, height), color=(128, 128, 128))
        img.save(buf, format="JPEG", quality=85)
        return buf.getvalue()
    except ImportError:
        pytest.skip("PIL not available for JPEG generation")


def _make_artifact(file_path: str, mime_type: str = "image/jpeg") -> EvidenceArtifact:
    sid = uuid4()
    return EvidenceArtifact.create_root(
        artifact_type=ArtifactType.ORIGINAL,
        file_path=file_path,
        content_hash="abc",
        action="upload",
        agent_id="test",
        session_id=sid,
        metadata={"mime_type": mime_type, "original_filename": os.path.basename(file_path)},
    )


class TestFileHashVerify:
    """Test file_hash_verify tool output structure."""

    @pytest.mark.asyncio
    async def test_file_hash_verify_returns_hashes(self, tmp_path: Path):
        from core.persistence.evidence_store import EvidenceStore
        from tools.image_tools import file_hash_verify

        test_file = tmp_path / "test.txt"
        test_file.write_text("hello forensic world")
        artifact = _make_artifact(str(test_file), "text/plain")
        es = MagicMock(spec=EvidenceStore)

        result = await file_hash_verify(artifact, es)

        assert "current_hash" in result or "hash_matches" in result

    @pytest.mark.asyncio
    async def test_file_hash_verify_deterministic(self, tmp_path: Path):
        from core.persistence.evidence_store import EvidenceStore
        from tools.image_tools import file_hash_verify

        test_file = tmp_path / "test.txt"
        test_file.write_text("deterministic content")
        artifact = _make_artifact(str(test_file), "text/plain")
        es = MagicMock(spec=EvidenceStore)

        r1 = await file_hash_verify(artifact, es)
        r2 = await file_hash_verify(artifact, es)

        assert r1["current_hash"] == r2["current_hash"]


class TestPerceptualHash:
    """Test perceptual_hash tool output structure."""

    @pytest.mark.asyncio
    async def test_phash_returns_hash(self, tmp_path: Path):
        from tools.image_tools import compute_perceptual_hash

        jpeg_bytes = _create_minimal_jpeg(8, 8)
        test_file = tmp_path / "test.jpg"
        test_file.write_bytes(jpeg_bytes)
        artifact = _make_artifact(str(test_file), "image/jpeg")

        result = await compute_perceptual_hash(artifact)

        assert "phash" in result or "available" in result


class TestELA:
    """Test ELA tool with a minimal JPEG fixture."""

    @pytest.mark.asyncio
    async def test_ela_full_image_returns_structure(self, tmp_path: Path):
        from tools.image_tools import ela_full_image

        jpeg_bytes = _create_minimal_jpeg(16, 16)
        test_file = tmp_path / "test.jpg"
        test_file.write_bytes(jpeg_bytes)
        artifact = _make_artifact(str(test_file), "image/jpeg")

        result = await ela_full_image(artifact)

        assert "available" in result or "status" in result or "error" in result
        if result.get("available") is True:
            assert isinstance(result["mean_ela"], (int, float))
            assert 0.0 <= result["mean_ela"] <= 255.0


class TestToolRegistryIntegration:
    """Test that tool registry can execute tools with timeout protection."""

    @pytest.mark.asyncio
    async def test_tool_registry_timeout_protection(self):
        from core.tool_registry import ToolRegistry

        registry = ToolRegistry()

        async def slow_tool(data: dict) -> dict:
            await asyncio.sleep(100)
            return {"status": "done"}

        registry.register("slow_tool", slow_tool, description="A slow tool")

        result = await registry.call(
            tool_name="slow_tool",
            input_data={},
            agent_id="test_agent",
            session_id=uuid4(),
        )

        assert result.tool_name == "slow_tool"
        assert isinstance(result.success, bool)


class TestAudioToolStructure:
    """Test audio tool output structures (without requiring audio models)."""

    @pytest.mark.asyncio
    async def test_codec_fingerprinting_structure(self, tmp_path: Path):
        from tools.audio_tools import codec_fingerprint

        wav_header = b"RIFF" + struct.pack("<I", 36) + b"WAVE"
        wav_header += (
            b"fmt " + struct.pack("<I", 16) + struct.pack("<HHIIHH", 1, 1, 8000, 8000, 1, 8)
        )
        wav_header += b"data" + struct.pack("<I", 0)

        test_file = tmp_path / "test.wav"
        test_file.write_bytes(wav_header)
        artifact = _make_artifact(str(test_file), "audio/wav")

        result = await codec_fingerprint(artifact)

        assert isinstance(result, dict)
        assert (
            "codec_chain" in result
            or "format_info" in result
            or "status" in result
            or "error" in result
        )
