"""
Memory Mixin for Forensic Agents.
Handles working memory initialization, task state management, and custody logging.
"""

from __future__ import annotations

import uuid

from core.custody_logger import CustodyLogger
from core.structured_logging import get_logger
from core.working_memory import TaskStatus, WorkingMemory

logger = get_logger(__name__)


class AgentMemoryMixin:
    """
    Mixin handling working memory and chain-of-custody logging.
    """

    # Attributes provided by the base class or other mixins
    agent_id: str
    session_id: uuid.UUID
    working_memory: WorkingMemory
    custody_logger: CustodyLogger
    task_decomposition: list[str]
    iteration_ceiling: int

    async def _initialize_working_memory(self) -> None:
        """Initialize working memory with task decomposition."""
        await self.working_memory.initialize(
            session_id=self.session_id,
            agent_id=self.agent_id,
            tasks=self.task_decomposition,
            iteration_ceiling=self.iteration_ceiling,
        )

        logger.debug(
            "Working memory initialized",
            agent_id=self.agent_id,
            task_count=len(self.task_decomposition),
        )

    async def update_sub_task(self, sub_info: str) -> None:
        """
        Update the progress text for the CURRENT active task.
        Allows handlers to push fine-grained progress (e.g. 'Frame 45/100').
        """
        try:
            # ReActLoopEngine stores the current task_id in working memory state
            state = await self.working_memory.get_state(self.session_id, self.agent_id)
            # Find the first 'IN_PROGRESS' task
            inprogress = [t for t in state.tasks if t.status == TaskStatus.IN_PROGRESS]
            if inprogress:
                task = inprogress[0]
                await self.working_memory.update_task(
                    session_id=self.session_id,
                    agent_id=self.agent_id,
                    task_id=task.task_id,
                    status=TaskStatus.IN_PROGRESS,
                    sub_task_info=sub_info,
                )

            # Also update deep namespace if active
            deep_ns = getattr(self, "_deep_wm_namespace", None)
            if deep_ns:
                state_deep = await self.working_memory.get_state(self.session_id, deep_ns)
                inprogress_deep = [
                    t for t in state_deep.tasks if t.status == TaskStatus.IN_PROGRESS
                ]
                if inprogress_deep:
                    task_d = inprogress_deep[0]
                    await self.working_memory.update_task(
                        session_id=self.session_id,
                        agent_id=deep_ns,
                        task_id=task_d.task_id,
                        status=TaskStatus.IN_PROGRESS,
                        sub_task_info=sub_info,
                    )
        except Exception as e:
            logger.debug(f"Sub-task update failed (non-fatal): {e}")

    async def _record_tool_error(self, tool_name: str, error_msg: str) -> None:
        """
        Increment error counter and write last_tool_error to working memory.
        """
        # Note: _tool_error_count is handled by AgentContextMixin
        if hasattr(self, "_tool_error_count"):
            self._tool_error_count += 1

        display_name = tool_name.replace("_", " ").title()
        error_text = f"{display_name} failed — continuing…"
        try:
            await self.working_memory.update_state(
                session_id=self.session_id,
                agent_id=self.agent_id,
                updates={"last_tool_error": error_text},
            )
            # Also write to deep namespace so heartbeat surfaces errors during deep pass
            deep_ns = getattr(self, "_deep_wm_namespace", None)
            if deep_ns:
                await self.working_memory.update_state(
                    session_id=self.session_id,
                    agent_id=deep_ns,
                    updates={"last_tool_error": error_text},
                )
        except Exception as e:
            logger.warning(f"Could not update working memory bookkeeping: {e}")

    def _signal_completion(self, skipped: bool = False) -> None:
        """Signal agent completion to the inter-agent bus."""
        self._investigation_completed = True
        if hasattr(self, "inter_agent_bus") and self.inter_agent_bus:  # type: ignore[attr-defined]
            base_id = self.agent_id.replace("_deep", "")
            event_name = f"{base_id.lower()}_complete"
            self.inter_agent_bus.signal_event(
                self.session_id,
                event_name,
                {
                    "skipped": skipped,
                    "agent_name": getattr(self, "agent_name", ""),
                    "phase": "deep" if "_deep" in self.agent_id else "initial",
                },
            )
            logger.debug(f"Completion signal sent: {event_name}", agent_id=self.agent_id)
