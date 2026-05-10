"""
Embedding-Based Task Router
============================

Replaces the fragile YAML keyword-scoring task-to-tool matcher with a
semantic embedding similarity approach.

Problem with the old approach (react_loop.py `_match_tool_to_task`):
  - YAML config requires manual maintenance for every new tool
  - Keyword scoring fails on paraphrased task descriptions
  - Produces silent INCOMPLETE findings for unmatched tasks (TD-04)

New approach:
  - Embed both task descriptions and tool descriptions with TF-IDF hash embedding
  - Match via cosine similarity (identical to the RAG layer approach)
  - Falls back to YAML overrides for deterministic critical mappings
  - Optional upgrade path: swap _embed() with sentence-transformers for higher accuracy

Usage (in ReActLoopEngine):
    from core.task_router import TaskRouter
    router = TaskRouter()
    best_tool = router.route(task_description, tools)
"""

from __future__ import annotations

import hashlib
import math
from dataclasses import dataclass
from typing import Any

from core.structured_logging import get_logger
from core.task_tool_config import get_task_tool_overrides

logger = get_logger(__name__)


# ---------------------------------------------------------------------------
# Embedding (same as rag_forensic_knowledge.py — shared logic, no import cycle)
# ---------------------------------------------------------------------------

def _ngram_embed(text: str, dims: int = 256) -> list[float]:
    """Character n-gram hash embedding (CPU-only, no ML dependency)."""
    text_lower = text.lower()
    vec = [0.0] * dims

    for n in (2, 3, 4):
        for i in range(len(text_lower) - n + 1):
            gram = text_lower[i : i + n]
            h = int(hashlib.md5(gram.encode(), usedforsecurity=False).hexdigest(), 16)
            idx = h % dims
            vec[idx] += 1.0

    magnitude = math.sqrt(sum(x * x for x in vec))
    if magnitude > 0:
        vec = [x / magnitude for x in vec]
    return vec


def _cosine_sim(a: list[float], b: list[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b, strict=False))
    mag_a = math.sqrt(sum(x * x for x in a))
    mag_b = math.sqrt(sum(x * x for x in b))
    if mag_a == 0 or mag_b == 0:
        return 0.0
    return dot / (mag_a * mag_b)


@dataclass
class ToolEntry:
    """A cached tool representation for routing."""
    name: str
    description: str
    embedding: list[float]


class TaskRouter:
    """
    Semantic task-to-tool router.

    Builds tool embeddings lazily on first use, then matches incoming task
    descriptions via cosine similarity against the tool index.

    Ordering of routing strategies (highest priority first):
    1. YAML explicit overrides (deterministic, admin-controlled)
    2. Semantic embedding similarity (dynamic, handles paraphrasing)
    3. Legacy keyword scoring (fallback for very short tasks)
    """

    # Minimum cosine similarity to accept an embedding match
    EMBEDDING_THRESHOLD = 0.22

    # Minimum keyword score for legacy fallback
    KEYWORD_THRESHOLD = 2

    # Skip tasks that are coordination/synthesis-only (no tool needed)
    SKIP_TASK_PATTERNS = frozenset({
        "self-reflection pass",
        "submit calibrated findings to arbiter",
        "submit findings",
        "calibrated findings",
        "synthesize cross-field consistency",
        "synthesize",
        "classify each anomaly",
        "issue collaborative call",
        "for each suspicious anomaly",
        "for each flagged anomaly",
        "for frames containing",
    })

    def __init__(self) -> None:
        self._tool_index: list[ToolEntry] = []
        self._yaml_overrides: dict[str, str] = {}
        self._built = False

    def _build(self, tools: list[Any]) -> None:
        """Build the tool embedding index from the registered tools."""
        if self._built and len(self._tool_index) == len(tools):
            return  # Already built for this tool set

        self._yaml_overrides = get_task_tool_overrides()
        self._tool_index = []

        for tool in tools:
            name = getattr(tool, "name", str(tool))
            description = getattr(tool, "description", "") or ""
            # Embed combined name + description for richer matching
            combined = f"{name.replace('_', ' ')} {description}"
            embedding = _ngram_embed(combined)
            self._tool_index.append(ToolEntry(
                name=name,
                description=description,
                embedding=embedding,
            ))

        self._built = True
        logger.debug("TaskRouter index built", tool_count=len(self._tool_index))

    def should_skip(self, task_description: str) -> bool:
        """Return True if the task requires no tool (coordination/synthesis only)."""
        task_lower = (task_description or "").lower()
        return any(pattern in task_lower for pattern in self.SKIP_TASK_PATTERNS)

    def route(
        self,
        task_description: str,
        tools: list[Any],
        agent_id: str = "",
    ) -> Any | None:
        """
        Route a task description to the best available tool.

        Returns the matched tool object, or None if no suitable tool found.
        """
        self._build(tools)

        # Guard: warn on empty or unconfigured tool list
        if not tools:
            logger.warning("TaskRouter.route called with empty tools list", agent_id=agent_id)
            return None

        # Compute a deterministic hash of the tool set to detect unexpected changes
        tool_names = sorted(getattr(t, "name", "") for t in tools)
        tool_set_hash = hashlib.md5("|".join(tool_names).encode(), usedforsecurity=False).hexdigest()[:8]
        if not hasattr(self, "_last_tool_set_hash") or self._last_tool_set_hash != tool_set_hash:
            self._last_tool_set_hash = tool_set_hash
            logger.info(
                "TaskRouter: tool set changed",
                tool_count=len(tools),
                tool_set_hash=tool_set_hash,
                agent_id=agent_id,
            )

        task_lower = (task_description or "").lower().strip()

        # --- Strategy 1: YAML explicit overrides ---
        for keyword, tool_name in self._yaml_overrides.items():
            if keyword in task_lower:
                matched = next((t for t in tools if getattr(t, "name", "") == tool_name), None)
                if matched:
                    logger.debug(
                        "TaskRouter: YAML override match",
                        task=task_description[:60],
                        tool=tool_name,
                        agent_id=agent_id,
                    )
                    return matched

        # --- Strategy 2: Embedding similarity ---
        task_embedding = _ngram_embed(task_lower)
        best_score = 0.0
        best_tool_entry: ToolEntry | None = None

        for entry in self._tool_index:
            score = _cosine_sim(task_embedding, entry.embedding)
            if score > best_score:
                best_score = score
                best_tool_entry = entry

        if best_score >= self.EMBEDDING_THRESHOLD and best_tool_entry is not None:
            matched = next(
                (t for t in tools if getattr(t, "name", "") == best_tool_entry.name),
                None,
            )
            if matched:
                logger.debug(
                    "TaskRouter: embedding match",
                    task=task_description[:60],
                    tool=best_tool_entry.name,
                    score=round(best_score, 3),
                    agent_id=agent_id,
                )
                return matched

        # --- Strategy 3: Legacy keyword scoring (safety net) ---
        best_tool = None
        best_keyword_score = 0

        for tool in tools:
            score = 0
            name = getattr(tool, "name", "")
            desc = getattr(tool, "description", "") or ""
            name_parts = name.lower().replace("_", " ").split()
            desc_parts = desc.lower().split()

            for part in name_parts:
                if len(part) > 2 and part in task_lower:
                    score += 3
            for part in desc_parts:
                if len(part) > 3 and part in task_lower:
                    score += 1

            if score > best_keyword_score:
                best_keyword_score = score
                best_tool = tool

        if best_keyword_score >= self.KEYWORD_THRESHOLD:
            logger.debug(
                "TaskRouter: keyword fallback match",
                task=task_description[:60],
                tool=getattr(best_tool, "name", "?"),
                keyword_score=best_keyword_score,
                agent_id=agent_id,
            )
            return best_tool

        logger.warning(
            "TaskRouter: no match found",
            task=task_description[:80],
            best_embedding_score=round(best_score, 3),
            best_keyword_score=best_keyword_score,
            agent_id=agent_id,
        )
        return None

    def invalidate(self) -> None:
        """Force rebuild on next route call (e.g., after tool registration changes)."""
        self._built = False
        self._tool_index = []


# Module-level singleton — shared across all ReActLoopEngine instances
_router_instance: TaskRouter | None = None


def get_task_router() -> TaskRouter:
    """Get or create the module-level TaskRouter singleton."""
    global _router_instance
    if _router_instance is None:
        _router_instance = TaskRouter()
    return _router_instance
