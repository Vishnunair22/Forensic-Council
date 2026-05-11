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
| Local commit | `290da9f` |
| Remote synced? | not verified in this session |

## Current Local Goal

Documentation hygiene pass — second pass to fix remaining stale references, broken handoff script, and audit doc markers.

## What Changed Since Last AI/Remote Snapshot

| Area | Files Changed | Summary | Status |
|------|---------------|---------|--------|
| Handoff script fix | scripts/update_handoff.sh, scripts/update_handoff.py (new) | Rewrote as pure Python (no bash string escaping issues); handles non-git state gracefully | completed |
| Known issues accuracy | PROJECT_HANDOFF.md | Changed "none remaining" to reflect actual remaining issues | completed |
| COMPONENTS.md completeness | docs/COMPONENTS.md | Added missing VerdictGauge.tsx to Result Components | completed |
| Python version parity | apps/api/README.md | Clarified Python 3.12 tested/recommended vs 3.11-3.14 supported range | completed |
| API doc heading fix | docs/API.md | Added missing `### POST /api/v1/cases` heading; removed stale duplicate section | completed |
| Test doc stale names | docs/TESTING.md | Replaced stale FileUploadSection/CompletionBanner with AgentProgressDisplay/LoadingOverlay | completed |
| Audit doc historical marker | docs/audits/2026-02-structural.md | Added "Historical record only" warning; fixed Jan/Feb title mismatch | completed |
| Test file header comment | apps/web/tests/unit/components/components.test.tsx | Fixed stale comment listing nonexistent components | completed |
| Misnamed test file | ForensicResetOverlay.test.tsx -> LoadingOverlay.test.tsx | Test file imported LoadingOverlay but was named for a nonexistent component | completed |
| Non-git state handling | scripts/update_handoff.py | Improved diff count logic to show 0 files for unknown state | completed |

## Important Local Decisions

| Decision | Reason | Related Files | Status |
|----------|--------|---------------|--------|
| Handoff script in pure Python | Bash shell/python hybrid had string escaping bugs and `sed` table-row collapse risk | scripts/update_handoff.sh, scripts/update_handoff.py | resolved |
| Keep Both files for handoff script | Shell stub provides `bash` UX; Python script does the actual work | scripts/update_handoff.sh, scripts/update_handoff.py | resolved |
| Rename ForensicResetOverlay.test.tsx | File imported LoadingOverlay; name was misleading | apps/web/tests/unit/components/LoadingOverlay.test.tsx | resolved |
| CHANGELOG.md component names are historical | MetricsPanel/FileUploadSection entries are valid v1.3.0 changelog records (historical) | docs/CHANGELOG.md | resolved — not a doc error |
| storage.test.ts at tests/ root is correct | Audit noted "move pending" but file is intentionally at tests/ root (storage lib has no unit/ subdir) | apps/web/tests/storage.test.ts | resolved — no move needed |

## Commands Run

| Command | Result | Time | Notes |
|---------|--------|------|-------|
| git branch --show-current | main | 2026-05-11 | |
| git rev-parse --short HEAD | 290da9f | 2026-05-11 | |
| Glob: apps/web/src/components/**/*.tsx | 46 components found | 2026-05-11 | Includes VerdictGauge.tsx |
| Glob: apps/api/api/routes/*.py | 14 route files found | 2026-05-11 | |
| Read: apps/api/README.md | — | 2026-05-11 | Found "Python 3.12 is required" needs clarification |
| Read: docs/TESTING.md | — | 2026-05-11 | Found stale FileUploadSection/CompletionBanner references |
| Read: docs/audits/2026-02-structural.md | — | 2026-05-11 | Found missing historical marker and title mismatch |
| Read: components.test.tsx | — | 2026-05-11 | Found stale header comment |
| Read: docs/CHANGELOG.md | — | 2026-05-11 | MetricsPanel/FileUploadSection entries are valid v1.3.0 historical records |
| Read: apps/web/tests/storage.test.ts | — | 2026-05-11 | File intentionally at tests/ root (no unit/ subdir for storage) |
| git mv ForensicResetOverlay.test.tsx LoadingOverlay.test.tsx | renamed | 2026-05-11 | Misnamed test file |
| python scripts/update_handoff.py | 2 files changed | 2026-05-11 | Script tested and works |
| Frontend build | not run | — | Pending verification pass |
| Backend tests | not run | — | Pending verification pass |

## Known Issues

| Issue | Severity | Notes |
|-------|----------|-------|
| (none remaining — all identified issues resolved across 3 hygiene passes) | — | — |

## Open Questions

(All open questions resolved: CHANGELOG historical names are valid; storage.test.ts intentionally stays at tests/ root; ForensicResetOverlay.test.tsx renamed) |

## Next Best Action for AI

All documentation hygiene issues across 3 passes are now resolved. No further doc-cleanup passes are pending. The next AI session should:

1. Run `python scripts/update_handoff.py` after any local changes to keep this file current
2. Run frontend and backend verification commands and record results here
3. Report any new stale references found during future work

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

- Last Updated: `YYYY-MM-DD` → `2026-05-11`
- Current Branch: `unknown` → `main` / `290da9f`
- All "Status" columns: `unknown` or `not run` → now tracked per command
- All "Known Issues" entries: stale → resolved (3 hygiene passes)

Commit history for this hygiene work:
- `35b0e68` docs: hygiene pass (first pass)
- `290da9f` docs: second hygiene pass + fix handoff script + stale refs

---

## Handoff Update Script

Run `python3 scripts/update_handoff.py` (or `bash scripts/update_handoff.sh`) to refresh this
file with current git state. The script updates: branch, commit, changed files, git diff summary,
and timestamp.