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

## Gemini API Downtime

When the Gemini API is unreachable or rate-limited, Agents 1, 3, and 5 downgrade
to local-only analysis. Investigations still complete but the `degradation_flags`
field in the report will be non-empty.

```bash
# 1. Confirm Gemini is the issue
docker compose logs backend | grep -i "gemini\|circuit.*open\|GEMINI_DEGRADED"

# 2. Check which circuit state the breaker is in
curl -H "Authorization: Bearer $TOKEN" http://localhost:8000/api/v1/metrics/raw \
  | grep circuit_breaker

# 3. Check current API quota (free tier = 10 RPM, 1500 RPD)
#    Open: https://aistudio.google.com/apikey ? Usage tab

# 4. If the key is valid but quota exhausted, wait for the daily reset (midnight PT).
#    Investigations running during the outage will carry the degradation flag:
#    "gemini_unavailable: deep analysis ran without Gemini context"

# 5. To force the circuit breaker to attempt recovery immediately (HALF_OPEN):
#    Restart only the backend container (keeps Redis/Postgres intact):
docker compose -f infra/docker-compose.yml restart backend

# 6. To switch permanently to local-only mode (no Gemini):
#    Remove GEMINI_API_KEY from .env and restart.
#    All reports will carry the degradation flag � communicate this to investigators.
```

**Impact on report quality**: Without Gemini, cross-modal semantic grounding is
disabled. The manipulation_probability score is still computed from local tools,
but court_statement values will be less detailed. Mark any reports generated
during an outage with the `analysis_coverage_note` field in the report footer.

---

## Redis Restart and Working Memory Recovery

Redis holds in-flight investigation state (tool results, agent progress, HITL
checkpoints). A Redis restart during an active investigation will cause those
investigations to lose their working memory.

```bash
# 1. Check Redis health
docker compose exec redis redis-cli ping
docker compose exec redis redis-cli INFO memory | grep used_memory_human

# 2. Check active investigation keys before restart
docker compose exec redis redis-cli KEYS "investigation:*" | wc -l
docker compose exec redis redis-cli KEYS "session:*" | wc -l

# 3. Safe restart path:
#    a. Wait for active investigations to complete (check /api/v1/metrics for
#       active_investigations count = 0), OR
#    b. Accept that in-flight investigations will orphan and be cleaned up
#       by the orphaned-session recovery at next backend startup.

# 4. Restart Redis
docker compose -f infra/docker-compose.yml restart redis

# 5. Verify recovery
docker compose exec redis redis-cli ping  # ? PONG
curl -s http://localhost:8000/health | python -m json.tool  # redis: "healthy"

# 6. Orphaned sessions are auto-recovered at backend startup.
#    To trigger manually without restart:
curl -X POST -H "Authorization: Bearer $ADMIN_TOKEN" \
  http://localhost:8000/api/v1/admin/recover-sessions
```

**Data loss scope**: Only in-progress tool results are lost. PostgreSQL custody
logs are written per-tool and are durable. Completed investigations are unaffected.

---

## Evidence File Cleanup

Evidence files are retained for `EVIDENCE_RETENTION_DAYS` (default 7) days.
There is no automated scheduler � cleanup must be triggered manually until a
cron job is added.

```bash
# 1. Check current evidence storage size
docker compose exec backend du -sh /app/storage/evidence/

# 2. Preview what would be deleted (dry run) � files older than retention period
docker compose exec backend python scripts/cleanup_storage.py --dry-run

# 3. Run cleanup
docker compose exec backend python scripts/cleanup_storage.py

# 4. Verify disk freed
docker compose exec backend du -sh /app/storage/evidence/
```

**GDPR note**: Evidence files belonging to EU subjects must be deleted on request
within 30 days (Article 17). Use the session_id to locate and delete specific files:
```bash
docker compose exec backend python scripts/cleanup_storage.py --session-id <uuid>
```

---

## Graceful Shutdown Behaviour

The backend waits up to 120 seconds for active investigations to complete before
shutting down (`stop_grace_period: 130s` in docker-compose.yml). During this window:

- New investigation submissions are rejected (503)
- Active investigations continue running
- WebSocket clients receive a `PIPELINE_PAUSED` or completion event

```bash
# Monitor shutdown progress
docker compose logs -f backend | grep -i "shutdown\|graceful\|investigation"

# If an investigation is stuck and shutdown is blocking:
# 1. Wait the full 130-second grace period
# 2. After SIGKILL, orphaned sessions are recovered at next startup
# 3. Check custody logs for completeness of the orphaned session
curl -H "Authorization: Bearer $TOKEN" \
  http://localhost:8000/api/v1/sessions/<session_id>/verify
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

## Maintenance Tasks

### Automated Backups (Postgres)

The system includes a backup cron task for Postgres:

```bash
# Run manual backup
docker compose exec backend python scripts/backup_db.py

# Restore from backup
docker compose exec -T postgres pg_restore -U forensic_user -d forensic_council < backup_file.dump
```

**Note**: Configure a scheduled job outside Docker (cron, kubernetes cronjob) to run `backup_db.py` daily.

### Evidence Retention

The system includes an evidence retention enforcer:

```bash
# Runs with EVIDENCE_RETENTION_DAYS env var (default: 7)
docker compose exec worker python scripts/enforce_retention.py
```

**Note**: Configure a scheduled job outside Docker to run `enforce_retention.py` daily.
Evidence older than `EVIDENCE_RETENTION_DAYS` is deleted from the evidence store.

### Zero-Downtime Deploys (Swarm/K8s)

Current `docker-compose` deployment does NOT support zero-downtime rolling updates.
For production deployments requiring zero-downtime, migrate to:

- **Docker Swarm**: Use `deploy.update_config` in compose
- **Kubernetes**: Use rolling update strategy with readiness probes

---

## Post-Incident

After resolving any P0 or P1 incident:

1. Write a brief post-mortem (what happened, root cause, fix, prevention)
2. Update this runbook if a new failure mode was discovered
3. Add a test case to prevent regression
4. Update `docs/TROUBLESHOOTING.md` with a new entry if a previously unknown failure mode was encountered
