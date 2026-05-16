# Chain of Custody — Technical Reference

## Overview

Every tool execution in Forensic Council is recorded in an immutable custody
ledger. Each entry is cryptographically signed by the agent that produced it,
creating a tamper-evident audit trail that can be presented in legal proceedings.

---

## What Is Signed

Each custody entry covers one discrete tool invocation. The signed payload
includes:

| Field | Description |
|---|---|
| `action` | Tool name (e.g. `ela_full_image`, `voice_clone_detect`) |
| `session_id` | Investigation session UUID |
| `agent_id` | Agent that called the tool |
| `finding_type` | Category of result |
| `result_summary` | Structured tool output |
| `timestamp_utc` | Nanosecond-resolution UTC timestamp |
| `phase` | `initial` or `deep` analysis pass |

The signed message is: `SHA-256(JSON(payload)) + ":" + timestamp_ISO8601`

---

## Algorithm

| Component | Choice | Rationale |
|---|---|---|
| Signing | ECDSA P-256 (SECP256R1) | NIST-approved, compact signatures (≈72 bytes DER) |
| Hash | SHA-256 | Collision-resistant, NIST-approved |
| Key encryption at rest | Fernet (AES-128-CBC + HMAC-SHA256) | Symmetric, authenticated |
| Key derivation | HKDF-SHA256 | Proper KDF with domain separation (`forensic-council-keystore-v1`) |

---

## Key Architecture

### Per-Agent Independent Keys (preferred)

Each of the six agents (Agent1–Agent5, Arbiter) has its own independently
generated ECDSA P-256 key pair:

```
SIGNING_KEY (env var)
       │
       └─► HKDF-SHA256 ──► Fernet encryption key
                                   │
                ┌──────────────────┴──────────────────────┐
                │                                          │
         Agent1 private key                         Agent2 private key
         (random, encrypted at rest)                (random, encrypted at rest)
                │                                          │
                └──────────────── PostgreSQL ──────────────┘
                                  (agent_signing_keys table)
```

Compromising one agent's key does **not** compromise the others.

### Deterministic Fallback

When PostgreSQL is unavailable at startup, all agent keys are derived
deterministically from `SIGNING_KEY` via HMAC-SHA256:

```
SIGNING_KEY
       │
       ├─► HMAC-SHA256("Agent1") ──► P-256 private key for Agent1
       ├─► HMAC-SHA256("Agent2") ──► P-256 private key for Agent2
       └─► HMAC-SHA256("AgentN") ──► P-256 private key for AgentN
```

**Risk**: In fallback mode, all agents share the same master secret. A `SIGNING_KEY`
compromise undermines all agent signatures simultaneously. This is documented at
startup with a `CRITICAL` log entry.

Production deployments fail closed if the database-backed keystore cannot be
initialized; deterministic fallback is available only outside production.

---

## Storage

```sql
CREATE TABLE agent_signing_keys (
    id              SERIAL PRIMARY KEY,
    agent_id        TEXT NOT NULL,
    encrypted_private_key_pem  TEXT NOT NULL,   -- Fernet-encrypted
    public_key_pem  TEXT NOT NULL,              -- plaintext (public)
    is_active       BOOLEAN NOT NULL DEFAULT TRUE,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE chain_of_custody (
    entry_id        UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    entry_type      VARCHAR(64) NOT NULL,
    agent_id        VARCHAR(64) NOT NULL,
    session_id      UUID NOT NULL,
    timestamp_utc   TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    content         JSONB NOT NULL,
    content_hash    VARCHAR(64) NOT NULL,
    signature       TEXT NOT NULL,
    prior_entry_ref VARCHAR(64)
);
```

---

## Verification

### Verify a session chain

There is no public `/api/v1/sessions/{session_id}/verify` route in the current
API. Chain verification is performed by backend code through
`CustodyLogger.verify_chain(session_id)`, and the pipeline calls this verifier
during report enrichment.

`verify_chain` returns:
- `valid: true/false` — whether every entry verifies
- `total_entries` — total number of signed entries
- `broken_at` — entry ID where verification failed, if any
- `broken_reason` — failure reason, if any

### Manual verification

```python
from core.signing import compute_content_hash, verify_entry, SignedEntry, get_keystore
import json

# Load entry from the database
entry = SignedEntry.from_dict(row)

# Verify one entry
ks = get_keystore()
is_valid = verify_entry(entry, keystore=ks)
print(f"Entry {entry.content_hash[:8]}... valid={is_valid}")
```

---

## Key Rotation

Key rotation should be performed:
- After any suspected key compromise
- Periodically per your security policy (recommended: annually)
- After personnel changes with key access

**Before rotating**, archive all signed entries for the agent — post-rotation
entries signed with the old key will not verify with the new key.

There is no public admin key-rotation route in the current API. Rotation is an
operator action against the backend keystore:

```python
import asyncio
from core.signing import get_keystore


async def rotate() -> None:
    ks = get_keystore()
    await ks.initialize()
    await ks.rotate_key("Agent1")


asyncio.run(rotate())
```

Back up the `agent_signing_keys` table before rotation; old entries signed with
retired keys are not verifiable after the active key changes.

---

## Limitations

| Limitation | Impact | Mitigation |
|---|---|---|
| Clock skew | Timestamp in signed message could be off if server clock drifts | Use NTP; Caddy/Docker include NTP sync |
| Fallback mode reduces key separation | One `SIGNING_KEY` compromise → all agents affected | Production fails closed; keep PostgreSQL healthy and monitor fallback log entries in non-production |
| No HSM | Private keys live in application memory | Fernet encryption at rest; access control via env secrets |
| No cross-server verification | Another instance cannot verify without the same `SIGNING_KEY` | Share `SIGNING_KEY` only between trusted replicas |
| Engineering-default calibration | Confidence scores are not court-calibrated | Run calibration training against a labelled forensic dataset |

---

## Reading a Signed Report in Court

When presenting a Forensic Council report as evidence:

1. **Provide the `report_hash`** — this is the SHA-256 of the complete report JSON
2. **Provide `cryptographic_signature`** — the Arbiter's ECDSA signature over the report
3. **State the algorithm** — ECDSA P-256 with SHA-256
4. **Confirm calibration status** — if `degradation_flags` is non-empty, disclose it
5. **Note the `calibration_status`** field on each finding — `UNCALIBRATED` scores
   are indicative only and must not be cited as calibrated probabilities

Any report with `calibration_status: UNCALIBRATED` on its findings carries the
following automatic court statement prefix:
> "[NOT court-admissible — UNCALIBRATED] ..."

This is set deterministically by `CalibrationLayer.calibrate()` and cannot be
suppressed by operators.

---

## Incident Response: Suspected Tampering

If you suspect a custody entry has been tampered with:

```bash
# 1. Verify the session chain from a backend shell
python - <<'PY'
import asyncio
from uuid import UUID
from core.custody_logger import get_custody_logger


async def main() -> None:
    report = await get_custody_logger().verify_chain(UUID("SESSION_UUID_HERE"))
    print(report)


asyncio.run(main())
PY

# 2. Check for CUSTODY GAP log entries
docker compose logs backend | grep "CUSTODY GAP"

# 3. Compare report_hash against what was issued
echo -n '{"report_id": ...}' | sha256sum

# 4. Escalate to security team — see OPERATIONAL_RUNBOOK.md §P0
```

See [OPERATIONAL_RUNBOOK.md](OPERATIONAL_RUNBOOK.md) for full incident escalation procedures.
