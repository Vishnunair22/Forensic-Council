"use client";

import { useState, useCallback, useRef, useEffect, useLayoutEffect, useMemo } from "react";
import { useRouter } from "next/navigation";
import { useSimulation } from "./useSimulation";
import {
  startInvestigation,
  submitHITLDecision,
  DuplicateInvestigationError,
  getArbiterStatus,
  getReport,
  getAuthToken,
  type HITLCheckpoint,
  type ArbiterStatusResponse,
  type HITLDecision
} from "@/lib/api";
import { toast } from "./use-toast";
import { AGENTS as AGENTS_DATA, ALLOWED_MIME_TYPES, INVESTIGATION_REQUEST_TIMEOUT_MS, ARBITER_POLL_INTERVAL_MS, MAX_UPLOAD_SIZE_BYTES } from "@/lib/constants";
import { __pendingFileStore } from "@/lib/pendingFileStore";
import { arbiterControl } from "@/lib/arbiterControl";
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
  let consecutiveNotFound = 0;
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
        consecutiveNotFound = 0;
        try {
          const res = await withTimeout(getReport(sessionId), 30_000);
          if (res.status === "complete" && res.report) return true;
        } catch {
          /* in progress */
        }
      }
      if (st.status === "not_found") {
        consecutiveNotFound++;
        if (consecutiveNotFound >= 5) {
          throw new Error("Investigation session not found. The session may have expired.");
        }
      } else {
        consecutiveNotFound = 0;
      }
    } catch (e: unknown) {
      if (e instanceof Error && e.message.includes("Council synthesis"))
        throw e;
      if (e instanceof Error && e.message.includes("not found") || e instanceof Error && e.message.includes("session may have expired"))
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
  const [isHydrated] = useState(() => {
    if (typeof window === "undefined") return false;
    return true;
  });
  const [autoStartBlocking, setAutoStartBlocking] = useState(() => {
    if (typeof window === "undefined") return false;
    return sessionOnlyStorage.getItem("forensic_auto_start") === "true";
  });
  const [showLoadingOverlay, setShowLoadingOverlay] = useState(() => {
    if (typeof window === "undefined") return false;
    // Issue 3 Fix A: Guard fc_show_loading cleanup with a hard clear on reconnect
    const hasSession = !!storage.getItem("forensic_session_id");
    const showLoading = sessionOnlyStorage.getItem("fc_show_loading") === "true";
    if (showLoading && hasSession) {
      sessionOnlyStorage.removeItem("fc_show_loading");
      return false;
    }
    return showLoading;
  });
  const [analysisStreamReady, setAnalysisStreamReady] = useState(false);
  const [arbiterLiveText, setArbiterLiveText] = useState("");
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
  const prevAwaitingDecisionRef = useRef(false);
  const arbiterAbortControllerRef = useRef<AbortController | null>(null);
  const minOverlayTimerRef = useRef<NodeJS.Timeout | null>(null);
  const overlayStartTimeRef = useRef<number>(0);

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
    restoreSimulationState,
    isReconnecting,
    reconnectStatusMessage,
    arbiterStatus,
    arbiterThinking,
  } = useSimulation({
    playSound,
    onComplete: () => {},
  });

  useEffect(() => {
    completedAgentsRef.current = completedAgents;
    const sid = storage.getItem("forensic_session_id");
    if (completedAgents.length > 0 && status !== "idle" && sid) {
      storage.setItem(
        phase === "deep" ? `forensic_deep_agents:${sid}` : `forensic_initial_agents:${sid}`,
        completedAgents,
        true,
      );
    }
  }, [completedAgents, phase, status]);

  const sessionExistsRef = useRef(typeof window !== "undefined" && !!storage.getItem("forensic_session_id"));

  const showUploadForm =
    isHydrated &&
    !autoStartBlocking &&
    status === "idle" &&
    !isUploading &&
    !sessionExistsRef.current;

  useLayoutEffect(() => {
    // This effect now serves as a hydration completion signal for sub-components.
  }, []);

  const [authError, setAuthError] = useState<string | null>(null);

  const authReadyRef = useRef<Promise<void> | null>(null);

  useEffect(() => {
    if (typeof window === "undefined" || authReadyRef.current) return;

    const initAuth = async () => {
      if (document.cookie.includes("access_token") || getAuthToken() !== null) {
        return;
      } else if (__pendingFileStore.authPromise) {
        await __pendingFileStore.authPromise
          .then(() => {
            storage.setItem("forensic_auth_ok", "1");
            __pendingFileStore.authPromise = null;
          })
          .catch((err: unknown) => {
            __pendingFileStore.authPromise = null;
            const msg = err instanceof Error ? err.message : "Authentication failed";
            setAuthError(msg);
            toast.destructive({
              title: "Authentication Error",
              description: `Could not establish session: ${msg}. Please refresh the page.`,
            });
          });
      }
      // Issue 1 Fix A: Never initiate a fresh autoLogin call here; trust the HeroAuthActions pre-warm
    };
    authReadyRef.current = initAuth();
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
    sessionOnlyStorage.removeItem("fc_show_loading");
    storage.removeItem("forensic_session_id");
    storage.removeItem("forensic_investigation_ctx");
    try { storage.removeItem("forensic_thumbnail"); } catch { /* ignore */ }
    sessionExistsRef.current = false; // Update ref snapshot
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
      setArbiterLiveText("");

      const investigatorId = investigatorIdRef.current;
      const uuid = (typeof crypto !== "undefined" && "randomUUID" in crypto)
        ? crypto.randomUUID()
        : Math.random().toString(36).slice(2) + Date.now().toString(36);
      const caseId = "CASE-" + uuid;
      storage.removeItem("forensic_session_id");
      storage.removeItem("forensic_investigation_ctx");
      storage.removeItem("forensic_hitl_checkpoint");
      storage.removeItem("forensic_is_deep");
      // Clean up any stale agent snapshots
      Object.keys(localStorage).forEach(key => {
        if (key.startsWith("forensic_initial_agents:") || key.startsWith("forensic_deep_agents:")) {
          localStorage.removeItem(key);
        }
      });

      setShowLoadingOverlay(true);
      sessionOnlyStorage.setItem("fc_show_loading", "true");

      try {
        await authReadyRef.current;
      } catch (authErr) {
        setIsUploading(false);
        setShowLoadingOverlay(false);
        resetSimulation();
        investigationInFlightRef.current = false;
        toast.destructive({ title: "Authentication failed", description: authErr instanceof Error ? authErr.message : "Could not establish session." });
        return;
      }

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
      // Issue 2 Fix D: Set cookie for server-side /result redirect
      if (typeof document !== "undefined") {
        document.cookie = `forensic_session_id=${sessionIdToUse}; path=/; max-age=3600; SameSite=Lax`;
      }
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
          // Issue 3 Fix: Do NOT call setShowLoadingOverlay(false) here.
          // The overlay dismissal is now handled by the state-tracking effect
          // which ensures a minimum display duration of 2.5s for UX.
        })
        .catch((wsErr: unknown) => {
          const wsErrMsg = wsErr instanceof Error ? wsErr.message : "Failed to connect to stream";
          setWsConnectionError(wsErrMsg);
          setShowLoadingOverlay(false);
          resetSimulation();
        })
        .finally(() => {
          investigationInFlightRef.current = false;
          __pendingFileStore.file = null;
          sessionExistsRef.current = true; // Update ref snapshot
        });
    },
    [playSound, startSimulation, connectWebSocket, resetSimulation]
  );


  // Issue 2 Fix A: Effect A — Auto-start from pending file
  useEffect(() => {
    if (!isHydrated || autoStartFiredRef.current) return;
    const pending = __pendingFileStore.file;
    if (!pending) {
      sessionOnlyStorage.removeItem("forensic_auto_start");
      setAutoStartBlocking(false);
      return;
    }

    autoStartFiredRef.current = true;
    setFile(pending);
    sessionOnlyStorage.removeItem("forensic_auto_start");
    sessionOnlyStorage.setItem("fc_show_loading", "true");
    setShowLoadingOverlay(true);
    // Keep autoStartBlocking=true until triggerAnalysis sets isUploading=true.
    // This prevents showUploadForm from flickering true during the transition.
    // triggerAnalysis will call setAutoStartBlocking(false) after isUploading is set.
    triggerAnalysis(pending);
  }, [isHydrated, triggerAnalysis]);

  // Effect B — Reconnect existing session
  useEffect(() => {
    if (!isHydrated || autoStartFiredRef.current) return;
    if (__pendingFileStore.file || autoStartBlocking || isUploading) return;
    if (status !== "idle" && status !== "error") return;

    // fc_show_loading guard on reconnect
    if (sessionOnlyStorage.getItem("fc_show_loading") === "true") {
      sessionOnlyStorage.removeItem("fc_show_loading");
      setShowLoadingOverlay(false);
    }

    const existingSessionId = storage.getItem("forensic_session_id");
    const noReconnect = sessionOnlyStorage.getItem("fc_no_reconnect");

    if (!existingSessionId || noReconnect) {
      if (noReconnect) sessionOnlyStorage.removeItem("fc_no_reconnect");
      return;
    }

    autoStartFiredRef.current = true;
    const savedDeepAgents = storage.getItem<AgentUpdate[]>(`forensic_deep_agents:${existingSessionId}`, true, []);
    const savedInitialAgents = storage.getItem<AgentUpdate[]>(`forensic_initial_agents:${existingSessionId}`, true, []);
    const savedAgents = (savedDeepAgents?.length ? savedDeepAgents : savedInitialAgents) ?? [];
    const restoredPhase = savedDeepAgents?.length ? "deep" : "initial";

    setPhase(restoredPhase);
    startSimulation();
    if (savedAgents.length > 0) {
      restoreSimulationState(savedAgents, "awaiting_decision");
    }
    setAnalysisStreamReady(false);
    setUploadPhaseText("Reconnecting to analysis stream...");
    setShowLoadingOverlay(false);
    sessionOnlyStorage.removeItem("fc_show_loading");

    (async () => {
      try {
        const st = await withTimeout(getArbiterStatus(existingSessionId), 8_000);
        if (st.status === "not_found") {
          storage.removeItem("forensic_session_id");
          storage.removeItem("forensic_investigation_ctx");
          resetSimulation();
          return;
        }
        if (st.status === "complete") {
          router.push("/result", { scroll: true });
          return;
        }
      } catch { /* ignore poll errors during reconnect */ }

      connectWebSocket(existingSessionId, true)
        .then(() => setAnalysisStreamReady(true))
        .catch((wsErr: unknown) => {
          const wsErrMsg = wsErr instanceof Error ? wsErr.message : "Failed to connect to stream";
          setWsConnectionError(wsErrMsg);
          setShowLoadingOverlay(false);
        });
    })();
  }, [isHydrated, autoStartBlocking, isUploading, status, startSimulation, connectWebSocket, resetSimulation, restoreSimulationState, router]);

  const handleFile = (f: File) => {
    if (f.size > MAX_UPLOAD_SIZE_BYTES) {
      setValidationError("File must be 50MB or smaller.");
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
    playSound("success-chime");
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
    playSound("click");
    playSound("arbiter_start");
    storage.setItem("forensic_is_deep", "false");
    const sid = storage.getItem("forensic_session_id");
    if (sid) storage.setItem(`forensic_initial_agents:${sid}`, completedAgentsRef.current, true);
    setIsNavigating(true);
    setArbiterDeliberating(true);
    try {
      if (!sid) throw new Error("No active session");
      await resumeInvestigation(false);
      arbiterControl.abortController = new AbortController();
      const ok = await waitForFinalReport(sid, setArbiterLiveText, 300_000, arbiterControl.abortController.signal);
      if (!ok) throw new Error("Council synthesis timed out");
      router.push("/result", { scroll: true });
    } catch (err) {
      toast.destructive({
        title: "Council synthesis failed",
        description: err instanceof Error ? err.message : "Could not finalize verdict.",
      });
    } finally {
      setIsNavigating(false);
      setArbiterDeliberating(false);
    }
  }, [playSound, resumeInvestigation, router, isNavigating]);

  const handleDeepAnalysis = useCallback(async () => {
    if (investigationInFlightRef.current) return;
    investigationInFlightRef.current = true;
    playSound("click");
    playSound("think");
    storage.setItem("forensic_is_deep", "true");
    const sid = storage.getItem("forensic_session_id");
    if (sid) storage.setItem(`forensic_initial_agents:${sid}`, completedAgentsRef.current, true);
    analysisCompleteSoundedRef.current = false;
    prevAwaitingDecisionRef.current = false;
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
        setShowLoadingOverlay(false);
        sessionOnlyStorage.removeItem("fc_show_loading");
      })
      .catch((wsErr: unknown) => {
        const wsErrMsg = wsErr instanceof Error ? wsErr.message : "Failed to connect to stream";
        setWsConnectionError(wsErrMsg);
        resetSimulation();
      });
  }, [file, triggerAnalysis, startSimulation, connectWebSocket, resetSimulation]);

  const handleNewUpload = useCallback(() => {
    playSound("click");
    arbiterControl.abort();
    setArbiterDeliberating(false);
    setArbiterLiveText("");
    setFile(null);
    setPhase("initial");
    setWsConnectionError(null);
    lastSessionIdRef.current = null;
    autoStartFiredRef.current = false;
    storage.removeItem("forensic_session_id");
    storage.removeItem("forensic_investigation_ctx");
    storage.removeItem("forensic_case_id");
    storage.removeItem("forensic_file_name");
    storage.removeItem("forensic_mime_type");
    storage.removeItem("forensic_pipeline_start");
    analysisCompleteSoundedRef.current = false;
    Object.keys(localStorage).forEach(key => {
      if (key.startsWith("forensic_initial_agents:") || key.startsWith("forensic_deep_agents:")) {
        localStorage.removeItem(key);
      }
    });
    resetSimulation();
    sessionOnlyStorage.removeItem("forensic_auto_start");
    sessionOnlyStorage.setItem("fc_open_upload_once", "1");
    sessionOnlyStorage.setItem("fc_no_reconnect", "1");
    router.push("/?upload=1");
  }, [resetSimulation, playSound, router]);

  const handleViewResults = useCallback(async () => {
    if (isNavigating) return;
    playSound("click");
    playSound("complete");
    const sid = storage.getItem("forensic_session_id");
    if (sid) storage.setItem(`forensic_deep_agents:${sid}`, completedAgentsRef.current, true);
    setIsNavigating(true);
    setArbiterDeliberating(true);
    try {
      if (!sid) throw new Error("No active session");
      arbiterAbortControllerRef.current = new AbortController();
      const ok = await waitForFinalReport(sid, setArbiterLiveText, 600_000, arbiterAbortControllerRef.current.signal);
      if (!ok) throw new Error("Report synthesis timed out");
      router.push("/result", { scroll: true });
    } catch (err) {
      toast.destructive({
        title: "Could not load report",
        description: err instanceof Error ? err.message : "Try again.",
      });
    } finally {
      setIsNavigating(false);
      setArbiterDeliberating(false);
    }
  }, [playSound, router, isNavigating]);

  const validAgentsData = AGENTS_DATA.filter((a) => a.name !== "Council Arbiter");
  const validCompletedAgents = completedAgents.filter((c: AgentUpdate) =>
    validAgentsData.some((v) => v.id === c.agent_id)
  );

  const [mimeType, setMimeType] = useState<string | null>(() =>
    storage.getItem("forensic_mime_type") || null
  );

  useEffect(() => {
    setMimeType(storage.getItem("forensic_mime_type") || file?.type || null);
  }, [file]);

  const expectedAgentIds = useMemo(() => supportedAgentIdsForMime(mimeType), [mimeType]);

  const expectedCompletedCount = validCompletedAgents.filter((c: AgentUpdate) =>
    expectedAgentIds.has(c.agent_id)
  ).length;

  const awaitingDecision =
    !isNavigating &&
    !arbiterDeliberating &&
    (status === "awaiting_decision" ||
      (phase === "initial" &&
        mimeType !== null &&
        expectedAgentIds.size > 0 &&
        expectedCompletedCount >= expectedAgentIds.size &&
        !revealPending));
  const allAgentsDone = phase === "deep"
    ? (status === "complete" || expectedCompletedCount >= expectedAgentIds.size)
    : expectedCompletedCount >= expectedAgentIds.size;

  useEffect(() => {
    if (awaitingDecision && !prevAwaitingDecisionRef.current) {
      // playSound("think"); // Suppressed to avoid double sound with analysis_done
    }
    prevAwaitingDecisionRef.current = awaitingDecision;
  }, [awaitingDecision, playSound]);

  useEffect(() => {
    if (awaitingDecision && !analysisCompleteSoundedRef.current) {
      analysisCompleteSoundedRef.current = true;
      playSound("analysis_done");
    }
  }, [awaitingDecision, playSound]);

  const hasStartedAnalysis = isHydrated && (status !== "idle" || isUploading || validCompletedAgents.length > 0 || autoStartBlocking);

  // Safety dismissal for reconnects or very fast streams that update state
  // before the connection promise settles.
  useEffect(() => {
    // Wait until the backend has transitioned out of initiating to dismiss.
    // status !== "idle" && status !== "initiating" means we've started receiving real updates.
    const isActuallyRunning = status !== "idle" && status !== "initiating";
    
    if (showLoadingOverlay) {
      if (overlayStartTimeRef.current === 0) {
        overlayStartTimeRef.current = Date.now();
      }

      if (isActuallyRunning) {
        const elapsed = Date.now() - overlayStartTimeRef.current;
        const minDuration = 2500; // Keep overlay for at least 2.5s for perceived performance

        if (elapsed >= minDuration) {
          setShowLoadingOverlay(false);
          sessionOnlyStorage.removeItem("fc_show_loading");
        } else if (!minOverlayTimerRef.current) {
          minOverlayTimerRef.current = setTimeout(() => {
            setShowLoadingOverlay(false);
            sessionOnlyStorage.removeItem("fc_show_loading");
            minOverlayTimerRef.current = null;
          }, minDuration - elapsed);
        }
      }
    } else {
      // If overlay is hidden, ensure timer is cleared and start time reset
      if (minOverlayTimerRef.current) {
        clearTimeout(minOverlayTimerRef.current);
        minOverlayTimerRef.current = null;
      }
      overlayStartTimeRef.current = 0;
    }
  }, [showLoadingOverlay, status]);


  useEffect(() => {
    if (!showLoadingOverlay) return;
    const safety = setTimeout(() => {
      // Hard safety: if the overlay is still up after 8s, something is stuck.
      // We dismiss it to let the user see the current (possibly errored) state.
      setShowLoadingOverlay(false);
      sessionOnlyStorage.removeItem("fc_show_loading");
      
      if (!analysisStreamReady && (status === "idle" || status === "initiating")) {
        setWsConnectionError("Analysis startup timed out. Please try again.");
        toast.destructive({
          title: "Connection Timeout",
          description: "The analysis stream did not start in time. Please refresh and try again.",
        });
      }
    }, 8000);
    return () => clearTimeout(safety);
  }, [showLoadingOverlay, analysisStreamReady, status]);

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
    isReconnecting,
    reconnectStatusMessage,
    arbiterStatus,
    arbiterThinking,
  };
}
