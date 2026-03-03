"""
Adversarial Robustness Checks
===========================

Provides adversarial robustness checking for all five agent domains.
"""

from __future__ import annotations

from enum import Enum
from typing import Any, Literal, Optional
from uuid import UUID, uuid4

from pydantic import BaseModel, Field


class RobustnessCaveat(BaseModel):
    """Represents a potential adversarial evasion technique."""
    caveat_id: UUID = Field(default_factory=uuid4)
    agent_id: str
    evasion_technique: str
    plausibility: Literal["LOW", "MEDIUM", "HIGH"]
    detection_basis: str
    court_disclosure: str


class AdversarialChecker:
    """
    Adversarial robustness checker for forensic agents.
    
    Checks for known anti-forensics techniques and generates
    court-disclosure statements when evasion is plausible.
    """
    
    def __init__(self):
        # Registry of known evasion techniques
        self._techniques = {
            # Image ELA evasion
            "uniform_recompression": {
                "description": "Uniform recompression to flatten ELA anomalies",
                "plausibility_factors": ["low_ela_variance", "consistent_quality"],
            },
            "texture_synthesis": {
                "description": "Anti-forensic texture synthesis signatures",
                "plausibility_factors": ["spatial_frequency_uniformity"],
            },
            # Audio anti-spoofing evasion
            "frequency_uniformity": {
                "description": "Statistical uniformity in frequency bands",
                "plausibility_factors": ["flat_spectrum", "low_variance"],
            },
            "prosody_normalization": {
                "description": "Prosody normalization artifacts",
                "plausibility_factors": ["smooth_pitch_contour", "low_intonation_variance"],
            },
            # Object detection evasion
            "adversarial_patch": {
                "description": "High-frequency pixel patterns (adversarial patch)",
                "plausibility_factors": ["high_frequency_in_bbox", "regular_texture"],
            },
            # Optical flow evasion
            "flow_smoothing": {
                "description": "Unusually smooth motion vectors",
                "plausibility_factors": ["low_flow_variance", "consistent_motion"],
            },
            "frame_blending": {
                "description": "Frame blending artifacts at splice boundary",
                "plausibility_factors": ["blended_edges", "smooth_transitions"],
            },
            # Metadata spoofing
            "spoofed_metadata": {
                "description": "Suspiciously complete metadata on low-end device",
                "plausibility_factors": ["excessive_fields", "inconsistent_capabilities"],
            },
            "gps_precision_exceeded": {
                "description": "GPS precision exceeding device capability",
                "plausibility_factors": ["unrealistic_precision", "round_coordinates"],
            },
        }
    
    def check_anti_ela_evasion(self, image_data: dict[str, Any]) -> list[RobustnessCaveat]:
        """
        Check for anti-ELA evasion techniques.
        
        Args:
            image_data: Dictionary containing image analysis results
            
        Returns:
            List of caveats (empty if no evasion detected)
        """
        caveats = []
        
        # Check for uniform recompression
        ela_variance = image_data.get("ela_variance", 1.0)
        if ela_variance < 0.01:
            caveats.append(RobustnessCaveat(
                agent_id="Agent1_ImageIntegrity",
                evasion_technique="uniform_recompression",
                plausibility="MEDIUM",
                detection_basis=f"ELA variance ({ela_variance}) is unusually low, suggesting uniform recompression",
                court_disclosure=(
                    "A known anti-forensics technique (uniform recompression) could produce findings "
                    "consistent with this evidence. This does not invalidate the finding but "
                    "must be disclosed to the court."
                ),
            ))
        
        # Check for texture synthesis signatures
        spatial_freq = image_data.get("spatial_frequency_uniformity", 0.0)
        if spatial_freq > 0.95:
            caveats.append(RobustnessCaveat(
                agent_id="Agent1_ImageIntegrity",
                evasion_technique="texture_synthesis",
                plausibility="LOW",
                detection_basis=f"Spatial frequency uniformity ({spatial_freq}) suggests texture synthesis",
                court_disclosure=(
                    "A known anti-forensics technique (texture synthesis) could produce findings "
                    "consistent with this evidence. This does not invalidate the finding but "
                    "must be disclosed to the court."
                ),
            ))
        
        return caveats
    
    def check_anti_spoofing_evasion(self, audio_data: dict[str, Any]) -> list[RobustnessCaveat]:
        """
        Check for anti-spoofing evasion techniques.
        
        Args:
            audio_data: Dictionary containing audio analysis results
            
        Returns:
            List of caveats (empty if no evasion detected)
        """
        caveats = []
        
        # Check for frequency uniformity (adversarial perturbation signature)
        freq_variance = audio_data.get("frequency_variance", 1.0)
        if freq_variance < 0.05:
            caveats.append(RobustnessCaveat(
                agent_id="Agent2_Audio",
                evasion_technique="frequency_uniformity",
                plausibility="MEDIUM",
                detection_basis=f"Frequency variance ({freq_variance}) is unusually low",
                court_disclosure=(
                    "A known anti-forensics technique (frequency uniformity) could produce findings "
                    "consistent with this evidence. This does not invalidate the finding but "
                    "must be disclosed to the court."
                ),
            ))
        
        # Check for prosody normalization artifacts
        pitch_variance = audio_data.get("pitch_contour_variance", 1.0)
        if pitch_variance < 0.02:
            caveats.append(RobustnessCaveat(
                agent_id="Agent2_Audio",
                evasion_technique="prosody_normalization",
                plausibility="HIGH",
                detection_basis=f"Pitch contour variance ({pitch_variance}) is unnaturally smooth",
                court_disclosure=(
                    "A known anti-forensics technique (prosody normalization) could produce findings "
                    "consistent with this evidence. This does not invalidate the finding but "
                    "must be disclosed to the court."
                ),
            ))
        
        return caveats
    
    def check_object_detection_evasion(self, image_data: dict[str, Any]) -> list[RobustnessCaveat]:
        """
        Check for object detection evasion techniques.
        
        Args:
            image_data: Dictionary containing image analysis results
            
        Returns:
            List of caveats (empty if no evasion detected)
        """
        caveats = []
        
        # Check for adversarial patch signatures
        high_freq_in_bbox = image_data.get("high_frequency_in_bbox", 0.0)
        if high_freq_in_bbox > 0.9:
            caveats.append(RobustnessCaveat(
                agent_id="Agent3_Object",
                evasion_technique="adversarial_patch",
                plausibility="HIGH",
                detection_basis=f"High frequency content in object region ({high_freq_in_bbox}) suggests adversarial patch",
                court_disclosure=(
                    "A known anti-forensics technique (adversarial patch) could produce findings "
                    "consistent with this evidence. This does not invalidate the finding but "
                    "must be disclosed to the court."
                ),
            ))
        
        # Check for anomalous texture regularity
        texture_regularity = image_data.get("texture_regularity", 0.0)
        if texture_regularity > 0.95:
            caveats.append(RobustnessCaveat(
                agent_id="Agent3_Object",
                evasion_technique="adversarial_patch",
                plausibility="MEDIUM",
                detection_basis=f"Texture regularity ({texture_regularity}) in detected object region",
                court_disclosure=(
                    "A known anti-forensics technique (adversarial patch) could produce findings "
                    "consistent with this evidence. This does not invalidate the finding but "
                    "must be disclosed to the court."
                ),
            ))
        
        return caveats
    
    def check_optical_flow_evasion(self, video_data: dict[str, Any]) -> list[RobustnessCaveat]:
        """
        Check for optical flow evasion techniques.
        
        Args:
            video_data: Dictionary containing video analysis results
            
        Returns:
            List of caveats (empty if no evasion detected)
        """
        caveats = []
        
        # Check for unusually smooth motion vectors (flow smoothing)
        flow_variance = video_data.get("flow_variance", 1.0)
        if flow_variance < 0.01:
            caveats.append(RobustnessCaveat(
                agent_id="Agent4_Video",
                evasion_technique="flow_smoothing",
                plausibility="MEDIUM",
                detection_basis=f"Optical flow variance ({flow_variance}) is unusually low",
                court_disclosure=(
                    "A known anti-forensics technique (flow smoothing) could produce findings "
                    "consistent with this evidence. This does not invalidate the finding but "
                    "must be disclosed to the court."
                ),
            ))
        
        # Check for frame blending at splice boundary
        blend_detected = video_data.get("frame_blending_detected", False)
        if blend_detected:
            caveats.append(RobustnessCaveat(
                agent_id="Agent4_Video",
                evasion_technique="frame_blending",
                plausibility="HIGH",
                detection_basis="Frame blending artifacts detected at edit point",
                court_disclosure=(
                    "A known anti-forensics technique (frame blending) could produce findings "
                    "consistent with this evidence. This does not invalidate the finding but "
                    "must be disclosed to the court."
                ),
            ))
        
        return caveats
    
    def check_metadata_spoofing(self, metadata: dict[str, Any]) -> list[RobustnessCaveat]:
        """
        Check for metadata spoofing techniques.
        
        Args:
            metadata: Dictionary containing metadata analysis results
            
        Returns:
            List of caveats (empty if no evasion detected)
        """
        caveats = []
        
        # Check for suspiciously complete metadata on low-end device
        device_class = metadata.get("device_class", "unknown")
        completeness = metadata.get("metadata_completeness", 0.0)
        
        if device_class in ["low_end", "smartphone", "budget"] and completeness > 0.95:
            caveats.append(RobustnessCaveat(
                agent_id="Agent5_Metadata",
                evasion_technique="spoofed_metadata",
                plausibility="HIGH",
                detection_basis=f"Metadata completeness ({completeness}) unusually high for {device_class} device",
                court_disclosure=(
                    "A known anti-forensics technique (spoofed metadata) could produce findings "
                    "consistent with this evidence. This does not invalidate the finding but "
                    "must be disclosed to the court."
                ),
            ))
        
        # Check for GPS precision exceeding device capability
        gps_precision = metadata.get("gps_precision_meters", 0.0)
        if 0 < gps_precision < 0.1:  # Less than 10cm precision is unrealistic
            caveats.append(RobustnessCaveat(
                agent_id="Agent5_Metadata",
                evasion_technique="gps_precision_exceeded",
                plausibility="HIGH",
                detection_basis=f"GPS precision ({gps_precision}m) exceeds typical device capability",
                court_disclosure=(
                    "A known anti-forensics technique (GPS precision spoofing) could produce findings "
                    "consistent with this evidence. This does not invalidate the finding but "
                    "must be disclosed to the court."
                ),
            ))
        
        return caveats
    
    def generate_disclosure(self, technique_name: str) -> str:
        """
        Generate a court disclosure statement for a technique.
        
        Args:
            technique_name: Name of the evasion technique
            
        Returns:
            Court disclosure string
        """
        technique = self._techniques.get(technique_name, {})
        description = technique.get("description", technique_name)
        
        return (
            f"A known anti-forensics technique ({description}) could produce findings "
            f"consistent with this evidence. This does not invalidate the finding but "
            f"must be disclosed to the court."
        )


# Global instance
_adversarial_checker: Optional[AdversarialChecker] = None


def get_adversarial_checker() -> AdversarialChecker:
    """Get the global adversarial checker instance."""
    global _adversarial_checker
    if _adversarial_checker is None:
        _adversarial_checker = AdversarialChecker()
    return _adversarial_checker
