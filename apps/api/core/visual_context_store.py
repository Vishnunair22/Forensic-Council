import asyncio
import json
import time
from typing import Any
from uuid import UUID

from core.persistence.redis_client import get_redis_client
from core.structured_logging import get_logger
from core.visual_context_models import VisualContext

logger = get_logger(__name__)

async def get_visual_context(
    session_id: str,
    sha256: str | None = None,
    working_memory: Any = None,
    inter_agent_bus: Any = None,
) -> VisualContext | None:
    """
    Retrieve the visual context for a session or SHA256 hash.
    Checks three layers of storage:
      1. In-memory inter-agent bus
      2. Working memory state
      3. Redis persistence (by session_id, then by sha256)
    """
    # Layer 1: Check InterAgentBus
    if inter_agent_bus:
        try:
            data = inter_agent_bus.get_visual_profile(session_id)
            if data:
                return VisualContext.model_validate(data)
        except Exception as e:
            logger.debug("Failed retrieving visual context from inter-agent bus", error=str(e))

    # Layer 2: Check Working Memory
    if working_memory:
        try:
            state = await working_memory.get_state(UUID(session_id), "Agent1")
            data = None
            if hasattr(state, "model_extra") and state.model_extra:
                data = state.model_extra.get("shared_visual_context")
            if data:
                return VisualContext.model_validate(data)
        except Exception as e:
            logger.debug("Failed retrieving visual context from working memory", error=str(e))

    # Layer 3: Check Redis
    try:
        redis = await get_redis_client()
        raw_data = await redis.get(f"visual_context:{session_id}")
        if raw_data:
            data = json.loads(raw_data)
            return VisualContext.model_validate(data)

        if sha256:
            prompt_version = 1
            raw_data = await redis.get(f"visual_context_by_hash:{sha256}:{prompt_version}")
            if raw_data:
                data = json.loads(raw_data)
                return VisualContext.model_validate(data)
    except Exception as e:
        logger.debug("Failed retrieving visual context from Redis", error=str(e))

    return None

async def save_visual_context(
    session_id: str,
    sha256: str,
    context: VisualContext,
    working_memory: Any = None,
    inter_agent_bus: Any = None,
) -> None:
    """
    Save the visual context across all three storage layers:
      1. In-memory inter-agent bus
      2. Working memory state
      3. Redis persistence (by session_id and by sha256)
    """
    # Layer 1: Save to InterAgentBus
    if inter_agent_bus:
        try:
            inter_agent_bus.set_visual_profile(session_id, context.model_dump())
        except Exception as e:
            logger.warning("Failed saving visual context to inter-agent bus", error=str(e))

    # Layer 2: Save to Working Memory
    if working_memory:
        try:
            await working_memory.update_state(
                session_id=UUID(session_id),
                agent_id="Agent1",
                updates={"shared_visual_context": context.model_dump()}
            )
        except Exception as e:
            logger.warning("Failed saving visual context to working memory", error=str(e))

    # Layer 3: Save to Redis
    try:
        redis = await get_redis_client()
        context_json = context.model_dump_json()
        await redis.set(f"visual_context:{session_id}", context_json, ex=14400)  # 4 hour TTL
        if sha256:
            prompt_version = 1
            await redis.set(f"visual_context_by_hash:{sha256}:{prompt_version}", context_json, ex=86400)  # 24 hour TTL
    except Exception as e:
        logger.warning("Failed saving visual context to Redis", error=str(e))

async def wait_for_visual_context(
    session_id: str,
    sha256: str | None = None,
    working_memory: Any = None,
    inter_agent_bus: Any = None,
    timeout: float = 30.0,
) -> VisualContext | None:
    """
    Wait (poll) for visual context to be created/stored.
    """
    t0 = time.monotonic()
    while time.monotonic() - t0 < timeout:
        context = await get_visual_context(
            session_id=session_id,
            sha256=sha256,
            working_memory=working_memory,
            inter_agent_bus=inter_agent_bus
        )
        if context:
            return context
        await asyncio.sleep(1.0)
    return None
