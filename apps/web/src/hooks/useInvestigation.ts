"use client";

import { useState, useCallback, useRef, useEffect, useLayoutEffect, useMemo } from "react";
import { useRouter } from "next/navigation";
import { useSimulation } from "./useSimulation";
import {
  startInvestigation,
  submitHITLDecision,
  autoLoginAsInvestigator,
  DuplicateInvestigationError,
  getArbiterStatus,
  getReport,
  getAuthToken,
  type HITLCheckpoint,
  type ArbiterStatusResponse,
  type HITLDecision
} from "@/lib/api";
import { toast } from "./use-toast";
import { AGENTS as AGENTS_DATA, ALLOWED_MIME_TYPES, INVESTIGATION_REQUEST_TIMEOUT_MS, ARBITER_POLL_INTERVAL_MS } from "@/lib/constants";
import { __pendingFileStore } from "@/lib/pendingFileStore";
import { type SoundType } from "@/hooks/useSound";
import { type AgentUpdate } from "@/components/evidence/AgentProgressDisplay";
import { storage, sessionOnlyStorage } from "@/lib/storage";
import { supportedAgentIdsForMime } from "@/lib/agentSupport";

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
      },
    );
  });
}

async function waitForFinalReport(
  sessionId: string,
  onLiveMessage: (message: string) => void,
  maxMs: number,
  signal?: AbortSignal,
): Promise<boolean> {
  const deadline = Date.now() + maxMs;
  let pollInterval = ARBITER_POLL_INTERVAL_MS;
  while (Date.now() < deadline) {
    if (signal?.aborted) return false;
    try {
      const st = await withTimeout(
        getArbiterStatus(sessionId),
        INVESTIGATION_REQUEST_TIMEOUT_MS,
      ) as ArbiterStatusResponse;

      if (st.message) onLiveMessage(st.message);
      if (st.status === "error") {
        throw new Error(st.message || "Council synthesis failed.");
      }
      if (st.status === "complete") {
        try {
          const res = await withTimeout(getReport(sessionId), 30_000);
          if (res.status === "complete" && res.report) return true;
        } catch {
          /* in progress */
        }
      }
    } catch (e: unknown) {
      if (e instanceof Error && e.message.includes("Council synthesis"))
        throw e;
    }
    await new Promise<void>((r) => {
      const timer = setTimeout(r, pollInterval);
      signal?.addEventListener("abort", () => clearTimeout(timer), {
        once: true,
      });
    });
    if (signal?.aborted) return false;
    pollInterval = Math.min(pollInterval * 1.2, 3000);
  }
  return false;
}

export function useInvestigation(playSound: (type: SoundType) => void) {
  const router = useRouter();

  const _initInvestigatorId = () => {
    if (typeof window === "undefined") return "REQ-000000";
    const stored = storage.getItem("forensic_investigator_id");
    const validIdPattern = /^REQ-\d{5,10}$/;
    if (stored && validIdPattern.test(stored)) return stored;
    const fresh = "REQ-" + (Math.floor(Math.random() * 900000) + 100000);
    storage.setItem("forensic_investigator_id", fresh);
    return fresh;
  };

  const investigatorIdRef = useRef<string>(_initInvestigatorId());
  const [file, setFile] = useState<File | null>(null);
  const [isDragging, setIsDragging] = useState(false);
  const [validationError, setValidationError] = useState<string | null>(null);
  const [isUploading, setIsUploading] = useState(false);
  const [uploadPhaseText, setUploadPhaseText] = useState<string>("");
  const [showLoadingOverlay, setShowLoadingOverlay] = useState(false);
  const [analysisStreamReady, setAnalysisStreamReady] = useState(false);
  const [arbiterLiveText, setArbiterLiveText] = useState("");
  const [autoStartBlocking, setAutoStartBlocking] = useState(false);
  const [phase, setPhase] = useState<"initial" | "deep">("initial");
  const [isSubmittingHITL, setIsSubmittingHITL] = useState(false);
  const [isNavigating, setIsNavigating] = useState(false);
  const [wsConnectionError, setWsConnectionError] = useState<string | null>(null);
  const [arbiterDeliberating, setArbiterDeliberating] = useState(false);
  const analysisCompleteSoundedRef = useRef(false);
  const autoStartFiredRef = useRef(false);
  const investigationInFlightRef = useRef(false);
  const lastSessionIdRef = useRef<string | null>(null);
  const completedAgentsRef = useRef<AgentUpdate[]>([]);
  const arbiterAbortControllerRef = useRef<AbortController | null>(null);

  useEffect(() => {
    return () => {
      if (arbiterAbortControllerRef.current) {
        arbiterAbortControllerRef.current.abort();
      }
    };
  }, []);

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
    revealQueue,
    revealPending,
  } = useSimulation({
    playSound,
    onComplete: () => {},
  });

  useEffect(() => {
    completedAgentsRef.current = completedAgents;
  }, [completedAgents]);

  useLayoutEffect(() => {
    try {
      setAutoStartBlocking(sessionOnlyStorage.getItem("forensic_auto_start") === "true");
      if (sessionOnlyStorage.getItem("fc_show_loading") === "true") {
        setShowLoadingOverlay(true);
      }
    } catch {
      setAutoStartBlocking(false);
    }
  }, []);

  const [authError, setAuthError] = useState<string | null>(null);

  const authReadyRef = useRef<Promise<void> | null>(null);

  useEffect(() => {
    if (typeof window === "undefined" || authReadyRef.current) return;

    if (
      document.cookie.includes("access_token") ||
      (storage.getItem("forensic_auth_ok") === "1" && getAuthToken() !== null)
    ) {
      authReadyRef.current = Promise.resolve();
    } else {
      authReadyRef.current = autoLoginAsInvestigator()
        .then(() => {
          storage.setItem("forensic_auth_ok", "1");
        })
        .catch((err: unknown) => {
          const msg = err instanceof Error ? err.message : "Authentication failed";
          setAuthError(msg);
          toast.destructive({
            title: "Authentication Error",
            description: `Could not establish session: ${msg}. Please refresh the page.`,
          });
        });
    }
  }, []);

  const filePreviewUrl = useMemo(() => {
    if (!file) return null;
    if (file.type.startsWith("image/") || file.type.startsWith("video/")) {
      return URL.createObjectURL(file);
    }
    return null;
  }, [file]);

  useEffect(() => {
    return () => {
      if (filePreviewUrl) URL.revokeObjectURL(filePreviewUrl);
    };
  }, [filePreviewUrl]);

  const resetSimulation = useCallback(() => {
    setIsUploading(false);
    setPhase("initial");
    setAnalysisStreamReady(false);
    resetSimulationHook();
  }, [resetSimulationHook]);

  const triggerAnalysis = useCallback(
    async (targetFile: File) => {
      if (!targetFile) return;
      // Synchronous ref guard — prevents concurrent submissions from rapid clicks
      // or retry button spam before React re-renders with isUploading=true.
      if (investigationInFlightRef.current) return;
      investigationInFlightRef.current = true;

      playSound("upload");
      playSound("scan");
      setIsUploading(true);
      setValidationError(null);
      setWsConnectionError(null);
      setPhase("initial");
      setAnalysisStreamReady(false);
      setAutoStartBlocking(false);
      setUploadPhaseText("Uploading evidence to secure pipeline…");

      const investigatorId = investigatorIdRef.current;
      const caseId = storage.getItem("forensic_case_id") || "CASE-" + crypto.randomUUID();

      setShowLoadingOverlay(true);
      sessionOnlyStorage.setItem("fc_show_loading", "true");

      await authReadyRef.current;

      // Capture image thumbnail before upload so it's available on the result page
      if (targetFile.type.startsWith("image/")) {
        try {
          const thumbUrl = URL.createObjectURL(targetFile);
          const img = new window.Image();
          img.src = thumbUrl;
          await new Promise<void>((res) => {
            img.onload = () => res();
            img.onerror = () => res();
          });
          const maxDim = 240;
          const ratio = Math.min(maxDim / img.width, maxDim / img.height, 1);
          const canvas = document.createElement("canvas");
          canvas.width = Math.max(1, Math.round(img.width * ratio));
          canvas.height = Math.max(1, Math.round(img.height * ratio));
          const ctx = canvas.getContext("2d");
          if (ctx) {
            ctx.drawImage(img, 0, 0, canvas.width, canvas.height);
            storage.setItem("forensic_thumbnail", canvas.toDataURL("image/jpeg", 0.72));
          }
          URL.revokeObjectURL(thumbUrl);
        } catch {
          // thumbnail is cosmetic — never block upload on failure
        }
      } else {
        storage.removeItem("forensic_thumbnail");
      }

      let sessionIdToUse: string | undefined;
      try {
        const investigationRes = await startInvestigation(targetFile, caseId, investigatorId);
        sessionIdToUse = investigationRes.session_id;
      } catch (err) {
        if (err instanceof DuplicateInvestigationError) {
          const sid = err.existingSessionId;
          storage.setItem("forensic_session_id", sid);
          sessionIdToUse = sid;
          toast.default({
            title: "Resuming Existing Session",
            description: "This file was already submitted. Connecting to the active investigation.",
          });
        } else {
          const errorMsg = err instanceof Error ? err.message : "Failed to start investigation";
          setValidationError(errorMsg);
          setIsUploading(false);
          setShowLoadingOverlay(false);
          resetSimulation();
          playSound("error");
          toast.destructive({ title: "Investigation Failed", description: errorMsg });
          investigationInFlightRef.current = false;
          return;
        }
      } finally {
        if (!sessionIdToUse) {
          investigationInFlightRef.current = false;
        }
      }

      startSimulation();

      // Write all investigation context atomically under one key so
      // the result page always sees a consistent snapshot, then write
      // individual keys for backward-compatible reads elsewhere.
      const pipelineStart = new Date().toISOString();
      const investigationCtx = {
        session_id: sessionIdToUse,
        file_name: targetFile.name,
        case_id: caseId,
        investigator_id: investigatorId,
        mime_type: targetFile.type,
        pipeline_start: pipelineStart,
      };
      storage.setItem("forensic_investigation_ctx", investigationCtx, true);
      // Individual keys kept for hooks that read them directly
      storage.setItem("forensic_session_id", sessionIdToUse);
      storage.setItem("forensic_file_name", targetFile.name);
      storage.setItem("forensic_case_id", caseId);
      storage.setItem("forensic_investigator_id", investigatorId);
      storage.setItem("forensic_mime_type", targetFile.type);

      storage.setItem("forensic_pipeline_start", pipelineStart);
      setIsUploading(false);
      setUploadPhaseText("Connecting to analysis stream…");

      lastSessionIdRef.current = sessionIdToUse;

      connectWebSocket(sessionIdToUse)
        .then(() => {
          setAnalysisStreamReady(true);
          setUploadPhaseText("Agents dispatching…");
        })
        .catch((wsErr: unknown) => {
          const wsErrMsg = wsErr instanceof Error ? wsErr.message : "Failed to connect to stream";
          setWsConnectionError(wsErrMsg);
          setShowLoadingOverlay(false);
          resetSimulation();
        })
        .finally(() => {
          investigationInFlightRef.current = false;
        });
    },
    [playSound, startSimulation, connectWebSocket, resetSimulation]
  );

  useEffect(() => {
    const pending = __pendingFileStore.file;
    if (pending && !autoStartFiredRef.current) {
      autoStartFiredRef.current = true;
      __pendingFileStore.file = null;
      setFile(pending);
      sessionOnlyStorage.removeItem("forensic_auto_start");
      sessionOnlyStorage.setItem("fc_show_loading", "true");
      setShowLoadingOverlay(true);
      setAutoStartBlocking(false);
      triggerAnalysis(pending);
    } else if (!pending && autoStartBlocking && !isUploading && status === "idle") {
      // Safety guard: auto-start was requested but file is lost (e.g. refresh)
      setAutoStartBlocking(false);
      setShowLoadingOverlay(false);
      sessionOnlyStorage.removeItem("forensic_auto_start");
      sessionOnlyStorage.removeItem("fc_show_loading");
    } else if (!pending && !autoStartFiredRef.current && status === "idle" && !isUploading && !autoStartBlocking) {
      // Auto-reconnect to an active session when navigating directly to the evidence page
      const existingSessionId = storage.getItem("forensic_session_id");
      if (existingSessionId) {
        autoStartFiredRef.current = true;
        startSimulation();
        connectWebSocket(existingSessionId)
          .then(() => {
            setAnalysisStreamReady(true);
          })
          .catch((wsErr: unknown) => {
            const wsErrMsg = wsErr instanceof Error ? wsErr.message : "Failed to connect to stream";
            setWsConnectionError(wsErrMsg);
            setShowLoadingOverlay(false);
            resetSimulation();
          });
      }
    }
  }, [triggerAnalysis, autoStartBlocking, isUploading, status, startSimulation, connectWebSocket, resetSimulation]);

  const handleFile = (f: File) => {
    if (f.size > 55 * 1024 * 1024) {
      setValidationError("File must be under 55MB");
      playSound("error");
      return;
    }
    if (!ALLOWED_MIME_TYPES.has(f.type)) {
      setValidationError(`File type "${f.type}" is not supported.`);
      playSound("error");
      return;
    }
    setFile(f);
    setValidationError(null);
    playSound("success");
  };

  const handleHITLDecision = async (decision: HITLDecision, note?: string) => {
    if (!hitlCheckpoint || isSubmittingHITL) return;
    setIsSubmittingHITL(true);
    try {
      await submitHITLDecision({
        session_id: hitlCheckpoint.session_id,
        checkpoint_id: hitlCheckpoint.checkpoint_id,
        agent_id: hitlCheckpoint.agent_id,
        decision,
        note: note || `Investigator decision: ${decision}`,
      });
      dismissCheckpoint();
      playSound("success");
    } catch {
      toast.destructive({ title: "Decision Failed", description: "Could not submit decision." });
    } finally {
      setIsSubmittingHITL(false);
    }
  };

  const handleAcceptAnalysis = useCallback(async () => {
    if (isNavigating) return;
    playSound("arbiter_start");
    storage.setItem("forensic_is_deep", "false");
    storage.setItem("forensic_initial_agents", completedAgentsRef.current, true);
    setIsNavigating(true);
    setArbiterDeliberating(true);
    try {
      await resumeInvestigation(false);
      const sid = storage.getItem("forensic_session_id");
      if (sid) {
        arbiterAbortControllerRef.current = new AbortController();
        await waitForFinalReport(sid, setArbiterLiveText, 300_000, arbiterAbortControllerRef.current.signal);
      }
      router.push("/result", { scroll: true });
    } catch {
      setIsNavigating(false);
    } finally {
      setArbiterDeliberating(false);
    }
  }, [playSound, resumeInvestigation, router, isNavigating]);

  const handleDeepAnalysis = useCallback(async () => {
    if (investigationInFlightRef.current) return;
    investigationInFlightRef.current = true;
    playSound("think");
    storage.setItem("forensic_is_deep", "true");
    storage.setItem("forensic_initial_agents", completedAgentsRef.current, true);
    analysisCompleteSoundedRef.current = false;
    clearCompletedAgents();
    setPhase("deep");
    try {
      await resumeInvestigation(true);
    } catch {
      playSound("error");
    } finally {
      investigationInFlightRef.current = false;
    }
  }, [playSound, resumeInvestigation, clearCompletedAgents]);

  const retryWsConnection = useCallback(() => {
    const sid = lastSessionIdRef.current || storage.getItem("forensic_session_id");
    if (!sid) {
      // No session to reconnect to — fall back to a fresh upload
      if (file) triggerAnalysis(file);
      return;
    }
    setWsConnectionError(null);
    startSimulation();
    connectWebSocket(sid)
      .then(() => {
        setAnalysisStreamReady(true);
        setUploadPhaseText("Agents dispatching…");
      })
      .catch((wsErr: unknown) => {
        const wsErrMsg = wsErr instanceof Error ? wsErr.message : "Failed to connect to stream";
        setWsConnectionError(wsErrMsg);
        resetSimulation();
      });
  }, [file, triggerAnalysis, startSimulation, connectWebSocket, resetSimulation]);

  const handleNewUpload = useCallback(() => {
    playSound("click");
    setFile(null);
    setPhase("initial");
    setWsConnectionError(null);
    lastSessionIdRef.current = null;
    resetSimulation();
    router.push("/?upload=1");
  }, [resetSimulation, playSound, router]);

  const handleViewResults = useCallback(async () => {
    if (isNavigating) return;
    playSound("complete");
    storage.setItem("forensic_deep_agents", completedAgentsRef.current, true);
    setIsNavigating(true);
    setArbiterDeliberating(true);
    const sid = storage.getItem("forensic_session_id");
    try {
      if (sid) {
        arbiterAbortControllerRef.current = new AbortController();
        await waitForFinalReport(sid, setArbiterLiveText, 300_000, arbiterAbortControllerRef.current.signal);
      }
      router.push("/result", { scroll: true });
    } finally {
      setIsNavigating(false);
      setArbiterDeliberating(false);
    }
  }, [playSound, router, isNavigating]);

  const validAgentsData = AGENTS_DATA.filter((a) => a.name !== "Council Arbiter");
  const validCompletedAgents = completedAgents.filter((c: AgentUpdate) =>
    validAgentsData.some((v) => v.id === c.agent_id)
  );

  const [mimeType, setMimeType] = useState<string | null>(null);

  useEffect(() => {
    // Safely sync from storage on mount/file change to avoid hydration mismatch
    setMimeType(storage.getItem("forensic_mime_type") || file?.type || null);
  }, [file]);

  const expectedAgentIds = useMemo(() => supportedAgentIdsForMime(mimeType), [mimeType]);

  const expectedCompletedCount = validCompletedAgents.filter((c: AgentUpdate) =>
    expectedAgentIds.has(c.agent_id)
  ).length;

  const awaitingDecision = status === "awaiting_decision";
  const allAgentsDone = phase === "deep"
    ? (status === "complete" || expectedCompletedCount >= expectedAgentIds.size)
    : expectedCompletedCount >= expectedAgentIds.size;

  useEffect(() => {
    if (awaitingDecision && !analysisCompleteSoundedRef.current) {
      analysisCompleteSoundedRef.current = true;
      playSound("analysis_done");
    }
  }, [awaitingDecision, playSound]);

  const hasStartedAnalysis = status !== "idle" || isUploading || validCompletedAgents.length > 0;
  const showUploadForm = !autoStartBlocking && status === "idle" && !isUploading;

  // Dismiss overlay only once the first agent update arrives, proving the
  // backend has actually started processing (not just that the WS opened).
  useEffect(() => {
    if (
      showLoadingOverlay &&
      analysisStreamReady &&
      (Object.keys(agentUpdates).length > 0 || validCompletedAgents.length > 0)
    ) {
      setShowLoadingOverlay(false);
      sessionOnlyStorage.removeItem("fc_show_loading");
    }
  }, [showLoadingOverlay, analysisStreamReady, agentUpdates, validCompletedAgents]);

  return {
    file, setFile,
    isDragging, setIsDragging,
    validationError, setValidationError,
    authError,
    isUploading,
    uploadPhaseText,
    showLoadingOverlay, setShowLoadingOverlay,
    analysisStreamReady,
    arbiterLiveText,
    autoStartBlocking, setAutoStartBlocking,
    phase,
    isSubmittingHITL,
    isNavigating,
    status,
    agentUpdates,
    validCompletedAgents,
    pipelineMessage,
    pipelineThinking,
    hitlCheckpoint: hitlCheckpoint as HITLCheckpoint | null,
    errorMessage,
    dismissCheckpoint,
    handleFile,
    triggerAnalysis,
    retryWsConnection,
    handleHITLDecision,
    handleAcceptAnalysis,
    handleDeepAnalysis,
    handleNewUpload,
    handleViewResults,
    resetSimulation,
    allAgentsDone,
    awaitingDecision,
    hasStartedAnalysis,
    showUploadForm,
    validAgentsData,
    wsConnectionError,
    revealQueue,
    revealPending,
    arbiterDeliberating,
  };
}
