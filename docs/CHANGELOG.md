# Changelog

All notable changes to Forensic Council are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [1.4.0] - 2026-04-22

### Security
- HKDF key derivation for signing key storage now uses an explicit domain-separation
  salt (`b"forensic-council-keystore-v1-salt"`), hardening Fernet key derivation per
  NIST SP 800-56C. **Requires key rotation on upgrade** — see signing.py docstring.
- Removed stale `rppg_liveness_check` tool references from policy, overrides, and synthesis.
- bcrypt dependency unpinned from `<4.0.0` to `>=3.2`.
- Caddyfile CSP `connect-src` tightened from wildcard `wss:` to explicit `wss://{$DOMAIN}`.

### Fixed
- Agent 2: `anti_spoofing_deep_ensemble` handler was defined but never registered in
  the tool registry — deep audio investigations silently failed this step.
- Sessions API: `calibrated_probability` field was incorrectly mapped to `raw_confidence_score`;
  both the DTO conversion paths now use their respective source keys.
- Frontend: Agent 2 (Audio Forensics) was absent from the video MIME type support set,
  causing video investigations to show no audio agent progress in the UI.
- Startup: `mediainfo` added to required binary check; missing binary now fails fast.
- WebSocket: background tasks (subscriber, ping, idle monitor) now cleaned up with
  `asyncio.gather(..., return_exceptions=True)` to avoid shutdown log noise.
- Agent 3: `_is_screen_capture` promoted to `@cached_property` to avoid repeated
  computation across `task_decomposition` and `deep_task_decomposition` calls.
- Agent 5: `inject_agent1_context` method reordered to follow `__init__`, preventing
  the context attribute from being silently overwritten on construction.
- Caddyfile: HTTP block now includes `encode zstd gzip` for dev/localhost responses.
- Config: removed module-level `settings = get_settings()` alias to prevent import-time
  side effects that break test isolation.

## [1.3.0] - 2026-04-13

### Added
- Per-page metadata for evidence, result, and session-expired routes
- Degradation flags banner and agent confidence spread (σ) in MetricsPanel
- SHA-256 hash display and file size warnings in FileUploadSection
- `completed_at` timestamp in AGENT_COMPLETE WebSocket broadcasts
- YAML anchors (`x-backend-env`) in docker-compose.yml to deduplicate env vars
- Production readiness checks: `.env` git tracking, REDIS_PASSWORD, Jaeger OTLP exposure
- Storage directory documentation in apps/api/README.md
- jsx-a11y ESLint rules (alt-text, aria-props, role-has-required-aria-props, interactive-supports-focus)
- Dev extras in pyproject.toml: httpx, faker, factory-boy
- Escalated Ruff lint rules: N, UP, S, B, A, C4, PT

### Changed
- AgentAnalysisTab: auto-open first non-skipped agent instead of idx=0
- AgentFindingCard: added `aria-label` to expand/collapse button
- Dockerfile: targeted COPY instead of broad `COPY . .` for migration and app stages
- package.json: replaced `ts-node` with `tsx`, added `@axe-core/react`

### Security
- Verified `.env` is not tracked in Git history
- Added Jaeger OTLP port exposure check to validate_production_readiness.sh
- Confirmed all `.env.example` variables present (REDIS_PASSWORD, OTEL_ENABLED, NEXT_PUBLIC_API_URL)

