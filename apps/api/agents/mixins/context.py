"""
Context Mixin for Forensic Agents.
Handles tool results, episodic state, and inter-agent communication.
"""

from __future__ import annotations

import uuid
from typing import Any

from core.config import Settings
from core.episodic_memory import EpisodicEntry, EpisodicMemory, ForensicSignatureType
from core.evidence import EvidenceArtifact
from core.persistence.evidence_store import EvidenceStore
from core.react_loop import AgentFinding
from core.structured_logging import get_logger

logger = get_logger(__name__)


class AgentContextMixin:
    """
    Mixin handling agent state, tool context, and episodic retrieval.
    """

    agent_id: str
    session_id: uuid.UUID
    evidence_artifact: EvidenceArtifact
    config: Settings
    episodic_memory: EpisodicMemory
    custody_logger: Any
    evidence_store: EvidenceStore
    inter_agent_bus: Any

    def __init_subclass__(cls, **kwargs):
        super().__init_subclass__(**kwargs)

    def _init_context(self) -> None:
        """Initialize context attributes."""
        self._tool_registry: Any = None
        self._findings: list[AgentFinding] = []
        self._react_chain: list = []
        self._tool_context: dict[str, Any] = {}
        self._tool_success_count: int = 0
        self._tool_error_count: int = 0
        self._agent_confidence: float | None = None
        self._agent_error_rate: float | None = None
        self._gemini_signal_callback: Any = None
        self._episodic_context: str = ""

    async def _retrieve_episodic_context(self) -> str:
        """Retrieve relevant context from episodic memory for injection."""
        try:
            _AGENT_SIGNATURE_MAP = {
                "Agent1": [ForensicSignatureType.MANIPULATION_SIGNATURE],
                "Agent2": [ForensicSignatureType.AUDIO_ARTIFACT],
                "Agent3": [ForensicSignatureType.OBJECT_DETECTION],
                "Agent4": [ForensicSignatureType.VIDEO_ARTIFACT],
                "Agent5": [
                    ForensicSignatureType.DEVICE_FINGERPRINT,
                    ForensicSignatureType.METADATA_PATTERN,
                ],
            }
            sig_types = _AGENT_SIGNATURE_MAP.get(self.agent_id, [])
            all_entries: list = []
            for sig_type in sig_types:
                entries = await self.episodic_memory.retrieve_similar_cases(
                    signature_type=sig_type,
                    exclude_session_id=self.session_id,
                    top_k=3,
                )
                all_entries.extend(entries)

            if not all_entries:
                return ""

            lines = ["== RELEVANT PAST INVESTIGATIONS (from episodic memory) =="]
            for i, entry in enumerate(all_entries[:5], 1):
                lines.append(
                    f"  {i}. [{entry.signature_type.value}] {entry.finding_type} "
                    f"(confidence: {entry.confidence:.2f}, case: {entry.case_id}): "
                    f"{entry.summary[:200]}"
                )
            lines.append(
                "These findings are from prior cases. Use them as contextual reference "
                "but do NOT assume the same conclusions apply to the current evidence."
            )
            return "\n".join(lines)
        except Exception as e:
            logger.debug(f"Episodic context retrieval failed: {e}")
            return ""

    async def _record_tool_result(self, tool_name: str, result: dict) -> None:
        """Store a successful tool result in _tool_context."""
        self._tool_context[tool_name] = result
        self._tool_success_count += 1

    async def query_episodic_memory(
        self,
        signature_type: ForensicSignatureType,
        query_embedding: list[float],
        limit: int = 10,
    ) -> list[EpisodicEntry]:
        """Query episodic memory for similar forensic signatures."""
        if self.custody_logger:
            from core.custody_logger import EntryType
            await self.custody_logger.log_entry(
                agent_id=self.agent_id,
                session_id=self.session_id,
                entry_type=EntryType.MEMORY_READ,
                content={
                    "action": "query_episodic_memory",
                    "signature_type": signature_type.value,
                    "limit": limit,
                },
            )

        return await self.episodic_memory.query(
            signature_type=signature_type, query_embedding=query_embedding, top_k=limit
        )

    async def store_episodic_finding(
        self, entry: EpisodicEntry, embedding: list[float]
    ) -> None:
        """Store a finding in episodic memory."""
        if self.custody_logger:
            from core.custody_logger import EntryType
            await self.custody_logger.log_entry(
                agent_id=self.agent_id,
                session_id=self.session_id,
                entry_type=EntryType.MEMORY_WRITE,
                content={
                    "action": "store_episodic_finding",
                    "signature_type": entry.signature_type.value,
                    "session_id": str(entry.session_id),
                },
            )

        await self.episodic_memory.store(entry, embedding)
