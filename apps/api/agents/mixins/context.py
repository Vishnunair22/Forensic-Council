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
        self._agent_synthesis: dict[str, Any] | None = None
        self._gemini_signal_callback: Any = None
        self._episodic_context: str = ""
        self._investigation_completed: bool = False

    async def _retrieve_episodic_context(self) -> str:
        """Retrieve relevant context from episodic memory for injection."""
        try:
            agent_signature_map = {
                "Agent1": [ForensicSignatureType.MANIPULATION_SIGNATURE],
                "Agent2": [ForensicSignatureType.AUDIO_ARTIFACT],
                "Agent3": [ForensicSignatureType.OBJECT_DETECTION],
                "Agent4": [ForensicSignatureType.VIDEO_ARTIFACT],
                "Agent5": [
                    ForensicSignatureType.DEVICE_FINGERPRINT,
                    ForensicSignatureType.METADATA_PATTERN,
                ],
            }
            sig_types = agent_signature_map.get(self.agent_id, [])
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
            logger.warning(
                "Episodic context retrieval failed — proceeding without historical calibration",
                agent_id=self.agent_id,
                error=str(e),
            )
            return ""

    async def _record_tool_result(self, tool_name: str, result: dict) -> None:
        """Store a tool result. If the result contains an error, route to the error counter."""
        self._tool_context[tool_name] = result
        if result.get("error") and not result.get("available", True):
            # Result is a structured failure — count as error, not success
            if hasattr(self, "_tool_error_count"):
                self._tool_error_count += 1
        else:
            self._tool_success_count += 1

        # Prune context to prevent memory bloat
        self._prune_tool_context()

    def _prune_tool_context(self, max_entries: int = 50, max_payload_bytes: int = 100_000) -> None:
        """Prune _tool_context to prevent memory bloat."""
        # Keep only last N entries by insertion order
        if len(self._tool_context) > max_entries:
            keys = list(self._tool_context.keys())
            for key in keys[:-max_entries]:
                del self._tool_context[key]

        # Truncate large string/list payloads
        for _key, val in self._tool_context.items():
            if isinstance(val, dict):
                for k in list(val.keys()):
                    # Check for large string or list payloads that don't need full persistence
                    if isinstance(val[k], (str, list)) and len(str(val[k])) > max_payload_bytes:
                        if isinstance(val[k], str):
                            val[k] = val[k][:max_payload_bytes] + "...[truncated]"
                        else:
                            # For lists, preserve the structure but limit elements
                            val[k] = val[k][:100] + [f"...[truncated {len(val[k]) - 100} items]"]

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

    async def store_episodic_finding(self, entry: EpisodicEntry, embedding: list[float]) -> None:
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
