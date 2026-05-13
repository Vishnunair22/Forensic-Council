# Documentation Inventory — Forensic Council

> **Purpose:** Canonical index of all documentation files. Every important doc is either listed
> here as active/archived, or intentionally excluded with a reason.
>
> **Owner:** Primary maintainer responsible for keeping this doc current.

---

## Primary Docs (entrypoints for contributors)

| Doc | Owner | Purpose | Source of Truth? | Last Reviewed Phase | Should Local AI Edit? | Verification |
|-----|-------|---------|-----------------|--------------------|---------------------|--------------|
| `README.md` | All | Project entrypoint — onboarding, monorepo layout, fast start, links to source docs | Partial (duplicates sub-docs) | 9 | Only to trim duplicates and fix broken links | `grep -n "docs/WORKFLOW_TRACE.md" README.md` |
| `PROJECT_HANDOFF.md` | AI/Contributors | Local AI handoff — current phase, changed files, verification results, rules | Yes | 8→9 | Yes, after every phase | `grep -n "Phase" PROJECT_HANDOFF.md` |
| `docs/ARCHITECTURE.md` | Architecture | System runtime topology, agent flow, infra components, security | Yes | 9 | Yes | `grep -n "State ownership" docs/ARCHITECTURE.md` |
| `docs/WORKFLOW_TRACE.md` | Workflow | Route/state machine, Effect A/B, storage key ownership, edge cases | Yes | 7→9 | Yes | `grep -n "Effect A" docs/WORKFLOW_TRACE.md` |
| `docs/API_CONTRACT.md` | API/Frontend | Backend/frontend contract — auth, investigation, WS/SSE, HITL, report, termination | Created phase 9 | 9 | Yes | `grep -n "409" docs/API_CONTRACT.md` |
| `docs/TESTING.md` | QA/Dev | All test commands, coverage targets, verification gates, hygiene | Yes | 8→9 | Yes | `grep -n "verify_phase8_tests" docs/TESTING.md` |
| `docs/OPERATIONAL_RUNBOOK.md` | Ops | Incident triage, severity, common failures, recovery commands | Created phase 9 | 9 | Yes | `grep -n "worker heartbeat" docs/OPERATIONAL_RUNBOOK.md` |
| `docs/SECURITY.md` | Security | Auth, authorization, upload, custody, secrets, rate limiting, failure behavior | Yes | 9 | Yes | `grep -n "session ownership" docs/SECURITY.md` |
| `docs/MODEL_REGISTRY.md` | ML/Dev | Model/provider registry, free-tier setup, verification | Created phase 9 | 9 | Yes | `grep -n "FREE_TIER_MODE" docs/MODEL_REGISTRY.md` |
| `docs/PRODUCTION_CHECKLIST.md` | Ops | Production deployment gates, checklist, validation commands | Yes | 9 | Yes | `grep -n "validate_production_readiness" docs/PRODUCTION_CHECKLIST.md` |

---

## App-Specific Docs

| Doc | Owner | Purpose | Source of Truth? | Last Reviewed Phase | Should Local AI Edit? | Verification |
|-----|-------|---------|-----------------|--------------------|---------------------|--------------|
| `apps/api/README.md` | Backend | Backend setup, run, test, config, architecture pointers, guardrails | Yes | 9 | Yes | `grep -n "uv sync" apps/api/README.md` |
| `apps/web/README.md` | Frontend | Frontend setup, run, test, routes, state ownership, guardrails | Yes | 9 | Yes | `grep -n "npm ci" apps/web/README.md` |
| `infra/README.md` | Ops | Docker/infra — quickstart, ports, volumes, validation, common commands | Yes | 9 | Yes | `grep -n "verify_phase1" infra/README.md` |
| `infra/DOCKER_BUILD.md` | Ops | Image build internals, cache, volumes, troubleshooting | Yes | 9 | Yes | `grep -n "PRELOAD_MODELS" infra/DOCKER_BUILD.md` |

---

## Deleted Docs (removed Phase 10 cleanup)

The following docs were deprecated stubs explicitly superseded by newer documents.
They have been **deleted** from the repository. Do not recreate them.

| Deleted Doc | Superseded By |
|-------------|--------------|
| `docs/API.md` | `docs/API_CONTRACT.md` |
| `docs/ROUTES_AND_APIS.md` | `docs/API_CONTRACT.md` |
| `docs/RUNBOOK.md` | `docs/OPERATIONAL_RUNBOOK.md` |
| `docs/TROUBLESHOOTING.md` | `docs/OPERATIONAL_RUNBOOK.md` |
| `docs/MODELS.md` | `docs/MODEL_REGISTRY.md` |
| `docs/ML_AGENTS.md` | `docs/AGENT_CAPABILITIES.md` + agent source |
| `docs/FRONTEND_FLOW.md` | `docs/WORKFLOW_TRACE.md` |
| `docs/BACKEND_FLOW.md` | `docs/WORKFLOW_TRACE.md` + `docs/ARCHITECTURE.md` |

---

## Docs Intentionally Not Listed (reference-only)

These files exist in the repo but are not primary contributor references.

| Doc | Reason Not Listed |
|-----|-------------------|
| `docs/CHAIN_OF_CUSTODY.md` | Architectural reference only; not a contributor source of truth |
| `docs/AGENT_CAPABILITIES.md` | Reference only; canonical source is agent code |
| `docs/COMPONENTS.md` | Reference only; canonical source is component code |
| `docs/MONITORING.md` | Reference only; ops team owns directly |
| `docs/SCHEMAS.md` | Reference only; canonical source is Pydantic models and API contract |
| `docs/AI_CONTEXT.md` | Reference only; not a contributor handoff doc |
| `docs/CHANGELOG.md` | Version history; maintained by release process |
| `docs/MODEL_LICENSING.md` | Licensing reference; canonical source is `docs/MODEL_REGISTRY.md` |
| `docs/ADR-*.md` | Decision records; architectural only |
| `docs/audits/` | Audit records; reference only |

---

## Doc Update Rule

When any of the following changes, the owning doc and this inventory must be updated:

- Route or state ownership changes
- Model or provider config changes
- Test commands or verification scripts
- Docker compose structure
- Auth or security behavior

---

## Script Verification

Run `python scripts/check_docs.py` to validate:
- All listed docs exist
- No active doc links to archived paths
- README links to entrypoint docs
- No stale `npm install` where `npm ci` is required
- No unresolved TODO/TBD placeholders
- PROJECT_HANDOFF.md contains phase invariants and verification commands