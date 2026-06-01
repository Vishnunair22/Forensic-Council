Below is the full destructured end-to-end flow map for your app based on the uploaded codebase `Forensic-Council-main(45).zip`. This is written so you can hand it to another AI coding tool and have it trace each layer, mark each section complete, and fix broken runtime paths.

# Forensic Council full end-to-end app flow trace

## Core route map

Your app is a Next.js frontend with a FastAPI backend.

Frontend route surfaces:

```txt
/                              Landing page
/evidence                      Evidence analysis runtime page
/result                        Redirect/helper result route
/result/[sessionId]            Final report/result page
/session-expired               Session expiry page
/api/auth/demo                 Next.js demo-auth proxy
/api/v1/[...path]              Next.js API proxy to backend
```

Important frontend files:

```txt
apps/web/src/app/layout.tsx
apps/web/src/app/page.tsx
apps/web/src/app/evidence/page.tsx
apps/web/src/app/result/[sessionId]/page.tsx
apps/web/src/components/pages/HomeClient.tsx
apps/web/src/components/pages/EvidenceUploadClient.tsx
apps/web/src/components/pages/DynamicResultClient.tsx
apps/web/src/components/ui/GlobalNavbar.tsx
apps/web/src/components/ui/GlobalLoadingOverlay.tsx
apps/web/src/components/ui/RouteExperience.tsx
apps/web/src/components/ui/HeroAuthActions.tsx
apps/web/src/components/evidence/UploadModal.tsx
apps/web/src/components/evidence/UploadSuccessModal.tsx
apps/web/src/hooks/useInvestigation.ts
apps/web/src/hooks/useSimulation.ts
apps/web/src/hooks/useResult.ts
apps/web/src/lib/appReset.ts
apps/web/src/lib/api/client.ts
apps/web/src/lib/upload/fileHandoffManager.ts
apps/web/src/lib/upload/authService.ts
apps/web/src/lib/crypto/fileHash.ts
apps/web/src/lib/fileValidation.ts
apps/web/src/lib/storage.ts
apps/web/src/lib/storageKeys.ts
```

Important backend files:

```txt
apps/api/api/main.py
apps/api/api/routes/auth.py
apps/api/api/routes/investigation.py
apps/api/api/routes/sessions.py
apps/api/api/routes/_websocket.py
apps/api/api/routes/sse.py
apps/api/api/routes/hitl.py
apps/api/api/routes/_session_state.py
apps/api/orchestration/pipeline.py
apps/api/orchestration/pipeline_phases.py
apps/api/orchestration/investigation_queue.py
apps/api/orchestration/worker.py
apps/api/agents/agent1_image.py
apps/api/agents/agent2_audio.py
apps/api/agents/agent3_object.py
apps/api/agents/agent4_video.py
apps/api/agents/agent5_metadata.py
apps/api/agents/arbiter.py
apps/api/core/final_report_groq_refiner.py
apps/api/core/deterministic_report_builder.py
apps/api/core/pdf_report_exporter.py
apps/api/core/docx_report_exporter.py
```

---

# 1. App load, refresh, hard refresh, navbar reset, routing, scroll, and stability

## 1.1 Initial app shell load

### User-level flow

User opens:

```txt
/
```

Expected visible sequence:

```txt
Browser loads root app
↓
Global layout renders navbar/background/providers
↓
Landing page hero appears
↓
Hero animation fades/staggers content
↓
CTA “Begin Analysis” is visible
↓
How-it-works and agent sections lazy-load below hero
```

### UI and animation layer

Trace:

```txt
apps/web/src/app/layout.tsx
→ wraps the whole app
→ should include global CSS, QueryProvider, navbar, loading overlay, toaster, route experience, footer/background
```

Landing page:

```txt
apps/web/src/app/page.tsx
→ renders HomeClient
```

Home client:

```txt
apps/web/src/components/pages/HomeClient.tsx
```

Important UI behavior:

```txt
HomeClient
→ renders min-h-screen landing container
→ decorative dot/grid background
→ hero section with id="hero"
→ framer-motion containerVariants
→ itemVariants for headline, paragraph, CTA
→ respects prefers-reduced-motion via useReducedMotion()
→ lazy-loads HowWorksSection and AgentsSection with next/dynamic
```

Checklist:

```txt
[ ] / route renders without client/server hydration mismatch.
[ ] Hero is centered and does not jump after hydration.
[ ] Framer motion disabled/softened when prefers-reduced-motion is true.
[ ] CTA is keyboard focusable.
[ ] Lazy sections do not cause layout collapse; loading placeholders hold min height.
[ ] Body scroll is enabled on landing.
[ ] No stale body overflow lock remains from modals/overlays.
```

## 1.2 Global navbar behavior

Main file:

```txt
apps/web/src/components/ui/GlobalNavbar.tsx
```

### User-level behavior

Expected:

```txt
On home with no active session:
  logo click → play “hum” sound → smooth-scroll to top

On any non-home route without active session:
  logo click → play “reset” → navigate home

With active investigation/session:
  logo click → open confirmation modal
  Abort & Reset → terminate backend session, clear local state, go home
  Keep Going → close modal, preserve investigation
```

### UI/animation behavior

Navbar:

```txt
fixed top
height 64px
glass/elevated surface
hides on downward scroll
shows on upward scroll/top
stays visible for keyboard users
uses inert when hidden
shows direct API warning bar if NEXT_PUBLIC_API_URL is set
```

Checklist:

```txt
[ ] Navbar never blocks clicks when hidden.
[ ] Navbar returns on keyboard Tab.
[ ] Navbar returns near top scroll < 60px.
[ ] prefers-reduced-motion keeps navbar visible.
[ ] Direct API warning does not overlap clickable navbar content.
[ ] Reset modal is accessible: title, focus trap, Escape/close behavior.
```

### State detection layer

Navbar calls:

```txt
hasResettableInvestigationState()
```

From:

```txt
apps/web/src/lib/appReset.ts
```

It treats the app as resettable if any of these exist:

```txt
local/session storage session id
fc_session cookie
/result/[sessionId] URL
AUTO_START flag
FC_SHOW_LOADING flag
FC_PENDING_FILE_META flag
```

Navbar refreshes active-state detection through:

```txt
fc_storage_update event
storage event
window focus
document visibilitychange
pathname change
```

Checklist:

```txt
[ ] storage wrapper emits fc_storage_update reliably.
[ ] hasActiveSession becomes true after upload/session creation.
[ ] hasActiveSession becomes false after reset cleanup.
[ ] Result URL itself counts as active resettable state.
```

## 1.3 Universal reset flow

Main file:

```txt
apps/web/src/lib/appReset.ts
```

Reset path:

```txt
GlobalNavbar logo click
→ setConfirmResetOpen(true)
→ user clicks Abort & Reset
→ resetActiveInvestigation(queryClient)
```

Reset internals:

```txt
resolveActiveSessionId()
→ storage SESSION_ID
→ current /result/[sessionId] path
→ fc_session cookie fallback

resetActiveInvestigation()
→ prepare mutation headers
→ DELETE /api/v1/sessions/{sessionId}
→ POST /api/v1/auth/logout
→ cleanupLocalInvestigationState()
→ wait max 800ms for backend cleanup/logout
```

Local cleanup:

```txt
arbiterControl.abort()
queryClient.clear()
preserve HISTORY
storage.clearAllForensicKeys()
sessionOnlyStorage.clearAllForensicKeys()
restore HISTORY
expire session cookie
expire auth cookies
remove body data-fc-loading
clear body overflow
clear __pendingFileStore
clear IndexedDB/file persistence
set FC_NO_RECONNECT=1
dispatch fc:reset-home
```

Backend cleanup route:

```txt
DELETE /api/v1/sessions/{session_id}
apps/api/api/routes/sessions.py
```

Checklist:

```txt
[ ] Reset does not destroy local history.
[ ] Reset clears SESSION_ID, FC_SHOW_LOADING, AUTO_START, pending file meta.
[ ] Reset clears in-memory pending file store.
[ ] Reset clears persisted file handoff.
[ ] Reset aborts arbiter polling/control.
[ ] Reset sends backend DELETE even from result page route.
[ ] Reset sends logout but does not hang UI if backend is slow.
[ ] Reset prevents auto reconnect after returning home via FC_NO_RECONNECT.
[ ] Home receives fc:reset-home and closes upload modal.
```

## 1.4 Refresh and hard refresh survival

There are two different refresh scenarios.

### A. Refresh after session exists

Expected:

```txt
User refreshes /evidence after session id exists
↓
EvidenceUploadClient mounts
↓
useInvestigation sees no AUTO_START pending handoff
↓
Effect B reconnects existing session
↓
getArbiterStatus(sessionId)
↓
if complete → route to /result/[sessionId]
↓
else connect WebSocket/SSE and restore saved agent cards
```

Files:

```txt
apps/web/src/components/pages/EvidenceUploadClient.tsx
apps/web/src/hooks/useInvestigation.ts
apps/web/src/hooks/useSimulation.ts
```

Reconnect effect:

```txt
useInvestigation Effect B — Reconnect existing session
```

Storage keys involved:

```txt
SESSION_ID
INITIAL_AGENTS:{sessionId}
DEEP_AGENTS:{sessionId}
RESULT_PHASE:{sessionId}
FC_SHOW_LOADING
FC_NO_RECONNECT
```

Checklist:

```txt
[ ] Refresh on /evidence with active session reconnects instead of starting duplicate upload.
[ ] If arbiter status complete, navigates to /result/[sessionId].
[ ] If saved deep agents exist, phase restores as deep.
[ ] If only initial agents exist, phase restores as initial.
[ ] FC_SHOW_LOADING is cleared during reconnect to avoid stuck overlay.
[ ] If backend returns not_found, stale session clears and upload opens again.
```

### B. Hard refresh during pre-upload handoff before backend session exists

Expected:

```txt
User selected file
↓
file was only available as browser File object / persisted handoff
↓
hard refresh may lose File access
↓
app should not silently hang
↓
show destructive toast: file selection lost
↓
cleanup pending file handoff
↓
return user to home/upload flow
```

Files:

```txt
apps/web/src/lib/upload/fileHandoffManager.ts
apps/web/src/lib/pendingFileStore.ts
apps/web/src/lib/pendingFilePersistence.ts
apps/web/src/hooks/useInvestigation.ts
```

Auto-start effect:

```txt
useInvestigation Effect A — Auto-start from pending file
```

Checklist:

```txt
[ ] AUTO_START true but recoverFile() returns null shows clean error.
[ ] Browser limitation is explained: cannot retain file across hard refresh.
[ ] FC_SHOW_LOADING is cleared.
[ ] FC_HANDOFF_FIRED is cleared when stale.
[ ] Pending file meta is removed.
[ ] No infinite loading loop.
```

## 1.5 Smooth scroll and route transitions

User-level expectations:

```txt
Home scroll is smooth.
Landing logo scrolls to top.
Evidence page scrolls top on mount.
Result page scrolls top on session change.
Route overlays do not leave body locked.
```

Files:

```txt
HomeClient.tsx
EvidenceUploadClient.tsx
DynamicResultClient.tsx
ResultLayout.tsx
RouteExperience.tsx
GlobalLoadingOverlay.tsx
globals.css
```

Checklist:

```txt
[ ] /evidence mount sets body overflow to "".
[ ] /evidence calls window.scrollTo({ top: 0, behavior: "instant" }).
[ ] /result/[sessionId] plays stamp and reveals with motion.
[ ] Result session changes call window.scrollTo(0,0).
[ ] Modal close restores focus to CTA.
[ ] Loading overlays remove body data-fc-loading.
[ ] No stuck fixed overlay blocks result page after navigation.
```

---

# 2. Landing page → evidence analysis page full flow

## 2.1 Landing CTA open upload modal

### User-level flow

```txt
User clicks “Begin Analysis”
↓
Upload modal opens
↓
envelope-open sound plays
↓
demo/investigator auth starts in background
↓
user can drag/drop or browse file
```

Files:

```txt
apps/web/src/components/ui/HeroAuthActions.tsx
apps/web/src/components/evidence/UploadModal.tsx
apps/web/src/lib/upload/authService.ts
apps/web/src/lib/api/client.ts
```

HeroAuthActions behavior:

```txt
handleCTAClick()
→ setShowUpload(true)
→ clear selectedFile
→ clear handing-off state
→ clear local auth error
→ playSound("envelope-open")
→ authService.reset()
→ authService.ensureAuthenticated()
```

Auth flow:

```txt
authService.ensureAuthenticated()
→ client ensureAuthenticated()
→ GET /api/v1/auth/me
→ if 401/403 → autoLoginAsInvestigator()
→ POST /api/auth/demo
→ backend /api/v1/auth/login or demo auth proxy
```

Checklist:

```txt
[ ] CTA click opens modal immediately even if auth is still pending.
[ ] Auth failure appears inside modal as authError, not as app crash.
[ ] Upload route /evidence is prefetched.
[ ] Modal has DialogTitle and DialogDescription for accessibility.
[ ] onFocusOutside prevents accidental modal dismissal.
```

## 2.2 Upload modal file selection

### User-level flow

```txt
Upload modal visible
↓
User drags file over dropzone or clicks browse
↓
File picker opens
↓
File selected
↓
Client validates file type, extension, size
↓
click/drop sound plays
↓
Modal transitions to success/sealed state
```

Files:

```txt
UploadModal.tsx
fileValidation.ts
constants.ts
useSound.ts
animations.ts
```

Important UI details:

```txt
drag-over state changes visual dropzone
drag-leave clears drag state
invalid file shows error inside modal
isSecuring prevents duplicate file submit
motion/AnimatePresence handles upload→success transition
```

Checklist:

```txt
[ ] Drag/drop prevents browser opening the file.
[ ] relatedTarget guard prevents drag-leave flicker inside dropzone.
[ ] File input accepts ALLOWED_MIME_TYPES/extensions.
[ ] validateEvidenceFile result is shown to user.
[ ] Duplicate rapid selection is guarded.
[ ] Unsupported extension/type never reaches backend.
```

## 2.3 SHA-256 hash computation and upload success modal

### User-level flow

```txt
Valid file selected
↓
Client computes SHA-256
↓
Success modal says Evidence Sealed
↓
Preview is shown for image/video or generic file icon
↓
SHA-256 checksum preview appears
↓
Deploy Council button enabled only after hash is ready
```

Files:

```txt
HeroAuthActions.tsx
UploadSuccessModal.tsx
crypto/fileHash.ts
```

Hash flow:

```txt
handleFileSelected(file)
→ setSelectedFile(file)
→ setSelectedFileHash(null)
→ setHashError(null)
→ setIsHashComputing(true)
→ computeFileSha256(file)
→ setSelectedFileHash(result.hex)
→ setIsHashComputing(false)
```

Success modal states:

```txt
isHashComputing → “Calculating SHA-256...”
hashError → “Hash unavailable — reselect file”
fileSha256 → shortened hash display
```

Deploy button disabled when:

```txt
isHandingOff
isHashComputing
hashError exists
fileSha256 missing
```

Checklist:

```txt
[ ] SHA-256 is lowercase-normalized before upload.
[ ] Hash failure prevents analysis start.
[ ] User can reselect file.
[ ] Image object URL is revoked.
[ ] Video metadata duration loads without blocking.
[ ] Large file hash computation does not freeze UI badly.
[ ] UploadSuccessModal displays correct file category.
```

## 2.4 Deploy Council handoff to /evidence

### User-level flow

```txt
User clicks Deploy Council
↓
scan sound plays
↓
app ensures authentication
↓
file + client hash are prepared for handoff
↓
upload modal closes
↓
user navigates to /evidence
↓
global loading overlay begins
```

Files:

```txt
HeroAuthActions.tsx
fileHandoffManager.ts
pendingFileStore.ts
pendingFilePersistence.ts
loadingOverlayController.ts
useInvestigation.ts
```

Actual path:

```txt
UploadSuccessModal onStartAnalysis()
→ playSound("scan")
→ handleStartAnalysis()

handleStartAnalysis()
→ guard selectedFile and duplicate handoff ref
→ require selectedFileHash
→ authService.ensureAuthenticated()
→ fileHandoffManager.prepareUpload(selectedFile, { clientSha256 })
→ setShowUpload(false)
→ remove FC_HANDOFF_FIRED
→ router.push("/evidence")
```

Handoff should set/prepare:

```txt
__pendingFileStore.file
FC_PENDING_FILE_META
AUTO_START
FC_SHOW_LOADING
clientSha256
possibly persisted file fallback
```

Checklist:

```txt
[ ] Deploy Council cannot double-fire.
[ ] Auth failure resets isHandingOff.
[ ] Missing hash blocks start with toast.
[ ] Pending file store is populated before route change.
[ ] AUTO_START is set for /evidence.
[ ] FC_SHOW_LOADING is set for GlobalLoadingOverlay.
[ ] FC_HANDOFF_FIRED is removed before route push so /evidence can fire once.
```

---

# 3. Evidence analysis page and initial analysis full flow

## 3.1 /evidence page mount

### User-level flow

```txt
/evidence route loads
↓
If pending file exists, analysis starts automatically
↓
If active session exists, reconnects
↓
If neither exists, shows “No Evidence Queued”
```

Files:

```txt
apps/web/src/app/evidence/page.tsx
apps/web/src/components/pages/EvidenceUploadClient.tsx
apps/web/src/hooks/useInvestigation.ts
```

EvidenceUploadClient:

```txt
const investigation = useInvestigation(playSound)
```

Rendered states:

```txt
if investigation.wsConnectionError && !isReconnecting
  → ForensicErrorModal

if investigation.hasStartedAnalysis || investigation.handoffRecovering
  → AgentProgressDisplay + overlays + HITL modal

else
  → No Evidence Queued + Return Home button
```

Checklist:

```txt
[ ] Fresh /evidence without session does not crash.
[ ] Fresh /evidence without session provides Return Home.
[ ] Pending handoff starts exactly once.
[ ] Strict Mode double mount does not double-upload.
[ ] Agent progress display is protected by error boundary.
```

## 3.2 Auto-start pending upload

Main logic:

```txt
useInvestigation Effect A
```

Flow:

```txt
/evidence mounts
↓
if FC_HANDOFF_FIRED=1 and no pending file → clear stale flag
↓
if FC_HANDOFF_FIRED=1 → return
↓
recover pending file via fileHandoffManager.recoverFile()
↓
if no file but AUTO_START true → show “file selection was lost”
↓
validateEvidenceFile(pending)
↓
set FC_HANDOFF_FIRED=1
↓
setFile(pending)
↓
remove AUTO_START
↓
write FC_PENDING_FILE_META
↓
triggerAnalysis(pending)
```

Checklist:

```txt
[ ] FC_HANDOFF_FIRED prevents duplicate upload.
[ ] Stale FC_HANDOFF_FIRED is cleared when no file exists.
[ ] AUTO_START is removed after handoff begins.
[ ] Validation is repeated on evidence page.
[ ] Pending clientSha256 survives from handoff manager.
```

## 3.3 triggerAnalysis frontend upload

Main function:

```txt
useInvestigation.triggerAnalysis(targetFile)
```

Frontend sequence:

```txt
guard investigationInFlightRef
↓
abort previous arbiter control
↓
reset simulation hook
↓
clear investigation persistence
↓
set mime type
↓
play scan sound
↓
set isUploading true
↓
set phase initial
↓
startSimulation()
↓
generate investigatorId and caseId
↓
show loading overlay
↓
ensure auth
↓
create thumbnail for images
↓
get pending client SHA-256 or recompute
↓
POST /api/v1/investigate
↓
store session context
↓
connect WebSocket/live stream
```

Storage writes after backend responds:

```txt
INVESTIGATION_CTX
INVESTIGATION_CTX:{sessionId}
SESSION_ID
cookie SESSION_ID
FILE_NAME
FILE_NAME:{sessionId}
CASE_ID
INVESTIGATOR_ID
MIME_TYPE
MIME_TYPE:{sessionId}
PIPELINE_START
PIPELINE_START:{sessionId}
EVIDENCE_SHA256:{sessionId}
THUMBNAIL:{sessionId}
```

Checklist:

```txt
[ ] investigationInFlightRef blocks duplicate POST.
[ ] Old persisted state is cleared before new session.
[ ] MIME type is stored before progress render.
[ ] Image thumbnail is optional and never blocks upload.
[ ] Client SHA-256 is recomputed if missing.
[ ] Missing/recompute hash failure stops upload.
[ ] Backend content_hash is stored by session.
[ ] Session cookie is written for reset fallback.
```

## 3.4 Backend `/api/v1/investigate` intake

Main file:

```txt
apps/api/api/routes/investigation.py
```

Route:

```txt
POST /api/v1/investigate
```

Backend sequence:

```txt
validate case_id and investigator_id through InvestigationRequest
↓
read first 8192 bytes
↓
detect actual MIME
↓
PIL fallback MIME detection if octet-stream
↓
verify MIME in SUPPORTED_MIME_TYPES
↓
get applicable agents for MIME
↓
verify extension in SUPPORTED_EXTENSIONS
↓
verify exact MIME-extension match
↓
verify size limit
↓
rate limit investigation
↓
daily cost quota check
↓
generate backend session_id
↓
stream upload to incoming temp path
↓
compute server SHA-256
↓
verify client_sha256 format and equality
↓
dedup by case_id + content_hash
↓
register session metadata
↓
dispatch to worker queue or in-process pipeline
↓
return InvestigationResponse
```

Critical security and custody checks:

```txt
actual MIME detection, not just browser-provided type
extension allowlist
exact MIME-extension map
max file size while streaming
empty file rejection
client hash/server hash equality
dedup active session protection
session pre-registration before dispatch
worker liveness check
```

Checklist:

```txt
[ ] Browser MIME and backend MIME cannot diverge silently.
[ ] Renamed malicious file is rejected.
[ ] Oversized file is rejected while streaming.
[ ] Empty file rejected.
[ ] Client SHA-256 mismatch rejected.
[ ] Duplicate active investigation returns 409 with existing session id.
[ ] Stale dedup key clears when old session is inactive.
[ ] Worker unavailable returns 503 warmup/liveness message.
[ ] Response includes session_id, content_hash, detected_mime, applicable_agents.
```

## 3.5 Worker dispatch / pipeline start

Two modes:

```txt
settings.use_redis_worker = true
  → investigation_queue.submit()
  → worker service runs pipeline

settings.use_redis_worker = false
  → create ForensicCouncilPipeline in process
  → asyncio.create_task(run_investigation_task(...))
```

Files:

```txt
apps/api/orchestration/investigation_queue.py
apps/api/orchestration/worker.py
apps/api/orchestration/investigation_runner.py
apps/api/orchestration/pipeline.py
```

Checklist:

```txt
[ ] Docker dev has API, worker, Redis, Postgres, web running.
[ ] Worker heartbeat key is fresh.
[ ] Queue submit writes all required payload fields.
[ ] In-process mode sets active pipeline/task.
[ ] Pipeline metadata says running/queued before UI connects.
```

## 3.6 Live progress connection

Frontend files:

```txt
useInvestigation.ts
useSimulation.ts
api/client.ts
```

Backend files:

```txt
api/routes/_websocket.py
api/routes/sse.py
api/routes/_session_state.py
```

Frontend sequence:

```txt
startInvestigation returns sessionId
↓
connectWebSocket(sessionId)
↓
createLiveSocket(sessionId)
↓
WebSocket /api/v1/sessions/{sessionId}/live
↓
client waits for CONNECTED or AGENT_UPDATE bootstrap
↓
useSimulation processes messages into status, agentUpdates, completedAgents, pipelineThinking
```

Supported event types observed in client:

```txt
CONNECTED
AGENT_UPDATE
AGENT_COMPLETE
PIPELINE_PAUSED
PIPELINE_COMPLETE
ARBITER_UPDATE
REPORT_READY
HITL_CHECKPOINT
PIPELINE_QUARANTINED
```

Client filtering rules:

```txt
ignore messages from non-current session
ignore stale phase messages
ignore initial AGENT_COMPLETE during deep phase
ignore deep AGENT_COMPLETE during initial phase
pipeline-level agent_id=null updates go to pipelineMessage/pipelineThinking
```

Checklist:

```txt
[ ] WebSocket uses correct ws base through getWSBase().
[ ] Auth cookies are present before WebSocket opens.
[ ] WebSocket resolves only after CONNECTED or first update.
[ ] Reconnect closes old WebSocket and SSE.
[ ] Message phase filtering does not hide allowed cross-phase events.
[ ] AGENT_COMPLETE updates persist to INITIAL_AGENTS or DEEP_AGENTS.
[ ] Pipeline-level messages display separately from agent cards.
[ ] Connection error surfaces retry modal.
```

## 3.7 Initial analysis backend pipeline

Main file:

```txt
apps/api/orchestration/pipeline.py
apps/api/orchestration/pipeline_phases.py
```

High-level backend pipeline:

```txt
ForensicCouncilPipeline.run_investigation()
↓
_initialize_components()
↓
_ingest_evidence()
↓
session_manager.create_session()
↓
run_agents_concurrent()
↓
normalize agent results
↓
initial phase pauses for analyst decision or goes to arbiter/report depending decision flow
```

Component initialization:

```txt
Redis
Qdrant
Postgres
CustodyLogger
EvidenceStore
WorkingMemory
EpisodicMemory
InterAgentBus
SessionManager
AgentFactory
CouncilArbiter
SignalBus
```

Degradation behavior:

```txt
Redis unavailable → working memory fallback, degradation flag
Qdrant unavailable → episodic memory disabled, degradation flag
Postgres unavailable → custody/report persistence degraded, degradation flag
```

Evidence ingestion:

```txt
correct MIME if PIL detects mismatch
metadata includes original filename, content hash, size
for images: build image evidence profile and image agent tool plan
EvidenceStore.ingest()
custody ledger records artifact
```

Initial agent phase:

```txt
run_agents_concurrent()
→ instantiate supported agents
→ unsupported agents skipped/not applicable
→ run each supported agent investigation
→ broadcast tool progress through custody logger patch
→ collect AgentLoopResult
→ broadcast AGENT_COMPLETE
→ start arbiter pre-warm with phase 1 findings
→ await deep-analysis decision
```

Agents:

```txt
Agent1 image
Agent2 audio
Agent3 object
Agent4 video
Agent5 metadata
Council Arbiter
```

Checklist:

```txt
[ ] Each file MIME maps only to applicable agents.
[ ] Unsupported agents produce clean skipped status, not failure.
[ ] Agent factory receives evidence artifact.
[ ] InterAgentBus has evidence artifact.
[ ] Custody log broadcasts ACTION/tool updates.
[ ] Each tool update has tool_name, tools_done, analysis_phase.
[ ] Initial AGENT_COMPLETE includes analysis_phase="initial".
[ ] Failed agents are counted.
[ ] Majority failure aborts pipeline.
[ ] Arbiter pre-warm starts after initial findings.
[ ] Pipeline pauses for user choice after initial analysis.
```

## 3.8 Initial analysis UI completion state

User-level flow:

```txt
Agent cards animate/progress
↓
Agent complete cards reveal
↓
When initial agents done, analysis_done sound plays
↓
UI shows decision controls:
   accept/generate report
   or run deep analysis
```

Files:

```txt
AgentProgressDisplay.tsx
AgentStatusCard.tsx
AgentStatusSummary.tsx
ArbiterCard.tsx
useInvestigation.ts
```

Decision logic:

```txt
awaitingDecision =
  !isNavigating
  && !arbiterDeliberating
  && status === "awaiting_decision"
  && phase === "initial"

allAgentsDone initial =
  status === "awaiting_decision"
  || expectedCompletedCount >= expectedAgentIds.size
```

Checklist:

```txt
[ ] Initial completion does not require skipped unsupported agents.
[ ] expectedAgentIds comes from supportedAgentIdsForMime(mimeType).
[ ] Sound fires once via analysisCompleteSoundedRef.
[ ] Buttons disabled during navigation/resume.
[ ] HITL modal can appear over progress UI.
```

---

# 4. Deep analysis full flow

## 4.1 User starts deep analysis

### User-level flow

```txt
Initial analysis complete
↓
User chooses Deep Analysis
↓
click sound + scan sound
↓
UI phase changes to deep
↓
initial findings are saved
↓
agent cards clear
↓
backend resumes pipeline with deep_analysis=true
↓
deep tool progress streams
↓
deep agent cards complete
↓
user can then view final results
```

Frontend function:

```txt
useInvestigation.handleDeepAnalysis()
```

Sequence:

```txt
guard investigationInFlightRef/resumeInFlightRef
↓
play click and scan
↓
storage IS_DEEP=true
↓
sid = SESSION_ID
↓
filter current completed agents excluding skipped
↓
storage RESULT_PHASE:{sid}=deep
↓
storage INITIAL_AGENTS:{sid}=initial snapshot
↓
sessionOnly FC_RESUME_REQUESTED:{sid}=deep
↓
remove DEEP_AGENTS:{sid}
↓
clear pipeline thinking
↓
clear completed agents
↓
set phase deep
↓
setSimulationPhase("deep")
↓
resumeInvestigation(true)
```

API path:

```txt
POST /api/v1/sessions/{sessionId}/resume
body deep_analysis=true
```

Checklist:

```txt
[ ] Guard prevents double deep-analysis POST.
[ ] Initial agents saved before clearing UI.
[ ] Skipped agents excluded from initial snapshot.
[ ] RESULT_PHASE is deep before result page.
[ ] DEEP_AGENTS old stale data removed.
[ ] active phase changes before deep stream events arrive.
[ ] On failure, phase rolls back to initial.
[ ] FC_RESUME_REQUESTED is cleared/rolled back on failure.
```

## 4.2 Backend resume into deep analysis

Backend route:

```txt
apps/api/api/routes/sessions.py
POST /api/v1/sessions/{session_id}/resume
```

Backend responsibilities:

```txt
verify ownership
verify pipeline status can resume
determine decision key:
  initial_to_deep if deep_analysis=true
  deep_to_report if deep_analysis=false after deep
prevent duplicate resume through Redis lock/decision key
write resume decision
update metadata status paused_resume_requested/resumed
broadcast resume progress
```

Pipeline wait gate:

```txt
pipeline_phases._await_deep_analysis_decision()
```

Expected backend sequence:

```txt
initial agents complete
↓
pipeline waits at initial_to_deep decision key
↓
resume endpoint writes deep_analysis=true
↓
pipeline invalidates initial arbiter pre-warm if needed
↓
run deep analysis for supported agents
```

Checklist:

```txt
[ ] Resume endpoint is idempotent for duplicate clicks.
[ ] Cannot resume completed/invalid sessions.
[ ] Decision key names match pipeline phase.
[ ] initial_to_deep and deep_to_report keys cannot race.
[ ] Metadata status/brief updates allow arbiter-status polling.
```

## 4.3 Deep agent execution

Backend file:

```txt
apps/api/orchestration/pipeline_phases.py
```

Deep execution:

```txt
_run_deep_with_fallback(aid)
→ _run_agent_deep_only()
→ agent.run_deep_investigation()
→ progress monitor polls working memory
→ broadcasts deep progress every ~3s
→ returns AgentLoopResult
```

After deep agents:

```txt
combine Phase 1 + Phase 2 evidence
normalize deep results
start/restart arbiter pre-warm with full findings
pause for final-report request
```

Checklist:

```txt
[ ] Deep AGENT_UPDATE messages include analysis_phase="deep".
[ ] Deep AGENT_COMPLETE messages include analysis_phase="deep".
[ ] Initial-phase complete messages are ignored by frontend during deep.
[ ] Deep progress monitor stops after completion/failure.
[ ] Deep findings do not duplicate initial findings.
[ ] Cross-modal fusion/telemetry data is attached when applicable.
[ ] Arbiter pre-warm is refreshed with combined findings.
```

## 4.4 Deep completion UI

Frontend derived state:

```txt
allAgentsDone deep =
  status === "complete"
  || expectedCompletedCount >= expectedAgentIds.size
```

But the deep flow should end in a report-request decision, not immediately navigate unless the user chooses results.

User-level expected:

```txt
Deep agents finish
↓
analysis_done sound plays once
↓
View Results button available
↓
User clicks View Results
```

Checklist:

```txt
[ ] Completion sound fires once for deep phase.
[ ] View Results button is not shown before expected deep agents complete.
[ ] Expected agent count respects MIME.
[ ] Deep completed agents persist to DEEP_AGENTS:{sid}.
```

---

# 5. Report generation, result page, export options

There are two report entry paths:

```txt
A. Initial analysis → Accept Analysis / Generate Report
B. Deep analysis → View Results
```

## 5.1 Initial analysis → final report

Frontend function:

```txt
useInvestigation.handleAcceptAnalysis()
```

Sequence:

```txt
guard isNavigating/resumeInFlight/investigationInFlight
↓
play click
↓
play arbiter_start
↓
storage IS_DEEP=false
↓
storage RESULT_PHASE:{sid}=initial
↓
storage INITIAL_AGENTS:{sid}=completedAgents snapshot
↓
sessionOnly FC_RESUME_REQUESTED:{sid}=initial
↓
arbiterControl.abort()
↓
set isNavigating true
↓
show ArbiterDeliberationOverlay
↓
set live text “Compiling findings”
↓
resumeInvestigation(false)
↓
waitForFinalReport()
↓
set FC_REPORT_READY:{sid}=1
↓
set FC_ARBITER_TRANSITIONING:{sid}=1
↓
document.body data-fc-loading=1
↓
router.push(/result/{sid})
```

Checklist:

```txt
[ ] Initial report path sets RESULT_PHASE initial.
[ ] resumeInvestigation(false) does not accidentally trigger deep.
[ ] Arbiter overlay has minimum display duration.
[ ] waitForFinalReport handles complete arbiter but delayed report availability.
[ ] If wait times out, result page still opens and polls.
[ ] On failure, FC_REPORT_READY and transition flags are cleared.
```

## 5.2 Deep analysis → final report

Frontend function:

```txt
useInvestigation.handleViewResults()
```

Sequence:

```txt
guard navigation/resume
↓
play click
↓
play arbiter_start
↓
storage RESULT_PHASE:{sid}=deep
↓
storage DEEP_AGENTS:{sid}=completedAgents
↓
set isNavigating true
↓
show ArbiterDeliberationOverlay
↓
getArbiterStatus(sid)
↓
if not complete → resumeInvestigation(false)
↓
waitForFinalReport()
↓
set FC_REPORT_READY and transition flags
↓
body data-fc-loading=1
↓
router.push(/result/{sid})
```

Checklist:

```txt
[ ] Deep path stores DEEP_AGENTS before navigation.
[ ] Deep path keeps RESULT_PHASE deep.
[ ] It only calls resumeInvestigation(false) if arbiter not already complete.
[ ] It does not overwrite initial snapshot.
[ ] Result page reads deep phase correctly.
```

## 5.3 Backend final arbiter/report generation

Backend files:

```txt
apps/api/orchestration/pipeline.py
apps/api/agents/arbiter.py
apps/api/core/final_report_groq_refiner.py
apps/api/core/deterministic_report_builder.py
apps/api/orchestration/pipeline_enrichment.py
```

Backend sequence:

```txt
pipeline._run_deliberation()
↓
wait for arbiter pre-warm or run synchronous pre-warm fallback
↓
broadcast final arbiter status: deliberating
↓
arbiter.finalise_from_cache(use_llm=...)
↓
if timeout and LLM used:
    add degradation flag
    fallback finalise_from_cache(use_llm=false)
↓
broadcast status: synthesizing
↓
enrich_report()
↓
append degradation flags if any
↓
arbiter.sign_report()
↓
session_manager.set_final_report()
↓
cache final report in session state/Redis
↓
broadcast final arbiter status complete
↓
custody log REPORT_SIGNED
↓
broadcast REPORT_READY
```

Report should contain:

```txt
report_id
session_id
case_id
overall_verdict
overall_confidence
manipulation_probability
overall_error_rate
confidence_std_dev
verdict_sentence
executive_summary
key_findings
per_agent_findings
per_agent_summary
per_agent_metrics
agent_summaries
cross_modal_fusion
degradation_flags
reliability_note
uncertainty_statement
analysis_coverage_note
skipped_agents
signing/integrity data
```

Checklist:

```txt
[ ] Arbiter has full initial findings for initial report.
[ ] Arbiter has initial + deep findings for deep report.
[ ] Pre-warm cache is invalidated when deep analysis changes findings.
[ ] Timeout fallback still produces report.
[ ] Degradation flag only added for actual tool/LLM/persistence failure.
[ ] Report enrichment failure does not prevent report but flags reliability.
[ ] Signed report is cached before REPORT_READY.
[ ] /arbiter-status returns complete only when report can be fetched soon.
```

## 5.4 Result page route and reveal

Files:

```txt
apps/web/src/app/result/[sessionId]/page.tsx
apps/web/src/components/pages/DynamicResultClient.tsx
apps/web/src/components/result/ResultLayout.tsx
apps/web/src/hooks/useResult.ts
```

User-level sequence:

```txt
/result/[sessionId] loads
↓
stamp sound plays
↓
white flash/reveal animation fades
↓
ResultLayout starts in arbiter/loading/ready state
↓
useResult hydrates session metadata from storage
↓
report query polls /api/v1/sessions/{sid}/report
↓
arbiter status polls /api/v1/sessions/{sid}/arbiter-status
↓
when report complete, result content reveals
```

useResult initial hydration:

```txt
sessionId = route param or SESSION_ID
ready = FC_REPORT_READY:{sid}
ctx = INVESTIGATION_CTX:{sid}
deep = RESULT_PHASE:{sid}
thumbnail = THUMBNAIL:{sid}
mimeType = ctx.mime_type or MIME_TYPE
pipelineStartAt = ctx.pipeline_start
fileName = ctx.file_name
agentTimeline = DEEP_AGENTS or INITIAL_AGENTS depending phase
```

Checklist:

```txt
[ ] Direct visit /result/[sid] with storage present renders correct metadata.
[ ] Direct visit with no storage still fetches report by route sid.
[ ] FC_REPORT_READY skips long arbiter overlay.
[ ] FC_ARBITER_TRANSITIONING is removed on result mount.
[ ] body data-fc-loading is removed after reveal guard.
[ ] React Query polls report while 202 in_progress.
[ ] Arbiter status polling stops when report complete.
[ ] 404/not_found eventually shows session-expired/error, not infinite spinner.
```

## 5.5 Result UI sections

File:

```txt
ResultLayout.tsx
```

Result content order:

```txt
EvidenceHeader
VerdictSection
DegradationBanner, only if degradation_flags exists
IntelligenceBrief
AgentsStrip
AgentAnalysisTab
DeepModelTelemetry, only if cross_modal_fusion exists
FindingsMetadata
ExecutionTimeline
ReportIntegrity
PageNavigation
```

Tabs:

```txt
Analysis
History
```

History:

```txt
HistoryPanel
→ selectSession(sid)
→ set active tab analysis
→ useResult fetches selected report
```

Checklist:

```txt
[ ] Empty report sections do not render broken blocks.
[ ] DegradationBanner only appears when flags length > 0.
[ ] Deep telemetry only appears when cross_modal_fusion has data.
[ ] activeAgentIds excludes purely skipped/not-applicable agents.
[ ] Agent findings do not show skipped/template-only data as evidence.
[ ] History selection does not overwrite original current badge incorrectly.
```

## 5.6 Result export options

Export menu file:

```txt
apps/web/src/components/result/ResultLayout.tsx
```

Options:

```txt
PDF Report
Word (.docx)
JSON Export
```

PDF path:

```txt
GET /api/v1/sessions/{sessionId}/report/pdf
```

DOCX path:

```txt
GET /api/v1/sessions/{sessionId}/report/docx
```

JSON path:

```txt
client-side Blob(JSON.stringify(report, null, 2))
```

Backend export files/routes:

```txt
apps/api/api/routes/sessions.py
apps/api/core/pdf_report_exporter.py
apps/api/core/docx_report_exporter.py
```

Expected export behavior:

```txt
PDF success → downloads .pdf
PDF fallback → may download .html or .json with warning
PDF failure → falls back to JSON export
DOCX success → downloads .docx
DOCX 503 → warning that python-docx unavailable
JSON → always client-side if report exists
```

Checklist:

```txt
[ ] Export dropdown only appears in ready state with report.
[ ] Export menu has keyboard Escape and Arrow navigation.
[ ] Outside click closes menu.
[ ] Export button disables while exporting.
[ ] PDF fallback extension uses Content-Type and X-PDF-Fallback header.
[ ] JSON filename uses report_id/session id.
[ ] Failed PDF does not silently do nothing.
[ ] DOCX unavailable warning is visible.
```

---

# 6. Back from result page to result page, and back to home page

## 6.1 Browser back/forward between evidence and result

Expected:

```txt
Result page is open
↓
Browser back to /evidence
↓
EvidenceUploadClient mounts
↓
if session still exists and report complete → routes back to /result/[sid]
↓
if session running → reconnects stream
↓
if no session → no evidence queued
```

Key logic:

```txt
useInvestigation Effect B
→ getArbiterStatus(existingSessionId)
→ if complete: router.push(/result/{sid})
→ else connect stream
```

Checklist:

```txt
[ ] Back from result to evidence does not restart upload.
[ ] Complete session redirects back to result.
[ ] Running session reconnects.
[ ] If reset happened, evidence shows no queued evidence.
```

## 6.2 Result history: result page to another result page

Expected:

```txt
User opens History tab
↓
Clicks prior session
↓
useResult.selectSession(sid)
↓
SESSION_ID is updated
↓
report state resets to arbiter
↓
metadata loads from session-specific storage
↓
report fetch starts for selected sid
↓
Analysis tab displays selected report
```

Checklist:

```txt
[ ] Selecting history item fetches correct report by sid.
[ ] Initial/deep phase is read from RESULT_PHASE:{sid}.
[ ] Agent timeline corresponds to that phase.
[ ] Current badge still refers to original session, not selected session.
[ ] Missing session metadata gracefully shows Unknown File.
```

## 6.3 Result page → new upload

Button file:

```txt
PageNavigation.tsx
```

Hook:

```txt
useResult.handleNew()
→ _resetAndNavigate("/?upload=1")
```

Flow:

```txt
play reset
↓
resetActiveInvestigation()
↓
router.push("/?upload=1")
↓
HomeClient/HeroAuthActions sees upload=1
↓
opens UploadModal
↓
removes upload query param via history.replaceState
```

Checklist:

```txt
[ ] Backend current session is terminated.
[ ] Local session state cleared but history preserved.
[ ] Home opens upload modal automatically.
[ ] FC_NO_RECONNECT prevents stale reconnect.
[ ] Query param upload=1 is removed after opening.
```

## 6.4 Result page → home

Hook:

```txt
useResult.handleHome()
→ _resetAndNavigate("/#hero")
```

Flow:

```txt
play reset
↓
resetActiveInvestigation()
↓
router.push("/#hero")
↓
home page loads at hero
↓
no modal opens unless upload flag exists
```

Checklist:

```txt
[ ] Result Home clears active session.
[ ] Preserves history.
[ ] Does not leave upload modal open.
[ ] Does not reconnect stale session.
[ ] Scroll lands at hero/top.
```

---

# 7. HITL checkpoint flow

This is an important flow not listed explicitly.

## User-level flow

```txt
Agent needs human review
↓
HITLCheckpointModal appears
↓
User accepts/rejects/provides decision
↓
Decision is submitted
↓
Modal closes
↓
Agent/pipeline continues
```

Frontend:

```txt
EvidenceUploadClient.tsx
HITLCheckpointModal.tsx
useInvestigation.handleHITLDecision()
```

Backend:

```txt
POST /api/v1/hitl/decision
apps/api/api/routes/hitl.py
pipeline.handle_hitl_decision()
```

Flow:

```txt
HITL_CHECKPOINT event or custody HITL broadcast
↓
useSimulation sets hitlCheckpoint
↓
modal opens
↓
submitHITLDecision()
↓
backend verifies checkpoint/session
↓
decision is cached/published
↓
pipeline resolves checkpoint
↓
modal dismisses
↓
success-chime sound
```

Checklist:

```txt
[ ] HITL modal appears over progress UI.
[ ] Submit is disabled during isSubmittingHITL.
[ ] Decision contains session_id, checkpoint_id, agent_id, decision, note.
[ ] Duplicate submit is blocked.
[ ] Failed submit shows toast.
[ ] Dismiss does not accidentally resolve checkpoint unless intended.
```

---

# 8. Auth and session-expiry flow

## Auth flow

Frontend:

```txt
authService.ensureAuthenticated()
client.ensureAuthenticated()
apiFetch()
handleAuthError()
autoLoginAsInvestigator()
```

Backend:

```txt
api/routes/auth.py
```

Expected:

```txt
GET /api/v1/auth/me
↓
if valid: continue
↓
if 401/403: demo login
↓
cookies set
↓
mutation headers include CSRF where required
```

Session expiry:

```txt
apiFetch receives 401
↓
clear access_token/fc_session cookies
↓
dispatch fc:session-expired
↓
HeroAuthActions handles event
↓
resetActiveInvestigation()
↓
router.push("/?session_expired=true")
↓
toast appears on home
```

Checklist:

```txt
[ ] 401 during API fetch dispatches session-expired.
[ ] Session expired does not leave modal/loading stuck.
[ ] session_expired query is removed after toast.
[ ] Auth retry does not infinite-loop.
[ ] WebSocket reconnect refreshes auth or surfaces error cleanly.
```

---

# 9. Error and recovery flows

## 9.1 Upload/backend start failure

Possible failures:

```txt
auth failure
client hash missing
client hash mismatch backend
unsupported file
worker unavailable/warming
rate limit/quota
network failure
duplicate investigation
```

Expected frontend behavior:

```txt
auth failure → toast + modal auth error
hash missing → toast, no upload
backend 400 → destructive toast + reset simulation
worker 503 → warmup toast + retry in 15s
duplicate 409 → reconnect to existing session
network/ws failure → ForensicErrorModal
```

Checklist:

```txt
[ ] Every failure clears isHandingOff/isUploading appropriately.
[ ] FC_SHOW_LOADING is removed on failure.
[ ] Pending file cleanup happens after unrecoverable upload failure.
[ ] Duplicate investigation path does not delete existing session.
[ ] Worker warmup retry does not create multiple timers.
```

## 9.2 Stream failure

Flow:

```txt
connectWebSocket fails
↓
setWsConnectionError
↓
clear loading overlay
↓
remove SESSION_ID if new connection failed
↓
show ForensicErrorModal
↓
Retry calls retryWsConnection()
```

Checklist:

```txt
[ ] Reconnect uses existing sid when available.
[ ] If no sid but file still exists, retry starts upload again.
[ ] Error modal Home calls handleNewUpload.
[ ] Error modal Retry does not duplicate WebSockets.
```

## 9.3 Result report failure

Flow:

```txt
useResult report query fails
↓
if 404 and arbiterComplete → /session-expired
↓
else state=error
↓
ForensicErrorModal shown
```

Checklist:

```txt
[ ] 202 in_progress keeps polling.
[ ] Temporary report fetch error retries 3 times.
[ ] Arbiter status not_found waits up to 30s before error.
[ ] Error modal home/new reset correctly.
```

---

# 10. Storage and key integrity checklist

Important storage keys:

```txt
SESSION_ID
INVESTIGATION_CTX
INVESTIGATION_CTX:{sessionId}
FILE_NAME
FILE_NAME:{sessionId}
CASE_ID
INVESTIGATOR_ID
MIME_TYPE
MIME_TYPE:{sessionId}
PIPELINE_START
PIPELINE_START:{sessionId}
EVIDENCE_SHA256:{sessionId}
THUMBNAIL
THUMBNAIL:{sessionId}
INITIAL_AGENTS:{sessionId}
DEEP_AGENTS:{sessionId}
RESULT_PHASE:{sessionId}
IS_DEEP
HISTORY

AUTO_START
FC_SHOW_LOADING
FC_HANDOFF_FIRED
FC_PENDING_FILE_META
FC_OPEN_UPLOAD_ONCE
FC_NO_RECONNECT
FC_REPORT_READY:{sessionId}
FC_ARBITER_TRANSITIONING:{sessionId}
FC_RESUME_REQUESTED:{sessionId}
```

Checklist:

```txt
[ ] Session-specific keys are always written with :{sessionId}.
[ ] Generic fallback keys do not override selected history session.
[ ] Result phase is written before result navigation.
[ ] Initial and deep agent arrays are not mixed.
[ ] History persists through reset.
[ ] clearAllForensicKeys does not delete unrelated app/browser data.
[ ] Storage quota failure shows warning event.
```

---

# 11. Full AI-tool audit prompt you can use

Use this as the instruction for another AI coding tool:

```txt
You are auditing the Forensic Council app end to end. Trace the real code paths, do not infer generic behavior.

Goal:
Ensure the full runtime flow is intact from landing page → upload modal → file selection → hash/sealed modal → evidence analysis page → initial analysis → optional deep analysis → report generation → result page → export → history/result switching → back home/new upload/reset. The app must survive refresh, hard refresh, browser back/forward, WebSocket reconnects, session expiry, and backend worker warmup.

Audit these files first:
- apps/web/src/app/layout.tsx
- apps/web/src/app/page.tsx
- apps/web/src/app/evidence/page.tsx
- apps/web/src/app/result/[sessionId]/page.tsx
- apps/web/src/components/pages/HomeClient.tsx
- apps/web/src/components/pages/EvidenceUploadClient.tsx
- apps/web/src/components/pages/DynamicResultClient.tsx
- apps/web/src/components/ui/GlobalNavbar.tsx
- apps/web/src/components/ui/GlobalLoadingOverlay.tsx
- apps/web/src/components/ui/HeroAuthActions.tsx
- apps/web/src/components/evidence/UploadModal.tsx
- apps/web/src/components/evidence/UploadSuccessModal.tsx
- apps/web/src/hooks/useInvestigation.ts
- apps/web/src/hooks/useSimulation.ts
- apps/web/src/hooks/useResult.ts
- apps/web/src/lib/appReset.ts
- apps/web/src/lib/api/client.ts
- apps/web/src/lib/upload/fileHandoffManager.ts
- apps/web/src/lib/upload/authService.ts
- apps/web/src/lib/crypto/fileHash.ts
- apps/web/src/lib/fileValidation.ts
- apps/web/src/lib/storage.ts
- apps/web/src/lib/storageKeys.ts

Then audit backend:
- apps/api/api/routes/auth.py
- apps/api/api/routes/investigation.py
- apps/api/api/routes/sessions.py
- apps/api/api/routes/_websocket.py
- apps/api/api/routes/sse.py
- apps/api/api/routes/hitl.py
- apps/api/api/routes/_session_state.py
- apps/api/orchestration/pipeline.py
- apps/api/orchestration/pipeline_phases.py
- apps/api/orchestration/investigation_queue.py
- apps/api/orchestration/worker.py
- apps/api/agents/*
- apps/api/core/final_report_groq_refiner.py
- apps/api/core/deterministic_report_builder.py
- apps/api/core/pdf_report_exporter.py
- apps/api/core/docx_report_exporter.py

For each flow below, produce:
1. Actual code path.
2. Expected user-visible behavior.
3. State/storage keys read and written.
4. API calls and backend routes.
5. WebSocket/SSE events involved.
6. Race conditions and duplicate-submit risks.
7. Refresh/hard-refresh behavior.
8. Broken or redundant code.
9. Exact file-level fixes with code snippets.
10. Tests to add.

Flows:
A. App load, landing render, navbar behavior, smooth scroll, route transition, global overlays.
B. Navbar universal reset from home/evidence/result, including backend session DELETE and local cleanup.
C. Landing CTA → auth warmup → upload modal.
D. Upload modal → drag/drop/file picker → validation → SHA-256 → success modal.
E. Success modal → Deploy Council → pending file handoff → /evidence.
F. /evidence auto-start pending file exactly once, including Strict Mode double mount.
G. Backend /api/v1/investigate intake: MIME, extension, size, hash, dedup, quota, worker dispatch.
H. WebSocket/SSE live progress connection, reconnect, stale phase filtering.
I. Initial analysis agent execution, unsupported-agent skips, HITL, agent completion, initial decision gate.
J. Initial report generation path through handleAcceptAnalysis and backend arbiter.
K. Deep analysis path through handleDeepAnalysis, resume endpoint, deep agent execution, deep completion.
L. Deep result generation through handleViewResults and backend arbiter.
M. Result page loading, arbiter polling, report polling, reveal animation, metadata hydration.
N. Result history tab and selecting previous sessions.
O. Export PDF/DOCX/JSON and backend export fallbacks.
P. Browser back/forward between result/evidence/home.
Q. Hard refresh during upload handoff, running analysis, completed analysis, and result page.
R. Session expiry/auth failure.
S. Worker warmup, Redis/Postgres/Qdrant degradation, report fallback behavior.
T. Any missing flows, dead code, duplicate state, or state keys that can cause runtime breakage.

Mark each flow:
- PASS
- PARTIAL
- BROKEN
- RISK

Do not give a high-level summary only. Provide exact files, functions, state keys, endpoint names, and concrete patches.
```

---

# 12. Services to restart after fixes in Docker dev mode

For frontend-only fixes:

```bash
docker compose -f infra/docker-compose.dev.yml restart web
```

For backend route/pipeline/agent fixes:

```bash
docker compose -f infra/docker-compose.dev.yml restart api worker
```

For shared config/env/dependency changes:

```bash
docker compose -f infra/docker-compose.dev.yml up -d --build web api worker
```

For Redis/session-state issues during testing:

```bash
docker compose -f infra/docker-compose.dev.yml restart redis api worker web
```

For full clean dev restart:

```bash
docker compose -f infra/docker-compose.dev.yml down
docker compose -f infra/docker-compose.dev.yml up -d --build
```
