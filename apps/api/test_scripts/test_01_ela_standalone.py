"""
Test 1: ELA Anomaly Classification (Agent 1 - Classical ML)
Tests the ela_anomaly_classifier on a synthetic test image.
"""
import asyncio

import numpy as np
from PIL import Image


async def test_ela_classifier():
    from tools.ml_tools.ela_anomaly_classifier import classify_ela

    # Create a synthetic test JPEG with known noise pattern
    img = np.random.randint(0, 255, (128, 128, 3), dtype=np.uint8)
    test_path = "/tmp/test_ela_synthetic.jpg"
    Image.fromarray(img).save(test_path, format="JPEG", quality=95)

    result = classify_ela(test_path, quality=95)

    assert result["available"] is True
    assert "verdict" in result
    assert "anomaly_score" in result
    # IsolationForest raw scores can exceed 1.0; check it's a valid float
    assert isinstance(result["anomaly_score"], float)
    assert not np.isnan(result["anomaly_score"])
    assert "num_anomalous_blocks" in result
    assert result["total_blocks_analyzed"] > 0

    print(f"  Verdict: {result['verdict']}")
    print(f"  Anomaly Score: {result['anomaly_score']:.4f}")
    print(f"  Anomalous Blocks: {result['num_anomalous_blocks']}/{result['total_blocks_analyzed']}")


async def test_ela_production_tool():
    from core.evidence import ArtifactType, EvidenceArtifact
    from tools.image_tools import ela_full_image

    img = np.random.randint(0, 255, (128, 128, 3), dtype=np.uint8)
    test_path = "/tmp/test_ela_production.jpg"
    Image.fromarray(img).save(test_path, format="JPEG", quality=95)

    artifact = EvidenceArtifact.create_root(
        artifact_type=ArtifactType.ORIGINAL,
        file_path=test_path,
        content_hash="test",
        action="test",
        agent_id="test",
        session_id="test-session",
    )

    result = await ela_full_image(artifact)

    assert result["available"] is True
    assert "max_anomaly" in result
    assert "num_anomaly_regions" in result
    assert result["num_anomaly_regions"] >= 0
    assert result["court_defensible"] is True

    print(f"  Max Anomaly: {result['max_anomaly']:.2f}")
    print(f"  Anomaly Regions: {result['num_anomaly_regions']}")
    print(f"  Multi-quality fusion: {result['multi_quality_fusion']}")


if __name__ == "__main__":
    print("Test 1a: ELA ML Classifier (classify_ela)")
    asyncio.run(test_ela_classifier())
    print()
    print("Test 1b: ELA Production Tool (ela_full_image)")
    asyncio.run(test_ela_production_tool())
    print()
    print(" All ELA tests passed!")
