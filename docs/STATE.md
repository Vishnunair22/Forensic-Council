# Phase: R1–R5 Stabilization In Progress

## Current Status (v1.7.0)
**R1–R4 hardening complete as of 2026-04-25**

## Completed Work
- [x] Phase 1–5 audit (v1.6.4)
- [x] R1: Infra stabilization — Qdrant API key, OTel reconciled, 150s grace period, web bind-mount dropped in prod
- [x] R2: Backend hardening — per-provider circuit breaker, RS256 warning, ProcessPool semaphore, rate-limit metric, CSRF one-per-session
- [x] R4: ML/Free-tier — AASIST → Apache-2.0, CLIP ViT-B-32, quota env vars, prompt injection fencing, Gemini model centralization

## Open Items (v1.7.x)

### High Priority
- [ ] R2.2: Per-investigation token/quota meter UI (Redis hash keyed by session_id; backend exists, frontend not wired)
- [ ] R3: Frontend A11y polish — color contrast /75, ForensicErrorModal Radix Dialog, AgentProgressDisplay aria-live
- [ ] R1 backup: pg_dump cron sidecar OR Litestream documented
- [ ] R5 chaos test: Redis down 30s, Postgres down 10s, external Gemini → verify no 5xx cascade

### License Risk (Blocking for Commercial / Expert-Witness Use)
- [ ] **YOLO AGPL exposure**: Legal review required before SaaS distribution. Mitigation: set `YOLO_MODEL_NAME=detr-resnet-50` (Apache-2.0).
- [ ] **Research-only models** (BusterNet, F3-Net, ManTra-Net): Cannot be used in court exhibits without license. Gate behind `ENABLE_RESEARCH_MODELS=false` (default off) in production.
- [ ] **TruFor CC-NC**: Non-commercial only. Same gating required.

### Deferred (Backlog)
- WebSocket migration from SSE for bi-directional HITL
- Full-text search on evidence ledger
- Multi-tenant org support
- WCAG 2.2 AAA audit
- `models.lock.json` revision hash population (currently `"main"` — pin to SHA after first CI run)

## v1.7.0 Exit Criteria Status
- [ ] validate_production_readiness.sh passes clean (new checks added)
- [ ] CHANGELOG.md updated ✅
- [ ] MODEL_LICENSING.md created ✅
- [ ] models.lock.json created ✅

## Historical
- v1.6.4 (2026-04-25): Final Phase 5 orchestrator audit
- v1.6.3 (2026-04-25): Backend core Phase 3 audit
- v1.5.0 (2026-04-22): Phase 2 infrastructure audit