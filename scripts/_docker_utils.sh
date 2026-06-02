#!/usr/bin/env bash
# Forensic Council - Docker Utilities

source "$(dirname "${BASH_SOURCE[0]}")/_platform_detect.sh"

check_docker_available() {
  if ! command -v docker >/dev/null 2>&1; then
    echo "ERROR: docker is not installed or not in PATH" >&2
    echo "  Install from: https://docs.docker.com/get-docker/" >&2
    return 1
  fi

  if ! docker info >/dev/null 2>&1; then
    echo "ERROR: Docker daemon is not running" >&2
    local platform
    platform=$(detect_platform)
    case "$platform" in
      windows|macos)
        echo "  Start Docker Desktop and try again" >&2
        ;;
      linux)
        echo "  Start Docker: sudo systemctl start docker" >&2
        ;;
    esac
    return 1
  fi

  if ! docker compose version >/dev/null 2>&1; then
    echo "ERROR: docker compose plugin not available" >&2
    echo "  Install from: https://docs.docker.com/compose/install/" >&2
    return 1
  fi

  return 0
}

check_buildkit_available() {
  if ! docker buildx version >/dev/null 2>&1; then
    echo "ERROR: BuildKit (docker buildx) not available" >&2
    echo "  BuildKit is required for cache mounts and multi-stage builds" >&2
    echo "  Upgrade to Docker 23+ or enable BuildKit manually" >&2
    return 1
  fi
  return 0
}

get_compose_version() {
  docker compose version --short 2>/dev/null || \
    docker compose version | grep -oE "[0-9]+\.[0-9]+\.[0-9]+" | head -n1
}

check_compose_version() {
  local min_version="$1"
  local current_version
  current_version=$(get_compose_version)

  if [[ -z "$current_version" ]]; then
    echo "ERROR: Could not determine docker compose version" >&2
    return 1
  fi

  local min_major min_minor min_patch
  IFS='.' read -r min_major min_minor min_patch <<< "$min_version"

  local cur_major cur_minor cur_patch
  IFS='.' read -r cur_major cur_minor cur_patch <<< "$current_version"

  if (( cur_major < min_major )) || \
     (( cur_major == min_major && cur_minor < min_minor )); then
    echo "ERROR: docker compose version $current_version is too old" >&2
    echo "  Required: >= $min_version" >&2
    echo "  Upgrade: https://docs.docker.com/compose/install/" >&2
    return 1
  fi

  return 0
}

check_disk_space() {
  local required_gb="$1"
  local path="${2:-.}"

  local available_kb
  if command -v df >/dev/null 2>&1; then
    available_kb=$(df "$path" | tail -1 | awk '{print $4}')
  else
    echo "WARNING: Cannot check disk space (df not available)" >&2
    return 0
  fi

  local available_gb=$((available_kb / 1024 / 1024))

  if (( available_gb < required_gb )); then
    echo "ERROR: Insufficient disk space" >&2
    echo "  Required: ${required_gb}GB" >&2
    echo "  Available: ${available_gb}GB" >&2
    return 1
  fi

  echo "  Disk: ${available_gb}GB available (${required_gb}GB required)"
  return 0
}

check_docker_memory() {
  local required_gb="$1"

  local total_mem
  total_mem=$(docker info --format '{{.MemTotal}}' 2>/dev/null)

  if [[ -z "$total_mem" ]] || [[ "$total_mem" -eq 0 ]]; then
    echo "WARNING: Cannot determine Docker memory limit" >&2
    return 0
  fi

  local total_gb=$((total_mem / 1024 / 1024 / 1024))

  if (( total_gb < required_gb )); then
    echo "WARNING: Docker memory may be insufficient" >&2
    echo "  Required: ${required_gb}GB" >&2
    echo "  Allocated: ${total_gb}GB" >&2

    if is_docker_desktop; then
      local platform
      platform=$(detect_platform)
      case "$platform" in
        windows|macos)
          echo "  Increase in Docker Desktop: Settings -> Resources -> Memory" >&2
          ;;
      esac
    fi

    return 0
  fi

  echo "  Memory: ${total_gb}GB allocated (${required_gb}GB required)"
  return 0
}

get_container_name() {
  local service="$1"
  shift
  local compose_files=("$@")

  docker compose "${compose_files[@]}" ps -q "$service" 2>/dev/null | \
    xargs -r docker inspect --format '{{.Name}}' 2>/dev/null | \
    sed 's#^/##'
}

get_all_container_names() {
  local compose_files=("$@")

  docker compose "${compose_files[@]}" ps -q 2>/dev/null | \
    xargs -r docker inspect --format '{{.Name}}' 2>/dev/null | \
    sed 's#^/##'
}

is_service_healthy() {
  local service="$1"
  shift
  local compose_files=("$@")

  local container
  container=$(get_container_name "$service" "${compose_files[@]}")

  if [[ -z "$container" ]]; then
    return 1
  fi

  local health
  health=$(docker inspect --format '{{if .State.Health}}{{.State.Health.Status}}{{else}}no-healthcheck{{end}}' "$container" 2>/dev/null)

  [[ "$health" == "healthy" ]] || [[ "$health" == "no-healthcheck" ]]
}

export -f check_docker_available check_buildkit_available get_compose_version
export -f check_compose_version check_disk_space check_docker_memory
export -f get_container_name get_all_container_names is_service_healthy
