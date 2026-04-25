"""
Forensic Agent Definitions
=========================

Core Enums and constants for agent identification across the system.
"""

from enum import StrEnum


class AgentID(StrEnum):
    """Enumeration of all core forensic agents."""

    AGENT1 = "Agent1"
    AGENT2 = "Agent2"
    AGENT3 = "Agent3"
    AGENT4 = "Agent4"
    AGENT5 = "Agent5"
    ARBITER = "Arbiter"

    @property
    def friendly_name(self) -> str:
        """Get the human-readable name for the agent."""
        names = {
            AgentID.AGENT1: "Image Forensics",
            AgentID.AGENT2: "Audio Forensics",
            AgentID.AGENT3: "Object Detection",
            AgentID.AGENT4: "Video Forensics",
            AgentID.AGENT5: "Metadata Forensics",
            AgentID.ARBITER: "Arbiter Synthesis",
        }
        return names.get(self, "Unknown Agent")

    @property
    def modality(self) -> str:
        """Get the primary forensic modality for the agent."""
        modalities = {
            AgentID.AGENT1: "IMAGE",
            AgentID.AGENT2: "AUDIO",
            AgentID.AGENT3: "OBJECT",
            AgentID.AGENT4: "VIDEO",
            AgentID.AGENT5: "METADATA",
            AgentID.ARBITER: "MULTIMODAL",
        }
        return modalities.get(self, "UNKNOWN")
