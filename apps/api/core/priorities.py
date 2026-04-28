"""
Task priority constants for working memory injection.
Ensures consistent priority ordering across all agents.
"""

from enum import IntEnum


class TaskPriority(IntEnum):
    """Priority levels for reactive task injection."""

    BACKGROUND = 5  # Low-priority background analysis
    NORMAL = 10  # Standard agent tasks
    ELEVATED = 15  # Reactive triggers based on findings
    URGENT = 20  # High-urgency signals (e.g., face-swap detected)
    CRITICAL = 30  # Immediate intervention needed
