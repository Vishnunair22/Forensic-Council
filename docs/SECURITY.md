# Security Policy — Forensic Council

The Forensic Council handles highly sensitive, evidentiary material. Security is a primary concern at every layer.

---

## Cryptographic Signing Architecture

### 1. The Signing Key

The system derives an Elliptic Curve private key (SECP256R1 / P-256) deterministically from `SIGNING_KEY` (a 32-byte hex string from `.env`) using HMAC-SHA-256. Each agent gets its own deterministic key derived from `HMAC(SIGNING_KEY, agent_id)`. This ensures keys are stable across restarts as long as `SIGNING_KEY` doesn't change.

Generate a secure key:
```bash
python -c "import secrets; print(secrets.token_hex(32))"
```

### 2. The Custody Chain

1. Every agent action (THOUGHT, ACTION, OBSERVATION) is signed and written to `chain_of_custody` in PostgreSQL.
2. Upon final verdict, the complete report JSON is serialised with sorted keys and hashed via **SHA-256** → `report_hash`.
3. The hash is then signed: `ECDSA-P256-SHA256(report_hash + timestamp_iso)` → `cryptographic_signature`.
4. The signature is attached to the `ReportDTO` returned to the frontend.

### 3. Key Rotation

If `SIGNING_KEY` must be rotated:
1. Generate a new 32-byte hex: `python -c "import secrets; print(secrets.token_hex(32))"`
2. Update `SIGNING_KEY` in `.env`
3. Restart backend: `docker compose -f docs/docker/docker-compose.yml --env-file .env up -d --force-recreate backend`

> **Note:** Reports signed with the old key will fail verification against the new key. This is expected and ensures temporal separation of evidence custody boundaries.

---

## Authentication & Credential Hardening

### No credentials in source code
Demo-user password hashes are never stored in the codebase. On startup, the backend reads `BOOTSTRAP_ADMIN_PASSWORD` and `BOOTSTRAP_INVESTIGATOR_PASSWORD` from the environment, hashes them with bcrypt (work factor 12), and inserts them into the `users` table. Changing a password requires only an env update and container restart.

### JWT token lifetime
Access tokens expire after **60 minutes**. The `expires_in` field in the login response reflects the real TTL in seconds. Longer-lived sessions are unsupported to limit blast radius if a token is stolen in an evidentiary context.

> The 60-minute limit is enforced in `JWT_ACCESS_TOKEN_EXPIRE_MINUTES`. The security tests include a regression guard (`test_jwt_expire_minutes_is_reasonable`) that fails if this is set above 120 minutes.

### Token blacklisting (fail-secure)
Logout blacklists the token via Redis (`blacklist:{token}` key with TTL = remaining JWT validity). On every authenticated request, `is_token_blacklisted()` checks Redis before decoding the JWT.

**Fail-secure behaviour:** If Redis is unavailable, `is_token_blacklisted()` returns `True` — all requests are denied until Redis recovers. This is intentional: the alternative (granting access when blacklist is unverifiable) could allow replayed stolen tokens during an outage. See ADR 7 in `docs/DECISIONS.md`.

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

- **File upload:** MIME type allow-list AND `_ALLOWED_EXTENSIONS` frozenset — both must match. Max 50 MB enforced at middleware level (HTTP 413 before the request body is read).
- **`case_id` / `investigator_id`:** Strict allow-list regex `^[A-Za-z0-9_\-\.]{1,128}$` enforced before the pipeline starts. Rejects path-traversal characters, shell metacharacters, and SQL injection payloads.
- **Request body size:** 55 MB hard limit on all POST/PUT/PATCH requests (middleware, before any route handler).
- **WebSocket auth:** Token required within 10 seconds of connection open; close code 4001 on failure.

---

## Container Security

The backend container runs with:
```yaml
read_only: true             # Filesystem is read-only
tmpfs:
  - /tmp:nosuid,size=512m  # Only writable path is tmpfs /tmp
```
All other writable paths (`/app/storage/evidence`, `/app/cache`, ML model caches) are Docker named volumes — not host-mounted directories.

---

## HTML Output Security

The `reports/report_renderer.py` `render_html()` function applies `html.escape()` to all user-controlled fields (`case_id`, `executive_summary`, `uncertainty_statement`, `agent_id`, `finding_type`, `report_hash`, `cryptographic_signature`) before inserting them into HTML output. This prevents XSS if a malicious actor embeds HTML/JS in evidence metadata.

---

## Reporting a Vulnerability

If you discover a security vulnerability, please avoid opening a public issue.

Send an encrypted report to the project maintainers containing:
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
- Pin exact versions in `pyproject.toml` (managed via `uv.lock`)
- Security updates applied via `uv lock --upgrade` then tested in CI
- Critical CVEs block merges via the `security-scan` CI job

### Frontend
- Run `npm audit` weekly to check for known vulnerabilities
- `package-lock.json` ensures reproducible builds
- The `security-scan` CI job (Trivy) scans the entire filesystem for CRITICAL/HIGH CVEs
- High-severity npm audit findings block merges

### Automated Scanning
- GitHub Dependabot is recommended for automated dependency update PRs
- Trivy runs on every push/PR via `.github/workflows/ci.yml` `security-scan` job
- Docker images should be re-scanned before each production deployment
