#!/usr/bin/env bash
# Forensic Council - Unified Environment Validation

validate_env_exists() {
  local env_file="${1:-.env}"

  if [[ ! -f "$env_file" ]]; then
    echo "  Environment file not found: $env_file"
    echo "   Copy from template: cp .env.example $env_file"
    return 1
  fi

  if file "$env_file" 2>/dev/null | grep -q "CRLF"; then
    echo "  WARNING: $env_file has Windows line endings (CRLF)"
    echo "   This may cause parse errors. Convert to LF."
  fi

  return 0
}

validate_required_vars() {
  local env_file="${1:-.env}"
  local mode="${2:-dev}"

  local REQUIRED_VARS=(
    SIGNING_KEY
    JWT_SECRET_KEY
    POSTGRES_PASSWORD
    REDIS_PASSWORD
    QDRANT_API_KEY
    BOOTSTRAP_ADMIN_PASSWORD
    BOOTSTRAP_INVESTIGATOR_PASSWORD
    DEMO_PASSWORD
    METRICS_SCRAPE_TOKEN
    GEMINI_API_KEY_POLICY_OK
  )

  if [[ "$mode" == "prod" ]]; then
    REQUIRED_VARS+=(
      DOMAIN
      CADDY_SITE_ADDRESS
      ACME_EMAIL
    )
  fi

  local failed=0

  for var in "${REQUIRED_VARS[@]}"; do
    local value
    value=$(grep "^${var}=" "$env_file" | cut -d= -f2- || echo "")

    if [[ -z "$value" ]]; then
      echo "  $var is not set in $env_file"
      failed=1
      continue
    fi

    case "$value" in
      __REPLACE_ME*|__PASTE_*|*placeholder*|*Placeholder*|*PLACEHOLDER*|change-me|changeme|change_me)
        echo "  $var is still a placeholder: $value"
        failed=1
        ;;
    esac
  done

  if [[ "$failed" -eq 1 ]]; then
    echo ""
    echo "   Generate strong secrets with:"
    echo "   bash infra/generate_production_keys.sh --update"
    return 1
  fi

  return 0
}

validate_production_invariants() {
  local env_file="${1:-.env}"

  local app_env
  app_env=$(grep "^APP_ENV=" "$env_file" | cut -d= -f2-)
  if [[ "$app_env" != "production" ]]; then
    echo "  APP_ENV must be 'production' (got: '$app_env')"
    return 1
  fi

  local domain
  domain=$(grep "^DOMAIN=" "$env_file" | cut -d= -f2-)
  if [[ "$domain" == "localhost" ]]; then
    echo "  DOMAIN cannot be 'localhost' in production"
    return 1
  fi

  local signing_key jwt_key
  signing_key=$(grep "^SIGNING_KEY=" "$env_file" | cut -d= -f2-)
  jwt_key=$(grep "^JWT_SECRET_KEY=" "$env_file" | cut -d= -f2-)
  if [[ "$signing_key" == "$jwt_key" ]]; then
    echo "  SIGNING_KEY must differ from JWT_SECRET_KEY"
    return 1
  fi

  if [[ ${#signing_key} -lt 32 ]]; then
    echo "  SIGNING_KEY must be at least 32 characters (got: ${#signing_key})"
    return 1
  fi

  local research_models
  research_models=$(grep "^ENABLE_RESEARCH_MODELS=" "$env_file" | cut -d= -f2-)
  if [[ "$research_models" != "false" ]] && [[ -n "$research_models" ]]; then
    echo "  ENABLE_RESEARCH_MODELS must be 'false' in production (research-only licenses)"
    return 1
  fi

  local cors
  cors=$(grep "^CORS_ALLOWED_ORIGINS=" "$env_file" | cut -d= -f2-)
  if echo "$cors" | grep -qw "localhost"; then
    echo "  CORS_ALLOWED_ORIGINS contains 'localhost' - not valid for production"
    return 1
  fi

  local investigator_pwd demo_pwd
  investigator_pwd=$(grep "^BOOTSTRAP_INVESTIGATOR_PASSWORD=" "$env_file" | cut -d= -f2-)
  demo_pwd=$(grep "^DEMO_PASSWORD=" "$env_file" | cut -d= -f2-)
  if [[ "$investigator_pwd" != "$demo_pwd" ]]; then
    echo "  BOOTSTRAP_INVESTIGATOR_PASSWORD must match DEMO_PASSWORD"
    return 1
  fi

  return 0
}

validate_llm_config() {
  local env_file="${1:-.env}"

  local llm_provider
  llm_provider=$(grep "^LLM_PROVIDER=" "$env_file" | cut -d= -f2- || echo "none")

  if [[ "$llm_provider" != "none" ]]; then
    local llm_key
    llm_key=$(grep "^LLM_API_KEY=" "$env_file" | cut -d= -f2- || echo "")

    if [[ -z "$llm_key" ]] || [[ "$llm_key" == __PASTE_* ]]; then
      echo "  LLM_PROVIDER=$llm_provider but LLM_API_KEY is not set"
      echo "   Either set LLM_API_KEY or change LLM_PROVIDER to 'none'"
      return 1
    fi
  fi

  local policy_ok
  policy_ok=$(grep "^GEMINI_API_KEY_POLICY_OK=" "$env_file" | cut -d= -f2-)
  case "$policy_ok" in
    true|false)
      ;;
    *)
      echo "  GEMINI_API_KEY_POLICY_OK must be exactly 'true' or 'false' (got: '$policy_ok')"
      echo "   Set to 'true' only after reading https://ai.google.dev/terms"
      return 1
      ;;
  esac

  return 0
}

validate_env() {
  local env_file="${1:-.env}"
  local mode="${2:-dev}"

  validate_env_exists "$env_file" || return 1
  validate_required_vars "$env_file" "$mode" || return 1
  validate_llm_config "$env_file" || return 1

  if [[ "$mode" == "prod" ]]; then
    validate_production_invariants "$env_file" || return 1
  fi

  return 0
}

export -f validate_env_exists validate_required_vars validate_production_invariants
export -f validate_llm_config validate_env
