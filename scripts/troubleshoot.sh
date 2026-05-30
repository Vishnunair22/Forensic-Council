#!/usr/bin/env bash
set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

echo "=== docker version ===";          docker --version
echo "=== compose version ===";          docker compose version
echo "=== compose project containers ==="
docker compose -f "$ROOT/infra/docker-compose.yml" ps --format 'table {{.Name}}\t{{.Status}}\t{{.Ports}}' 2>/dev/null || \
  docker ps --filter "label=com.docker.compose.project=forensic-council" --format 'table {{.Names}}\t{{.Status}}\t{{.Ports}}'
echo "=== unhealthy logs (tail 60) ==="
for c in $(docker ps -aq --filter "label=com.docker.compose.project=forensic-council"); do
  name=$(docker inspect --format '{{.Name}}' "$c" | sed 's#^/##')
  health=$(docker inspect --format '{{.State.Health.Status}}' "$c" 2>/dev/null || echo n/a)
  echo "--- $name ($health) ---"
  [ "$health" = "unhealthy" ] && docker logs --tail 60 "$c"
done
echo "=== volume sizes ==="; docker system df -v | grep forensic-council || true
