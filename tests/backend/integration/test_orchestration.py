import pytest
from unittest.mock import MagicMock, patch, AsyncMock
from uuid import uuid4
from orchestration.pipeline import ForensicCouncilPipeline
from backend.core.evidence import EvidenceArtifact
from backend.core.config import get_settings

@pytest.fixture
def mock_pipeline_deps():
    config = get_settings()
    wm = MagicMock()
    em = MagicMock()
    cl = MagicMock()
    es = MagicMock()
    return config, wm, em, cl, es

def create_mock_artifact(mime_type="image/jpeg"):
    return EvidenceArtifact(
        artifact_id=uuid4(),
        file_path="test_image.jpg",
        original_filename="test_image.jpg",
        mime_type=mime_type,
        file_size=1024,
        sha256_hash="abc",
        content_hash="abc",
        metadata={"mime_type": mime_type}
    )

@pytest.mark.asyncio
async def test_pipeline_execution_flow(mock_pipeline_deps):
    config, wm, em, cl, es = mock_pipeline_deps
    artifact = create_mock_artifact()
    session_id = str(uuid4())
    
    pipeline = ForensicCouncilPipeline(
        config=config,
        working_memory=wm,
        episodic_memory=em,
        custody_logger=cl,
        evidence_store=es
    )
    
    # Mock agent classes to return mock findings
    mock_finding = MagicMock()
    mock_finding.finding_type = "Test Finding"
    
    with patch("backend.agents.agent1_image.Agent1Image.run_investigation", new_callable=AsyncMock) as mock_a1, \
         patch("backend.agents.agent5_metadata.Agent5Metadata.run_investigation", new_callable=AsyncMock) as mock_a5, \
         patch("backend.agents.arbiter.Arbiter.deliberate", new_callable=AsyncMock) as mock_arbiter:
        
        mock_a1.return_value = [mock_finding]
        mock_a5.return_value = [mock_finding]
        mock_arbiter.return_value = MagicMock()
        
        # We only run Agent 1 and 5 for image/jpeg in this test logic override or check
        # Actually, the pipeline filters agents based on supports_uploaded_file
        
        results = await pipeline.run(artifact, session_id=session_id)
        
        assert mock_a1.called
        assert mock_a5.called
        assert mock_arbiter.called

@pytest.mark.asyncio
async def test_pipeline_error_handling(mock_pipeline_deps):
    config, wm, em, cl, es = mock_pipeline_deps
    artifact = create_mock_artifact()
    session_id = str(uuid4())
    
    pipeline = ForensicCouncilPipeline(
        config=config,
        working_memory=wm,
        episodic_memory=em,
        custody_logger=cl,
        evidence_store=es
    )
    
    with patch("backend.agents.agent1_image.Agent1Image.run_investigation", side_effect=Exception("Agent Crash")), \
         patch("backend.agents.arbiter.Arbiter.deliberate", new_callable=AsyncMock) as mock_arbiter:
        
        # Even if an agent crashes, the pipeline should continue to other agents or report failure gracefully
        results = await pipeline.run(artifact, session_id=session_id)
        
        # Arbiter should still be called with whatever findings were collected (if any)
        assert mock_arbiter.called
