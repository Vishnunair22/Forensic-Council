#!/usr/bin/env bash
# Forensic Council - Platform Detection Utilities

detect_platform() {
  case "$(uname -s)" in
    Linux*)
      echo "linux"
      ;;
    Darwin*)
      echo "macos"
      ;;
    MINGW*|MSYS*|CYGWIN*)
      echo "windows"
      ;;
    *)
      echo "unknown"
      ;;
  esac
}

is_docker_desktop() {
  if docker info 2>/dev/null | grep -qi "Docker Desktop"; then
    return 0
  fi
  return 1
}

is_wsl2() {
  if grep -qi microsoft /proc/version 2>/dev/null; then
    return 0
  fi
  return 1
}

get_docker_context() {
  local platform
  platform=$(detect_platform)

  if is_docker_desktop; then
    case "$platform" in
      windows)
        if is_wsl2; then
          echo "docker-desktop-wsl2"
        else
          echo "docker-desktop-windows"
        fi
        ;;
      macos)
        echo "docker-desktop-macos"
        ;;
      linux)
        echo "docker-desktop-linux"
        ;;
    esac
  else
    echo "docker-engine-$platform"
  fi
}

is_git_bash() {
  [[ -n "$MSYSTEM" ]] && [[ "$MSYSTEM" =~ ^MINGW ]]
}

export -f detect_platform is_docker_desktop is_wsl2 get_docker_context is_git_bash
