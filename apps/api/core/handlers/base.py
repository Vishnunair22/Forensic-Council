"""
Base Tool Handler
=================

Defines the interface for domain-specific tool dispatchers.
Decentralizes the tool_handlers.py monolith.
"""

from abc import ABC, abstractmethod

from core.inference_client import InferenceClient, get_inference_client
from core.structured_logging import get_logger

logger = get_logger(__name__)


class BaseToolHandler(ABC):
    """
    Abstract base class for domain-specific tool handlers.

    Each subclass is responsible for a specific forensic domain
    (e.g., Image, Audio, Metadata).
    """

    def __init__(self, agent):
        self.agent = agent
        self._inference_client: InferenceClient | None = None

    async def get_inference(self) -> InferenceClient:
        """Lazy access to centralized inference client."""
        if self._inference_client is None:
            self._inference_client = await get_inference_client()
        return self._inference_client

    async def inject_task(self, description: str, priority: int = 10) -> None:
        """
        Dynamically inject a new task into the investigation pipeline.
        Used for reactive task decomposition based on intermediate findings.
        """
        try:
            from core.working_memory import TaskStatus

            await self.agent.working_memory.create_task(
                session_id=self.agent.session_id,
                agent_id=self.agent.agent_id,
                description=description,
                status=TaskStatus.PENDING,
                priority=priority,
            )
            logger.info("Dynamic task injected", agent_id=self.agent.agent_id, task=description)
        except Exception as e:
            logger.error(
                "Failed to inject dynamic task", agent_id=self.agent.agent_id, error=str(e)
            )

    @abstractmethod
    def register_tools(self, registry) -> None:
        """Register domain-specific tools into the agent's ToolRegistry."""
        pass
