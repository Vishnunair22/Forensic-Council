# Maintenance & Operations â€” Forensic Council

This guide covers the necessary procedures to maintain a production-hardened Forensic Council (v1.3.0) environment.

---

## 1. Automated Cleanup Service

The system includes a background cleanup task managed by `worker.py`. 

### Configuration
Adjust cleanup intensity in `.env`:
- `TEMPORARY_STORAGE_TTL_HOURS=24`: How long raw evidence artifacts persist in `/app/storage/evidence` before deletion.
- `SESSION_CACHE_TTL_HOURS=48`: How long Redis-backed working memory for inactive sessions is retained.

### Manual Cleanup
If storage reaches critical levels:
```bash
# Force cleanup of evidence older than 24h
docker exec -it forensic-backend python tools/maintenance_cleanup.py --age 24
```

---

## 2. ML Tool Warming

Deep Analysis agents (v1.3.0) utilize heavy ML models (YOLOv11, DeepFace, Whisper). Startup time can be significant during first-run.

### Pre-warming Models
To avoid latency spikes on the first investigation:
```bash
# Triggers model downloads and JIT compilation
docker exec -it forensic-backend python core/ml_prepro.py --warm-all
```

---

## 3. Log Rotation

 Forensic Council generates high-volume structured JSON logs.

### System Logs
Docker handles rotation via `infra/docker-compose.yml`:
```yaml
logging:
  driver: "json-file"
  options:
    max-size: "100m"
    max-file: "5"
```

### Forensic Ledger (Immutable)
The PostgreSQL `chain_of_custody` table is **APPEND-ONLY**. Never truncate this table in a production environment as it will break the cryptographic hash chain.
- **Vacuuming**: Run `VACUUM ANALYZE chain_of_custody;` monthly to maintain query performance.
- **Archiving**: To archive old cases, use the `tools/export_case.py` script which generates a signed ZIP containing the evidence and hash-ledger.

---

## 4. Database Maintenance

### Postgres
Backup the database daily:
```bash
docker exec forensic-db pg_dump -U $DB_USER $DB_NAME > backups/db_$(date +%F).sql
```

### Qdrant (Episodic Memory)
Qdrant snapshots ensure vector persistence:
```bash
# Create a snapshot
curl -X POST http://localhost:6333/collections/forensic_signatures/snapshots
```

---

## 5. Health Monitoring

Monitor the `/health` endpoint for infrastructure readiness:
- `migration_status`: `true` (Alembic up to date)
- `redis_ready`: `true`
- `qdrant_ready`: `true`
- `ml_tools_warmed`: `true` (Indicates models are in RAM/VRAM)

