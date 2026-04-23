"""
Central Agent Registry
======================

Single source of truth for forensic agent IDs, classes, and metadata.
Used by the Pipeline and Inter-Agent Bus to prevent hardcoded redundancy.
"""

from typing import Any

from core.agents import AgentID
from core.structured_logging import get_logger

logger = get_logger(__name__)

class AgentRegistry:
    """Registry for discovering and instantiating Forensic Agents."""

    _instance = None
    _agents: dict[str, type] = {}
    _metadata: dict[str, dict[str, Any]] = {}

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._register_core_agents()
        return cls._instance

    def _register_core_agents(self):
        """Register the 5 primary specialist agents."""
        from agents.agent1_image import Agent1Image
        from agents.agent2_audio import Agent2Audio
        from agents.agent3_object import Agent3Object
        from agents.agent4_video import Agent4Video
        from agents.agent5_metadata import Agent5Metadata

        self.register(AgentID.AGENT1, Agent1Image, {"modality": "IMAGE", "name": "Image Integrity", "permitted_callees": [AgentID.AGENT5]})
        self.register(AgentID.AGENT2, Agent2Audio, {"modality": "AUDIO", "name": "Audio Forensics", "permitted_callees": [AgentID.AGENT4]})
        self.register(AgentID.AGENT3, Agent3Object, {"modality": "OBJECT", "name": "Object & Scene", "permitted_callees": [AgentID.AGENT1, AgentID.AGENT5]})
        self.register(AgentID.AGENT4, Agent4Video, {"modality": "VIDEO", "name": "Video Forensics", "permitted_callees": [AgentID.AGENT2]})
        self.register(AgentID.AGENT5, Agent5Metadata, {"modality": "METADATA", "name": "Metadata & Provenance", "permitted_callees": []})

    def register(self, agent_id: str, agent_class: type, metadata: dict[str, Any] = None):
        """Register a new agent."""
        self._agents[agent_id] = agent_class
        self._metadata[agent_id] = metadata or {}
        logger.info(f"Registered agent: {agent_id}")

    def get_agent_class(self, agent_id: str) -> type:
        """Get agent class for instantiation."""
        if agent_id not in self._agents:
            raise ValueError(f"Agent {agent_id} not found in registry")
        return self._agents[agent_id]

    def get_all_agent_ids(self) -> list[str]:
        """Get all registered agent IDs."""
        return list(self._agents.keys())

    def get_permitted_callees(self, agent_id: str) -> list[str]:
        """Get list of agents this agent is permitted to call."""
        if agent_id == AgentID.ARBITER:
             return self.get_all_agent_ids()
        return self._metadata.get(agent_id, {}).get("permitted_callees", [])

# Singleton accessor
def get_agent_registry() -> AgentRegistry:
    return AgentRegistry()
