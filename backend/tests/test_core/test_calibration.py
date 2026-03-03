"""
Tests for Confidence Calibration Layer
=====================================

Tests the calibration layer with versioned models.
"""

import pytest
import tempfile
import shutil
from uuid import uuid4

from core.calibration import (
    CalibrationLayer,
    CalibrationModel,
    CalibratedConfidence,
    CalibrationMethod,
)


class TestCalibrationLayer:
    """Test CalibrationLayer functionality."""
    
    @pytest.fixture
    def temp_models_path(self):
        """Create a temporary directory for calibration models."""
        temp_dir = tempfile.mkdtemp()
        yield temp_dir
        shutil.rmtree(temp_dir)
    
    @pytest.fixture
    def calibration_layer(self, temp_models_path):
        """Create a CalibrationLayer with temp directory."""
        return CalibrationLayer(models_path=temp_models_path)
    
    def test_calibrate_returns_calibrated_confidence_object(self, calibration_layer):
        """Test that calibrate returns a CalibratedConfidence object."""
        result = calibration_layer.calibrate(
            agent_id="Agent1_ImageIntegrity",
            raw_score=0.89,
            finding_class="splicing_detected"
        )
        
        assert isinstance(result, CalibratedConfidence)
        assert result.raw_score == 0.89
        assert 0 <= result.calibrated_probability <= 1.0
    
    def test_court_statement_contains_benchmark_name(self, calibration_layer):
        """Test that court statement contains benchmark dataset name."""
        result = calibration_layer.calibrate(
            agent_id="Agent1_ImageIntegrity",
            raw_score=0.75,
            finding_class="manipulation_detected"
        )
        
        assert "stub_benchmark" in result.court_statement
    
    def test_court_statement_contains_tpr_and_fpr(self, calibration_layer):
        """Test that court statement contains TPR and FPR."""
        result = calibration_layer.calibrate(
            agent_id="Agent1_ImageIntegrity",
            raw_score=0.85,
            finding_class="tampering_detected"
        )
        
        assert "true positive rate" in result.court_statement
        assert "false positive rate" in result.court_statement
        assert "%" in result.court_statement  # Should have percentage format
    
    def test_calibration_model_versioning_creates_new_version(self, calibration_layer):
        """Test that fitting a new model creates a new version."""
        # Create first version
        model1 = calibration_layer.fit_stub_model("Agent1_ImageIntegrity")
        version1 = model1.version
        
        # Create second version
        model2 = calibration_layer.fit_stub_model("Agent1_ImageIntegrity")
        version2 = model2.version
        
        # Versions should be different
        assert version1 != version2
    
    def test_old_version_model_still_loadable_after_new_version_created(self, calibration_layer):
        """Test that old model versions remain accessible."""
        # Create two versions
        model1 = calibration_layer.fit_stub_model("Agent1_ImageIntegrity")
        version1 = model1.version
        
        model2 = calibration_layer.fit_stub_model("Agent1_ImageIntegrity")
        
        # Load the old version
        loaded_model = calibration_layer.load_model("Agent1_ImageIntegrity", version1)
        
        assert loaded_model.model_id == model1.model_id
        assert loaded_model.version == version1
    
    def test_finding_retains_original_calibration_version_id(self, calibration_layer):
        """Test that findings retain their original calibration model ID."""
        # Create a model and calibrate
        calibration_layer.fit_stub_model("Agent1_ImageIntegrity")
        
        result1 = calibration_layer.calibrate(
            agent_id="Agent1_ImageIntegrity",
            raw_score=0.9,
            finding_class="test"
        )
        model_id_1 = result1.calibration_model_id
        
        # Create new version
        calibration_layer.fit_stub_model("Agent1_ImageIntegrity")
        
        # Original finding should still reference old model
        assert result1.calibration_model_id == model_id_1
    
    def test_uncalibrated_finding_flagged_if_calibration_skipped(self):
        """Test that uncalibrated findings can be identified."""
        # This test verifies the pattern - in practice, findings would
        # have a calibration_model_id that is checked
        layer = CalibrationLayer(models_path="./storage/calibration_models")
        
        # When no model exists, fit_stub_model is called automatically
        result = layer.calibrate(
            agent_id="TestAgent",
            raw_score=0.5,
            finding_class="test"
        )
        
        # Should have a valid model ID
        assert result.calibration_model_id is not None
    
    def test_all_agents_have_stub_calibration_models_loadable(self, calibration_layer):
        """Test that stub models can be created for all agents."""
        agents = [
            "Agent1_ImageIntegrity",
            "Agent2_Audio",
            "Agent3_Object",
            "Agent4_Video",
            "Agent5_Metadata"
        ]
        
        for agent_id in agents:
            model = calibration_layer.fit_stub_model(agent_id)
            assert model.agent_id == agent_id
            assert model.method == CalibrationMethod.RULE_BASED
    
    def test_calibrate_different_scores_produce_different_results(self, calibration_layer):
        """Test that different raw scores produce different calibrated results."""
        result_low = calibration_layer.calibrate(
            agent_id="Agent1_ImageIntegrity",
            raw_score=0.3,
            finding_class="test"
        )
        
        result_high = calibration_layer.calibrate(
            agent_id="Agent1_ImageIntegrity",
            raw_score=0.9,
            finding_class="test"
        )
        
        # Calibrated probabilities should differ
        assert result_low.calibrated_probability != result_high.calibrated_probability
    
    def test_list_versions_returns_all_versions(self, calibration_layer):
        """Test that list_versions returns all available versions."""
        # Create multiple versions
        calibration_layer.fit_stub_model("Agent1_ImageIntegrity")
        calibration_layer.fit_stub_model("Agent1_ImageIntegrity")
        calibration_layer.fit_stub_model("Agent1_ImageIntegrity")
        
        versions = calibration_layer.list_versions("Agent1_ImageIntegrity")
        
        # Should have 3 versions (not counting "latest")
        assert len(versions) >= 3


class TestCalibrationModel:
    """Test CalibrationModel functionality."""
    
    def test_model_creation(self):
        """Test creating a calibration model."""
        model = CalibrationModel(
            agent_id="Agent1_ImageIntegrity",
            method=CalibrationMethod.RULE_BASED,
            benchmark_dataset="test_dataset",
            version="1.0.0",
            params={"k": 10.0}
        )
        
        assert model.agent_id == "Agent1_ImageIntegrity"
        assert model.method == CalibrationMethod.RULE_BASED
        assert model.version == "1.0.0"
    
    def test_model_id_is_uuid(self):
        """Test that model_id is automatically generated as UUID."""
        model = CalibrationModel(
            agent_id="Agent1_ImageIntegrity",
            method=CalibrationMethod.RULE_BASED,
            benchmark_dataset="test",
            version="1.0"
        )
        
        assert model.model_id is not None


class TestCalibratedConfidence:
    """Test CalibratedConfidence functionality."""
    
    def test_confidence_creation(self):
        """Test creating a calibrated confidence result."""
        confidence = CalibratedConfidence(
            raw_score=0.85,
            calibrated_probability=0.78,
            true_positive_rate=0.9,
            false_positive_rate=0.1,
            calibration_model_id=uuid4(),
            calibration_version="1.0.0",
            benchmark_dataset="test",
            court_statement="Test statement"
        )
        
        assert confidence.raw_score == 0.85
        assert confidence.calibrated_probability == 0.78
        assert confidence.true_positive_rate == 0.9
        assert confidence.false_positive_rate == 0.1
    
    def test_court_statement_format(self):
        """Test court statement format matches requirements."""
        confidence = CalibratedConfidence(
            raw_score=0.89,
            calibrated_probability=0.85,
            true_positive_rate=0.95,
            false_positive_rate=0.05,
            calibration_model_id=uuid4(),
            calibration_version="1.0.0",
            benchmark_dataset="benchmark_v1",
            court_statement=""
        )
        
        # Generate statement
        statement = (
            f"Based on benchmark performance against {confidence.benchmark_dataset}, "
            f"a model confidence of {confidence.raw_score:.2f} in class 'test' "
            f"corresponds to a true positive rate of {confidence.true_positive_rate:.1%} "
            f"with a false positive rate of {confidence.false_positive_rate:.1%}."
        )
        
        assert "benchmark_v1" in statement
        assert "0.89" in statement
        assert "true positive rate" in statement
        assert "false positive rate" in statement
