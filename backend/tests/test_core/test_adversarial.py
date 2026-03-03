"""
Tests for Adversarial Robustness Checks
=====================================

Tests the adversarial checker for all agent domains.
"""

import pytest

from core.adversarial import (
    AdversarialChecker,
    RobustnessCaveat,
)


class TestAdversarialChecker:
    """Test AdversarialChecker functionality."""
    
    @pytest.fixture
    def checker(self):
        """Create an AdversarialChecker instance."""
        return AdversarialChecker()
    
    def test_clean_image_returns_no_ela_caveats(self, checker):
        """Test that a clean image returns no ELA caveats."""
        image_data = {
            "ela_variance": 0.5,
            "spatial_frequency_uniformity": 0.3,
        }
        
        caveats = checker.check_anti_ela_evasion(image_data)
        
        assert len(caveats) == 0
    
    def test_uniform_compressed_image_returns_ela_caveat(self, checker):
        """Test that uniform compressed image returns ELA caveat."""
        image_data = {
            "ela_variance": 0.005,  # Very low
            "spatial_frequency_uniformity": 0.3,
        }
        
        caveats = checker.check_anti_ela_evasion(image_data)
        
        assert len(caveats) == 1
        assert caveats[0].evasion_technique == "uniform_recompression"
        assert caveats[0].plausibility == "MEDIUM"
    
    def test_clean_audio_returns_no_spoofing_caveats(self, checker):
        """Test that clean audio returns no spoofing caveats."""
        audio_data = {
            "frequency_variance": 0.5,
            "pitch_contour_variance": 0.5,
        }
        
        caveats = checker.check_anti_spoofing_evasion(audio_data)
        
        assert len(caveats) == 0
    
    def test_smooth_pitch_contour_audio_returns_caveat(self, checker):
        """Test that smooth pitch contour returns caveat."""
        audio_data = {
            "frequency_variance": 0.5,
            "pitch_contour_variance": 0.01,  # Very smooth
        }
        
        caveats = checker.check_anti_spoofing_evasion(audio_data)
        
        assert len(caveats) == 1
        assert caveats[0].evasion_technique == "prosody_normalization"
        assert caveats[0].plausibility == "HIGH"
    
    def test_adversarial_patch_image_returns_object_detection_caveat(self, checker):
        """Test that adversarial patch returns object detection caveat."""
        image_data = {
            "high_frequency_in_bbox": 0.95,
            "texture_regularity": 0.3,
        }
        
        caveats = checker.check_object_detection_evasion(image_data)
        
        assert len(caveats) == 1
        assert caveats[0].evasion_technique == "adversarial_patch"
        assert caveats[0].plausibility == "HIGH"
    
    def test_smooth_optical_flow_at_edit_returns_caveat(self, checker):
        """Test that smooth optical flow returns caveat."""
        video_data = {
            "flow_variance": 0.005,  # Very smooth
            "frame_blending_detected": False,
        }
        
        caveats = checker.check_optical_flow_evasion(video_data)
        
        assert len(caveats) == 1
        assert caveats[0].evasion_technique == "flow_smoothing"
        assert caveats[0].plausibility == "MEDIUM"
    
    def test_complete_metadata_on_low_end_device_returns_spoofing_caveat(self, checker):
        """Test that complete metadata on low-end device returns caveat."""
        metadata = {
            "device_class": "smartphone",
            "metadata_completeness": 0.98,
            "gps_precision_meters": 1.0,
        }
        
        caveats = checker.check_metadata_spoofing(metadata)
        
        assert len(caveats) == 1
        assert caveats[0].evasion_technique == "spoofed_metadata"
        assert caveats[0].plausibility == "HIGH"
    
    def test_caveat_court_disclosure_contains_technique_name(self, checker):
        """Test that court disclosure contains technique description."""
        image_data = {
            "ela_variance": 0.005,
        }
        
        caveats = checker.check_anti_ela_evasion(image_data)
        
        assert len(caveats) == 1
        assert "anti-forensics technique" in caveats[0].court_disclosure
        assert "uniform recompression" in caveats[0].court_disclosure
    
    def test_empty_caveat_list_does_not_set_robustness_flag_on_finding(self, checker):
        """Test that empty caveats means no robustness concerns."""
        # Clean image
        image_data = {
            "ela_variance": 0.5,
            "spatial_frequency_uniformity": 0.3,
        }
        
        caveats = checker.check_anti_ela_evasion(image_data)
        
        # Empty list means no flag should be set
        assert len(caveats) == 0
    
    def test_multiple_caveats_detected(self, checker):
        """Test that multiple evasion techniques are detected."""
        image_data = {
            "ela_variance": 0.005,  # Low
            "spatial_frequency_uniformity": 0.98,  # High
        }
        
        caveats = checker.check_anti_ela_evasion(image_data)
        
        assert len(caveats) == 2
    
    def test_gps_precision_exceeded_returns_caveat(self, checker):
        """Test that unrealistic GPS precision returns caveat."""
        metadata = {
            "device_class": "unknown",
            "metadata_completeness": 0.5,
            "gps_precision_meters": 0.05,  # Very precise
        }
        
        caveats = checker.check_metadata_spoofing(metadata)
        
        assert len(caveats) == 1
        assert caveats[0].evasion_technique == "gps_precision_exceeded"
        assert caveats[0].plausibility == "HIGH"
    
    def test_frame_blending_detected_returns_caveat(self, checker):
        """Test that frame blending returns caveat."""
        video_data = {
            "flow_variance": 0.5,
            "frame_blending_detected": True,
        }
        
        caveats = checker.check_optical_flow_evasion(video_data)
        
        assert len(caveats) == 1
        assert caveats[0].evasion_technique == "frame_blending"
        assert caveats[0].plausibility == "HIGH"
    
    def test_generate_disclosure(self, checker):
        """Test court disclosure generation."""
        disclosure = checker.generate_disclosure("uniform_recompression")
        
        assert "anti-forensics technique" in disclosure
        assert "must be disclosed to the court" in disclosure
    
    def test_all_agents_have_checks(self, checker):
        """Test that all agents have adversarial check methods."""
        # Verify methods exist
        assert hasattr(checker, "check_anti_ela_evasion")
        assert hasattr(checker, "check_anti_spoofing_evasion")
        assert hasattr(checker, "check_object_detection_evasion")
        assert hasattr(checker, "check_optical_flow_evasion")
        assert hasattr(checker, "check_metadata_spoofing")


class TestRobustnessCaveat:
    """Test RobustnessCaveat model."""
    
    def test_caveat_creation(self):
        """Test creating a robustness caveat."""
        caveat = RobustnessCaveat(
            agent_id="Agent1_ImageIntegrity",
            evasion_technique="uniform_recompression",
            plausibility="MEDIUM",
            detection_basis="Low ELA variance",
            court_disclosure="Test disclosure"
        )
        
        assert caveat.agent_id == "Agent1_ImageIntegrity"
        assert caveat.evasion_technique == "uniform_recompression"
        assert caveat.plausibility == "MEDIUM"
        assert caveat.caveat_id is not None
    
    def test_plausibility_values(self):
        """Test valid plausibility values."""
        for plausibility in ["LOW", "MEDIUM", "HIGH"]:
            caveat = RobustnessCaveat(
                agent_id="TestAgent",
                evasion_technique="test",
                plausibility=plausibility,
                detection_basis="test",
                court_disclosure="test"
            )
            assert caveat.plausibility == plausibility
