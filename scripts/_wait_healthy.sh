#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
source "$SCRIPT_DIR/_docker_utils.sh"
source "$SCRIPT_DIR/_path_utils.sh"

MODE="${1:-dev}"
ROOT=$(get_project_root)

COMPOSE_FILES=(-f "$ROOT/infra/docker-compose.yml")
if [[ "$MODE" == "dev" ]]; then
  COMPOSE_FILES+=(-f "$ROOT/infra/docker-compose.dev.yml")
else
  COMPOSE_FILES+=(-f "$ROOT/infra/docker-compose.prod.yml")
fi
COMPOSE_FILES+=(--env-file "$ROOT/.env")

SERVICES=(redis qdrant postgres backend worker frontend caddy prometheus)

end=$((SECONDS + 900))

while [ "$SECONDS" -lt "$end" ]; do
  bad=()

  for service in "${SERVICES[@]}"; do
    if ! is_service_healthy "$service" "${COMPOSE_FILES[@]}"; then
      container=$(get_container_name "$service" "${COMPOSE_FILES[@]}")
      if [[ -z "$container" ]]; then
        bad+=("$service: container not found")
      else
        state=$(docker inspect --format '{{.State.Status}}' "$container")
        health=$(docker inspect --format '{{if .State.Health}}{{.State.Health.Status}}{{else}}no-check{{end}}' "$container")
        bad+=("$service($container): state=$state health=$health")
      fi
    fi
  done

  if [ "${#bad[@]}" -eq 0 ]; then
    echo "All services are running and healthy"
    exit 0
  fi

  printf 'Waiting for services... %s\n' "${bad[*]}"
  sleep 10
done

echo "Timeout waiting for healthy services"
docker compose "${COMPOSE_FILES[@]}" ps
exit 1
