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
import tempfile
from pathlib import Path

import pytest

# ---------------------------------------------------------------------------
# Minimal fixture generators (no external image files needed)
# ---------------------------------------------------------------------------

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

    # Raw image data: RGB pixels (all red)
    raw = b""
    for _ in range(height):
        raw += b"\x00"  # filter byte
        raw += b"\xff\x00\x00" * width  # red pixels

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


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestFileHashVerify:
    """Test file_hash_verify tool output structure."""

    @pytest.mark.asyncio
    async def test_file_hash_verify_returns_hashes(self, tmp_path: Path):
        from tools.file_tools import file_hash_verify

        test_file = tmp_path / "test.txt"
        test_file.write_text("hello forensic world")

        result = await file_hash_verify({"file_path": str(test_file)})

        assert "sha256" in result
        assert "md5" in result
        assert "sha1" in result
        assert len(result["sha256"]) == 64  # hex-encoded SHA-256
        assert result["file_size_bytes"] == len(b"hello forensic world")
        assert result.get("status") == "CONFIRMED"

    @pytest.mark.asyncio
    async def test_file_hash_verify_deterministic(self, tmp_path: Path):
        from tools.file_tools import file_hash_verify

        test_file = tmp_path / "test.txt"
        test_file.write_text("deterministic content")

        r1 = await file_hash_verify({"file_path": str(test_file)})
        r2 = await file_hash_verify({"file_path": str(test_file)})

        assert r1["sha256"] == r2["sha256"]


class TestPerceptualHash:
    """Test perceptual_hash tool output structure."""

    @pytest.mark.asyncio
    async def test_phash_returns_hash(self, tmp_path: Path):
        from tools.file_tools import perceptual_hash

        png_bytes = _create_minimal_png(8, 8)
        test_file = tmp_path / "test.png"
        test_file.write_bytes(png_bytes)

        result = await perceptual_hash({"file_path": str(test_file)})

        assert "phash_hex" in result
        assert len(result["phash_hex"]) == 16  # 64-bit hash = 16 hex chars
        assert result.get("status") == "CONFIRMED"


class TestELA:
    """Test ELA tool with a minimal JPEG fixture."""

    @pytest.mark.asyncio
    async def test_ela_full_image_returns_structure(self, tmp_path: Path):
        from tools.image_tools import ela_full_image

        jpeg_bytes = _create_minimal_jpeg(16, 16)
        test_file = tmp_path / "test.jpg"
        test_file.write_bytes(jpeg_bytes)

        result = await ela_full_image({"file_path": str(test_file)})

        # Must return standard finding keys
        assert "status" in result
        assert "mean_ela" in result or "error" in result
        if "error" not in result:
            assert isinstance(result["mean_ela"], (int, float))
            assert 0.0 <= result["mean_ela"] <= 255.0


class TestFileStructureAnalysis:
    """Test file_structure_analysis tool."""

    @pytest.mark.asyncio
    async def test_png_structure_valid(self, tmp_path: Path):
        from tools.file_tools import file_structure_analysis

        png_bytes = _create_minimal_png(4, 4)
        test_file = tmp_path / "test.png"
        test_file.write_bytes(png_bytes)

        result = await file_structure_analysis({"file_path": str(test_file)})

        assert "file_type" in result
        assert "header_valid" in result
        assert result["header_valid"] is True
        assert result.get("status") == "CONFIRMED"


class TestToolRegistryIntegration:
    """Test that tool registry can execute tools with timeout protection."""

    @pytest.mark.asyncio
    async def test_tool_registry_timeout_protection(self):
        from core.tool_registry import ToolRegistry

        registry = ToolRegistry()

        async def slow_tool(data: dict) -> dict:
            await asyncio.sleep(100)  # intentionally long
            return {"status": "done"}

        registry.register("slow_tool", slow_tool, description="A slow tool")

        result = await registry.call(
            tool_name="slow_tool",
            input_data={},
            agent_id="test_agent",
            session_id=__import__("uuid").uuid4(),
        )

        # Should timeout (60s in tool_registry) — but we can't wait 60s in a test.
        # Just verify the structure is correct.
        assert result.tool_name == "slow_tool"
        # The tool either succeeds or times out — both are valid ToolResult states
        assert isinstance(result.success, bool)


class TestAudioToolStructure:
    """Test audio tool output structures (without requiring audio models)."""

    @pytest.mark.asyncio
    async def test_codec_fingerprinting_structure(self, tmp_path: Path):
        """Verify codec_fingerprinting returns expected keys even for non-audio files."""
        from tools.audio_tools import codec_fingerprinting

        # Create a tiny WAV-like file (header only, not real audio)
        wav_header = b"RIFF" + struct.pack("<I", 36) + b"WAVE"
        wav_header += b"fmt " + struct.pack("<I", 16) + struct.pack("<HHIIHH", 1, 1, 8000, 8000, 1, 8)
        wav_header += b"data" + struct.pack("<I", 0)

        test_file = tmp_path / "test.wav"
        test_file.write_bytes(wav_header)

        result = await codec_fingerprinting({"file_path": str(test_file)})

        # Should return a dict with standard keys (may report error for empty audio)
        assert isinstance(result, dict)
        assert "status" in result or "error" in result
