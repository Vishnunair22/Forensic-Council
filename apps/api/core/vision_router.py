import asyncio
import hashlib
import mimetypes
from typing import Any
from uuid import uuid4

from core.config import Settings
from core.evidence import ArtifactType, EvidenceArtifact
from core.gemini_client import (
    GeminiVisionClient,
    GeminiVisionFinding,
)
from core.image_routing import build_image_forensic_routing
from core.structured_logging import get_logger
from core.vision_local_ensemble import analyze_local_visual_profile
from core.vision_types import VisualEvidenceFinding

logger = get_logger(__name__)
analyze_local_ensemble = analyze_local_visual_profile
_ORIGINAL_LOCAL_ENSEMBLE = analyze_local_visual_profile


class VisionRouter:
    """
    Vision Router Facade.

    Implements the strict hybrid visual-profile contract:
      - Agent 1 may call Gemini once per investigation session.
      - All other agents and local_only mode always route to the local ensemble.
      - When Gemini fails (or is unavailable) the local ensemble is the
        deterministic fallback — no API failure can block evidentiary output.

    Routing rules:
      local_only               → local_ensemble
      agent_id != "Agent1"     → local_ensemble
      Gemini available + Agent1 → Gemini → fallback → local_ensemble
      Gemini unavailable       → local_ensemble

    Returns a VisualEvidenceFinding in all code paths so downstream consumers
    never need to handle a provider-specific type.
    """

    # F5-2: Module-level set of running validation tasks + once-validated flag.
    _validation_tasks: set[asyncio.Task] = set()
    _validated_once: bool = False

    @classmethod
    def configure_quota_pool(cls, max_concurrent: int) -> None:
        """Forward concurrency settings to GeminiVisionClient."""
        GeminiVisionClient.configure_quota_pool(max_concurrent)

    def __init__(self, config: Settings):
        self.config = config
        self.gemini_client = GeminiVisionClient(config)

        self.local_only = config.local_only_analysis
        self._gemini_enabled = (
            not self.local_only
            and "gemini" in (getattr(config, "vision_provider_chain", "gemini,local_ensemble") or "")
            and config.remote_visual_profile_allowed
        )

        # F5-2: Prune unavailable models once per process lifetime.
        if self._gemini_enabled and not VisionRouter._validated_once:
            VisionRouter._validated_once = True
            try:
                loop = asyncio.get_event_loop()
                if loop.is_running():
                    task = loop.create_task(self.gemini_client.validate_model_availability())
                    VisionRouter._validation_tasks.add(task)
                    task.add_done_callback(VisionRouter._validation_tasks.discard)
            except RuntimeError:
                logger.warning("No running event loop — skipping Gemini model validation")

        logger.info(
            "VisionRouter initialized",
            execution_mode=config.analysis_execution_mode,
            gemini_enabled=self._gemini_enabled,
            local_only=self.local_only,
        )

    @staticmethod
    def _coerce_artifact(artifact: EvidenceArtifact | str) -> EvidenceArtifact:
        if isinstance(artifact, EvidenceArtifact):
            return artifact
        file_path = str(artifact)
        try:
            with open(file_path, "rb") as fh:
                content_hash = hashlib.sha256(fh.read()).hexdigest()
        except OSError:
            content_hash = ""
        return EvidenceArtifact.create_root(
            artifact_type=ArtifactType.ORIGINAL,
            file_path=file_path,
            content_hash=content_hash,
            action="vision_router_input",
            agent_id="system",
            session_id=uuid4(),
            metadata={"mime_type": mimetypes.guess_type(file_path)[0] or ""},
        )

    @staticmethod
    def _normalize_gemini_profile(gf: GeminiVisionFinding) -> VisualEvidenceFinding:
        """Convert a GeminiVisionFinding into a provider-neutral VisualEvidenceFinding.

        Preserves all forensic signal data while stripping Gemini-specific
        type information. The provider_used field is set to 'gemini' so
        downstream consumers can distinguish AI-assisted vs local-only findings.
        """
        verdict = getattr(gf, "_authenticity_verdict", "AUTHENTIC") or "AUTHENTIC"
        model_used = gf.model_used or "gemini-2.5-flash"
        is_local_fallback = model_used.startswith("local_")
        provider_used = "local_visual_ensemble" if is_local_fallback else "gemini"

        content_description = gf.content_description or ""
        routing = build_image_forensic_routing(
            dict(getattr(gf, "_forensic_routing", {}) or {}),
            description=content_description,
        )
        return VisualEvidenceFinding(
            analysis_type=getattr(gf, "analysis_type", "visual_evidence_profile") or "visual_evidence_profile",
            model_used=model_used,
            content_description=content_description,
            provider_used=provider_used,
            manipulation_signals=list(gf.manipulation_signals or []),
            detected_objects=list(gf.detected_objects or []),
            contextual_anomalies=list(gf.contextual_anomalies or []),
            file_type_assessment=gf.file_type_assessment or "",
            confidence=gf.confidence or 0.0,
            court_defensible=bool(gf.court_defensible),
            caveat=gf.caveat or "",
            raw_response=gf.raw_response or "",
            latency_ms=gf.latency_ms or 0.0,
            error=gf.error,
            from_cache=bool(gf.from_cache),
            _extracted_text=list(getattr(gf, "_extracted_text", []) or []),
            _interface_identification=getattr(gf, "_interface_identification", "") or "",
            _contextual_narrative=getattr(gf, "_contextual_narrative", "") or "",
            _authenticity_verdict=verdict,
            _metadata_visual_consistency=getattr(gf, "_metadata_visual_consistency", "") or "",
            _forensic_routing=routing,
            _forensic_specifics=getattr(gf, "_forensic_specifics", "") or "",
            provider_attempts=[],
            fallback_applied=is_local_fallback,
            fallback_reason=gf.caveat if is_local_fallback else "",
            tool_coverage={},
            degradation_flags=[],
        )

    async def _run_local_visual_profile(
        self,
        artifact: EvidenceArtifact,
        exif_summary: dict[str, Any] | None = None,
        is_screen_capture_like: bool = False,
    ) -> VisualEvidenceFinding:
        local_runner = (
            analyze_local_ensemble
            if analyze_local_ensemble is not _ORIGINAL_LOCAL_ENSEMBLE
            else analyze_local_visual_profile
        )
        return await local_runner(
            artifact=artifact,
            exif_summary=exif_summary,
            is_screen_capture_like=is_screen_capture_like,
        )

    async def deep_forensic_analysis(
        self,
        artifact: EvidenceArtifact,
        exif_summary: dict[str, Any] | None = None,
        model_hint: str | None = None,
        signal_callback: Any | None = None,
        persona: str | None = None,
        is_screen_capture_like: bool = False,
        agent_id: str = "",
        session_id: str | None = None,
    ) -> VisualEvidenceFinding:
        """
        Execute a single visual-profile analysis that always returns a
        VisualEvidenceFinding.

        Routing priority (highest to lowest):
          1. Pre-computed preflight VisualContext in Redis (session_id provided)
             → zero extra Gemini calls; agents share the single preflight result.
          2. local_only mode → always local ensemble.
          3. agent_id != "Agent1" → always local ensemble (Gemini reserved for Agent1).
          4. Agent1 + Gemini enabled → attempt Gemini; on any failure → local ensemble.
          5. Gemini not enabled → local ensemble.

        The fallback_applied / fallback_reason / provider_attempts fields are
        populated on the result so every report discloses the actual provenance.
        """
        artifact = self._coerce_artifact(artifact)
        file_path = artifact.file_path
        provider_attempts: list[dict] = []
        errors: list[str] = []

        # ── Priority 1: preflight context already in Redis ─────────────────
        # The /investigate route fires create_visual_context_preflight() as a
        # background task before any agent starts. When that task completes, the
        # VisualContext is in Redis under visual_context:{session_id}. Agents
        # that call deep_forensic_analysis with session_id can reuse it without
        # consuming any additional Gemini RPM/RPD quota.
        if session_id:
            try:
                from core.visual_context_store import (
                    visual_context_to_profile_dict,
                    wait_for_visual_context,
                )

                # Bounded wait, not a one-shot read: the preflight is fired as a
                # background task and may still be in-flight when the first agents
                # reach this point (Gemini latency / rate-limit). Waiting briefly
                # lets every agent share the single preflight result instead of
                # each firing its own Gemini call and racing — which previously
                # left the arbiter with no shared context to corroborate against.
                # Returns immediately once the context lands (the common case).
                preflight_ctx = await wait_for_visual_context(
                    session_id=session_id,
                    sha256=getattr(artifact, "content_hash", None),
                    timeout=20.0,
                )
                if preflight_ctx:
                    logger.info(
                        "VisionRouter: preflight context hit — no Gemini call needed",
                        session_id=session_id,
                        agent_id=agent_id,
                        source=preflight_ctx.source,
                        file_type=preflight_ctx.file_type_assessment,
                    )
                    profile = visual_context_to_profile_dict(preflight_ctx)
                    iface = (
                        preflight_ctx.interface_elements[0]
                        if preflight_ctx.interface_elements
                        else ""
                    )
                    meta_notes = "; ".join(
                        preflight_ctx.metadata_visual_context.metadata_consistency_notes or []
                    )
                    return VisualEvidenceFinding(
                        analysis_type="visual_evidence_profile",
                        model_used=preflight_ctx.provider_name or "preflight",
                        content_description=profile.get("content_description", ""),
                        provider_used=preflight_ctx.provider_name or "preflight",
                        manipulation_signals=list(
                            preflight_ctx.image_integrity_context.visible_manipulation_signals or []
                        ),
                        detected_objects=[
                            obj.label for obj in (preflight_ctx.detected_objects or [])
                        ],
                        contextual_anomalies=list(
                            preflight_ctx.image_integrity_context.ai_generation_signals or []
                        ),
                        file_type_assessment=preflight_ctx.file_type_assessment,
                        confidence=preflight_ctx.confidence,
                        court_defensible=True,
                        from_cache=True,
                        _extracted_text=list(preflight_ctx.extracted_text or []),
                        _interface_identification=iface,
                        _authenticity_verdict=preflight_ctx.authenticity_verdict,
                        _metadata_visual_consistency=meta_notes,
                        provider_attempts=list(preflight_ctx.provider_attempts or []),
                        fallback_applied=preflight_ctx.source != "llm_assisted",
                        fallback_reason="" if preflight_ctx.source == "llm_assisted" else "preflight used local ensemble",
                        tool_coverage=dict(preflight_ctx.tool_coverage or {}),
                    )
            except Exception as _pf_exc:
                logger.debug(
                    "VisionRouter: preflight context lookup failed — proceeding with normal path",
                    session_id=session_id,
                    error=str(_pf_exc),
                )

        # ── short-circuit: local_only or non-Agent1 ────────────────────────
        if self.local_only:
            logger.info("local_only mode — local ensemble", agent_id=agent_id)
            result = await self._run_local_visual_profile(
                artifact=artifact,
                exif_summary=exif_summary,
                is_screen_capture_like=is_screen_capture_like,
            )
            result.provider_attempts = [
                {"provider": "local_visual_ensemble", "reason": "local_only_mode", "success": True}
            ]
            return result

        if agent_id != "Agent1":
            logger.info("Non-Agent1 caller — local ensemble", agent_id=agent_id)
            result = await self._run_local_visual_profile(
                artifact=artifact,
                exif_summary=exif_summary,
                is_screen_capture_like=is_screen_capture_like,
            )
            result.provider_attempts = [
                {"provider": "local_visual_ensemble", "reason": f"agent_id={agent_id} not authorized for Gemini", "success": True}
            ]
            result.fallback_applied = False
            result.fallback_reason = "Visual context provider reserved for Agent1 single-call policy"
            return result

        # ── Agent1 — Gemini is the per-file VISUAL-CONTEXT-CREATION call only ──
        # In the pipeline a session_id is always present and the per-file visual
        # context is created exactly once by the preflight (handled above and reused
        # by every agent/phase). Making a second deep_forensic Gemini call here would
        # duplicate that read and multiply free-tier RPM/RPD usage, which is what
        # saturated quota on deep image runs. Policy: session_id present ⇒ the
        # preflight is the single Gemini touchpoint, so if we reach here without a
        # reusable context we degrade to the local ensemble instead of re-calling
        # Gemini. A direct (no-session) call still allows Gemini for standalone use.
        if session_id:
            logger.info(
                "VisionRouter: preflight-only Gemini policy — no redundant deep call, using local ensemble",
                agent_id=agent_id,
            )
            provider_attempts.append(
                {"provider": "gemini", "success": False, "reason": "preflight_only_policy"}
            )
        elif self._gemini_enabled and self.gemini_client._enabled:
            try:
                logger.info("Attempting Gemini deep forensic analysis for Agent1")
                gf = await self.gemini_client.deep_forensic_analysis(
                    file_path=file_path,
                    exif_summary=exif_summary,
                    model_hint=model_hint,
                    signal_callback=signal_callback,
                    persona=persona,
                    is_screen_capture_like=is_screen_capture_like,
                    agent_id=agent_id,
                )
                if gf and not gf.error:
                    logger.info("Gemini visual profile succeeded for Agent1")
                    result = self._normalize_gemini_profile(gf)
                    if gf.model_used.startswith("local_"):
                        result.provider_attempts = [
                            {"provider": "gemini", "success": False, "error": "Visual context fallback triggered"},
                            {"provider": "local_visual_ensemble", "success": True},
                        ]
                    else:
                        result.provider_attempts = [
                            {"provider": "gemini", "success": True},
                        ]
                    return result
                if gf and gf.error:
                    errors.append(f"Gemini error response: {gf.error}")
                    provider_attempts.append({"provider": "gemini", "success": False, "error": gf.error})
            except Exception as e:
                logger.warning("Gemini deep_forensic_analysis failed", error=str(e))
                errors.append(f"Gemini exception: {str(e)}")
                provider_attempts.append({"provider": "gemini", "success": False, "error": str(e)})
        else:
            logger.info("Gemini not enabled — skipping for Agent1")
            provider_attempts.append({"provider": "gemini", "success": False, "reason": "not_enabled"})

        # Vision fallback chain is intentionally Gemini → local ensemble only.
        # Groq is reserved exclusively for text synthesis (per-agent narratives +
        # final report) and must NOT be spent on vision profiling, where its
        # quota competes with the synthesis path.

        # ── Fallback: local ensemble ───────────────────────────────────────
        logger.info("Falling back to local visual ensemble")
        result = await self._run_local_visual_profile(
            artifact=artifact,
            exif_summary=exif_summary,
            is_screen_capture_like=is_screen_capture_like,
        )
        all_attempts = provider_attempts + [
            {"provider": "local_visual_ensemble", "success": True},
        ]
        result.provider_attempts = all_attempts
        result.fallback_applied = True
        result.fallback_reason = "; ".join(errors) if errors else "Gemini unavailable or skipped"
        logger.info("Local visual profile delivered after Gemini fallback")
        return result
