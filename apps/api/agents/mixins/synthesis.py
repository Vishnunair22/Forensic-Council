"""
Neural Synthesis Mixin for Forensic Agents.
Centralizes Gemini-based deep forensic analysis and cross-modal grounding.
"""

from __future__ import annotations

import asyncio
import json
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

        result = {
            **profile,
            "agent_id": self.agent_id,
            "finding_type": "shared_visual_evidence_profile",
            "confidence_raw": max(0.0, min(1.0, confidence)),
            "status": profile.get("status") or "CONFIRMED",
            "evidence_verdict": profile.get("evidence_verdict") or "INCONCLUSIVE",
            "reasoning_summary": (
                f"Reused Agent 1 visual evidence profile: {str(content_description)[:200]}"
            ),
            "summary": (
                f"Reused Agent 1 visual evidence profile: {str(content_description)[:240]}"
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

            # Persist visual context to the durable store (Redis + inter_agent_bus + working memory)
            if self.agent_id == "Agent1" and not finding.error:
                try:
                    from core.visual_context_store import (
                        build_visual_context_from_finding,
                        save_visual_context,
                    )
                    sha256 = getattr(artifact, "content_hash", "") or ""
                    context_obj = build_visual_context_from_finding(
                        session_id=str(self.session_id),
                        evidence_sha256=sha256,
                        finding=finding
                    )
                    await save_visual_context(
                        session_id=str(self.session_id),
                        sha256=sha256,
                        context=context_obj,
                        working_memory=getattr(self, "working_memory", None),
                        inter_agent_bus=self.inter_agent_bus
                    )
                    logger.info("Durable visual context persisted successfully", session_id=self.session_id)
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

