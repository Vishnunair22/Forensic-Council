"""
Forensic Council Agents Package.

Specialist agents:
- Agent1 (Agent1Image): Pixel integrity — ELA, noise fingerprint, AI-generation detection
- Agent2 (Agent2Audio): Audio authenticity — voice clone, anti-spoofing, ENF analysis
- Agent3 (Agent3Object): Object & scene — YOLO detection, lighting consistency, contraband
- Agent4 (Agent4Video): Temporal video — optical flow, face-swap, frame integrity
- Agent5 (Agent5Metadata): Provenance — EXIF, GPS, C2PA, hex signature, timestamps

Base class: ForensicAgent (modular mixin architecture)
Synthesis: CouncilArbiter (deliberation, challenge loops, report signing)
"""

from agents.agent1_image import Agent1Image
from agents.agent2_audio import Agent2Audio
from agents.agent3_object import Agent3Object
from agents.agent4_video import Agent4Video
from agents.agent5_metadata import Agent5Metadata
from agents.arbiter import CouncilArbiter
from agents.base_agent import ForensicAgent
from agents.reflection import SelfReflectionReport

__all__ = [
    "ForensicAgent",
    "SelfReflectionReport",
    "Agent1Image",
    "Agent2Audio",
    "Agent3Object",
    "Agent4Video",
    "Agent5Metadata",
    "CouncilArbiter",
]
