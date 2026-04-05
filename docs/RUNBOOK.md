# Production Incident Runbook

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

### P1: Chain-of-custody logging failures

```bash
# 1. Check logs for "CUSTODY GAP"
docker compose logs backend | grep "CUSTODY GAP"

# 2. Common causes:
#    - PostgreSQL write failure (disk full, permissions)
#    - Connection pool exhausted

# 3. Check disk space
docker compose exec postgres df -h /var/lib/postgresql/data

# 4. Verify chain integrity for affected session
# Use the /api/v1/sessions/{id}/verify endpoint
curl -H "Authorization: Bearer $TOKEN" http://localhost:8000/api/v1/sessions/{session_id}/verify
```

### P1: Agent repeatedly failing

```bash
# 1. Identify which agent
docker compose logs backend | grep "Agent.*error\|Agent.*failed"

# 2. Common causes per agent:
#    Agent 1 (Image): EasyOCR model download failure, Gemini API key invalid
#    Agent 2 (Audio): Missing HF_TOKEN, pyannote model download failure
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

# 3. Quick fix: increase timeout in .env
INVESTIGATION_TIMEOUT=900

# 4. Long-term: enable GPU for YOLO, use Gemini flash model
```

### P2: Redis connection errors

```bash
# 1. Is Redis running?
docker compose exec redis redis-cli ping

# 2. Check memory
docker compose exec redis redis-cli INFO memory

# 3. If Redis is down, the app fails secure (rejects tokens)
# Restart Redis:
docker compose restart redis
```

### P2: JWT tokens rejected

```bash
# 1. Check if SIGNING_KEY changed (tokens signed with old key become invalid)
grep SIGNING_KEY .env

# 2. Check token expiry
# Default is 60 minutes. If users report frequent logouts, verify:
grep JWT_ACCESS_TOKEN_EXPIRE_MINUTES .env

# 3. If Redis is down and app_env=production, all tokens are rejected (fail-secure)
# Fix Redis first, then tokens will work again
```

---

## Rollback Procedure

If a deployment breaks production:

```bash
# 1. Revert to previous Docker image
docker compose -f infra/docker-compose.yml --env-file .env down
git checkout HEAD~1
docker compose -f infra/docker-compose.yml --env-file .env up -d --build

# 2. Verify health
curl -s http://localhost:8000/health

# 3. If database schema changed, restore from backup
docker compose exec postgres pg_restore -U forensic_user -d forensic_council /backups/latest.dump
```

---

## Escalation Path

1. **On-call engineer** investigates using this runbook
2. If unresolved in 30 minutes → **Team lead** notified
3. If data integrity suspected → **Security team** engaged
4. If legal/compliance impact → **Legal counsel** notified

---

## Post-Incident

After resolving any P0 or P1 incident:

1. Write a brief post-mortem (what happened, root cause, fix, prevention)
2. Update this runbook if a new failure mode was discovered
3. Add a test case to prevent regression
4. Update `docs/Development-Status.md` if a code fix was deployed
