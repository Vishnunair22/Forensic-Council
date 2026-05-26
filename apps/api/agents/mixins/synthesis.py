"""
Neural Synthesis Mixin for Forensic Agents.
Centralizes Gemini-based deep forensic analysis and cross-modal grounding.
"""

from __future__ import annotations

import asyncio
from collections.abc import Callable
from typing import Any

import httpx

from core.gemini_client import GeminiVisionClient
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

    async def _gemini_deep_forensic_handler(
        self,
        input_data: dict,
        model_hint: str | None = None,
        signal_callback: Callable[[str], Any] | None = None,
    ) -> dict:
        """
        Unified handler for Gemini multimodal visual forensic synthesis.
        """
        artifact = input_data.get("artifact") or self.evidence_artifact

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
            client = GeminiVisionClient(self.config)

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

            finding = await client.deep_forensic_analysis(
                file_path=artifact.file_path,
                exif_summary=full_context,
                signal_callback=signal_callback,
                model_hint=model_hint,
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

            result = finding.to_finding_dict(self.agent_id)
            result["analysis_source"] = f"gemini_{model_hint}" if model_hint else "gemini_vision"

            # Record result if method exists
            if hasattr(self, "_record_tool_result"):
                await self._record_tool_result("gemini_deep_forensic", result)

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
