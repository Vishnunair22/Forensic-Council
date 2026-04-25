# Deployment Migration Guide

This document outlines migration paths from the current `docker-compose` deployment to container orchestrators supporting zero-downtime updates.

## Current State

- **Deployment**: `docker compose` (standalone)
- **Limitations**: No rolling updates, no zero-downtime deploys, manual health checks

## Why Migrate?

| Feature | docker-compose | Swarm | Kubernetes |
|---------|-------------|-------|------------|
| Rolling updates | ❌ | ✅ | ✅ |
| Auto-healing | ❌ | ✅ | ✅ |
| Zero-downtime | ❌ | ✅ | ✅ |
| Secrets management | env files | secrets | secrets/vault |
| Horizontal scaling | manual | scale 命令 | HPA |

## Option 1: Docker Swarm

Deploy using `docker stack deploy` with update config:

```yaml
# docker-compose.swarm.yml
services:
  backend:
    deploy:
      replicas: 2
      update_config:
        parallelism: 1
        delay: 10s
        failure_action: rollback
      restart_policy:
        condition: on-failure
        delay: 5s
        max_attempts: 3
```

Deploy:
```bash
docker stack deploy -c docker-compose.yml -c docker-compose.swarm.yml forensic
```

### Secrets in Swarm

```bash
echo "mysecret" | docker secret create postgres_password -
docker secret create jwt_secret_key -
```

## Option 2: Kubernetes (Recommended)

### Required Resources

1. **Deployment** - backend and worker with rolling strategy
2. **Service** - ClusterIP for internal communication  
3. **Ingress** - Caddy or nginx-ingress for external
4. **ConfigMap** - non-secret config
5. **Secret** - sensitive data
6. **PersistentVolumeClaim** - evidence data

### Example Deployment

```yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: backend
spec:
  replicas: 2
  strategy:
    type: RollingUpdate
    rollingUpdate:
      maxSurge: 1
      maxUnavailable: 0
  template:
    spec:
      containers:
      - name: backend
        image: forensic-council/backend:latest
        readinessProbe:
          httpGet:
            path: /health
            port: 8000
          initialDelaySeconds: 30
          periodSeconds: 5
        livenessProbe:
          httpGet:
            path: /health
            port: 8000
          initialDelaySeconds: 60
          periodSeconds: 10
        envFrom:
        - configMapRef:
            name: forensic-config
        - secretRef:
            name: forensic-secrets
```

### Secrets Migration

```bash
# Create secrets from .env
kubectl create secret generic forensic-secrets \
  --from-literal=POSTGRES_PASSWORD="$(grep POSTGRES_PASSWORD .env | cut -d= -f2)" \
  --from-literal=JWT_SECRET_KEY="$(grep JWT_SECRET_KEY .env | cut -d= -f2)" \
  --from-literal=SIGNING_KEY="$(grep SIGNING_KEY .env | cut -d= -f2)"
```

## Migration Checklist

- [ ] Run evidence backup
- [ ] Export .env to ConfigMap/Secret
- [ ] Create PVC for evidence_data volume
- [ ] Test restore from backup with new deployment
- [ ] Verify health checks pass
- [ ] Update CI/CD pipelines
- [ ] Document new deployment commands