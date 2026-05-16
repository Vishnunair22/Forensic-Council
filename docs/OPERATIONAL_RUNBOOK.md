# Operational Runbook — Forensic Council

**Version:** v1.7.0

This runbook covers triage, severity levels, common failures, recovery commands, and observability for the Forensic Council stack. It supersedes the removed `docs/RUNBOOK.md`.

---

## Triage Checklist

When an alert fires or a user reports an issue:

1. Check `GET /health` — is the API responding?
2. Check Docker container status: `docker compose ps`
3. Check logs: `docker compose logs --tail=100 backend worker`
4. Check resource usage: `docker stats --no-stream`
5. Determine severity from the table below

---

## Severity Levels

| Level | Definition | Response Time | Examples |
|-------|-----------|---------------|----------|
| **P0** | Service completely down | Immediate | API returning 5xx, all investigations failing |
| **P1** | Partial degradation | < 1 hour | One agent failing, chain-of-custody gaps |
| **P2** | Performance issue | < 4 hours | Slow investigations, high latency |
| **P3** | Cosmetic / non-blocking | Next business day | UI glitch, log noise |

---

## Common Incidents

### P0: Backend container won't start

```bash
# 1. Check logs
docker compose logs --tail=50 backend

# 2. Common causes:
#    - Invalid .env (missing or malformed vars like SIGNING_KEY, JWT_SECRET_KEY)
#    - Database unreachable
#    - Port conflict

# 3. Fix:
#    - Validate .env: ensure all required vars are set (check for CHANGE_ME placeholders)
#    - Check postgres: docker compose exec postgres pg_isready
#    - Check port: netstat -tlnp | grep 8000

# 4. Restart:
docker compose -f infra/docker-compose.yml --env-file .env up -d --force-recreate backend
```

### P0: Database connection failures

```bash
# 1. Is postgres running?
docker compose exec postgres pg_isready

# 2. Check connection pool exhaustion
curl -s http://localhost:8000/health | python -m json.tool
# Look for postgres: "error: ..."

# 3. Check max connections
docker compose exec postgres psql -U forensic_user -c "SELECT count(*) FROM pg_stat_activity;"

# 4. Fix: increase pool or kill idle connections
docker compose exec postgres psql -U forensic_user -c "SELECT pg_terminate_backend(pid) FROM pg_stat_activity WHERE state = 'idle' AND query_start < now() - interval '10 minutes';"
```

### P0: Worker unhealthy during model warmup

```bash
# 1. Check worker health
docker compose ps worker

# 2. Check worker logs
docker compose logs --tail=50 worker

# 3. Common causes:
#    - Model download failure on first start (15-40 min on slow connections)
#    - GPU unavailable for GPU-accelerated models

# 4. Fix:
#    - Wait for model downloads to complete (check backend logs for model init)
#    - Verify GPU: docker exec worker nvidia-smi
#    - Restart worker: docker compose restart worker
```

### P1: Chain-of-custody logging failures

```bash
# 1. Check logs for "CUSTODY GAP"
docker compose logs backend | grep "CUSTODY GAP"

# 2. Common causes:
#    - PostgreSQL write failure (disk full, permissions)
#    - Connection pool exhausted

# 3. Check disk space
docker compose exec postgres df -h /var/lib/postgresql/data

# 4. Verify chain integrity for the affected session from a backend shell.
# There is no public /api/v1/sessions/{id}/verify route.
docker compose exec backend python - <<'PY'
import asyncio
from uuid import UUID
from core.custody_logger import get_custody_logger


async def main() -> None:
    report = await get_custody_logger().verify_chain(UUID("SESSION_UUID_HERE"))
    print(report)


asyncio.run(main())
PY
```

### P1: Redis unavailable

```bash
# 1. Is Redis running?
docker compose exec redis redis-cli ping

# 2. If Redis is down, the app fails secure (rejects tokens when APP_ENV=production)
# All requests are denied until Redis recovers.
# Restart Redis:
docker compose restart redis

# 3. Check memory
docker compose exec redis redis-cli INFO memory

# 4. Check for evicted keys
docker compose exec redis redis-cli INFO stats | grep evicted
```

### P1: Agent repeatedly failing

```bash
# 1. Identify which agent
docker compose logs backend | grep "Agent.*error\|Agent.*failed"

# 2. Common causes per agent:
#    Agent 1 (Image): EasyOCR model download failure, Gemini API key invalid
#    Agent 2 (Audio): pyannote model download failure, librosa fallback active
#    Agent 3 (Object): YOLO model corruption, GPU unavailable
#    Agent 4 (Video): FFmpeg not installed, codec unsupported
#    Agent 5 (Metadata): exiftool not found, hachoir import error

# 3. Fix per agent:
#    - Check API keys in .env
#    - Clear model cache: docker volume rm forensic-council_hf_cache
#    - Rebuild: docker compose build backend
```

### P2: Investigations timing out

```bash
# 1. Check current investigation duration
curl -s http://localhost:8000/api/v1/metrics | grep investigation_duration

# 2. Common causes:
#    - Large file upload (> 50MB)
#    - Gemini API rate limiting
#    - Slow ML model inference (YOLO on CPU)

# 3. Quick fix: increase timeout in .env (ML_SUBPROCESS_TIMEOUT_S)
# Default: 120 seconds

# 4. Long-term: enable GPU for YOLO, use Gemini flash model
```

### P2: Session stuck in "running"

```bash
# 1. Check session state in Redis
docker compose exec redis redis-cli KEYS "session:*"
docker compose exec redis redis-cli GET "session:{session_id}:status"

# 2. Check if worker is processing
docker compose logs worker | grep "{session_id}"

# 3. Force-terminate the session
curl -X DELETE -H "Authorization: Bearer $TOKEN" \
  http://localhost:8000/api/v1/sessions/{session_id}

# 4. Clear Redis session keys
docker compose exec redis redis-cli DEL "session:{session_id}:status"
```

### P2: WebSocket reconnect fails

```bash
# 1. Check backend WebSocket endpoint
curl -s http://localhost:8000/health

# 2. Check for Caddy WebSocket routing
docker compose logs caddy | grep "websocket\|ws"

# 3. Verify CORS settings
grep CORS_ALLOWED_ORIGINS .env

# 4. Check for stale WS connections
docker compose exec backend python -c "from core.websocket_manager import ws_manager; print(len(ws_manager.connections))"
```

---

## Recovery Commands

### Restart specific service
```bash
docker compose -f infra/docker-compose.yml --env-file .env restart backend
docker compose -f infra/docker-compose.yml --env-file .env restart worker
```

### Inspect Redis session keys
```bash
docker compose exec redis redis-cli KEYS "session:*"
docker compose exec redis redis-cli KEYS "investigation:*"
docker compose exec redis redis-cli KEYS "hitl:*"
```

### Inspect Postgres report state
```bash
docker compose exec postgres psql -U forensic_user -d forensic_council \
  -c "SELECT session_id, status, verdict, manipulation_probability FROM forensic_reports LIMIT 10;"
```

### Run provider verification script
```bash
cd apps/api
uv run python scripts/verify_llm_keys.py --json
```

### Run verification scripts
```bash
./scripts/verify_project.sh static
./scripts/verify_project.sh backend
```

---

## Gemini API Downtime

When Gemini is unreachable or rate-limited, Agents 1, 3, and 5 downgrade to local-only analysis. Investigations still complete but `degradation_flags` in the report will be non-empty.

```bash
# 1. Confirm Gemini is the issue
docker compose logs backend | grep -i "gemini\|circuit.*open\|GEMINI_DEGRADED"

# 2. Check which circuit state the breaker is in
curl -s http://localhost:8000/api/v1/metrics | grep -i gemini

# 3. Verify key and policy flag
grep GEMINI_API_KEY .env
grep GEMINI_API_KEY_POLICY_OK .env

# 4. If policy flag is false, set it true
# Edit .env: GEMINI_API_KEY_POLICY_OK=true
# Then: docker compose -f infra/docker-compose.yml --env-file .env up -d --force-recreate backend
```

---

## Observability

### Prometheus metrics
```text
/api/v1/metrics/raw  (requires METRICS_SCRAPE_TOKEN bearer)
```

### Prometheus UI
- `http://localhost:9090`

### Jaeger tracing
- `http://localhost:16686`

### Health endpoint
```bash
curl -s http://localhost:8000/health | python -m json.tool
```

---

## Production Deploy Gate

Run `infra/validate_production_readiness.sh` before any production deployment:

```bash
./infra/validate_production_readiness.sh
```

Run `scripts/verify_phase8_tests.sh` for comprehensive test verification:

```bash
./scripts/verify_phase8_tests.sh static
./scripts/verify_phase8_tests.sh backend-unit
./scripts/verify_phase8_tests.sh frontend-unit
./scripts/verify_project.sh all
```
