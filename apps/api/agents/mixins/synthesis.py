"""
Neural Synthesis Mixin for Forensic Agents.
Centralizes Gemini-based deep forensic analysis and cross-modal grounding.
"""

from __future__ import annotations

import asyncio
from collections.abc import Callable
from typing import Any

from core.structured_logging import get_logger
from core.tool_names import TOOL_VISUAL_PROFILE
from core.vision_router import VisionRouter

logger = get_logger(__name__)


class NeuralSynthesisMixin:
    """
    Mixin providing unified deep forensic analysis capabilities via Gemini.
    """

    # These will be provided by the base class or other mixins
    agent_id: str
    session_id: Any
    evidence_artifact: Any
    config: Any
    _tool_context: dict[str, Any]
    inter_agent_bus: Any | None

    async def _wait_for_agent1_visual_profile(self) -> dict:
        """
        Wait for Agent 1 (Image Integrity) visual profile if applicable.
        Used by downstream agents to ground their findings in pixel-level data.
        """
        # Fast path: the shared visual context was resolved up-front and threaded
        # onto this agent — use it directly, no bus/Agent-1 wait.
        threaded = getattr(self, "visual_context", None)
        if threaded is not None:
            try:
                from core.visual_context_store import visual_context_to_profile_dict
                return visual_context_to_profile_dict(threaded)
            except Exception as e:
                logger.debug("Failed converting threaded visual context to profile", error=str(e))

        if self.inter_agent_bus:
            shared = self.inter_agent_bus.get_visual_profile(str(self.session_id)) or {}
            if shared:
                return shared

        # Try retrieving from the persistent visual context store first
        from core.visual_context_store import get_visual_context, visual_context_to_profile_dict
        try:
            sha256 = getattr(self.evidence_artifact, "content_hash", "") or ""
            vis_ctx = await get_visual_context(
                session_id=str(self.session_id),
                sha256=sha256,
                working_memory=getattr(self, "working_memory", None),
                inter_agent_bus=self.inter_agent_bus
            )
            if vis_ctx:
                return visual_context_to_profile_dict(vis_ctx)
        except Exception as e:
            logger.debug("Failed retrieving visual context from store at start of wait", error=str(e))

        event = getattr(self, "_agent1_context_event", None)
        if event is None:
            # If there's no event and no context, we can wait a bit for the store
            from core.visual_context_store import wait_for_visual_context
            try:
                sha256 = getattr(self.evidence_artifact, "content_hash", "") or ""
                vis_ctx = await wait_for_visual_context(
                    session_id=str(self.session_id),
                    sha256=sha256,
                    working_memory=getattr(self, "working_memory", None),
                    inter_agent_bus=self.inter_agent_bus,
                    timeout=getattr(self.config, "agent_context_wait_timeout", 30.0)
                )
                if vis_ctx:
                    return visual_context_to_profile_dict(vis_ctx)
            except Exception as e:
                logger.warning("Error waiting for visual context from store", error=str(e))
            return {}

        if not event.is_set():
            timeout = getattr(self.config, "agent_context_wait_timeout", 30.0)
            try:
                # Use shield to prevent cancellation of the wait if the agent pass is still running
                await asyncio.wait_for(asyncio.shield(event.wait()), timeout=timeout)
            except TimeoutError:
                # Check store one last time after timeout
                try:
                    sha256 = getattr(self.evidence_artifact, "content_hash", "") or ""
                    vis_ctx = await get_visual_context(
                        session_id=str(self.session_id),
                        sha256=sha256,
                        working_memory=getattr(self, "working_memory", None),
                        inter_agent_bus=self.inter_agent_bus
                    )
                    if vis_ctx:
                        return visual_context_to_profile_dict(vis_ctx)
                except Exception:
                    pass

                logger.warning(
                    "Timed out waiting for Agent 1 context; proceeding with local data",
                    agent_id=self.agent_id,
                    timeout=timeout,
                )
                if hasattr(self, "_record_tool_error"):
                    await self._record_tool_error(
                        "agent1_context_sync",
                        f"Agent 1 context unavailable after {timeout}s — grounding may be incomplete",
                    )

        return getattr(self, "_agent1_context", {})

    async def _record_visual_profile_result(self, result: dict) -> None:
        if hasattr(self, "_record_tool_result"):
            await self._record_tool_result(TOOL_VISUAL_PROFILE, result)
        self._tool_context[TOOL_VISUAL_PROFILE] = result

    def _visual_profile_to_tool_result(
        self,
        profile: dict,
        *,
        source: str = "agent1_visual_profile",
    ) -> dict:
        """Convert the shared Agent 1 visual profile into this agent's tool result."""
        metadata = profile.get("metadata") if isinstance(profile, dict) else {}
        if not isinstance(metadata, dict):
            metadata = {}
        content_description = (
            profile.get("content_description")
            or metadata.get("content_description")
            or metadata.get("gemini_scene")
            or metadata.get("scene_description")
            or "Agent 1 visual evidence profile available."
        )
        confidence = (
            profile.get("confidence_raw")
            or profile.get("confidence")
            or metadata.get("confidence")
            or metadata.get("gemini_confidence")
            or 0.68
        )
        try:
            confidence = float(confidence)
        except (TypeError, ValueError):
            confidence = 0.68

        # Derive a POSITIVE evidence_verdict when the native profile concluded the
        # media is synthetic/manipulated (e.g. synthetic speech, deepfake video,
        # AI-generated text). Without this the holistic determination is inert and
        # the specialist agent's verdict ignores it (synthetic audio → "authentic").
        _MANIP_PROFILE_VERDICTS = {
            "AI_GENERATED", "LIKELY_AI_GENERATED", "MANIPULATED", "LIKELY_MANIPULATED",
            "TAMPERED", "SUSPICIOUS", "DEEPFAKE",
        }
        _pv = str(profile.get("verdict") or "").upper()
        _fta = str(profile.get("file_type_assessment") or "").lower()
        # Only the NATIVE preflight profile (audio/video/document, where the Gemini
        # determination IS the primary signal) is authoritative enough to FORCE a
        # POSITIVE verdict. For IMAGE profile reuse the profile is one corroborating
        # signal among many tools — forcing POSITIVE there overrode clean tool
        # evidence and produced false "Manipulated" on clean isolated-object /
        # benign-edited images. Restrict the escalation to the native non-image path.
        # EXCEPTION: when Agent 1's own analysis flagged AI generation (strong
        # evidence_verdict or ai_generation_signals present), the reused profile
        # carries a real forensic signal that must not be silenced — escalate to
        # POSITIVE so Agent 5's verdict reflects the AI detection.
        _is_native = source == "native_preflight_visual_context"
        _has_agent1_ai_signal = (
            not _is_native
            and (
                str(profile.get("evidence_verdict") or "").upper() in ("POSITIVE",)
                or bool(profile.get("ai_generation_signals"))
                or _pv in _MANIP_PROFILE_VERDICTS
                or _fta == "ai_generated"
            )
        )
        _profile_is_manip = (_is_native or _has_agent1_ai_signal) and (_pv in _MANIP_PROFILE_VERDICTS or _fta == "ai_generated")
        _evidence_verdict = profile.get("evidence_verdict")
        if _profile_is_manip and (not _evidence_verdict or _evidence_verdict in ("INCONCLUSIVE", "NEGATIVE")):
            _evidence_verdict = "POSITIVE"
        elif not _evidence_verdict:
            _evidence_verdict = "INCONCLUSIVE"

        # Non-image evidence consumes the native preflight profile (audio/video/doc),
        # not an Agent-1 image profile — phrase the finding accordingly.
        _profile_lead = (
            "Holistic media analysis"
            if source == "native_preflight_visual_context"
            else "Reused Agent 1 visual evidence profile"
        )
        # When the profile flagged manipulation, surface the ACTUAL reason
        # (synthetic-speech / deepfake / AI-text signals) rather than the neutral
        # content description, so the visible finding explains the verdict.
        _manip_signals = profile.get("manipulation_signals") or []
        if _profile_is_manip and _manip_signals:
            _summary_body = "; ".join(str(s) for s in _manip_signals[:2])
        else:
            _summary_body = str(content_description)

        result = {
            **profile,
            "agent_id": self.agent_id,
            "finding_type": "shared_visual_evidence_profile",
            "confidence_raw": max(0.0, min(1.0, confidence)),
            "status": "CONFIRMED" if _profile_is_manip else (profile.get("status") or "CONFIRMED"),
            "evidence_verdict": _evidence_verdict,
            "reasoning_summary": (
                f"{_profile_lead}: {_summary_body[:200]}"
            ),
            "summary": (
                f"{_profile_lead}: {_summary_body[:240]}"
            ),
            "metadata": {
                **metadata,
                "tool_name": TOOL_VISUAL_PROFILE,
                "analysis_source": source,
                "source_agent": "Agent1",
                "reused_visual_profile": True,
                "external_ai_used": bool(metadata.get("external_ai_used", False)),
                "available": True,
                "court_defensible": metadata.get("court_defensible", True),
                "content_description": content_description,
            },
            "court_defensible": True,
            "available": True,
        }
        return result

    async def _build_local_media_profile(self, artifact, mime: str) -> dict:
        """Fast on-device holistic profile for audio/video when no native (Gemini)
        media context exists. Replaces the old behaviour where the non-image
        'read_shared_image_context' axis waited 60s for an Agent1 visual profile that
        never runs for audio, then ran the IMAGE ensemble on a non-image file —
        producing a timeout + a degraded finding + an empty Agent2 context.

        Populates the agent's CONTENT context (duration / format / channels) and
        carries an explicit, court-honest COVERAGE caveat: without a holistic speech
        model, synthetic-speech / voice-clone determination is screening-tier only."""
        path = getattr(artifact, "file_path", "") or ""
        is_video = mime.startswith("video/")
        is_document = (
            mime == "application/pdf"
            or mime.startswith("text/")
            or "officedocument" in mime
            or "msword" in mime
            or "document" in mime
        )
        dur = sr = ch = None
        w = h = 0
        caption = ""

        if is_video:
            # Describe what the VIDEO SHOWS (the Florence-for-images analog): probe
            # via OpenCV and caption a representative middle frame on-device, so the
            # video's CONTENT context is the visual scene — not just the audio track.
            def _probe_video() -> tuple:
                import os
                import tempfile
                dur = None
                w = h = 0
                caption = ""
                frame_path = ""
                try:
                    import cv2
                    cap = cv2.VideoCapture(path)
                    fps = cap.get(cv2.CAP_PROP_FPS) or 0.0
                    n = cap.get(cv2.CAP_PROP_FRAME_COUNT) or 0.0
                    w = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH) or 0)
                    h = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT) or 0)
                    if fps and n:
                        dur = n / fps
                    if n:
                        cap.set(cv2.CAP_PROP_POS_FRAMES, int(n // 2))
                    ok, frame = cap.read()
                    cap.release()
                    if ok and frame is not None:
                        fd, frame_path = tempfile.mkstemp(suffix=".jpg")
                        os.close(fd)
                        cv2.imwrite(frame_path, frame)
                except Exception:
                    pass
                if frame_path:
                    try:
                        from tools.florence_analyzer import get_florence_analyzer
                        res = get_florence_analyzer().analyze(frame_path)
                        if getattr(res, "available", False):
                            caption = (res.best_description() or "").strip()
                    except Exception:
                        caption = ""
                    finally:
                        try:
                            os.unlink(frame_path)
                        except Exception:
                            pass
                return (dur, w, h, caption)

            dur, w, h, caption = await asyncio.to_thread(_probe_video)
            for _pre in ("the image shows ", "the image is ", "this image shows "):
                if caption.lower().startswith(_pre):
                    caption = caption[len(_pre):]
                    break
            vprops = []
            if dur:
                vprops.append(f"~{dur:.0f}s")
            if w and h:
                vprops.append(f"{w}x{h}")
            vprops_s = ", ".join(vprops)
            lead = f"The video shows {caption}" if caption else "Video file"
            description = (
                lead.rstrip(".") + ". " + (f"({vprops_s}). " if vprops_s else "")
                + "On-device frame-integrity, motion, and audio-track forensic checks "
                "were applied locally."
            )
            coverage = (
                "Coverage note: no holistic video model (frame-level deepfake / "
                "synthetic-render assessment) is available on this analysis path, so "
                "AI-generation / deepfake determination is screening-tier only — a clean "
                "result does not exclude high-quality synthetic or rendered video."
            )
        elif is_document:
            # Describe the DOCUMENT by its extracted text (the content axis for docs)
            # so Agent5's context is the document content, not an empty image axis.
            def _probe_doc() -> tuple:
                npages = 0
                text = ""
                try:
                    import fitz  # PyMuPDF
                    _doc = fitz.open(path)
                    npages = _doc.page_count
                    chunks = []
                    for _i, _page in enumerate(_doc):
                        if _i >= 3:
                            break
                        chunks.append(_page.get_text() or "")
                    text = " ".join(chunks).strip()
                    _doc.close()
                except Exception:
                    try:
                        with open(path, errors="ignore") as _f:
                            text = _f.read(4000).strip()
                            npages = 1
                    except Exception:
                        pass
                return (npages, text)

            npages, _text = await asyncio.to_thread(_probe_doc)
            snippet = " ".join((_text or "").split())[:180]
            lead = f"A {npages}-page document" if npages else "A text document"
            description = (
                lead
                + (f". Opening text: “{snippet}…”" if snippet else ".")
                + " On-device text extraction and structural / provenance checks were "
                "applied locally."
            )
            coverage = (
                "Coverage note: no holistic document model (semantic AI-authored-text "
                "assessment) is available on this analysis path, so AI-generated-text / "
                "document-tampering determination is screening-tier only — a clean result "
                "does not exclude machine-authored text."
            )
        else:
            def _probe() -> tuple:
                try:
                    import soundfile as sf
                    info = sf.info(path)
                    return (info.duration, info.samplerate, info.channels, str(info.format or ""))
                except Exception:
                    try:
                        import wave
                        with wave.open(path, "rb") as w:
                            sr = w.getframerate() or 0
                            return (w.getnframes() / float(sr or 1), sr, w.getnchannels(), "WAV")
                    except Exception:
                        return (None, None, None, "")

            dur, sr, ch, fmt = await asyncio.to_thread(_probe)
            ch_desc = {1: "mono", 2: "stereo"}.get(ch, (f"{ch}-channel" if ch else ""))
            parts = []
            if dur:
                parts.append(f"~{dur:.0f}s")
            if ch_desc:
                parts.append(ch_desc)
            if sr:
                parts.append(f"{int(sr)} Hz")
            props = ", ".join(parts)
            description = (
                "On-device profile — audio recording" + (f" ({props})" if props else "") + ". "
                "Acoustic forensic checks (spectral, prosody, voice-clone, anti-spoofing, "
                "codec) were applied locally."
            )
            coverage = (
                "Coverage note: no holistic speech model (transcription + synthetic-speech "
                "assessment) is available on this analysis path, so AI-voice / voice-clone "
                "determination is screening-tier only — a clean result does not exclude "
                "high-quality speech synthesis."
            )
        return {
            "agent_id": self.agent_id,
            "available": True,
            "status": "COMPLETE",
            "evidence_verdict": "NOT_APPLICABLE",
            "confidence_raw": 0.0,
            "court_defensible": False,
            "content_description": description,
            "reasoning_summary": coverage,
            "summary": coverage,
            "metadata": {
                "tool_name": TOOL_VISUAL_PROFILE,
                "content_description": description,
                "coverage_caveat": coverage,
                "analysis_source": (
                    "local_document_profile" if is_document
                    else "local_video_profile" if is_video
                    else "local_audio_profile"
                ),
                "provider_used": (
                    "local_document_profile" if is_document
                    else "local_video_profile" if is_video
                    else "local_audio_profile"
                ),
                "external_ai_used": False,
                "media_duration_s": round(dur, 2) if dur else None,
                "sample_rate_hz": int(sr) if sr else None,
                "channels": ch,
                "resolution": (f"{w}x{h}" if (w and h) else None),
            },
        }

    async def _visual_evidence_profile_handler(
        self,
        input_data: dict,
        model_hint: str | None = None,
        signal_callback: Callable[[str], Any] | None = None,
    ) -> dict:
        """
        Unified handler for visual evidence profile — the session-wide
        shared visual context used by all downstream agents.
        """
        artifact = input_data.get("artifact") or self.evidence_artifact

        # Hard quota contract: only Agent 1 may make the Gemini visual API call.
        # All other agents consume Agent 1's shared visual evidence profile or
        # fall back to local tools without touching Gemini.
        if self.agent_id != "Agent1":
            # For non-image evidence (audio/video/document) Agent1 never runs, so the
            # session-wide NATIVE preflight VisualContext (Gemini File API analysis of
            # the real media — transcription, synthetic-speech / deepfake / AI-text
            # signals) is the source of truth, not an Agent1 profile that never exists.
            _mime = (getattr(artifact, "mime_type", "") or "").lower()
            if not _mime.startswith("image/"):
                try:
                    from core.visual_context_store import (
                        create_visual_context_preflight,
                        visual_context_to_profile_dict,
                    )

                    # Get-or-create the native preflight VisualContext (single-flight
                    # locked + cached). This is race-safe: for audio/video the backend's
                    # fire-and-forget preflight may not have finished (File API upload
                    # latency), so we block here rather than fall back to the image
                    # local-ensemble (which is meaningless on audio/video).
                    _vc = await create_visual_context_preflight(
                        session_id=str(self.session_id),
                        file_path=getattr(artifact, "file_path", "") or "",
                        sha256=getattr(artifact, "content_hash", "") or "",
                        config=self.config,
                        working_memory=getattr(self, "working_memory", None),
                        inter_agent_bus=self.inter_agent_bus,
                    )
                    if _vc is not None:
                        _prof = visual_context_to_profile_dict(_vc)
                        if _prof:
                            # The preflight now returns EITHER a native (Gemini) context
                            # OR a local media profile — label the source accurately so a
                            # local read is not presented as a court-defensible native one.
                            _is_native = bool(
                                getattr(_vc, "external_llm_used", False)
                            ) and str(getattr(_vc, "source", "")) == "llm_assisted"
                            result = self._visual_profile_to_tool_result(
                                _prof,
                                source=(
                                    "native_preflight_visual_context"
                                    if _is_native
                                    else "local_media_profile"
                                ),
                            )
                            result["agent_id"] = self.agent_id
                            if hasattr(self, "_record_tool_result"):
                                await self._record_tool_result(TOOL_VISUAL_PROFILE, result)
                            return result
                except Exception as _vc_err:
                    logger.debug(
                        "Native preflight VisualContext unavailable for non-image agent",
                        agent_id=self.agent_id,
                        error=str(_vc_err),
                    )

                # No native (Gemini) media context → for audio/video/document, build a
                # fast LOCAL media profile instead of waiting 60s for an Agent1 visual
                # profile (Agent1 never runs for non-image) or running the IMAGE
                # ensemble on a non-image file.
                _is_doc_mime = (
                    _mime == "application/pdf"
                    or _mime.startswith("text/")
                    or "officedocument" in _mime
                    or "msword" in _mime
                    or "document" in _mime
                )
                if _mime.startswith(("audio/", "video/")) or _is_doc_mime:
                    result = await self._build_local_media_profile(artifact, _mime)
                    if hasattr(self, "_record_tool_result"):
                        await self._record_tool_result(TOOL_VISUAL_PROFILE, result)
                    return result

            agent1_profile = await self._wait_for_agent1_visual_profile()
            if agent1_profile:
                result = self._visual_profile_to_tool_result(agent1_profile)
                if hasattr(self, "_record_tool_result"):
                    await self._record_tool_result(TOOL_VISUAL_PROFILE, result)
                return result

            try:
                from core.vision_local_ensemble import analyze_local_visual_profile

                finding = await analyze_local_visual_profile(
                    artifact=artifact,
                    exif_summary={"reason": "Agent 1 visual profile unavailable"},
                    is_screen_capture_like=getattr(self, "_is_screen_capture", False),
                )
                result = finding.to_finding_dict(
                    self.agent_id,
                    tool_name=TOOL_VISUAL_PROFILE,
                )
                result["metadata"] = {
                    **(result.get("metadata") or {}),
                    "tool_name": TOOL_VISUAL_PROFILE,
                    "analysis_source": "local_visual_ensemble",
                    "provider_used": "local_visual_ensemble",
                    "external_ai_used": False,
                    "agent1_profile_missing": True,
                }
                await self._record_visual_profile_result(result)
                return result
            except Exception as fallback_err:
                return {
                    "agent_id": self.agent_id,
                    "finding_type": "shared_visual_evidence_profile",
                    "confidence_raw": 0.0,
                    "status": "INCOMPLETE",
                    "evidence_verdict": "INCONCLUSIVE",
                    "reasoning_summary": "Agent 1 visual profile unavailable; local visual profile failed.",
                    "summary": "Agent 1 visual profile unavailable.",
                    "metadata": {
                        "tool_name": TOOL_VISUAL_PROFILE,
                        "analysis_source": "agent1_visual_profile",
                        "available": False,
                        "court_defensible": False,
                        "skipped": True,
                        "error": str(fallback_err),
                    },
                    "court_defensible": False,
                    "available": False,
                }
        elif self.inter_agent_bus:
            existing_profile = self.inter_agent_bus.get_visual_profile(str(self.session_id)) or {}
            if existing_profile:
                result = self._visual_profile_to_tool_result(
                    existing_profile,
                    source="agent1_visual_profile_cached",
                )
                result["agent_id"] = self.agent_id
                if hasattr(self, "_record_tool_result"):
                    await self._record_tool_result(TOOL_VISUAL_PROFILE, result)
                return result

        # 1. Aggregate local tool context
        # 2. Integrate Agent 1 context for cross-modal grounding
        agent1_profile = await self._wait_for_agent1_visual_profile()

        # Extract flat EXIF fields for the prompt builder — do NOT pass the
        # full tool context dict as exif_summary; the prompt builder expects
        # flat keys like camera_make, datetime_original, gps_location.
        exif_fields: dict[str, Any] = {}
        # File-level facts always available
        exif_fields["mime_type"] = getattr(artifact, "mime_type", None) or ""
        exif_fields["filename"] = getattr(artifact, "original_filename", None) or getattr(artifact, "file_path", "")
        # Try Agent 5 inter-agent bus for richer EXIF if available
        if self.inter_agent_bus:
            try:
                from core.agent_registry import AgentID
                agent5_ctx = await self.inter_agent_bus.get_agent_context(
                    str(self.session_id), AgentID.AGENT5
                )
                agent5_meta = (agent5_ctx or {}).get("tool_context", {})
                exif_extract = agent5_meta.get("extract_exif_metadata") or agent5_meta.get("exif_extract") or {}
                if isinstance(exif_extract, dict):
                    exif_fields["camera_make"] = exif_extract.get("camera_make") or exif_extract.get("Make")
                    exif_fields["camera_model"] = exif_extract.get("camera_model") or exif_extract.get("Model")
                    exif_fields["datetime_original"] = exif_extract.get("datetime_original") or exif_extract.get("DateTimeOriginal")
                    exif_fields["gps_location"] = exif_extract.get("gps_location") or exif_extract.get("GPS")
            except Exception as exc:
                logger.debug("Agent 5 context unavailable for visual synthesis", error=str(exc))
                pass  # Agent 5 not available yet — file-level facts are enough

        full_context = exif_fields

        # 3. Initialize router and execute
        try:
            client = VisionRouter(self.config)

            # Default signal callback to inter-agent bus if not provided
            if signal_callback is None:

                async def _default_signal(msg: str):
                    if self.inter_agent_bus:
                        self.inter_agent_bus.signal_event(
                            self.session_id,
                            f"{self.agent_id.lower()}_vision_signal",
                            {"progress": msg},
                        )

                signal_callback = _default_signal

            if hasattr(self, "update_sub_task"):
                await self.update_sub_task("Running visual evidence profile...")

            agent_persona = getattr(self, "persona", None)
            is_screen_cap = getattr(self, "_is_screen_capture", False)
            finding = await client.deep_forensic_analysis(
                artifact=artifact,
                exif_summary=full_context,
                signal_callback=signal_callback,
                model_hint=model_hint,
                persona=agent_persona,
                is_screen_capture_like=is_screen_cap,
                agent_id=self.agent_id,
                # Pass session_id so the router reuses the pre-flight VisualContext
                # already created in Redis by /investigate. Without this, Agent1
                # makes a redundant Gemini call (quota burn + ~120s latency) that
                # duplicates work the pre-flight already completed.
                session_id=str(self.session_id),
            )

            if finding.error:
                err_msg = finding.error
                err_result = {
                    "agent_id": self.agent_id,
                    "finding_type": "visual_evidence_profile",
                    "confidence_raw": 0.55,
                    "status": "FAILED",
                    "evidence_refs": [],
                    "reasoning_summary": f"Visual evidence profile failed: {err_msg}",
                    "summary": f"Visual evidence profile failed: {err_msg}",
                    "metadata": {
                        "tool_name": TOOL_VISUAL_PROFILE,
                        "analysis_source": finding.provider_used,
                        "available": False,
                        "court_defensible": False,
                        "provider_attempts": finding.provider_attempts,
                        "fallback_applied": finding.fallback_applied,
                        "fallback_reason": finding.fallback_reason,
                        "tool_coverage": finding.tool_coverage,
                        "error": err_msg,
                    },
                    "court_defensible": False,
                    "caveat": "Visual evidence profile failed/unavailable.",
                    "stub_result": True,
                    "available": False,
                }
                if hasattr(self, "_record_tool_error"):
                    await self._record_tool_error(TOOL_VISUAL_PROFILE, f"Error: {err_msg}")
                return err_result

            result = finding.to_finding_dict(
                self.agent_id,
                tool_name=TOOL_VISUAL_PROFILE,
            )
            result["analysis_source"] = result.get("metadata", {}).get(
                "analysis_source",
                "local_visual_ensemble",
            )
            result["metadata"] = {
                **(result.get("metadata") or {}),
                "tool_name": TOOL_VISUAL_PROFILE,
                "visual_profile_owner": "Agent1",
                "execution_mode": self.config.analysis_execution_mode,
                "external_ai_used": bool((result.get("metadata") or {}).get("external_ai_used", False)),
            }

            await self._record_visual_profile_result(result)

            # Persist visual context to the durable store — but NEVER clobber a
            # richer pre-flight context. The pre-flight 3-section VisualContext
            # (created at upload) carries the per-agent axes — manipulation vs
            # AI-generation vs compression signals, people/UI/scene inconsistencies,
            # visible timestamps/location/device clues — that a flat deep finding
            # cannot reconstruct. build_visual_context_from_finding() can only
            # populate a thin subset, so overwriting collapsed the deep report to a
            # bare file-type lead (e.g. "composite") and an empty Agent 5 metadata
            # axis. Save only when no richer context exists yet, or when upgrading a
            # local-ensemble context with a genuine remote-vision result.
            if self.agent_id == "Agent1" and not finding.error:
                try:
                    from core.visual_context_store import (
                        build_visual_context_from_finding,
                        get_visual_context,
                        save_visual_context,
                    )
                    sha256 = getattr(artifact, "content_hash", "") or ""
                    existing = await get_visual_context(
                        session_id=str(self.session_id),
                        sha256=sha256,
                        working_memory=getattr(self, "working_memory", None),
                        inter_agent_bus=self.inter_agent_bus,
                    )
                    existing_is_rich = existing is not None and (
                        existing.source == "llm_assisted"
                        or (
                            existing.source != "local_ensemble"
                            and bool(getattr(existing, "external_llm_used", False))
                        )
                        or bool(
                            existing.metadata_visual_context.visible_timestamps
                            or existing.metadata_visual_context.device_or_platform_clues
                            or existing.image_integrity_context.ai_generation_signals
                            or existing.object_scene_context.scene_inconsistencies
                        )
                    )
                    is_upgrade = (
                        existing is not None
                        and existing.source == "local_ensemble"
                        and finding.provider_used == "gemini"
                        and not finding.from_cache
                    )
                    if existing_is_rich and not is_upgrade:
                        logger.info(
                            "Preserving richer pre-flight visual context; skipping deep overwrite",
                            session_id=self.session_id,
                        )
                    else:
                        context_obj = build_visual_context_from_finding(
                            session_id=str(self.session_id),
                            evidence_sha256=sha256,
                            finding=finding,
                        )
                        await save_visual_context(
                            session_id=str(self.session_id),
                            sha256=sha256,
                            context=context_obj,
                            working_memory=getattr(self, "working_memory", None),
                            inter_agent_bus=self.inter_agent_bus,
                        )
                        logger.info("Durable visual context persisted", session_id=self.session_id)
                except Exception as save_exc:
                    logger.warning("Failed to save durable visual context", error=str(save_exc))

            if self.inter_agent_bus and not result.get("error"):
                self.inter_agent_bus.set_visual_profile(str(self.session_id), result)

            return result

        except Exception as e:
            err_msg = str(e)
            err_result = {
                "agent_id": self.agent_id,
                "finding_type": "visual_evidence_profile",
                "confidence_raw": 0.55,
                "status": "FAILED",
                "evidence_refs": [],
                "reasoning_summary": f"Visual evidence profile failed: {err_msg}",
                "summary": f"Visual evidence profile failed: {err_msg}",
                "metadata": {
                    "tool_name": TOOL_VISUAL_PROFILE,
                    "analysis_source": "router_exception",
                    "available": False,
                    "court_defensible": False,
                    "status": "FAILED",
                    "error": err_msg,
                },
                "court_defensible": False,
                "caveat": "Visual evidence profile failed/unavailable.",
                "stub_result": True,
                "available": False,
            }
            if hasattr(self, "_record_tool_error"):
                await self._record_tool_error(TOOL_VISUAL_PROFILE, f"Error: {err_msg}")
            return err_result

    async def _gemini_deep_forensic_handler(
        self,
        input_data: dict,
        model_hint: str | None = None,
        signal_callback: Callable[[str], Any] | None = None,
    ) -> dict:
        """Deprecated compatibility alias for persisted investigations."""
        return await self._visual_evidence_profile_handler(
            input_data,
            model_hint=model_hint,
            signal_callback=signal_callback,
        )

