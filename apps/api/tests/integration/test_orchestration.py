import pytest

from core.config import get_settings
from orchestration.pipeline import ForensicCouncilPipeline


@pytest.mark.asyncio
async def test_pipeline_creation():
    config = get_settings()
    pipeline = ForensicCouncilPipeline(config=config)
    assert pipeline is not None
    assert pipeline.config is not None


@pytest.mark.asyncio
async def test_pipeline_error_handling():
    pipeline = ForensicCouncilPipeline()
    assert pipeline is not None
