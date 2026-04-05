# Troubleshooting Guide

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
- Pre-download models: `python backend/scripts/model_pre_download.py`
- Check `/tmp/model_download.log`
- Increase Docker memory limit to 8GB
- Verify internet connectivity from container

### Symptom: "ML tool initialization failed"

**Fix**:
```bash
# Check model cache
docker exec forensic_api ls -la /tmp/ml_models/

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
docker exec forensic_api python backend/core/migrations.py status

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

### Symptom: "CSRF token missing or invalid"

**Fix**:
- Ensure frontend sends `X-CSRF-Token` header
- Check cookie domain matches your site
- Verify `credentials: 'include'` in fetch calls
- Clear browser cookies

---

## File Upload Failures

### Symptom: "413 Request Entity Too Large"

**Fix**:
- Increase upload limit in `.env`:
  ```bash
  MAX_UPLOAD_SIZE_MB=100
  ```
- Update nginx/proxy settings if behind reverse proxy
- Check Docker memory limits

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
- Check database connection pool: `GET /api/v1/metrics/pool-status`
- Monitor Redis latency: `redis-cli --latency`
- Check for slow queries in PostgreSQL:
  ```sql
  SELECT query, mean_exec_time FROM pg_stat_statements ORDER BY mean_exec_time DESC LIMIT 10;
  ```
- Enable query logging in `.env`: `LOG_SLOW_QUERIES=true`

### Symptom: "Frontend bundle size too large"

**Fix**:
```bash
cd frontend
npm run build -- --analyze
# Check for oversized dependencies
npx webpack-bundle-analyzer .next/stats.json
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
