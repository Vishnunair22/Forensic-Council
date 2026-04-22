# Pre-Deployment Checklist

## 48 Hours Before Deployment

- [ ] All pull requests merged to main
- [ ] Release notes drafted
- [ ] Changelog updated
- [ ] Version bumped in all places (pyproject.toml, package.json, main.py)

## 24 Hours Before Deployment

- [ ] Full test suite passes (unit + integration + E2E)
- [ ] Code coverage ≥ 80%
- [ ] No high-severity security warnings
- [ ] Performance baseline established
- [ ] Staging deployment tested

## 4 Hours Before Deployment (Pre-flight)

### Code Quality
- [ ] `pytest tests/ --cov` — ≥80% coverage
- [ ] `ruff check apps/api/` — No violations
- [ ] `ruff format --check apps/api/` — Code formatted
- [ ] `npm run lint` (frontend) — No ESLint errors
- [ ] `npm run test:coverage` (frontend) — ≥70% coverage

### Configuration
- [ ] `.env.prod` created with all required vars
- [ ] Secrets rotated (SIGNING_KEY, JWT_SECRET_KEY)
- [ ] Database backups tested
- [ ] SSL certificate valid
- [ ] Firewall rules configured

### Infrastructure
- [ ] Docker images built: `docker compose build`
- [ ] Health check endpoints responding
- [ ] ML tools warm up: `/api/v1/health/ml-tools`
- [ ] Database migrations complete: `scripts/init_db.py`
- [ ] Redis cache cleared: `docker compose exec redis redis-cli FLUSHALL`

### Smoke Tests

```bash
# 1. Start stack
docker compose -f infra/docker-compose.prod.yml up -d

# 2. Wait for health
sleep 30

# 3. Verify endpoints
curl -s http://localhost:8000/health | jq '.status'
curl -s http://localhost:8000/api/v1/health/ml-tools | jq '.tools_ready'

# 4. Test auth
curl -s -X POST http://localhost:8000/api/v1/auth/login \
  -d 'username=investigator&password=DEMO_PASSWORD' | jq '.access_token'

# 5. Test upload
curl -F "file=@test_image.jpg" -H "Authorization: Bearer $TOKEN" \
  http://localhost:8000/api/v1/investigate | jq '.session_id'
```

## During Deployment

- [ ] Team notified in Slack
- [ ] On-call engineer monitoring
- [ ] Rollback procedure ready
- [ ] Customer success team on standby

## Post-Deployment (First Hour)

- [ ] All health checks green
- [ ] No error rate spikes in metrics
- [ ] WebSocket connections stable
- [ ] Investigations completing successfully
- [ ] No security alerts

## Post-Deployment (First 24 Hours)

- [ ] Monitor error logs continuously
- [ ] Verify database backups captured
- [ ] Check performance metrics
- [ ] Update status page if applicable
- [ ] Document any issues encountered

