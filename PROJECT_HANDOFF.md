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
| Local commit | `35b0e68` |
| Remote synced? | not verified in this session |

## Current Local Goal

Documentation hygiene pass — second pass to fix remaining stale references, broken handoff script, and audit doc markers.

## What Changed Since Last AI/Remote Snapshot

| Area | Files Changed | Summary | Status |
|------|---------------|---------|--------|
| Handoff script fix | scripts/update_handoff.sh, scripts/update_handoff.py (new) | Rewrote as pure Python (no bash string escaping issues); old shell/python hybrid was broken | completed |
| Known issues accuracy | PROJECT_HANDOFF.md | Changed "none remaining" to reflect actual remaining issues (see Known Issues table) | completed |
| COMPONENTS.md completeness | docs/COMPONENTS.md | Added missing VerdictGauge.tsx to Result Components | completed |
| Python version parity | apps/api/README.md | Clarified Python 3.12 tested/recommended vs 3.11-3.14 supported range | completed |
| API doc heading fix | docs/API.md | Added missing `### POST /api/v1/cases` heading; removed stale `## HITL` duplicate section | completed |
| Test doc stale names | docs/TESTING.md | Replaced stale FileUploadSection/CompletionBanner with AgentProgressDisplay | completed |
| Audit doc historical marker | docs/audits/2026-02-structural.md | Added "Historical record only" warning and fixed Jan/Feb title | completed |
| Test file header comment | apps/web/tests/unit/components/components.test.tsx | Fixed stale comment listing nonexistent components | completed |

## Exact Files Changed

```text
M	PROJECT_HANDOFF.md
M	apps/api/README.md
M	apps/web/tests/unit/components/components.test.tsx
M	docs/API.md
M	docs/COMPONENTS.md
M	docs/TESTING.md
M	docs/audits/2026-02-structural.md
M	scripts/update_handoff.sh
```

## Important Local Decisions

| Decision | Reason | Related Files | Status |
|----------|--------|---------------|--------|
| Rewrite handoff script in pure Python | Bash shell/python hybrid had string escaping bugs and `sed` table-row collapse risk | scripts/update_handoff.sh, scripts/update_handoff.py | resolved |
| Keep Both files for handoff script | Shell stub provides `bash` UX; Python script does the actual work | scripts/update_handoff.sh, scripts/update_handoff.py | resolved |
| COMPONENTS.md must be regenerated from actual filesystem | Previous version listed 5 nonexistent components and missed 8 real ones | docs/COMPONENTS.md | resolved |
| Python version must match across README files | Inconsistency between root README and apps/api/README confused contributors | README.md, apps/api/README.md | resolved |
| Audit doc in docs/audits/ must be marked historical | Title said "2026-Jan" while filename said "2026-02" — source of truth unclear | docs/audits/2026-02-structural.md | resolved |
| Test file header comments must match actual imports | components.test.tsx listed FileUploadSection/CompletionBanner which no longer exist | apps/web/tests/unit/components/components.test.tsx | resolved |

## Commands Run

| Command | Result | Time | Notes |
|---------|--------|------|-------|
| git branch --show-current | main | 2026-05-11 | |
| git rev-parse --short HEAD | f0e53f7 | 2026-05-11 | |
| Glob: apps/web/src/components/**/*.tsx | 46 components found | 2026-05-11 | Includes VerdictGauge.tsx |
| Glob: apps/api/api/routes/*.py | 14 route files found | 2026-05-11 | |
| Read: apps/api/README.md | — | 2026-05-11 | Found "Python 3.12 is required" needs clarification |
| Read: docs/TESTING.md | — | 2026-05-11 | Found stale FileUploadSection/CompletionBanner references |
| Read: docs/audits/2026-02-structural.md | — | 2026-05-11 | Found missing historical marker and title mismatch |
| Read: components.test.tsx | — | 2026-05-11 | Found stale header comment |
| python3 scripts/update_handoff.py | not run | — | Script updated; run manually after future changes |
| Frontend build | not run | — | Pending verification pass |
| Backend tests | not run | — | Pending verification pass |

## Known Issues

| Issue | Severity | Notes |
|-------|----------|-------|
| scripts/update_handoff.sh rewritten but not tested end-to-end | medium | Python script replaces broken shell/python hybrid; test with `python3 scripts/update_handoff.py` after future changes |
| Historical audit docs may still exist in docs/ not in docs/audits/ | low | docs/audits/ exists but other audit docs may remain in docs/ root |
| docs/CHANGELOG.md may reference removed components | low | Not verified in this pass |
| apps/web/tests/storage.test.ts moved status from audit | low | Audit said this was "not yet done" — verify if still needs doing |

## Open Questions

1. Should test file `ForensicResetOverlay.test.tsx` be renamed to `LoadingOverlay.test.tsx` (it tests LoadingOverlay, not ForensicResetOverlay)?
2. Should docs/CHANGELOG.md be verified for stale component name references?
3. Should `apps/web/tests/storage.test.ts` move be completed?

## Next Best Action for AI

This is the second hygiene pass. Remaining items are small and scoped. Suggested next steps:

1. Rename or clarify `ForensicResetOverlay.test.tsx` → `LoadingOverlay.test.tsx`
2. Verify docs/CHANGELOG.md for stale references
3. Check if `storage.test.ts` move is still pending
4. Run `python3 scripts/update_handoff.py` after any future changes to test the script
5. Run frontend and backend verification commands and record results in this file

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

Run `python3 scripts/update_handoff.py` (or `bash scripts/update_handoff.sh`) to refresh this
file with current git state. The script updates: branch, commit, changed files, git diff summary,
and timestamp.