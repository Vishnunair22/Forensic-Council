# Security Policy

The Forensic Council handles highly sensitive, evidentiary material. Security is our paramount concern.

## Cryptographic Signing Architecture

The system uses an ECDSA deterministic methodology to sign the final `InvestigationReport`.

### 1. The Signing Key
*   The system is seeded with a `SIGNING_KEY` 256-bit hexadecimal string defined in `.env`.
*   This key is used to derive an Elliptic Curve private key (SECP256R1 / P-256).

### 2. The Custody Chain
*   Upon the Council Arbiter reaching a final verdict, the entire JSON payload (including the verdict string, timestamp, and array of agent findings) is serialized.
*   This serialized string is hashed via **SHA-256** to generate the `report_hash`.
*   The `report_hash` is then signed using the derived private key. This signature is attached to the final DTO as `cryptographic_signature`.

### 3. Key Rotation Procedure
If the key must be rotated:
1.  Generate a new 32-byte hex.
2.  Update `SIGNING_KEY` in the `.env` root file.
3.  Restart the backend container: `docker compose -f docs/docker/docker-compose.yml --env-file .env up -d --force-recreate backend`
**Note:** Old reports accessed via the API or stored in Postgres will fail signature verification against the new key. This is expected and ensures temporal separation of evidence custody boundaries.

---

## Authentication & Credential Hardening (v1.0.3)

### No credentials in source code
Demo-user password hashes are never stored in the codebase. On startup, the backend reads `BOOTSTRAP_ADMIN_PASSWORD` and `BOOTSTRAP_INVESTIGATOR_PASSWORD` from the environment, hashes them with bcrypt, and inserts them into the database. Changing a password requires only an env update and container restart.

### JWT token lifetime
Access tokens expire after **60 minutes** (down from 7 days in earlier versions). This limits the blast radius of a stolen token in evidentiary systems where long-lived sessions are a compliance risk.

### Brute-force login protection
Failed login attempts are tracked per source IP using Redis (`login_fail:{ip}` counter). After 5 failures within a 5-minute window the IP is locked out for 15 minutes. Lockout state and TTL are stored in Redis with automatic expiry; the implementation falls back to an in-process dict when Redis is unavailable.

---

## Rate Limiting

### Investigation rate limiter (v1.0.3)
Authenticated users are limited to **5 investigation submissions per 5-minute window**. Counters are backed by Redis and fall back to an in-process dict when Redis is unavailable. Exceeding the limit returns `HTTP 429 Too Many Requests` with a `Retry-After` header.

---

## HTTP Security Headers

Every response carries the following headers (set in `api/main.py`):

| Header | Value |
|--------|-------|
| `X-Content-Type-Options` | `nosniff` |
| `X-Frame-Options` | `DENY` |
| `X-XSS-Protection` | `1; mode=block` |
| `Referrer-Policy` | `strict-origin-when-cross-origin` |
| `Permissions-Policy` | `camera=(), microphone=(), geolocation=()` |
| `Content-Security-Policy` | `default-src 'self'; …` |
| `Strict-Transport-Security` | `max-age=31536000; includeSubDomains` *(production only)* |

---

## Input Validation

*   **File upload:** MIME type allow-list + `_ALLOWED_EXTENSIONS` frozenset; both must match. Max size 50 MB enforced at middleware level (HTTP 413 before the body is read).
*   **`case_id` / `investigator_id`:** Allow-list regex (`^[A-Za-z0-9_\-]{1,64}$`) enforced before the pipeline starts. Rejects path-traversal and injection payloads.

---

## Reporting a Vulnerability

If you discover a security vulnerability within the Forensic Council, please avoid opening a public issue.

Send an encrypted email directly to the project maintainers containing:
*   Description of the vulnerability.
*   The environment details (Docker version, Postgres/Redis versions).
*   A Proof-Of-Concept (PoC) script or detailed reproduction steps.

Maintainers will respond within 48 hours to acknowledge receipt and provide a triage timeline.

**Vulnerability Types of High Interest:**
*   Bypass of file size or extension validation checks.
*   Injection attacks via `case_id` or `investigator_id` payloads.
*   Any method capable of coercing an agent into an infinite ReAct loop, causing a Denial of Service (DoS) attack.
*   JWT forgery or token blacklist bypass.
*   Rate-limiter bypass allowing resource exhaustion.
