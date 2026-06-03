"""
Agent ↔ Tool Taxonomy — single source of truth
===============================================

Defines which specialist agent OWNS each image-forensic tool, by analysis axis.
Image evidence is split across three specialist agents, each with one coherent
concern:

  - Agent1  IMAGE INTEGRITY    — "was it altered?"  pixel/forgery manipulation
                                 detectors (ELA, splicing, copy-move, frequency,
                                 fingerprint, diffusion/AI-gen, font/UI forgery).
  - Agent3  OBJECT / CONTENT   — "what is in it?"   object/scene understanding,
                                 OCR, semantic classification, contraband, layout.
  - Agent5  METADATA / PROVENANCE — "where did it come from?"  EXIF, file
                                 structure, hashes, timestamps, GPS, camera profile.

Routing plans and per-agent tool registration both derive their ownership from
this map, so "which agent runs what" is answerable in exactly one place and can
never silently drift.

Tools in SHARED_TOOLS are cross-cutting infrastructure (the preflight visual
context, the shared-context reader, inter-agent calls) and are not owned by a
single analysis agent.
"""

from __future__ import annotations

AGENT_AXIS: dict[str, str] = {
    "Agent1": "image_integrity",
    "Agent3": "object_content",
    "Agent5": "metadata_provenance",
}

# ── Agent 1 — Image Integrity (did someone alter it?) ────────────────────────
AGENT1_INTEGRITY: frozenset[str] = frozenset(
    {
        "ela_full_image",
        "ela_anomaly_classify",
        "neural_ela",
        "roi_extract",
        "jpeg_ghost_detect",
        "frequency_domain_analysis",
        "splicing_detect",
        "neural_splicing",
        "neural_copy_move",
        "noise_fingerprint",
        "noiseprint_cluster",
        "deepfake_frequency_check",
        "neural_fingerprint",
        "anomaly_tracer",
        "diffusion_artifact_detector",
        "synthid_watermark_detect",
        "f3_net_frequency",
        "f3net_frequency",
        "steganography_scan",
        "prnu_sensor_verification",
        # Forgery detectors that operate on rendered content but detect tampering
        # (kept with integrity per design decision).
        "detect_font_inconsistency",
        "detect_ui_overlay_forgery",
    }
)

# ── Agent 3 — Object / Content (what does the image contain?) ────────────────
AGENT3_CONTENT: frozenset[str] = frozenset(
    {
        "object_detection",
        "scene_incongruence",
        "lighting_consistency",
        "lighting_correlation_initial",
        "scale_validation",
        "contraband_database",
        "vector_contraband_search",
        "screenshot_scene_applicability",
        "screenshot_layout_forensics",
        "secondary_classification",
        "adversarial_robustness_check",
        "reverse_image_search",
        "lens_style_multimodal_scan",
        # Content understanding — MOVED here from Agent 1: these answer "what is in
        # the image", which is Agent 3's axis, not image integrity.
        "analyze_image_content",
        "extract_text_from_image",
        "extract_evidence_text",
    }
)

# ── Agent 5 — Metadata / Provenance (where did it come from?) ─────────────────
AGENT5_METADATA: frozenset[str] = frozenset(
    {
        "file_hash_verify",
        "exif_extract",
        "file_structure_analysis",
        "hex_signature_scan",
        "compression_risk_audit",
        "timestamp_analysis",
        "metadata_anomaly_score",
        "exif_isolation_forest",
        "provenance_chain_verify",
        "camera_profile_match",
        "astro_grounding",
        "gps_timezone_validate",
    }
)

# ── Cross-cutting / system tools — not owned by a single analysis agent ───────
SHARED_TOOLS: frozenset[str] = frozenset(
    {
        "visual_evidence_profile",
        "shared_visual_evidence_profile",
        "read_shared_image_context",
        "gemini_deep_forensic",  # deprecated compatibility alias
        "inter_agent_call",
    }
)

_OWNER: dict[str, str] = {}
for _t in AGENT1_INTEGRITY:
    _OWNER[_t] = "Agent1"
for _t in AGENT3_CONTENT:
    _OWNER[_t] = "Agent3"
for _t in AGENT5_METADATA:
    _OWNER[_t] = "Agent5"

# Image specialist agents that participate in ownership reassignment.
_IMAGE_AGENTS: frozenset[str] = frozenset({"Agent1", "Agent3", "Agent5"})


def owner_of(tool: str) -> str | None:
    """Return the agent that owns `tool`, or None for shared/unknown tools."""
    if tool in SHARED_TOOLS:
        return None
    return _OWNER.get(tool)


def tools_owned_by(agent_id: str) -> frozenset[str]:
    """All tools owned by `agent_id` per the taxonomy."""
    return frozenset(t for t, a in _OWNER.items() if a == agent_id)


def resolve_owner(current_agent: str, tool: str) -> str:
    """The agent that SHOULD run `tool`.

    Returns the taxonomy owner when the tool is owned by an image specialist
    agent; otherwise leaves it with `current_agent` (shared/infrastructure tools
    and tools with no declared owner are never moved).
    """
    o = owner_of(tool)
    if o in _IMAGE_AGENTS:
        return o
    return current_agent
