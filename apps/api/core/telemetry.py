"""
Forensic Council Telemetry
==========================

Tracks API usage, tool execution metrics, and finding quality statistics.
Provides lightweight in-memory counters for operational monitoring.
No external dependencies required.
"""

from __future__ import annotations

import threading
import time
from collections import defaultdict
from dataclasses import dataclass
from typing import Any


@dataclass
class ToolExecutionRecord:
    tool_name: str
    agent_id: str
    success: bool
    duration_ms: float
    timestamp: float
    error: str | None = None
    finding_verdict: str | None = None


@dataclass
class ProviderUsageRecord:
    provider: str
    model: str
    tokens_in: int = 0
    tokens_out: int = 0
    duration_ms: float = 0.0
    success: bool = True
    error: str | None = None
    timestamp: float = 0.0


@dataclass
class FindingQualityRecord:
    agent_id: str
    tool_count: int
    positive_findings: int
    negative_findings: int
    inconclusive_findings: int
    error_findings: int
    total_findings: int
    avg_confidence: float
    timestamp: float


class TelemetryCollector:
    """
    Thread-safe in-memory telemetry collector.

    Stores execution records in deques with bounded size to prevent
    unbounded memory growth.
    """

    MAX_TOOL_RECORDS = 10_000
    MAX_PROVIDER_RECORDS = 5_000
    MAX_QUALITY_RECORDS = 1_000

    def __init__(self):
        self._lock = threading.Lock()
        self._tool_records: list[ToolExecutionRecord] = []
        self._provider_records: list[ProviderUsageRecord] = []
        self._quality_records: list[FindingQualityRecord] = []
        self._tool_counts: dict[str, int] = defaultdict(int)
        self._tool_errors: dict[str, int] = defaultdict(int)
        self._provider_counts: dict[str, int] = defaultdict(int)
        self._provider_errors: dict[str, int] = defaultdict(int)
        self._session_count = 0
        self._start_time = time.time()

    # ── Recording ────────────────────────────────────────────────────────

    def record_tool_execution(
        self,
        tool_name: str,
        agent_id: str,
        success: bool,
        duration_ms: float,
        error: str | None = None,
        finding_verdict: str | None = None,
    ) -> None:
        rec = ToolExecutionRecord(
            tool_name=tool_name,
            agent_id=agent_id,
            success=success,
            duration_ms=duration_ms,
            timestamp=time.time(),
            error=error,
            finding_verdict=finding_verdict,
        )
        with self._lock:
            self._tool_records.append(rec)
            if len(self._tool_records) > self.MAX_TOOL_RECORDS:
                self._tool_records.pop(0)
            self._tool_counts[tool_name] += 1
            if not success:
                self._tool_errors[tool_name] += 1

    def record_provider_usage(
        self,
        provider: str,
        model: str,
        tokens_in: int = 0,
        tokens_out: int = 0,
        duration_ms: float = 0.0,
        success: bool = True,
        error: str | None = None,
    ) -> None:
        rec = ProviderUsageRecord(
            provider=provider,
            model=model,
            tokens_in=tokens_in,
            tokens_out=tokens_out,
            duration_ms=duration_ms,
            success=success,
            error=error,
            timestamp=time.time(),
        )
        with self._lock:
            self._provider_records.append(rec)
            if len(self._provider_records) > self.MAX_PROVIDER_RECORDS:
                self._provider_records.pop(0)
            self._provider_counts[provider] += 1
            if not success:
                self._provider_errors[provider] += 1

    def record_finding_quality(
        self,
        agent_id: str,
        tool_count: int,
        positive_findings: int,
        negative_findings: int,
        inconclusive_findings: int,
        error_findings: int,
        total_findings: int,
        avg_confidence: float,
    ) -> None:
        rec = FindingQualityRecord(
            agent_id=agent_id,
            tool_count=tool_count,
            positive_findings=positive_findings,
            negative_findings=negative_findings,
            inconclusive_findings=inconclusive_findings,
            error_findings=error_findings,
            total_findings=total_findings,
            avg_confidence=avg_confidence,
            timestamp=time.time(),
        )
        with self._lock:
            self._quality_records.append(rec)
            if len(self._quality_records) > self.MAX_QUALITY_RECORDS:
                self._quality_records.pop(0)

    def increment_session_count(self) -> int:
        with self._lock:
            self._session_count += 1
            return self._session_count

    # ── Query ────────────────────────────────────────────────────────────

    def get_tool_stats(self) -> dict[str, Any]:
        with self._lock:
            error_rates = {}
            for tool, total in self._tool_counts.items():
                errs = self._tool_errors.get(tool, 0)
                error_rates[tool] = round(errs / total, 4) if total > 0 else 0.0

            return {
                "total_tool_calls": sum(self._tool_counts.values()),
                "tool_call_counts": dict(self._tool_counts),
                "tool_error_counts": dict(self._tool_errors),
                "tool_error_rates": error_rates,
                "unique_tools": len(self._tool_counts),
            }

    def get_provider_stats(self) -> dict[str, Any]:
        with self._lock:
            error_rates = {}
            for prov, total in self._provider_counts.items():
                errs = self._provider_errors.get(prov, 0)
                error_rates[prov] = round(errs / total, 4) if total > 0 else 0.0

            return {
                "total_provider_calls": sum(self._provider_counts.values()),
                "provider_call_counts": dict(self._provider_counts),
                "provider_error_counts": dict(self._provider_errors),
                "provider_error_rates": error_rates,
            }

    def get_finding_quality_summary(self) -> dict[str, Any]:
        with self._lock:
            if not self._quality_records:
                return {}
            total = len(self._quality_records)
            avg_positive = sum(r.positive_findings for r in self._quality_records) / total
            avg_negative = sum(r.negative_findings for r in self._quality_records) / total
            avg_inconclusive = sum(r.inconclusive_findings for r in self._quality_records) / total
            avg_error = sum(r.error_findings for r in self._quality_records) / total
            avg_confidence = sum(r.avg_confidence for r in self._quality_records) / total
            return {
                "total_quality_records": total,
                "avg_positive_findings": round(avg_positive, 2),
                "avg_negative_findings": round(avg_negative, 2),
                "avg_inconclusive_findings": round(avg_inconclusive, 2),
                "avg_error_findings": round(avg_error, 2),
                "avg_confidence": round(avg_confidence, 4),
                "avg_tools_per_agent": sum(r.tool_count for r in self._quality_records) / total,
            }

    def get_session_count(self) -> int:
        with self._lock:
            return self._session_count

    def get_uptime_seconds(self) -> float:
        return time.time() - self._start_time

    def get_summary(self) -> dict[str, Any]:
        return {
            "uptime_seconds": round(self.get_uptime_seconds(), 1),
            "sessions": self.get_session_count(),
            "tools": self.get_tool_stats(),
            "providers": self.get_provider_stats(),
            "finding_quality": self.get_finding_quality_summary(),
        }

    def reset(self) -> None:
        with self._lock:
            self._tool_records.clear()
            self._provider_records.clear()
            self._quality_records.clear()
            self._tool_counts.clear()
            self._tool_errors.clear()
            self._provider_counts.clear()
            self._provider_errors.clear()
            self._session_count = 0
            self._start_time = time.time()


# Global singleton
_telemetry_instance: TelemetryCollector | None = None
_telemetry_lock = threading.Lock()


def get_telemetry() -> TelemetryCollector:
    global _telemetry_instance
    if _telemetry_instance is None:
        with _telemetry_lock:
            if _telemetry_instance is None:
                _telemetry_instance = TelemetryCollector()
    return _telemetry_instance
