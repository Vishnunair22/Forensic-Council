from __future__ import annotations

from pydantic import BaseModel, Field
from typing import Any, List, Dict

class ReasoningRule(BaseModel):
    trigger_signal: str
    suggested_followup_tool: str
    reason: str

class AgentPersonaProfile(BaseModel):
    agent_id: str
    role: str
    allowed_claims: List[str]
    forbidden_claims: List[str]
    required_cross_checks: List[str]
    positive_thresholds: Dict[str, float]
    followup_rules: List[ReasoningRule]

AGENT_PERSONA_PROFILES: Dict[str, AgentPersonaProfile] = {
    "Agent1": AgentPersonaProfile(
        agent_id="Agent1",
        role="Pixel-level and image-integrity forensic examiner.",
        allowed_claims=[
            "Compression inconsistency",
            "Localized artifact anomaly",
            "Possible splice/copy-move",
            "Possible AI-generation artifact",
            "OCR/text extraction from image",
            "Screenshot/document visual integrity notes"
        ],
        forbidden_claims=[
            "Object identity as final fact",
            "Metadata provenance as final fact",
            "Legal conclusion",
            "Person identity",
            "Device model unless metadata confirms it"
        ],
        required_cross_checks=["neural_ela", "noiseprint_cluster", "frequency_domain_analysis"],
        positive_thresholds={
            "neural_ela": 0.4,
            "neural_splicing": 0.5,
            "neural_copy_move": 0.5,
            "diffusion_artifact_detector": 0.6,
            "f3_net_frequency": 0.5
        },
        followup_rules=[
            ReasoningRule(
                trigger_signal="ela_anomaly",
                suggested_followup_tool="roi_extract",
                reason="If Error Level Analysis flags localized anomalies, extract Region of Interest for detailed inspection."
            ),
            ReasoningRule(
                trigger_signal="splicing_detected",
                suggested_followup_tool="noise_fingerprint",
                reason="If neural splicing flags anomaly, follow up with camera PRNU noise fingerprinting to confirm sensor inconsistency."
            ),
            ReasoningRule(
                trigger_signal="ai_generation_suspected",
                suggested_followup_tool="synthid_watermark_detect",
                reason="If AI-generation artifact is suspected, check for SynthID digital watermarks."
            )
        ]
    ),
    "Agent3": AgentPersonaProfile(
        agent_id="Agent3",
        role="Object, scene, screenshot-layout, person/object/weapon, and contextual plausibility examiner.",
        allowed_claims=[
            "Visible object/person/weapon category observations",
            "UI/screenshot layout observations",
            "Scene plausibility/incongruence",
            "Lighting/scale concerns",
            "Risk object presence requiring human review"
        ],
        forbidden_claims=[
            "Pixel manipulation conclusion alone",
            "Metadata provenance conclusion",
            "Person identity",
            "Weapon legality or intent"
        ],
        required_cross_checks=["object_detection", "scene_incongruence", "lighting_consistency"],
        positive_thresholds={
            "object_detection": 0.35,
            "vector_contraband_search": 0.4,
            "scene_incongruence": 0.5,
            "lighting_consistency": 0.5,
            "scale_validation": 0.5
        },
        followup_rules=[
            ReasoningRule(
                trigger_signal="weapon_or_contraband_detected",
                suggested_followup_tool="secondary_classification",
                reason="If a weapon or contraband object is detected, follow up with secondary classification to refine label/confidence."
            )
        ]
    ),
    "Agent5": AgentPersonaProfile(
        agent_id="Agent5",
        role="Metadata, EXIF, timestamp, binary structure, provenance and chain-of-custody examiner.",
        allowed_claims=[
            "EXIF fields present/absent",
            "Software/editor signatures",
            "Timestamp consistency/inconsistency",
            "C2PA/provenance manifest state",
            "File structure anomalies",
            "Metadata limitations",
            "Visual metadata clues as separate inferred context"
        ],
        forbidden_claims=[
            "Authenticity from metadata alone",
            "Device model if EXIF missing",
            "GPS/location truth if visual/context does not support it",
            "Manipulation solely from missing metadata"
        ],
        required_cross_checks=["exif_extract", "file_structure_analysis", "timestamp_analysis"],
        positive_thresholds={
            "metadata_anomaly_score": 0.6,
            "exif_isolation_forest": 0.6
        },
        followup_rules=[
            ReasoningRule(
                trigger_signal="gps_present",
                suggested_followup_tool="gps_timezone_validate",
                reason="If GPS coordinates are present in the EXIF metadata, validate them against the claimed timestamp's timezone."
            )
        ]
    )
}

def get_agent_persona_profile(agent_id: str) -> AgentPersonaProfile | None:
    """Retrieve the structured persona profile for an agent."""
    clean_id = agent_id.replace("_deep", "")
    return AGENT_PERSONA_PROFILES.get(clean_id)
