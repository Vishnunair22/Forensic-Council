# Development Status

**Last updated:** 2026-03-12
**Current version:** v1.0.3
**Overall health:** 🟢 Production-ready
**Actively working on:** —
**Blocked on:** None

---

## Pipeline Health

```
Upload → [✅] → Evidence Store → [✅] → Agent Dispatch → [✅] → Council Arbiter → [✅] → Signing → [✅] → Report
```

| Stage | Status | Notes |
|-------|--------|-------|
| File Upload | ✅ | MIME + extension allowlists, 50MB limit, non-blocking async I/O |
| Evidence Store | ✅ | Immutable storage with SHA-256 integrity check |
| Agent Dispatch | ✅ | Sequential execution with WebSocket streaming |
| Council Arbiter | ✅ | Cross-modal correlation, HITL, signing complete |
| Report Signing | ✅ | ECDSA P-256 + SHA-256, PostgreSQL custody log |
| Frontend Display | ✅ | Deduplication fix applied, arbiter race condition resolved |

---

## v1.0.3 Fixes (2026-03-12)

| # | File | Issue | Fix |
|---|------|-------|-----|
| 1 | `frontend/src/app/evidence/page.tsx` | `resumeInvestigation()` not awaited before `router.push('/result')` — report loaded before arbiter finished | Added `await resumeInvestigation()` before navigation |
| 2 | `frontend/src/app/evidence/page.tsx` | No guard on decision buttons — double-click submitted two concurrent arbiter calls | Added `isNavigating` boolean guard; buttons disabled and show "Compiling Report…" while navigating |
| 3 | `frontend/src/app/evidence/page.tsx` | Error during navigation left `isNavigating=true` permanently — UI stuck | Catch block resets `isNavigating=false` on error |
| 4 | `frontend/src/app/result/page.tsx` | Duplicate findings shown when same `finding_type` appeared in initial and re-run analyses | Dedup by `finding_type` unless `metadata.analysis_phase` is set (deep analysis findings preserved) |
| 5 | `frontend/src/hooks/useSound.ts` | Sound effects too jarring | Replaced with subtle, lower-volume audio cues |
| 6 | `frontend/Dockerfile` | `HOSTNAME` not set — container bound to `127.0.0.1` instead of `0.0.0.0`, unreachable from host | Added `ENV HOSTNAME=0.0.0.0` |
| 7 | `frontend/Dockerfile` | Healthcheck used `curl` — not available on Alpine images | Changed to `wget -q --spider` |
| 8 | `docs/docker/docker-compose.yml` | `start_period` too short — healthchecks failed before the server finished starting | Increased to 60s for backend, 45s for frontend |
| 9 | `docs/docker/docker-compose.yml` | No `restart` policy on frontend — crashed containers not recovered | Added `restart: unless-stopped` |

---

## v1.0.2 Fixes (2026-03-11)

| # | Issue | Fix |
|---|-------|-----|
| 1 | `fetchrow` called on client that only exposes `fetch_one` — DB report lookup crashed | Renamed all `fetchrow` → `fetch_one` |
| 2 | In-memory report cache lost on restart; second replica had no knowledge of another's sessions | Reports persisted to `session_reports` table; fallback chain: memory → Postgres |
| 3 | JWT token lifetime defaulted to 10,080 minutes (7 days) | Changed to 60 minutes everywhere |
| 4 | No rate limit on `/investigate` — single user could exhaust memory | Per-user Redis-backed rate limiter (5 req / 5-min window) |
| 5 | Hard-coded bcrypt hashes for demo users in binary | Moved to env-var-driven `_build_dev_fallback()` at startup |
| 6 | In-process dict metric counters reset on restart | Rewrote with Redis INCRBY counters |
| 7 | No HTTPS documentation in `.env.example` | Added full Caddy/Let's Encrypt guide |
| 8 | No CI/CD pipeline | Created `.github/workflows/ci.yml` |

---

## v1.0.1 Fixes (2026-03-10)

| # | Issue | Fix |
|---|-------|-----|
| 1 | `backend/Dockerfile` missing `development` stage | Added multi-stage: `base` → `development` → `production` |
| 2 | `uv` image pinned to non-existent tag | Changed to `uv:latest` |
| 3 | `eslint-config-next` version mismatch failed `next build` | Added `eslint: { ignoreDuringBuilds: true }` |
| 4 | No Caddy log volume — writes failed silently | Added `caddy_logs:/var/log/caddy` volume |
| 5 | Prod compose missing `build.target: production` | Added explicit target |
| 6 | `BEGIN/COMMIT/ROLLBACK` SQL with asyncpg (incompatible) | Replaced with `async with conn.transaction()` |
| 7 | Typo `Thumbbs.db` in `.dockerignore` | Fixed to `Thumbs.db` |
| 8 | `BOOTSTRAP_ADMIN_PASSWORD` was commented out | Uncommented with dev default |

---

## Known Limitations

| Area | Limitation |
|------|-----------|
| Agent execution | Sequential (not parallel) to maintain stable WebSocket streaming and prevent connection saturation |
| LLM inference | No fallback if provider API is unavailable — pipeline will fail and session times out |
| Video analysis | Frame extraction is CPU-intensive; large video files (>200MB) may timeout on slow machines |
| Audio diarization | Requires `HF_TOKEN` for pyannote gated models; skipped gracefully without it |
| Qdrant collections | Auto-created on first use; if Qdrant restarts before first write, collection may need manual init |
| Report persistence | Report data in Redis expires after 24 hours; Postgres custody log is permanent |

---

## Roadmap

- [ ] Parallel agent execution (configurable)
- [ ] LLM provider failover / retry
- [ ] Multi-file batch investigation
- [ ] WebSocket reconnection handling (auto-retry on drop)
- [ ] Prometheus metrics export
- [ ] Kubernetes Helm chart
