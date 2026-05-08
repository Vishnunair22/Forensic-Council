#!/usr/bin/env bash
set -euo pipefail
end=$((SECONDS + 900))
while [ $SECONDS -lt $end ]; do
  bad=$(docker ps --filter "name=forensic_" --format '{{.Names}} {{.Status}}' | grep -E '(unhealthy|starting)' || true)
  [ -z "$bad" ] && { echo "All forensic_* containers healthy"; exit 0; }
  echo "Waiting… $bad"; sleep 10
done
echo "Timeout"; docker ps --filter "name=forensic_"; exit 1
