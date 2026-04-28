from __future__ import annotations
import asyncio
from uuid import UUID

_LIVE_PIPELINES: dict[str, "ForensicCouncilPipeline"] = {}


def register_pipeline(session_id: UUID, pipeline: "ForensicCouncilPipeline") -> None:
    _LIVE_PIPELINES[str(session_id)] = pipeline


def unregister_pipeline(session_id: UUID) -> None:
    _LIVE_PIPELINES.pop(str(session_id), None)


def notify_decision(session_id: UUID, deep_analysis: bool) -> bool:
    p = _LIVE_PIPELINES.get(str(session_id))
    if p is None:
        return False
    p.run_deep_analysis_flag = bool(deep_analysis)
    p.deep_analysis_decision_event.set()
    return True


def get_pipeline(session_id: str | UUID) -> "ForensicCouncilPipeline" | None:
    return _LIVE_PIPELINES.get(str(session_id))