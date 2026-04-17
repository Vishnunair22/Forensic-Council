"""
Self-reflection data models and reasoning utilities for Forensic Agents.
Extracted from base_agent.py to improve maintainability.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any, Literal

from pydantic import BaseModel, Field

from core.react_loop import AgentFinding


class SelfReflectionReport(BaseModel):
    """
    Report from self-reflection pass.

    Generated after each investigation to ensure quality and completeness.
    """

    all_tasks_complete: bool = Field(
        default=False, description="Whether all tasks in decomposition are complete"
    )
    incomplete_tasks: list[str] = Field(
        default_factory=list, description="List of incomplete task descriptions"
    )
    overconfident_findings: list[str] = Field(
        default_factory=list, description="Findings that may have inflated confidence"
    )
    untreated_absences: list[str] = Field(
        default_factory=list,
        description="Absence of expected data that wasn't analyzed",
    )
    deprioritized_avenues: list[str] = Field(
        default_factory=list,
        description="Investigation avenues that were deprioritized",
    )
    court_defensible: bool = Field(
        default=False, description="Whether findings are defensible in court"
    )
    reflection_notes: str = Field(
        default="", description="Additional notes from reflection"
    )


def _attach_llm_reasoning_to_findings(
    findings: list[AgentFinding],
    react_chain: list[Any],
) -> list[AgentFinding]:
    """
    Attach LLM THOUGHT reasoning to the AgentFinding that followed it.

    When the LLM drives the ReAct loop, each ACTION step is typically
    preceded by a THOUGHT step containing the LLM's interpretation of
    previous observations and its reasoning for choosing the next tool.

    This function matches each finding (created from a tool ACTION+OBSERVATION)
    to the THOUGHT step that immediately preceded that ACTION in the chain, and
    stores the LLM reasoning text in finding.metadata["llm_reasoning"].

    It also scans THOUGHT steps for explicit anomaly language and appends
    those insights to finding.reasoning_summary so they appear in the
    per-agent report cards.

    Args:
        findings: List of AgentFinding objects from the loop
        react_chain: Full list of ReActStep objects from the loop

    Returns:
        The same findings list with llm_reasoning populated where available
    """
    if not findings or not react_chain:
        return findings

    # Build index: tool_name -> list of THOUGHT contents that preceded it
    # Walk the chain and collect (thought_content, action_tool_name) pairs
    thought_before_action: list[tuple[str, str]] = []
    prev_thought = ""
    for step in react_chain:
        stype = (
            step.step_type if hasattr(step, "step_type") else step.get("step_type", "")
        )
        if stype == "THOUGHT":
            content = (
                step.content if hasattr(step, "content") else step.get("content", "")
            )
            prev_thought = content
        elif stype == "ACTION" and prev_thought:
            tool = (
                step.tool_name
                if hasattr(step, "tool_name")
                else step.get("tool_name", "")
            )
            if tool:
                thought_before_action.append((prev_thought, tool))
            prev_thought = ""

    # Map tool_name -> list of reasoning snippets (in order of occurrence)
    tool_reasoning: dict[str, list[str]] = {}
    for thought, tool in thought_before_action:
        tool_reasoning.setdefault(tool, []).append(thought)

    # Usage counters so we consume each reasoning entry at most once per finding
    tool_usage: dict[str, int] = {}

    # Anomaly signal words — thoughts containing these are especially important
    _ANOMALY_SIGNALS = (
        "anomal",
        "manipulat",
        "inconsisten",
        "suspicious",
        "unusual",
        "mismatch",
        "artifact",
        "synthetic",
        "deepfake",
        "edited",
        "absent",
        "missing",
        "unexpected",
        "flag",
    )

    for finding in findings:
        tool_name = (
            finding.metadata.get("tool_name", "")
            if hasattr(finding, "metadata")
            else ""
        )
        if not tool_name:
            continue

        idx = tool_usage.get(tool_name, 0)
        reasoning_list = tool_reasoning.get(tool_name, [])

        if idx < len(reasoning_list):
            thought_text = reasoning_list[idx]
            tool_usage[tool_name] = idx + 1

            # Store full LLM thought in metadata
            if hasattr(finding, "metadata") and isinstance(finding.metadata, dict):
                finding.metadata["llm_reasoning"] = thought_text

            # If the thought contains anomaly language, prepend a note to
            # reasoning_summary so it surfaces in the report card
            thought_lower = thought_text.lower()
            has_anomaly_signal = any(sig in thought_lower for sig in _ANOMALY_SIGNALS)
            if has_anomaly_signal and thought_text.strip():
                # Take the most relevant sentence (the one with the signal word)
                sentences = [
                    s.strip()
                    for s in thought_text.replace("\n", " ").split(".")
                    if s.strip()
                ]
                relevant = [
                    s
                    for s in sentences
                    if any(sig in s.lower() for sig in _ANOMALY_SIGNALS)
                ]
                if relevant:
                    insight = relevant[0][:200]
                    if hasattr(finding, "reasoning_summary"):
                        existing = finding.reasoning_summary or ""
                        if insight not in existing:
                            finding.reasoning_summary = (
                                f"[LLM] {insight}. {existing}".strip()
                            )
                        elif insight not in existing: # duplicate check
                             finding.reasoning_summary = (
                                f"[LLM] {insight}. {existing}".strip()
                            )

    return findings
