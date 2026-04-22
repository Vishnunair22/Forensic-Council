"""
ForensicAgent Base Class — Modular Refactor.

Every specialist agent (1-5) extends this base class.
Provides common investigation workflow, self-reflection, and memory integration.
Now decomposed into mixins for better maintainability.
"""

from __future__ import annotations

import math
import uuid
from abc import ABC, abstractmethod
from typing import Any

from agents.mixins.context import AgentContextMixin
from agents.mixins.investigation import AgentInvestigationMixin
from agents.mixins.memory import AgentMemoryMixin
from agents.mixins.reflection import AgentReflectionMixin
from core.config import Settings
from core.custody_logger import CustodyLogger
from core.episodic_memory import EpisodicMemory
from core.evidence import EvidenceArtifact
from core.mime_registry import MimeRegistry
from core.persistence.evidence_store import EvidenceStore
from core.structured_logging import get_logger
from core.tool_registry import ToolRegistry
from core.working_memory import WorkingMemory

logger = get_logger(__name__)


class ForensicAgent(
    AgentContextMixin,
    AgentMemoryMixin,
    AgentInvestigationMixin,
    AgentReflectionMixin,
    ABC,
):
    """
    Modular base class for all forensic specialist agents.

    Inherits from specialized mixins to handle distinct aspects of the
    agent's lifecycle and mandated workflow.
    """

    def __init__(
        self,
        agent_id: str,
        session_id: uuid.UUID,
        evidence_artifact: EvidenceArtifact,
        config: Settings,
        working_memory: WorkingMemory,
        episodic_memory: EpisodicMemory,
        custody_logger: CustodyLogger,
        evidence_store: EvidenceStore,
        inter_agent_bus: Any = None,
    ) -> None:
        """Initialize a forensic agent and all its modular components."""
        self.agent_id = agent_id
        self.session_id = session_id
        self.evidence_artifact = evidence_artifact
        self.config = config
        self.working_memory = working_memory
        self.episodic_memory = episodic_memory
        self.custody_logger = custody_logger
        self.evidence_store = evidence_store
        self.inter_agent_bus = inter_agent_bus

        # Initialize mixin-provided state containers
        self._init_context()

    # ── Abstract properties that must be overridden by Specialists ───────────

    @property
    @abstractmethod
    def agent_name(self) -> str:
        """Human-readable name of this agent."""
        pass

    @property
    @abstractmethod
    def task_decomposition(self) -> list[str]:
        """Static list of tasks for the initial pass."""
        pass

    @property
    @abstractmethod
    def iteration_ceiling(self) -> int:
        """Maximum iterations for the ReAct loop."""
        pass

    @abstractmethod
    async def build_tool_registry(self) -> ToolRegistry:
        """Build and return the tool registry for this agent."""
        pass

    @abstractmethod
    async def build_initial_thought(self) -> str:
        """Build the opening thought for investigation."""
        pass

    # ── Specialist Overridables ──────────────────────────────────────────────

    @property
    def deep_task_decomposition(self) -> list[str]:
        """Heavy tasks that run in background (optional)."""
        return []

    @property
    def supported_file_types(self) -> list[str]:
        """List of MIME type prefixes supported by this specialist."""
        return ["*"]

    # ── Concrete Infrastructure Logic ────────────────────────────────────────

    @staticmethod
    def _compute_ceiling(task_count: int) -> int:
        """Dynamic iteration ceiling: base task count + 25% buffer."""
        return task_count + max(3, math.ceil(task_count * 0.25))

    @property
    def supports_uploaded_file(self) -> bool:
        """Check if this agent supports the uploaded evidence file type."""
        if "*" in self.supported_file_types:
            return True

        mime_type = getattr(self.evidence_artifact, "mime_type", "") or ""
        file_path = getattr(self.evidence_artifact, "file_path", "") or ""

        return MimeRegistry.is_supported(
            agent_name=self.agent_name,
            mime_type=mime_type,
            file_path=file_path
        )
