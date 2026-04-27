import pytest
from unittest.mock import AsyncMock, MagicMock, patch
import sys

# Mock heavy modules before they are imported by api.routes.investigation
mock_pipeline_mod = MagicMock()
sys.modules["orchestration.pipeline"] = mock_pipeline_mod
mock_runner_mod = MagicMock()
sys.modules["orchestration.investigation_runner"] = mock_runner_mod

from fastapi import HTTPException
from fastapi.responses import JSONResponse
import hashlib
from uuid import uuid4

@pytest.mark.asyncio
async def test_get_session_report_in_progress_202():
    """Fix 4: Test that get_session_report returns 202 if report is not ready."""
    mock_persistence = AsyncMock()
    mock_persistence.get_report.return_value = {"status": "running"}
    
    with patch("api.routes.sessions.get_active_pipeline", return_value=None), \
         patch("api.routes.sessions._final_reports", {}), \
         patch("core.session_persistence.get_session_persistence", return_value=mock_persistence):
        
        from api.routes.sessions import get_session_report
        response = await get_session_report("test-session", current_user=MagicMock())
        
        assert isinstance(response, JSONResponse)
        assert response.status_code == 202
        import json
        content = json.loads(response.body)
        assert content["status"] == "in_progress"

@pytest.mark.asyncio
async def test_rate_limit_bearer_stripping():
    """Fix 9: Test that rate limiter strips 'Bearer ' prefix for consistent hashing."""
    mock_redis = AsyncMock()
    mock_redis.eval.return_value = [1, 60] 
    
    with patch("core.persistence.redis_client.get_redis_client", return_value=mock_redis):
        from api.main import rate_limit_middleware
        
        async def mock_call_next(request):
            return MagicMock()
            
        request1 = MagicMock()
        request1.url.path = "/api/v1/test"
        request1.method = "GET"
        request1.headers = {"Authorization": "Bearer mytoken"}
        request1.cookies = {}
        
        await rate_limit_middleware(request1, mock_call_next)
        
        request2 = MagicMock()
        request2.url.path = "/api/v1/test"
        request2.method = "GET"
        request2.headers = {"Authorization": "mytoken"}
        request2.cookies = {}
        
        await rate_limit_middleware(request2, mock_call_next)
        
        keys = [call.kwargs['keys'][0] for call in mock_redis.eval.call_args_list]
        assert keys[0] == keys[1]
        assert "tok:" in keys[0]

@pytest.mark.asyncio
async def test_mime_before_dedup():
    """Fix 7: Test that MIME validation happens before Redis dedup check."""
    mock_file = AsyncMock()
    mock_file.filename = "test.jpg"
    mock_file.content_type = "image/jpeg"
    mock_file.size = 100
    mock_file.read.return_value = b"fake-header"
    
    mock_redis = AsyncMock()
    mock_settings = MagicMock()
    mock_settings.use_redis_worker = True
    
    with patch("core.persistence.redis_client.get_redis_client", return_value=mock_redis), \
         patch("api.routes.investigation.asyncio.to_thread", return_value="text/plain") as mock_thread, \
         patch("api.routes.investigation.settings", mock_settings), \
         patch("api.routes.investigation.Path.mkdir"), \
         patch("api.routes.investigation.open", MagicMock()):
        
        from api.routes.investigation import start_investigation
        
        with pytest.raises(HTTPException) as exc:
            await start_investigation(
                file=mock_file,
                case_id="case1",
                investigator_id="inv1",
                current_user=MagicMock(user_id="u1", role=MagicMock(value="investigator"))
            )
        
        assert exc.value.status_code == 400
        assert "Security violation" in exc.value.detail
        assert mock_redis.set.called is False
        assert mock_thread.called is True
