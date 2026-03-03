"""
Forensic Council Agents Package.

Contains the base ForensicAgent class and 5 specialist agents:
- Agent1: Image Integrity Analysis
- Agent2: Audio/Media Analysis
- Agent3: Object/Weapon Detection
- Agent4: Video Analysis
- Agent5: Metadata Analysis
"""

from agents.base_agent import ForensicAgent, SelfReflectionReport

__all__ = [
    "ForensicAgent",
    "SelfReflectionReport",
]
