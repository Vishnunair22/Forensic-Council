# Changelog

All notable changes to Forensic Council are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [1.7.0] - 2026-04-25

### Security
- **Prompt injection hardening**: All OCR text and EXIF metadata passed to Gemini now wrapped in `[UNTRUSTED EVIDENCE START/END]` fences with a system safety preamble that prevents evidence content from acting as instructions
- **Per-provider circuit breakers**: LLMClient circuit breakers are now keyed by `provider:model` (shared across agents) instead of per-instance; a failing model on one provider no longer blocks healthy fallbacks
- **CSRF one-per-session**: CSRF cookie now only issued when absent, eliminating redundant `Set-Cookie` headers on every GET
- **Rate-limiter fail-open metric**: `rate_limit_redis_bypasses` counter emitted when Redis is unavailable; visible in `/api/v1/metrics/` and Prometheus output
- **RS256 startup warning**: Explicit log warning when `JWT_ALGORITHM=RS256` but `JWT_PRIVATE_KEY` is absent (dev falls back to HS256)
- **Qdrant API key enforcement**: `QDRANT__SERVICE__API_KEY` wired to `QDRANT_API_KEY` env; production validation checks for it

### Infrastructure
- **ProcessPoolExecutor semaphore**: `app.state.process_pool_semaphore = Semaphore(max_workers × 4)` caps CPU-task queue depth; callers reject with 503 on overflow
- **Model licensing matrix**: `docs/MODEL_LICENSING.md` added listing every ML weight, license (AGPL, research-only, Apache-2.0), and required legal actions
- **`models.lock.json`**: `apps/api/models.lock.json` created to pin HF model revision hashes for reproducibility
- **validate_production_readiness.sh**: Enhanced with checks for signing key length (≥32), JWT key length (≥32), CORS no-wildcard, Redis password, demo password not default, Qdrant API key (production), and `MODEL_LICENSING.md` presence

### ML / Free-tier
- **AASIST → Apache-2.0**: Default `aasist_model_name` changed from `clovaai/AASIST` (research-only) to `MattyB95/AST-anti-spoofing` (Apache-2.0); AASIST remains available as opt-in
- **CLIP downsized**: Default `siglip_model_name` changed from `ViT-L-14` (~1.5GB) to `ViT-B-32` (~150MB); ViT-L-14 available as opt-in
- **Per-provider quota env vars**: `GEMINI_RPM_LIMIT`, `GEMINI_RPD_LIMIT`, `GROQ_RPM_LIMIT`, `GROQ_TPM_LIMIT` added to settings with free-tier defaults
- **Separate Arbiter Gemini key**: `ARBITER_GEMINI_API_KEY` setting added to isolate Arbiter quota from analysis agents
- **Gemini model centralization**: Removed `model_hint="gemini-2.5-flash"` hardcodes from agents 1, 2, 3; all now route through `settings.gemini_model`

### Changed
- `degraded_findings_summary: dict[str, list[str]]` added to `ReportDTO` for per-agent fallback visibility in report header

## [1.6.4] - 2026-04-25

### Security (Free-tier Focus)
- Prompt injection hardening in `_sanitize()` function
- Cost quota default $0 for free tier

### Fixed
- Phase 4: Model licensing documentation added (MODEL_PINNING.md)

## [1.6.3] - 2026-04-25

### Fixed
- OTEL endpoint consistency (4317 → 4318)
- evidence_retention_days 7 → 30 days
- use_redis_worker default False → True
- validate_production_settings before start_monitoring

## [1.6.0] - 2026-04-25

### Security (Frontend/UI)
- CSP tightened in Caddyfile
- lucide-react updated to ^0.468.0
- ForensicErrorModal accessibility (role=dialog, aria-*)

## [1.5.2] - 2026-04-25

### Security (Agents Part 1)
- super().__init__() call added
- _init_context assertion guard
- Adversarial check status fix
- copy.deepcopy for snapshot

## [1.5.0] - 2026-04-22

### Security (Root-level)
- package.json: workspaces, dev kill-others, engines, prepare
- .env.example: unique placeholders, QDRANT, Postgres
- .gitignore: anchored patterns
- .pre-commit-config.yaml: removed pycln, fixed eslint

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
- Config: get_settings() is LRU-cached for performance; note that module-level
  calls require env vars to be set before first import (or use lazy initialization).

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
