import asyncio
import json
import time
from typing import Any
from uuid import UUID

from core.persistence.redis_client import get_redis_client
from core.structured_logging import get_logger
from core.visual_context_models import VisualContext

logger = get_logger(__name__)

async def get_visual_context(
    session_id: str,
    sha256: str | None = None,
    working_memory: Any = None,
    inter_agent_bus: Any = None,
) -> VisualContext | None:
    """
    Retrieve the visual context for a session or SHA256 hash.
    Checks three layers of storage:
      1. In-memory inter-agent bus
      2. Working memory state
      3. Redis persistence (by session_id, then by sha256)
    """
    # Layer 1: Check InterAgentBus
    if inter_agent_bus:
        try:
            data = inter_agent_bus.get_visual_profile(session_id)
            if data:
                return VisualContext.model_validate(data)
        except Exception as e:
            logger.debug("Failed retrieving visual context from inter-agent bus", error=str(e))

    # Layer 2: Check Working Memory
    if working_memory:
        try:
            state = await working_memory.get_state(UUID(session_id), "Agent1")
            data = None
            if hasattr(state, "model_extra") and state.model_extra:
                data = state.model_extra.get("shared_visual_context")
            if data:
                return VisualContext.model_validate(data)
        except Exception as e:
            logger.debug("Failed retrieving visual context from working memory", error=str(e))

    # Layer 3: Check Redis
    try:
        redis = await get_redis_client()
        raw_data = await redis.get(f"visual_context:{session_id}")
        if raw_data:
            data = json.loads(raw_data)
            return VisualContext.model_validate(data)

        if sha256:
            prompt_version = 1
            raw_data = await redis.get(f"visual_context_by_hash:{sha256}:{prompt_version}")
            if raw_data:
                data = json.loads(raw_data)
                return VisualContext.model_validate(data)
    except Exception as e:
        logger.debug("Failed retrieving visual context from Redis", error=str(e))

    return None


def build_visual_context_from_finding(
    session_id: str,
    evidence_sha256: str,
    finding: Any
) -> VisualContext:
    """Helper to convert VisualEvidenceFinding into the standardized VisualContext model."""
    import datetime

    from core.visual_context_models import (
        DetectedObject,
        ImageIntegrityContext,
        MetadataVisualContext,
        ObjectSceneContext,
        VisualContext,
    )

    source_val = "llm_assisted" if (finding.provider_used != "local_visual_ensemble" and finding.provider_used != "local") else "local_ensemble"
    external_llm_used = (source_val == "llm_assisted")

    raw_verdict = str(finding._authenticity_verdict or "").upper()
    verdict = "CANNOT_DETERMINE"
    if "AUTHENTIC" in raw_verdict:
        verdict = "AUTHENTIC"
    elif "SUSPICIOUS" in raw_verdict:
        verdict = "SUSPICIOUS"
    elif "MANIPULATED" in raw_verdict or "TAMPERED" in raw_verdict:
        verdict = "LIKELY_MANIPULATED"
    elif "AI_GENERATED" in raw_verdict or "DEEPFAKE" in raw_verdict:
        verdict = "AI_GENERATED"

    integrity_assessment = "cannot_determine"
    if verdict == "AUTHENTIC":
        integrity_assessment = "no_visible_issue"
    elif verdict == "SUSPICIOUS":
        integrity_assessment = "suspicious"
    elif verdict == "LIKELY_MANIPULATED":
        integrity_assessment = "likely_manipulated"
    elif verdict == "AI_GENERATED":
        integrity_assessment = "ai_generated_suspect"

    image_integrity_context = ImageIntegrityContext(
        visible_manipulation_signals=list(finding.manipulation_signals or []),
        integrity_assessment=integrity_assessment,
        confidence=finding.confidence
    )

    object_scene_context = ObjectSceneContext(
        scene_description=finding.content_description or "",
        objects=list(finding.detected_objects or []),
        visible_text=list(finding._extracted_text or []),
        confidence=finding.confidence
    )

    # Visible provenance clues extracted from the image (timestamps, device/
    # platform, app). Populated by the local ensemble so the metadata-provenance
    # section is filled even on the no-Gemini path.
    _clues = getattr(finding, "_visible_metadata_clues", {}) or {}
    metadata_visual_context = MetadataVisualContext(
        visible_timestamps=list(_clues.get("visible_timestamps", []) or []),
        visible_location_clues=list(_clues.get("location_clues", []) or []),
        device_or_platform_clues=list(_clues.get("device_platform_clues", []) or []),
        software_or_app_clues=list(_clues.get("software_clues", []) or []),
        metadata_consistency_notes=[finding._metadata_visual_consistency] if finding._metadata_visual_consistency else [],
        confidence=finding.confidence
    )

    detected_objs = [DetectedObject(label=obj, confidence=finding.confidence) for obj in (finding.detected_objects or [])]

    return VisualContext(
        session_id=session_id,
        evidence_sha256=evidence_sha256,
        source=source_val,
        provider_name=finding.provider_used,
        external_llm_used=external_llm_used,
        image_integrity_context=image_integrity_context,
        object_scene_context=object_scene_context,
        metadata_visual_context=metadata_visual_context,
        extracted_text=list(finding._extracted_text or []),
        detected_objects=detected_objs,
        interface_elements=[finding._interface_identification] if finding._interface_identification else [],
        visible_timestamps=list(_clues.get("visible_timestamps", []) or []),
        scene_description=finding.content_description or "",
        file_type_assessment=finding.file_type_assessment or "",
        authenticity_verdict=verdict,
        confidence=finding.confidence,
        tool_coverage=dict(finding.tool_coverage or {}),
        provider_attempts=list(finding.provider_attempts or []),
        created_at=datetime.datetime.utcnow().isoformat()
    )


async def save_visual_context(
    session_id: str,
    sha256: str,
    context: VisualContext,
    working_memory: Any = None,
    inter_agent_bus: Any = None,
) -> None:
    """
    Save the visual context across all three storage layers:
      1. In-memory inter-agent bus
      2. Working memory state
      3. Redis persistence (by session_id and by sha256)
    """
    # Layer 1: Save to InterAgentBus
    if inter_agent_bus:
        try:
            inter_agent_bus.set_visual_profile(session_id, context.model_dump())
        except Exception as e:
            logger.warning("Failed saving visual context to inter-agent bus", error=str(e))

    # Layer 2: Save to Working Memory
    if working_memory:
        try:
            await working_memory.update_state(
                session_id=UUID(session_id),
                agent_id="Agent1",
                updates={"shared_visual_context": context.model_dump()}
            )
        except Exception as e:
            logger.warning("Failed saving visual context to working memory", error=str(e))

    # Layer 3: Save to Redis
    try:
        redis = await get_redis_client()
        context_json = context.model_dump_json()
        await redis.set(f"visual_context:{session_id}", context_json, ex=14400)  # 4 hour TTL
        if sha256:
            prompt_version = 1
            await redis.set(f"visual_context_by_hash:{sha256}:{prompt_version}", context_json, ex=86400)  # 24 hour TTL
    except Exception as e:
        logger.warning("Failed saving visual context to Redis", error=str(e))

async def create_visual_context_preflight(
    session_id: str,
    file_path: str,
    sha256: str,
    config: Any,
    working_memory: Any = None,
    inter_agent_bus: Any = None,
) -> "VisualContext | None":
    """
    Create rich visual context before any agent executes.

    Fires a single Gemini call with a three-section structured prompt that covers
    Agent1 (image integrity), Agent3 (object/scene), and Agent5 (metadata provenance).
    The result is stored in Redis keyed by both session_id and sha256 so:
      - All agents start warm on their first access via get_visual_context()
      - The same file uploaded again hits the 24-hour hash-keyed cache, costing
        zero additional Gemini RPM/RPD

    Falls back to the local CLIP/YOLO ensemble if Gemini is unavailable or fails.
    Returns None only if both Gemini and the local ensemble fail.
    """
    # Fast path: context already exists (same session re-queried, or same file
    # previously uploaded and still within the 24-hour hash-TTL).
    existing = await get_visual_context(
        session_id=session_id,
        sha256=sha256,
        working_memory=working_memory,
        inter_agent_bus=inter_agent_bus,
    )
    if existing:
        logger.info(
            "Preflight visual context cache hit — skipping Gemini call",
            session_id=session_id,
            source=existing.source,
        )
        # A hit may have come from the 24h hash-keyed cache (same file, new
        # session). Consumers look up by session_id only (no sha256), so re-save
        # under the current session/layers — otherwise agents see "Visual context
        # not found" and ground on empty context despite a valid cache hit.
        await save_visual_context(
            session_id=session_id,
            sha256=sha256,
            context=existing,
            working_memory=working_memory,
            inter_agent_bus=inter_agent_bus,
        )
        return existing

    context: VisualContext | None = None

    # ── Attempt Gemini ────────────────────────────────────────────────────
    try:
        from core.gemini_client import GeminiVisionClient

        client = GeminiVisionClient(config)
        if client._enabled:
            context = await client.analyze_visual_context_preflight(
                file_path=file_path,
                session_id=session_id,
                sha256=sha256,
            )
            logger.info(
                "Gemini preflight visual context created",
                session_id=session_id,
                file_type=context.file_type_assessment,
                verdict=context.authenticity_verdict,
                model=context.provider_name,
            )
    except Exception as exc:
        logger.warning(
            "Gemini preflight failed — falling back to local ensemble",
            session_id=session_id,
            error=str(exc),
        )

    # ── Local ensemble fallback ───────────────────────────────────────────
    if context is None:
        try:
            import mimetypes
            from uuid import UUID

            from core.evidence import ArtifactType, EvidenceArtifact
            from core.vision_local_ensemble import analyze_local_visual_profile

            artifact = EvidenceArtifact.create_root(
                artifact_type=ArtifactType.ORIGINAL,
                file_path=file_path,
                content_hash=sha256,
                action="preflight_visual_context",
                agent_id="system",
                session_id=UUID(session_id),
                metadata={"mime_type": mimetypes.guess_type(file_path)[0] or ""},
            )
            local_finding = await analyze_local_visual_profile(artifact=artifact)
            context = build_visual_context_from_finding(session_id, sha256, local_finding)
            logger.info(
                "Local ensemble preflight visual context created",
                session_id=session_id,
            )
        except Exception as exc:
            logger.warning(
                "Local ensemble preflight also failed — visual context unavailable",
                session_id=session_id,
                error=str(exc),
            )
            return None

    # ── Persist to all three storage layers ──────────────────────────────
    await save_visual_context(
        session_id=session_id,
        sha256=sha256,
        context=context,
        working_memory=working_memory,
        inter_agent_bus=inter_agent_bus,
    )

    return context


async def wait_for_visual_context(
    session_id: str,
    sha256: str | None = None,
    working_memory: Any = None,
    inter_agent_bus: Any = None,
    timeout: float = 30.0,
) -> VisualContext | None:
    """
    Wait (poll) for visual context to be created/stored.
    """
    t0 = time.monotonic()
    while time.monotonic() - t0 < timeout:
        context = await get_visual_context(
            session_id=session_id,
            sha256=sha256,
            working_memory=working_memory,
            inter_agent_bus=inter_agent_bus
        )
        if context:
            return context
        await asyncio.sleep(1.0)
    return None


def visual_context_to_profile_dict(context: VisualContext) -> dict:
    """Convert VisualContext back into the dictionary format expected by the agents.

    Includes file_type_assessment, scene_inconsistencies, and device_platform_clues
    so that visual_grounding.py can apply calibration without a separate Redis lookup.
    """
    evidence_verdict = (
        "POSITIVE"
        if context.authenticity_verdict in ("LIKELY_MANIPULATED", "AI_GENERATED", "SUSPICIOUS")
        else ("NEGATIVE" if context.authenticity_verdict == "AUTHENTIC" else "INCONCLUSIVE")
    )
    # The visual profile is court-defensible ONLY when it came from the real
    # remote vision model (Gemini). When it fell back to the local heuristic
    # ensemble it is a screening signal — same tier as the classical tools — so
    # it must not drive a court-defensible POSITIVE on its own. This makes Gemini
    # authoritative for the verdict while honestly downgrading the fallback.
    is_remote_gemini = bool(context.external_llm_used) and context.source != "local_ensemble"
    return {
        "content_description": context.scene_description,
        "confidence_raw": context.confidence,
        "status": "CONFIRMED",
        "evidence_verdict": evidence_verdict,
        "verdict": context.authenticity_verdict,
        "court_defensible": is_remote_gemini,
        # Grounding fields — used by core/visual_grounding.py
        "file_type_assessment": context.file_type_assessment,
        "scene_inconsistencies": list(
            context.object_scene_context.scene_inconsistencies or []
        ),
        "device_platform_clues": list(
            context.metadata_visual_context.device_or_platform_clues or []
        ),
        # Standard agent-facing fields
        "detected_objects": [obj.label for obj in context.detected_objects],
        "manipulation_signals": list(
            context.image_integrity_context.visible_manipulation_signals or []
        ),
        "extracted_text": context.extracted_text,
        "interface_identification": (
            context.interface_elements[0] if context.interface_elements else ""
        ),
        "metadata": {
            "tool_name": "shared_visual_evidence_profile",
            "analysis_source": context.provider_name or "visual_context_store",
            "provider_used": context.provider_name or "visual_context_store",
            "external_ai_used": context.external_llm_used,
            "fallback_applied": context.source == "local_ensemble",
            "provider_attempts": context.provider_attempts,
            "tool_coverage": context.tool_coverage,
        },
    }

