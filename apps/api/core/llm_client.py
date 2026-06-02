"""
LLM Client for Forensic Council ReAct Loop Reasoning.

Provides async LLM API clients for Groq and Gemini,
with a unified interface for generating ReAct reasoning steps.

    - groq      -> Groq API (Llama 3.3 70B, ~700 tok/s, recommended)
    - gemini    -> Google Gemini API (Gemini 2.5 Flash)
    - none      -> Disabled; task-decomposition driver handles all steps
"""

from __future__ import annotations

import asyncio
import json
import random
import time
from dataclasses import dataclass
from typing import Any

import httpx

from core.config import Settings
from core.observability import get_tracer
from core.provider_quota_guard import ProviderQuotaGuard, configure_provider_quota_guards
from core.retry import CircuitBreaker
from core.structured_logging import get_logger

logger = get_logger(__name__)
_tracer = get_tracer("forensic-council.llm")

# Shared placeholder detection across all secret fields
PLACEHOLDER_SIGNALS = (
    "your_",
    "_here",
    "placeholder",
    "changeme",
    "replace_me",
    "__paste_",
    "paste_",
    "sk-xxx",
    "replace_me",
    "change_me",
    "changeme",
    "example_key",
    "test_key",
    "dummy",
    "<your",
    ">",
    "api_key_here",
    "insert",
    "add_your"
)


def is_placeholder_secret(value: str | None) -> bool:
    """True if value is null/empty or contains placeholder signals."""
    if not value:
        return True
    lower = value.strip().lower()
    if len(lower) < 10:
        return True
    return not lower or any(sig in lower for sig in PLACEHOLDER_SIGNALS)


_RETRYABLE_STATUS = {429, 500, 502, 503, 504}
_MAX_RETRIES = 3
_BASE_BACKOFF = 2.0
_MAX_BACKOFF = 5.0  # cap per-attempt wait so worker never blocks more than ~15 s total

# Per-provider circuit breakers shared across all LLMClient instances.
# Keyed by "provider:model" so a failing model on one provider does not
# block the same model on a different provider (or a healthy fallback).
_provider_circuit_breakers: dict[str, CircuitBreaker] = {}


def _get_provider_breaker(provider: str, model: str) -> CircuitBreaker:
    key = f"{provider}:{model}"
    if key not in _provider_circuit_breakers:
        _provider_circuit_breakers[key] = CircuitBreaker(
            failure_threshold=5,
            recovery_timeout=60.0,
            half_open_max_calls=2,
        )
    return _provider_circuit_breakers[key]


@dataclass
class LLMResponse:
    """Structured response from LLM."""

    content: str
    tool_call: dict[str, Any] | None = None
    usage: dict[str, int] | None = None
    latency_ms: float = 0.0
    provider: str = ""


class _GroqTokensRateLimiter:
    """Token bucket rate limiter for Groq API. 30 RPM, 7000 RPD."""
    def __init__(self, rpm_limit: int = 30, rpd_limit: int = 7000):
        self.rpm = TokenBucket(rpm_limit, rpm_limit / 60.0)
        self.rpd = TokenBucket(rpd_limit, rpd_limit / 86400.0)

    async def acquire(self) -> tuple[bool, str]:
        if not self.rpm.try_consume(1.0):
            return False, f"RPM limit reached, retry in {self.rpm.time_until_refill(1.0):.0f}s"
        if not self.rpd.try_consume(1.0):
            return False, "Daily quota exhausted"
        return True, ""


class TokenBucket:
    def __init__(self, capacity: float, refill_rate: float):
        self.capacity = capacity
        self.tokens = capacity
        self.refill_rate = refill_rate
        self.last_refill = time.time()

    def try_consume(self, cost: float = 1.0) -> bool:
        now = time.time()
        elapsed = now - self.last_refill
        self.tokens = min(self.capacity, self.tokens + (elapsed * self.refill_rate))
        self.last_refill = now
        if self.tokens >= cost:
            self.tokens -= cost
            return True
        return False

    def time_until_refill(self, cost: float = 1.0) -> float:
        needed = cost - self.tokens
        if needed <= 0:
            return 0.0
        return needed / self.refill_rate if self.refill_rate > 0 else float('inf')


class LLMClient:
    """
    Async LLM client with unified interface across Groq and Gemini.

    All requests run through exponential-backoff retry logic.
    Groq (Llama 3.3 70B) is the recommended provider for this project:
    - ~700 tok/s
    - Full function-calling support
    - Free tier supports full investigations in dev
    """

    def __init__(self, config: Settings, use_arbiter_tier: bool = False):
        self.config = config
        self.use_arbiter_tier = use_arbiter_tier
        self._groq_limiter = _GroqTokensRateLimiter()
        configure_provider_quota_guards(config)

        if use_arbiter_tier:
            self.provider = config.arbiter_llm_provider.lower()
            self.api_key = config.arbiter_llm_api_key or config.llm_api_key
            self.model = config.arbiter_primary_model
            self.fallback_models = [
                m.strip() for m in config.arbiter_fallback_chain.split(",") if m.strip()
            ]
        else:
            self.provider = config.llm_provider.lower()
            self.api_key = config.llm_api_key
            self.model = config.llm_model
            self.fallback_models = [
                model.strip()
                for model in getattr(config, "llm_fallback_models", "").split(",")
                if model.strip()
            ]

        self.temperature = config.llm_temperature
        self.max_tokens = config.llm_max_tokens
        self.timeout = config.llm_timeout
        self._circuit_breaker = _get_provider_breaker(self.provider, self.model)

        # Fallback settings
        self.fallback_enabled = True
        # Arbiter gets its own Gemini key if configured — isolates Arbiter quota from agents.
        if use_arbiter_tier and getattr(config, "arbiter_gemini_api_key", None):
            self.gemini_api_key = config.arbiter_gemini_api_key
        else:
            self.gemini_api_key = config.gemini_api_key
        self.gemini_model = config.gemini_model

        self._client: httpx.AsyncClient | None = None

        # Global semaphore to limit concurrency and avoid blasting API limits
        if not hasattr(LLMClient, "_global_semaphore"):
            LLMClient._global_semaphore = asyncio.Semaphore(2)

        # Synthesis-specific serialization: multiple agents finishing simultaneously
        # (especially on fast screenshot paths) would all call generate_synthesis()
        # concurrently and exhaust the Groq TPM budget in one burst → all 429.
        # Semaphore(2) limits concurrent synthesis calls to avoid blasting limits while permitting overlap.
        if not hasattr(LLMClient, "_synthesis_semaphore"):
            LLMClient._synthesis_semaphore = asyncio.Semaphore(1)

    async def _get_client(self, timeout_override: float | None = None) -> httpx.AsyncClient:
        """Return a shared httpx.AsyncClient, creating it on first use.

        Connection pool is sized for concurrent agent + arbiter LLM calls:
        5 agents × 1 synthesis + 4 arbiter narratives = ~10 concurrent connections.
        Pool allows 50 max with 20 keepalive for burst tolerance.
        """
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(
                timeout=self.timeout,
                limits=httpx.Limits(
                    max_connections=50,
                    max_keepalive_connections=20,
                ),
            )
        return self._client

    async def close(self) -> None:
        """Close the shared HTTP client."""
        if self._client and not self._client.is_closed:
            await self._client.aclose()
            self._client = None

    @property
    def is_available(self) -> bool:
        """True if the LLM client has a real (non-placeholder) API key configured."""
        if not self.api_key or self.provider == "none":
            return False
        if is_placeholder_secret(self.api_key):
            return False
        # Gemini calls require policy acknowledgment
        if self.provider == "gemini":
            if not getattr(self.config, "gemini_text_calls_enabled", False):
                return False
            if not getattr(self.config, "gemini_api_key_policy_ok", False):
                return False
            if not self.gemini_api_key or is_placeholder_secret(self.gemini_api_key):
                return False
        # Groq keys must start with gsk_
        if self.provider == "groq" and not self.api_key.startswith("gsk_"):
            return False
        return True

    async def health_check(self) -> bool:
        """Quick probe to verify LLM service is reachable (3s timeout)."""
        if not self.is_available:
            return False
        try:
            client = await self._get_client(timeout_override=3.0)
            # M-C-4: Gemini API key carried as `x-goog-api-key` header
            # instead of `?key=...` query string. Query-string keys are
            # captured by httpx DEBUG logs, OTel URL attributes, and
            # intermediate proxy access logs.
            url_map = {
                "groq": "https://api.groq.com/openai/v1/models",
                "gemini": f"https://generativelanguage.googleapis.com/v1beta/models/{self.model}",
            }
            url = url_map.get(self.provider)
            if not url:
                return True
            headers: dict[str, str] = {}
            api_key = self.api_key or ""
            if self.provider == "groq":
                headers = {"Authorization": f"Bearer {api_key}"}
            elif self.provider == "gemini":
                headers = {"x-goog-api-key": api_key}

            resp = await asyncio.wait_for(client.get(url, headers=headers), timeout=3.0)
            return resp.status_code < 500
        except (TimeoutError, ConnectionError, OSError) as e:
            logger.debug(
                "LLM health check failed (network/timeout)", provider=self.provider, error=str(e)
            )
            return False
        except Exception as e:
            logger.debug(
                "LLM health check failed (unexpected)", provider=self.provider, error=str(e)
            )
            return False

    async def generate_reasoning_step(
        self,
        system_prompt: str,
        react_chain: list[dict[str, Any]],
        available_tools: list[dict[str, Any]],
        current_task: str | None = None,
    ) -> LLMResponse:
        """Generate the next reasoning step using model candidates with cross-provider support."""
        with _tracer.start_as_current_span("llm.generate_reasoning_step") as span:
            if self.provider == "none" or not self.api_key or not self.is_available:
                return LLMResponse(content="", provider="none")

            messages = self._build_messages(system_prompt, react_chain, current_task)
            t0 = time.monotonic()
            candidates = self._get_model_candidates()
            last_exc: Exception | None = None

            for model_spec in candidates:
                # Resolve provider and model from spec (e.g. "gemini/gemini-2.5-flash")
                original_provider = self.provider
                original_model = self.model
                original_key = self.api_key

                try:
                    if "/" in model_spec:
                        parts = model_spec.split("/", 1)
                        self.provider = parts[0].lower()
                        self.model = parts[1]
                        # Update key for the target provider
                        if self.provider == "gemini":
                            self.api_key = self.gemini_api_key
                        elif self.provider == "groq":
                            # Use arbiter key when in arbiter tier, agent key otherwise.
                            # This prevents arbiter Groq synthesis calls from burning agent-tier quota.
                            self.api_key = (
                                self.config.arbiter_llm_api_key
                                if self.use_arbiter_tier and self.config.arbiter_llm_api_key
                                else self.config.llm_api_key
                            )
                    else:
                        self.model = model_spec

                    if not self.api_key or self.api_key.startswith("REPLACE_"):
                        continue

                    # Check per-provider circuit breaker before attempting the call
                    cb = _get_provider_breaker(self.provider, self.model)
                    if cb.state == "OPEN":
                        logger.warning(
                            "Circuit breaker OPEN — skipping candidate",
                            provider=self.provider,
                            model=self.model,
                        )
                        continue

                    # Check provider quota before the API call
                    estimated_tokens = (
                        sum(len(m.get("content", "")) for m in messages) // 4
                        + min(self.max_tokens, 1024)
                    )
                    allowed, quota_result = await ProviderQuotaGuard.check_and_record(
                        self.provider,
                        self.model,
                        estimated_tokens=estimated_tokens,
                        tpm_limit_override=self._model_tpm_limit(self.provider, self.model),
                    )
                    if not allowed:
                        logger.warning(
                            "Provider quota guard blocked call",
                            provider=self.provider,
                            model=self.model,
                            reason=quota_result.reason,
                        )
                        continue

                    resp = await self._execute_call(messages, available_tools, t0, span)
                    cb.record_success()
                    if model_spec != candidates[0]:
                        resp.provider = f"{original_provider}_fallback_{self.provider}"
                    return resp
                except Exception as exc:
                    last_exc = exc
                    _get_provider_breaker(self.provider, self.model).record_failure()
                    logger.warning(f"Reasoning candidate {model_spec} failed: {exc}")
                finally:
                    # Restore original settings for next candidate or next call
                    self.provider = original_provider
                    self.model = original_model
                    self.api_key = original_key

            if last_exc:
                logger.error(f"All reasoning candidates failed: {last_exc}")
            return LLMResponse(content="", provider=self.provider)

    async def _execute_call(
        self,
        messages: list[dict[str, str]],
        available_tools: list[dict[str, Any]],
        start_time: float,
        span: Any,
    ) -> LLMResponse:
        """Helper to execute the actual provider call."""
        if self.provider == "groq":
            resp = await self._call_groq(messages, available_tools)
        elif self.provider == "gemini":
            resp = await self._call_gemini(messages, available_tools)
        else:
            raise ValueError(f"Unknown LLM provider: {self.provider}")

        resp.latency_ms = (time.monotonic() - start_time) * 1000
        resp.provider = self.provider
        tool_name = resp.tool_call.get("name") if resp.tool_call else None
        span.set_attribute("latency_ms", resp.latency_ms)
        span.set_attribute("tool_name", tool_name or "")
        return resp

    def _build_messages(
        self,
        system_prompt: str,
        react_chain: list[dict[str, Any]],
        current_task: str | None,
    ) -> list[dict[str, str]]:
        """Build the message list from the current ReAct chain."""
        messages: list[dict[str, str]] = [{"role": "system", "content": system_prompt}]
        if current_task:
            messages.append({"role": "user", "content": f"Current task: {current_task}"})

        for step in react_chain:
            step_type = step.get("step_type", "")
            content = step.get("content", "")

            if step_type == "THOUGHT":
                messages.append({"role": "assistant", "content": f"Thought: {content}"})
            elif step_type == "ACTION":
                tool_name = step.get("tool_name", "")
                tool_input = step.get("tool_input", {})
                messages.append(
                    {
                        "role": "assistant",
                        "content": f"Action: {tool_name}({json.dumps(tool_input, default=str)})",
                    }
                )
            elif step_type == "OBSERVATION":
                obs = content
                if len(obs) > 3000:
                    obs = obs[:3000] + "\n... [observation truncated for context length]"
                messages.append({"role": "user", "content": f"Observation: {obs}"})

        return messages

    async def _with_retry(self, coro_factory) -> httpx.Response:
        """Execute an HTTP coroutine factory with exponential-backoff retry."""
        if not self.is_available:
            raise RuntimeError(
                f"LLM API key is placeholder or missing — skipping {self.provider} calls"
            )
        last_response = None
        for attempt in range(_MAX_RETRIES):
            try:
                # Use global semaphore to prevent API rate limit blasting
                async with self._global_semaphore:
                    response = await coro_factory()

                last_response = response
                if response.status_code in _RETRYABLE_STATUS:
                    wait = min(_BASE_BACKOFF * (2**attempt), _MAX_BACKOFF) * (0.5 + random.random())
                    logger.warning(
                        f"LLM API {response.status_code}, retrying in {wait:.1f}s (attempt {attempt + 1}/{_MAX_RETRIES})"
                    )
                    await asyncio.sleep(wait)
                    continue
                return response
            except (httpx.TimeoutException, httpx.NetworkError) as e:
                if attempt < _MAX_RETRIES - 1:
                    wait = min(_BASE_BACKOFF * (2**attempt), _MAX_BACKOFF) * (0.5 + random.random())
                    logger.warning(f"LLM API {type(e).__name__}, retrying in {wait:.1f}s")
                    await asyncio.sleep(wait)
                else:
                    raise

        if last_response is not None:
            last_response.raise_for_status()
        raise RuntimeError(f"LLM API failed after {_MAX_RETRIES} attempts")

    def _get_model_candidates(self) -> list[str]:
        """Return primary model followed by de-duplicated fallbacks."""
        candidates: list[str] = []
        for model in [self.model, *self.fallback_models]:
            if (
                str(model).lower().startswith("gemini/")
                and not getattr(self.config, "gemini_text_calls_enabled", False)
            ):
                continue
            if model and model not in candidates:
                candidates.append(model)
        return candidates

    async def _call_groq(
        self,
        messages: list[dict[str, str]],
        available_tools: list[dict[str, Any]],
    ) -> LLMResponse:
        """Call Groq API using the current self.model (already resolved by outer loop)."""
        if not self.is_available:
            raise RuntimeError("Groq API key is placeholder or missing")

        url = "https://api.groq.com/openai/v1/chat/completions"
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        tools = self._tools_to_openai_format(available_tools)
        payload: dict[str, Any] = {
            "messages": messages,
            "temperature": self.temperature,
            "max_tokens": self.max_tokens,
            "model": self.model,
        }
        if tools:
            payload["tools"] = tools
            payload["tool_choice"] = "auto"

        client = await self._get_client()
        response = await self._with_retry(
            lambda c=payload: client.post(url, headers=headers, json=c)
        )
        response.raise_for_status()
        return self._parse_openai_response(response.json())

    async def _call_gemini(
        self,
        messages: list[dict[str, str]],
        available_tools: list[dict[str, Any]],
    ) -> LLMResponse:
        """Call Google Gemini API (v1beta)."""
        if not self.api_key:
            raise RuntimeError("Gemini API key missing")

        # M-C-4: Gemini key as header, not query string.
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{self.model}:generateContent"
        gemini_headers = {"x-goog-api-key": self.api_key}

        # Convert messages to Gemini format
        contents = []
        for msg in messages:
            role = "user" if msg["role"] == "user" or msg["role"] == "system" else "model"
            contents.append({"role": role, "parts": [{"text": msg["content"]}]})

        payload: dict[str, Any] = {
            "contents": contents,
            "generationConfig": {
                "temperature": self.temperature,
                "maxOutputTokens": self.max_tokens,
            },
        }

        if available_tools:
            payload["tools"] = [
                {
                    "functionDeclarations": [
                        {
                            "name": t["name"],
                            "description": t.get("description", ""),
                            "parameters": t.get("parameters", {"type": "object", "properties": {}}),
                        }
                        for t in available_tools
                    ]
                }
            ]

        client = await self._get_client()
        response = await self._with_retry(lambda: client.post(url, json=payload, headers=gemini_headers))
        response.raise_for_status()
        data = response.json()

        try:
            candidate = data["candidates"][0]
            content = ""
            tool_call = None

            for part in candidate["content"]["parts"]:
                if "text" in part:
                    content += part["text"]
                elif "functionCall" in part:
                    tool_call = {
                        "name": part["functionCall"]["name"],
                        "arguments": part["functionCall"].get("args", {}),
                    }

            return LLMResponse(content=content, tool_call=tool_call)
        except (KeyError, IndexError) as e:
            logger.error(f"Failed to parse Gemini response: {data}")
            raise RuntimeError(f"Invalid Gemini response: {e}") from e



    @staticmethod
    def _tools_to_openai_format(tools: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """Convert tool list to OpenAI/Groq function-calling format."""
        return [
            {
                "type": "function",
                "function": {
                    "name": t["name"],
                    "description": t.get("description", ""),
                    "parameters": t.get(
                        "parameters",
                        {"type": "object", "properties": {}, "required": []},
                    ),
                },
            }
            for t in tools
        ]

    @staticmethod
    def _strip_markdown_fences(text: str) -> str:
        """Strip leading/trailing markdown code fences from a string.

        Handles both ```json ... ``` and ``` ... ``` forms.  The stripped
        result is used as input to json.loads so the LLM can freely wrap
        JSON in fences without breaking argument parsing.
        """
        stripped = text.strip()
        if stripped.startswith("```"):
            # Remove opening fence (with optional language tag)
            first_newline = stripped.find("\n")
            if first_newline != -1:
                stripped = stripped[first_newline + 1 :]
            else:
                stripped = stripped[3:]
        if stripped.endswith("```"):
            stripped = stripped[: stripped.rfind("```")]
        return stripped.strip()

    @staticmethod
    def _parse_openai_response(data: dict[str, Any]) -> LLMResponse:
        """Parse an OpenAI/Groq-format response dict."""
        choice = data["choices"][0]
        message = choice["message"]

        if message.get("tool_calls"):
            tc = message["tool_calls"][0]
            raw_args = tc["function"]["arguments"]
            try:
                if isinstance(raw_args, str):
                    cleaned = LLMClient._strip_markdown_fences(raw_args)
                    args = json.loads(cleaned)
                else:
                    args = raw_args
            except json.JSONDecodeError:
                logger.warning(
                    "Tool call arguments JSON parse failed; using empty dict",
                    tool_name=tc["function"]["name"],
                    raw_args=raw_args[:200] if isinstance(raw_args, str) else str(raw_args),
                )
                args = {}
            return LLMResponse(
                content=message.get("content") or "",
                tool_call={"name": tc["function"]["name"], "arguments": args},
                usage=data.get("usage"),
            )

        return LLMResponse(
            content=message.get("content") or "",
            usage=data.get("usage"),
        )

    async def generate_multimodal_synthesis(
        self,
        artifact: Any,
        prompt: str,
        max_tokens: int | None = None,
        json_mode: bool = True,
    ) -> Any:
        """
        Multimodal synthesis supporting image/PDF vision inputs via Gemini.
        Essential for Tier 0 OCR and deep forensic visual grounding.
        """
        if not getattr(self.config, "gemini_text_calls_enabled", False):
            logger.info("Gemini multimodal synthesis skipped; reserved for Agent 1 visual probe")
            return {}
        if not self.gemini_api_key:
            return {}

        import base64
        import mimetypes

        try:
            with open(artifact.file_path, "rb") as f:
                data = f.read()
                encoded = base64.b64encode(data).decode("utf-8")
                mime_type = artifact.mime_type or mimetypes.guess_type(artifact.file_path)[0] or "image/jpeg"

            # M-C-4: Gemini key as header, not query string.
            url = f"https://generativelanguage.googleapis.com/v1beta/models/{self.gemini_model}:generateContent"
            gemini_headers = {"x-goog-api-key": self.gemini_api_key}

            payload = {
                "contents": [
                    {
                        "role": "user",
                        "parts": [
                            {"inlineData": {"mimeType": mime_type, "data": encoded}},
                            {"text": prompt}
                        ],
                    }
                ],
                "generationConfig": {
                    "temperature": 0.1,
                    "maxOutputTokens": max_tokens or 1024,
                },
            }
            if json_mode:
                payload["generationConfig"]["responseMimeType"] = "application/json"

            client = await self._get_client(timeout_override=55.0)
            resp = await self._with_retry(
                lambda c=client, u=url, p=payload, h=gemini_headers: c.post(u, json=p, headers=h)
            )
            resp.raise_for_status()
            text = resp.json()["candidates"][0]["content"]["parts"][0].get("text", "").strip()

            if json_mode:
                try:
                    return json.loads(text)
                except json.JSONDecodeError:
                    # Fallback if model didn't return valid JSON despite responseMimeType
                    return text
            return text

        except Exception as exc:
            logger.warning(f"Multimodal synthesis failed: {exc}")
            raise

    # Per-model prompt character limits (conservative, ~3.5 chars/token).
    # Prevents 413 Payload Too Large on smaller context-window models.
    _MODEL_PROMPT_CHAR_LIMITS: dict[str, int] = {
        "llama-3.1-8b-instant": 14000,          # 8k ctx → ~6k chars after output budget
        "llama-3.2-1b-preview": 10000,
        "llama-3.2-3b-preview": 10000,
        "gemini-2.5-flash-lite": 60000,
        "gemini-2.0-flash-lite": 60000,
        "gemini-2.5-flash": 120000,
        "gemini-2.0-flash": 120000,
        "llama-3.3-70b-versatile": 40000,       # 32k ctx window
    }
    _DEFAULT_PROMPT_CHAR_LIMIT: int = 18000

    _GROQ_MODEL_TPM_LIMITS: dict[str, int] = {
        "llama-3.3-70b-versatile": 12000,
        "llama-3.1-8b-instant": 6000,
        "meta-llama/llama-4-scout-17b-16e-instruct": 30000,
        "qwen/qwen3-32b": 6000,
        "openai/gpt-oss-120b": 8000,
        "openai/gpt-oss-20b": 8000,
        "groq/compound": 70000,
        "groq/compound-mini": 70000,
    }

    def _model_tpm_limit(self, provider: str, model: str) -> int | None:
        if provider != "groq":
            return getattr(self.config, f"{provider}_tpm_limit", None)
        return self._GROQ_MODEL_TPM_LIMITS.get(
            model,
            getattr(self.config, "groq_tpm_limit", None),
        )

    async def _chunked_synthesis(
        self,
        system_prompt: str,
        user_content: str,
        max_tokens: int | None = None,
        timeout_override: float | None = None,
        json_mode: bool = True,
    ) -> str:
        """
        Smart chunking for large finding sets.
        
        If user_content (findings JSON) exceeds 6000 characters, split by agent
        and generate per-agent micro-syntheses, then combine.
        """
        if len(user_content) <= 6000:
            return None  # No chunking needed

        try:
            data = json.loads(user_content) if isinstance(user_content, str) else user_content
        except (json.JSONDecodeError, TypeError):
            return None

        # Try to split by agent_id
        findings_by_agent: dict[str, list] = {}
        if isinstance(data, dict):
            agent_section = data.get("per_agent_findings") or data.get("agent_results") or data
            if isinstance(agent_section, dict):
                for aid, findings in agent_section.items():
                    findings_by_agent[aid] = findings if isinstance(findings, list) else [findings]
            elif isinstance(agent_section, list):
                for f in agent_section:
                    aid = f.get("agent_id", "unknown") if isinstance(f, dict) else "unknown"
                    findings_by_agent.setdefault(aid, []).append(f)

        if not findings_by_agent or len(findings_by_agent) <= 1:
            return None  # Can't effectively chunk

        micro_syntheses = []
        for agent_id, agent_findings in findings_by_agent.items():
            chunk_content = json.dumps({agent_id: agent_findings}, default=str)
            micro = await self._generate_synthesis_inner(
                system_prompt=system_prompt,
                user_content=chunk_content,
                max_tokens=min(max_tokens or 500, 500),
                timeout_override=timeout_override,
                json_mode=json_mode,
            )
            if micro and len(micro.strip()) > 10:
                micro_syntheses.append(f"{agent_id}: {micro.strip()}")

        if micro_syntheses:
            combined = " | ".join(micro_syntheses)
            logger.info(
                "Chunked synthesis produced per-agent micro-syntheses",
                agent_count=len(micro_syntheses),
                combined_chars=len(combined),
            )
            return combined

        return None

    async def _generate_synthesis_inner(
        self,
        system_prompt: str,
        user_content: str,
        max_tokens: int | None = None,
        timeout_override: float | None = None,
        json_mode: bool = True,
    ) -> str:
        """Inner synthesis implementation — always called under _synthesis_semaphore."""
        with _tracer.start_as_current_span("llm.generate_synthesis"):
            if not self.is_available:
                return ""

            tokens = max_tokens or min(self.max_tokens, 1500)
            candidates = list(self._get_model_candidates())

            # Expand Gemini fallback candidates: lighter models use a different
            # quota bucket and have higher RPD on the free tier.
            if (
                self.gemini_api_key
                and not is_placeholder_secret(self.gemini_api_key)
                and getattr(self.config, "gemini_text_calls_enabled", False)
            ):
                for gem_model in [
                    "gemini/gemini-2.5-flash",
                    "gemini/gemini-2.0-flash-lite",
                    "gemini/gemini-2.5-flash-lite",
                ]:
                    if gem_model not in candidates:
                        candidates.append(gem_model)

            last_exc: Exception | None = None

            for model_spec in candidates:
                # Resolve provider / model / key from spec
                if "/" in model_spec:
                    parts = model_spec.split("/", 1)
                    target_provider = parts[0].lower()
                    target_model = parts[1]
                    target_api_key = self.gemini_api_key if target_provider == "gemini" else self.api_key
                else:
                    target_provider = self.provider
                    target_model = model_spec
                    target_api_key = self.api_key

                if not target_api_key or is_placeholder_secret(target_api_key):
                    continue

                # Check priority-based quota manager
                from core.quota_manager import get_quota_manager
                priority = "critical" if self.use_arbiter_tier else "medium"

                rpm_limit = getattr(self.config, f"{target_provider}_rpm_limit", 15)
                rpd_limit = getattr(self.config, f"{target_provider}_rpd_limit", 1500)

                quota_mgr = get_quota_manager(
                    f"{target_provider}_synthesis",
                    rpm_limit=rpm_limit,
                    rpd_limit=rpd_limit
                )

                allowed_quota, reason = await quota_mgr.can_make_call(priority, estimated_tokens=tokens)
                if not allowed_quota:
                    self._last_synthesis_blocked_reason = reason
                    logger.warning(
                        f"Quota manager blocked call for {target_provider}: {reason} — trying next model in chain",
                        priority=priority
                    )
                    continue

                # Trim prompt to per-model character limit BEFORE sending to avoid 413.
                char_limit = self._MODEL_PROMPT_CHAR_LIMITS.get(
                    target_model, self._DEFAULT_PROMPT_CHAR_LIMIT
                )
                trimmed_user = user_content
                if len(system_prompt) + len(user_content) > char_limit:
                    # Reserve space for the system prompt; trim user content.
                    user_budget = max(1000, char_limit - len(system_prompt) - 200)
                    if len(user_content) > user_budget:
                        trimmed_user = user_content[:user_budget] + "\n\n[...context trimmed for model context window...]"
                        logger.debug(
                            "Synthesis prompt trimmed for model context window",
                            model=target_model,
                            original_chars=len(user_content),
                            trimmed_chars=len(trimmed_user),
                        )

                estimated_tokens = (len(system_prompt) + len(trimmed_user)) // 4 + tokens
                allowed, quota_result = await ProviderQuotaGuard.check_and_record(
                    target_provider,
                    target_model,
                    estimated_tokens=estimated_tokens,
                    tpm_limit_override=self._model_tpm_limit(target_provider, target_model),
                )
                if not allowed:
                    self._last_synthesis_blocked_reason = quota_result.reason
                    logger.warning(
                        "Provider quota guard blocked synthesis call",
                        provider=target_provider,
                        model=target_model,
                        reason=quota_result.reason,
                    )
                    continue

                try:
                    client = await self._get_client()
                    req_timeout = timeout_override or 30.0

                    if target_provider == "groq":
                        url = "https://api.groq.com/openai/v1/chat/completions"
                        req_headers = {
                            "Authorization": f"Bearer {target_api_key}",
                            "Content-Type": "application/json",
                        }
                        payload: dict[str, Any] = {
                            "model": target_model,
                            "messages": [
                                {"role": "system", "content": system_prompt},
                                {"role": "user", "content": trimmed_user},
                            ],
                            "temperature": 0.2,
                            "max_tokens": tokens,
                        }
                        if json_mode:
                            payload["response_format"] = {"type": "json_object"}
                        async with LLMClient._global_semaphore:
                            resp = await client.post(url, headers=req_headers, json=payload, timeout=req_timeout)

                    elif target_provider == "gemini":
                        # M-C-4: Gemini key as header, not query string.
                        url = f"https://generativelanguage.googleapis.com/v1beta/models/{target_model}:generateContent"
                        req_headers = {"x-goog-api-key": target_api_key}
                        gemini_prompt = f"{system_prompt}\n\n{trimmed_user}"
                        payload = {
                            "contents": [
                                {
                                    "role": "user",
                                    "parts": [{"text": gemini_prompt}],
                                }
                            ],
                            "generationConfig": {"temperature": 0.2, "maxOutputTokens": tokens},
                        }
                        if json_mode:
                            payload["generationConfig"]["responseMimeType"] = "application/json"
                        async with LLMClient._global_semaphore:
                            resp = await client.post(url, headers=req_headers, json=payload, timeout=req_timeout)
                    else:
                        continue

                    # Fast-fail on 429 — skip to next candidate with short backoff.
                    if resp.status_code == 429:
                        await quota_mgr.record_call(priority, success=False)
                        # Synthesis has a fast deterministic fallback, so a long
                        # rate-limit backoff is counterproductive — it compounds
                        # across the many per-agent/arbiter synthesis calls in one
                        # investigation and blows the deliberation timeout. Cap the
                        # backoff tightly and move to the next candidate quickly.
                        ra_header = resp.headers.get("Retry-After")
                        delay = min(float(ra_header) if ra_header else 1.5, 2.0)
                        logger.warning(
                            f"Synthesis {target_provider}/{target_model} rate-limited — "
                            f"trying next candidate (backoff={delay:.1f}s, capped)"
                        )
                        await asyncio.sleep(delay)
                        continue

                    # Fast-fail on 413 — prompt too large for this model, try next.
                    if resp.status_code == 413:
                        logger.warning(
                            f"Synthesis {target_provider}/{target_model} payload too large — "
                            f"skipping to next candidate"
                        )
                        continue

                    resp.raise_for_status()

                    if target_provider == "groq":
                        result = resp.json()["choices"][0]["message"].get("content", "").strip()
                    else:
                        result = (
                            resp.json()["candidates"][0]["content"]["parts"][0]
                            .get("text", "")
                            .strip()
                        )
                    if result:
                        await quota_mgr.record_call(priority, success=True)
                        logger.debug(
                            "Synthesis succeeded",
                            provider=target_provider,
                            model=target_model,
                            response_chars=len(result),
                        )
                    return result

                except Exception as exc:
                    await quota_mgr.record_call(priority, success=False)
                    last_exc = exc
                    logger.warning(f"Synthesis candidate {model_spec} failed: {exc}")

            # All candidates exhausted — try one final lightweight Gemini model
            # after a short pause. Using gemini-2.0-flash-lite which has a separate
            # quota bucket from the primary flash model.
            if (
                self.gemini_api_key
                and not is_placeholder_secret(self.gemini_api_key)
                and (self.use_arbiter_tier or self.provider == "gemini")
                and getattr(self.config, "gemini_text_calls_enabled", False)
            ):
                logger.warning(
                    "All synthesis candidates exhausted. Retrying with gemini-2.0-flash-lite in 5s..."
                )
                await asyncio.sleep(5.0)
                try:
                    client = await self._get_client()
                    req_timeout = timeout_override or 30.0
                    lite_model = "gemini-2.0-flash-lite"
                    url = f"https://generativelanguage.googleapis.com/v1beta/models/{lite_model}:generateContent"
                    req_headers = {"x-goog-api-key": self.gemini_api_key}
                    # Use a hard-trimmed prompt for the lite model retry
                    lite_limit = self._MODEL_PROMPT_CHAR_LIMITS.get(lite_model, 60000)
                    lite_user = user_content[:lite_limit // 2]
                    estimated_tokens = (len(system_prompt) + len(lite_user)) // 4 + tokens
                    allowed, quota_result = await ProviderQuotaGuard.check_and_record(
                        "gemini",
                        lite_model,
                        estimated_tokens=estimated_tokens,
                        tpm_limit_override=self._model_tpm_limit("gemini", lite_model),
                    )
                    if not allowed:
                        logger.warning(
                            "Skipping final Gemini retry because quota guard blocked it",
                            reason=quota_result.reason,
                        )
                        return ""
                    payload = {
                        "contents": [
                            {
                                "role": "user",
                                "parts": [{"text": f"{system_prompt}\n\n{lite_user}"}],
                            }
                        ],
                        "generationConfig": {"temperature": 0.2, "maxOutputTokens": tokens},
                    }
                    if json_mode:
                        payload["generationConfig"]["responseMimeType"] = "application/json"
                    async with LLMClient._global_semaphore:
                        resp = await client.post(url, headers=req_headers, json=payload, timeout=req_timeout)
                    if resp.status_code == 200:
                        result = (
                            resp.json()["candidates"][0]["content"]["parts"][0]
                            .get("text", "")
                            .strip()
                        )
                        if result:
                            logger.info(
                                "Synthesis succeeded on gemini-2.0-flash-lite final retry"
                            )
                            return result
                    else:
                        logger.warning(
                            f"gemini-2.0-flash-lite final retry returned {resp.status_code}"
                        )
                except Exception as final_exc:
                    logger.error(f"gemini-2.0-flash-lite final retry failed: {final_exc}")
                    last_exc = final_exc

            if last_exc:
                logger.error(f"All synthesis candidates failed: {last_exc}")
            return ""

    def _compress_prompt(self, text: str, max_length: int) -> str:
        """Compress prompt by removing redundant phrases and truncating."""
        if len(text) <= max_length:
            return text

        # Remove common filler phrases
        compressed = text
        fillers = [
            "Please analyze the following",
            "Your task is to",
            "Based on the information provided",
            "Please provide a detailed",
            "Make sure to include",
        ]
        for filler in fillers:
            compressed = compressed.replace(filler, "")

        # Truncate to max length
        if len(compressed) > max_length:
            compressed = compressed[:max_length] + "..."

        return compressed.strip()

    def _generate_template_synthesis(self, findings_json: str | dict) -> str:
        """Generate deterministic synthesis from findings when API unavailable."""
        try:
            data = findings_json if isinstance(findings_json, dict) else json.loads(findings_json)

            summary_parts = []

            # Count real tool executions
            tool_results = data.get("tool_results", [])
            if tool_results:
                tools_executed = len([t for t in tool_results if t.get("status") != "skipped"])
                summary_parts.append(f"Executed {tools_executed} forensic tools.")
            elif "tool_results" in data:
                tools_run = len(data["tool_results"])
                summary_parts.append(f"{tools_run} forensic tools executed.")

            # Extract manipulation probability
            if "manipulation_probability" in data:
                prob = data["manipulation_probability"]
                if prob > 0.7:
                    summary_parts.append(f"High manipulation indicators ({prob:.1%}).")
                elif prob > 0.4:
                    summary_parts.append(f"Moderate manipulation signals ({prob:.1%}).")
                else:
                    summary_parts.append(f"Low manipulation probability ({prob:.1%}).")

            # List key findings (NOT templates)
            key_findings = data.get("key_findings", [])
            real_findings = [f for f in key_findings if f and "template" not in str(f).lower()]
            if real_findings:
                summary_parts.append("Findings: " + "; ".join(real_findings[:3]))

            # If we have NO real data, be explicit
            if not summary_parts:
                return "No reportable signal could be extracted from the structured analysis output; refer to the per-tool findings."

            return " ".join(summary_parts)

        except Exception:
            return "A synthesis summary could not be generated from the analysis output; refer to the per-tool findings in the detailed report."

    async def generate_synthesis(
        self,
        system_prompt: str,
        user_content: str,
        max_tokens: int | None = None,
        timeout_override: float | None = None,
        json_mode: bool = True,
        priority: str = "medium",
    ) -> str:
        """Executive summary synthesis with cross-provider fallback support and priority."""
        # Check Groq rate limiter proactively
        if self.provider == "groq":
            allowed, reason = await self._groq_limiter.acquire()
            if not allowed:
                self._last_synthesis_blocked_reason = reason
                logger.warning(f"Groq rate limit hit: {reason}. Falling back to template synthesis.")
                return ""

        # Check quota first
        from core.quota_manager import get_quota_manager

        effective_priority = "critical" if self.use_arbiter_tier else priority
        provider = self.provider if self.provider != "none" else "groq"
        rpm_limit = getattr(self.config, f"{provider}_rpm_limit", 15)
        rpd_limit = getattr(self.config, f"{provider}_rpd_limit", 1500)

        quota_mgr = get_quota_manager(
            f"{provider}_text",
            rpm_limit=rpm_limit,
            rpd_limit=rpd_limit
        )

        estimated_tokens = (len(system_prompt) + len(user_content)) // 4 + (max_tokens or 2048)
        allowed, reason = await quota_mgr.can_make_call(
            effective_priority, estimated_tokens=estimated_tokens
        )

        if not allowed:
            self._last_synthesis_blocked_reason = reason
            logger.warning(
                f"Quota manager blocked synthesis: {reason}. Using template synthesis.",
                priority=effective_priority
            )
            return ""

        async with LLMClient._synthesis_semaphore:
            self._last_synthesis_blocked_reason = ""
            # No fallback model cascade: restrict to primary model only for synthesis.
            original_fallback_models = self.fallback_models
            self.fallback_models = []
            try:
                result = await self._generate_synthesis_inner(
                    system_prompt=system_prompt,
                    user_content=user_content,
                    max_tokens=max_tokens,
                    timeout_override=timeout_override,
                    json_mode=json_mode,
                )
            finally:
                self.fallback_models = original_fallback_models
            return result


def parse_llm_step(content: str, tool_call: dict[str, Any] | None) -> dict[str, Any]:
    """
    Parse LLM output into a structured ReAct step.

    Native tool calls (from API function-calling) produce ACTION steps
    with high reliability. Text-encoded actions are also parsed.
    Anything else is treated as a THOUGHT.
    """
    content = (content or "").strip()

    if tool_call:
        return {
            "step_type": "ACTION",
            "content": f"Using tool: {tool_call['name']}",
            "tool_name": tool_call["name"],
            "tool_input": tool_call.get("arguments", {}),
        }

    for prefix in ("Action:", "Use tool", "Call", "Execute", "Calling"):
        if content.startswith(prefix):
            rest = content[len(prefix) :].strip()
            if "(" in rest:
                tool_name = rest.split("(")[0].strip()
                if tool_name:
                    return {
                        "step_type": "ACTION",
                        "content": rest,
                        "tool_name": tool_name,
                        "tool_input": {},
                    }

    return {"step_type": "THOUGHT", "content": content}
