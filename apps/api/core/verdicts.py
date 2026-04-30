"""
Evidence verdict strings used across all forensic agents.
Centralized to prevent typos and ensure consistency.
"""

from enum import StrEnum


class EvidenceVerdict(StrEnum):
    """Legal-sound verdict vocabulary for forensic findings."""

    POSITIVE = "POSITIVE"  # Manipulation / forgery detected
    NEGATIVE = "NEGATIVE"  # Clean, no manipulation detected
    SUSPICIOUS = "SUSPICIOUS"  # Anomalous but inconclusive
    CLONE = "CLONE"  # Voice clone detected
    SYNTHETIC = "SYNTHETIC"  # Audio synth / deepfake detected
    SPOOF = "SPOOF"  # Presentation attack (spoofing)
    GENUINE = "GENUINE"  # Authenticated as real
    CLEAN = "CLEAN"  # No audio/tampering anomalies
    INCONCLUSIVE = "INCONCLUSIVE"  # Insufficient evidence
    ADVERSARIAL_EVASION = "adversarial_evasion_suspected"  # Perturbation evasion
