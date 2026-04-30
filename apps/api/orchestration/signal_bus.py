"""
Signal Bus
==========

Async cross-agent coordination and early quorum deliberation.
"""

from __future__ import annotations

import asyncio

from core.structured_logging import get_logger

logger = get_logger(__name__)


def _calculate_quorum(agent_count: int) -> int:
    """Return minimum agents needed for quorum: floor(n/2) + 1.

    Ensures more than 50% of agents must agree, preventing tie scenarios.
    n=1: 1 (100%), n=2: 2 (100%), n=3: 2 (66.7%), n=4: 3 (75%), n=5: 3 (60%).
    """
    return max(1, agent_count // 2 + 1)


class SignalBus:
    """Async signal bus for cross-agent coordination and early deliberation."""

    def __init__(self, agent_ids: list[str]):
        self.events = {aid: asyncio.Event() for aid in agent_ids}
        self.findings = {aid: [] for aid in agent_ids}
        self.quorum_event = asyncio.Event()
        self._agent_ids = agent_ids
        # Initial quorum based on all agents; refined once support is checked.
        self._required_quorum = _calculate_quorum(len(agent_ids))
        self._ready_agents: set[str] = set()
        self._quorum_lock = asyncio.Lock()

    def update_applicable_agents(self, applicable_ids: list[str]) -> None:
        """Update quorum threshold based on actually applicable agents."""
        sorted_ids = sorted(applicable_ids)
        self._required_quorum = _calculate_quorum(len(sorted_ids))
        logger.info(
            "Quorum threshold updated",
            applicable_count=len(sorted_ids),
            required_quorum=self._required_quorum,
            agent_ids=sorted_ids,
        )
        asyncio.get_running_loop().create_task(self._async_check_quorum())

    async def signal_ready(self, agent_id: str, initial_findings: list) -> None:
        """Signal that an agent has finished its initial investigation."""
        if agent_id in self.events:
            self.findings[agent_id] = list(initial_findings)
            self.events[agent_id].set()
            self._ready_agents.add(agent_id)
            await self._async_check_quorum()

    async def signal_failure(self, agent_id: str) -> None:
        """Signal that an agent has failed its initial investigation."""
        if agent_id in self.events:
            self.events[agent_id].set()
            self._ready_agents.add(agent_id)
            await self._async_check_quorum()

    async def _async_check_quorum(self) -> None:
        """Thread-safe quorum check and event setting."""
        async with self._quorum_lock:
            if len(self._ready_agents) >= self._required_quorum:
                self.quorum_event.set()

    async def wait_for_quorum(self, timeout: float = 60.0) -> bool:
        """Wait until a quorum of agents is ready."""
        try:
            await asyncio.wait_for(self.quorum_event.wait(), timeout=timeout)
            return True
        except TimeoutError:
            return False
