import asyncio
import json
import time
from typing import Any

import httpx

from core.config import Settings
from core.gemini_client import (
    GeminiVisionClient,
    GeminiVisionFinding,
    _build_deep_forensic_prompt,
)
from core.llm_client import is_placeholder_secret
from core.provider_quota_guard import ProviderQuotaGuard, configure_provider_quota_guards
from core.structured_logging import get_logger
from core.vision_local_ensemble import analyze_local_visual_profile

logger = get_logger(__name__)


class VisionRouter:
    """
    Vision Router Facade.
    
    Adheres to the same public surface as GeminiVisionClient, enabling
    transparent provider routing (Gemini -> Groq Vision -> OpenRouter -> Local Ensemble).
    """

    @classmethod
    def configure_quota_pool(cls, max_concurrent: int) -> None:
        """Forward concurrency settings to GeminiVisionClient."""
        GeminiVisionClient.configure_quota_pool(max_concurrent)

    def __init__(self, config: Settings):
        self.config = config
        configure_provider_quota_guards(config)
        self.gemini_client = GeminiVisionClient(config)

        self.local_only = config.local_only_analysis

        if self.local_only:
            self.provider_chain = ["local_ensemble"]
        else:
            chain_str = getattr(config, "vision_provider_chain", "gemini,groq_vision,openrouter,local_ensemble")
            self.provider_chain = [
                provider.strip().lower()
                for provider in chain_str.split(",")
                if provider.strip()
            ]

        # Ensure Quota Guards are configured
        if not ProviderQuotaGuard.get_config("groq_vision"):
            ProviderQuotaGuard.configure(
                "groq_vision",
                rpm_limit=getattr(config, "groq_vision_rpm_limit", 15),
                rpd_limit=getattr(config, "groq_vision_rpd_limit", 14400),
            )
        if not ProviderQuotaGuard.get_config("openrouter"):
            ProviderQuotaGuard.configure(
                "openrouter",
                rpm_limit=getattr(config, "openrouter_rpm_limit", 20),
                rpd_limit=getattr(config, "openrouter_rpd_limit", 200),
            )

        logger.info(
            "VisionRouter initialized",
            execution_mode=config.analysis_execution_mode,
            chain=self.provider_chain,
        )

    def _use_gemini(self) -> bool:
        """Check if Gemini is in the chain and configured."""
        return "gemini" in self.provider_chain and self.gemini_client._enabled

    async def identify_file_content(self, file_path: str, agent_context: str = "") -> GeminiVisionFinding:
        if self.local_only:
            return await self._run_local_visual_profile(file_path=file_path, exif_summary={}, is_screen_capture_like=False)
        if self._use_gemini():
            try:
                return await self.gemini_client.identify_file_content(file_path, agent_context)
            except Exception as e:
                logger.warning("identify_file_content failed on Gemini, falling back to local ELA/metrics", error=str(e))
        return await self.gemini_client._local_forensic_fallback(file_path)

    async def analyze_manipulation_evidence(self, file_path: str, preliminary_findings: list[str]) -> GeminiVisionFinding:
        if self.local_only:
            return await self._run_local_visual_profile(file_path=file_path, exif_summary={}, is_screen_capture_like=False)
        if self._use_gemini():
            try:
                return await self.gemini_client.analyze_manipulation_evidence(file_path, preliminary_findings)
            except Exception as e:
                logger.warning("analyze_manipulation_evidence failed on Gemini, falling back to local ELA/metrics", error=str(e))
        return await self.gemini_client._local_forensic_fallback(file_path)

    async def analyze_objects_and_scene(self, file_path: str, preliminary_detections: list[str]) -> GeminiVisionFinding:
        if self.local_only:
            return await self._run_local_visual_profile(file_path=file_path, exif_summary={}, is_screen_capture_like=False)
        if self._use_gemini():
            try:
                return await self.gemini_client.analyze_objects_and_scene(file_path, preliminary_detections)
            except Exception as e:
                logger.warning("analyze_objects_and_scene failed on Gemini, falling back to local ELA/metrics", error=str(e))
        return await self.gemini_client._local_forensic_fallback(file_path)

    async def analyze_metadata_visual_consistency(self, file_path: str, metadata_summary: dict[str, Any]) -> GeminiVisionFinding:
        if self.local_only:
            return await self._run_local_visual_profile(file_path=file_path, exif_summary=metadata_summary, is_screen_capture_like=False)
        if self._use_gemini():
            try:
                return await self.gemini_client.analyze_metadata_visual_consistency(file_path, metadata_summary)
            except Exception as e:
                logger.warning("analyze_metadata_visual_consistency failed on Gemini, falling back to local ELA/metrics", error=str(e))
        return await self.gemini_client._local_forensic_fallback(file_path, metadata_summary)

    async def _run_local_visual_profile(
        self,
        file_path: str,
        exif_summary: dict[str, Any] | None = None,
        is_screen_capture_like: bool = False,
    ):
        return await analyze_local_visual_profile(
            file_path=file_path,
            exif_summary=exif_summary,
            is_screen_capture_like=is_screen_capture_like,
        )

    async def deep_forensic_analysis(
        self,
        file_path: str,
        exif_summary: dict[str, Any] | None = None,
        model_hint: str | None = None,
        signal_callback: Any | None = None,
        persona: str | None = None,
        is_screen_capture_like: bool = False,
        agent_id: str = "",
    ) -> GeminiVisionFinding:
        """
        Execute deep vision forensic analysis by routing through the provider chain.
        """
        if self.local_only:
            logger.info(
                "Executing native local visual profile",
                execution_mode="local_only",
                agent_id=agent_id,
            )
            return await self._run_local_visual_profile(
                file_path=file_path,
                exif_summary=exif_summary,
                is_screen_capture_like=is_screen_capture_like,
            )

        errors = []

        for provider in self.provider_chain:
            logger.info("VisionRouter trying provider in cascade", provider=provider)

            if provider == "gemini":
                if agent_id != "Agent1":
                    logger.info(
                        "Gemini skipped: single-call policy reserves Gemini for Agent1",
                        agent_id=agent_id,
                    )
                    continue
                if not self.gemini_client._enabled:
                    logger.info("Gemini skipped: not configured or policy not accepted")
                    continue
                try:
                    res = await self.gemini_client.deep_forensic_analysis(
                        file_path=file_path,
                        exif_summary=exif_summary,
                        model_hint=model_hint,
                        signal_callback=signal_callback,
                        persona=persona,
                        is_screen_capture_like=is_screen_capture_like,
                        agent_id=agent_id,
                    )
                    if res and not res.error:
                        return res
                    if res and res.error:
                        errors.append(f"Gemini error response: {res.error}")
                except Exception as e:
                    logger.warning("Gemini failed in deep_forensic_analysis", error=str(e))
                    errors.append(f"Gemini exception: {str(e)}")

            elif provider == "groq_vision":
                groq_key = self.config.groq_vision_api_key
                if not groq_key or groq_key.strip() == "":
                    if getattr(self.config, "llm_provider", "").lower() == "groq":
                        groq_key = self.config.llm_api_key

                if not groq_key or is_placeholder_secret(groq_key):
                    logger.info("Groq Vision skipped: key missing or placeholder")
                    continue

                model = self.config.groq_vision_model or "llama-3.2-11b-vision-preview"
                
                # Quota Guard check
                allowed, q_result = await ProviderQuotaGuard.check_and_record("groq_vision", model)
                if not allowed:
                    logger.warning("Groq Vision blocked by quota guard", reason=q_result.reason)
                    errors.append(f"Groq Vision quota blocked: {q_result.reason}")
                    continue

                try:
                    t0 = time.perf_counter()
                    b64_data, mime_type = GeminiVisionClient._encode_file(file_path)
                    prompt = _build_deep_forensic_prompt(exif_summary, persona, is_screen_capture_like)

                    payload = {
                        "model": model,
                        "response_format": {"type": "json_object"},
                        "messages": [
                            {
                                "role": "user",
                                "content": [
                                    {"type": "text", "text": prompt},
                                    {"type": "image_url", "image_url": {"url": f"data:{mime_type};base64,{b64_data}"}},
                                ],
                            }
                        ],
                    }

                    timeout = getattr(self.config, "groq_vision_timeout", 30.0)
                    async with httpx.AsyncClient(timeout=timeout) as client:
                        resp = await client.post(
                            "https://api.groq.com/openai/v1/chat/completions",
                            headers={
                                "Authorization": f"Bearer {groq_key}",
                                "Content-Type": "application/json",
                            },
                            json=payload,
                        )

                    if resp.status_code == 200:
                        data = resp.json()
                        content = data["choices"][0]["message"]["content"]
                        latency = (time.perf_counter() - t0) * 1000.0
                        return self._parse_openai_vision_response(content, latency, model)
                    else:
                        logger.warning("Groq Vision returned non-200 status", status=resp.status_code)
                        errors.append(f"Groq Vision HTTP status {resp.status_code}: {resp.text}")
                except Exception as e:
                    logger.warning("Groq Vision failed", error=str(e))
                    errors.append(f"Groq Vision exception: {str(e)}")

            elif provider == "openrouter":
                if not getattr(self.config, "openrouter_enabled", False):
                    logger.info("OpenRouter skipped: disabled in config")
                    continue
                openrouter_key = self.config.openrouter_api_key
                if not openrouter_key or is_placeholder_secret(openrouter_key):
                    logger.info("OpenRouter skipped: key missing or placeholder")
                    continue

                models = [m.strip() for m in self.config.openrouter_vision_models.split(",") if m.strip()]
                
                for model in models:
                    logger.info("Trying OpenRouter vision model", model=model)
                    
                    # Quota Guard check
                    allowed, q_result = await ProviderQuotaGuard.check_and_record("openrouter", model)
                    if not allowed:
                        logger.warning("OpenRouter model blocked by quota guard", model=model, reason=q_result.reason)
                        errors.append(f"OpenRouter quota blocked for {model}: {q_result.reason}")
                        continue

                    try:
                        t0 = time.perf_counter()
                        b64_data, mime_type = GeminiVisionClient._encode_file(file_path)
                        prompt = _build_deep_forensic_prompt(exif_summary, persona, is_screen_capture_like)

                        payload = {
                            "model": model,
                            "response_format": {"type": "json_object"},
                            "messages": [
                                {
                                    "role": "user",
                                    "content": [
                                        {"type": "text", "text": prompt},
                                        {"type": "image_url", "image_url": {"url": f"data:{mime_type};base64,{b64_data}"}},
                                    ],
                                }
                            ],
                        }

                        timeout = getattr(self.config, "openrouter_timeout", 45.0)
                        referer = getattr(self.config, "openrouter_referer", "https://forensic-council.local")
                        
                        async with httpx.AsyncClient(timeout=timeout) as client:
                            resp = await client.post(
                                "https://openrouter.ai/api/v1/chat/completions",
                                headers={
                                    "Authorization": f"Bearer {openrouter_key}",
                                    "HTTP-Referer": referer,
                                    "Content-Type": "application/json",
                                },
                                json=payload,
                            )

                        if resp.status_code == 200:
                            data = resp.json()
                            content = data["choices"][0]["message"]["content"]
                            latency = (time.perf_counter() - t0) * 1000.0
                            return self._parse_openai_vision_response(content, latency, model)
                        else:
                            logger.warning("OpenRouter returned non-200 status", model=model, status=resp.status_code)
                            errors.append(f"OpenRouter {model} HTTP status {resp.status_code}: {resp.text}")
                    except Exception as e:
                        logger.warning("OpenRouter model run failed", model=model, error=str(e))
                        errors.append(f"OpenRouter {model} exception: {str(e)}")

            elif provider == "local_ensemble":
                logger.info("Executing native local visual profile")
                return await self._run_local_visual_profile(file_path, exif_summary, is_screen_capture_like)

        # Fallback of last resort if all in the chain failed or were skipped
        logger.warning("All providers in cascade failed or skipped. Triggering last-resort local profile.", errors=errors)
        return await self._run_local_visual_profile(file_path, exif_summary, is_screen_capture_like)

    def _parse_openai_vision_response(self, text: str, latency: float, model: str) -> GeminiVisionFinding:
        """Parse JSON response from OpenAI-compatible Vision API."""
        text_clean = text.strip()
        if text_clean.startswith("```"):
            lines = text_clean.splitlines()
            if lines[0].startswith("```"):
                lines = lines[1:]
            if lines and lines[-1].startswith("```"):
                lines = lines[:-1]
            text_clean = "\n".join(lines).strip()

        try:
            data = json.loads(text_clean)
        except Exception as e:
            logger.error("Failed to parse vision response JSON", error=str(e), raw_text=text[:500])
            raise ValueError(f"Invalid JSON returned by vision API: {e}")

        # Map to GeminiVisionFinding fields
        return GeminiVisionFinding(
            analysis_type="deep_forensic_analysis",
            model_used=model,
            content_description=data.get("scene_description", data.get("content_type", "")),
            manipulation_signals=data.get("manipulation_signals", []),
            detected_objects=data.get("detected_objects", []),
            contextual_anomalies=data.get("contradiction_audit", []),
            file_type_assessment=data.get("content_type", ""),
            confidence=data.get("confidence", 0.8),
            court_defensible=True,
            caveat=f"Vision analysis — LLM-derived from {model}, requires corroboration with deterministic tools.",
            raw_response=text,
            latency_ms=latency,
            error=None,
            from_cache=False,
            _extracted_text=data.get("extracted_text", []),
            _interface_identification=data.get("interface_identification", ""),
            _contextual_narrative=data.get("contextual_narrative", ""),
            _authenticity_verdict=data.get("authenticity_verdict", "AUTHENTIC"),
            _metadata_visual_consistency=data.get("metadata_visual_consistency", ""),
            _forensic_routing=data.get("forensic_routing", {}),
            _forensic_specifics=data.get("forensic_specifics", ""),
        )
