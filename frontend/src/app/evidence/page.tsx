/**
 * Evidence Investigation Page
 * ===========================
 *
 * Main page for forensic evidence upload and analysis.
 * Orchestrates the two-phase investigation workflow with WebSocket updates.
 *
 * Flow:
 *   Upload → Initial Analysis → [Accept Analysis | Deep Analysis]
 *   Accept Analysis → Arbiter synthesis → Results page
 *   Deep Analysis → heavy ML scan → [New Analysis | View Results]
 */

"use client";

import React, { useState, useCallback, useRef, useEffect, useMemo } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import { CheckCircle2, Circle, AlertCircle, PlayCircle } from "lucide-react";
import { AnimatePresence, motion } from "framer-motion";
import { ShieldCheck } from "lucide-react";

import { useSimulation } from "@/hooks/useSimulation";
import { PageTransition } from "@/components/ui/PageTransition";
import { GlobalFooter } from "@/components/ui/GlobalFooter";
import { useSound } from "@/hooks/useSound";
import { startInvestigation, submitHITLDecision, type InvestigationResponse } from "@/lib/api";
import { AGENTS_DATA, ALLOWED_MIME_TYPES } from "@/lib/constants";

import {
  HeaderSection,
  FileUploadSection,
  AgentProgressDisplay,
  ErrorDisplay,
  HITLCheckpointModal,
  AgentUpdate,
} from "@/components/evidence";

/** Dev-only logger — silenced in production builds */
const isDev = process.env.NODE_ENV !== "production";
const dbg = {
  error: isDev ? console.error.bind(console) : () => {},
};

export default function EvidencePage() {
  const router = useRouter();
  const { playSound } = useSound();

  // Stable investigator ID — generated once, stored in sessionStorage and a ref.
  // NOTE: useRef does NOT accept a lazy-initializer function like useState does.
  // We must compute the value first, then pass it directly to useRef().
  const _initInvestigatorId = (): string => {
    if (typeof window === "undefined") return "REQ-000000";
    const stored = sessionStorage.getItem("forensic_investigator_id");
    const validIdPattern = /^REQ-\d{5,10}$/;
    if (stored && validIdPattern.test(stored)) return stored;
    const fresh = "REQ-" + (Math.floor(Math.random() * 900000) + 100000);
    sessionStorage.setItem("forensic_investigator_id", fresh);
    return fresh;
  };
  // eslint-disable-next-line react-hooks/exhaustive-deps
  const investigatorIdRef = useRef<string>(_initInvestigatorId());

  // File upload state
  const [file, setFile] = useState<File | null>(null);
  const [isDragging, setIsDragging] = useState(false);
  const [validationError, setValidationError] = useState<string | null>(null);
  const [isUploading, setIsUploading] = useState(false);

  // Phase tracking: initial analysis vs deep analysis
  const [phase, setPhase] = useState<"initial" | "deep">("initial");

  // HITL state
  const [isSubmittingHITL, setIsSubmittingHITL] = useState(false);

  // Navigation loading state — declared early so callbacks below can reference it
  const [isNavigating, setIsNavigating] = useState(false);
  const [showArbiterOverlay, setShowArbiterOverlay] = useState(false);

  // Tracks whether analysis_done sound has been played for current session
  const analysisCompleteSoundedRef = useRef(false);

  // Simulation/Analysis state
  const {
    status,
    agentUpdates,
    completedAgents,
    pipelineMessage,
    pipelineThinking,
    startSimulation,
    connectWebSocket,
    resumeInvestigation,
    resetSimulation: resetSimulationHook,
    hitlCheckpoint,
    errorMessage,
    dismissCheckpoint,
    clearCompletedAgents,
    restoreSimulationState,
  } = useSimulation({
    playSound,
    onComplete: () => {
      // Analysis complete callback
    },
  });

  const fileInputRef = useRef<HTMLInputElement>(null);

  // Memoize file preview URL to avoid memory leaks
  const filePreviewUrl = useMemo(() => {
    if (!file) return null;
    if (file.type.startsWith("image/") || file.type.startsWith("video/")) {
      return URL.createObjectURL(file);
    }
    return null;
  }, [file]);

  // Cleanup blob URL on unmount
  useEffect(() => {
    return () => {
      if (filePreviewUrl) {
        URL.revokeObjectURL(filePreviewUrl);
      }
    };
  }, [filePreviewUrl]);

  // Evidence page load sound — plays once on mount (AudioContext unlocked by CTA click on landing)
  useEffect(() => {
    const id = setTimeout(() => playSound("page_load"), 280);
    return () => clearTimeout(id);
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // State restoring guard to prevent initial mount flicker
  const isRestoringRef = useRef(typeof window !== "undefined" ? sessionStorage.getItem("forensic_restore_view") === "true" : false);

  // Restore state if returning from Result page
  useEffect(() => {
    if (isRestoringRef.current) {
      sessionStorage.removeItem("forensic_restore_view");
      const isDeep = sessionStorage.getItem("forensic_is_deep") === "true";
      try {
        const stored = sessionStorage.getItem(isDeep ? "forensic_deep_agents" : "forensic_initial_agents");
        if (stored) {
           const agents = JSON.parse(stored);
           setPhase(isDeep ? "deep" : "initial");
           restoreSimulationState(agents, isDeep ? "complete" : "awaiting_decision");
        }
      } catch (e) {
        dbg.error("Failed to restore agents", e);
      }
      isRestoringRef.current = false;
    }
  }, [restoreSimulationState]);

  // Reset simulation wrapper
  const resetSimulation = useCallback(() => {
    setIsUploading(false);
    setPhase("initial");
    resetSimulationHook();
  }, [resetSimulationHook]);

  // Start investigation analysis
  const triggerAnalysis = useCallback(
    async (targetFile: File) => {
      if (!targetFile) return;
      playSound("upload");
      setIsUploading(true);
      setValidationError(null);
      setPhase("initial");
      startSimulation();

      try {
        // Yield an event loop tick so React can paint the "initiating" UI before heavy upload work blocks the thread.
        await new Promise<void>((resolve) => setTimeout(resolve, 50));

        // Use IDs pre-generated by the landing page (already stored in sessionStorage).
        // If the landing page wasn't used (direct navigation), fall back to generating fresh ones.
        const investigatorId = investigatorIdRef.current;
        const caseId =
          sessionStorage.getItem("forensic_case_id") || "CASE-" + Date.now();

        // Pick up the in-flight investigation Promise started by handleInitiate on the
        // landing page the moment the user clicked Analyze — it's been running during
        // the 380 ms animation and page navigation, so it may already be resolved.
        const win = window as {
          __forensic_investigation_promise?: Promise<InvestigationResponse>;
        };
        const inflightPromise = win.__forensic_investigation_promise;
        if (inflightPromise) delete win.__forensic_investigation_promise;

        const res = await (
          inflightPromise ?? startInvestigation(targetFile, caseId, investigatorId)
        );

        sessionStorage.setItem("forensic_session_id", res.session_id);
        sessionStorage.setItem("forensic_file_name", targetFile.name);
        sessionStorage.setItem("forensic_case_id", caseId);
        sessionStorage.setItem("forensic_investigator_id", investigatorId);

        try {
          await connectWebSocket(res.session_id);
          setIsUploading(false);
        } catch (wsErr: unknown) {
          dbg.error("WebSocket connection failed", wsErr);
          const wsErrMsg = wsErr instanceof Error ? wsErr.message : "Failed to connect to analysis streams";
          setValidationError(wsErrMsg);
          setIsUploading(false);
          resetSimulation();
        }
      } catch (err: unknown) {
        dbg.error("Investigation start failed", err);
        let errorMsg = err instanceof Error ? err.message : "Failed to start investigation";
        // Surface common backend errors clearly
        if (errorMsg.includes("422") || errorMsg.toLowerCase().includes("unprocessable")) {
          errorMsg = "Upload rejected by server — check file type and try again.";
        } else if (errorMsg.includes("429")) {
          errorMsg = "Too many investigations started. Please wait a moment and try again.";
        } else if (errorMsg.includes("413")) {
          errorMsg = "File is too large. Maximum size is 50 MB.";
        } else if (errorMsg.includes("401") || errorMsg.includes("Unauthorized")) {
          errorMsg = "Session expired — please refresh the page and try again.";
        }
        setValidationError(errorMsg);
        setIsUploading(false);
        resetSimulation();
        playSound("error");
      }
    },
    [playSound, startSimulation, connectWebSocket, resetSimulation]
  );

  // Pick up file injected from landing page
  useEffect(() => {
    const pending = (window as { __forensic_pending_file?: File }).__forensic_pending_file;
    if (pending) {
      delete (window as { __forensic_pending_file?: File }).__forensic_pending_file;
      setFile(pending);

      const autoStart = sessionStorage.getItem("forensic_auto_start");
      if (autoStart === "true") {
        sessionStorage.removeItem("forensic_auto_start");
        triggerAnalysis(pending);
      }
    } else if (sessionStorage.getItem("forensic_auto_start") === "true") {
      setValidationError("File was not received. Please re-select.");
      sessionStorage.removeItem("forensic_auto_start");
    }
  }, [triggerAnalysis]);
  
  // Handle 'sample' query parameter for quick demo
  const searchParams = useSearchParams();
  useEffect(() => {
    if (searchParams.get('sample') === 'true' && status === 'idle') {
      // Mock a sample file for the demo
      const sampleFile = new File(["sample data"], "sample_evidence.png", { type: "image/png" });
      setFile(sampleFile);
      triggerAnalysis(sampleFile);
    }
  }, [searchParams, status, triggerAnalysis]);

  // Validate file — uses the single canonical ALLOWED_MIME_TYPES from constants.ts
  const validateFile = (f: File): boolean => {
    setValidationError(null);
    if (f.size > 50 * 1024 * 1024) {
      setValidationError("File must be under 50MB");
      return false;
    }
    if (!ALLOWED_MIME_TYPES.has(f.type)) {
      setValidationError(`File type "${f.type || "unknown"}" is not supported. Upload an image, video, or audio file.`);
      return false;
    }
    return true;
  };

  // Handle file selection
  const handleFile = (f: File) => {
    if (validateFile(f)) {
      setFile(f);
      playSound("success");
    } else {
      playSound("error");
    }
  };

  // Handle HITL decision
  const handleHITLDecision = async (
    decision: "APPROVE" | "REDIRECT" | "OVERRIDE" | "TERMINATE" | "ESCALATE",
    note?: string
  ) => {
    if (!hitlCheckpoint) return;
    setIsSubmittingHITL(true);

    try {
      const { session_id, checkpoint_id, agent_id } = hitlCheckpoint;
      await submitHITLDecision({
        session_id,
        checkpoint_id,
        agent_id,
        decision,
        note: note || `Investigator decision: ${decision}`,
      });
      dismissCheckpoint();
      playSound("success");
    } catch (err) {
      dbg.error("HITL decision failed", err);
      playSound("error");
    } finally {
      setIsSubmittingHITL(false);
    }
  };

  // === Decision handlers for the two-phase flow ===

  // Accept Analysis → skip deep, arbiter compiles, go to results
  const handleAcceptAnalysis = useCallback(async () => {
    if (isNavigating) return;
    playSound("arbiter_start");
    sessionStorage.setItem("forensic_is_deep", "false");
    sessionStorage.setItem("forensic_initial_agents", JSON.stringify(completedAgents));
    setIsNavigating(true);
    setShowArbiterOverlay(true); // Show arbiter progress overlay
    try {
      // Tell the backend to skip deep analysis and compile the report via the arbiter.
      await resumeInvestigation(false);
      // Small pause so the backend registers the resume before result page polls
      await new Promise(r => setTimeout(r, 400));
      router.push("/result");
    } catch (err) {
      dbg.error("Accept analysis failed", err);
      playSound("error");
      setIsNavigating(false);
      setShowArbiterOverlay(false);
    }
  }, [playSound, resumeInvestigation, router, isNavigating, completedAgents]);

  // Deep Analysis → run heavy ML pass
  const handleDeepAnalysis = useCallback(async () => {
    playSound("think");
    sessionStorage.setItem("forensic_is_deep", "true");
    // Reset sound guard so analysis_done can play again at end of deep phase
    analysisCompleteSoundedRef.current = false;
    // Clear initial-phase completed agents so allAgentsDone starts fresh in deep phase
    clearCompletedAgents();
    setPhase("deep");
    await resumeInvestigation(true);
  }, [playSound, resumeInvestigation, clearCompletedAgents]);

  // New Analysis → clear everything, go to upload form
  const handleNewUpload = useCallback(() => {
    playSound("click");
    setFile(null);
    setPhase("initial");
    setIsNavigating(false);
    resetSimulation();
    sessionStorage.removeItem('forensic_session_id');
    sessionStorage.removeItem('forensic_file_name');
    sessionStorage.removeItem('forensic_case_id');
  }, [resetSimulation, playSound]);

  // View Results → after deep analysis the arbiter already compiled — just navigate
  const handleViewResults = useCallback(async () => {
    if (isNavigating) return;
    playSound("arbiter_start");
    sessionStorage.setItem("forensic_deep_agents", JSON.stringify(completedAgents));
    setIsNavigating(true);
    setShowArbiterOverlay(true); // Show arbiter progress overlay
    // Small pause to let the user see the overlay before navigating
    await new Promise(r => setTimeout(r, 500));
    router.push("/result");
  }, [playSound, router, isNavigating, completedAgents]);

  // Determine what to show
  const validAgentsData = AGENTS_DATA.filter(a => a.name !== "Council Arbiter");
  const validCompletedAgents = completedAgents.filter((c: AgentUpdate) =>
    validAgentsData.some(v => v.id === c.agent_id)
  );

  // In deep phase, unsupported agents never run — only count supported ones
  const unsupportedAgentIds = new Set(
    validCompletedAgents
      .filter(c =>
        c.error?.includes("Not applicable") ||
        c.error?.includes("not applicable") ||
        c.error?.includes("not supported") ||
        c.error?.includes("Format not supported") ||
        c.message?.includes("not applicable") ||
        c.message?.includes("not supported") ||
        c.message?.includes("Skipping") ||
        c.message?.includes("Skipped") ||
        (c.findings_count === 0 && c.confidence === 0 && !!c.error)
      )
      .map(c => c.agent_id)
  );
  const supportedAgentCount = validAgentsData.filter(a => !unsupportedAgentIds.has(a.id)).length;
  const supportedCompletedCount = validCompletedAgents.filter(c => !unsupportedAgentIds.has(c.agent_id)).length;

  // allAgentsDone: all supported agents finished (deep or initial)
  // For deep phase: also accept status==="complete" (PIPELINE_COMPLETE) since unsupported
  // agents don't send AGENT_COMPLETE in deep phase after completedAgents was cleared.
  const allAgentsDone = phase === "deep"
    ? status === "complete" || (supportedCompletedCount >= supportedAgentCount && supportedAgentCount > 0)
    : validCompletedAgents.length >= validAgentsData.length;

  // Awaiting decision = backend sent PIPELINE_PAUSED
  const awaitingDecision = status === "awaiting_decision";

  // Play analysis_done sound once when initial analysis finishes (PIPELINE_PAUSED)
  useEffect(() => {
    if (awaitingDecision && !analysisCompleteSoundedRef.current) {
      analysisCompleteSoundedRef.current = true;
      playSound("analysis_done");
    }
    if (!awaitingDecision && status === "idle") {
      analysisCompleteSoundedRef.current = false; // reset for next session
    }
  }, [awaitingDecision, status, playSound]);

  const hasStartedAnalysis =
    status === "initiating" ||
    status === "analyzing" ||
    status === "processing" ||
    status === "complete" ||
    status === "awaiting_decision" ||
    isUploading ||
    validCompletedAgents.length > 0 ||
    Object.keys(agentUpdates).length > 0;

  const showUploadForm =
    (status === "idle" ||
      (status === "error" && !hasStartedAnalysis)) &&
    !isUploading &&
    !isRestoringRef.current;

  // Show agent progress for both phases
  const showAgentProgress = hasStartedAnalysis && !showUploadForm;

  // After deep analysis, show results buttons when all agents done + pipeline complete
  const deepAnalysisDone = phase === "deep" && (status === "complete" || allAgentsDone);

  // Progress text — specific and contextual
  const runningAgentNames = Object.keys(agentUpdates)
    .map(id => validAgentsData.find(a => a.id === id)?.name)
    .filter((n): n is string => !!n);

  let progressText = "Establishing secure forensic pipeline…";
  if (awaitingDecision) {
    progressText = "Initial analysis complete. Choose how to proceed.";
  } else if (phase === "deep" && (status === "complete" || deepAnalysisDone)) {
    progressText = "Deep analysis complete. All findings collected.";
  } else if (phase === "deep") {
    if (runningAgentNames.length === 1) {
      progressText = `${runningAgentNames[0]} running deep ML scan…`;
    } else if (runningAgentNames.length > 1) {
      progressText = `${runningAgentNames.length} agents running deep ML scan…`;
    } else {
      progressText = "Running deep forensic analysis with heavy ML models…";
    }
  } else if (status === "complete") {
    progressText = "All agents have reported. Council consensus reached.";
  } else if (validCompletedAgents.length > 0) {
    const remaining = validAgentsData.length - validCompletedAgents.length;
    if (runningAgentNames.length > 0) {
      const names = runningAgentNames.length === 1
        ? runningAgentNames[0]
        : `${runningAgentNames.length} agents`;
      progressText = `${validCompletedAgents.length}/${validAgentsData.length} complete — ${names} still scanning…`;
    } else {
      progressText = `${validCompletedAgents.length} of ${validAgentsData.length} agents complete — ${remaining} remaining…`;
    }
  } else if (runningAgentNames.length > 0) {
    if (runningAgentNames.length === 1) {
      progressText = `${runningAgentNames[0]} is scanning the evidence…`;
    } else {
      progressText = `${runningAgentNames.length} agents actively scanning the evidence…`;
    }
  } else if (status === "analyzing" || status === "initiating") {
    progressText = isUploading ? "Uploading and encrypting evidence securely…" : "Deploying forensic agents…";
  } else if (isUploading) {
    progressText = "Uploading and encrypting evidence securely…";
  }

  return (
    <div className="min-h-screen bg-[#050505] text-white p-6 pb-20 overflow-x-hidden relative">
      {/* Background gradient */}
      <div className="fixed inset-0 bg-[radial-gradient(ellipse_at_top,_var(--tw-gradient-stops))] from-slate-900/30 via-black to-black -z-50" />

      {/* Arbiter compiling overlay — shown when user accepts or views results */}
      {showArbiterOverlay && (
        <div
          className="fixed inset-0 z-50 flex items-center justify-center bg-black/80 backdrop-blur-md"
          role="dialog"
          aria-modal="true"
          aria-label="Council Arbiter deliberating"
        >
          <motion.div
            initial={{ opacity: 0, scale: 0.9, y: 12 }}
            animate={{ opacity: 1, scale: 1, y: 0 }}
            className="glass-panel flex flex-col items-center gap-6 px-8 py-10 rounded-3xl shadow-[0_20px_80px_rgba(0,0,0,0.85),0_0_60px_rgba(124,58,237,0.12)] max-w-xs w-full mx-4 border-violet-500/22"
          >
            <div className="relative w-20 h-20 flex items-center justify-center">
              <motion.div
                animate={{ scale: [1, 1.2, 1], opacity: [0.2, 0.45, 0.2] }}
                transition={{ duration: 2.2, repeat: Infinity, ease: "easeInOut" }}
                className="absolute inset-0 rounded-full bg-purple-500/20 border border-purple-500/30"
              />
              <div className="relative z-10 w-12 h-12 rounded-full bg-purple-950/80 border border-purple-500/40 flex items-center justify-center shadow-[0_0_30px_rgba(168,85,247,0.4)]">
                <ShieldCheck className="w-6 h-6 text-purple-300" />
              </div>
              <motion.div
                animate={{ rotate: 360 }}
                transition={{ duration: 2.8, repeat: Infinity, ease: "linear" }}
                className="absolute inset-0 pointer-events-none"
              >
                <div className="absolute top-0.5 left-1/2 -translate-x-1/2 w-1.5 h-1.5 rounded-full bg-purple-400 shadow-[0_0_6px_rgba(168,85,247,1)]" />
              </motion.div>
            </div>
            <div className="text-center space-y-1.5">
              <p className="text-white font-bold">Council Arbiter Deliberating</p>
              <p className="text-purple-300/70 text-sm font-mono">Synthesising all agent findings…</p>
              <p className="text-slate-700 text-xs mt-2">Redirecting to results shortly</p>
            </div>
            <div className="relative w-full h-0.5 bg-white/5 rounded-full overflow-hidden">
              <div
                className="absolute h-full w-[40%] bg-gradient-to-r from-transparent via-purple-400 to-transparent"
                style={{ animation: "bar-slide 2.2s ease-in-out infinite" }}
              />
            </div>
          </motion.div>
        </div>
      )}

      {/* Header */}
      <HeaderSection
        status={status}
        showBrowse={showUploadForm}
        onBrowseClick={() => fileInputRef.current?.click()}
      />

      {/* Main content */}
      <main className="max-w-6xl mx-auto relative z-10 px-6 sm:px-8">
        {/* Phase Indicator */}
        {hasStartedAnalysis && (
          <motion.div 
            initial={{ opacity: 0, y: -10 }}
            animate={{ opacity: 1, y: 0 }}
            className="mb-12 flex items-center justify-center"
          >
            <div className="flex items-center gap-4 bg-white/[0.03] border border-white/[0.08] p-1.5 rounded-2xl backdrop-blur-sm">
              <div className={`flex items-center gap-2.5 px-5 py-2.5 rounded-xl transition-all duration-500 ${
                phase === "initial" 
                  ? "bg-cyan-500/10 text-cyan-400 border border-cyan-500/20" 
                  : "text-slate-500 opacity-60"
              }`}>
                {phase === "initial" && status !== "complete" && !awaitingDecision ? (
                  <div className="w-2.5 h-2.5 rounded-full bg-cyan-400 animate-pulse" />
                ) : (
                  <CheckCircle2 className={`w-4 h-4 ${phase === "deep" || awaitingDecision || status === "complete" ? "text-cyan-400" : ""}`} />
                )}
                <span className="text-[11px] font-mono uppercase tracking-[0.15em] font-bold">1. Rapid Forensic Scan</span>
              </div>
              
              <div className="w-8 h-px bg-white/10" />

              <div className={`flex items-center gap-2.5 px-5 py-2.5 rounded-xl transition-all duration-500 ${
                phase === "deep" 
                  ? "bg-violet-500/10 text-violet-400 border border-violet-500/20 shadow-[0_0_20px_rgba(139,92,246,0.1)]" 
                  : "text-slate-500 opacity-60"
              }`}>
                {phase === "deep" && status !== "complete" ? (
                  <div className="w-2.5 h-2.5 rounded-full bg-violet-400 animate-pulse shadow-[0_0_8px_rgba(139,92,246,0.8)]" />
                ) : (
                  <Circle className={`w-4 h-4 ${phase === "deep" && status === "complete" ? "text-violet-400" : ""}`} />
                )}
                <span className="text-[11px] font-mono uppercase tracking-[0.15em] font-bold">2. Deep Investigative Analysis</span>
              </div>
            </div>
          </motion.div>
        )}

        <PageTransition>
        <AnimatePresence mode="wait">
          {/* Upload Form */}
          {showUploadForm && (
            <FileUploadSection
              key="upload-form"
              file={file}
              isDragging={isDragging}
              isUploading={isUploading}
              validationError={validationError}
              onFileSelect={handleFile}
              onFileDrop={handleFile}
              onDragEnter={() => setIsDragging(true)}
              onDragLeave={() => setIsDragging(false)}
              onUpload={triggerAnalysis}
              onClear={() => {
                setFile(null);
                setValidationError(null);
              }}
            />
          )}

          {/* Agent Progress — handles both initial and deep phases */}
          {showAgentProgress && (
            <AgentProgressDisplay
              key="agent-progress"
              agentUpdates={agentUpdates}
              completedAgents={validCompletedAgents}
              progressText={progressText}
              allAgentsDone={allAgentsDone}
              phase={phase}
              awaitingDecision={awaitingDecision}
              pipelineStatus={status}
              pipelineMessage={pipelineMessage || pipelineThinking}
              onAcceptAnalysis={handleAcceptAnalysis}
              onDeepAnalysis={handleDeepAnalysis}
              onNewUpload={handleNewUpload}
              onViewResults={handleViewResults}
              playSound={playSound}
              isNavigating={isNavigating}
            />
          )}

          {/* Error Display */}
          {(validationError || errorMessage) && !showAgentProgress && !showUploadForm && (
            <div key="error-display" className="flex flex-col items-center justify-center min-h-[60vh]">
              <ErrorDisplay
                message={validationError || errorMessage || "Unknown error"}
                onDismiss={() => {
                  setValidationError(null);
                  resetSimulation();
                }}
                onRetry={() => {
                  if (file) {
                    triggerAnalysis(file);
                  }
                }}
                showRetry={!!file}
              />
            </div>
          )}
        </AnimatePresence>
      </PageTransition>
      </main>

      {/* HITL Checkpoint Modal */}
      <HITLCheckpointModal
        checkpoint={hitlCheckpoint}
        isOpen={!!hitlCheckpoint}
        isSubmitting={isSubmittingHITL}
        onDecision={handleHITLDecision}
        onDismiss={dismissCheckpoint}
      />

      <GlobalFooter />

      {/* Hidden file input */}
      <input
        ref={fileInputRef}
        type="file"
        onChange={(e: React.ChangeEvent<HTMLInputElement>) => {
          const f = e.target.files?.[0];
          if (f) handleFile(f);
        }}
        className="hidden"
        accept="image/*,video/*,audio/*,.pdf,.doc,.docx"
        aria-label="Upload evidence file"
      />
    </div>
  );
}
