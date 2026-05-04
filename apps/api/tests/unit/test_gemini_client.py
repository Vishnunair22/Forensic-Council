import os
from unittest.mock import patch

import numpy as np
import pytest

from core.gemini_client import GeminiVisionClient, GeminiVisionFinding

os.environ.setdefault("APP_ENV", "testing")
os.environ.setdefault("SIGNING_KEY", "test-signing-key-" + "x" * 32)
os.environ.setdefault("POSTGRES_USER", "test")
os.environ.setdefault("POSTGRES_PASSWORD", "test")
os.environ.setdefault("POSTGRES_DB", "test")
os.environ.setdefault("REDIS_PASSWORD", "test")
os.environ.setdefault("DEMO_PASSWORD", "test")
os.environ.setdefault("LLM_PROVIDER", "none")
os.environ.setdefault("LLM_API_KEY", "test-key")
os.environ.setdefault("LLM_MODEL", "test-model")

from core.config import Settings


def _settings(**kwargs) -> Settings:
    base = {
        "app_env": "testing",
        "signing_key": "test-signing-key-" + "x" * 32,
        "postgres_user": "test",
        "postgres_password": "test",
        "postgres_db": "test",
        "redis_password": "test",
        "DEMO_PASSWORD": "test",
        "llm_provider": "none",
        "llm_api_key": None,
        "llm_model": "test-model",
        "gemini_api_key": None,
        "bootstrap_admin_password": "Admin_123!",
        "bootstrap_investigator_password": "Inv_123!",
    }
    base.update(kwargs)
    return Settings(**base)


def _make_client(**kwargs) -> GeminiVisionClient:
    return GeminiVisionClient(_settings(**kwargs))


class TestGeminiVisionClientInit:
    def test_init_no_key_disabled(self):
        client = _make_client()
        # No gemini_api_key set → _enabled is False
        assert client._enabled is False

    def test_init_with_placeholder_key_disabled(self):
        client = _make_client(gemini_api_key="your_gemini_key_here")
        assert client._enabled is False

    def test_init_with_real_key_enabled(self):
        client = _make_client(gemini_api_key="AIzaSyRealKey1234567890")
        assert client._enabled is True

    def test_fallback_chain_excludes_primary(self):
        client = _make_client(gemini_api_key="AIzaSyRealKey1234567890")
        assert client.model not in client.fallback_chain

    def test_circuit_breaker_created(self):
        client = _make_client()
        assert client._circuit_breaker is not None


class TestGeminiVisionFindingSchema:
    def test_to_finding_dict_structure(self):
        finding = GeminiVisionFinding(
            analysis_type="file_content_identification",
            model_used="gemini-2.5-flash",
            content_description="No manipulation detected.",
            confidence=0.85,
        )
        d = finding.to_finding_dict(agent_id="Agent1")
        assert d["agent_id"] == "Agent1"
        assert d["confidence_raw"] == 0.85
        assert "gemini_vision" in d["finding_type"]
        assert d["reasoning_summary"] == "No manipulation detected."
        assert "metadata" in d

    def test_to_finding_dict_confirmed_status_high_confidence(self):
        finding = GeminiVisionFinding(
            analysis_type="deep_forensic_analysis",
            model_used="gemini-2.5-flash",
            content_description="Artifacts detected.",
            confidence=0.75,
        )
        d = finding.to_finding_dict(agent_id="Agent1")
        assert d["status"] == "CONFIRMED"

    def test_to_finding_dict_incomplete_status_low_confidence(self):
        finding = GeminiVisionFinding(
            analysis_type="file_content_identification",
            model_used="gemini-2.5-flash",
            content_description="Inconclusive.",
            confidence=0.2,
        )
        d = finding.to_finding_dict(agent_id="Agent1")
        assert d["status"] == "INCOMPLETE"

    def test_manipulation_signals_in_metadata(self):
        finding = GeminiVisionFinding(
            analysis_type="file_content_identification",
            model_used="gemini-2.5-flash",
            content_description="Splicing detected.",
            manipulation_signals=["edge discontinuity", "frequency artifact"],
        )
        d = finding.to_finding_dict(agent_id="Agent1")
        assert "edge discontinuity" in d["metadata"]["manipulation_signals"]

    def test_detected_objects_in_metadata(self):
        finding = GeminiVisionFinding(
            analysis_type="object_weapon_detection",
            model_used="gemini-2.5-flash",
            content_description="Weapon detected.",
            detected_objects=["firearm"],
        )
        d = finding.to_finding_dict(agent_id="Agent3")
        assert "firearm" in d["metadata"]["detected_objects"]

    def test_caveat_present(self):
        finding = GeminiVisionFinding(
            analysis_type="file_content_identification",
            model_used="gemini-2.5-flash",
            content_description="Test.",
        )
        d = finding.to_finding_dict(agent_id="Agent1")
        assert "caveat" in d

    def test_court_defensible_present(self):
        finding = GeminiVisionFinding(
            analysis_type="file_content_identification",
            model_used="gemini-2.5-flash",
            content_description="Test.",
            court_defensible=False,
        )
        d = finding.to_finding_dict(agent_id="Agent1")
        assert d["court_defensible"] is False


class TestGeminiGenerateSpectrogram:
    @patch("soundfile.read")
    @patch("scipy.signal.spectrogram")
    def test_generate_spectrogram_returns_png_bytes(self, mock_spectrogram, mock_sf_read, tmp_path):
        test_file = tmp_path / "test.wav"
        test_file.write_bytes(b"RIFF" + b"\x00" * 36)

        sr = 22050
        mock_sf_read.return_value = (np.zeros(sr, dtype="float32"), sr)

        freqs = np.linspace(0, sr / 2, 64)
        times = np.linspace(0, 1.0, 50)
        spec = np.abs(np.random.randn(64, 50)).astype("float32") + 1e-6
        mock_spectrogram.return_value = (freqs, times, spec)

        data, mime = GeminiVisionClient._generate_spectrogram(str(test_file))

        assert mime == "image/png"
        assert isinstance(data, bytes)
        assert len(data) > 0
        mock_sf_read.assert_called_once_with(str(test_file), dtype="float32", always_2d=False)


class TestGeminiEncodeFile:
    def test_encode_image_returns_base64_and_mime(self, tmp_path):
        img_file = tmp_path / "test.jpg"
        img_file.write_bytes(
            b"\xff\xd8\xff\xe0\x00\x10JFIF\x00\x01\x01\x00\x00\x01\x00\x01\x00\x00\xff\xd9"
        )

        data, mime = GeminiVisionClient._encode_file(str(img_file))

        assert mime == "image/jpeg"
        assert isinstance(data, str)
        import base64

        decoded = base64.b64decode(data)
        assert len(decoded) > 0

    def test_encode_audio_routes_to_spectrogram(self, tmp_path):
        mp3_file = tmp_path / "test.mp3"
        mp3_file.write_bytes(b"ID3" + b"\x00" * 10)

        with patch.object(
            GeminiVisionClient, "_generate_spectrogram", return_value=(b"fake_png", "image/png")
        ) as mock_spec:
            data, mime = GeminiVisionClient._encode_file(str(mp3_file))

        assert mime == "image/png"
        import base64

        assert base64.b64decode(data) == b"fake_png"
        mock_spec.assert_called_once()

    def test_encode_nonexistent_file_raises(self):
        with pytest.raises(FileNotFoundError):
            GeminiVisionClient._encode_file("/nonexistent/path/file.jpg")


class TestGeminiDisabledGraceful:
    @pytest.mark.asyncio
    async def test_identify_file_content_disabled_returns_error_finding(self, tmp_path):
        """When Gemini is disabled, identify_file_content should return a finding with error set."""
        client = _make_client()  # no api key → disabled
        assert client._enabled is False

        img_file = tmp_path / "ev.jpg"
        img_file.write_bytes(b"\xff\xd8\xff\xd9")

        result = await client.identify_file_content(str(img_file))
        assert isinstance(result, GeminiVisionFinding)
        assert result.error is not None

    @pytest.mark.asyncio
    async def test_quota_pool_configure(self):
        GeminiVisionClient.configure_quota_pool(3)
        sem = GeminiVisionClient._get_quota_semaphore()
        assert sem is not None
