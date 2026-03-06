"""
LLM Client for Forensic Council ReAct Loop Reasoning.

Provides async LLM API clients for OpenAI and Anthropic,
with a unified interface for generating ReAct reasoning steps.
"""

from __future__ import annotations

import asyncio
import json
from dataclasses import dataclass
from typing import Any, Optional

import httpx
from core.config import Settings
from core.logging import get_logger

logger = get_logger(__name__)


@dataclass
class LLMResponse:
    """Structured response from LLM."""
    content: str
    tool_call: Optional[dict[str, Any]] = None
    usage: dict[str, int] | None = None


class LLMClient:
    """Async LLM client for forensic reasoning."""
    
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
        """
        Generate the next reasoning step in a ReAct loop.
        
        Args:
            system_prompt: System prompt with forensic context
            react_chain: Current chain of ReAct steps
            available_tools: List of available tools with descriptions
            current_task: Current task being worked on (optional)
            
        Returns:
            LLMResponse with the next thought or action
        """
        if self.provider == "none" or not self.api_key:
            logger.warning("LLM not configured, returning None")
            return LLMResponse(content="")
        
        # Build the conversation
        messages = self._build_messages(system_prompt, react_chain, current_task)
        
        try:
            if self.provider == "openai":
                return await self._call_openai(messages, available_tools)
            elif self.provider == "anthropic":
                return await self._call_anthropic(messages, available_tools)
            else:
                logger.error(f"Unknown LLM provider: {self.provider}")
                return LLMResponse(content="")
        except Exception as e:
            logger.error(f"LLM call failed: {e}")
            return LLMResponse(content="")
    
    def _build_messages(
        self,
        system_prompt: str,
        react_chain: list[dict[str, Any]],
        current_task: str | None,
    ) -> list[dict[str, str]]:
        """Build message list from ReAct chain."""
        messages = [{"role": "system", "content": system_prompt}]
        
        if current_task:
            messages.append({
                "role": "user",
                "content": f"Current task: {current_task}"
            })
        
        # Add ReAct chain as context
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
                    "content": f"Action: {tool_name}({json.dumps(tool_input)})"
                })
            elif step_type == "OBSERVATION":
                messages.append({"role": "user", "content": f"Observation: {content}"})
        
        return messages
    
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
        
        # Convert tools to OpenAI format
        tools = []
        for tool in available_tools:
            tools.append({
                "type": "function",
                "function": {
                    "name": tool["name"],
                    "description": tool.get("description", ""),
                    "parameters": tool.get("parameters", {"type": "object", "properties": {}}),
                }
            })
        
        payload = {
            "model": self.model,
            "messages": messages,
            "temperature": self.temperature,
            "max_tokens": self.max_tokens,
        }
        
        if tools:
            payload["tools"] = tools
            payload["tool_choice"] = "auto"
        
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            response = await client.post(
                url,
                headers=headers,
                json=payload,
            )
            response.raise_for_status()
            data = response.json()
            
            choice = data["choices"][0]
            message = choice["message"]
            
            # Check for tool calls
            if "tool_calls" in message and message["tool_calls"]:
                tool_call = message["tool_calls"][0]
                return LLMResponse(
                    content=message.get("content", ""),
                    tool_call={
                        "name": tool_call["function"]["name"],
                        "arguments": json.loads(tool_call["function"]["arguments"]),
                    },
                    usage=data.get("usage"),
                )
            
            return LLMResponse(
                content=message.get("content", ""),
                usage=data.get("usage"),
            )
    
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
        
        # Separate system message
        system_message = ""
        chat_messages = []
        
        for msg in messages:
            if msg["role"] == "system":
                system_message = msg["content"]
            else:
                chat_messages.append(msg)
        
        payload = {
            "model": self.model,
            "max_tokens": self.max_tokens,
            "messages": chat_messages,
        }
        if self.temperature > 0:
            payload["temperature"] = self.temperature
        
        if system_message:
            payload["system"] = system_message
        
        # Add tools if available (Anthropic supports function calling)
        if available_tools:
            payload["tools"] = [
                {
                    "name": tool["name"],
                    "description": tool.get("description", ""),
                    "input_schema": tool.get("parameters", {"type": "object", "properties": {}}),
                }
                for tool in available_tools
            ]
        
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            response = await client.post(
                url,
                headers=headers,
                json=payload,
            )
            response.raise_for_status()
            data = response.json()
            
            content = ""
            tool_call = None
            
            for block in data.get("content", []):
                if block["type"] == "text":
                    content += block["text"]
                elif block["type"] == "tool_use":
                    tool_call = {
                        "name": block["name"],
                        "arguments": block["input"],
                    }
            
            return LLMResponse(
                content=content,
                tool_call=tool_call,
                usage=data.get("usage"),
            )


def parse_llm_step(content: str, tool_call: dict[str, Any] | None) -> dict[str, Any]:
    """
    Parse LLM output into a ReAct step.
    
    Args:
        content: Raw LLM output
        tool_call: Optional tool call from LLM
        
    Returns:
        Dict with step_type, content, and optional tool info
    """
    content = content.strip()
    
    # If there's a tool call, this is an ACTION step
    if tool_call:
        return {
            "step_type": "ACTION",
            "content": f"Using tool: {tool_call['name']}",
            "tool_name": tool_call["name"],
            "tool_input": tool_call["arguments"],
        }
    
    # Check if content starts with action keywords
    action_keywords = ["Action:", "Use tool", "Call", "Execute"]
    for keyword in action_keywords:
        if content.startswith(keyword):
            # Try to extract tool name
            rest = content[len(keyword):].strip()
            if "(" in rest:
                tool_name = rest.split("(")[0].strip()
                return {
                    "step_type": "ACTION",
                    "content": rest,
                    "tool_name": tool_name,
                    "tool_input": {},
                }
    
    # Default to THOUGHT step
    return {
        "step_type": "THOUGHT",
        "content": content,
    }
