import io
import json
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import httpx
import pytest

from core.config import Settings
from core.gemini_client import GeminiVisionFinding
from core.vision_router import VisionRouter


def _create_minimal_jpeg() -> bytes:
    """Create a minimal valid JPEG file in memory."""
    from PIL import Image
    buf = io.BytesIO()
    img = Image.new("RGB", (8, 8), color=(128, 128, 128))
    img.save(buf, format="JPEG", quality=85)
    return buf.getvalue()


@pytest.mark.asyncio
async def test_cascade_gemini_success(tmp_path: Path):
    """Test that when Gemini succeeds, the router returns it immediately."""
    test_image = tmp_path / "test.jpg"
    test_image.write_bytes(_create_minimal_jpeg())

    settings = Settings()
    # Force Gemini to be configured and at the front
    settings.vision_provider_chain = "gemini,groq_vision,local_ensemble"
    
    mock_finding = GeminiVisionFinding(
        analysis_type="deep_forensic_analysis",
        model_used="gemini-2.5-flash",
        content_description="Gemini direct success",
        confidence=0.9,
        court_defensible=True,
    )

    router = VisionRouter(settings)

    with patch.object(
        router.gemini_client, "deep_forensic_analysis", new_callable=AsyncMock
    ) as mock_deep:
        # Gemini succeeds
        mock_deep.return_value = mock_finding

        res = await router.deep_forensic_analysis(str(test_image))
        
        assert res.model_used == "gemini-2.5-flash"
        assert res.content_description == "Gemini direct success"
        mock_deep.assert_called_once()


@pytest.mark.asyncio
async def test_cascade_gemini_fail_groq_success(tmp_path: Path):
    """Test that when Gemini fails, the cascade routes to Groq Vision."""
    test_image = tmp_path / "test.jpg"
    test_image.write_bytes(_create_minimal_jpeg())

    settings = Settings()
    settings.vision_provider_chain = "gemini,groq_vision,local_ensemble"
    settings.groq_vision_api_key = "mock_groq_api_key_123"
    settings.groq_vision_model = "mock-groq-model"

    router = VisionRouter(settings)

    # Mock Gemini to fail (raise exception)
    with patch.object(
        router.gemini_client, "deep_forensic_analysis", new_callable=AsyncMock
    ) as mock_gemini:
        mock_gemini.side_effect = Exception("Gemini API key expired")

        # Mock Groq http call
        groq_json_response = {
            "choices": [
                {
                    "message": {
                        "content": json.dumps({
                            "content_type": "high-res-photo",
                            "scene_description": "Groq vision success",
                            "extracted_text": [],
                            "detected_objects": ["person"],
                            "authenticity_verdict": "AUTHENTIC",
                            "confidence": 0.85
                        })
                    }
                }
            ]
        }

        mock_response = MagicMock(spec=httpx.Response)
        mock_response.status_code = 200
        mock_response.json.return_value = groq_json_response

        # We also mock check_and_record to bypass quota guard blocks in tests
        with patch("core.provider_quota_guard.ProviderQuotaGuard.check_and_record", new_callable=AsyncMock) as mock_quota:
            mock_quota.return_value = (True, MagicMock(allowed=True))

            with patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mock_post:
                mock_post.return_value = mock_response

                res = await router.deep_forensic_analysis(str(test_image))

                assert res.model_used == "mock-groq-model"
                assert res.content_description == "Groq vision success"
                assert res._authenticity_verdict == "AUTHENTIC"
                mock_gemini.assert_called_once()
                mock_post.assert_called_once()


@pytest.mark.asyncio
async def test_cascade_all_fail_local_success(tmp_path: Path):
    """Test that when all cloud providers fail or are unconfigured, local ensemble is run."""
    test_image = tmp_path / "test.jpg"
    test_image.write_bytes(_create_minimal_jpeg())

    settings = Settings()
    # Explicitly configure cascade to try all cloud services before fallback
    settings.vision_provider_chain = "gemini,groq_vision,openrouter,local_ensemble"
    settings.groq_vision_api_key = "mock_groq_key"
    settings.openrouter_enabled = True
    settings.openrouter_api_key = "mock_openrouter_key"
    settings.openrouter_vision_models = "mock-openrouter-model"

    router = VisionRouter(settings)

    # Mock all API attempts to fail
    with patch.object(router.gemini_client, "deep_forensic_analysis", new_callable=AsyncMock) as mock_gemini, \
         patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mock_post:
        
        mock_gemini.side_effect = Exception("Gemini error")
        
        # httpx calls return 500 for Groq and OpenRouter
        mock_error_resp = MagicMock(spec=httpx.Response)
        mock_error_resp.status_code = 500
        mock_error_resp.text = "Internal Server Error"
        mock_post.return_value = mock_error_resp

        # Mock Quota guard to pass
        with patch("core.provider_quota_guard.ProviderQuotaGuard.check_and_record", new_callable=AsyncMock) as mock_quota:
            mock_quota.return_value = (True, MagicMock(allowed=True))

            # Mock local ensemble output to verify call occurred
            local_mock_finding = GeminiVisionFinding(
                analysis_type="deep_forensic_analysis",
                model_used="local_opencv_fallback",
                content_description="Local fallback triggered successfully",
                confidence=0.5,
                court_defensible=True,
            )

            with patch("core.vision_router.analyze_local_ensemble", new_callable=AsyncMock) as mock_local:
                mock_local.return_value = local_mock_finding

                res = await router.deep_forensic_analysis(str(test_image))

                assert res.model_used == "local_opencv_fallback"
                assert res.content_description == "Local fallback triggered successfully"
                mock_gemini.assert_called_once()
                mock_local.assert_called_once()


@pytest.fixture
def test_client():
    from fastapi.testclient import TestClient
    from api.main import app
    from unittest.mock import AsyncMock, patch

    mock_redis = AsyncMock()
    mock_redis.ping = AsyncMock(return_value=True)
    mock_pg = AsyncMock()
    mock_pg.ping = AsyncMock(return_value=True)
    mock_qdrant = AsyncMock()
    mock_qdrant.ping = AsyncMock(return_value=True)

    async def mock_get_redis(*args, **kwargs): return mock_redis
    async def mock_get_pg(*args, **kwargs): return mock_pg
    async def mock_get_qdrant(*args, **kwargs): return mock_qdrant
    async def mock_noop(*args, **kwargs): return False

    patches = [
        patch("core.persistence.redis_client.get_redis_client", new=mock_get_redis),
        patch("core.persistence.postgres_client.get_postgres_client", new=mock_get_pg),
        patch("core.persistence.qdrant_client.get_qdrant_client", new=mock_get_qdrant),
        patch("core.dev_seed.run_migrations", new=mock_noop),
        patch("scripts.init_db.bootstrap_users", new=mock_noop),
    ]

    for p in patches:
        p.start()
    try:
        with TestClient(app) as c:
            yield c
    finally:
        for p in patches:
            p.stop()


def test_health_providers_endpoint(test_client):
    """Test that GET /api/v1/health/providers returns 200 and the expected structure."""
    r = test_client.get("/api/v1/health/providers")
    assert r.status_code == 200
    data = r.json()
    assert data["status"] == "healthy"
    assert "vision_provider_chain" in data
    assert "text_provider_chain" in data
    assert "providers" in data
    assert "gemini" in data["providers"]
    assert "groq_vision" in data["providers"]
    assert "openrouter" in data["providers"]
    assert "local_ensemble" in data["providers"]
