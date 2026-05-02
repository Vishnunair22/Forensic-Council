# Structural Audit 2026-Jan

Date: 2026-02-05 | Status: Complete

## Summary

Structural cleanup of Forensic Council codebase addressing documentation drift, dead code, and stale references. **No functional changes** were made — only removals, path fixes, and documentation updates.

---

## Changes Made

### B — Removed Orphans & Dead Code

| Item | Action | Reason |
|------|--------|-------|
| `apps/api/core/audit_logger.py` | Deleted | Zero external imports |
| `apps/api/core/model_registry.py` | Deleted | Zero external imports |
| `apps/api/tests/fixtures/ai_persona_test.png` | Deleted | Orphan |
| `apps/api/tests/fixtures/beach_gps_test.png` | Deleted | Orphan |
| `apps/api/tests/fixtures/invoice_ela_test.png` | Deleted | Orphan |
| `apps/api/tests/fixtures/sample_evidence.png` | Deleted | Orphan |
| `apps/api/tests/fixtures/whatsapp_context_test.png` | Deleted | Orphan |

### C — Deprecated Shim Modules

Added DEPRECATED banners to:
- `core/rate_limit.py`
- `core/rate_limiting.py`
- `core/custody_chain.py`

### D — Fixed Stale Paths

| Item | Change |
|------|-------|
| `infra/docker-compose.yml` | Removed bind-mounts for non-existent `apps/api/reports/` |
| Shell scripts | Added exec bit (was 100644, now 100755) |
| `apps/web/public/robots.txt` | Stripped UTF-8 BOM, fixed mojibake |

### E — Fixed Documentation

| File | Change |
|------|-------|
| `README.md` | Version badge v1.4.0 → v1.7.0; rewrote Common Commands |
| `apps/api/README.md` | Removed stale references |
| `docs/RUNBOOK.md` | Removed stale file references |
| `docs/SECURITY.md` | Fixed ADR 7 path |
| `docs/TROUBLESHOOTING.md` | Removed stale reference |
| `docs/MODEL_LICENSING.md` | Created (new file) |

### Version Sync

Updated to v1.7.0 in:
- `apps/api/pyproject.toml`
- `apps/web/package.json`
- `docs/ARCHITECTURE.md`, `docs/API.md`, `docs/COMPONENTS.md`, `docs/SCHEMAS.md`, `docs/AGENT_CAPABILITIES.md`

---

## What's Left (Out of Scope)

- `docs/COMPONENTS.md` requires rewrite (46 real components not yet documented)
- `apps/web/tests/storage.test.ts` move not yet done
- Operator scripts in `apps/api/scripts/` not yet documented

---

## Verification

- All Python imports resolve (no broken references to removed modules)
- Docker compose syntax validates
- Git status shows clean working tree (all changes committed)