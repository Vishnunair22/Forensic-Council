import asyncio
import json
import time
from typing import Any
from uuid import UUID, uuid4

from core.persistence.redis_client import get_redis_client
from core.structured_logging import get_logger
from core.visual_context_models import VisualContext

logger = get_logger(__name__)

# Single-flight preflight lock TTL (seconds). Must exceed the Gemini preflight
# timeout; auto-expires so a crashed creator can never deadlock the flow.
_PREFLIGHT_LOCK_TTL = 120

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
    # Layer 1: Check InterAgentBus.
    # The bus profile is often a FLAT finding dict (Agent 1 overwrites the
    # preflight VisualContext dump with its visual_evidence_profile result), which
    # is NOT VisualContext-shaped — blindly validating it raised on every call and
    # fell through to Redis. Only validate when the payload carries the nested
    # VisualContext structure; otherwise skip straight to the persisted layers.
    if inter_agent_bus:
        try:
            data = inter_agent_bus.get_visual_profile(session_id)
            if isinstance(data, dict) and any(
                k in data
                for k in ("image_integrity_context", "object_scene_context", "metadata_visual_context")
            ):
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
            prompt_version = 2
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

    # Any on-device provider is a LOCAL (screening-tier, not court-defensible) source.
    # "local_media_profile" is the audio/video/document analog of the image ensemble;
    # mislabeling it llm_assisted would wrongly mark it court-defensible AND suppress
    # the report's no-holistic-model coverage caveat (gated on external_llm_used).
    _local_providers = ("local_visual_ensemble", "local", "local_media_profile")
    source_val = "local_ensemble" if finding.provider_used in _local_providers else "llm_assisted"
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

    # Visible provenance + derived scene clues from the local ensemble (timestamps,
    # device/platform, app, plus weapons/documents/people/lighting/regions/edits).
    # Populated so the no-Gemini path reaches parity with the Gemini visual context.
    _clues = getattr(finding, "_visible_metadata_clues", {}) or {}

    # Only surface signals as "manipulation indicators" when the holistic verdict
    # actually supports manipulation. Under an AUTHENTIC / CANNOT_DETERMINE verdict
    # the ensemble's screening signals are either clean notes or uncorroborated
    # leads the ensemble itself declined to escalate — listing them here makes the
    # visual context read "ELA anomaly detected (84 regions)" beside an authentic
    # verdict (the natural-image false-positive narrative). Keep the raw tool
    # metrics on the findings; the visual context must stay verdict-consistent.
    _verdict_alert = verdict in ("SUSPICIOUS", "LIKELY_MANIPULATED", "AI_GENERATED")
    _visible_manip = list(finding.manipulation_signals or []) if _verdict_alert else []

    image_integrity_context = ImageIntegrityContext(
        visible_manipulation_signals=_visible_manip,
        editing_or_compositing_signals=list(_clues.get("editing_signals", []) or []),
        regions_for_followup=list(_clues.get("regions_for_followup", []) or []),
        integrity_assessment=integrity_assessment,
        confidence=finding.confidence
    )

    object_scene_context = ObjectSceneContext(
        scene_description=finding.content_description or "",
        objects=list(finding.detected_objects or []),
        weapons_or_dangerous_items=list(_clues.get("weapons", []) or []),
        documents_or_ids=list(_clues.get("documents", []) or []),
        people=list(_clues.get("people", []) or []),
        visible_text=list(finding._extracted_text or []),
        confidence=finding.confidence
    )

    metadata_visual_context = MetadataVisualContext(
        visible_timestamps=list(_clues.get("visible_timestamps", []) or []),
        visible_location_clues=list(_clues.get("location_clues", []) or []),
        device_or_platform_clues=list(_clues.get("device_platform_clues", []) or []),
        software_or_app_clues=list(_clues.get("software_clues", []) or []),
        lighting_weather_season_clues=list(_clues.get("lighting_weather_season", []) or []),
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


# A visual context earns the long (24h) cross-session by-hash TTL only when it is a
# genuinely high-quality ("top tier") Gemini read: an authoritative LLM result, with
# usable content and adequate self-reported confidence. Everything else — local-
# ensemble fallbacks, low-confidence or content-less Gemini replies — gets a short
# TTL so Gemini is re-attempted promptly instead of a mediocre read being locked in
# for a day (the StyleGAN-face false-negative trap). NOTE: we deliberately do NOT
# require a decisive authenticity_verdict: for audio/video/document evidence the
# verdict is intentionally deferred to the modality tools, so the context's value is
# its description — gating on a decisive verdict would wrongly demote good non-image
# reads (which legitimately carry CANNOT_DETERMINE).
_TOP_TIER_MIN_CONFIDENCE = 0.7
_TOP_TIER_TTL_S = 86400   # 24h — authoritative Gemini read
_LOCAL_STABLE_TTL_S = 14400  # 4h — good local read when Gemini is permanently off
_SHORT_TTL_S = 900        # 15m — re-attempt Gemini soon (transient fallback)


def _gemini_configured_enabled() -> bool:
    """True when Gemini is a configured provider (hybrid mode). When False — the
    local_ensemble-only baseline or a hard-disabled key — there is no point holding
    a local context for only 15m to 're-attempt Gemini': Gemini will never be tried,
    so re-running the full ensemble every 15m on a repeated file is pure waste."""
    try:
        from core.config import get_settings
        s = get_settings()
        if getattr(s, "local_only_analysis", False):
            return False
        chain = str(getattr(s, "vision_provider_chain", "") or "")
        return "gemini" in chain and bool(getattr(s, "remote_visual_profile_allowed", True))
    except Exception:  # noqa: S110 - cache metadata annotation must not break retrieval
        return False


def _is_top_tier_context(context: "VisualContext") -> bool:
    """True only for a high-quality authoritative Gemini read worth caching 24h."""
    if not bool(getattr(context, "external_llm_used", False)):
        return False
    if getattr(context, "source", "") != "llm_assisted":
        return False
    try:
        confidence = float(getattr(context, "confidence", 0.0) or 0.0)
    except (TypeError, ValueError):
        confidence = 0.0
    if confidence < _TOP_TIER_MIN_CONFIDENCE:
        return False
    has_content = bool(
        (getattr(context, "scene_description", "") or "").strip()
        or (getattr(context, "file_type_assessment", "") or "").strip()
        or (getattr(context, "extracted_text", None) or [])
    )
    return has_content


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
            prompt_version = 2
            # Top-tier authoritative Gemini reads are cached 24h (deterministic +
            # quota-friendly: a re-upload of the same bytes reuses it with no Gemini
            # call). Anything weaker — local-ensemble fallbacks, or low-confidence /
            # content-less Gemini replies — gets a short TTL so Gemini is re-attempted
            # promptly rather than a mediocre read being locked in for a day (the
            # GAN-face false-negative trap: a cached local "authentic" read of a
            # StyleGAN portrait that skipped Gemini for 24h).
            _top_tier = _is_top_tier_context(context)
            # A good local read (has content) earns a 4h TTL ONLY when Gemini is not
            # configured — re-attempting it is moot, so don't re-run the ensemble every
            # 15m on a repeated file (no-Gemini/outage efficiency + stability). In
            # hybrid mode a local context keeps the 15m TTL so Gemini is re-tried (the
            # GAN-face trap protection is preserved exactly).
            # "Content" must be a REAL read, not a degraded/failed-ensemble fallback
            # (e.g. a "could not analyze this image" sentinel with confidence 0.0,
            # file_type=unknown — produced when the ensemble couldn't load models under
            # memory pressure). Caching such a failure for 4h would lock a blank
            # object/scene context onto the file. Require a non-trivial confidence and
            # a real scene/file-type signal that is not the failure sentinel.
            try:
                _ctx_conf = float(getattr(context, "confidence", 0.0) or 0.0)
            except (TypeError, ValueError):
                _ctx_conf = 0.0
            _scene = (getattr(context, "scene_description", "") or "").strip()
            _ftype = (getattr(context, "file_type_assessment", "") or "").strip()
            _is_failure_read = (
                _ctx_conf <= 0.0
                or _ftype.lower() in ("", "unknown")
                or "could not analyze" in _scene.lower()
                or "could not be categor" in _scene.lower()
            )
            _has_content = bool(
                _scene or _ftype or (getattr(context, "extracted_text", None) or [])
            )
            _stable_local = (
                (not _top_tier)
                and _has_content
                and not _is_failure_read
                and _ctx_conf >= 0.35
                and not _gemini_configured_enabled()
            )
            _ttl = _TOP_TIER_TTL_S if _top_tier else (_LOCAL_STABLE_TTL_S if _stable_local else _SHORT_TTL_S)
            await redis.set(f"visual_context_by_hash:{sha256}:{prompt_version}", context_json, ex=_ttl)
            if not _top_tier:
                logger.info(
                    "Cached non-top-tier visual context",
                    sha256=sha256[:12],
                    source=getattr(context, "source", None),
                    external_llm_used=getattr(context, "external_llm_used", None),
                    confidence=getattr(context, "confidence", None),
                    ttl_s=_ttl,
                    stable_local=_stable_local,
                )
    except Exception as e:
        logger.warning("Failed saving visual context to Redis", error=str(e))

async def _acquire_preflight_lock(redis: Any, sha256: str, token: str) -> bool:
    """Atomically elect a single preflight creator for `sha256` (Redis SET NX EX).

    Returns True only for the elected creator. Any error (incl. Redis down)
    returns False so the caller proceeds unlocked — degrading to prior behaviour
    rather than failing.
    """
    if not sha256:
        return False
    try:
        return bool(
            await redis.set(f"visual_context_lock:{sha256}", token, nx=True, ex=_PREFLIGHT_LOCK_TTL)
        )
    except Exception:
        return False


async def _release_preflight_lock(redis: Any, sha256: str, token: str) -> None:
    """Release the preflight lock iff this caller still owns it (token match)."""
    try:
        key = f"visual_context_lock:{sha256}"
        cur = await redis.get(key)
        if isinstance(cur, bytes | bytearray):
            cur = cur.decode()
        if cur == token:
            await redis.delete(key)
    except Exception as exc:
        logger.debug("Failed releasing preflight lock", sha256=sha256, error=str(exc))


async def _wait_for_concurrent_creator(
    redis: Any,
    session_id: str,
    sha256: str,
    working_memory: Any,
    inter_agent_bus: Any,
) -> "VisualContext | None":
    """Wait for the elected creator's visual context.

    Returns the context as soon as it lands. Returns None promptly if the
    creator's lock disappears without producing a context (creator failed), so a
    dead winner never stalls the loser for the full lock TTL.
    """
    deadline = time.monotonic() + _PREFLIGHT_LOCK_TTL
    while time.monotonic() < deadline:
        ctx = await get_visual_context(
            session_id=session_id,
            sha256=sha256,
            working_memory=working_memory,
            inter_agent_bus=inter_agent_bus,
        )
        if ctx is not None:
            return ctx
        try:
            if not await redis.get(f"visual_context_lock:{sha256}"):
                return None
        except Exception:
            return None
        await asyncio.sleep(0.5)
    return None


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
        # II.3-3 — mark the read as cache-reused so the report can disclose it was
        # not produced fresh this session (content-hash keyed; same bytes = same read).
        try:
            existing.cached = True
        except Exception:  # noqa: S110 - legacy cache entries may not allow transient attributes
            pass
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

    # ── Single-flight guard ───────────────────────────────────────────────
    # The API route (backend process) and the worker pipeline both call this for
    # the same file; without coordination a cross-process race fires the Gemini
    # preflight twice, doubling RPM/RPD. A short-lived Redis SETNX lock keyed by
    # sha256 elects ONE creator; concurrent callers wait for that creator's
    # result instead of spending quota. The lock auto-expires (TTL) so a crashed
    # creator can never deadlock; if Redis is unavailable we degrade to the prior
    # unlocked behaviour.
    redis = None
    lock_token = uuid4().hex
    have_lock = False
    try:
        redis = await get_redis_client()
        have_lock = await _acquire_preflight_lock(redis, sha256, lock_token)
    except Exception:  # noqa: S110 - Redis preflight is optional; continue without it
        redis = None

    if redis is not None and not have_lock:
        shared = await _wait_for_concurrent_creator(
            redis, session_id, sha256, working_memory, inter_agent_bus
        )
        if shared is not None:
            logger.info(
                "Preflight single-flight: reused concurrent creator's context (no Gemini call)",
                session_id=session_id,
                source=shared.source,
            )
            # Re-save under this session's layers so consumers (which look up by
            # session_id) see it even if the creator keyed it differently.
            await save_visual_context(
                session_id=session_id,
                sha256=sha256,
                context=shared,
                working_memory=working_memory,
                inter_agent_bus=inter_agent_bus,
            )
            return shared
        # Concurrent creator vanished without producing a context → create directly.

    try:
        if have_lock:
            # Double-checked locking: another creator may have finished between
            # our cache miss and acquiring the lock.
            existing2 = await get_visual_context(
                session_id=session_id,
                sha256=sha256,
                working_memory=working_memory,
                inter_agent_bus=inter_agent_bus,
            )
            if existing2:
                await save_visual_context(
                    session_id=session_id,
                    sha256=sha256,
                    context=existing2,
                    working_memory=working_memory,
                    inter_agent_bus=inter_agent_bus,
                )
                return existing2

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

        # ── Local ensemble fallback (IMAGE evidence only) ─────────────────────
        # analyze_local_visual_profile is an IMAGE ensemble (CLIP/YOLO/ELA/Noiseprint).
        # Running it on audio/video produces image-forensics nonsense ("Live
        # Photograph", "Visual content could not be categorized. Forensic signals:
        # ELA/Noiseprint/Splicing…") that leaks into the audio/video agent's findings.
        # When the native (Gemini) read fails for non-image evidence — e.g. an HTTP 429
        # on the audio File API — there is NO local holistic substitute; leave the
        # context absent so the modality-specific tools (audio/video forensics) carry
        # the analysis instead of a fabricated visual read.
        if context is None:
            import mimetypes as _mt_guard

            _fallback_mime = (_mt_guard.guess_type(file_path)[0] or "").lower()
            _is_image_fallback = _fallback_mime.startswith("image/") or (
                not _fallback_mime
                and str(file_path).lower().rsplit(".", 1)[-1]
                in ("jpg", "jpeg", "png", "webp", "gif", "bmp")
            )
            if not _is_image_fallback:
                # Audio / video / document: the IMAGE ensemble (CLIP/YOLO/ELA) would
                # fabricate image-forensics nonsense. Instead build the LOCAL MEDIA
                # profile (the no-Gemini holistic substitute: audio properties, a
                # captioned video key-frame, or extracted document text + coverage
                # caveat) and CACHE it here — symmetric with the image fallback below.
                # Caching the context makes the agent's later read_shared_image_context
                # a cache hit, so there is a SINGLE Gemini→local handoff: no second
                # Gemini attempt and no re-running the frame-caption / text-extract in
                # the deep phase.
                try:
                    from core.vision_local_ensemble import analyze_local_media_profile

                    _media_finding = await analyze_local_media_profile(file_path, _fallback_mime)
                    context = build_visual_context_from_finding(
                        session_id, sha256, _media_finding
                    )
                    logger.info(
                        "Local media profile preflight visual context created",
                        session_id=session_id,
                        mime=_fallback_mime or "unknown",
                        file_type=context.file_type_assessment,
                    )
                except Exception as exc:
                    logger.warning(
                        "Local media profile failed — visual context unavailable",
                        session_id=session_id,
                        error=str(exc),
                    )
                    return None
        if context is None:
            try:
                import mimetypes

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
    finally:
        if have_lock and redis is not None:
            await _release_preflight_lock(redis, sha256, lock_token)


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
        "weapons_or_dangerous_items": list(
            context.object_scene_context.weapons_or_dangerous_items or []
        ),
        # Merge AI-generation signals (synthetic-speech / deepfake / AI-generated-text
        # reasons) into the manipulation signals so the actual "why" reaches the
        # agent finding — not just the neutral content description.
        "manipulation_signals": list(
            context.image_integrity_context.visible_manipulation_signals or []
        ) + list(
            getattr(context.image_integrity_context, "ai_generation_signals", []) or []
        ),
        "ai_generation_signals": list(
            getattr(context.image_integrity_context, "ai_generation_signals", []) or []
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
