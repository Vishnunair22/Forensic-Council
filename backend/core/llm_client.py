"""
LLM Client for Forensic Council ReAct Loop Reasoning.

Provides async LLM API clients for OpenAI, Anthropic, and Groq,
with a unified interface for generating ReAct reasoning steps.

Provider routing:
  - groq      -> Groq API (Llama 3.3 70B, ~700 tok/s, recommended)
  - openai    -> OpenAI API (GPT-4o, GPT-4)
  - anthropic -> Anthropic API (Claude 3.5 Sonnet)
  - none      -> Disabled; task-decomposition driver handles all steps
"""

from __future__ import annotations

import asyncio
import json
import time
from dataclasses import dataclass, field
from typing import Any, Optional

import httpx
from core.config import Settings
from core.logging import get_logger

logger = get_logger(__name__)

_RETRYABLE_STATUS = {429, 500, 502, 503, 504}
_MAX_RETRIES = 3
_BASE_BACKOFF = 1.0


@dataclass
class LLMResponse:
    """Structured response from LLM."""
    content: str
    tool_call: Optional[dict[str, Any]] = None
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

    def __init__(self, config: Settings):
        self.config = config
        self.provider = config.llm_provider.lower()
        self.api_key = config.llm_api_key
        self.model = config.llm_model
        self.temperature = config.llm_temperature
        self.max_tokens = config.llm_max_tokens
        self.timeout = config.llm_timeout

    async def generate_reasoning_step(
        self,
        system_prompt: str,
        react_chain: list[dict[str, Any]],
        available_tools: list[dict[str, Any]],
        current_task: str | None = None,
    ) -> LLMResponse:
        """Generate the next reasoning step in a ReAct loop."""
        if self.provider == "none" or not self.api_key:
            logger.debug("LLM not configured - skipping reasoning step")
            return LLMResponse(content="", provider="none")

        messages = self._build_messages(system_prompt, react_chain, current_task)

        t0 = time.monotonic()
        try:
            if self.provider == "groq":
                resp = await self._call_groq(messages, available_tools)
            elif self.provider == "openai":
                resp = await self._call_openai(messages, available_tools)
            elif self.provider == "anthropic":
                resp = await self._call_anthropic(messages, available_tools)
            else:
                logger.error("Unknown LLM provider: %s", self.provider)
                return LLMResponse(content="", provider=self.provider)

            resp.latency_ms = (time.monotonic() - t0) * 1000
            resp.provider = self.provider
            logger.debug(
                "LLM call complete provider=%s model=%s latency_ms=%.0f tool=%s",
                self.provider, self.model, resp.latency_ms,
                resp.tool_call.get("name") if resp.tool_call else None,
            )
            return resp

        except Exception as exc:
            logger.error("LLM call failed: %s", exc)
            return LLMResponse(content="", provider=self.provider)

    def _build_messages(
        self,
        system_prompt: str,
        react_chain: list[dict[str, Any]],
        current_task: str | None,
    ) -> list[dict[str, str]]:
        """Build the message list from the current ReAct chain."""
        messages: list[dict[str, str]] = [
            {"role": "system", "content": system_prompt}
        ]
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
                messages.append({
                    "role": "assistant",
                    "content": f"Action: {tool_name}({json.dumps(tool_input)})",
                })
            elif step_type == "OBSERVATION":
                obs = content
                if len(obs) > 3000:
                    obs = obs[:3000] + "\n... [observation truncated for context length]"
                messages.append({"role": "user", "content": f"Observation: {obs}"})

        return messages

    async def _with_retry(self, coro_factory) -> httpx.Response:
        """Execute an HTTP coroutine factory with exponential-backoff retry."""
        for attempt in range(_MAX_RETRIES):
            try:
                response = await coro_factory()
                if response.status_code in _RETRYABLE_STATUS:
                    wait = _BASE_BACKOFF * (2 ** attempt)
                    logger.warning(
                        "LLM API %s, retrying in %.1fs (attempt %d/%d)",
                        response.status_code, wait, attempt + 1, _MAX_RETRIES,
                    )
                    await asyncio.sleep(wait)
                    continue
                return response
            except httpx.TimeoutException:
                if attempt < _MAX_RETRIES - 1:
                    wait = _BASE_BACKOFF * (2 ** attempt)
                    logger.warning("LLM API timeout, retrying in %.1fs", wait)
                    await asyncio.sleep(wait)
                else:
                    raise
        raise RuntimeError(f"LLM API failed after {_MAX_RETRIES} attempts")

    async def _call_groq(
        self,
        messages: list[dict[str, str]],
        available_tools: list[dict[str, Any]],
    ) -> LLMResponse:
        """
        Call Groq API.

        Groq uses the OpenAI-compatible endpoint.
        llama-3.3-70b-versatile supports full parallel tool calling.
        """
        url = "https://api.groq.com/openai/v1/chat/completions"
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

        async with httpx.AsyncClient(timeout=self.timeout) as client:
            response = await self._with_retry(
                lambda: client.post(url, headers=headers, json=payload)
            )
            response.raise_for_status()
            return self._parse_openai_response(response.json())

    async def _call_openai(
        self,
        messages: list[dict[str, str]],
        available_tools: list[dict[str, Any]],
    ) -> LLMResponse:
        """Call OpenAI API."""
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

        async with httpx.AsyncClient(timeout=self.timeout) as client:
            response = await self._with_retry(
                lambda: client.post(url, headers=headers, json=payload)
            )
            response.raise_for_status()
            return self._parse_openai_response(response.json())

    async def _call_anthropic(
        self,
        messages: list[dict[str, str]],
        available_tools: list[dict[str, Any]],
    ) -> LLMResponse:
        """Call Anthropic Claude API."""
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

        async with httpx.AsyncClient(timeout=self.timeout) as client:
            response = await self._with_retry(
                lambda: client.post(url, headers=headers, json=payload)
            )
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
    ) -> str:
        """
        Single-shot text generation for Arbiter report synthesis.

        No tool calling. Used to write the executive summary and uncertainty
        statement from structured forensic findings. Low temperature (0.2)
        for factual, consistent prose.
        """
        if self.provider == "none" or not self.api_key:
            return ""

        tokens = max_tokens or min(self.max_tokens, 1500)
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_content},
        ]

        try:
            if self.provider in ("groq", "openai"):
                url = (
                    "https://api.groq.com/openai/v1/chat/completions"
                    if self.provider == "groq"
                    else "https://api.openai.com/v1/chat/completions"
                )
                headers = {
                    "Authorization": f"Bearer {self.api_key}",
                    "Content-Type": "application/json",
                }
                payload = {
                    "model": self.model,
                    "messages": messages,
                    "temperature": 0.2,
                    "max_tokens": tokens,
                }
                async with httpx.AsyncClient(timeout=self.timeout) as client:
                    resp = await self._with_retry(
                        lambda: client.post(url, headers=headers, json=payload)
                    )
                    resp.raise_for_status()
                    return resp.json()["choices"][0]["message"].get("content", "").strip()

            elif self.provider == "anthropic":
                url = "https://api.anthropic.com/v1/messages"
                headers = {
                    "x-api-key": self.api_key,
                    "Content-Type": "application/json",
                    "anthropic-version": "2023-06-01",
                }
                payload = {
                    "model": self.model,
                    "max_tokens": tokens,
                    "system": system_prompt,
                    "messages": [{"role": "user", "content": user_content}],
                    "temperature": 0.2,
                }
                async with httpx.AsyncClient(timeout=self.timeout) as client:
                    resp = await self._with_retry(
                        lambda: client.post(url, headers=headers, json=payload)
                    )
                    resp.raise_for_status()
                    data = resp.json()
                return "".join(
                    b["text"] for b in data.get("content", []) if b["type"] == "text"
                ).strip()

        except Exception as exc:
            logger.error("LLM synthesis failed: %s", exc)

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
            rest = content[len(prefix):].strip()
            if "(" in rest:
                return {
                    "step_type": "ACTION",
                    "content": rest,
                    "tool_name": rest.split("(")[0].strip(),
                    "tool_input": {},
                }

    return {"step_type": "THOUGHT", "content": content}
