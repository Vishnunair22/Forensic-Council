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

import React, { useState, useCallback, useRef, useEffect, useLayoutEffect, useMemo } from "react";
import { useRouter } from "next/navigation";
import { useSimulation } from "@/hooks/useSimulation";
import { PageTransition } from "@/components/ui/PageTransition";
import { useSound } from "@/hooks/useSound";
import {
  startInvestigation,
  submitHITLDecision,
  autoLoginAsInvestigator,
  DuplicateInvestigationError,
  getArbiterStatus,
  getReport,
  type InvestigationResponse,
} from "@/lib/api";
import { AGENTS_DATA, ALLOWED_MIME_TYPES } from "@/lib/constants";
import { __pendingFileStore } from "@/lib/pendingFileStore";
import { LoadingOverlay } from "@/components/ui/LoadingOverlay";
import { ForensicProgressOverlay } from "@/components/ui/ForensicProgressOverlay";

import {
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

const POLL_REQUEST_MS = 12_000;

function withTimeout<T>(p: Promise<T>, ms: number): Promise<T> {
  return new Promise((resolve, reject) => {
    const t = setTimeout(() => reject(new Error("request timed out")), ms);
    p.then(
      (v) => {
        clearTimeout(t);
        resolve(v);
      },
      (e) => {
        clearTimeout(t);
        reject(e);
      }
    );
  });
}

/** Poll until the signed report is available (HTTP — survives WS teardown on navigation). */
async function waitForFinalReport(
  sessionId: string,
  onLiveMessage: (message: string) => void,
  maxMs: number,
  signal?: AbortSignal,
): Promise<boolean> {
  const deadline = Date.now() + maxMs;
  while (Date.now() < deadline) {
    if (signal?.aborted) return false;
    try {
      const st = await withTimeout(getArbiterStatus(sessionId), POLL_REQUEST_MS);
      if (st.message) onLiveMessage(st.message);
      if (st.status === "error") {
        throw new Error(st.message || "Council synthesis failed.");
      }
    } catch (e) {
      if (e instanceof Error && e.message.includes("Council synthesis")) throw e;
      /* timeout / network — keep polling */
    }
    try {
      const res = await withTimeout(getReport(sessionId), POLL_REQUEST_MS);
      if (res.status === "complete" && res.report) return true;
    } catch {
      /* in progress, 404, timeout, or not yet persisted */
    }
    await new Promise<void>((r) => {
      const timer = setTimeout(r, 550);
      signal?.addEventListener("abort", () => clearTimeout(timer), { once: true });
    });
    if (signal?.aborted) return false;
  }
  return false;
}

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
  const investigatorIdRef = useRef<string>(_initInvestigatorId());

  // File upload state
  const [file, setFile] = useState<File | null>(null);
  const [isDragging, setIsDragging] = useState(false);
  const [validationError, setValidationError] = useState<string | null>(null);
  const [isUploading, setIsUploading] = useState(false);
  const [uploadPhaseText, setUploadPhaseText] = useState<string>("");
  const [showLoadingOverlay, setShowLoadingOverlay] = useState(
    typeof window !== "undefined" && sessionStorage.getItem("fc_show_loading") === "true"
  );
  /** True once the live analysis WebSocket has opened (not just HTTP session created). */
  const [analysisStreamReady, setAnalysisStreamReady] = useState(false);
  /** Arbiter phase — latest line from GET /arbiter-status (and WS fallback). */
  const [arbiterLiveText, setArbiterLiveText] = useState("");

  /**
   * Landing → evidence with `forensic_auto_start` suppresses the upload form until the
   * file + triggerAnalysis path runs. Must be React state (not a ref) so updates re-render
   * — refs do not trigger paint; combined with SSR/hydration this left a blank shell.
   */
  const [autoStartBlocking, setAutoStartBlocking] = useState(false);
  useLayoutEffect(() => {
    try {
      setAutoStartBlocking(
        sessionStorage.getItem("forensic_auto_start") === "true"
      );
    } catch {
      setAutoStartBlocking(false);
    }
  }, []);

  // Shared auth promise — reuse existing session if available, otherwise auto-login.
  // The landing page already calls autoLoginAsInvestigator() on mount, so the cookie
  // is usually already set by the time the evidence page loads.  Firing a second
  // redundant login round-trip here was the primary cause of the post-upload delay.
  const authReadyRef = useRef<Promise<void>>(
    typeof document !== "undefined" && document.cookie.includes("access_token")
      ? Promise.resolve() // Already authenticated from landing page — skip re-login
      : autoLoginAsInvestigator()
          .then(() => { /* auth cookie set */ })
          .catch(() => { /* handled by handleAuthError on first API call */ })
  );

  // Phase tracking:  analysis vs deep analysis
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
      // Completion is handled by the PIPELINE_COMPLETE WebSocket event
    },
  });

  const fileInputRef = useRef<HTMLInputElement>(null);
  const pollAbortRef = useRef<AbortController | null>(null);

  // Abort any in-flight polling when component unmounts
  useEffect(() => {
    return () => {
      pollAbortRef.current?.abort();
    };
  }, []);

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

  // Auto-login is handled by authReadyRef above (fires once on mount)

  // Evidence page load sound — plays once on mount (AudioContext unlocked by CTA click on landing)
  useEffect(() => {
    const id = setTimeout(() => playSound("page_load"), 280);
    return () => clearTimeout(id);
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // State restoring guard to prevent  mount flicker
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
    setAnalysisStreamReady(false);
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
      setAnalysisStreamReady(false);
      setAutoStartBlocking(false);
      setUploadPhaseText("Uploading evidence to secure pipeline…");

      const investigatorId = investigatorIdRef.current;
      const caseId =
        sessionStorage.getItem("forensic_case_id") || "CASE-" + Date.now();

      const win = window as {
        __forensic_investigation_promise?: Promise<InvestigationResponse>;
      };
      const inflightPromise = win.__forensic_investigation_promise;
      if (inflightPromise) delete win.__forensic_investigation_promise;

      // ── Phase 1: Ensure auth is ready, then HTTP upload ───────────────
      // Yield one tick so React can paint the analysis grid before the async work.
      await new Promise<void>((resolve) => setTimeout(resolve, 50));

      // Wait for the auto-login to complete before hitting the backend.
      await authReadyRef.current;

      let sessionIdToUse: string | undefined;
      try {
        const investigationRes = await (inflightPromise ??
          startInvestigation(targetFile, caseId, investigatorId));
        sessionIdToUse = investigationRes.session_id;
      } catch (err: unknown) {
        if (err instanceof DuplicateInvestigationError) {
          const sid = err.existingSessionId;
          sessionStorage.setItem("forensic_session_id", sid);
          sessionStorage.setItem("forensic_file_name", targetFile.name);
          sessionStorage.setItem("forensic_case_id", caseId);
          sessionStorage.setItem("forensic_investigator_id", investigatorId);
          sessionStorage.setItem("forensic_mime_type", targetFile.type);

          let goResults = false;
          try {
            const st = await withTimeout(getArbiterStatus(sid), POLL_REQUEST_MS);
            if (st.status === "complete") goResults = true;
          } catch {
            /* keep reconnecting */
          }
          if (!goResults) {
            try {
              const rep = await withTimeout(getReport(sid), POLL_REQUEST_MS);
              if (rep.status === "complete" && rep.report) goResults = true;
            } catch {
              /* in flight or unavailable */
            }
          }
          if (goResults) {
            setIsUploading(false);
            setUploadPhaseText("");
            playSound("success");
            setShowLoadingOverlay(false);
            sessionStorage.removeItem("fc_show_loading");
            router.push("/result");
            return;
          }

          sessionIdToUse = sid;
          setUploadPhaseText(
            "This file was already submitted — reconnecting to that investigation…"
          );
        } else {
          dbg.error("Investigation start failed", err);
          let errorMsg =
            err instanceof Error ? err.message : "Failed to start investigation";
          if (
            errorMsg.includes("422") ||
            errorMsg.toLowerCase().includes("unprocessable")
          ) {
            errorMsg =
              "Upload rejected by server — check file type and try again.";
          } else if (errorMsg.includes("429")) {
            errorMsg =
              "Too many investigations started. Please wait a moment and try again.";
          } else if (errorMsg.includes("413")) {
            errorMsg = "File is too large. Maximum size is 50 MB.";
          } else if (
            errorMsg.includes("401") ||
            errorMsg.includes("Unauthorized")
          ) {
            errorMsg =
              "Session expired — please refresh the page and try again.";
          }
          setValidationError(errorMsg);
          setIsUploading(false);
          setUploadPhaseText("");
          setShowLoadingOverlay(false);
          sessionStorage.removeItem("fc_show_loading");
          resetSimulation();
          playSound("error");
          return;
        }
      }

      if (!sessionIdToUse) {
        setIsUploading(false);
        setUploadPhaseText("");
        resetSimulation();
        return;
      }

      sessionStorage.setItem("forensic_session_id", sessionIdToUse);
      sessionStorage.setItem("forensic_file_name", targetFile.name);
      sessionStorage.setItem("forensic_case_id", caseId);
      sessionStorage.setItem("forensic_investigator_id", investigatorId);
      sessionStorage.setItem("forensic_mime_type", targetFile.type);

      // Store a small thumbnail for images so the result page can show a preview
      if (targetFile.type.startsWith("image/")) {
        try {
          const bmp = await createImageBitmap(targetFile);
          const MAX = 240;
          const scale = Math.min(MAX / bmp.width, MAX / bmp.height, 1);
          const canvas = document.createElement("canvas");
          canvas.width = Math.round(bmp.width * scale);
          canvas.height = Math.round(bmp.height * scale);
          canvas.getContext("2d")!.drawImage(bmp, 0, 0, canvas.width, canvas.height);
          bmp.close();
          const dataUrl = canvas.toDataURL("image/jpeg", 0.75);
          if (dataUrl.length < 60_000) {
            sessionStorage.setItem("forensic_thumbnail", dataUrl);
          }
        } catch {
          /* non-critical — thumbnail generation failing is fine */
        }
      } else {
        sessionStorage.removeItem("forensic_thumbnail");
      }

      startSimulation();

      // ── Phase 2: Show analysis grid immediately, connect WS in background ─
      setIsUploading(false);
      setUploadPhaseText("Connecting to analysis stream…");

      connectWebSocket(sessionIdToUse)
        .then(() => {
          setAnalysisStreamReady(true);
          setUploadPhaseText("Agents dispatching…");
        })
        .catch((wsErr: unknown) => {
          dbg.error("WebSocket connection failed", wsErr);
          const wsErrMsg =
            wsErr instanceof Error
              ? wsErr.message
              : "Failed to connect to analysis stream";
          setValidationError(wsErrMsg);
          setShowLoadingOverlay(false);
          sessionStorage.removeItem("fc_show_loading");
          resetSimulation();
        });
    },
    [
      playSound,
      startSimulation,
      connectWebSocket,
      resetSimulation,
      router,
    ]
  );

  // Pick up file injected from landing page via module-scoped store
  useEffect(() => {
    const pending = __pendingFileStore.file;
    if (pending) {
      __pendingFileStore.file = null;
      setFile(pending);

      const autoStart = sessionStorage.getItem("forensic_auto_start");
      if (autoStart === "true") {
        sessionStorage.removeItem("forensic_auto_start");
        setAutoStartBlocking(false);
        triggerAnalysis(pending);
      }
    } else if (sessionStorage.getItem("forensic_auto_start") === "true") {
      setValidationError("File was not received. Please re-select.");
      sessionStorage.removeItem("forensic_auto_start");
      setAutoStartBlocking(false);
      setShowLoadingOverlay(false);
      sessionStorage.removeItem("fc_show_loading");
    }
  }, [triggerAnalysis]);
  

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
    setShowArbiterOverlay(true);
    setArbiterLiveText("Submitting investigator decision…");
    try {
      await resumeInvestigation(false);
    } catch (err) {
      dbg.error("Accept analysis failed", err);
      playSound("error");
      setValidationError(
        err instanceof Error ? err.message : "Could not resume the investigation on the server."
      );
      setIsNavigating(false);
      setShowArbiterOverlay(false);
      return;
    }

    const sid = sessionStorage.getItem("forensic_session_id");
    if (!sid) {
      setValidationError("Session missing — start a new investigation.");
      setIsNavigating(false);
      setShowArbiterOverlay(false);
      return;
    }

    let navigated = false;
    const navigateOnce = () => {
      if (navigated) return;
      navigated = true;
      setShowArbiterOverlay(false);
      setIsNavigating(false);
      router.push("/result");
    };
    // Guaranteed exit if polling hangs (unlikely with per-request timeouts, but safe).
    const safetyNav = window.setTimeout(navigateOnce, 120_000);

    const abortController = new AbortController();
    pollAbortRef.current = abortController;

    try {
      const ok = await waitForFinalReport(sid, setArbiterLiveText, 110_000, abortController.signal);
      if (!ok) {
        playSound("error");
        setValidationError(
          "The report is taking longer than expected. Opening the results view — it will keep checking."
        );
      }
    } catch (err) {
      dbg.error("Council synthesis wait failed", err);
      playSound("error");
      setValidationError(err instanceof Error ? err.message : "Council synthesis failed.");
    } finally {
      window.clearTimeout(safetyNav);
      pollAbortRef.current = null;
      navigateOnce();
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
    try {
      await resumeInvestigation(true);
    } catch (err) {
      dbg.error("Deep analysis resume failed", err);
      playSound("error");
      setValidationError(
        err instanceof Error ? err.message : "Could not start deep analysis on the server."
      );
    }
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

  // View Results → after deep analysis confirm report is addressable, then navigate
  const handleViewResults = useCallback(async () => {
    if (isNavigating) return;
    playSound("arbiter_start");
    sessionStorage.setItem("forensic_deep_agents", JSON.stringify(completedAgents));
    setIsNavigating(true);
    setShowArbiterOverlay(true);
    setArbiterLiveText("Preparing council ledger…");
    const sid = sessionStorage.getItem("forensic_session_id");
    try {
      if (sid) {
        await waitForFinalReport(sid, setArbiterLiveText, 120_000);
      }
    } catch (err) {
      dbg.error("View results prefetch failed", err);
      setValidationError(err instanceof Error ? err.message : "Could not confirm report status.");
    } finally {
      setShowArbiterOverlay(false);
      setIsNavigating(false);
      router.push("/result");
    }
  }, [playSound, router, isNavigating, completedAgents]);

  // Determine what to show
  const validAgentsData = AGENTS_DATA.filter(a => a.name !== "Council Arbiter");
  const validCompletedAgents = completedAgents.filter((c: AgentUpdate) =>
    validAgentsData.some(v => v.id === c.agent_id)
  );

  /** Each specialist agent has received WS activity (running updates or terminal completion). */
  const allForensicAgentsLive =
    validAgentsData.length > 0 &&
    validAgentsData.every(
      (a) =>
        Boolean(agentUpdates[a.id]) ||
        validCompletedAgents.some((c: AgentUpdate) => c.agent_id === a.id)
    );

  // In deep phase, unsupported agents never run — only count supported ones.
  // Only mark as unsupported if backend explicitly skipped or error says not applicable.
  const unsupportedAgentIds = new Set(
    validCompletedAgents
      .filter(c =>
        c.status === "skipped" ||
        (c.error && /not applicable|not supported|format not supported|skipping/i.test(c.error))
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

  // Play analysis_done sound once when  analysis finishes (PIPELINE_PAUSED)
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
    !autoStartBlocking &&
    (status === "idle" ||
      (status === "error" && !hasStartedAnalysis)) &&
    !isUploading &&
    !isRestoringRef.current;

  // Dismiss landing-page loading overlay only when the stream is up and busy agents are live — or safety timeouts / errors.
  useEffect(() => {
    if (!showLoadingOverlay) return;

    const fallbackMs = 45000;
    const fallback = setTimeout(() => {
      setShowLoadingOverlay(false);
      sessionStorage.removeItem("fc_show_loading");
    }, fallbackMs);

    let successTimer: ReturnType<typeof setTimeout> | undefined;

    if (analysisStreamReady && allForensicAgentsLive) {
      successTimer = setTimeout(() => {
        setShowLoadingOverlay(false);
        sessionStorage.removeItem("fc_show_loading");
      }, 400);
    }

    return () => {
      clearTimeout(fallback);
      if (successTimer) clearTimeout(successTimer);
    };
  }, [showLoadingOverlay, analysisStreamReady, allForensicAgentsLive]);

  /** If upload/investigate failed while landing overlay is up, never trap the UI under a spinner. */
  useEffect(() => {
    if (showLoadingOverlay && validationError) {
      setShowLoadingOverlay(false);
      sessionStorage.removeItem("fc_show_loading");
    }
  }, [showLoadingOverlay, validationError]);

  /** Stream is up but agent heartbeats are slow (e.g. stale duplicate session) — still reveal the workspace. */
  useEffect(() => {
    if (!showLoadingOverlay || !analysisStreamReady) return;
    const t = setTimeout(() => {
      setShowLoadingOverlay(false);
      sessionStorage.removeItem("fc_show_loading");
    }, 25000);
    return () => clearTimeout(t);
  }, [showLoadingOverlay, analysisStreamReady]);

  // Show agent progress for both phases
  const showAgentProgress = hasStartedAnalysis && !showUploadForm;

  // After deep analysis, show results buttons when all agents done + pipeline complete
  const deepAnalysisDone = phase === "deep" && (status === "complete" || allAgentsDone);

  // Progress text — specific and contextual
  const runningAgentNames = Object.keys(agentUpdates)
    .map(id => validAgentsData.find(a => a.id === id)?.name)
    .filter((n): n is string => !!n);

  let progressText = uploadPhaseText || "Establishing secure forensic pipeline…";
  if (awaitingDecision) {
    progressText = "Initial analysis complete. Choose how to proceed.";
  } else if (phase === "deep" && (status === "complete" || deepAnalysisDone)) {
    progressText = "Deep analysis complete. All findings collected.";
  } else if (phase === "deep") {
    if (runningAgentNames.length === 1) {
      progressText = `${runningAgentNames[0]} running deep analysis…`;
    } else if (runningAgentNames.length > 1) {
      progressText = `${runningAgentNames.length} agents running deep analysis…`;
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
    progressText = uploadPhaseText || (isUploading ? "Uploading evidence…" : "Deploying forensic agents…");
  } else if (isUploading) {
    progressText = uploadPhaseText || "Uploading evidence…";
  }

  return (
    <div className="min-h-screen text-foreground p-6 pb-20 overflow-x-hidden relative font-sans">

      {/* Loading overlay from landing page transition */}
      {showLoadingOverlay && (
        <LoadingOverlay
          liveText={
            uploadPhaseText ||
            pipelineMessage ||
            pipelineThinking ||
            progressText ||
            ""
          }
        />
      )}

      {/* Arbiter / ledger — live text from HTTP poll + WS until navigation */}
      {showArbiterOverlay && (
        <ForensicProgressOverlay
          variant="council"
          title="Council deliberation"
          liveText={
            arbiterLiveText ||
            pipelineMessage ||
            pipelineThinking ||
            ""
          }
          telemetryLabel="Arbiter telemetry"
          showElapsed
        />
      )}

      {/* Main content */}
      <main className="max-w-6xl mx-auto relative z-10">
        <PageTransition>
        <>
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

          {/* Agent Progress — handles both  and deep phases */}
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

          {/* Never render a completely empty main — avoids “page not loading” when gates desync */}
          {!showUploadForm &&
            !showAgentProgress &&
            !isRestoringRef.current &&
            !(validationError || errorMessage) && (
              <div className="flex flex-col items-center justify-center min-h-[50vh] gap-4 text-center px-6">
                <p className="text-sm text-foreground/55 max-w-md">
                  Initialising the evidence workspace. If this lingers, you can clear the landing
                  loader and try again.
                </p>
                <button
                  type="button"
                  onClick={() => {
                    setAutoStartBlocking(false);
                    setShowLoadingOverlay(false);
                    sessionStorage.removeItem("fc_show_loading");
                    sessionStorage.removeItem("forensic_auto_start");
                  }}
                  className="text-[11px] font-mono font-bold uppercase tracking-widest text-cyan-400/90 hover:text-cyan-300 border border-cyan-500/30 rounded-full px-5 py-2.5 transition-colors"
                >
                  Reset loading &amp; continue
                </button>
              </div>
            )}
        </>
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

      {/* Hidden file input */}
      <input
        ref={fileInputRef}
        type="file"
        onChange={(e: React.ChangeEvent<HTMLInputElement>) => {
          const f = e.target.files?.[0];
          if (f) handleFile(f);
        }}
        className="hidden"
        accept="image/*,video/*,audio/*"
        aria-label="Upload evidence file"
      />
    </div>
  );
}
