# WORKFLOW_TRACE.md — Route & State Ownership Map

> **Purpose:** Document how state flows through the Forensic Council frontend journey, which files own which state, and what invariants must hold for future changes not to break the user experience.

> **Last updated:** Phase 7

---

## Global Stores

| Key | Owner | Survives refresh? | Notes |
|-----|-------|-------------------|-------|
| `forensic_investigator_id` | `storage.ts` | Yes | Persisted; read by `useInvestigation` and sent as `investigator_id` |
| `forensic_session_id` | `useInvestigation` / `useResult` | Yes | Written by `triggerAnalysis` and `selectSession`; cookie mirror for SSR |
| `forensic_investigation_ctx` | `useInvestigation` | Yes | Session-scoped snapshot `forensic_investigation_ctx:{sid}` for result page |
| `forensic_is_deep` | `useInvestigation` | Yes | Written by `handleAcceptAnalysis` / `handleDeepAnalysis` |
| `forensic_auto_start` | `HeroAuthActions` | Session only | Signals `/evidence` to auto-start from pending file |
| `fc_show_loading` | `useInvestigation` | Session only | Forces loading overlay during reconnect/auto-start |
| `fc_open_upload_once` | `useInvestigation` | Session only | One-shot flag for home to reopen upload modal |
| `fc_report_ready` | `useInvestigation` | Session only | Written by `handleAcceptAnalysis`; read by `useResult` |
| `forensic_history` | `useResult` | Yes | Array of `HistoryItem`; must survive New Upload / Home |

---

## Route Ownership

### `/` (Landing Page)

**Owner:** `apps/web/src/app/page.tsx` + `apps/web/src/components/ui/HeroAuthActions.tsx`

**State owned:**
- `showUpload` / `selectedFile` local state in `HeroAuthActions`
- `__pendingFileStore.file` (written here, consumed on `/evidence`)
- `__pendingFileStore.authPromise` (written here, awaited on `/evidence`)

**Invariants:**
- `HeroAuthActions.handleCTAClick` pre-authenticates and stores promise in `__pendingFileStore`
- `handleStartAnalysis` writes `__pendingFileStore.file`, sets `forensic_auto_start`, then navigates to `/evidence`
- On `?upload=1` or `fc_open_upload_once`, upload modal is reopened once
- `fc_open_upload_once` is consumed immediately (single-use)

**Triggers:**
- `fc:open-upload` event → reopens upload modal
- `fc:reset-home` event → resets local state

---

### `/evidence` (Investigation Page)

**Owner:** `apps/web/src/app/evidence/page.tsx` + `apps/web/src/hooks/useInvestigation.ts`

**State owned:**
- WebSocket connection lifecycle
- Agent progress / completion state
- HITL checkpoint state
- Phase tracking (`initial` / `deep`)
- `pendingFileStore` consumption

**Entry guards (in order):**
1. **Effect A — Pending file (auto-start):** If `__pendingFileStore.file` exists → call `triggerAnalysis`. Sets `autoStartFiredRef = true`.
2. **Effect B — Reconnect existing session:** If no pending file, `status === "idle"`, and `forensic_session_id` exists → reconnect WebSocket.
3. **Empty state:** No pending file, no session → show "No Evidence Queued"

**Effect A behavior:**
```
if (__pendingFileStore.file) {
  autoStartFiredRef.current = true;
  triggerAnalysis(pending);  // ← uploads, creates session, connects WS
}
```

**Effect B behavior:**
```
if (!__pendingFileStore.file && status === "idle" && forensic_session_id exists) {
  autoStartFiredRef.current = true;
  // Polls arbiter-status:
  //   not_found  → clear session, reset (← Fix #4 target)
  //   unreachable → reconnect WS
  //   complete   → navigate to /result/{sid}
  //   running    → reconnect WS
}
```

**Triggers:**
- `fc_show_loading` flag controls overlay during reconnect
- `fc_no_reconnect` prevents Effect B when `handleNewUpload` was called

---

### `/result/{sessionId}` (Result Page)

**Owner:** `apps/web/src/app/result/[sessionId]/page.tsx` + `apps/web/src/hooks/useResult.ts`

**State owned:**
- Report fetch via TanStack Query
- Arbiter status polling
- History persistence
- Tab state (analysis / history)

**Entry guards:**
1. `fc_report_ready` flag set by `handleAcceptAnalysis` → skips min-overlay delay
2. Polls `getArbiterStatus` until `complete` / `error`
3. On `complete` → enables TanStack Query report fetch
4. On report → writes to `forensic_history`, transitions to `ready`

**Session context read from:**
- `forensic_investigation_ctx:{sid}` (session-scoped, survives concurrent uploads)
- Falls back to global keys for backward compat

---

### `/session-expired`

**Owner:** `apps/web/src/app/session-expired/page.tsx`

**Behavior:**
- Dispatches `fc:open-upload` on "New Intake" click → home reopens modal
- Dispatches `fc:reset-home` on "Return to Hub" click → home resets

---

## State Machine — /evidence Page

```
                    ┌──────────────────────────────────────────┐
                    │           PAGE MOUNT                     │
                    └──────────┬───────────────────────────────┬┘
                               │
              ┌────────────────┴────────────────┐
              ▼                                 ▼
        pending file?                    no pending file?
              │                                 │
              ▼                                 ▼
    ┌─────────────────┐               ┌──────────────────┐
    │  Effect A fires  │               │  Effect B fires   │
    │  triggerAnalysis │               │  reconnect WS     │
    │  upload → WS     │               │  poll arbiter     │
    └────────┬────────┘               └─────────┬─────────┘
             │                                 │
             │                                 ▼
             │                    ┌────────────┴────────────┐
             │                    ▼            ▼            ▼
             │               not_found    unreachable   complete
             │                  │            │            │
             │                  ▼            ▼            ▼
             │              clear sess  reconnect WS  → /result/{sid}
             │              reset state
             │                    │
             │                    ▼
             │              retry or error
             │                    │
             └──────┬─────────────┘
                    │
                    ▼
         ┌──────────┴──────────────┐
         ▼                         ▼
   analysis phase              deep phase
   (Agent1-5 run)            (Agent1-5 rerun)
         │                         │
         ▼                         ▼
   awaiting_decision         awaiting_decision
         │                         │
   ┌─────┴─────┐                   │
   ▼           ▼                   │
Accept      Deep                   │
   │      Analysis                 │
   ▼           ▼                   │
→ /result   reconnect WS ─────────┘
            deep phase agents

```

---

## State Enum Reference

### SessionStatus (`orchestration/session_manager.py`)
| Value | Meaning |
|-------|---------|
| `INITIALIZING` | Session created, pipeline not yet started |
| `RUNNING` | Agents actively executing |
| `AWAITING_HITL` | Paused at an agent-level HITL checkpoint |
| `COMPLETED` | Pipeline finished (initial or deep pass) |
| `FAILED` | Unrecoverable error |

### WebSocket Message Types (`api/schemas.py` — `BriefUpdate.type`)
| Type | Meaning |
|------|---------|
| `CONNECTED` | WebSocket connection established |
| `AGENT_UPDATE` | Agent progress update |
| `AGENT_COMPLETE` | Individual agent finished |
| `PIPELINE_PAUSED` | Pipeline reached HITL gate; `run_deep_analysis_flag` awaiting human decision |
| `HITL_CHECKPOINT` | Agent-level ReAct loop paused for human decision |
| `HITL_EXPIRED` | HITL timeout elapsed; auto-skipping deep pass |
| `PIPELINE_COMPLETE` | All agents complete; arbiter synthesizing |
| `REPORT_READY` | Arbiter report finalized |
| `ARBITER_UPDATE` | Arbiter deliberation progress |
| `PIPELINE_QUARANTINED` | Evidence quarantined; pipeline halted |
| `ERROR` | Unrecoverable pipeline error |

### HITLCheckpointStatus / HITLCheckpointReason (`core/hitl.py`)
| Status | Description |
|--------|-------------|
| `PAUSED` | Triggered by: `CONTESTED_FINDING`, `TOOL_UNAVAILABLE`, `SEVERITY_THRESHOLD_BREACH`, `TRIBUNAL_ESCALATION` |
| `RESUMED` | Human approved or auto-timeout elapsed |
| `OVERRIDDEN` | Human overrode agent findings |
| `TERMINATED` | Human terminated the investigation |

### Arbiter Status Values (pipeline metadata — `pipeline_phases.py`)
Returned by `getArbiterStatus()` frontend call; drives Effect B reconnect logic:
| Value | Meaning |
|-------|---------|
| `running` | Pipeline still executing |
| `awaiting_decision` | Initial pass complete; `PIPELINE_PAUSED` sent; waiting for Accept or Deep |
| `complete` | Arbiter report ready; navigate to `/result/{sid}` |
| `not_found` | Session expired or never started; clear and reset |

### `run_deep_analysis_flag`
Boolean stored in pipeline Redis metadata. Set by `POST /sessions/{sid}/resume {deep_analysis: bool}`. `false` → arbiter synthesizes initial pass only. `true` → all agents re-run in deep phase before arbiter.

---

## Key State Transitions

### `handleAcceptAnalysis` (Accept Initial → Arbiter synthesizes)
```
1. playSound(arbiter_start)
2. storage.setItem("forensic_is_deep", "false")
3. storage.setItem(`forensic_initial_agents:${sid}`, completedAgentsRef.current)
4. sessionOnlyStorage.removeItem("fc_report_ready")
5. document.body.setAttribute("data-fc-loading", "1")
6. resumeInvestigation(false)     ← POST /sessions/{sid}/resume {deep_analysis: false}
7. router.push(/result/{sid})     ← result page polls arbiter, fetches report
```

### `handleDeepAnalysis` (Deep → Agent re-run)
```
1. storage.setItem("forensic_is_deep", "true")
2. storage.setItem(`forensic_initial_agents:${sid}`, nonSkipped)
3. connectWebSocket(sid, true)   ← reconnect WS to discard old initial-phase messages
4. clearCompletedAgents()
5. setPhase("deep")
6. resumeInvestigation(true)     ← POST /sessions/{sid}/resume {deep_analysis: true}
```

### `handleNewUpload` (Reset → Home)
```
1. clearInvestigationPersistence()  ← clears forensic_session_id, ctx, agents, etc.
2. sessionOnlyStorage.setItem("fc_open_upload_once", "1")
3. sessionOnlyStorage.setItem("fc_no_reconnect", "1")
4. router.push("/?upload=1")       ← home reopens modal once
```

**CRITICAL:** `handleNewUpload` calls `clearInvestigationPersistence()` which clears ALL forensic keys — including `forensic_history`. This is the bug fixed in #7.

---

## Storage Keys — Who Writes What

| Key | Written by | Read by | Cleared by |
|-----|-----------|--------|-----------|
| `forensic_session_id` | triggerAnalysis, selectSession | Effect B, useResult, ResultLayout | clearInvestigationPersistence, handleNew, handleHome |
| `forensic_investigation_ctx` | triggerAnalysis | useResult | clearInvestigationPersistence |
| `forensic_history` | useResult | HistoryPanel | **nothing** (preserved) |
| `forensic_initial_agents:{sid}` | triggerAnalysis, handleAcceptAnalysis | useInvestigation Effect B | clearInvestigationPersistence |
| `forensic_deep_agents:{sid}` | handleDeepAnalysis, handleViewResults | useInvestigation Effect B | clearInvestigationPersistence |
| `forensic_is_deep` | handleAcceptAnalysis, handleDeepAnalysis | useResult | clearInvestigationPersistence |
| `forensic_thumbnail:{sid}` | triggerAnalysis | useResult | clearInvestigationPersistence |
| `forensic_mime_type:{sid}` | triggerAnalysis | useResult | clearInvestigationPersistence |
| `forensic_pipeline_start:{sid}` | triggerAnalysis | useResult | clearInvestigationPersistence |
| `fc_report_ready` | handleAcceptAnalysis | useResult | useResult (after 1 read) |

---

## Known Edge Cases

### Expired Upload Handoff
When user navigates to `/evidence` without `__pendingFileStore.file` but with `forensic_auto_start` flag set (indicating the handoff expired). Fix: detect flag, show toast, route home with `?upload=1`.

### Duplicate Upload 409
When user uploads the same file twice. Backend returns 409 with existing session ID. Fix: catch `DuplicateInvestigationError` in `triggerAnalysis`, reconnect to existing session.

### Session not_found on reconnect
Effect B polls `getArbiterStatus` on reconnect. `not_found` means session expired. Fix: clear session, show empty state, let user start fresh.

### Accept Analysis bridge
`handleAcceptAnalysis` sets `fc_report_ready` but `useResult` reads it once and clears it. The arbiter status polling in `useResult` must start immediately — it cannot depend solely on `fc_report_ready`.

### Duplicate Accept/Deep decisions
`investigationInFlightRef` guards `triggerAnalysis` and `handleDeepAnalysis`, but `handleAcceptAnalysis` uses `isNavigating`. A double-click on "Accept Analysis" could fire two resumes. Fix: guard with a ref.

### forensic_history preservation
`clearInvestigationPersistence()` clears ALL forensic keys including history. Fix: save history before clearing.

---

## Rules for Future Changes

1. **Never clear `forensic_history`** — it's the History panel source of truth. If `clearInvestigationPersistence` needs to clear session keys, exclude history.
2. **Never remove the `fc_report_ready` bridge** — `handleAcceptAnalysis` needs it to skip the min-overlay delay on the result page.
3. **Effect A and B are mutually exclusive** — one fires per mount. They must both set `autoStartFiredRef = true` to prevent double-firing.
4. **Session-scoped keys** (`forensic_investigation_ctx:{sid}`) are written for every new investigation. Always write both the global key AND the session-scoped key.
5. **`investigationInFlightRef` guards all async submission entry points** (`triggerAnalysis`, `handleDeepAnalysis`). Never remove it.
6. **Duplicate session 409** must reconnect (not error) — `DuplicateInvestigationError` handling is part of the critical path.
