#!/usr/bin/env bash
set -e
echo "=== docker version ===";          docker --version
echo "=== compose version ===";          docker compose version
echo "=== container states ===";         docker ps --filter "name=forensic_" --format 'table {{.Names}}\t{{.Status}}\t{{.Ports}}'
echo "=== unhealthy logs (tail 60) ===";
for c in $(docker ps -aq --filter "name=forensic_"); do
  name=$(docker inspect --format '{{.Name}}' "$c" | sed 's#^/##')
  health=$(docker inspect --format '{{.State.Health.Status}}' "$c" 2>/dev/null || echo n/a)
  echo "--- $name ($health) ---"
  [ "$health" == "unhealthy" ] && docker logs --tail 60 "$c"
done
echo "=== volume sizes ==="; docker system df -v | grep forensic-council || true
