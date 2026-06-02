# Security Policy â€” Forensic Council

The Forensic Council handles highly sensitive, evidentiary material. Security is a primary concern at every layer.

---

## Cryptographic Signing Architecture

### 1. The Signing Key

In the normal runtime path, the system stores an independent ECDSA P-256 key pair
for each forensic agent in the `agent_signing_keys` PostgreSQL table. Private
keys are encrypted at rest with a Fernet key derived from `SIGNING_KEY` via
HKDF-SHA256.

If PostgreSQL is unavailable outside production, the keystore can derive
deterministic fallback keys from `SIGNING_KEY` via HMAC-SHA256. Production
deployments fail closed instead of using this fallback, because a single
`SIGNING_KEY` compromise would otherwise undermine all agent signatures.

Generate a secure root key:
```bash
python -c "import secrets; print(secrets.token_hex(32))"
```

### 2. The Custody Chain

1. Every agent action (THOUGHT, ACTION, OBSERVATION) is signed and written to `chain_of_custody` in PostgreSQL.
2. Upon final verdict, the complete report JSON is serialised with sorted keys and hashed via **SHA-256** â†’ `report_hash`.
3. The hash is then signed: `ECDSA-P256-SHA256(report_hash + timestamp_iso)` â†’ `cryptographic_signature`.
4. The signature is attached to the `ReportDTO` returned to the frontend.

### 3. Key Rotation

If an individual agent key must be rotated, back up `agent_signing_keys`, then run
the backend keystore rotation path (`get_keystore().rotate_key("Agent1")`) from an
operator-controlled backend shell. There is no public key-rotation API route.

If the root `SIGNING_KEY` must be rotated, treat it as a high-impact maintenance
operation: existing encrypted private keys cannot be decrypted with the new root
secret unless they are rewrapped or regenerated, and reports signed with older
keys may fail verification against only the new active key material.

---

## Authentication & Credential Hardening

### No credentials in source code
Demo-user password hashes are never stored in the codebase. On startup, the backend reads `BOOTSTRAP_ADMIN_PASSWORD` and `BOOTSTRAP_INVESTIGATOR_PASSWORD` from the environment, hashes them with bcrypt (work factor 12), and inserts them into the `users` table. Changing a password requires only an env update and container restart.

**âš ï¸ CRITICAL:** Never commit `.env` files to source control. The `.env.example` file uses `CHANGE_ME` placeholders â€” replace these with strong, unique values before deployment.

### JWT token lifetime
Access tokens expire after **60 minutes**. The `expires_in` field in the login response reflects the real TTL in seconds. Longer-lived sessions are unsupported to limit blast radius if a token is stolen in an evidentiary context.

> The 60-minute limit is enforced in `JWT_ACCESS_TOKEN_EXPIRE_MINUTES`. The security tests include a regression guard (`test_jwt_expire_minutes_is_reasonable`) that fails if this is set above 120 minutes.

### Token blacklisting (fail-secure)
Logout blacklists the token via Redis (`blacklist:{token}` key with TTL = remaining JWT validity). On every authenticated request, `is_token_blacklisted()` checks Redis before decoding the JWT.

**Fail-secure behaviour:** If Redis is unavailable, `is_token_blacklisted()` returns `True` â€” all requests are denied until Redis recovers. This is intentional: the alternative (granting access when blacklist is unverifiable) could allow replayed stolen tokens during an outage. See ADR 7 in `docs/adr/`.

> **Session 4 audit (2026-03-16):** The `blacklist_token()` call in the logout endpoint was verified to store `blacklist:{jti}` with a TTL equal to the token's remaining validity seconds (not a fixed TTL). This ensures blacklist entries expire naturally and Redis memory does not accumulate indefinitely. The `is_token_blacklisted()` function was also confirmed to check the JTI claim, not the raw token string, making blacklist lookups O(1) and immune to token re-encoding attacks.

### Brute-force login protection
Failed login attempts are tracked per source IP using Redis (`login_fail:{ip}` counter with a 15-minute TTL). After 5 failures within a 5-minute window, the IP is locked out for 15 minutes. Falls back to an in-process dict when Redis is unavailable (correct behaviour on a single replica).

---

## Rate Limiting

### Investigation rate limiter
Authenticated users are limited to **10 investigation submissions per 5-minute window**. Counters are backed by Redis and fall back to an in-process sliding window when Redis is unavailable. Exceeding the limit returns `HTTP 429 Too Many Requests` with a `Retry-After` header.

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
| `Content-Security-Policy` | `default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' blob: data:; connect-src 'self' ws: wss:;` |
| `Strict-Transport-Security` | `max-age=31536000; includeSubDomains` *(production only)* |

---

## Input Validation

- **File upload:** MIME type allow-list AND `_ALLOWED_EXTENSIONS` frozenset â€” both must match. Max 50 MB enforced at middleware level (HTTP 413 before the request body is read).
- **`case_id` / `investigator_id`:** Strict allow-list regex `^[A-Za-z0-9_\-\.]{1,128}$` enforced before the pipeline starts. `case_id` must also start with `CASE-`. Rejects path-traversal characters, shell metacharacters, and SQL injection payloads.
- **Request body size:** 55 MB hard limit on all POST/PUT/PATCH requests (middleware, before any route handler).
- **WebSocket auth:** Token required within 10 seconds of connection open; close code 4001 on failure.

---

## Container Security

The backend container runs with:
```yaml
read_only: true             # Filesystem is read-only
security_opt:
  - no-new-privileges:true  # Prevent privilege escalation
cap_drop:
  - ALL                     # Drop all Linux capabilities
tmpfs:
  - /tmp:nosuid,size=512m  # Only writable path is tmpfs /tmp
```
All other writable paths (`/app/storage/evidence`, `/app/cache`, ML model caches) are Docker named volumes â€” not host-mounted directories.

---

## Admissibility Standards

The Forensic Council is designed to meet the rigorous requirements for digital evidence admissibility in international courts.

### 1. Daubert Standard (US Federal)
Our methodology adheres to the Daubert criteria for expert testimony:
- **Empirical Testing**: Every forensic tool is subject to recall/precision validation in our CI suite.
- **Peer Review**: We use industry-standard algorithms (SIFT, ELA, SRM) documented in forensic literature.
- **Error Rates**: Real-time error rate estimation is calculated for every agent verdict.
- **Standards & Controls**: Cryptographic chain-of-custody ensures evidence integrity.

### 2. ISO/IEC 27037:2012
We implement the principles of **Digital Evidence Preservation**:
- **Auditability**: Every "Act" in the ReAct loop is signed and logged.
- **Reproducibility**: Analysis can be re-run on the original artifact to yield identical results.
- **Repeatability**: Using consistent ML weights and deterministic tool execution.

### 3. NIST SP 800-86
The system follows the NIST Guideline for Integrating Forensic Techniques into Incident Response, ensuring that digital data is acquired and analyzed without alteration of the original evidence artifact (read-only volume mounts for models).

---

## Report Output Security

The production report surface is JSON returned by the API and rendered by the Next.js UI. User-controlled evidence metadata is validated before pipeline entry, report DTOs are typed in `api/schemas.py`, and React escapes interpolated text by default when rendering the report components under `apps/web/src/components/result/`.

---

## Reporting a Vulnerability

If you discover a security vulnerability in Forensic Council, please report it via a **GitHub Security Advisory** at [https://github.com/Vishnunair22/Forensic-Council/security/advisories/new](https://github.com/Vishnunair22/Forensic-Council/security/advisories/new).

**Do NOT** file a public issue for security vulnerabilities.

Your report should contain:
- Description of the vulnerability
- Environment details (Docker version, OS, Python version)
- Proof-of-concept or detailed reproduction steps

Response time: 48 hours for acknowledgement, 7 days for triage.

**High-interest vulnerability classes:**
- Bypass of file size or extension validation
- Injection attacks via `case_id` or `investigator_id` payloads
- JWT forgery or token blacklist bypass
- Any method forcing an agent into an infinite ReAct loop (DoS)
- Rate-limiter bypass allowing resource exhaustion
- WebSocket authentication bypass
- Chain-of-custody log tampering

---

## Dependency Vulnerability Management

### Python Backend
- Run `pip-audit --desc` weekly to check for known vulnerabilities
- Pin exact versions in `pyproject.toml` when reproducibility is required
- Security updates are applied through dependency manifest updates and Docker build verification
- Critical CVEs block merges via the `security-scan` CI job

### Frontend
- Run `npm audit` weekly to check for known vulnerabilities
- Add and maintain npm/uv lockfiles before using frozen or `npm ci` installs
- The `security-scan` CI job (Trivy) scans the entire filesystem for CRITICAL/HIGH CVEs
- High-severity npm audit findings block merges

### Automated Scanning
- GitHub Dependabot is recommended for automated dependency update PRs
- Trivy runs on every push/PR via `.github/workflows/ci.yml` `security-scan` job
- Docker images should be re-scanned before each production deployment

---

## bcrypt Shim Retention Rationale

(P3-DOCS-003 fix, audit v6→v7 — see also `docs/adr/ADR-005-bcrypt-shim-retention.md`)

`apps/api/core/_bcrypt_shim.py` pins `bcrypt>=3.2,<4.1` and re-exports `hashpw`/
`checkpw` via the `passlib` compatibility shim. This is intentionally retained because:

1. `passlib` 1.7.x's `bcrypt` backend makes private API calls removed in bcrypt 4.x.
   The shim restores them without patching passlib itself.
2. Upgrading to native `bcrypt>=4.1` requires replacing all `passlib.hash.bcrypt` call
   sites — a broader change that warrants its own migration and testing cycle.
3. The current pin has no known CVEs and is tested in CI.

**Forward path**: when migrating off passlib, remove the shim and use
`bcrypt.hashpw`/`bcrypt.checkpw` directly with `bcrypt>=4.1`.

---

## Caddy Security Header Decisions

(P3-DOCS-003 fix, audit v6→v7)

- **CSP is owned by Next.js middleware** (`apps/web/src/middleware.ts`), not Caddy.
  Caddy previously set a conflicting CSP header that broke `'unsafe-inline'` styles;
  that header was removed so Next.js middleware is the sole CSP authority.
- **COOP / COEP**: Currently not set. SharedArrayBuffer is not used. If COOP/COEP are
  added in future, they must be set in Next.js middleware (not Caddy) to avoid the same
  double-header conflict.
- **Permissions-Policy**: Not set by Caddy. If added, use Next.js middleware so the
  policy is consistent across all routes including API proxying.
