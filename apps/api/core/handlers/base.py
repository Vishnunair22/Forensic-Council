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

    @abstractmethod
    def register_tools(self, registry) -> None:
        """Register domain-specific tools into the agent's ToolRegistry."""
        pass
