"""
ForensicAgent Base Class — Modular Refactor.

Every specialist agent (1-5) extends this base class.
Provides common investigation workflow, self-reflection, and memory integration.
Now decomposed into mixins for better maintainability.
"""

from __future__ import annotations

import asyncio
import json
import math
import uuid
from abc import ABC, abstractmethod
from typing import Any

from agents.mixins import (
    AgentContextMixin,
    AgentInvestigationMixin,
    AgentMemoryMixin,
    AgentReflectionMixin,
    NeuralSynthesisMixin,
)
from core.config import Settings
from core.custody_logger import CustodyLogger
from core.episodic_memory import EpisodicMemory
from core.evidence import EvidenceArtifact
from core.mime_registry import MimeRegistry
from core.persistence.evidence_store import EvidenceStore
from core.react_loop import AgentFinding
from core.structured_logging import get_logger
from core.tool_registry import ToolRegistry
from core.working_memory import WorkingMemory

logger = get_logger(__name__)


class ForensicAgent(
    AgentContextMixin,
    AgentMemoryMixin,
    AgentInvestigationMixin,
    AgentReflectionMixin,
    NeuralSynthesisMixin,
    ABC,
):
    """
    Modular base class for all forensic specialist agents.

    Inherits from specialized mixins to handle distinct aspects of the
    agent's lifecycle and mandated workflow.

    MRO contract:
    - AgentContextMixin       supplies _tool_context, _tool_registry, _init_context
    - AgentMemoryMixin        depends on context; consumes _record_tool_result
    - AgentInvestigationMixin depends on memory; defines run_investigation / run_deep_investigation
    - AgentReflectionMixin   depends on investigation; uses self._react_chain
    - NeuralSynthesisMixin  depends on context; defines _gemini_deep_forensic_handler
    Mixins must NOT override each other's methods. Add new behaviour to the most specific mixin.
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
        heavy_tool_semaphore: asyncio.Semaphore | None = None,
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
        self.heavy_tool_semaphore = heavy_tool_semaphore

        # Initialize mixin-provided state containers
        if not hasattr(self, "_init_context"):
            raise AttributeError("AgentContextMixin missing from MRO - _init_context not found")
        self._init_context()
        super().__init__()

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

    async def on_tool_result(self, finding: AgentFinding) -> None:
        """
        Lifecycle hook called after each tool result is processed.
        Override this to implement reactive logic (e.g. dynamic task injection).
        """
        pass

    # ── Concrete Infrastructure Logic ────────────────────────────────────────

    @staticmethod
    def _compute_ceiling(initial_n: int, deep_n: int = 0) -> int:
        """Dynamic iteration ceiling: base task count + 30% buffer, minimum 3."""
        return initial_n + deep_n + max(3, math.ceil((initial_n + deep_n) * 0.30))

    @property
    def supports_uploaded_file(self) -> bool:
        """Check if this agent supports the uploaded evidence file type."""
        if "*" in self.supported_file_types:
            return True

        mime_type = getattr(self.evidence_artifact, "mime_type", "") or ""
        file_path = getattr(self.evidence_artifact, "file_path", "") or ""

        return MimeRegistry.is_supported(
            agent_name=self.agent_name, mime_type=mime_type, file_path=file_path
        )

    async def generate_synthesis(self, findings: list) -> str:
        """Generate executive synthesis with robust no-LLM fallback."""
        from core.llm_client import LLMClient
        llm_client = LLMClient(config=self.config)
        llm_available = llm_client.is_available

        if not llm_available:
            logger.info(f"{self.agent_id}: LLM unavailable, using template synthesis")
            return self._generate_template_synthesis_from_findings(findings)

        try:
            findings_json = json.dumps([
                f.model_dump() if hasattr(f, 'model_dump') else f
                for f in findings
            ], default=str)
            synthesis = await llm_client.generate_synthesis(
                system_prompt=f"Executive synthesis for {self.agent_id} forensic findings.",
                user_content=findings_json,
                max_tokens=1024,
                json_mode=False
            )
            if synthesis and len(synthesis.strip()) > 20:
                return synthesis
            logger.warning(f"{self.agent_id}: LLM returned empty synthesis, using template")
            return self._generate_template_synthesis_from_findings(findings)
        except Exception as e:
            logger.warning(f"{self.agent_id}: Synthesis generation failed: {e}")
            return self._generate_template_synthesis_from_findings(findings)

    def _generate_template_synthesis_from_findings(self, findings: list) -> str:
        """Deterministic synthesis from tool findings only."""
        if not findings:
            return f"{self.agent_id}: No forensic anomalies detected in this evidence."
        tool_names = set()
        positive_findings = []
        for f in findings:
            meta = f.metadata if hasattr(f, 'metadata') else f.get('metadata', {})
            tool_name = meta.get('tool_name')
            if tool_name:
                tool_names.add(tool_name)
            verdict = (f.evidence_verdict if hasattr(f, 'evidence_verdict')
                      else f.get('evidence_verdict', ''))
            if verdict == 'POSITIVE':
                finding_type = (f.finding_type if hasattr(f, 'finding_type')
                              else f.get('finding_type', tool_name))
                positive_findings.append(finding_type)
        parts = []
        parts.append(f"Analyzed using {len(tool_names)} specialized tools.")
        if positive_findings:
            parts.append(f"Detected: {', '.join(positive_findings[:3])}.")
        else:
            parts.append("No significant anomalies detected.")
        return " ".join(parts)
