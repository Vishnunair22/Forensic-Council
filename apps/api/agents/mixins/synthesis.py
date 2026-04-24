"""
Neural Synthesis Mixin for Forensic Agents.
Centralizes Gemini-based deep forensic analysis and cross-modal grounding.
"""

from __future__ import annotations

import asyncio
from typing import Any, Callable

import httpx

from core.context_utils import aggregate_tool_context
from core.gemini_client import GeminiVisionClient
from core.structured_logging import get_logger

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
            timeout = getattr(self.config, "agent_context_wait_timeout", 60.0)
            try:
                # Use shield to prevent cancellation of the wait if the agent pass is still running
                await asyncio.wait_for(asyncio.shield(event.wait()), timeout=timeout)
            except asyncio.TimeoutError:
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
        model_hint: str = "gemini-2.5-flash",
        signal_callback: Callable[[str], Any] | None = None
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
                            {"progress": msg}
                        )
                signal_callback = _default_signal

            if hasattr(self, "update_sub_task"):
                await self.update_sub_task("Synthesizing multi-modal forensic verdict...")

            finding = await client.deep_forensic_analysis(
                file_path=artifact.file_path,
                exif_summary=full_context,
                signal_callback=signal_callback,
                model_hint=model_hint
            )
            
            result = finding.to_finding_dict(self.agent_id)
            result["analysis_source"] = f"gemini_{model_hint}"
            
            # Record result if method exists
            if hasattr(self, "_record_tool_result"):
                await self._record_tool_result("gemini_deep_forensic", result)
                
            return result
            
        except httpx.AuthenticationError as e:
            logger.error(
                "Gemini authentication failed - invalid API key",
                agent_id=self.agent_id,
                error=str(e),
                exc_info=True
            )
            err_result = {
                "error": str(e),
                "analysis_source": "gemini_vision",
                "available": False,
                "court_defensible": False,
                "confidence": 0.0,
                "status": "AUTH_FAILED"
            }
            if hasattr(self, "_record_tool_error"):
                await self._record_tool_error("gemini_deep_forensic", f"Authentication error: {e}")
            raise  # Re-raise auth failures - cannot recover

        except httpx.RateLimitError as e:
            logger.warning(
                "Gemini rate limit hit - will retry",
                agent_id=self.agent_id,
                error=str(e),
            )
            if hasattr(self, "_record_tool_error"):
                await self._record_tool_error("gemini_deep_forensic", f"Rate limited: {e}")
            raise  # Retry on rate limits

        except httpx.TimeoutException as e:
            logger.warning(
                "Gemini request timed out",
                agent_id=self.agent_id,
                error=str(e),
            )
            err_result = {
                "error": f"Timeout: {e}",
                "analysis_source": "gemini_vision",
                "available": False,
                "court_defensible": False,
                "confidence": 0.0,
                "status": "TIMEOUT"
            }
            if hasattr(self, "_record_tool_error"):
                await self._record_tool_error("gemini_deep_forensic", f"Timeout: {e}")
            return err_result

        except Exception as e:
            logger.error(
                "Gemini deep forensic analysis failed",
                agent_id=self.agent_id,
                error=str(e),
                exc_info=True
            )
            err_result = {
                "error": str(e),
                "analysis_source": "gemini_vision",
                "available": False,
                "court_defensible": False,
                "confidence": 0.0,
                "status": "FAILED"
            }
            if hasattr(self, "_record_tool_error"):
                await self._record_tool_error("gemini_deep_forensic", str(e))
            return err_result
