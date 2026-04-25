"""
Unit tests for the chain-of-custody logger.

All tests are fully self-contained â€” no real PostgreSQL connection required.
A MockPostgresClient simulates the database in memory so every test runs
offline and in isolation.
"""

import os
from typing import Any
from uuid import uuid4

import pytest

# ── Minimal env so config initializes without a .env file ────────────────────
os.environ.setdefault("APP_ENV", "testing")
os.environ.setdefault("SIGNING_KEY", "test-signing-key-" + "x" * 32)
os.environ.setdefault("POSTGRES_USER", "test")
os.environ.setdefault("POSTGRES_PASSWORD", "test")
os.environ.setdefault("POSTGRES_DB", "test")
os.environ.setdefault("REDIS_PASSWORD", "test")
os.environ.setdefault("NEXT_PUBLIC_DEMO_PASSWORD", "test")
os.environ.setdefault("LLM_PROVIDER", "none")
os.environ.setdefault("LLM_API_KEY", "test-key")
os.environ.setdefault("LLM_MODEL", "test-model")

from core.custody_logger import (
    ChainVerificationReport,
    CustodyLogger,
    EntryType,
)
from core.signing import compute_content_hash

# â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
# Mock database client
# â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€


class MockPostgresClient:
    """
    In-memory substitute for the PostgreSQL client used by CustodyLogger.

    Stores every INSERT row so that fetch / fetch_one queries can replay
    the same data without a real database.
    """

    def __init__(self) -> None:
        self._rows: list[dict[str, Any]] = []

    # â”€â”€ Write side â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

    async def execute(self, query: str, *args) -> str:
        """Intercept INSERT and UPDATE statements."""
        q = query.strip().upper()

        if q.startswith("INSERT INTO CHAIN_OF_CUSTODY"):
            # args positional: entry_id, entry_type, agent_id, session_id,
            #                  timestamp_utc, content, content_hash, signature,
            #                  prior_entry_ref
            (
                entry_id,
                entry_type,
                agent_id,
                session_id,
                timestamp_utc,
                content,
                content_hash,
                signature,
                prior_entry_ref,
            ) = args
            self._rows.append(
                {
                    "entry_id": entry_id,
                    "entry_type": entry_type,
                    "agent_id": agent_id,
                    "session_id": session_id,
                    "timestamp_utc": timestamp_utc,
                    "content": content,
                    "content_hash": content_hash,
                    "signature": signature,
                    "prior_entry_ref": prior_entry_ref,
                }
            )
        elif q.startswith("UPDATE CHAIN_OF_CUSTODY"):
            # tamper_entry: SET content = $1 WHERE entry_id = $2
            new_content, entry_id = args
            for row in self._rows:
                if row["entry_id"] == entry_id:
                    row["content"] = new_content
                    break

        return "OK"

    # â”€â”€ Read side â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

    async def fetch(self, query: str, *args) -> list[dict[str, Any]]:
        """Return rows for a session, ordered by timestamp."""
        session_id = args[0] if args else None
        matching = [r for r in self._rows if r["session_id"] == session_id]
        return sorted(matching, key=lambda r: r["timestamp_utc"])

    async def fetch_one(self, query: str, *args) -> dict[str, Any] | None:
        """Return the most-recent row for a session, or a row by entry_id."""
        if not args:
            return None

        q = query.strip().upper()

        # _get_last_entry_hash query â€” keyed by session_id, ORDER BY timestamp DESC
        if "ORDER BY TIMESTAMP_UTC DESC" in q:
            session_id = args[0]
            matching = [r for r in self._rows if r["session_id"] == session_id]
            if not matching:
                return None
            return sorted(matching, key=lambda r: r["timestamp_utc"])[-1]

        # get_entry query â€” keyed by entry_id
        if "WHERE ENTRY_ID = $1" in q:
            entry_id = args[0]
            for row in self._rows:
                if row["entry_id"] == entry_id:
                    return row
            return None

        return None


# â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
# Helpers
# â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€


def _make_logger(mock_db: MockPostgresClient) -> CustodyLogger:
    """Create a CustodyLogger wired to the given in-memory database."""
    cl = CustodyLogger(postgres_client=mock_db)  # type: ignore[arg-type]
    return cl


# â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
# Tests
# â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€


@pytest.mark.asyncio
async def test_chain_links_entries() -> None:
    """
    Writing 3 entries should produce a hash-linked chain where:
    - Entry 0: prior_entry_ref is None
    - Entry 1: prior_entry_ref == content_hash of entry 0
    - Entry 2: prior_entry_ref == content_hash of entry 1
    """
    db = MockPostgresClient()
    cl = _make_logger(db)

    session_id = uuid4()
    agent = "test_agent"

    await cl.log_entry(agent, session_id, EntryType.THOUGHT, {"step": 1})
    await cl.log_entry(agent, session_id, EntryType.ACTION, {"step": 2})
    await cl.log_entry(agent, session_id, EntryType.OBSERVATION, {"step": 3})

    entries = db._rows  # raw rows, already ordered by insertion
    assert len(entries) == 3, "Expected exactly 3 rows"

    # First entry has no prior
    assert entries[0]["prior_entry_ref"] is None

    # Second entry links back to first
    assert entries[1]["prior_entry_ref"] == entries[0]["content_hash"]

    # Third entry links back to second
    assert entries[2]["prior_entry_ref"] == entries[1]["content_hash"]


@pytest.mark.asyncio
async def test_empty_chain_is_valid() -> None:
    """verify_chain on a session with no entries should return valid=True."""
    db = MockPostgresClient()
    cl = _make_logger(db)

    session_id = uuid4()
    report: ChainVerificationReport = await cl.verify_chain(session_id)

    assert isinstance(report, ChainVerificationReport)
    assert report.valid is True
    assert report.total_entries == 0
    assert report.broken_at is None
    assert report.broken_reason is None


@pytest.mark.asyncio
async def test_tampered_entry_fails_verification() -> None:
    """
    Manually corrupting a stored content dict should cause verify_chain to
    report valid=False with a non-empty broken_reason.
    """
    db = MockPostgresClient()
    cl = _make_logger(db)

    session_id = uuid4()
    agent = "integrity_agent"

    await cl.log_entry(agent, session_id, EntryType.THOUGHT, {"data": "original"})
    await cl.log_entry(agent, session_id, EntryType.ACTION, {"data": "second"})

    # Corrupt the first entry's content dict directly in the mock store
    db._rows[0]["content"] = {"data": "tampered!"}

    report: ChainVerificationReport = await cl.verify_chain(session_id)

    assert report.valid is False
    assert report.broken_reason is not None
    assert len(report.broken_reason) > 0


@pytest.mark.asyncio
async def test_first_entry_has_no_prior() -> None:
    """The very first log_entry for a session must have prior_entry_ref=None."""
    db = MockPostgresClient()
    cl = _make_logger(db)

    session_id = uuid4()
    await cl.log_entry("agent_x", session_id, EntryType.FINAL_FINDING, {"result": "ok"})

    assert len(db._rows) == 1
    assert db._rows[0]["prior_entry_ref"] is None


@pytest.mark.asyncio
async def test_valid_chain_verifies_successfully() -> None:
    """An unmodified chain of several entries should verify as valid."""
    db = MockPostgresClient()
    cl = _make_logger(db)

    session_id = uuid4()
    for i in range(5):
        await cl.log_entry("agent_v", session_id, EntryType.THOUGHT, {"n": i})

    report = await cl.verify_chain(session_id)
    assert report.valid is True
    assert report.total_entries == 5
    assert report.broken_at is None


@pytest.mark.asyncio
async def test_sessions_are_independent() -> None:
    """Entries from separate sessions must not interfere with each other."""
    db = MockPostgresClient()
    cl = _make_logger(db)

    session_a = uuid4()
    session_b = uuid4()

    await cl.log_entry("agent", session_a, EntryType.THOUGHT, {"s": "a"})
    await cl.log_entry("agent", session_b, EntryType.THOUGHT, {"s": "b"})

    report_a = await cl.verify_chain(session_a)
    report_b = await cl.verify_chain(session_b)

    assert report_a.valid is True
    assert report_a.total_entries == 1
    assert report_b.valid is True
    assert report_b.total_entries == 1


@pytest.mark.asyncio
async def test_content_hash_used_as_link() -> None:
    """prior_entry_ref must equal the SHA-256 hash of the prior entry's content."""
    db = MockPostgresClient()
    cl = _make_logger(db)

    session_id = uuid4()
    content_first = {"payload": "alpha"}
    await cl.log_entry("agent", session_id, EntryType.ACTION, content_first)
    await cl.log_entry("agent", session_id, EntryType.OBSERVATION, {"payload": "beta"})

    first_hash = db._rows[0]["content_hash"]
    expected_prior = compute_content_hash(content_first)

    assert first_hash == expected_prior
    assert db._rows[1]["prior_entry_ref"] == first_hash
