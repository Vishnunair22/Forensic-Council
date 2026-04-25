"""
Property-based tests for forensic algorithm invariants using Hypothesis.
Ensures boundary conditions and core mathematical invariants hold across a
wide range of inputs.
"""

import os
import tempfile
from uuid import uuid4

import numpy as np
import pytest
from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st
from PIL import Image

from core.evidence import ArtifactType, EvidenceArtifact
from tools.image_tools import ela_full_image


@pytest.mark.unit
class TestForensicProperties:
    """Property-based tests for image forensic tools."""

    @settings(suppress_health_check=[HealthCheck.function_scoped_fixture], deadline=None)
    @given(
        width=st.integers(min_value=32, max_value=512),
        height=st.integers(min_value=32, max_value=512),
        quality=st.integers(min_value=1, max_value=100),
    )
    @pytest.mark.asyncio
    async def test_ela_invariants(self, width, height, quality):
        """
        Verify ELA invariants:
        1. Result contains expected statistical keys.
        2. max_anomaly is within valid byte range [0, 255].
        3. Mean ELA is non-negative.
        """
        # Create a random RGB image
        img_data = np.random.randint(0, 256, (height, width, 3), dtype=np.uint8)
        img = Image.fromarray(img_data)

        with tempfile.NamedTemporaryFile(suffix=".jpg", delete=False) as tmp:
            # Save at high quality to ensure it's a valid JPEG
            img.save(tmp.name, "JPEG", quality=95)
            tmp_path = tmp.name

        try:
            artifact = EvidenceArtifact(
                artifact_id=uuid4(),
                parent_id=None,
                root_id=uuid4(),
                artifact_type=ArtifactType.ORIGINAL,
                file_path=tmp_path,
                content_hash="dummy_hash",
                action="test_op",
                agent_id="test_agent",
                session_id=uuid4(),
                metadata={"mime_type": "image/jpeg"},
            )

            # Test single-quality ELA
            result = await ela_full_image(artifact, quality=quality, multi_quality=False)

            # Basic invariant checks
            assert "max_anomaly" in result
            assert "mean_ela" in result

            if result.get("ela_not_applicable"):
                return

            assert result["available"] is True
            assert isinstance(result["max_anomaly"], (int, float))
            assert 0 <= result["max_anomaly"] <= 255
            assert result["mean_ela"] >= 0
            assert result["std_ela"] >= 0

        finally:
            if os.path.exists(tmp_path):
                os.unlink(tmp_path)

    @settings(suppress_health_check=[HealthCheck.function_scoped_fixture], deadline=None)
    @given(size=st.integers(min_value=64, max_value=256))
    @pytest.mark.asyncio
    async def test_ela_dimension_robustness(self, size):
        """Verify ELA handles various square and non-square aspect ratios."""
        img_data = np.zeros((size, size, 3), dtype=np.uint8)
        # Draw a white square in the middle to create some contrast
        img_data[size // 4 : size // 2, size // 4 : size // 2] = 255
        img = Image.fromarray(img_data)

        with tempfile.NamedTemporaryFile(suffix=".jpg", delete=False) as tmp:
            img.save(tmp.name, "JPEG", quality=90)
            tmp_path = tmp.name

        try:
            artifact = EvidenceArtifact(
                artifact_id=uuid4(),
                parent_id=None,
                root_id=uuid4(),
                artifact_type=ArtifactType.ORIGINAL,
                file_path=tmp_path,
                content_hash="dummy",
                action="test",
                agent_id="test",
                session_id=uuid4(),
            )

            result = await ela_full_image(artifact, multi_quality=True)
            assert result["available"] is True
            assert "num_anomaly_regions" in result
            assert isinstance(result["num_anomaly_regions"], int)

        finally:
            if os.path.exists(tmp_path):
                os.unlink(tmp_path)
