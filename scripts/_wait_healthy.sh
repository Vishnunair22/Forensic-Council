#!/usr/bin/env bash
set -euo pipefail

MODE="${1:-dev}"
end=$((SECONDS + 900))

EXPECTED_DEV=(
  forensic_redis
  forensic_qdrant
  forensic_postgres
  forensic_api
  forensic_worker
  forensic_ui
  forensic_caddy
  forensic_prometheus
)

if [[ "$MODE" == "prod" ]]; then
  EXPECTED=("${EXPECTED_DEV[@]}")
else
  EXPECTED=("${EXPECTED_DEV[@]}")
fi

while [ "$SECONDS" -lt "$end" ]; do
  bad=()

  for name in "${EXPECTED[@]}"; do
    if ! docker inspect "$name" >/dev/null 2>&1; then
      bad+=("$name missing")
      continue
    fi

    state="$(docker inspect -f '{{.State.Status}}' "$name")"
    health="$(docker inspect -f '{{if .State.Health}}{{.State.Health.Status}}{{else}}no-healthcheck{{end}}' "$name")"

    if [[ "$state" != "running" ]]; then
      bad+=("$name state=$state")
      continue
    fi

    if [[ "$health" == "starting" || "$health" == "unhealthy" ]]; then
      bad+=("$name health=$health")
    fi
  done

  if [ "${#bad[@]}" -eq 0 ]; then
    echo "All expected forensic containers are running and healthy"
    exit 0
  fi

  printf 'Waiting... %s\n' "${bad[*]}"
  sleep 10
done

echo "Timeout waiting for healthy containers"
docker ps -a --filter "name=forensic_" --format 'table {{.Names}}\t{{.Status}}\t{{.Ports}}'
exit 1