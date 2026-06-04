#!/bin/sh
# Forensic Council - Model Download with Retry Logic
# Centralizes retry logic for consistency across Dockerfile and entrypoint

set -e

RETRY_COUNT="${MODEL_DOWNLOAD_RETRIES:-3}"
RETRY_DELAY="${MODEL_DOWNLOAD_RETRY_DELAY:-30}"
STRICT="${1:-}"

log() {
  echo "[model-download] $*"
}

log "Starting model download (max $RETRY_COUNT attempts)"

for attempt in $(seq 1 "$RETRY_COUNT"); do
  log "Attempt $attempt/$RETRY_COUNT..."

  if python scripts/model_pre_download.py $STRICT; then
    log "  Model download successful on attempt $attempt"
    exit 0
  fi

  # NB: $? after the `if` reflects the compound, not python's exit code, so we
  # report the attempt rather than a misleading code.
  log "  Download attempt $attempt failed"

  if [ "$attempt" -lt "$RETRY_COUNT" ]; then
    log "Retrying in ${RETRY_DELAY}s..."
    sleep "$RETRY_DELAY"
  fi
done

log "FATAL: Model download failed after $RETRY_COUNT attempts"
exit 1
