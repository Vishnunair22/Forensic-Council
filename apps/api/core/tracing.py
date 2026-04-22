"""
Forensic Tracing Module
=======================

Provides hierarchical tracing for forensic pipeline auditing.
Traces are persisted to PostgreSQL to ensure a court-defensible audit log
of all agent operations, tool calls, and deliberations.

This is distinct from OpenTelemetry (observability.py) which is used for
infrastructure monitoring. Pipeline tracing is part of the forensic record.
"""

import json
from datetime import UTC, datetime
from typing import Any
from uuid import UUID, uuid4

from core.persistence.postgres_client import get_postgres_client
from core.structured_logging import get_logger

logger = get_logger(__name__)


class PipelineTrace:
    """Represents a single operation in the forensic pipeline."""

    def __init__(
        self,
        session_id: UUID | str,
        agent_id: str,
        operation: str,
        parent_id: UUID | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        self.trace_id = uuid4()
        self.session_id = UUID(str(session_id))
        self.agent_id = agent_id
        self.operation = operation
        self.parent_id = parent_id
        self.metadata = metadata or {}
        self.start_time = datetime.now(UTC)
        self.end_time: datetime | None = None
        self.status = "STARTED"

    async def start(self) -> None:
        """Persist the start of the trace to PostgreSQL."""
        try:
            client = await get_postgres_client()
            await client.execute(
                """
                INSERT INTO pipeline_traces
                (trace_id, parent_id, session_id, agent_id, operation, status, metadata, start_time_utc)
                VALUES ($1, $2, $3, $4, $5, $6, $7, $8)
                """,
                self.trace_id,
                self.parent_id,
                self.session_id,
                self.agent_id,
                self.operation,
                self.status,
                json.dumps(self.metadata),
                self.start_time,
            )
        except Exception as e:
            logger.warning("Failed to persist trace start", trace_id=self.trace_id, error=str(e))

    async def complete(self, metadata_update: dict[str, Any] | None = None) -> None:
        """Mark the trace as successfully completed and persist to DB."""
        self.status = "COMPLETED"
        self.end_time = datetime.now(UTC)
        if metadata_update:
            self.metadata.update(metadata_update)

        duration_ms = int((self.end_time - self.start_time).total_seconds() * 1000)

        try:
            client = await get_postgres_client()
            await client.execute(
                """
                UPDATE pipeline_traces
                SET status = $2, metadata = $3, end_time_utc = $4, duration_ms = $5
                WHERE trace_id = $1
                """,
                self.trace_id,
                self.status,
                json.dumps(self.metadata),
                self.end_time,
                duration_ms,
            )
        except Exception as e:
            logger.warning("Failed to persist trace completion", trace_id=self.trace_id, error=str(e))

    async def fail(self, error: str, metadata_update: dict[str, Any] | None = None) -> None:
        """Mark the trace as failed and persist error details."""
        self.status = "FAILED"
        self.end_time = datetime.now(UTC)
        self.metadata["error"] = error
        if metadata_update:
            self.metadata.update(metadata_update)

        duration_ms = int((self.end_time - self.start_time).total_seconds() * 1000)

        try:
            client = await get_postgres_client()
            await client.execute(
                """
                UPDATE pipeline_traces
                SET status = $2, metadata = $3, end_time_utc = $4, duration_ms = $5
                WHERE trace_id = $1
                """,
                self.trace_id,
                self.status,
                json.dumps(self.metadata),
                self.end_time,
                duration_ms,
            )
        except Exception as e:
            logger.warning("Failed to persist trace failure", trace_id=self.trace_id, error=str(e))
