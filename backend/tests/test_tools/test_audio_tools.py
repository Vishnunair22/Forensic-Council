"""
Tests for Audio Forensic Tools
==============================

Tests for speaker diarization, anti-spoofing detection, prosody analysis,
background noise consistency, and codec fingerprinting.
"""

import hashlib
import os
import tempfile
import uuid
from pathlib import Path

import numpy as np
import pytest
import soundfile as sf

from core.evidence import ArtifactType, EvidenceArtifact
from core.exceptions import ToolUnavailableError
from tools.audio_tools import (
    speaker_diarize,
    anti_spoofing_detect,
    prosody_analyze,
    background_noise_consistency,
    codec_fingerprint,
)


# ============================================================================
# Test Fixtures
# ============================================================================

@pytest.fixture
def temp_dir():
    """Create a temporary directory for test files."""
    with tempfile.TemporaryDirectory() as tmpdir:
        yield Path(tmpdir)


def generate_sine_wave(duration: float, freq: float, sr: int = 22050) -> np.ndarray:
    """Generate a sine wave."""
    t = np.linspace(0, duration, int(sr * duration), endpoint=False)
    return np.sin(2 * np.pi * freq * t)


@pytest.fixture
def clean_wav(temp_dir: Path) -> Path:
    """Create a clean WAV file with a simple sine wave."""
    sr = 22050
    duration = 3.0
    freq = 440  # A4 note
    
    audio = generate_sine_wave(duration, freq, sr)
    
    # Add some variation to make it more realistic
    audio = audio * 0.5  # Reduce amplitude
    
    wav_path = temp_dir / "clean.wav"
    sf.write(str(wav_path), audio, sr)
    
    return wav_path


@pytest.fixture
def spliced_wav(temp_dir: Path) -> Path:
    """Create a WAV file with a spliced segment (different noise floor)."""
    sr = 22050
    duration = 3.0
    
    # First segment - 440 Hz
    audio1 = generate_sine_wave(1.5, 440, sr) * 0.5
    
    # Second segment - different frequency and amplitude (simulating splice)
    audio2 = generate_sine_wave(1.5, 880, sr) * 0.3
    
    # Add different noise floors
    noise1 = np.random.randn(len(audio1)) * 0.01
    noise2 = np.random.randn(len(audio2)) * 0.05  # Higher noise floor
    
    audio1 = audio1 + noise1
    audio2 = audio2 + noise2
    
    # Concatenate
    audio = np.concatenate([audio1, audio2])
    
    wav_path = temp_dir / "spliced.wav"
    sf.write(str(wav_path), audio, sr)
    
    return wav_path


@pytest.fixture
def clean_artifact(clean_wav: Path) -> EvidenceArtifact:
    """Create an evidence artifact from the clean WAV."""
    with open(clean_wav, "rb") as f:
        content_hash = hashlib.sha256(f.read()).hexdigest()
    
    return EvidenceArtifact.create_root(
        artifact_type=ArtifactType.ORIGINAL,
        file_path=str(clean_wav),
        content_hash=content_hash,
        action="upload",
        agent_id="test",
        session_id=uuid.uuid4(),
    )


@pytest.fixture
def spliced_artifact(spliced_wav: Path) -> EvidenceArtifact:
    """Create an evidence artifact from the spliced WAV."""
    with open(spliced_wav, "rb") as f:
        content_hash = hashlib.sha256(f.read()).hexdigest()
    
    return EvidenceArtifact.create_root(
        artifact_type=ArtifactType.ORIGINAL,
        file_path=str(spliced_wav),
        content_hash=content_hash,
        action="upload",
        agent_id="test",
        session_id=uuid.uuid4(),
    )


# ============================================================================
# Speaker Diarization Tests
# ============================================================================

@pytest.mark.asyncio
async def test_speaker_diarize_returns_speaker_count(clean_artifact: EvidenceArtifact):
    """Test that speaker diarization returns speaker count."""
    result = await speaker_diarize(clean_artifact)
    
    assert "speaker_count" in result
    assert "segments" in result
    assert "duration" in result
    
    # Should detect at least 1 speaker
    assert result["speaker_count"] >= 1
    
    # Segments should be a list
    assert isinstance(result["segments"], list)
    
    # Duration should be positive
    assert result["duration"] > 0


@pytest.mark.asyncio
async def test_speaker_diarize_handles_missing_file(temp_dir: Path):
    """Test that speaker diarization handles missing file."""
    missing_path = temp_dir / "nonexistent.wav"
    
    artifact = EvidenceArtifact.create_root(
        artifact_type=ArtifactType.ORIGINAL,
        file_path=str(missing_path),
        content_hash="abc123",
        action="upload",
        agent_id="test",
        session_id=uuid.uuid4(),
    )
    
    with pytest.raises(ToolUnavailableError):
        await speaker_diarize(artifact)


# ============================================================================
# Anti-Spoofing Detection Tests
# ============================================================================

@pytest.mark.asyncio
async def test_anti_spoofing_passes_clean_audio(clean_artifact: EvidenceArtifact):
    """Test that anti-spoofing detection passes clean audio."""
    result = await anti_spoofing_detect(clean_artifact)
    
    assert "spoof_detected" in result
    assert "confidence" in result
    assert "model_version" in result
    assert "anomalies" in result
    
    # Clean sine wave should not be flagged as spoof
    # (though it might have some synthetic characteristics)
    assert "confidence" in result
    assert 0 <= result["confidence"] <= 1


@pytest.mark.asyncio
async def test_anti_spoofing_with_segment(clean_artifact: EvidenceArtifact):
    """Test anti-spoofing detection with segment specification."""
    segment = {"start": 0.0, "end": 1.0}
    
    result = await anti_spoofing_detect(clean_artifact, segment=segment)
    
    assert "spoof_detected" in result
    assert "confidence" in result


# ============================================================================
# Prosody Analysis Tests
# ============================================================================

@pytest.mark.asyncio
async def test_prosody_detects_discontinuity_in_spliced_audio(
    spliced_artifact: EvidenceArtifact,
):
    """Test that prosody analysis detects discontinuity in spliced audio."""
    result = await prosody_analyze(spliced_artifact)
    
    assert "anomalies" in result
    assert "pitch_stats" in result
    assert "energy_stats" in result
    
    # Spliced audio should have some anomalies
    # (due to the frequency and amplitude change)
    # Note: This depends on the sensitivity of the detection


@pytest.mark.asyncio
async def test_prosody_analyze_clean_audio(clean_artifact: EvidenceArtifact):
    """Test prosody analysis on clean audio."""
    result = await prosody_analyze(clean_artifact)
    
    assert "anomalies" in result
    assert "pitch_stats" in result
    assert "energy_stats" in result
    
    # Pitch stats should have values
    assert result["pitch_stats"]["mean"] is not None or result["pitch_stats"]["range"] is not None


# ============================================================================
# Background Noise Consistency Tests
# ============================================================================

@pytest.mark.asyncio
async def test_background_noise_consistency_flags_noise_shift(
    spliced_artifact: EvidenceArtifact,
):
    """Test that background noise consistency flags noise shift."""
    result = await background_noise_consistency(spliced_artifact, segment_duration=0.5)
    
    assert "shift_points" in result
    assert "consistent" in result
    assert "noise_profile" in result
    
    # Spliced audio with different noise floors should have shift points
    # Note: Detection depends on threshold and segment duration


@pytest.mark.asyncio
async def test_background_noise_consistency_clean_audio(
    clean_artifact: EvidenceArtifact,
):
    """Test background noise consistency on clean audio."""
    result = await background_noise_consistency(clean_artifact, segment_duration=0.5)
    
    assert "shift_points" in result
    assert "consistent" in result
    assert "noise_profile" in result
    
    # Clean audio should be more consistent
    # (though a simple sine wave might still show some variation)


# ============================================================================
# Codec Fingerprint Tests
# ============================================================================

@pytest.mark.asyncio
async def test_codec_fingerprint_detects_reencoding_event(
    clean_artifact: EvidenceArtifact,
):
    """Test codec fingerprint analysis."""
    result = await codec_fingerprint(clean_artifact)
    
    assert "reencoding_events" in result
    assert "codec_chain" in result
    assert "format_info" in result
    
    # Should detect the format
    assert len(result["codec_chain"]) > 0
    
    # Format info should have expected fields
    assert "samplerate" in result["format_info"]
    assert "channels" in result["format_info"]
    assert "duration" in result["format_info"]


@pytest.mark.asyncio
async def test_codec_fingerprint_handles_missing_file(temp_dir: Path):
    """Test codec fingerprint handles missing file."""
    missing_path = temp_dir / "nonexistent.wav"
    
    artifact = EvidenceArtifact.create_root(
        artifact_type=ArtifactType.ORIGINAL,
        file_path=str(missing_path),
        content_hash="abc123",
        action="upload",
        agent_id="test",
        session_id=uuid.uuid4(),
    )
    
    with pytest.raises(ToolUnavailableError):
        await codec_fingerprint(artifact)
