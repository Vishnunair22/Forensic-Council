# Monitoring & Alerting — Forensic Council

## Health Check Endpoint

```
GET /health
```

Returns JSON with status of all infrastructure dependencies:

```json
{
  "status": "healthy",
  "environment": "production",
  "active_sessions": 3,
  "checks": {
    "migrations": "ok",
    "postgres": "ok",
    "redis": "ok",
    "qdrant": "ok"
  }
}
```

Returns **200** when all dependencies are healthy, **503** when any is degraded.

---

## Prometheus Metrics

```
GET /api/v1/metrics
```

Requires `METRICS_SCRAPE_TOKEN` in `.env`. Returns Prometheus exposition format.

---

## Docker Health Checks

All services have built-in health checks in `docker-compose.yml`:

| Service    | Interval | Retries | Check                     |
|------------|----------|---------|---------------------------|
| postgres   | 10s      | 5       | `pg_isready`              |
| redis      | 5s       | 5       | `redis-cli ping`          |
| qdrant     | 10s      | 3       | HTTP GET `/healthz`       |
| caddy      | 30s      | 3       | `wget localhost:2019`     |
| backend    | 30s      | 3       | `curl /health`            |

---

## Prometheus Scrape Config

Add to your `prometheus.yml`:

```yaml
scrape_configs:
  - job_name: "forensic-council-backend"
    scrape_interval: 15s
    metrics_path: /api/v1/metrics
    authorization:
      credentials: "${METRICS_SCRAPE_TOKEN}"
    static_configs:
      - targets: ["localhost:8000"]
```

---

## Recommended Alerts

### Critical (page immediately)

```yaml
# Backend is down
- alert: BackendDown
  expr: up{job="forensic-council-backend"} == 0
  for: 1m

# PostgreSQL connection failures
- alert: PostgresDown
  expr: forensic_council_postgres_errors_total > 0
  for: 30s

# Chain-of-custody logging failures
- alert: CustodyLoggingFailed
  expr: rate(forensic_custody_errors_total[5m]) > 0
  for: 1m
```

### Warning (investigate within 1 hour)

```yaml
# Investigation timeout rate
- alert: HighTimeoutRate
  expr: rate(forensic_investigation_timeouts_total[15m]) > 0.1
  for: 5m

# Agent error rate
- alert: HighAgentErrors
  expr: rate(forensic_agent_errors_total[15m]) > 5
  for: 5m

# JWT validation failures (possible brute force)
- alert: JWTValidationSpike
  expr: rate(forensic_jwt_failures_total[5m]) > 10
  for: 2m
```

---

## Log Aggregation

Structured JSON logs are emitted to stdout. Configure your Docker logging driver:

```yaml
# docker-compose.yml
services:
  backend:
    logging:
      driver: "json-file"
      options:
        max-size: "10m"
        max-file: "5"
```

For centralized logging, use one of:
- **ELK Stack**: `docker.elastic.co/beats/filebeat` sidecar
- **Datadog**: `DD_LOGS_ENABLED=true` in agent container
- **Loki**: Promtail agent scraping Docker logs

---

## Grafana Dashboard Template

### Critical Metrics Pane
| Panel | Query | Thresholds |
|-------|-------|------------|
| Backend Uptime | `up{job="forensic-council-backend"}` | 0 = down |
| Investigation Success Rate | `rate(forensic_investigations_total{status="success"}) / rate(forensic_investigations_total)` | < 95% = warning, < 90% = critical |
| Avg Investigation Duration | `rate(forensic_investigation_duration_seconds_sum[5m]) / rate(forensic_investigation_duration_seconds_count[5m])` | > 300s = warning, > 600s = critical |
| Chain-of-Custody Errors | `increase(forensic_custody_errors_total[1h])` | > 0 = critical |
| Agent Failure Rate | `rate(forensic_agent_errors_total[5m]) by (agent_id)` | > 5/min = warning |
| JWT Validation Failures | `rate(forensic_jwt_failures_total[5m])` | > 10/min = critical (brute force) |
| Active Sessions | `forensic_active_sessions` | > 50 = capacity warning |

### Recommended Dashboard Layout
```
Row 1: [Uptime] [Success Rate] [Avg Duration] [Active Sessions]
Row 2: [Custody Errors] [Agent Failures (per agent)] [JWT Failures]
Row 3: [Investigation Duration Histogram] [Request Rate by Endpoint]
```
