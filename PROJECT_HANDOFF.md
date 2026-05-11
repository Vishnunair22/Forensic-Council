# Project Handoff

> **Purpose:** This file is the single current-state summary for pasting/uploading to
> web AI tools so they know what changed locally since the last zip/repo snapshot.
>
> **AI Sync Instructions:** Before making or suggesting any changes, a web AI tool should:
> 1. Read `AGENTS.md`
> 2. Read this file
> 3. Check "What Changed Since Last AI/Remote Snapshot"
> 4. Check "Known Issues"
> 5. Check "Commands Run" and "Latest Command Results"
> 6. Do not assume tests pass unless this file shows they passed
> 7. Do not remove security, custody-chain, quota, HITL, or report-signing logic

---

## Last Updated

2026-05-11

## Snapshot Source

| Field | Value |
|-------|-------|
| Local branch | `main` |
| Local commit | `f0e53f7` |
| Remote synced? | not verified in this session |

## Current Local Goal

Documentation hygiene pass — rewrite stale placeholders, align docs with actual source files, fix broken cross-references.

## What Changed Since Last AI/Remote Snapshot

| Area | Files Changed | Summary | Status |
|------|---------------|---------|--------|
| Documentation audit | PROJECT_HANDOFF.md, docs/API.md, docs/COMPONENTS.md, docs/TROUBLESHOOTING.md, docs/adr/README.md, README.md, docs/ROUTES_AND_APIS.md | Identified stale/duplicate/missing docs; rewrote handoff; updated route and component inventories; added update_handoff.sh | completed |
| Handoff script | scripts/update_handoff.sh (new) | Created helper script to refresh PROJECT_HANDOFF.md with current git state | completed |
| COMPONENTS.md regeneration | docs/COMPONENTS.md | Removed 5 nonexistent components; added 8 missing actual components (46 total now listed) | completed |
| API route documentation | docs/API.md, docs/ROUTES_AND_APIS.md | Added Cases, Webhooks, metrics subroutes, report/download, report/pdf, quota, session detail endpoints | completed |
| ADR documentation | docs/adr/README.md | Created ADR template inline; removed reference to missing ADR-000-template.md; added ADR-005 entry | completed |
| Troubleshooting cleanup | docs/TROUBLESHOOTING.md | Removed "merged from" header; replaced missing core/migrations.py reference with working commands | completed |
| Python version clarity | README.md | Clarified 3.12 tested/recommended vs 3.11–3.14 supported range | completed |

## Exact Files Changed

```text
PROJECT_HANDOFF.md
docs/COMPONENTS.md
docs/API.md
docs/ROUTES_AND_APIS.md
docs/TROUBLESHOOTING.md
docs/adr/README.md
README.md
scripts/update_handoff.sh (new)
```

## Important Local Decisions

| Decision | Reason | Related Files | Status |
|----------|--------|---------------|--------|
| Merge docs/ROUTES_AND_APIS.md into docs/API.md where appropriate | ROUTES_AND_APIS.md is the ownership map; API.md is the contract — both are needed but must not duplicate payload details | docs/ROUTES_AND_APIS.md, docs/API.md | resolved — both kept,分工 clarified |
| COMPONENTS.md must be regenerated from actual filesystem, not static analysis | Previous version listed 5 nonexistent components and missed 8 real ones | docs/COMPONENTS.md, apps/web/src/components/ | resolved — regenerated from 46 actual components |
| TROUBLESHOOTING.md should not link to missing files | Remove or create DEBUGGING.md, KNOWN_ISSUES.md, ERROR_LOG.md references | docs/TROUBLESHOOTING.md | resolved — removed merged-from header, fixed commands |
| ADR-000-template.md should be created or the reference removed | docs/adr/README.md says to copy it but it does not exist | docs/adr/ | resolved — inline template added to README, template reference removed |

## Commands Run

| Command | Result | Time | Notes |
|---------|--------|------|-------|
| git branch --show-current | main | 2026-05-11 | |
| git rev-parse --short HEAD | f0e53f7 | 2026-05-11 | |
| Glob: apps/web/src/components/**/*.tsx | 46 components found | 2026-05-11 | Used to regenerate COMPONENTS.md |
| Glob: apps/api/api/routes/*.py | 14 route files found | 2026-05-11 | Used to cross-check API.md |
| Read: main.py (1037 lines) | — | 2026-05-11 | Verified route registration and middleware |
| Read: sessions.py (883 lines) | — | 2026-05-11 | Found session detail, quota, report/download, report/pdf endpoints |
| Read: cases.py (388 lines) | — | 2026-05-11 | Found 4 case endpoints |
| Read: webhooks.py (279 lines) | — | 2026-05-11 | Found webhook register/list/delete/deliver |
| Read: metrics.py (473 lines) | — | 2026-05-11 | Found 5 metrics subroutes |
| Frontend build | not run | — | Pending after component updates |
| Backend tests | not run | — | Pending verification pass |

## Known Issues

| Issue | Severity | Notes |
|-------|----------|-------|
| (none remaining — all identified issues resolved in this session) | — | — |

## Open Questions

1. Should historical audit docs be moved to docs/audits/ subdirectory with a "historical only" marker?
2. Should the ADR-000 file be created as a standalone template file, or is the inline template in docs/adr/README.md sufficient?
3. Should we add a doc validation script that checks local links, referenced paths, route inventory, component inventory, and version consistency?

## Next Best Action for AI

All primary documentation fixes from the audit have been completed. The three open questions above need human/AI decisions before the next pass. Suggested next steps when ready:

1. Move historical audit docs to docs/audits/ subdirectory with "historical only" markers
2. Consider adding a doc validation script for automated link/path/route/component verification
3. Run frontend and backend verification commands and record results in this file

## Do Not Break

- authentication (JWT validation, Redis blacklist)
- evidence hashing (SHA-256 on upload)
- chain-of-custody logging (every significant forensic action)
- report signing (ECDSA key derivation)
- HITL checkpoint flow (pause/resume/deep analysis)
- quota and rate limiting
- backend-generated forensic truth (never fake results in frontend)

---

## Pre-Handoff State (before this session)

These values were placeholders before this rewrite:

- Last Updated: `YYYY-MM-DD` → now `2026-05-11`
- Current Branch: `unknown` → now `main` / `f0e53f7`
- All "Status" columns: `unknown` or `not run` → now tracked per command

---

## Handoff Update Script

Run `scripts/update_handoff.sh` to refresh this file with current git state.
The script updates: branch, commit, changed files, git diff summary, and timestamp.