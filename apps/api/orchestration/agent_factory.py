"""
Agent Factory
=============

Creates and re-invokes forensic agents for challenge loops without
requiring direct knowledge of agent instantiation details.
"""

from __future__ import annotations

import inspect
from typing import Any
from uuid import UUID

from core.agent_registry import get_agent_registry
from core.config import Settings
from core.structured_logging import get_logger

logger = get_logger(__name__)


def _serialize_react_chain(react_chain: list[Any]) -> list[dict[str, Any]]:
    """Convert ReActStep objects to JSON-safe dicts."""
    serialized: list[dict[str, Any]] = []
    for step in react_chain:
        if isinstance(step, dict):
            serialized.append(step)
        elif hasattr(step, "model_dump"):
            serialized.append(step.model_dump(mode="json"))
        else:
            serialized.append({"content": str(step)})
    return serialized


class AgentLoopResult:
    """Result from running an agent's investigation loop."""

    def __init__(
        self,
        agent_id: str,
        findings: list[dict[str, Any]],
        reflection_report: dict[str, Any],
        react_chain: list[dict[str, Any]],
        error: str | None = None,
        agent_active: bool = True,
        supports_file_type: bool = True,
        deep_findings_count: int = 0,
    ):
        self.agent_id = agent_id
        self.findings = findings
        self.reflection_report = reflection_report
        self.react_chain = react_chain
        self.error = error
        self.agent_active = agent_active
        self.supports_file_type = supports_file_type
        self.deep_findings_count = deep_findings_count


class AgentFactory:
    """
    Factory for creating and re-invoking forensic agents.

    Provides a clean interface for the Arbiter to re-invoke agents
    during challenge loops without needing direct knowledge of agent
    instantiation details.
    """

    def __init__(
        self,
        config: Settings,
        working_memory,
        episodic_memory,
        custody_logger,
        evidence_store,
        inter_agent_bus=None,
    ):
        self.config = config
        self.working_memory = working_memory
        self.episodic_memory = episodic_memory
        self.custody_logger = custody_logger
        self.evidence_store = evidence_store
        self.inter_agent_bus = inter_agent_bus
        self._evidence_artifact = None

    def set_evidence_artifact(self, artifact) -> None:
        """Set the evidence artifact for agent re-invocation."""
        self._evidence_artifact = artifact

    async def reinvoke_agent(
        self,
        agent_id: str,
        session_id: UUID,
        challenge_context: dict[str, Any],
    ) -> dict[str, Any]:
        """
        Re-invoke an agent with challenge context.

        Args:
            agent_id: ID of the agent to re-invoke (Agent1-5)
            session_id: Session ID for the investigation
            challenge_context: Context from the contradicting finding

        Returns:
            Agent results including findings and reflection report
        """
        if self._evidence_artifact is None:
            raise ValueError("Evidence artifact not set — call set_evidence_artifact first")

        logger.info(
            "Re-invoking agent for challenge loop",
            agent_id=agent_id,
            session_id=str(session_id),
            challenge_id=challenge_context.get("challenge_id"),
        )

        agent_kwargs = {
            "agent_id": agent_id,
            "session_id": session_id,
            "evidence_artifact": self._evidence_artifact,
            "config": self.config,
            "working_memory": self.working_memory,
            "episodic_memory": self.episodic_memory,
            "custody_logger": self.custody_logger,
            "evidence_store": self.evidence_store,
        }

        if agent_id in ("Agent2", "Agent3", "Agent4") and self.inter_agent_bus:
            agent_kwargs["inter_agent_bus"] = self.inter_agent_bus

        registry = get_agent_registry()
        create_agent = getattr(registry, "create_agent", None)
        used_create_agent = callable(create_agent)
        if used_create_agent:
            agent = create_agent(**agent_kwargs)
        else:
            agent_class = self._get_agent_class(agent_id)
            agent = agent_class(**agent_kwargs)

        if challenge_context.get("contradiction"):
            contradiction = challenge_context["contradiction"]
            if isinstance(contradiction, str):
                contradiction = {"finding_type": "contradiction", "detail": contradiction}
            agent._challenge_context = challenge_context

        challenge_id = challenge_context.get("challenge_id")
        if isinstance(challenge_id, str):
            try:
                challenge_id = UUID(challenge_id)
            except ValueError:
                pass

        if used_create_agent and challenge_id is not None:
            maybe_findings = agent.run_investigation(challenge_id)
        else:
            maybe_findings = agent.run_investigation()
        findings = await maybe_findings if inspect.isawaitable(maybe_findings) else maybe_findings

        serialized_findings = [
            f.model_dump(mode="json") if hasattr(f, "model_dump") else f for f in findings
        ]

        reflection_report = (
            getattr(agent, "__dict__", {}).get("_reflection_report")
            if hasattr(agent, "__dict__")
            else getattr(agent, "_reflection_report", None)
        )

        return {
            "agent_id": agent_id,
            "findings": serialized_findings,
            "reflection_report": (
                reflection_report.model_dump(mode="json")
                if reflection_report and hasattr(reflection_report, "model_dump")
                else {}
            ),
            "react_chain": _serialize_react_chain(getattr(agent, "_react_chain", [])),
            "challenge_context": challenge_context,
        }

    def _get_agent_class(self, agent_id: str) -> type:
        """Get the agent class from the central registry."""
        return get_agent_registry().get_agent_class(agent_id)
