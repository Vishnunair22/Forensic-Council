# Forensic Council - Troubleshooting Guide

Quick diagnostic guide for common issues. For detailed Docker commands, see [infra/DOCKER_BUILD.md](../infra/DOCKER_BUILD.md).

## Emergency Diagnostics

```bash
bash scripts/troubleshoot.sh
```

This checks Docker version, container states, unhealthy logs, and volume sizes.

## Problem Decision Tree

### 1. Build Failing?

**Error: `SIGNING_KEY must be set`**
```bash
bash infra/generate_production_keys.sh --update
```

**Error: `port is already allocated` / `bind: address already in use`**
Find the conflicting process:
```bash
# Linux/macOS:
sudo lsof -i :80
# Windows PowerShell:
netstat -ano | findstr :80
```
Workaround: Access directly via http://localhost:3000 (frontend) or http://localhost:8000 (API).

**Error: `no space left on device`**
ML models require ~40GB with PRELOAD_MODELS=1. Check space and either free up space or set:
```bash
echo "PRELOAD_MODELS=0" >> .env
```

**Error: `invalid mount path` (Windows)**
Docker Desktop cannot access the project directory:
- Docker Desktop \u2192 Settings \u2192 Resources \u2192 File Sharing
- Add the drive containing your project (e.g., C:\)
- Restart Docker Desktop

### 2. Container Unhealthy?

**Postgres unhealthy**
```bash
docker compose -f infra/docker-compose.yml --env-file .env logs --tail 50 postgres
```
Linux fix for volume permissions:
```bash
docker compose down
sudo chown -R 999:999 postgres_volume_mount_path
docker compose up -d
```

**Backend or Worker unhealthy**
```bash
docker compose -f infra/docker-compose.yml --env-file .env logs --tail 100 backend
# or
docker compose -f infra/docker-compose.yml --env-file .env logs --tail 100 worker
```

Common issues:
- "ML cache incomplete": Wait 15-40 min for model download, or set PRELOAD_MODELS=1 and rebuild
- "Connection refused": Check postgres/redis health
- "Error loading ML model": Force re-download with `docker compose exec backend python scripts/model_pre_download.py --force`

### 3. Hot Reload Not Working?

**Backend changes not reflected:** Ensure using dev overlay:
```bash
bash scripts/dev.sh
```

**Worker changes not reflected:** Worker doesn't auto-reload - restart it:
```bash
bash scripts/dev-restart-worker.sh
```

**Frontend (Next.js) changes not reflecting:**
```bash
docker compose -f infra/docker-compose.yml -f infra/docker-compose.dev.yml --env-file .env restart frontend
```

### 4. API Returning Errors?

**502 Bad Gateway (via Caddy):** Backend not healthy:
```bash
curl http://localhost:8000/health
docker compose logs caddy
```

**401 Unauthorized:** JWT expired - re-login or check JWT_ACCESS_TOKEN_EXPIRE_MINUTES in .env

**500 Internal Server Error:** Check backend logs:
```bash
docker compose -f infra/docker-compose.yml --env-file .env logs --tail 100 backend
```

### 5. Can't Access Frontend?

**http://localhost shows nothing:** Caddy not started:
```bash
docker compose -f infra/docker-compose.yml --env-file .env up -d caddy
```

**http://localhost:3000 works but http://localhost doesn't:** Caddy routing misconfigured:
```bash
docker compose -f infra/docker-compose.yml --env-file .env exec caddy cat /etc/caddy/Caddyfile
docker compose restart caddy
```

### 6. Production Issues?

**Let's Encrypt certificate not provisioning:**
- Verify domain resolves: `nslookup your-domain.com`
- Ensure ports 80 and 443 are open
- Check Caddy logs: `docker compose logs --tail 50 caddy`

**Production validation failing:** Run:
```bash
bash infra/validate_production_readiness.sh
```

## Advanced Diagnostics

```bash
# Full container state dump
bash scripts/troubleshoot.sh

# Check ML model cache
docker compose -f infra/docker-compose.yml --env-file .env exec backend python scripts/model_cache_check.py --strict

# Interactive debugging
docker compose -f infra/docker-compose.yml --env-file .env exec backend bash

# Verify merged compose config
docker compose -f infra/docker-compose.yml -f infra/docker-compose.dev.yml --env-file .env config
```

## Nuclear Reset

```bash
docker compose -f infra/docker-compose.yml --env-file .env down -v
docker builder prune -f
bash scripts/clean_project.sh --deep
bash scripts/dev.sh
```

This deletes ALL data (databases, evidence, ML models). First startup will take 20-40 minutes.
