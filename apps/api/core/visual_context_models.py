from pydantic import BaseModel, Field
from typing import List, Dict, Any, Literal, Optional

class DetectedObject(BaseModel):
    label: str
    confidence: float
    box: Optional[List[float]] = None

class ImageIntegrityContext(BaseModel):
    visible_manipulation_signals: List[str] = Field(default_factory=list)
    ai_generation_signals: List[str] = Field(default_factory=list)
    editing_or_compositing_signals: List[str] = Field(default_factory=list)
    compression_or_reupload_signals: List[str] = Field(default_factory=list)
    regions_for_followup: List[str] = Field(default_factory=list)
    integrity_assessment: Literal[
        "no_visible_issue", "suspicious", "likely_manipulated", "ai_generated_suspect", "cannot_determine"
    ] = "cannot_determine"
    confidence: float = 0.0

class ObjectSceneContext(BaseModel):
    scene_description: str = ""
    people: List[str] = Field(default_factory=list)
    objects: List[str] = Field(default_factory=list)
    weapons_or_dangerous_items: List[str] = Field(default_factory=list)
    documents_or_ids: List[str] = Field(default_factory=list)
    ui_elements: List[str] = Field(default_factory=list)
    visible_text: List[str] = Field(default_factory=list)
    scene_inconsistencies: List[str] = Field(default_factory=list)
    confidence: float = 0.0

class MetadataVisualContext(BaseModel):
    visible_timestamps: List[str] = Field(default_factory=list)
    visible_location_clues: List[str] = Field(default_factory=list)
    device_or_platform_clues: List[str] = Field(default_factory=list)
    software_or_app_clues: List[str] = Field(default_factory=list)
    lighting_weather_season_clues: List[str] = Field(default_factory=list)
    metadata_consistency_notes: List[str] = Field(default_factory=list)
    metadata_contradictions: List[str] = Field(default_factory=list)
    confidence: float = 0.0

class VisualContext(BaseModel):
    session_id: str
    evidence_sha256: str
    source: Literal["llm_assisted", "local_ensemble"]
    provider_name: Optional[str] = None
    external_llm_used: bool

    image_integrity_context: ImageIntegrityContext
    object_scene_context: ObjectSceneContext
    metadata_visual_context: MetadataVisualContext

    extracted_text: List[str] = Field(default_factory=list)
    detected_objects: List[DetectedObject] = Field(default_factory=list)
    interface_elements: List[str] = Field(default_factory=list)
    visible_timestamps: List[str] = Field(default_factory=list)
    scene_description: str = ""
    file_type_assessment: str = ""

    authenticity_verdict: Literal[
        "AUTHENTIC",
        "SUSPICIOUS",
        "LIKELY_MANIPULATED",
        "AI_GENERATED",
        "CANNOT_DETERMINE",
    ] = "CANNOT_DETERMINE"

    confidence: float = 0.0
    tool_coverage: Dict[str, bool] = Field(default_factory=dict)
    provider_attempts: List[Dict[str, Any]] = Field(default_factory=list)
    limitations: List[str] = Field(default_factory=list)
    created_at: str
