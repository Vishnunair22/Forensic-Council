"""
HITL Routes Unit Tests
=====================
"""

from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest
from fastapi import HTTPException

from api.schemas import HITLDecisionRequest


class TestSubmitDecision:
    """Tests for the submit_decision endpoint."""

    @pytest.fixture
    def hitl_request(self):
        return HITLDecisionRequest(
            session_id=str(uuid4()),
            checkpoint_id=str(uuid4()),
            agent_id="gemini-vision",
            decision="APPROVE",
            note="Looks authentic",
        )

    @pytest.fixture
    def mock_user(self):
        user = MagicMock()
        user.user_id = "user-123"
        return user

    @pytest.mark.asyncio
    async def test_successful_decision(self, hitl_request, mock_user):
        """Test successful decision submission."""
        pipeline = MagicMock()
        pipeline.handle_hitl_decision = AsyncMock()

        with (
            patch("core.persistence.redis_client.get_redis_client") as mock_redis,
            patch("api.routes._session_state.get_active_pipeline") as mock_get_pipeline,
        ):
            mock_get_pipeline.return_value = pipeline
            mockRedis = MagicMock()
            mockRedis.get = AsyncMock(return_value=None)
            mockRedis.set = AsyncMock()
            mock_redis.return_value = mockRedis

            from api.routes import hitl

            result = await hitl.submit_decision(hitl_request, mock_user)

            assert result["status"] == "processed"
            pipeline.handle_hitl_decision.assert_called_once()

    @pytest.mark.asyncio
    async def test_no_active_pipeline_raises_404(self, hitl_request, mock_user):
        """Test 404 raised when no active pipeline."""
        with (
            patch("core.persistence.redis_client.get_redis_client") as mock_redis,
            patch("api.routes._session_state.get_active_pipeline") as mock_get_pipeline,
        ):
            mock_get_pipeline.return_value = None
            mock_redis.return_value = None

            from api.routes import hitl

            try:
                await hitl.submit_decision(hitl_request, mock_user)
            except HTTPException as e:
                assert e.status_code == 404
            except Exception as e:
                pytest.fail(f"Expected HTTPException 404 but got {type(e).__name__}: {e}")

    @pytest.mark.asyncio
    async def test_redis_idempotency_check_returns_already_processed(self, hitl_request, mock_user):
        """Test idempotent duplicate decisions return early."""
        pipeline = MagicMock()

        with (
            patch("core.persistence.redis_client.get_redis_client") as mock_redis,
            patch("api.routes._session_state.get_active_pipeline") as mock_get_pipeline,
        ):
            mock_get_pipeline.return_value = pipeline
            mockRedis = MagicMock()
            mockRedis.get = AsyncMock(return_value="1")  # Already processed
            mockRedis.set = AsyncMock()
            mock_redis.return_value = mockRedis

            from api.routes import hitl

            result = await hitl.submit_decision(hitl_request, mock_user)

            assert result["status"] == "already_processed"
            pipeline.handle_hitl_decision.assert_not_called()

    @pytest.mark.asyncio
    async def test_handler_exception_raises_500(self, hitl_request, mock_user):
        """Test unexpected exception raises 500."""
        pipeline = MagicMock()
        pipeline.handle_hitl_decision = AsyncMock(side_effect=Exception("Internal error"))

        with (
            patch("core.persistence.redis_client.get_redis_client") as mock_redis,
            patch("api.routes._session_state.get_active_pipeline") as mock_get_pipeline,
        ):
            mock_get_pipeline.return_value = pipeline
            mockRedis = MagicMock()
            mockRedis.get = AsyncMock(return_value=None)
            mockRedis.set = AsyncMock()
            mock_redis.return_value = mockRedis

            from api.routes import hitl

            try:
                await hitl.submit_decision(hitl_request, mock_user)
            except HTTPException as e:
                assert e.status_code == 500
            except Exception as e:
                pytest.fail(f"Expected HTTPException 500 but got {type(e).__name__}: {e}")
