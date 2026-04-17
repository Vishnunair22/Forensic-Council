# Changelog

All notable changes to Forensic Council are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [1.3.0] - 2026-04-13

### Added
- Per-page metadata for evidence, result, and session-expired routes
- Degradation flags banner and agent confidence spread (Ïƒ) in MetricsPanel
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

