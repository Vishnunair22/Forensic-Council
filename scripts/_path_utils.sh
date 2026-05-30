#!/usr/bin/env bash
# Forensic Council - Path Utilities

source "$(dirname "${BASH_SOURCE[0]}")/_platform_detect.sh"

normalize_path_for_docker() {
  local path="$1"
  local platform
  platform=$(detect_platform)

  case "$platform" in
    windows)
      if [[ "$path" =~ ^/([a-z])/ ]]; then
        local drive="${BASH_REMATCH[1]}"
        path="${drive^^}:${path:2}"
      fi
      echo "$path" | tr '\\' '/'
      ;;
    *)
      echo "$path"
      ;;
  esac
}

get_project_root() {
  local script_dir
  script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
  local root
  root="$(cd "$script_dir/.." && pwd)"
  normalize_path_for_docker "$root"
}

validate_path() {
  local path="$1"
  local description="${2:-path}"

  if [[ ! -e "$path" ]]; then
    echo "ERROR: $description does not exist: $path" >&2
    return 1
  fi

  if [[ ! -r "$path" ]]; then
    echo "ERROR: $description is not readable: $path" >&2
    return 1
  fi

  return 0
}

export -f normalize_path_for_docker get_project_root validate_path
