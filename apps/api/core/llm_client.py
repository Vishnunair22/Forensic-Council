"""
LLM Client for Forensic Council ReAct Loop Reasoning.

Provides async LLM API clients for OpenAI, Anthropic, and Groq,
with a unified interface for generating ReAct reasoning steps.

    - groq      -> Groq API (Llama 3.3 70B, ~700 tok/s, recommended)
    - gemini    -> Google Gemini API (Gemini 2.5 Flash)
    - openai    -> OpenAI API (GPT-4o, GPT-4)
    - anthropic -> Anthropic API (Claude 3.5 Sonnet)
    - none      -> Disabled; task-decomposition driver handles all steps
"""

from __future__ import annotations

import asyncio
import json
import time
from dataclasses import dataclass
from typing import Any

import httpx

from core.config import Settings
from core.observability import get_tracer
from core.retry import CircuitBreaker
from core.structured_logging import get_logger

logger = get_logger(__name__)
_tracer = get_tracer("forensic-council.llm")

_RETRYABLE_STATUS = {429, 500, 502, 503, 504}
_MAX_RETRIES = 3
_BASE_BACKOFF = 2.0
_MAX_BACKOFF = 5.0  # cap per-attempt wait so worker never blocks more than ~15 s total

# Per-provider circuit breakers shared across all LLMClient instances.
# Keyed by "provider:model" so a failing model on one provider does not
# block the same model on a different provider (or a healthy fallback).
_provider_circuit_breakers: dict[str, "CircuitBreaker"] = {}


def _get_provider_breaker(provider: str, model: str) -> "CircuitBreaker":
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


class LLMClient:
    """
    Async LLM client with unified interface across Groq, OpenAI, and Anthropic.

    All requests run through exponential-backoff retry logic.
    Groq (Llama 3.3 70B) is the recommended provider for this project:
    - ~700 tok/s vs ~80 tok/s on OpenAI
    - Full function-calling support
    - Free tier supports full investigations in dev
    """

    def __init__(self, config: Settings, use_arbiter_tier: bool = False):
        self.config = config
        self.use_arbiter_tier = use_arbiter_tier

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
            LLMClient._global_semaphore = asyncio.Semaphore(4)

    async def _get_client(self, timeout_override: float | None = None) -> httpx.AsyncClient:
        """Return a shared httpx.AsyncClient, creating it on first use.

        Connection pool is sized for concurrent agent + arbiter LLM calls:
        5 agents × 1 synthesis + 4 arbiter narratives = ~10 concurrent connections.
        Pool allows 50 max with 20 keepalive for burst tolerance.
        """
        timeout = timeout_override or self.timeout
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(
                timeout=timeout,
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
        _placeholder_signals = ("your_", "_here", "placeholder", "changeme", "sk-xxx")
        key_lower = self.api_key.lower()
        return not any(sig in key_lower for sig in _placeholder_signals)

    async def health_check(self) -> bool:
        """Quick probe to verify LLM service is reachable (3s timeout)."""
        if not self.is_available:
            return False
        try:
            client = await self._get_client(timeout_override=3.0)
            url_map = {
                "groq": "https://api.groq.com/openai/v1/models",
                "gemini": f"https://generativelanguage.googleapis.com/v1beta/models/{self.model}?key={self.api_key}",
                "openai": "https://api.openai.com/v1/models",
                "anthropic": "https://api.anthropic.com/v1/models",
            }
            url = url_map.get(self.provider)
            if not url:
                return True
            headers = {}
            if self.provider == "groq" or self.provider == "openai":
                headers = {"Authorization": f"Bearer {self.api_key}"}
            elif self.provider == "anthropic":
                headers = {"x-api-key": self.api_key, "anthropic-version": "2023-06-01"}

            # For Gemini, the key is usually in the URL for v1beta, or we can use headers
            if self.provider == "gemini":
                resp = await asyncio.wait_for(client.get(url), timeout=3.0)
            else:
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
                            self.api_key = self.config.llm_api_key
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
        elif self.provider == "openai":
            resp = await self._call_openai(messages, available_tools)
        elif self.provider == "anthropic":
            resp = await self._call_anthropic(messages, available_tools)
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
                        "content": f"Action: {tool_name}({json.dumps(tool_input)})",
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
                    wait = min(_BASE_BACKOFF * (2**attempt), _MAX_BACKOFF)
                    logger.warning(
                        f"LLM API {response.status_code}, retrying in {wait:.1f}s (attempt {attempt + 1}/{_MAX_RETRIES})"
                    )
                    await asyncio.sleep(wait)
                    continue
                return response
            except (httpx.TimeoutException, httpx.NetworkError) as e:
                if attempt < _MAX_RETRIES - 1:
                    wait = min(_BASE_BACKOFF * (2**attempt), _MAX_BACKOFF)
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
            if model and model not in candidates:
                candidates.append(model)
        return candidates

    async def _call_groq(
        self,
        messages: list[dict[str, str]],
        available_tools: list[dict[str, Any]],
    ) -> LLMResponse:
        """Call Groq API using model candidates, skipping cross-provider specs."""
        if not self.is_available:
            raise RuntimeError("Groq API key is placeholder or missing")

        url = "https://api.groq.com/openai/v1/chat/completions"
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        tools = self._tools_to_openai_format(available_tools)
        base_payload: dict[str, Any] = {
            "messages": messages,
            "temperature": self.temperature,
            "max_tokens": self.max_tokens,
        }
        if tools:
            base_payload["tools"] = tools
            base_payload["tool_choice"] = "auto"

        client = await self._get_client()
        last_exc: Exception | None = None

        for model in self._get_model_candidates():
            # Skip candidates that specify a different provider (e.g. "gemini/...")
            if "/" in model and not model.startswith("groq/"):
                continue

            target_model = model.split("/", 1)[1] if "/" in model else model
            payload = {**base_payload, "model": target_model}

            try:
                response = await self._with_retry(
                    lambda p=payload: client.post(url, headers=headers, json=p)
                )
                response.raise_for_status()
                return self._parse_openai_response(response.json())
            except Exception as exc:
                last_exc = exc
                logger.warning(f"Groq candidate {model} failed: {exc}")

        raise RuntimeError("All Groq candidates failed") from last_exc

    async def _call_gemini(
        self,
        messages: list[dict[str, str]],
        available_tools: list[dict[str, Any]],
    ) -> LLMResponse:
        """Call Google Gemini API (v1beta)."""
        if not self.api_key:
            raise RuntimeError("Gemini API key missing")

        url = f"https://generativelanguage.googleapis.com/v1beta/models/{self.model}:generateContent?key={self.api_key}"

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
        response = await self._with_retry(lambda: client.post(url, json=payload))
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

    async def _call_openai(
        self,
        messages: list[dict[str, str]],
        available_tools: list[dict[str, Any]],
    ) -> LLMResponse:
        """Call OpenAI API."""
        if not self.is_available:
            raise RuntimeError("OpenAI API key is placeholder or missing — cannot call LLM")
        url = "https://api.openai.com/v1/chat/completions"
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        tools = self._tools_to_openai_format(available_tools)
        payload: dict[str, Any] = {
            "model": self.model,
            "messages": messages,
            "temperature": self.temperature,
            "max_tokens": self.max_tokens,
        }
        if tools:
            payload["tools"] = tools
            payload["tool_choice"] = "auto"

        client = await self._get_client()
        response = await self._with_retry(lambda: client.post(url, headers=headers, json=payload))
        response.raise_for_status()
        return self._parse_openai_response(response.json())

    async def _call_anthropic(
        self,
        messages: list[dict[str, str]],
        available_tools: list[dict[str, Any]],
    ) -> LLMResponse:
        """Call Anthropic Claude API."""
        if not self.is_available:
            raise RuntimeError("Anthropic API key is placeholder or missing — cannot call LLM")
        url = "https://api.anthropic.com/v1/messages"
        headers = {
            "x-api-key": self.api_key,
            "Content-Type": "application/json",
            "anthropic-version": "2023-06-01",
        }
        system_message = ""
        chat_messages: list[dict] = []
        for msg in messages:
            if msg["role"] == "system":
                system_message = msg["content"]
            else:
                chat_messages.append(msg)

        payload: dict[str, Any] = {
            "model": self.model,
            "max_tokens": self.max_tokens,
            "messages": chat_messages,
        }
        if self.temperature > 0:
            payload["temperature"] = self.temperature
        if system_message:
            payload["system"] = system_message
        if available_tools:
            payload["tools"] = [
                {
                    "name": t["name"],
                    "description": t.get("description", ""),
                    "input_schema": t.get("parameters", {"type": "object", "properties": {}}),
                }
                for t in available_tools
            ]

        client = await self._get_client()
        response = await self._with_retry(lambda: client.post(url, headers=headers, json=payload))
        response.raise_for_status()
        data = response.json()

        content = ""
        tool_call = None
        for block in data.get("content", []):
            if block["type"] == "text":
                content += block["text"]
            elif block["type"] == "tool_use":
                tool_call = {"name": block["name"], "arguments": block["input"]}

        return LLMResponse(content=content, tool_call=tool_call, usage=data.get("usage"))

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
    def _parse_openai_response(data: dict[str, Any]) -> LLMResponse:
        """Parse an OpenAI/Groq-format response dict."""
        choice = data["choices"][0]
        message = choice["message"]

        if message.get("tool_calls"):
            tc = message["tool_calls"][0]
            raw_args = tc["function"]["arguments"]
            try:
                args = json.loads(raw_args) if isinstance(raw_args, str) else raw_args
            except json.JSONDecodeError:
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

    async def generate_synthesis(
        self,
        system_prompt: str,
        user_content: str,
        max_tokens: int | None = None,
        timeout_override: float | None = None,
        json_mode: bool = True,
    ) -> str:
        """Executive summary synthesis with cross-provider fallback support."""
        with _tracer.start_as_current_span("llm.generate_synthesis"):
            if not self.is_available:
                return ""

            tokens = max_tokens or min(self.max_tokens, 1500)
            candidates = self._get_model_candidates()
            last_exc: Exception | None = None

            for model_spec in candidates:
                # Resolve provider and model from spec (e.g. "gemini/gemini-2.5-flash")
                target_provider = self.provider
                target_model = model_spec
                target_api_key = self.api_key

                if "/" in model_spec:
                    parts = model_spec.split("/", 1)
                    target_provider = parts[0].lower()
                    target_model = parts[1]
                    # Route to correct key if switching providers
                    if target_provider == "gemini":
                        target_api_key = self.gemini_api_key
                    elif target_provider == "groq":
                        target_api_key = self.config.llm_api_key

                if not target_api_key or target_api_key.startswith("REPLACE_"):
                    continue

                try:
                    # Dispatch to specific provider logic
                    if target_provider in ("groq", "openai"):
                        url = (
                            "https://api.groq.com/openai/v1/chat/completions"
                            if target_provider == "groq"
                            else "https://api.openai.com/v1/chat/completions"
                        )
                        headers = {
                            "Authorization": f"Bearer {target_api_key}",
                            "Content-Type": "application/json",
                        }
                        payload = {
                            "model": target_model,
                            "messages": [
                                {"role": "system", "content": system_prompt},
                                {"role": "user", "content": user_content},
                            ],
                            "temperature": 0.2,
                            "max_tokens": tokens,
                        }
                        if json_mode:
                            payload["response_format"] = {"type": "json_object"}

                        client = await self._get_client(timeout_override=timeout_override or 15.0)
                        resp = await self._with_retry(
                            lambda c=client, u=url, h=headers, p=payload: c.post(
                                u, headers=h, json=p
                            )
                        )
                        resp.raise_for_status()
                        return resp.json()["choices"][0]["message"].get("content", "").strip()

                    elif target_provider == "gemini":
                        url = f"https://generativelanguage.googleapis.com/v1beta/models/{target_model}:generateContent?key={target_api_key}"
                        payload = {
                            "contents": [
                                {
                                    "role": "user",
                                    "parts": [{"text": f"{system_prompt}\n\n{user_content}"}],
                                }
                            ],
                            "generationConfig": {"temperature": 0.2, "maxOutputTokens": tokens},
                        }
                        if json_mode:
                            payload["generationConfig"]["responseMimeType"] = "application/json"

                        client = await self._get_client(timeout_override=timeout_override or 15.0)
                        resp = await self._with_retry(
                            lambda c=client, u=url, p=payload: c.post(u, json=p)
                        )
                        resp.raise_for_status()
                        return (
                            resp.json()["candidates"][0]["content"]["parts"][0]
                            .get("text", "")
                            .strip()
                        )

                except Exception as exc:
                    last_exc = exc
                    logger.warning(f"Synthesis candidate {model_spec} failed: {exc}")

            if last_exc:
                logger.error(f"All synthesis candidates failed: {last_exc}")
            return ""


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
