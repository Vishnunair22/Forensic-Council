FLOW B: "Authorize Deep Analysis" → Final Report Generation
Phase B-1 — User Clicks "Authorize Deep Analysis"
File: apps/web/src/hooks/useInvestigation.ts → handleDeepAnalysis()
Step-by-step:

Guard check: investigationInFlightRef.current || resumeInFlightRef.current — prevent double-submit.
Sets both flight refs to true.
playSound("click") + playSound("scan").
storage.setItem(STORAGE_KEYS.IS_DEEP, "true").
Writes per-session keys: RESULT_PHASE:{sid}="deep", INITIAL_AGENTS:{sid}=completedAgentsRef.current (snapshot of Phase 1 results).
Deletes DEEP_AGENTS:{sid} (clean slate for deep phase).
clearPipelineThinking() + clearCompletedAgents() — clears UI agent cards for re-population.
setPhase("deep"), setSimulationPhase("deep").
Calls resumeInvestigation(true) (deep=true).


Phase B-2 — resumeInvestigation(deep=true) — Frontend Resume Call
File: apps/web/src/hooks/useSimulation.ts → resumeInvestigation()
Step-by-step:

Determines expectedPhase:

If status === "awaiting_decision" → "initial"
If status === "awaiting_deep_report" → "deep"


POST /api/v1/sessions/{session_id}/resume with body: { deep_analysis: true, expected_phase: "initial" }.
On success: resumeSucceededRef.current = true. Status held at current value until next WS message.


Phase B-3 — Backend Resume Endpoint
File: apps/api/api/routes/sessions.py → resume_investigation()
Step-by-step:

Validates session_id format.
Fetches metadata = get_active_pipeline_metadata(session_id) from Redis.
Verifies session ownership (investigator_id == current_user.user_id).
Phase gate token check — if expected_phase="initial", verifies pipeline_status == "awaiting_decision". Returns 409 if mismatch.
Determines decision_key:

awaiting_decision → forensic:session:resume_decision:{session_id}:initial_to_deep
awaiting_deep_report → forensic:session:resume_decision:{session_id}:deep_to_report


Idempotency check: if key already exists in Redis → return "already_resumed".
Atomic Redis pipeline: SET decision_key decision_payload EX 14400 + PUBLISH forensic:notify_decision payload.
Gets in-process pipeline via get_active_pipeline(session_id).
If pipeline found in-process:

pipeline.run_deep_analysis_flag = True
pipeline.deep_analysis_decision_event.set() — unblocks the waiting coroutine in Phase A-7 step 6.
pipeline.invalidate_pre_warm() — cancels Phase-1 pre-warm task, clears arbiter cache.


Broadcasts ARBITER_UPDATE with "Deep analysis requested. Dispatching expanded forensic checks.".
Updates Redis metadata status to "deep_analysis_requested".
Returns { status: "resumed", deep_analysis: true }.


Phase B-4 — Pipeline Resumes: Deep Phase Agents
File: apps/api/orchestration/pipeline_phases.py → run_agents_concurrent() (continuation after _await_deep_analysis_decision())
Step-by-step:

_await_deep_analysis_decision() returns True (deep_analysis flag set).
Broadcasts AGENT_UPDATE with status="processing", analysis_phase="deep" — frontend clears initial agent cards and prepares for deep phase display.
Working memory clear — working_memory.clear(session_id, agent_id) for each agent — prevents carry-over from Phase 1.
Context seeding from Phase 1: Finds Agent1's visual_evidence_profile finding from Phase 1 → injects into other agents via inter_agent_bus.set_visual_profile() and agent.inject_agent1_context(). Sets context_event.
Phase 2 staggered deep runs (all agents, idx * 4.0s stagger to avoid Gemini slot contention):

_run_agent_deep_only(pipeline, agent, agent_id, initial_findings) for each agent.
Each agent: calls agent.run_deep_investigation() with expanded tool set.
Tools run: adversarial checks, deeper ML models, frequency domain analysis, neural fingerprinting, cross-modal comparisons etc.
Per-tool progress monitor polls working memory every 3s, broadcasts "running" status updates.
On complete: broadcasts AGENT_COMPLETE with analysis_phase="deep" and deep-only findings.
Deep findings tagged with metadata.analysis_phase="deep".


Phase-2 pre-warm — asyncio.create_task(_run_arbiter_pre_warm(deep_norm, case_id, suppress_broadcasts=True)) — starts background arbiter computation with all Phase 1 + Phase 2 findings.
_await_deep_report_request():

Sets pipeline._awaiting_user_decision = True again.
Broadcasts PIPELINE_PAUSED with status="awaiting_deep_report" and deep_results_ready=True.
Polls forensic:session:resume_decision:{session_id}:deep_to_report in Redis every 2s.
Blocks here until user clicks "View Results".




Phase B-5 — Frontend: Deep Phase UI State
Files: useSimulation.ts, AgentProgressDisplay.tsx, EvidenceUploadClient.tsx
Step-by-step:

WebSocket sends PIPELINE_PAUSED with status="awaiting_deep_report" → frontend sets status="complete" (deep phase done, awaiting user action).
allAgentsDone becomes true (phase="deep", status="complete" or expected agent count reached).
playSound("analysis_done") fires.
AgentProgressDisplay shows deep phase agent cards + "View Results" button.
HITLCheckpointModal may have fired during deep phase for individual agent decisions.


Phase B-6 — User Clicks "View Results"
File: apps/web/src/hooks/useInvestigation.ts → handleViewResults()
Step-by-step:

Guard: isNavigating || resumeInFlightRef.current.
Sets resumeInFlightRef=true, isNavigating=true.
playSound("click") + playSound("arbiter_start").
Writes RESULT_PHASE:{sid}="deep", DEEP_AGENTS:{sid}=completedAgentsRef.current.
setArbiterDeliberating(true) → shows ArbiterDeliberationOverlay (full-screen frosted-glass overlay with live text).
setArbiterLiveText(UI_STRINGS.FINAL_SYNTHESIS).
Checks getArbiterStatus(sid) — if already complete, skips re-resume.
Calls resumeInvestigation(false) — submits deep_analysis=false, expected_phase="deep".
Starts waitForFinalReport(sid, setArbiterLiveText, ARBITER_WAIT_MAX_MS, signal) polling loop.


Phase B-7 — Backend: Final Arbiter Deliberation
Files involved:

apps/api/api/routes/sessions.py → resume_investigation() (deep_analysis=false, expected_phase="deep")
apps/api/orchestration/pipeline_phases.py → _await_deep_report_request() returns
apps/api/orchestration/pipeline.py → _run_deliberation()
apps/api/agents/arbiter.py → CouncilArbiter.finalise_from_cache()
apps/api/agents/arbiter.py → CouncilArbiter.deliberate()
apps/api/agents/arbiter_verdict.py — ForensicReport, scoring functions
apps/api/agents/arbiter_narrative.py — ArbiterNarrativeMixin.deliberate_narratives()
apps/api/core/deterministic_report_builder.py — fallback report generation
apps/api/core/final_report_groq_refiner.py — Groq LLM narrative synthesis
apps/api/core/cross_modal_fusion.py — fuse() — cross-agent finding correlation
apps/api/core/signing.py — ECDSA key store + report signing
apps/api/core/calibration.py — confidence calibration
apps/api/orchestration/pipeline_enrichment.py — enrich_report()
apps/api/core/custody_chain.py — chain-of-custody verification

Step-by-step:

Resume endpoint receives deep_analysis=false, verifies pipeline_status == "awaiting_deep_report".
Writes to forensic:session:resume_decision:{session_id}:deep_to_report.
pipeline.deep_analysis_decision_event.set() → _await_deep_report_request() returns.
_run_deliberation(arbiter_results, case_id, session_id):

Cancels any leftover pre-warm task, re-assigns _pre_warm_agent_results.
Broadcasts "Compiling final report from agent findings.".
Calls arbiter.finalise_from_cache(use_llm=False, artifact_mime) with 90-second timeout.


finalise_from_cache():

Awaits pre-warm background task (up to 30s) — this is the Phase-2 pre-warm started in B-4 step 6.
If pre-warm report available and use_llm=False → returns cached report directly (fast path).
Otherwise calls arbiter.deliberate(agent_results, case_id, use_llm=False).


arbiter.deliberate():

Iterates all agent findings.
Calls evidence_verdict_of(), confidence_of(), assign_severity_tier() per finding.
cross_agent_comparison() — detects agreements/contradictions across agents.
cross_modal_fuse() (from core/cross_modal_fusion.py) — correlates multi-modal findings.
calculate_manipulation_probability() — weighted scoring.
Determines overall_verdict (AUTHENTIC / MANIPULATED / INCONCLUSIVE / REVIEW REQUIRED).
Computes per_agent_metrics (error rates, confidence scores).
If use_llm=True (not in this path): calls Groq via ArbiterNarrativeMixin.deliberate_narratives().
Returns ForensicReport.


enrich_report(pipeline, report, session_id, artifact, agent_results):

Verifies custody chain integrity.
Attaches content_hash, applicable_agent_count, analysis_coverage_note.
Sets is_deep_analysis=True.


arbiter.sign_report(report):

Calls core/signing.py keystore → get_or_create(AgentID.ARBITER) gets ECDSA private key.
Computes report_hash (SHA-256 of canonical JSON).
Signs with ECDSA → cryptographic_signature field set on report.
Sets signed_utc.


session_manager.set_final_report() — writes report ID to session state.
Redis cache — set_final_report(session_id, report) caches serialized ForensicReport in Redis.
PostgreSQL persistence — session_persistence.save_report() writes full report JSON to session_reports table.
Broadcasts REPORT_READY — WebSocket message with report_id and verdict.
Custody log — EntryType.REPORT_SIGNED logged.
Broadcasts ARBITER_UPDATE with status="complete", verdict text.


Phase B-8 — Frontend: Arbiter Polling + Navigation
File: apps/web/src/hooks/useInvestigation.ts → waitForFinalReport() + navigation
Step-by-step:

waitForFinalReport() polls GET /api/v1/sessions/{sessionId}/arbiter-status with exponential backoff (starts at ARBITER_POLL_INTERVAL_MS, max 3s).
Arbiter status endpoint (sessions.py:get_arbiter_status()) checks in order:

Redis final report cache → if found → {status: "complete", report_id}
Active pipeline metadata → status field
PostgreSQL session_reports
Live in-process pipeline object


Meanwhile, WebSocket fires REPORT_READY message → useSimulation sets status="complete".
waitForFinalReport() parses responses:

If status="complete" → tries getReport(sessionId) (GET /api/v1/sessions/{sid}/report) up to 5 times with REPORT_POLL_DELAY_MS gaps.
If report has report_id → returns true.


Enforces ARBITER_MIN_DISPLAY_MS minimum overlay display time (prevents flash-dismiss).
Sets sessionStorage[FC_REPORT_READY:{sid}]=1, sessionStorage[FC_ARBITER_TRANSITIONING:{sid}]=1.
Sets document.body.setAttribute("data-fc-loading", "1").
await requestAnimationFrame() — ensures one final paint.
router.push('/result/{session_id}').


Phase B-9 — Result Page Rendering
Files involved:

apps/web/src/app/result/[sessionId]/page.tsx — SSR page, reads sessionId from params
apps/web/src/app/result/ResultClientRedirect.tsx — handles /result redirect to /result/{sessionId}
apps/web/src/components/pages/DynamicResultClient.tsx — dynamic import of result UI
apps/web/src/hooks/useResult.ts — fetches report via GET /api/v1/sessions/{sessionId}/report
apps/web/src/components/result/ResultLayout.tsx — top-level result layout
apps/web/src/components/result/ResultHeader.tsx — file name, MIME type, case ID
apps/web/src/components/result/VerdictSection.tsx — overall verdict + confidence gauge
apps/web/src/components/result/ArcGauge.tsx — confidence arc visualisation
apps/web/src/components/result/KeyFindings.tsx — key finding cards
apps/web/src/components/result/AgentAnalysisTab.tsx — per-agent findings tab
apps/web/src/components/result/IntelligenceBrief.tsx — executive summary
apps/web/src/components/result/TimelineTab.tsx — execution timeline
apps/web/src/components/result/ReportIntegrity.tsx — ECDSA signature verification display
apps/web/src/components/result/DeepModelTelemetry.tsx — per-agent metrics
apps/web/src/components/result/EvidenceThumbnail.tsx — reads localStorage[THUMBNAIL:{sid}]
apps/web/src/components/result/HistoryPanel.tsx — prior investigations list
apps/web/src/lib/verdict.ts — maps overall_verdict string to UI colour/label
apps/web/src/lib/api/types.ts — ReportDTO type definition

Step-by-step:

[sessionId]/page.tsx mounts, extracts sessionId from URL.
useResult(sessionId) hook fires → GET /api/v1/sessions/{sessionId}/report.
Backend get_session_report() resolves from (in order): in-memory pipeline, in-memory cache, Redis cache, PostgreSQL.
Returns ReportDTO (Pydantic model serialised to JSON via _forensic_report_to_dto()).
ResultLayout renders:

ResultHeader — filename, case ID, investigator ID (from localStorage).
VerdictSection — overall_verdict, overall_confidence, manipulation_probability, ArcGauge.
KeyFindings — report.key_findings array rendered as cards with severity badges.
AgentAnalysisTab — per_agent_findings mapped to AgentFindingCard components.
IntelligenceBrief — executive_summary + structured summary sections.
ReportIntegrity — cryptographic_signature, report_hash, signed_utc displayed for court audit.
DeepModelTelemetry — per_agent_metrics (error rates, confidence, tool counts).
TimelineTab — ExecutionTimeline from per_agent_metrics timing data.


EvidenceThumbnail reads localStorage[THUMBNAIL:{sid}] (the JPEG captured in A-3).
Export buttons:

PDF: GET /api/v1/sessions/{sessionId}/report/pdf → pdf_report_exporter.py → WeasyPrint
DOCX: GET /api/v1/sessions/{sessionId}/report/docx → docx_report_exporter.py → python-docx
JSON: GET /api/v1/sessions/{sessionId}/report/download → raw DTO as JSON file




Critical Cross-Cutting Files (Referenced by Both Flows)
FileRoleapps/api/api/routes/_session_state.pyIn-memory/Redis session dict; broadcast_update(); get/set_active_pipeline_metadata(); Redis pub/sub bridgeapps/api/api/routes/_websocket.pyWebSocket upgrade, auth, message routing from Redis pub/sub to clientapps/api/core/auth.pyJWT validation, get_current_user() dependencyapps/api/core/config.pySettings — all env vars accessed as get_settings()apps/api/orchestration/pipeline_registry.pyProcess-global dict of live ForensicCouncilPipeline objects keyed by session_idapps/api/orchestration/worker.pyRedis-queue consumer — picks up session_id from queue, calls run_investigation_task()apps/web/src/lib/storageKeys.tsAll STORAGE_KEYS constants — single source of truth for localStorage/sessionStorage key namesapps/web/src/lib/storage.tsTyped localStorage/sessionStorage wrapper with quota-exceeded event dispatchapps/web/src/lib/api/index.tsAll frontend API calls: startInvestigation, getArbiterStatus, getReport, submitHITLDecision etc.apps/api/agents/base_agent.pyBaseAgent — run_investigation(), run_deep_investigation(), supports_uploaded_fileapps/api/core/react_loop.pyReAct loop engine used by all 5 agents

Key Decision Points & Failure Surfaces to Audit
Upload path:

magic.from_buffer MIME detection can mismatch PIL detection — two-pass logic in investigation.py:~L60-90
_detect_mime_from_head() called on only first 8192 bytes — truncated file heads
Redis SET NX dedup race: two simultaneous uploads of identical content → only first gets session

WebSocket path:

broadcast_update() in _session_state.py — if Redis pub/sub is down, messages silently dropped
WebSocket reconnect counter never resets (known historical bug) — check useSimulation.ts
FC_HANDOFF_FIRED sessionStorage flag prevents Strict Mode double-fire but also prevents legitimate retry after session loss

Phase gate:

_await_deep_analysis_decision() — TOCTOU race between GETDEL and status write (guarded but subtle)
resume_investigation() phase-gate check: expected_phase token only validated if frontend sends it — frontend must always send it
Pre-warm cache invalidation: if invalidate_pre_warm() fails silently (B-3 step 9 catches Exception), stale Phase-1 report used for final arbiter

Report retrieval:

get_session_report() — 4-level fallback: in-memory → Redis → PostgreSQL → 404. Any Redis timeout causes fall-through to slower DB path with no timeout guard
waitForFinalReport() retries getReport() 5 times — but only after arbiter-status returns complete. If WebSocket delivers REPORT_READY faster than polling, duplicate navigation can trigger

Result page:

localStorage[THUMBNAIL:{sid}] — read by EvidenceThumbnail. If missing (non-image or localStorage cleared), must gracefully handle null
VerdictSection.tsx uses font-heading CSS token — verify it is defined in globals.css
ReportIntegrity.tsx displays raw ECDSA signature — if cryptographic_signature is empty string, display must not break
You said: Now i need a full flow de-structure for initial analysis and deep analysisNow i need a full flow de-structure for initial analysis and deep analysis
What i am expecting is this
Initial analysis
trigger file upload
File type validation
Filtering agents
Start initial analysis
Visual context build using gemini
Gemini cascade 
Fallback to local ensemble
How local ensemble works
like this each minor steps with exact minute details so an ai tool can understand the flow files involved and perfect it and give me the final implementation plan
Write the full destructure flow for
1.Initial analysis
2.Deep analysisShow more8:13 AMClaude responded: Now I have everything needed.Ran 3 commandsRan 3 commandsNow I have everything needed. Let me write the complete granular flow deconstruction.

FLOW 1: INITIAL ANALYSIS — Complete Granular Deconstruction

STEP 1 — File Upload Trigger
Entry point: User clicks "Analyse" on HomeClient.tsx
Exact file: apps/web/src/components/ui/HeroAuthActions.tsx
What happens:

__pendingFileStore.file is set with the selected File object (apps/web/src/lib/pendingFileStore.ts)
fileHandoffManager.storeFile(file) persists file bytes to IndexedDB and metadata to sessionStorage[FC_PENDING_FILE_META] (apps/web/src/lib/upload/fileHandoffManager.ts)
sessionStorage[AUTO_START] = "true" — flags that evidence page should auto-start
sessionStorage[FC_SHOW_LOADING] = "true" — flags that overlay should render immediately
router.push('/evidence') — Next.js client navigation

Files touched in this step:

apps/web/src/components/ui/HeroAuthActions.tsx
apps/web/src/lib/pendingFileStore.ts
apps/web/src/lib/upload/fileHandoffManager.ts
apps/web/src/lib/storage.ts


STEP 2 — Evidence Page Mount and File Recovery
Entry point: Next.js renders apps/web/src/app/evidence/page.tsx → mounts EvidenceUploadClient
Exact files:

apps/web/src/app/evidence/page.tsx
apps/web/src/components/pages/EvidenceUploadClient.tsx
apps/web/src/hooks/useInvestigation.ts

Sub-steps in exact order:
2a. Fresh mount guard (useInvestigation.ts lines ~185–195):

freshMountDoneRef.current prevents Strict Mode double-fire
Detects __pendingFileStore.file is set
Calls clearInvestigationPersistence() — wipes prior SESSION_ID, INITIAL_AGENTS:{sid}, DEEP_AGENTS:{sid}, INVESTIGATION_CTX from localStorage
Resets autoStartFiredRef.current = false
sessionExistsRef.current = false

2b. Auth pre-warm (Effect at ~line 200):

authService.ensureAuthenticated() (apps/web/src/lib/upload/authService.ts)
Makes POST /api/auth/demo via Next.js route apps/web/src/app/api/auth/demo/route.ts
JWT token stored in memory (not localStorage) for security

2c. Effect A — auto-start trigger (useInvestigation.ts ~line 300):

Reads sessionStorage[FC_HANDOFF_FIRED] — if "1", returns immediately (Strict Mode guard)
Calls fileHandoffManager.recoverFile() — reads file bytes back from IndexedDB
If recovery fails and AUTO_START was set — shows toast "File selection was lost", routes back to home
Runs validateEvidenceFile(pending) (apps/web/src/lib/fileValidation.ts) — client-side MIME/size/extension sanity check
On validation pass: sets sessionStorage[FC_HANDOFF_FIRED] = "1", writes FC_PENDING_FILE_META to sessionStorage
Calls triggerAnalysis(pending)


STEP 3 — triggerAnalysis() — Client-Side Pre-Upload Orchestration
Exact file: apps/web/src/hooks/useInvestigation.ts → triggerAnalysis()
Sub-steps in exact order:
3a. Concurrency guard:

investigationInFlightRef.current = true — synchronous, prevents any concurrent call

3b. State reset:

arbiterControl.abort() — cancels any running arbiter polling loop (apps/web/src/lib/arbiterControl.ts)
resetSimulationHook() — clears useSimulation internal state machine back to idle
clearInvestigationPersistence() — second call, ensures absolutely clean slate
Clears lastSessionIdRef, completedAgentsRef, analysisCompleteSoundedRef

3c. MIME type capture:

setMimeType(targetFile.type) → stored in React state AND localStorage[MIME_TYPE]
This immediately informs AgentProgressDisplay which agents to expect via supportedAgentIdsForMime(mimeType) (apps/web/src/lib/agentSupport.ts)

3d. UI state:

playSound("scan") — audio feedback
setIsUploading(true), setPhase("initial"), setWsConnectionError(null)
setAnalysisStreamReady(false), setArbiterDeliberating(false)
setSimulationPhase("initial") — sets useSimulation phase context
startSimulation() — transitions useSimulation status from idle → initiating
setShowLoadingOverlay(true) + sessionStorage[FC_SHOW_LOADING] = "true" — GlobalLoadingOverlay (apps/web/src/components/ui/GlobalLoadingOverlay.tsx) becomes visible with "Uploading evidence to secure pipeline" text

3e. Case ID generation:

caseId = "CASE-" + crypto.randomUUID() — unique per submission

3f. Thumbnail capture (images only):

URL.createObjectURL(targetFile) → loads image into new window.Image()
Draws to <canvas> at max 240px, encodes as JPEG at quality 0.72
localStorage[THUMBNAIL] = thumbnailDataUrl — used by EvidenceThumbnail.tsx on result page

3g. Auth final check:

authService.ensureAuthenticated() — defensive second call before touching backend

3h. SHA-256 computation:

fileHandoffManager.getPendingClientSha256() — returns pre-computed SHA-256 of file bytes (computed by apps/web/src/lib/crypto/fileHash.ts during file selection)
This value goes to the backend for integrity verification


STEP 4 — HTTP Upload: POST /api/v1/investigate
Frontend call: startInvestigation(targetFile, caseId, investigatorId, pendingClientSha256) in apps/web/src/lib/api/index.ts
Proxy: apps/web/src/app/api/v1/[...path]/route.ts — Next.js edge proxy forwards to FastAPI at BACKEND_URL
Backend entry: apps/api/api/routes/investigation.py → start_investigation()
Sub-steps in exact order on the backend:
4a. Input validation:

InvestigationRequest(case_id=case_id, investigator_id=investigator_id) — Pydantic validates case_id must start with "CASE-", investigator_id must match REQ-{5-10 digits}
Fails with 422 on format violation

4b. Magic-byte MIME detection (first 8192 bytes):

head = await file.read(8192) then await file.seek(0)
actual_mime = await _detect_mime_from_head(head) → calls magic.from_buffer(head, mime=True) in a thread via asyncio.to_thread (uses python-magic / libmagic)
If python-magic not installed: uses core/magic_fallback.py (extension-based fallback)
If magic returns "application/octet-stream": PIL fallback — reads head bytes as BytesIO, tries Image.open(), maps PIL format to MIME string
On magic failure: raises 503 "Evidence MIME detection service is unavailable"

4c. MIME allowlist check:

if actual_mime not in SUPPORTED_MIME_TYPES → 400
SUPPORTED_MIME_TYPES defined in apps/api/core/file_type_policy.py

4d. Agent applicability check:

applicable_agents = get_applicable_agents(actual_mime) (apps/api/core/file_type_policy.py)
If empty: 400 "not supported by any specialized forensic agent"

4e. Extension validation:

raw_suffix = Path(file.filename).suffix.lower()
Must be in SUPPORTED_EXTENSIONS → 400
Must match EXACT_MIME_EXT_MAP[actual_mime] (content-extension cross-check) → 400 "Security violation: content mismatch extension"

4f. File size pre-check:

if file.size > 50MB → 400 (header size, not yet reading body)

4g. Rate limiting:

check_investigation_rate_limit(current_user.user_id) (apps/api/api/routes/_rate_limiting.py)
check_daily_cost_quota(current_user.user_id, current_user.role.value) — per-user daily budget check

4h. Streaming write to disk with SHA-256:

tmp_path = evidence/incoming/{session_id}{ext} — temp file path
Streams file in 1MB chunks via asyncio.to_thread(_stream_to_file) — reads directly from file.file (SpooledTemporaryFile), never buffers full file in memory
Simultaneously updates hashlib.sha256() per chunk
Aborts if cumulative total_size > MAX_FILE_SIZE
On empty file: deletes tmp_path, raises 400
content_hash = hasher.hexdigest() — server-side SHA-256

4i. Client SHA-256 verification:

If client_sha256 provided: normalise to lowercase, validate regex [a-f0-9]{64}
If client_sha256 != content_hash → deletes tmp_path, raises 400 "Client SHA-256 does not match"
client_hash_verified = True recorded in session metadata

4j. Redis deduplication (atomic):

dedup_key = f"dedup:{case_id}:{content_hash}"
Redis SET dedup_key session_id NX EX (timeout+60) — atomic set-if-not-exists
On collision (was_set=False): fetches existing_session_id from the key
Checks get_active_pipeline_metadata(existing_session_id) for status — if status is NOT "running"/"paused"/"queued" (i.e., completed/error/terminated), deletes dedup key and retries SET NX
If still collision: returns 409 with {"code": "duplicate_investigation", "existing_session_id": "..."} — frontend handles this as DuplicateInvestigationError
If Redis unavailable: deletes tmp_path, raises 503

4k. Image integrity check (images only, not GIF):

asyncio.to_thread(img.verify, str(tmp_path)) — PIL structural integrity check
Second open: img.size — checks pixel dimensions; w * h > 100_000_000 → 400 "Image too large"
If verify raises: deletes tmp_path, raises 400 "Image verification failed"
In testing mode: logs and skips

4l. AV container check (audio/video):

subprocess.run(["ffprobe", "-v", "quiet", "-show_format", "-show_streams", tmp_path], timeout=30)
If ffprobe not found: logs warning, continues (degraded)
If returncode != 0: raises 400 "Audio/video container verification failed"

4m. Session metadata to Redis:

session_metadata = {status: "queued", file_path, content_hash, detected_mime, applicable_agents, created_at, ...}
set_active_pipeline_metadata(session_id, session_metadata) → writes forensic:session:metadata:{session_id} to Redis with TTL

4n. Session persistence to PostgreSQL:

_register_session_before_dispatch(session_id, case_id, investigator_id)
Calls session_persistence.save_session_state() → inserts into session_reports table
In production: failure here raises 500 and cleans up Redis key + tmp_path
In development: logs warning and continues

4o. Supersede prior sessions (if configured):

If settings.supersede_prior_investigations_on_upload: calls _supersede_prior_investigations(investigator_user_id, keep_session_id)
Redis SCAN for forensic:session:metadata:* keys owned by same investigator_id
Sets status "superseded" on all prior running sessions for this user
Publishes forensic:notify_decision to unblock any paused pipelines for those sessions

4p. Task dispatch:
Path A — Redis worker queue (use_redis_worker=True):

Checks queue.is_worker_alive() — if not alive: cleans up, raises 503
Broadcasts "Investigation enqueued..." via WebSocket
queue.submit(session_id, case_id, ..., evidence_file_path, detected_mime, ...) → writes to Redis list forensic:investigation:queue
pipeline_started = True

Path B — In-process (use_redis_worker=False):

pipeline = ForensicCouncilPipeline()
set_active_pipeline(session_id, pipeline) → stores in process-global dict in apps/api/api/routes/_session_state.py
task = asyncio.create_task(run_investigation_task(...)) — creates background asyncio task
set_active_task(session_id, task) → stores task reference
pipeline_started = True

4q. Response:

increment_investigations_started() — Prometheus counter
Returns InvestigationResponse(session_id, case_id, status="queued"/"started", content_hash, dispatch_mode)


STEP 5 — Frontend: Session Wiring and WebSocket Connect
Exact file: apps/web/src/hooks/useInvestigation.ts → triggerAnalysis() continuation
Sub-steps:
5a. Atomic localStorage write:

storage.setItem(STORAGE_KEYS.INVESTIGATION_CTX, investigationCtx, true) — full JSON context
storage.setItem(STORAGE_KEYS.SESSION_ID, sessionIdToUse) — bare session UUID
document.cookie = "SESSION_ID={sid}; path=/; max-age=3600; SameSite=Lax" — also set as cookie for middleware
Per-session keyed copies: FILE_NAME:{sid}, MIME_TYPE:{sid}, PIPELINE_START:{sid}, EVIDENCE_SHA256:{sid}, THUMBNAIL:{sid}, INVESTIGATION_CTX:{sid}

5b. WebSocket connect:

connectWebSocket(sessionIdToUse) (apps/web/src/hooks/useSimulation.ts)
Constructs URL: wss://{host}/api/v1/sessions/{sessionId}/ws
Native WebSocket opened
On open: sends auth handshake with JWT token as first message
Backend _websocket.py upgrades, authenticates, registers WS in get_session_websockets(session_id)
Backend subscribes WS to Redis pub/sub channel forensic:session:{session_id}
On WS connect success: setAnalysisStreamReady(true), setUploadPhaseText("Agents dispatching")
loadingOverlayController.dismiss() → after 800ms delay setShowLoadingOverlay(false)

5c. Cleanup:

investigationInFlightRef.current = false
__pendingFileStore.file = null
clearPendingEvidenceFile() — removes IndexedDB entry
sessionStorage[FC_PENDING_FILE_META] removed
sessionStorage[FC_HANDOFF_FIRED] removed


STEP 6 — Backend: Pipeline Initialization
Entry: apps/api/orchestration/investigation_runner.py → run_investigation_task() → pipeline.run_investigation()
File: apps/api/orchestration/pipeline.py → _run_investigation_core()
6a. Component initialization (_initialize_components(session_id)):

Redis connect: get_redis_client() (apps/api/core/persistence/redis_client.py) — if fails, _degradation_flags.append("Redis unavailable..."), _redis = None
First WebSocket broadcast: "Initializing forensic core..." with status="initiating" — sent via broadcast_update() (apps/api/api/routes/_session_state.py) → Redis pub/sub → WS → frontend useSimulation receives, transitions to "initiating" state
Qdrant connect: get_qdrant_client() (apps/api/core/persistence/qdrant_client.py) — if fails, degrades episodic memory
Broadcasts "Establishing episodic link..."
PostgreSQL connect: get_postgres_client() — if fails, degrades chain-of-custody persistence
Broadcasts "Connecting to custody ledger..."
CustodyLogger construction: CustodyLogger(postgres_client=_postgres) (apps/api/core/custody_logger.py)
Custody broadcast patch: monkey-patches custody_logger.log_entry to also call broadcast_update() for HITL_CHECKPOINT and ACTION entry types — this is how per-tool progress (e.g. "Running Neural Fingerprint...") is broadcast to the frontend
EvidenceStore construction: EvidenceStore(postgres_client, LocalStorageBackend, custody_logger) (apps/api/core/persistence/evidence_store.py)
WorkingMemory construction: WorkingMemory(redis_client, custody_logger) (apps/api/core/working_memory.py) — Redis-backed per-agent task state
EpisodicMemory construction: EpisodicMemory(qdrant_client, custody_logger) (apps/api/core/episodic_memory.py) — Qdrant vector store for cross-case signal memory
InterAgentBus construction: InterAgentBus(config, session_id, working_memory, episodic_memory, custody_logger, evidence_store) (apps/api/core/inter_agent_bus.py) — shared message bus for cross-agent context
inter_agent_bus.set_abort_handler(pipeline._handle_global_abort) — allows any agent to abort the whole pipeline
await inter_agent_bus.start() — starts internal pub/sub listener
SessionManager construction: SessionManager(redis_client) (apps/api/orchestration/session_manager.py)
AgentFactory construction: AgentFactory(config, working_memory, episodic_memory, custody_logger, evidence_store, inter_agent_bus) (apps/api/orchestration/agent_factory.py)
CouncilArbiter construction: CouncilArbiter(session_id, custody_logger, inter_agent_bus, agent_factory, config) (apps/api/agents/arbiter.py)
Arbiter _step_hook set to broadcast ARBITER_UPDATE WebSocket messages during deliberation

6b. Stale decision key cleanup:

Redis SCAN for forensic:session:resume_decision:{session_id}:* and bare forensic:session:resume_decision:{session_id}
Deletes all matches — prevents a prior crashed session's decision from leaking into this run


STEP 7 — Evidence Ingestion
File: apps/api/orchestration/pipeline.py → _ingest_evidence()
7a. MIME resolution:

Uses detected_mime passed from the investigation route (already magic-byte verified)
Falls back to mimetypes.guess_type() then PIL magic-byte probe if not provided

7b. Image routing profile (images only):

build_image_evidence_profile(path, original_filename, mime_type) (apps/api/core/image_evidence_routing.py)
Opens image with PIL, reads: width, height, PIL format, EXIF presence, camera make/model, GPS tags, software tag, animated flag
Classifies into ImageEvidenceClass route_classes: CAMERA_PHOTO, SCREENSHOT, DOCUMENT_OR_PAPER, WEB_OR_DIGITAL_IMAGE, PHYSICAL_SCENE, PEOPLE_OBJECT_WEAPON
build_image_agent_tool_plan(profile) → generates deterministic per-agent tool lists for initial and deep phases based on the image class
Both stored as metadata["image_evidence_profile"] and metadata["agent_tool_plan"] on the artifact

7c. Evidence artifact creation:

evidence_store.ingest(file_path, session_id, agent_id, metadata) (apps/api/core/persistence/evidence_store.py)
Computes SHA-256 of file if not already in metadata
Writes to PostgreSQL evidence_artifacts table (if available)
Returns EvidenceArtifact object with: artifact_id, file_path, mime_type, content_hash, metadata

7d. Agent factory and bus enrichment:

agent_factory.set_evidence_artifact(evidence_artifact) — all agents created via factory will have this artifact
inter_agent_bus._evidence_artifact = evidence_artifact — bus can serve artifact to any agent on demand

7e. Session creation:

session_manager.create_session(session_id, case_id, investigator_id, agent_ids=[all 5 agent IDs], content_sha256, file_size_bytes, detected_mime, ...) (apps/api/orchestration/session_manager.py)
Writes session record to Redis and PostgreSQL


STEP 8 — File Type Validation and Agent Filtering
File: apps/api/orchestration/pipeline_phases.py → run_agents_concurrent() → _init_agent(aid)
This runs concurrently for all 5 agents via asyncio.gather.
For each agent:
8a. Agent instantiation:

cls = registry.get_agent_class(aid) (apps/api/core/agent_registry.py)
Constructs agent with: agent_id, session_id, evidence_artifact, config, working_memory, episodic_memory, custody_logger, evidence_store, heavy_tool_semaphore, optionally inter_agent_bus
Calls _init_context() (apps/api/agents/mixins/context.py) — initialises _tool_context = {}, _findings = [], _react_chain = [], _agent_synthesis = None, _agent_confidence = None, _agent_error_rate = None

8b. LLM availability check:

LLMClient(config=pipeline.config).is_available — checks LLM_API_KEY and EXTERNAL_AI_ALLOWED settings
Sets inst._llm_available and inst._synthesis_mode = "llm"/"deterministic"

8c. Broadcast "validating":

_broadcast_agent_status(aid, "validating", f"{aid} file type validation in progress.")
Frontend useSimulation receives AGENT_UPDATE with status="validating" → agent card shows yellow pulse

8d. supports_uploaded_file check:

inst.supports_uploaded_file property (base_agent.py)
Calls MimeRegistry.is_supported(agent_name, mime_type, file_path) (apps/api/core/mime_registry.py)
MimeRegistry maps agent names to MIME prefixes they support (e.g. Agent1 supports image/*, Agent2 supports audio/*, Agent4 supports video/*)
Returns True/False

8e. Broadcast result:

If supported=True: broadcast "running" → agent card shows blue spinning indicator
If supported=False: broadcast "skipped" with error="Unsupported file type." → agent card shows grey "SKIPPED" badge
await asyncio.sleep(0) — yields event loop so UI renders "validating" before "running"

8f. Signal bus update:

pipeline.signal_bus.update_applicable_agents(applicable_ids) (apps/api/orchestration/signal_bus.py)
SignalBus tracks which agents are active, used for quorum completion detection

8g. Inter-agent bus registration:

pipeline.inter_agent_bus.register_agent(aid, inst) — agents can now send/receive cross-agent messages


STEP 9 — Initial ReAct Loop per Agent (Phase 1)
File: apps/api/orchestration/pipeline_phases.py → _run_one_staggered()
Each agent starts with idx * 2.0s stagger (Agent1=0s, Agent2=2s, Agent3=4s, Agent4=6s, Agent5=8s).
Within _run_one(agent, aid, supported) → calls agent.run_investigation():
File: apps/api/agents/mixins/investigation.py → run_investigation()
9a. PipelineTrace.start() (apps/api/core/tracing.py) — OpenTelemetry span opened for "initial_investigation"
9b. _initialize_working_memory() (apps/api/agents/mixins/memory.py):

working_memory.initialize(session_id, agent_id, task_decomposition, iteration_ceiling)
Writes agent's task list to Redis as WorkingMemoryState with each task as TaskItem(description, status="PENDING", priority)

9c. build_tool_registry() — agent-specific, e.g. for Agent1 (apps/api/agents/agent1_image.py):

Calls _validate_evidence_artifact() — checks file exists, size < 500MB, PIL can open it, MIME starts with "image/"
Calls classify_evidence_file(evidence_artifact) (apps/api/core/file_classifier.py):

is_screen_capture_like(artifact) — checks filename patterns (Screenshot, screen shot), content, dimensions
is_document_like(artifact) — checks aspect ratio, filename patterns
is_camera_still_candidate(artifact) — checks EXIF camera make/model tags via PIL
is_digitally_created_image(artifact), is_recompressed_web_image(artifact)
Maps to primary_category: "screenshot", "document", "live_photograph", "web_image", "object_scene", "ai_generated_suspect"
Looks up CATEGORY_TO_RECOMMENDED_TOOLS[category] and CATEGORY_TO_SKIP_TOOLS[category]
Returns FileClassification(primary_category, confidence, recommended_tools, skip_tools)


self._file_classification = classification — cached on agent instance
Registers category-specific tool handlers in ToolRegistry:

All categories: visual_evidence_profile_handler, synthid_watermark_detect, reverse_image_search, lens_style_multimodal_scan
screenshot: adds extract_text_from_image, analyze_image_content, detect_font_inconsistency, detect_ui_overlay_forgery, frequency_domain_analysis
live_photograph/web_image/object_scene: adds neural_ela, analyze_image_content, frequency_domain_analysis, neural_fingerprint
document: adds extract_text_from_image, analyze_image_content, frequency_domain_analysis, neural_ela
ai_generated_suspect: adds analyze_image_content, frequency_domain_analysis, diffusion_artifact_detector, deepfake_frequency_check
All: always registers neural_splicing, neural_copy_move, anomaly_tracer, f3_net_frequency, diffusion_artifact_detector



9d. _publish_tool_registry_snapshot() (apps/api/agents/mixins/investigation.py):

Gets allowed_tools = get_allowed_tools_for_mime(mime_type) (apps/api/core/task_tool_config.py) — MIME-filtered tool list
Writes filtered tool list to working_memory.update_state({tool_registry_snapshot: [...]}) — LLM ReAct mode reads this to pick valid tools

9e. _check_tool_availability():

Lists unavailable tools from registry, logs to custody logger with EntryType.TOOL_CALL — degraded mode note

9f. _retrieve_episodic_context() (apps/api/agents/mixins/memory.py):

Generates embedding of evidence_artifact descriptors
Queries Qdrant vector DB for similar past investigation findings (k-nearest neighbours)
Returns formatted text summary of relevant historical cases
Appended to initial_thought if non-empty

9g. build_initial_thought() — agent-specific, e.g. Agent1:

For screen capture: "Starting screen capture integrity analysis... Phase 1: OCR, CLIP, SHA-256, FFT, SigLIP2..."
For live photo: "Starting image integrity analysis... Phase 1 (fast): CLIP, Gemini OCR, SigLIP2, SHA-256, FFT, ViT Neural ELA..."
Combined with episodic context if present

9h. LLM step generator setup (conditional on LLM_ENABLE_REACT_REASONING):

Creates LLMClient(config) and verifies is_available
If available: create_llm_step_generator(llm_client, config, agent_name, evidence_context) (apps/api/core/react_loop.py)
Returns async generator function that will call LLM for each ReAct step decision
If unavailable: llm_generator = None → pure task-decomposition mode

9i. ReActLoopEngine.run(initial_thought, tool_registry, llm_generator) (apps/api/core/react_loop.py):

STEP 10 — ReAct Loop Engine Execution (Inside Each Agent)
File: apps/api/core/react_loop.py → ReActLoopEngine.run()
Each iteration = one THOUGHT → ACTION → OBSERVATION cycle:
10a. Read next pending task from working memory:

working_memory.get_state(session_id, agent_id) → WorkingMemoryState
Finds first task with status="PENDING", sets it "IN_PROGRESS"
working_memory.update_state(session_id, agent_id, {tasks: ...})

10b. THOUGHT step:
If llm_generator is not None (LLM mode):

llm_step_generator(react_chain, state) builds Groq/LLM prompt:

System prompt with agent persona, evidence context, available tools (from tool_registry_snapshot)
React chain history (prior THOUGHT/ACTION/OBSERVATION steps)
Currently pending task description


Calls llm_client.generate_reasoning_step() (apps/api/core/llm_client.py) → POST to Groq API with Llama model
Parses response: if tool_call format → extracts tool_name and tool_input; if text → tries JSON parsing, then regex text extraction
Returns ReActStep(type="THOUGHT", tool_name, tool_input)

If no LLM (task decomposition mode):

Builds ReActStep(type="THOUGHT") from current pending task description
Extracts tool_name from task description text using _parse_tool_name_from_task() (string matching: "Run neural_ela for..." → "neural_ela")
tool_input = {"artifact": evidence_artifact}

10c. ACTION step — tool dispatch:

tool_registry.execute(tool_name, tool_input) (apps/api/core/tool_registry.py)
Looks up registered handler for tool_name
Acquires heavy_tool_semaphore if tool is tagged as heavy (prevents concurrent ML model overload)
Per-tool timeout: asyncio.wait_for(handler(tool_input), timeout=120.0) (300s for deep phase)
Custody logger log_entry(EntryType.ACTION, {tool_name, agent_id, session_id}) — this triggers the broadcast patch, sending AGENT_UPDATE with thinking="Running {display_name}..." to the frontend
Returns ToolResult(result_data, available=True/False, error=None)

10d. OBSERVATION step — result processing:

ToolOutputClassifier.classify(tool_name, result) (apps/api/core/tool_output_classifier.py) → maps raw tool output to evidence_verdict enum: "POSITIVE", "NEGATIVE", "INCONCLUSIVE", "NOT_APPLICABLE", "ERROR"
_fmt_format_tool_result(tool_name, result) (apps/api/core/finding_formatter.py) → builds reasoning_summary text
_record_tool_result(tool_name, result) (apps/api/agents/mixins/memory.py):

Stores in self._tool_context[tool_name] = result — keyed dict of all tool outputs
Calls working_memory.update_state(..., {tool_name: result}) — persists to Redis
Marks task "COMPLETE" in working memory


Constructs AgentFinding(agent_id, finding_type=tool_name, confidence_raw, evidence_verdict, reasoning_summary, metadata={tool_name, analysis_phase, ...})
Appends to self._findings
Calls self.on_tool_result(finding) — agent-specific reactive hook

10e. on_tool_result reactive expansion (Agent1 example):

_on_tool_result_impl(finding) — content-semantic reactive tasks:

analyze_image_content result with image_type containing "person/face" → inject_task("Run deepfake_frequency_check...", priority=15)
analyze_image_content result with "screenshot" → inject_task("Run detect_font_inconsistency...", priority=13) + inject_task("Run detect_ui_overlay_forgery...", priority=13)
extract_text_from_image result with AI keywords → inject_task("Run diffusion_artifact_detector...", priority=19)
High-confidence neural_copy_move/neural_splicing POSITIVE → inject_task("Run roi_extract...", priority=20)


_reason_step(finding) — tool signal cross-validation reactive tasks:

ELA positive + FFT clean → inject_task("Run jpeg_ghost_detect...", priority=15) + inject_task("Run f3_net_frequency...", priority=15)
noiseprint_cluster multi-cluster → inject_task("Run neural_splicing...", priority=18) + inject_task("Run neural_copy_move...", priority=18)
neural_splicing POSITIVE → inject_task("Run neural_copy_move...", priority=17) (clone source confirmation)
Diffusion high-conf + clean FFT → inject_task("Run synthid_watermark_detect...", priority=16) + inject_task("Run f3_net_frequency...", priority=16)
ELA high-conf (>0.75 or >3 anomaly regions) → inject_task("Run roi_extract...", priority=20)
Splicing/copy-move POSITIVE → inject_task("Run adversarial_robustness_check...", priority=16) (anti-forensics check)


inject_task() writes new task to working_memory.create_task(), broadcasts updated tools_total to frontend

10f. HITL checkpoint check:

After each tool, loop checks if agent called flag_hitl(reason, brief)
If yes: custody_logger.log_entry(EntryType.HITL_CHECKPOINT, {checkpoint_id, reason, brief})
The custody broadcast patch fires: sends HITL_CHECKPOINT WebSocket message
Frontend useSimulation receives → setHitlCheckpoint(...) → HITLCheckpointModal renders
Loop blocks on asyncio.wait_for(hitl_event.wait(), timeout=540.0) — waits for human decision via POST /api/v1/hitl/{session_id}/decision
Decision consumed → loop resumes

10g. Loop continuation check:

iteration_ceiling reached → loop exits
No more PENDING tasks in working memory → loop exits naturally
Task status="COMPLETE" check prevents re-running the same tool


STEP 11 — Visual Context Build: visual_evidence_profile_handler
This is the most important tool in Phase 1 — it builds the shared visual context for all agents.
File: apps/api/agents/agent1_image.py → visual_evidence_profile_handler (registered in build_tool_registry)
Sub-steps:
11a. Call _visual_evidence_profile_handler() (from NeuralSynthesisMixin, apps/api/agents/mixins/synthesis.py):

HARD QUOTA CONTRACT: Only Agent1 may make the Gemini API call. All other agents (agent_id != "Agent1") either consume Agent1's cached profile or fall back to local ensemble — never call Gemini directly.

11b. Gemini visual analysis (Agent1 only):

VisionRouter.analyze(artifact, model_hint, signal_callback) (apps/api/core/vision_router.py)
Reads evidence file as bytes, encodes as base64
Builds prompt via _build_deep_forensic_prompt(exif_summary, persona, is_screen_capture_like) (apps/api/core/gemini_client.py):

Prepends _SAFETY_PREAMBLE (prompt injection defense)
Adds agent persona context
Adds FOCUS category directive (screenshot vs photograph)
Injects slim EXIF metadata in [UNTRUSTED EVIDENCE START]...[UNTRUSTED EVIDENCE END] block
Requests JSON with: what_it_is, origin, manipulation.signals, manipulation.assessment, visible_metadata, elements, routing_category, confidence




STEP 12 — Gemini Model Cascade
File: apps/api/core/gemini_client.py → GeminiClient.analyze_image()
12a. Provider quota guard check:

ProviderQuotaGuard.check("gemini") (apps/api/core/provider_quota_guard.py) — process-level rate limit
If quota exceeded: raises GeminiQuotaBlocked → immediately falls through to local ensemble

12b. Primary model attempt: gemini-2.5-flash

URL: https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:generateContent?key={GEMINI_API_KEY}
Request body: {contents: [{role: "user", parts: [{inline_data: {mime_type, data: base64}}, {text: prompt}]}], generationConfig: {response_mime_type: "application/json"}}
httpx.AsyncClient.post() with timeout=settings.gemini_timeout

12c. Response handling per status code:

200 OK: parse JSON response, extract candidates[0].content.parts[0].text → parse as JSON
404 or body contains "model not found": raises _ModelUnavailableError → skip to next model immediately, no backoff
401: raises _ApiKeyInvalidError → breaks entire cascade (all models will fail the same way)
429 (quota/rate limit): raises GeminiRateLimited → skip to next model immediately
Safety block in body (all candidates have finishReason: "SAFETY"): raises _SafetyBlockError → breaks cascade
Other errors: exponential backoff up to _MAX_RETRIES=5 with _BASE_BACKOFF=2.0s + jitter, then cascade to next model

12d. Fallback chain (configured via GEMINI_FALLBACK_MODELS):

Tries in order: gemini-2.5-flash → gemini-2.5-flash-lite → gemini-2.0-flash → gemini-2.0-flash-lite
Each model attempted with the same retry logic
On _ModelUnavailableError: advances immediately
On _ApiKeyInvalidError or _SafetyBlockError: breaks entire chain

12e. Thinking model handling (gemini-2.5-* prefix):

These models may return thinkingConfig — thought parts in the response
Code filters out thought parts, only processes non-thought text parts
Strips markdown fences from JSON if present

12f. Parse Gemini response → VisualEvidenceFinding:

Maps routing_category → image_category
Stores what_it_is, origin, manipulation.signals, visible_metadata.on_screen_datetime, elements, confidence in VisualEvidenceFinding metadata fields
Returns VisualEvidenceFinding model (apps/api/core/vision_types.py)


STEP 13 — Gemini Fallback to Local Ensemble
Triggered when: All Gemini models fail, API key invalid, safety block, quota exceeded, or EXTERNAL_AI_ALLOWED=False
File: apps/api/core/vision_local_ensemble.py → analyze_local_visual_profile(artifact)
Sub-steps:
13a. PIL basic image probe:

Opens image, reads: width, height, format, mode, EXIF
Extracts basic metadata: dimensions, color space, creation datetime from EXIF

13b. CLIP semantic classification (analyze_image_content tool):

If inference_client available: runs SigLIP2/CLIP model (apps/api/core/inference_client.py)
Model: google/siglip2-base-patch16-224 (or configured alternative)
Classifies image against predefined category labels: ["screenshot", "photograph", "document", "AI-generated image", "video frame", ...]
Returns top-N classifications with confidence scores
Determines image_type from highest-scoring label

13c. EasyOCR fallback (if Gemini OCR unavailable):

Runs easyocr.Reader(['en']) on the image file
Returns list of text segments with bounding boxes and confidence scores
If EasyOCR fails → Tesseract subprocess fallback

13d. Tesseract last-resort:

pytesseract.image_to_string(image, config="--oem 3 --psm 6")
Returns raw text without layout/structure

13e. Minimal heuristic classification:

Combines CLIP scores + OCR text content + image dimensions + filename
Maps to routing_category: "screenshot", "document", "live_photograph", "web_image", "ai_generated_suspect"
confidence set to 0.5 (reflects lower certainty vs Gemini)

13f. Builds VisualEvidenceFinding:

Marks external_ai_used=False in metadata
Sets fallback_reason="Gemini unavailable; local CLIP/OCR ensemble used"
Returns same VisualEvidenceFinding interface as Gemini path


STEP 14 — Visual Profile Storage and Cross-Agent Broadcast
File: apps/api/agents/agent1_image.py → visual_evidence_profile_handler (continuation)
14a. Store in Agent1's tool context:

self._tool_context[TOOL_VISUAL_PROFILE] = result (via _record_tool_result)
working_memory.update_state(..., {TOOL_VISUAL_PROFILE: result}) — persisted to Redis

14b. Publish to inter-agent bus:

inter_agent_bus.set_visual_profile(str(session_id), result) (apps/api/core/inter_agent_bus.py)
Stores in Redis as forensic:visual_profile:{session_id} — accessible to all agents in the session
Also signals _agent1_context_event that was set on each agent instance — unblocks Agents 2/3/4/5 that were waiting

14c. Dynamic content-aware routing:
After Gemini/local result arrives, visual_evidence_profile_handler does real-time tool gating:

Reads routing_source = result.metadata["forensic_routing"] → image_category, skip_tools, recommended_initial_tools
Gets current working memory state
For each pending task: if task's tool name is in skip_tools → marks task "COMPLETE" with result_ref="skipped_by_forensic_routing" — tool will not run
For each recommended_tools not yet queued: injects new task
Updates working memory with modified task list
Re-publishes visual profile to inter-agent bus after routing update


STEP 15 — Remaining Phase 1 Tools (Agent1 example, for live photos)
After visual_evidence_profile, the ReAct loop continues with remaining pending tasks:
analyze_image_content (CLIP semantic classification):

ImageHandlers.analyze_image_content_handler(input_data) (apps/api/core/handlers/image.py)
Calls InferenceClient.classify_image(file_path) (apps/api/core/inference_client.py)
Runs SigLIP2 model (via run_ml_tool("siglip2_classifier.py", ...) or inline if model loaded)
Returns: image_type, all_classifications=[{category, score}], confidence
Evidence verdict: INCONCLUSIVE (classification, not manipulation detection)
on_tool_result reactive: person/AI keywords → inject_task("deepfake_frequency_check")

frequency_domain_analysis (FFT):

ImageHandlers.frequency_domain_analysis_handler(input_data)
Calls run_ml_tool("deepfake_frequency.py", file_path, timeout=15.0) via ml_subprocess
Local Python: FFT of image, analyzes high-frequency component distribution
Compares against natural-image spectral profile baseline
Returns: anomaly_detected, high_frequency_score, num_anomaly_regions
Evidence verdict: POSITIVE if high_frequency_score > threshold, else NEGATIVE
No Gemini, no external API — fully local

neural_fingerprint (SigLIP2 neural fingerprint):

ImageHandlers.neural_fingerprint_handler(input_data)
run_ml_tool("neural_ela_transformer.py", file_path, timeout=15.0) — ViT-based ELA
Processes image through ViT transformer to detect re-compression artifacts
Returns: neural_score, num_anomaly_regions, manipulation_detected
Evidence verdict: POSITIVE if neural_score > 0.6

neural_ela (Error Level Analysis):
Primary path: run_ml_tool("neural_ela_transformer.py", file_path, timeout=15.0) (apps/api/core/ml_subprocess.py):

Serializes call as JSON to stdin of subprocess worker
Worker runs neural_ela_transformer.py in separate Python process (no app process pollution)
Script: re-saves image at multiple quality levels, computes ViT-embedded ELA residuals
Returns: manipulation_detected, anomaly_score, num_anomaly_regions, anomaly_map_path
Attaches visual grounding: _attach_visual_grounding(result, tool_name="neural_ela") — adds visual_profile context from _tool_context["visual_evidence_profile"] to finding metadata

Fallback path (if neural_ela_transformer.py unavailable or times out):

ela_full_image_handler(input_data, record=False) — classical multi-quality ELA
PIL saves image at quality levels 70, 85, 95; computes difference image
OpenCV SSIM-based anomaly detection on the difference map
fallback_reason = "neural_ela_transformer unavailable; used classical multi-quality ELA"
heuristic_mode = True

extract_text_from_image (Gemini OCR for screenshots/documents):

ImageHandlers.extract_text_from_image_handler(input_data)
If GEMINI_API_KEY set and EXTERNAL_AI_ALLOWED: calls GeminiClient.extract_text(file_path) — multimodal OCR
Gemini cascade same as Step 12
EasyOCR fallback if Gemini unavailable
Tesseract final fallback
Returns: extracted_text, text_blocks, content_type, content_description
Evidence verdict: always INCONCLUSIVE (OCR result, not manipulation verdict)
on_tool_result reactive: person/AI keywords → escalate deepfake/diffusion checks


STEP 16 — Agent Completion and Synthesis
File: apps/api/agents/mixins/investigation.py → run_investigation() continuation (after ReAct loop exits)
16a. Findings accounting:

_tool_success_count = count(findings where evidence_verdict != ERROR and status != INCOMPLETE)
_tool_error_count = count(findings where evidence_verdict == ERROR or status == INCOMPLETE)

16b. LLM synthesis attempt (_synthesize_findings_once(findings, phase="initial", timeout_s=90.0)):

Check: config.local_only_analysis → skip if true
Check: config.llm_enable_post_synthesis and config.llm_api_key → skip if not set
Builds visual_context dict from _tool_context["visual_evidence_profile"]:

content_description, image_category, interface_identification, visual_verdict, visual_confidence, priority_signals, contextual_anomalies, contextual_narrative, forensic_specifics, extracted_text


Stagger: agent_num * 2.0s sleep (agents 1-5 → 0-10s spread to avoid Groq RPM burst)
Broadcasts "Cross-referencing tool results with image context" via WebSocket
Starts keepalive broadcast task (every 4s: "Synthesis weighing results", "cross-referencing signals", etc.)
SynthesisService.synthesize_findings(agent_id, agent_name, findings, evidence_artifact, tool_success_count, tool_error_count, phase="initial", agent_persona, image_type_hint, visual_profile_context, phase1_context=None) (apps/api/core/synthesis.py)
Calls Groq API with structured prompt asking for JSON synthesis with: verdict, agent_confidence, agent_error_rate, narrative_summary, sections=[{id, label, severity, opinion, refined_findings}], key_findings, agent_brief
Cancels keepalive task after completion

16c. Deterministic synthesis fallback (if LLM fails, returns None, or sections is empty):

_build_deterministic_synthesis(findings, phase="initial") (apps/api/agents/mixins/investigation.py)
Scores findings: counts POSITIVE, NEGATIVE, ERROR, INCONCLUSIVE
Derives verdict from counts:

≥2 POSITIVE → "TAMPERED"
1 POSITIVE → "SUSPICIOUS"
error_rate > 0.4 and no positives → "INCONCLUSIVE"
Screenshot + no positives → "AUTHENTIC" (ELA/noise tools naturally flag screenshots)
All negative, low error → "AUTHENTIC"
Else → "INCONCLUSIVE"


Per-tool domain-knowledge deterministic narration rules (e.g. "Neural ELA detected N compression anomaly regions with score X.XX...") — rich tool-context-aware opinion strings for each tool type
Builds sections array, narrative_summary, agent_brief
Returns {verdict, agent_confidence, agent_error_rate, narrative_summary, sections, key_findings, synthesis_source: "tool_grounded_deterministic", fallback_reason: "LLM narrative unavailable..."}

16d. Apply synthesis sections back to findings:

_apply_synthesis_sections(findings, synthesis["sections"])
Writes metadata["llm_refined_summary"], metadata["section_id"], metadata["section_label"], metadata["section_flag"], metadata["llm_synthesis"], metadata["section_key_signal"] onto each finding that matches the section's tool name

16e. Context publish:

_publish_agent_context("initial", findings) — writes compact context to working_memory.set_agent_context(session_id, agent_id, context) → Redis key forensic:agent_context:{session_id}:{agent_id}
Available for sibling agents via inter_agent_bus to ground their own analyses

16f. Self-reflection pass:

self_reflection_pass(findings) (apps/api/agents/mixins/reflection.py)
Brief structured review of findings, flags potential errors or gaps
Writes _reflection_report — used by arbiter for quality assessment

16g. Signal completion:

_signal_completion(skipped=False) — updates SignalBus (apps/api/orchestration/signal_bus.py) with agent completion signal


STEP 17 — AGENT_COMPLETE Broadcast
File: apps/api/orchestration/pipeline_phases.py → _broadcast_agent_status(aid, "complete", ..., findings, agent_inst, ...)
When _run_one() receives findings from agent.run_investigation():
17a. Preview construction:

Iterates findings, filters out PREVIEW_EXCLUDED_TOOLS (hash_verify, custody_check, file_type_validation)
Filters out NOT_APPLICABLE findings
Screenshot-specific filter: excludes SCREENSHOT_PREVIEW_EXCLUDED_TOOLS (lighting_consistency, prnu_sensor_verification, etc.)
Deduplicates by tool name (first occurrence wins)
Per finding: calls _humanize_initial_finding() (apps/api/core/findings_humanizer.py) → clean user-facing text
Calls assign_severity_tier(f) (apps/api/core/severity.py) → "LOW"/"MEDIUM"/"HIGH"/"CRITICAL"
Maps evidence_verdict → display verdict "FLAGGED"/"CLEAN"/"NEEDS_REVIEW"/"NOT_APPLICABLE"
Builds preview = [{tool, summary, severity, verdict, key_signal, section, degraded, fallback_reason, elapsed_s, finding_kind}]
Sorts by severity descending, discoveries before confirmations
Appends synthesis sections (LLM-refined summaries) if available — deduplicates, limits to 8 preview items

17b. broadcast_update() with AGENT_COMPLETE:

type="AGENT_COMPLETE" (vs AGENT_UPDATE for in-progress)
data = {status: "complete", analysis_phase: "initial", findings_count, confidence, findings_preview, agent_verdict, verdict_score, summary, tool_error_rate, tools_ran, tools_failed, section_flags, agent_brief, image_context}
Published to forensic:session:{session_id} Redis channel → all connected WebSockets receive it

17c. Frontend receives AGENT_COMPLETE:

useSimulation WS message handler dispatches
Pushes to completedAgents array state
revealQueue mechanism: agent cards animate in one by one via staggered reveal
AgentProgressDisplay re-renders with updated agent cards


STEP 18 — Initial Analysis Complete — HITL Decision Gate
File: apps/api/orchestration/pipeline_phases.py → _await_deep_analysis_decision()
18a. Phase-1 arbiter pre-warm (concurrent):

Before blocking, creates background task: asyncio.create_task(pipeline._run_arbiter_pre_warm(_initial_norm, case_id, suppress_broadcasts=True))
_run_arbiter_pre_warm() calls arbiter.deliberate(agent_results, case_id, use_llm=False) — builds full arbiter report deterministically without LLM
This runs silently while the user reads Phase 1 results
Result cached as arbiter._pre_warm_report — if user clicks "Accept Analysis", this cached report is used directly (fast path, skips re-deliberation)

18b. Status set and broadcast:

pipeline._awaiting_user_decision = True
Broadcasts INITIAL_ANALYSIS_COMPLETE with status="initial_complete" + 500ms sleep (ensures UI receives it)
Updates Redis metadata: status="awaiting_decision", awaiting_decision=True
Broadcasts PIPELINE_PAUSED with status="awaiting_decision", initial_results_ready=True

18c. Frontend receives PIPELINE_PAUSED:

useSimulation sets status="awaiting_decision"
useInvestigation computes awaitingDecision=true (status is awaiting_decision AND phase is initial AND not navigating)
AgentProgressDisplay shows decision buttons: "Accept Analysis" + "Authorize Deep Analysis"
playSound("analysis_done") fires
loadingOverlayController fully dismissed if not already done

18d. Backend blocks polling Redis every 2s:

active_redis.get(decision_key) where decision_key = "forensic:session:resume_decision:{session_id}:initial_to_deep"
Also checks pipeline.deep_analysis_decision_event.is_set() for in-process signal
Timeout: config.hitl_decision_timeout (default 3600s = 1 hour)
On timeout: returns False (skip deep analysis)


FLOW 2: DEEP ANALYSIS — Complete Granular Deconstruction

STEP 1 — User Triggers Deep Analysis
File: apps/web/src/hooks/useInvestigation.ts → handleDeepAnalysis()
1a. Guard:

investigationInFlightRef.current || resumeInFlightRef.current — prevents double-submit; both set to true

1b. Phase 1 state snapshot:

storage.setItem(STORAGE_KEYS.IS_DEEP, "true")
storage.setItem(RESULT_PHASE:{sid}, "deep") — result page will know to render deep results
storage.setItem(INITIAL_AGENTS:{sid}, completedAgentsRef.current, true) — JSON snapshot of Phase 1 agent cards
storage.removeItem(DEEP_AGENTS:{sid}) — clean slate for deep phase cards

1c. UI reset:

clearPipelineThinking() — clears pipelineThinking text in simulation
clearCompletedAgents() — clears completedAgents array so Phase 1 cards disappear; deep phase cards will fill this
completedAgentsRef.current = [] — sync the ref
setPhase("deep"), setSimulationPhase("deep") — simulation and investigation hooks aligned

1d. Resume call:

Calls resumeInvestigation(true) (useSimulation.ts)


STEP 2 — resumeInvestigation(deep=true)
File: apps/web/src/hooks/useSimulation.ts → resumeInvestigation()
2a. Phase token determination:

expectedPhase = "initial" because status === "awaiting_decision" at this moment
This is the phase gate token that prevents the backend from writing to the wrong Redis decision key

2b. HTTP POST:

POST /api/v1/sessions/{session_id}/resume
Body: {deep_analysis: true, expected_phase: "initial"}
Auth header with JWT

2c. Success handling:

resumeSucceededRef.current = true — prevents duplicate resume calls
Status held at current value; next WS message will transition it


STEP 3 — Backend: /resume Endpoint Processes Deep Request
File: apps/api/api/routes/sessions.py → resume_investigation()
3a. Session validation:

validate_session_id(session_id) — UUID format check
get_active_pipeline_metadata(session_id) — must exist in Redis
Ownership check: current_user.user_id == metadata["investigator_id"]

3b. Phase gate token validation:

expected_phase = "initial", pipeline_status = metadata["status"]
Verifies pipeline_status == "awaiting_decision" — if not (e.g. already at "awaiting_deep_report"), returns 409 Phase mismatch

3c. Decide Redis decision key:

pipeline_status == "awaiting_decision" → decision_key = "forensic:session:resume_decision:{session_id}:initial_to_deep"

3d. Idempotency check:

redis.get(decision_key) — if already set, returns 200 already_resumed

3e. Atomic write + publish:

Redis pipeline (transaction=True):

SET decision_key {deep_analysis: true, decided_by: user_id, decided_at: ISO} EX 14400
PUBLISH forensic:notify_decision {session_id, deep_analysis: true}



3f. In-process pipeline signal:

pipeline = get_active_pipeline(session_id) — looks up process-global dict
If found:

Idempotency: if pipeline.deep_analysis_decision_event.is_set() → return 200 already_resumed
pipeline.run_deep_analysis_flag = True
pipeline.deep_analysis_decision_event.set() → unblocks the _await_deep_analysis_decision() coroutine
pipeline.invalidate_pre_warm() → cancels Phase-1 background pre-warm task (_pre_warm_task.cancel()) and clears arbiter._pre_warm_report


If not found (Redis worker mode): updates Redis metadata to "paused_resume_requested"

3g. Broadcast:

broadcast_update(session_id, ARBITER_UPDATE) with message "Deep analysis requested. Dispatching expanded forensic checks.", status="processing"
Frontend useSimulation receives → transitions from awaiting_decision to processing

3h. Redis metadata update:

update_active_pipeline_metadata(session_id, {status: "deep_analysis_requested", deep_analysis: true, brief: "...", awaiting_decision: false})


STEP 4 — Backend: Pipeline Resumes into Deep Phase
File: apps/api/orchestration/pipeline_phases.py → run_agents_concurrent() after _await_deep_analysis_decision() returns True
4a. Deep analysis broadcast:

broadcast_update(session_id, AGENT_UPDATE, {status: "processing", analysis_phase: "deep", thinking: "Dispatching deep forensic tools..."})
Frontend: agents transition to deep phase display mode, Phase 1 synthesis cards still visible but marked as "initial"

4b. Working memory clear per agent:

For each of the 5 agent IDs: working_memory.clear(session_id, agent_id)
Redis DEL forensic:wm:{session_id}:{agent_id} — prevents Phase 1 task state from bleeding into Phase 2
Logs debug-level clear per agent

4c. Context event setup:

context_event = asyncio.Event() — shared event, set when Agent1 produces visual profile in deep phase
context_injected: set[str] — tracks which agents have received Agent1's deep context
producer_id = AgentID.AGENT1.value

4d. Pre-inject Phase 1 visual context:

Scans Phase 1 findings for Agent1's visual_evidence_profile finding (is_visual_profile_tool(tool_name))
If found: calls _broadcast_context(phase1_visual_profile_finding):

Stores payload in inter_agent_bus.set_visual_profile(session_id, context_payload)
For each sibling agent: calls agent_inst.inject_agent1_context(context_payload) — populates agent._agent1_context
Marks agents in context_injected set
Sets context_event — unblocks any agent waiting for Agent1 context


_context_seeded = True if found
If Phase 1 visual profile not found: context_event.set() anyway — prevents infinite wait

4e. Gemini signal callback wiring:

producer_inst._gemini_signal_callback = _broadcast_context — when Agent1's deep-phase Gemini call completes, it fires this callback
Each agent: sets agent_inst._agent1_context_event = context_event — agents await this event before running tools that depend on visual context


STEP 5 — Deep Phase Agents: Staggered Launch
File: apps/api/orchestration/pipeline_phases.py → _run_deep_with_stagger(aid, idx)
Stagger: idx * 4.0s (Agent1=0s, Agent2=4s, Agent3=8s, Agent4=12s, Agent5=16s) to avoid simultaneous Gemini slot contention.
Each agent goes through _run_deep_with_fallback(aid) then _run_agent_deep_only():

STEP 6 — Per-Agent Deep Pass: run_deep_investigation()
File: apps/api/agents/mixins/investigation.py → run_deep_investigation()
6a. Initial findings summary build:

_build_initial_findings_summary(phase="initial") — builds human-readable text of Phase 1 results:

Lists POSITIVE findings with confidence scores
Lists SUSPICIOUS findings
Counts NEGATIVE and INCONCLUSIVE
Extracts key metrics: ELA anomaly score, noiseprint clusters, FFT score


Stored as self._initial_findings_summary and written to working_memory.update_state({initial_findings_summary: ...})

6b. Tool registry rebuild:

self._tool_registry = await self.build_tool_registry() — same as Phase 1, rebuilds the full handler map
This is required because deep-phase tools need fresh handler instances

6c. Deep working memory namespace:

deep_agent_id = f"{self.agent_id}_deep" — e.g. "Agent1_deep"
self._deep_wm_namespace = deep_agent_id
working_memory.initialize(session_id, deep_agent_id, deep_tasks, len(deep_tasks) + 3) — separate working memory namespace
_publish_tool_registry_snapshot(deep_agent_id) — stores tool list under deep namespace

6d. Enriched deep initial thought:

f"DEEP ANALYSIS PASS — {agent_name}. Running {len(deep_tasks)} deep tools. Phase-1 context:\n{initial_summary}"
LLM will see Phase 1 results as context for deep reasoning

6e. Deep ReAct loop:

self._reactive_expansion_agent_id = deep_agent_id — inject_task() writes to deep namespace
loop_engine = ReActLoopEngine(agent_id=deep_agent_id, ...) with per_tool_timeout=300.0 (5 min vs 2 min initial)
loop_engine.run(enriched_thought, tool_registry, llm_generator=None) — deep phase always no-LLM reasoning (deterministic tool order is sufficient)
After completion: self._reactive_expansion_agent_id = None

6f. Deep findings tagging:

For each finding in loop_result.findings:

finding.agent_id = self.agent_id (not "Agent1_deep" — normalised back to base agent ID)
finding.metadata["analysis_phase"] = "deep"


Special gating flags:

For each deep finding, checks: meta.get("skipped") is True, meta.get("anomaly_tracer_skipped") is True, "not triggered" in reason_str, "not warranted" in reason_str
If any gate condition: meta["gated"] = True — signals UI that this tool was intentionally skipped



6g. Deduplication against Phase 1:

existing_tool_names = {f.metadata["tool_name"] for f in self._findings} (Phase 1 findings)
deduped_deep = [f for f in deep_findings if f.metadata["tool_name"] not in existing_tool_names]
self._findings = self._findings + deduped_deep — appends only new tool findings


STEP 7 — Deep Phase Tool Execution (Agent1 example)
Deep tasks for Agent1 (live photos) from deep_task_decomposition:
diffusion_artifact_detector:

ImageHandlers.diffusion_artifact_detector_handler(input_data) (apps/api/core/handlers/image.py)
run_ml_tool("diffusion_artifact_detector.py", file_path, timeout=60.0)
Script: frequency domain analysis + CNN feature extraction trained on Stable Diffusion/Midjourney artifacts
Returns: is_ai_generated, diffusion_detected, confidence, model_signatures
Evidence verdict: POSITIVE if confidence > 0.6
On failure: falls back to deepfake_frequency.py subprocess with error flag

synthid_watermark_detect:

synthid_watermark_handler(input_data) (registered in build_tool_registry)
run_ml_subprocess("synthid_watermark_detector", file_path, timeout=30)
Checks: SynthID invisible watermark (Google's AI watermarking), C2PA ai_generated marker in JUMBF metadata, AI software string in EXIF (Adobe Firefly, DALL-E, Midjourney)
Falls back to inline import if subprocess unavailable
Returns: watermark_detected, watermark_type, confidence
Evidence verdict: POSITIVE if watermark found

f3_net_frequency (F3-Net):

ImageHandlers.f3_net_frequency_handler(input_data)
run_ml_tool("f3net_freq.py", file_path, timeout=60.0)
Frequency domain analysis trained specifically on GAN artifacts (alternating frequency stripe patterns)
Returns: gan_artifact_detected, frequency_score, artifact_type
Evidence verdict: POSITIVE if frequency_score > threshold

neural_splicing (TruFor):

ImageHandlers.neural_splicing_handler(input_data)
Primary: run_ml_tool("trufor_analyzer.py", file_path, timeout=120.0) — TruFor SRM-feature splicing detector
Returns: splicing_detected, splicing_confidence, localization_map
Evidence verdict: POSITIVE if splicing_confidence > 0.5
Fallback: detect_splicing(file_path) in executor (SIFT-based classical splice detection)
fallback_reason = "TruFor unavailable; SIFT-based splice detection used"
Reactive: if POSITIVE → inject_task("Run neural_copy_move...", priority=17)

neural_copy_move (BusterNet):

ImageHandlers.neural_copy_move_handler(input_data)
Primary: run_ml_tool("busternet_v2.py", file_path, timeout=120.0) — BusterNet dual-branch copy-move detector
Returns: copy_move_detected, copy_move_confidence, source_region, target_region
Evidence verdict: POSITIVE if copy_move_confidence > 0.5
Fallback: detect_copy_move(file_path) in executor (SIFT keypoint self-matching)
fallback_reason = "BusterNet dual-branch unavailable; SIFT-based copy-move used"
Reactive: if POSITIVE → inject_task("Run adversarial_robustness_check...", priority=16)

anomaly_tracer (ManTra-Net) — gated:

ImageHandlers.anomaly_tracer_handler(input_data)
Gate check: _has_tampering_signal() — checks if ANY prior tool returned POSITIVE: neural_ela.manipulation_detected, noiseprint.sensor_inconsistency, splicing_detect.splicing_detected, copy_move.detected, diffusion.is_ai_generated
If no tampering signal found: returns NOT_APPLICABLE finding with meta["anomaly_tracer_skipped"]=True, meta["gated"]=True
If triggered: run_ml_tool("mantra_net_tracer.py", file_path, timeout=120.0) — ManTra-Net universal anomaly tracer
Returns: manipulation_detected, anomaly_type, anomaly_map, confidence
Evidence verdict: POSITIVE if confidence > 0.5 and manipulation_detected

Deep progress monitor (concurrent with tool execution):

_deep_progress_monitor() coroutine runs alongside the ReAct loop
Every 3s: working_memory.get_state(session_id, f"{agent_id}_deep") — checks IN_PROGRESS tasks
If current_task changed: broadcasts AGENT_UPDATE with status="running", thinking="Deep: {current_task}", analysis_phase="deep"
Stops when _progress_stop.set()


STEP 8 — Agent1 Deep Context Re-broadcast (post visual profile)
File: apps/api/orchestration/pipeline_phases.py → _run_deep_with_fallback() (after Agent1 deep loop completes)
If aid == producer_id (Agent1):

Scans deep findings for visual profile tool result
If found: _broadcast_context(visual_profile_result):

inter_agent_bus.set_visual_profile(session_id, payload) — overwrites Phase 1 profile with deep-phase result
For Agents 3 and 5: checks if _agent1_context was successfully injected; warns if not


Sets context_event (in case it wasn't already set) — unblocks any waiting agents


STEP 9 — Deep Phase AGENT_COMPLETE Broadcast
File: apps/api/orchestration/pipeline_phases.py → _run_deep_with_fallback() → _broadcast_agent_status(..., "complete", ..., analysis_phase="deep")
9a. Filter to deep-only findings:

deep_only = [f for f in result.findings if f.metadata.get("analysis_phase") == "deep"]
Only deep findings go in the broadcast preview — prevents Phase 1 cards from duplicating in deep view

9b. Synthesis sections:

_append_synthesis_sections(synthesis_data) with analysis_phase="deep" and initial_tool_names set
Filters: skips any synthesis section whose tool is in _norm_initial_tools — prevents deep synthesis showing initial-phase findings as new
Max 8 items in preview

9c. WebSocket broadcast:

type="AGENT_COMPLETE", analysis_phase="deep", findings_preview=[deep_only_cards]
Frontend useSimulation receives → pushes to completedAgents → deep agent card replaces (or augments) the Phase 1 card


STEP 10 — Deep Phase Synthesis per Agent
File: apps/api/agents/mixins/investigation.py → run_deep_investigation() continuation
10a. Tool counts update:

_tool_success_count, _tool_error_count — recalculated across ALL findings (initial + deep combined)

10b. _generate_agent_brief(phase="deep"):

Counts findings by verdict category for this phase
Builds _agent_brief dict: {agent_name, phase, total_findings, actionable_findings, tools_used, positive_count, suspicious_count, ...}

10c. LLM synthesis attempt (_synthesize_findings_once(findings, phase="deep", timeout_s=90.0)):

phase1_context built from self._agent_synthesis (Phase 1 synthesis stored earlier):

phase1_verdict, phase1_confidence, phase1_narrative


Passed to SynthesisService.synthesize_findings(..., phase="deep", phase1_context=phase1_context)
LLM prompt includes Phase 1 verdict for delta comparison: "Phase 1 said AUTHENTIC at 0.72 confidence; deep phase found diffusion artifacts at 0.89 — your synthesis should explain this escalation"
Stagger: agent_num * 2.0s (same as initial phase)

10d. Deterministic synthesis fallback:

Same _build_deterministic_synthesis(findings, phase="deep") logic
Uses combined initial + deep findings for verdict calculation
Deep-specific section: if no Phase 1 synthesis available in _agent_synthesis, treats all findings as equal weight

10e. Synthesis enrichment:

If synthesis dict: sets synthesis["agent_brief"] = _agent_brief (if LLM didn't produce one)
Sets synthesis["initial_findings_summary"] = initial_summary

10f. Context publish:

_publish_agent_context("deep", findings) — updates Redis with deep-phase agent context


STEP 11 — Phase-2 Arbiter Pre-warm (concurrent)
File: apps/api/orchestration/pipeline_phases.py (after all deep agents complete)
After asyncio.gather(*[_run_deep_with_stagger(aid, idx) for ...]):

Normalises all results: _deep_norm = pipeline._normalize_agent_results(results)
normalize converts AgentLoopResult objects → arbiter-expected dict format: {findings, reflection_report, react_chain, agent_had_error, synthesis}
asyncio.create_task(pipeline._run_arbiter_pre_warm(_deep_norm, case_id, suppress_broadcasts=True))
This runs arbiter.deliberate(agent_results, case_id, use_llm=False) in background
Cached as arbiter._pre_warm_report — ready for when user clicks "View Results"


STEP 12 — Second HITL Gate: _await_deep_report_request()
File: apps/api/orchestration/pipeline_phases.py → _await_deep_report_request()
12a. Status broadcast:

Updates Redis metadata: status="awaiting_deep_report", awaiting_decision=True, deep_analysis_complete=True
Broadcasts PIPELINE_PAUSED with status="awaiting_deep_report", deep_results_ready=True

12b. Frontend receives:

useSimulation receives PIPELINE_PAUSED → if data.status=="awaiting_deep_report" → sets status="complete" (deep phase done)
allAgentsDone becomes true (phase="deep", all expected agents completed)
playSound("analysis_done")
AgentProgressDisplay shows "View Results" button

12c. Backend polls:

decision_key = "forensic:session:resume_decision:{session_id}:deep_to_report"
Polls every 2s for presence of this key
Timeout: config.hitl_decision_timeout


STEP 13 — User Clicks "View Results"
File: apps/web/src/hooks/useInvestigation.ts → handleViewResults()
13a. Arbiter deliberation overlay:

setArbiterDeliberating(true) → ArbiterDeliberationOverlay (apps/web/src/components/evidence/ArbiterDeliberationOverlay.tsx) renders — full-screen frosted glass
setArbiterLiveText(UI_STRINGS.FINAL_SYNTHESIS) — initial text shown

13b. Arbiter status pre-check:

getArbiterStatus(sid) — if status=="complete" (pre-warm already finished), skip resume call
Otherwise calls resumeInvestigation(false) — deep_analysis=false, expected_phase="deep"

13c. waitForFinalReport(sid, setArbiterLiveText, ARBITER_WAIT_MAX_MS, signal) polling:

Polls GET /api/v1/sessions/{sessionId}/arbiter-status with exponential backoff (starts at ARBITER_POLL_INTERVAL_MS, max 3s)
setArbiterLiveText(cleanArbiterMessage(st.message)) — updates overlay text with arbiter progress
cleanArbiterMessage() normalises cryptic backend messages to human-readable strings
On status=="complete": retries getReport(sessionId) up to 5 times with REPORT_POLL_DELAY_MS gaps
If report has report_id: returns true


STEP 14 — Backend: Final Arbiter Deliberation
File: apps/api/orchestration/pipeline.py → _run_deliberation()
14a. Cancel pre-warm task:

if self._pre_warm_task: self._pre_warm_task.cancel(); self._pre_warm_task = None
arbiter.clear_pre_warm_cache() — clears in-memory report
BUT: immediately re-assigns: arbiter._pre_warm_agent_results = arbiter_results, arbiter._pre_warm_case_id = case_id
This ensures finalise_from_cache() has the fresh combined results

14b. Broadcast "Compiling final report":

_broadcast_final_arbiter_status(session_id, "deliberating", "Compiling final report from agent findings.")
Sends ARBITER_UPDATE WebSocket message → frontend overlay updates text

14c. arbiter.finalise_from_cache(use_llm=False, artifact_mime) with 90s timeout:

File: apps/api/agents/arbiter.py
Awaits _pre_warm_task if still running (up to 30s)
use_llm=False and _pre_warm_report exists → returns cached report directly (fast path)
If no cached report: calls arbiter.deliberate(agent_results, case_id, use_llm=False, artifact_mime)

14d. arbiter.deliberate() (if cache miss):

File: apps/api/agents/arbiter.py
Iterates all agent findings from all 5 agents (initial + deep combined)
Per finding: evidence_verdict_of(finding), confidence_of(finding), assign_severity_tier(finding) (apps/api/agents/arbiter_verdict.py)
cross_agent_comparison(finding_a, finding_b) — for each pair of agents on same forensic dimension: AGREEMENT, INDEPENDENT, or CONTRADICTION
cross_modal_fuse(agent_results) (apps/api/core/cross_modal_fusion.py) — correlates multi-modal signals (e.g. Agent1 pixel anomaly + Agent5 EXIF strip = cross-modal confirmation)
Challenge loop: for findings in CONTRADICTION — re-invokes the challenged agent's run_challenge() method (up to MAX_CHALLENGE_ATTEMPTS=2)
Tribunal: unresolved contradictions → TribunalCase model flagged for human review
calculate_manipulation_probability(findings, metrics) (apps/api/agents/arbiter_verdict.py) — weighted scoring formula across all agents
Determines overall_verdict: "AUTHENTIC"/"MANIPULATED"/"INCONCLUSIVE"/"REVIEW REQUIRED"
Builds per_agent_metrics[aid] = AgentMetrics(total_tools_called, tools_succeeded, error_rate, confidence_score, finding_count, deep_finding_count)
per_agent_analysis — optional per-agent Groq narratives (if LLM enabled)
Returns ForensicReport (apps/api/agents/arbiter_verdict.py)

14e. Broadcast "Council verdict selected":

_broadcast_final_arbiter_status(session_id, "synthesizing", f"Council verdict selected: {report.overall_verdict}. Signing and caching the report.")


STEP 15 — Report Enrichment, Signing, Persistence
File: apps/api/orchestration/pipeline_enrichment.py → enrich_report()
15a. Custody chain verification:

Reads all custody log entries for this session from PostgreSQL
Verifies hash chain: each entry's previous_hash matches the prior entry's computed hash
Sets report.custody_chain_verified = True/False
Appends any custody anomalies to degradation_flags

15b. Report field enrichment:

report.is_deep_analysis = True (since deep analysis was run)
report.applicable_agent_count = count of non-skipped agents
report.skipped_agents = {agent_id: reason} for skipped agents
report.analysis_coverage_note — text explaining which file dimensions were covered
report.cross_modal_fusion = fusion result dict from arbiter
Calls arbiter.regenerate_missing_narratives(report) if per_agent_analysis is all empty (Groq timeout recovery)

15c. Degradation flags:

report.degradation_flags = list(pipeline._degradation_flags) — all accumulated warnings (Redis unavailable, Qdrant unavailable, arbiter LLM timeout, etc.)

15d. ECDSA report signing (arbiter.sign_report(report)):

get_keystore() (apps/api/core/signing.py) — returns KeyStore singleton
keystore.get_or_create(AgentID.ARBITER) — gets or generates ECDSA key pair for arbiter
report_hash = hashlib.sha256(canonical_json(report)).hexdigest() — canonical JSON serialisation (sorted keys)
signature = private_key.sign(report_hash.encode()) — ECDSA P-256 signature
report.cryptographic_signature = base64.b64encode(signature).decode()
report.report_hash = report_hash
report.signed_utc = datetime.now(UTC).isoformat()
Returns signed ForensicReport

15e. Session state update:

session_manager.set_final_report(session_id, report.report_id) — writes report ID to session record in Redis and PostgreSQL

15f. Redis cache:

set_final_report(session_id, report) (apps/api/api/routes/_session_state.py)
Serialises report as JSON, stores under forensic:report:{session_id} with TTL

15g. PostgreSQL persistence:

session_persistence.save_report(session_id, report.model_dump(mode="json")) — writes full report JSON to session_reports table, updates status="completed"

15h. Custody log — REPORT_SIGNED:

custody_logger.log_entry(EntryType.REPORT_SIGNED, agent_id=ARBITER, content={report_id, total_findings})

15i. REPORT_READY broadcast:

broadcast_update(session_id, BriefUpdate(type="REPORT_READY", data={report_id, verdict}))
WebSocket → frontend useSimulation receives → sets status="complete"

15j. Final arbiter status:

_broadcast_final_arbiter_status(session_id, "complete", f"Council report ready: {overall_verdict}.")
Updates Redis metadata: status="completed", brief=message, awaiting_decision=False


STEP 16 — Frontend: Navigation to Result Page
File: apps/web/src/hooks/useInvestigation.ts → waitForFinalReport() → navigation
16a. Arbiter polling receives complete:

waitForFinalReport() confirms getReport(sessionId) has report_id — returns true

16b. Minimum overlay display:

elapsed = Date.now() - arbiterStartTime
If elapsed < ARBITER_MIN_DISPLAY_MS: await setTimeout(ARBITER_MIN_DISPLAY_MS - elapsed) — prevents flash-dismiss of overlay

16c. Session storage flags:

sessionStorage[FC_REPORT_READY:{sid}] = "1" — result page reads this to know report is ready
sessionStorage[FC_ARBITER_TRANSITIONING:{sid}] = "1" — prevents WebSocket reconnect during transition

16d. Navigation:

document.body.setAttribute("data-fc-loading", "1") — prevents input during navigation
await requestAnimationFrame() — one final paint of the overlay
router.push('/result/{encodeURIComponent(sid)}') — Next.js client navigation


STEP 17 — Result Page: Report Fetch and Render
File: apps/web/src/app/result/[sessionId]/page.tsx → DynamicResultClient → useResult(sessionId)
17a. Report fetch:

GET /api/v1/sessions/{sessionId}/report (apps/api/api/routes/sessions.py → get_session_report())
Resolution order: in-memory pipeline → in-memory _final_reports cache → Redis cache → PostgreSQL
Returns ReportDTO (mapped from ForensicReport via _forensic_report_to_dto())

17b. Result page assembly:

ResultLayout renders using ReportDTO:

ResultHeader — filename from localStorage[FILE_NAME:{sid}], case ID, investigator ID
VerdictSection — overall_verdict, overall_confidence, manipulation_probability, ArcGauge
KeyFindings — report.key_findings array rendered as severity-coloured cards
AgentAnalysisTab — per_agent_findings → AgentFindingCard per agent, with initial vs deep finding tabs
IntelligenceBrief — executive_summary, summary_structured sections
ReportIntegrity — cryptographic_signature, report_hash, signed_utc
DeepModelTelemetry — per_agent_metrics (error rates, confidence, tool counts, deep_finding_count)
TimelineTab — ExecutionTimeline reconstructed from timing metadata
HistoryPanel — GET /api/v1/sessions for session list


EvidenceThumbnail reads localStorage[THUMBNAIL:{sid}] for image preview
Export buttons: PDF/DOCX/JSON via dedicated download routes


Key Audit Focal Points Per Flow
Initial Analysis — highest-risk areas:

_detect_mime_from_head() — magic fallback to PIL using only 8192 bytes head; truncated EXIF files may misclassify
classify_evidence_file() heuristics — is_screen_capture_like() relies on filename string matching and dimension ratios; easy to misclassify a low-res camera photo as screenshot
visual_evidence_profile_handler dynamic routing — skip_tools applied after task list built; race if working_memory.update_state() fails silently
inject_task() dedup check — checks PENDING, IN_PROGRESS, COMPLETE but NOT tasks injected within the same event loop tick before Redis write completes
_synthesize_findings_once() agent stagger — agent_num * 2.0s computed from regex on agent_id string; non-standard agent IDs produce _agent_num = 0, all agents attempt simultaneously

Deep Analysis — highest-risk areas:

working_memory.clear() before deep phase — clears per-agent Redis state but NOT inter_agent_bus visual profile; stale Phase 1 Gemini result persists in bus
_broadcast_context() — Phase 1 visual profile pre-injected before deep agents start; but if Agent1 fails in deep phase (Gemini 429), context_event.set() fires with no data, Agents 2/3/5 proceed without visual grounding
_run_agent_deep_only() timeout — deep_timeout = min(config.investigation_timeout // 4, 480.0) — integer division on Python float if investigation_timeout is float; may truncate to unexpected value
Phase-2 pre-warm task race — invalidate_pre_warm() called in /resume endpoint, then _run_deliberation() re-assigns _pre_warm_agent_results directly; if worker is on a different process (Redis worker mode), in-process pipeline is None, pre-warm invalidation via pipeline ref is skipped entirely
finalise_from_cache(use_llm=False) with valid _pre_warm_report — always returns cached report without re-running deliberation on final combined findings; if pre-warm ran during the deep phase with only Phase 1 results (stale cache), final report misses all deep findings