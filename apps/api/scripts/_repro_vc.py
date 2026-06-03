from core.per_agent_synthesis import (
    AgentSynthesisInput, generate_deterministic_agent_synthesis, split_visual_context, compose_evidence_identity
)
from core.visual_context_models import VisualContext, ImageIntegrityContext, ObjectSceneContext, MetadataVisualContext

vc = VisualContext(
    session_id="s", evidence_sha256="h", source="local_ensemble", provider_name="local",
    external_llm_used=False,
    image_integrity_context=ImageIntegrityContext(integrity_assessment="cannot_determine"),
    object_scene_context=ObjectSceneContext(scene_description=""),
    metadata_visual_context=MetadataVisualContext(),
    file_type_assessment="composite",
    authenticity_verdict="CANNOT_DETERMINE",
    scene_description="",
)
splits = split_visual_context("s", vc)
ident = compose_evidence_identity(vc)
print("evidence_identity =>", repr(ident))
for aid, sec in (("Agent1", splits.agent1_image_integrity), ("Agent5", splits.agent5_metadata_visual)):
    inp = AgentSynthesisInput(
        agent_id=aid, persona_name=aid,
        visual_context_available=bool(sec), visual_context_section=sec,
        evidence_identity=ident, completed_tools=["exif_extract"], failed_tools=[],
        findings=[], grounded_findings=[], agent_verdict="AUTHENTIC", agent_confidence=0.8,
    )
    out = generate_deterministic_agent_synthesis(inp)
    print(f"\n=== {aid} visual_context_summary ===")
    print(repr(out.visual_context_summary))
