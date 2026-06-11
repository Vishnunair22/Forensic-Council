#!/usr/bin/env bash
# Forensic Council - Pre-Build Validation Suite

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/_platform_detect.sh"
source "$SCRIPT_DIR/_docker_utils.sh"
source "$SCRIPT_DIR/_path_utils.sh"
source "$SCRIPT_DIR/_config.sh"
source "$SCRIPT_DIR/_validate_env.sh"

MODE="${1:-dev}"
ROOT=$(get_project_root)
cd "$ROOT"

CHECKS_PASSED=0
CHECKS_FAILED=0
WARNINGS=0

validate_check() {
  local description="$1"
  shift
  local result=0

  echo -n "  $description... "

  if "$@" > /tmp/prebuild_check.log 2>&1; then
    # Check passed; still surface any WARN lines it printed (e.g. low Docker
    # memory) so they are counted and visible instead of swallowed.
    if grep -qi "warn" /tmp/prebuild_check.log 2>/dev/null; then
      echo " (warnings)"
      WARNINGS=$((WARNINGS + 1))
      grep -i "warn" /tmp/prebuild_check.log 2>/dev/null | head -3
    else
      echo ""
    fi
    CHECKS_PASSED=$((CHECKS_PASSED + 1))
  else
    # A non-zero exit is ALWAYS a failure. (Previously a failing check whose
    # output merely contained the word "warning" was downgraded to a warning,
    # letting genuinely failed gates pass pre-build validation.)
    echo " FAILED"
    CHECKS_FAILED=$((CHECKS_FAILED + 1))
    cat /tmp/prebuild_check.log 2>/dev/null | head -5
  fi
}

echo "  Pre-Build Validation Suite ($MODE mode)"
echo "  ==========================================="

echo ""
echo " 1. System Requirements"
echo "  ----------------------"
validate_check "Docker available" check_docker_available
validate_check "BuildKit available" check_buildkit_available
validate_check "Docker Compose >= $MIN_DOCKER_COMPOSE_VERSION" check_compose_version "$MIN_DOCKER_COMPOSE_VERSION"

echo ""
echo " 2. Resource Availability"
echo "  ------------------------"
if grep -q "^PRELOAD_MODELS=1" .env 2>/dev/null; then
  validate_check "Disk space (40GB)" check_disk_space "$REQUIRED_DISK_GB_FULL" "$ROOT"
else
  validate_check "Disk space (10GB)" check_disk_space "$REQUIRED_DISK_GB_MINIMAL" "$ROOT"
fi
validate_check "Docker memory (18GB)" check_docker_memory "$REQUIRED_MEMORY_GB"

echo ""
echo " 3. Environment"
echo "  --------------"
validate_check "Environment file" validate_env_exists "$ROOT/.env"
validate_check "Required variables" validate_required_vars "$ROOT/.env" "$MODE"
validate_check "LLM configuration" validate_llm_config "$ROOT/.env"

if [[ "$MODE" == "prod" ]]; then
  validate_check "Production invariants" validate_production_invariants "$ROOT/.env"
fi

echo ""
echo " 4. File Structure"
echo "  -----------------"
validate_check "Backend Dockerfile" test -f "$ROOT/apps/api/Dockerfile"
validate_check "Frontend Dockerfile" test -f "$ROOT/apps/web/Dockerfile"
validate_check "Base compose file" test -f "$ROOT/infra/docker-compose.yml"

if [[ "$MODE" == "dev" ]]; then
  validate_check "Dev overlay" test -f "$ROOT/infra/docker-compose.dev.yml"
else
  validate_check "Prod overlay" test -f "$ROOT/infra/docker-compose.prod.yml"
fi

echo ""
echo " 5. Port Availability"
echo "  --------------------"

check_port_free() {
  local port="$1"
  if (echo > /dev/tcp/127.0.0.1/"$port") 2>/dev/null; then
    if docker ps --filter "label=com.docker.compose.project=forensic-council" \
         --format "{{.Ports}}" 2>/dev/null | grep -qE ":$port->"; then
      return 0
    fi
    echo "Port $port is in use by another process"
    return 1
  fi
  return 0
}

if [[ "$MODE" == "dev" ]]; then
  for port in "${DEV_PORTS[@]}"; do
    validate_check "Port $port free" check_port_free "$port"
  done
else
  for port in "${PROD_PORTS[@]}"; do
    validate_check "Port $port free" check_port_free "$port"
  done
fi

echo ""
echo " 6. Docker Compose Config"
echo "  ------------------------"
if [[ "$MODE" == "dev" ]]; then
  validate_check "Compose config valid" bash -c "cd '$ROOT' && docker compose -f infra/docker-compose.yml -f infra/docker-compose.dev.yml --env-file .env config -q"
else
  validate_check "Compose config valid" bash -c "cd '$ROOT' && docker compose -f infra/docker-compose.yml -f infra/docker-compose.prod.yml --env-file .env config -q"
fi

echo ""
echo " 7. Platform"
echo "  -----------"

PLATFORM=$(detect_platform)
case "$PLATFORM" in
  windows)
    echo "  Platform: Windows"
    if is_docker_desktop; then
      echo "  Docker Desktop detected"
      if is_wsl2; then
        echo "  WSL 2 detected"
      else
        echo "  WSL 2 not detected - enable in Docker Desktop for best performance"
        WARNINGS=$((WARNINGS + 1))
      fi
    else
      echo "  Docker Desktop recommended for Windows"
      WARNINGS=$((WARNINGS + 1))
    fi
    ;;
  macos)
    echo "  Platform: macOS"
    if is_docker_desktop; then
      echo "  Docker Desktop detected"
    fi
    ;;
  linux)
    echo "  Platform: Linux"
    ;;
esac

echo ""
echo "  ==========================================="
echo "  Summary: Passed=$CHECKS_PASSED Failed=$CHECKS_FAILED Warnings=$WARNINGS"
echo "  ==========================================="

if [[ "$CHECKS_FAILED" -gt 0 ]]; then
  echo ""
  echo "  Pre-build validation FAILED. Fix errors above."
  exit 1
fi

if [[ "$WARNINGS" -gt 0 ]]; then
  echo ""
  echo "  Validation passed with $WARNINGS warning(s) - review above."
fi

echo "  All pre-build checks passed."
exit 0
