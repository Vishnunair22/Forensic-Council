# Troubleshooting Guide

> **Merged from:** `DEBUGGING.md`, `KNOWN_ISSUES.md`, and `ERROR_LOG.md`.
> The historical error log is preserved in `ERROR_LOG.md` for reference.

## WebSocket Connection Failures

### Symptom: "WebSocket connection failed (code 4001)"

**Cause**: Auth cookie not sent cross-origin

**Fix**:
- Verify `NEXT_PUBLIC_API_URL` matches your domain
- Check browser cookie policy
- Ensure `HttpOnly` flag is set on `access_token` cookie
- Verify CORS origins in `.env` include your frontend domain

### Symptom: "WebSocket keeps reconnecting"

**Cause**: Network instability or server overload

**Fix**:
- Check server logs for connection drops
- Verify Redis is running (used for session state)
- Increase WebSocket timeout in frontend config
- Check firewall/proxy settings

---

## ML Model Download Hangs

### Symptom: "First request takes 30+ minutes"

**Cause**: Models downloading in background

**Fix**:
- Pre-download models: `python probes/model_pre_download.py`
- Check `/tmp/model_download.log`
- Increase Docker memory limit to 8GB
- Verify internet connectivity from container

### Symptom: "ML tool initialization failed"

**Fix**:
```bash
# Check model cache
docker exec forensic_api ls -la /app/cache/

# Force re-download
docker exec forensic_api python -c "from core.ml_subprocess import warmup_all_tools; import asyncio; asyncio.run(warmup_all_tools(force=True))"
```

---

## Database Migration Failures

### Symptom: "Custody log table missing"

**Fix**:
```bash
# Manual migration
docker exec forensic_api python scripts/init_db.py

# Check migration status
docker exec forensic_api python apps/api/core/migrations.py status

# Force re-run migrations
docker exec forensic_api python -c "from core.migrations import run_migrations; import asyncio; asyncio.run(run_migrations())"
```

### Symptom: "Migration validation failed"

**Fix**:
- Check PostgreSQL logs for constraint violations
- Verify database user has CREATE TABLE permissions
- Check disk space: `df -h`
- Review migration logs: `docker logs forensic_api | grep migration`

---

## Rate Limiting False Positives

### Symptom: "429 Too Many Requests" but few real requests

**Fix**:
- Check Redis memory: `redis-cli INFO memory`
- Clear rate limit keys: `redis-cli KEYS "rate_limit:*" | xargs redis-cli DEL`
- Increase limits in `.env`:
  ```bash
  RATE_LIMIT_AUTHENTICATED=120
  RATE_LIMIT_ANONYMOUS=30
  ```

---

## Authentication Issues

### Symptom: "401 Unauthorized" on valid requests

**Fix**:
- Verify JWT secret hasn't changed: `echo $JWT_SECRET_KEY | sha256sum`
- Check token expiry in browser dev tools
- Clear cookies and re-login
- Verify Redis is storing session tokens

---

## File Upload Failures

### Symptom: "413 Request Entity Too Large"

**Fix**:
- The 50 MB file size limit is enforced in the backend middleware. To increase it, update the `MAX_UPLOAD_SIZE_BYTES` constant in `apps/api/api/main.py` and rebuild.
- If behind a reverse proxy, also update the proxy's client_max_body_size (nginx) or request_buffering limit.
- Check Docker memory limits.

### Symptom: "415 Unsupported Media Type"

**Fix**:
- Verify file has correct MIME type
- Check file extension matches content
- Run file validation: `file your_file.jpg`
- Ensure magic bytes match claimed type

---

## Performance Issues

### Symptom: "API response time > 5s"

**Fix**:
- Check database connection pool: `GET /api/v1/metrics` (includes `active_sessions` and error counts)
- Monitor Redis latency: `redis-cli --latency`
- Check for slow queries in PostgreSQL:
  ```sql
  SELECT query, mean_exec_time FROM pg_stat_statements ORDER BY mean_exec_time DESC LIMIT 10;
  ```
- Enable query logging in `.env`: `LOG_SLOW_QUERIES=true`

### Symptom: "Frontend bundle size too large"

**Fix**:
```bash
cd apps/web
# Install the Next.js bundle analyzer
npm install --save-dev @next/bundle-analyzer

# Add to next.config.ts: const withBundleAnalyzer = require('@next/bundle-analyzer')({ enabled: true })
ANALYZE=true npm run build
# Bundle report opens in browser automatically
```

---

## Docker Issues

### Symptom: "Container keeps restarting"

**Fix**:
```bash
# Check logs
docker logs forensic_api --tail 100

# Check resource limits
docker stats forensic_api

# Verify .env file exists
docker exec forensic_api cat /app/.env
```

### Symptom: "Port already in use"

**Fix**:
```bash
# Find process using port
lsof -i :8000

# Or change port in docker-compose.yml
ports:
  - "8001:8000"
```

---

## Redis Issues

### Symptom: "Redis connection refused"

**Fix**:
```bash
# Check Redis is running
docker ps | grep redis

# Check Redis logs
docker logs forensic_redis

# Test connection
docker exec forensic_redis redis-cli ping
```

### Symptom: "Redis out of memory"

**Fix**:
```bash
# Check memory usage
docker exec forensic_redis redis-cli INFO memory

# Clear non-persistent keys
docker exec forensic_redis redis-cli FLUSHDB

# Increase max memory in docker-compose.yml
command: redis-server --maxmemory 2gb --maxmemory-policy allkeys-lru
```

---

## PostgreSQL Issues

### Symptom: "Too many connections"

**Fix**:
```sql
-- Check connection count
SELECT count(*) FROM pg_stat_activity;

-- Check idle connections
SELECT state, count(*) FROM pg_stat_activity GROUP BY state;

-- Increase max_connections in postgresql.conf
-- Or in docker-compose.yml:
command: postgres -c max_connections=200
```

---

## Monitoring & Debugging

### Check System Health

```bash
# API health endpoint
curl http://localhost:8000/health

# Check all services
docker compose ps

# View logs
docker compose logs -f --tail=100
```

### Enable Debug Mode

```bash
# In .env
DEBUG=true
LOG_LEVEL=DEBUG

# Restart to apply
docker compose restart
```

### Distributed Tracing

If OpenTelemetry is configured:
- Check Jaeger UI: `http://localhost:16686`
- Verify traces are being exported
- Look for high-latency spans

---

## Common Error Codes

| Code | Meaning | Action |
|------|---------|--------|
| 400 | Bad Request | Check request body/format |
| 401 | Unauthorized | Re-authenticate, check token |
| 403 | Forbidden | Check permissions/role |
| 404 | Not Found | Verify endpoint/ID |
| 413 | Payload Too Large | Reduce file size or increase limit |
| 415 | Unsupported Media | Check file type |
| 429 | Too Many Requests | Wait and retry |
| 500 | Internal Server Error | Check server logs |
| 503 | Service Unavailable | Check dependencies (DB, Redis) |

---

## Getting Help

1. Check logs: `docker compose logs -f`
2. Review this guide
3. Search existing GitHub issues
4. Create new issue with:
   - Error message
   - Steps to reproduce
   - Environment details (`docker compose version`)
   - Relevant logs

---

## Debug Workflows

### Enable Debug Logging

```bash
# Set in .env
APP_ENV=development
DEBUG=true
LOG_LEVEL=DEBUG

# Rebuild and restart
docker compose up --build
```

### Debug ML Tool Failure

```bash
# 1. Check if tool has syntax errors
python -m py_compile apps/api/tools/ml_tools/splicing_detector.py

# 2. Run tool directly with test image
python apps/api/tools/ml_tools/splicing_detector.py \
  --input tests/fixtures/test_image.jpg

# 3. Test warmup
python apps/api/tools/ml_tools/splicing_detector.py --warmup

# 4. Check logs
docker compose logs backend | grep splicing_detector
```

### Debug WebSocket Issues

```bash
# 1. Check if WebSocket endpoint responds
curl -i -N -H "Connection: Upgrade" \
  -H "Upgrade: websocket" \
  http://localhost:8000/api/v1/sessions/SESSION_ID/live

# 2. Check logs for connection/disconnect
docker compose logs backend | grep "WebSocket\|ws:"

# 3. Monitor message flow
docker compose logs backend | grep "AGENT_UPDATE\|PIPELINE"
```

### Debug Database Issues

```bash
# 1. Check if Postgres is running
docker compose exec postgres pg_isready

# 2. Connect to database
docker compose exec postgres psql -U forensic_user -d forensic_council

# 3. Check tables
\dt  # List tables

# 4. Check migrations status
SELECT name, applied_at FROM migrations ORDER BY applied_at DESC;
```

### Log Levels

| Level | Usage |
|-------|-------|
| DEBUG | Detailed debugging information (development only) |
| INFO | Normal operational messages |
| WARNING | Unexpected but non-breaking conditions |
| ERROR | Errors that prevent specific operations |
| CRITICAL | System-level failures requiring immediate attention |

### Common Issues Quick Reference

| Symptom | Root Cause | Resolution |
|---------|------------|------------|
| ML tools return `available: false` | Missing dependencies or weights | Run tool with `--warmup` flag |
| WebSocket disconnects immediately | Invalid or expired JWT | Check auth header and token expiry |
| Agents hang indefinitely | ML process deadlock | Restart worker service |
| Report generation fails | Postgres connection pool exhausted | Increase `postgres_max_pool_size` |

---

## Known Issues & Limitations

### Tool Fallbacks

Several forensic tools use simplified fallback implementations when ML models are unavailable. Findings produced by fallbacks are marked with `"degraded": true` and `"fallback_reason"` in their metadata. The DegradationBanner in the frontend displays these flags.

Affected tools:
- ELA anomaly classifier (falls back to local heuristic)
- PRNU noise fingerprint (falls back to pixel-domain variance check)
- Speaker diarization (falls back to energy-based VAD)
- All audio tools with scipy-based inline fallbacks

### Compression Penalty

Social media and messaging app compression degrades pixel-level forensic signals (ELA, JPEG ghost, copy-move). The arbiter applies a compression penalty to affected tools when metadata indicates a known platform (WhatsApp, Instagram, Telegram). See `arbiter.py` `_FRAGILE_TOOLS` for the full list.

### Gemini API Rate Limits

The free Gemini API tier has rate limits that may cause 429 errors during concurrent deep analysis of multiple agents. The system uses an ordered fallback chain (`gemini-2.5-flash` → `gemini-2.0-flash` → `gemini-2.0-flash-lite`) and skips backoff on 404/429 to fail fast.

### Session State Volatility

Active investigation sessions are held in process memory. If the API server restarts, in-progress investigations are lost. Completed reports are persisted to PostgreSQL and survive restarts.
