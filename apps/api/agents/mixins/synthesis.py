"""
Neural Synthesis Mixin for Forensic Agents.
Centralizes Gemini-based deep forensic analysis and cross-modal grounding.
"""

from __future__ import annotations

import asyncio
import json
from collections.abc import Callable
from typing import Any

import httpx

from core.tool_names import TOOL_GEMINI_DEEP, TOOL_VISUAL_PROFILE
from core.vision_router import VisionRouter
from core.structured_logging import get_logger

from .._context_utils import aggregate_tool_context

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

    async def _wait_for_agent1_context(self) -> dict:
        """
        Wait for Agent 1 (Image Integrity) context if applicable.
        Used by Agents 3 and 5 to ground their findings in pixel-level data.
        """
        if self.inter_agent_bus:
            shared = self.inter_agent_bus.get_image_context(str(self.session_id)) or {}
            if shared:
                return shared

        event = getattr(self, "_agent1_context_event", None)
        if event is None:
            return {}

        if not event.is_set():
            timeout = getattr(self.config, "agent_context_wait_timeout", 30.0)
            try:
                # Use shield to prevent cancellation of the wait if the agent pass is still running
                await asyncio.wait_for(asyncio.shield(event.wait()), timeout=timeout)
            except TimeoutError:
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
        self._tool_context[TOOL_GEMINI_DEEP] = result

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
                f"Reused Agent 1 visual evidence profile: {str(content_description)[:500]}"
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
            agent1_context = await self._wait_for_agent1_context()
            if agent1_context:
                result = self._visual_profile_to_tool_result(agent1_context)
                if hasattr(self, "_record_tool_result"):
                    await self._record_tool_result("gemini_deep_forensic", result)
                return result

            try:
                from core.vision_local_ensemble import analyze_local_visual_profile

                finding = await analyze_local_visual_profile(
                    artifact.file_path,
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
            existing_profile = self.inter_agent_bus.get_image_context(str(self.session_id)) or {}
            if existing_profile:
                result = self._visual_profile_to_tool_result(
                    existing_profile,
                    source="agent1_visual_profile_cached",
                )
                result["agent_id"] = self.agent_id
                if hasattr(self, "_record_tool_result"):
                    await self._record_tool_result("gemini_deep_forensic", result)
                return result

        # 1. Aggregate local tool context
        dynamic_context = aggregate_tool_context(self._tool_context, agent_id=self.agent_id)

        # 2. Integrate Agent 1 context for cross-modal grounding
        agent1_context = await self._wait_for_agent1_context()

        full_context = {
            "tools": dynamic_context,
            "agent1_vision": agent1_context,
        }

        # 3. Initialize client and execute
        try:
            client = VisionRouter(self.config)

            # Default signal callback to inter-agent bus if not provided
            if signal_callback is None:

                async def _default_signal(msg: str):
                    if self.inter_agent_bus:
                        self.inter_agent_bus.signal_event(
                            self.session_id,
                            f"{self.agent_id.lower()}_gemini_signal",
                            {"progress": msg},
                        )

                signal_callback = _default_signal

            if hasattr(self, "update_sub_task"):
                await self.update_sub_task("Synthesizing multi-modal forensic verdict...")

            agent_persona = getattr(self, "persona", None)
            is_screen_cap = getattr(self, "_is_screen_capture", False)
            finding = await client.deep_forensic_analysis(
                file_path=artifact.file_path,
                exif_summary=full_context,
                signal_callback=signal_callback,
                model_hint=model_hint,
                persona=agent_persona,
                is_screen_capture_like=is_screen_cap,
                agent_id=self.agent_id,
            )

            if finding.error:
                err_msg = finding.error
                err_status = "FAILED"
                if "401" in err_msg or "unauthorized" in err_msg.lower() or "auth" in err_msg.lower() or "api key" in err_msg.lower():
                    err_status = "AUTH_FAILED"
                elif "timeout" in err_msg.lower() or "timed out" in err_msg.lower():
                    err_status = "TIMEOUT"

                result = {
                    "agent_id": self.agent_id,
                    "finding_type": "gemini_vision_deep_forensic_analysis",
                    "confidence_raw": 0.55,
                    "status": err_status,
                    "evidence_refs": [],
                    "reasoning_summary": f"Gemini deep forensic analysis failed ({err_status}): {err_msg}",
                    "summary": f"Gemini deep forensic analysis failed ({err_status}): {err_msg}",
                    "metadata": {
                        "tool_name": "gemini_deep_forensic",
                        "analysis_source": "gemini_vision",
                        "available": False,
                        "court_defensible": False,
                        "status": err_status,
                        "error": err_msg,
                    },
                    "court_defensible": False,
                    "caveat": "Gemini vision analysis failed/unavailable.",
                    "stub_result": True,
                    "available": False,
                }
                if hasattr(self, "_record_tool_error"):
                    await self._record_tool_error("gemini_deep_forensic", f"Error ({err_status}): {err_msg}")
                return result

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
                "external_ai_used": not self.config.local_only_analysis,
            }

            await self._record_visual_profile_result(result)

            if self.inter_agent_bus and not result.get("error"):
                self.inter_agent_bus.set_image_context(str(self.session_id), result)

            return result

        except Exception as e:
            err_msg = str(e)
            err_status = "FAILED"

            if (
                "401" in err_msg
                or "unauthorized" in err_msg.lower()
                or "auth" in err_msg.lower()
                or "api key" in err_msg.lower()
                or (hasattr(e, "response") and getattr(e.response, "status_code", None) == 401)
            ):
                err_status = "AUTH_FAILED"
                logger.error(
                    "Gemini authentication failed - invalid API key",
                    agent_id=self.agent_id,
                    error=err_msg,
                    exc_info=True,
                )
            elif (
                isinstance(e, httpx.TimeoutException)
                or "timeout" in err_msg.lower()
                or "timed out" in err_msg.lower()
            ):
                err_status = "TIMEOUT"
                logger.warning(
                    "Gemini request timed out",
                    agent_id=self.agent_id,
                    error=err_msg,
                )
            elif (
                "429" in err_msg
                or "rate limit" in err_msg.lower()
                or "quota" in err_msg.lower()
                or (hasattr(e, "response") and getattr(e.response, "status_code", None) == 429)
            ):
                logger.warning(
                    "Gemini rate limit / quota hit",
                    agent_id=self.agent_id,
                    error=err_msg,
                )
            else:
                logger.error(
                    "Gemini deep forensic analysis failed",
                    agent_id=self.agent_id,
                    error=err_msg,
                    exc_info=True,
                )

            err_result = {
                "agent_id": self.agent_id,
                "finding_type": "gemini_vision_deep_forensic_analysis",
                "confidence_raw": 0.55,
                "status": err_status,
                "evidence_refs": [],
                "reasoning_summary": f"Gemini deep forensic analysis failed ({err_status}): {err_msg}",
                "summary": f"Gemini deep forensic analysis failed ({err_status}): {err_msg}",
                "metadata": {
                    "tool_name": "gemini_deep_forensic",
                    "analysis_source": "gemini_vision",
                    "available": False,
                    "court_defensible": False,
                    "status": err_status,
                    "error": err_msg,
                },
                "court_defensible": False,
                "caveat": "Gemini vision analysis failed/unavailable.",
                "stub_result": True,
                "available": False,
            }
            if hasattr(self, "_record_tool_error"):
                await self._record_tool_error("gemini_deep_forensic", f"Error ({err_status}): {err_msg}")
            return err_result

    async def generate_agent_synthesis(self, findings: list, react_chain: list) -> str:
        """Generate synthesis with guaranteed fallback."""
        if not findings:
            return f"{self.agent_id}: Classical forensic analysis complete. No anomalies detected."

        llm_available = getattr(self, "_llm_available", False) or getattr(self, "llm_available", False)
        if not llm_available:
            logger.info(f"{self.agent_id}: Generating template synthesis (no LLM)")
            return self._template_synthesis(findings)

        try:
            from core.llm_client import LLMClient
            llm_client = LLMClient(config=self.config)
            llm_synthesis = await asyncio.wait_for(
                llm_client.generate_synthesis(
                    system_prompt=f"Forensic synthesis for {self.agent_id}.",
                    user_content=json.dumps([
                        f.model_dump() if hasattr(f, 'model_dump') else f
                        for f in findings
                    ], default=str),
                    max_tokens=1024,
                    json_mode=False,
                ),
                timeout=30.0,
            )
            if llm_synthesis and len(llm_synthesis.strip()) > 30:
                template_markers = ['template', 'placeholder', 'example', 'TODO', 'lorem ipsum']
                if any(marker in llm_synthesis.lower() for marker in template_markers):
                    logger.warning(f"{self.agent_id}: LLM returned template text, using deterministic")
                    return self._template_synthesis(findings)
                return llm_synthesis
            logger.info(f"{self.agent_id}: LLM synthesis too short, using template")
            return self._template_synthesis(findings)
        except asyncio.TimeoutError:
            logger.warning(f"{self.agent_id}: LLM synthesis timeout, using template")
            return self._template_synthesis(findings)
        except Exception as e:
            logger.warning(f"{self.agent_id}: LLM synthesis failed: {e}, using template")
            return self._template_synthesis(findings)

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

    def _template_synthesis(self, findings: list) -> str:
        """Pure deterministic synthesis from findings."""
        tools_executed = set()
        positive_findings = []
        high_confidence = []
        for f in findings:
            meta = f.metadata if hasattr(f, 'metadata') else f.get('metadata', {})
            tool_name = meta.get('tool_name', '')
            if tool_name:
                tools_executed.add(tool_name)
            verdict = (f.evidence_verdict if hasattr(f, 'evidence_verdict')
                      else f.get('evidence_verdict', ''))
            confidence = (f.confidence_raw if hasattr(f, 'confidence_raw')
                         else f.get('confidence_raw', 0))
            if verdict == 'POSITIVE':
                finding_type = (f.finding_type if hasattr(f, 'finding_type')
                              else f.get('finding_type', tool_name))
                positive_findings.append(finding_type)
                if confidence and confidence > 0.7:
                    high_confidence.append(finding_type)
        parts = [f"Executed {len(tools_executed)} specialized forensic tools"]
        if positive_findings:
            parts.append(f"Detected {len(positive_findings)} positive indicators")
            if high_confidence:
                parts.append(f"High confidence: {', '.join(high_confidence[:2])}")
        else:
            parts.append("No manipulation indicators detected")
        return ". ".join(parts) + "."
