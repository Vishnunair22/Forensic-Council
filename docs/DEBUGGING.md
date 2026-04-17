# Debugging Guide

## Enable Debug Logging

```bash
# Set in .env
APP_ENV=development
DEBUG=true
LOG_LEVEL=DEBUG

# Rebuild and restart
docker compose up --build
```

## Common Debug Workflows

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

## Log Levels

| Level | Usage |
|-------|-------|
| DEBUG | Detailed debugging information (development only) |
| INFO | Normal operational messages |
| WARNING | Unexpected but non-breaking conditions |
| ERROR | Errors that prevent specific operations |
| CRITICAL | System-level failures requiring immediate attention |

## Common Issues

| Symptom | Root Cause | Resolution |
|---------|------------|------------|
| ML tools return `available: false` | Missing dependencies or weights | Run tool with `--warmup` flag |
| WebSocket disconnects immediately | Invalid or expired JWT | Check auth header and token expiry |
| Agents hang indefinitely | ML process deadlock | Restart worker service |
| Report generation fails | Postgres connection pool exhausted | Increase `postgres_max_pool_size` |

