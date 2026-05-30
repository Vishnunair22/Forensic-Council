"use client";
/**
 * BOUNDARY: Owns file selection, upload, authentication, session creation,
 * loading overlay lifecycle, and navigation after analysis completes.
 * Delegates streaming agent state to: useSimulation (via sessionId handoff).
 */

import { useState, useCallback, useRef, useEffect, useMemo } from "react";
import { useRouter } from "next/navigation";
import { useSimulation } from "./useSimulation";
import {
  startInvestigation,
  submitHITLDecision,
  getArbiterStatus,
  getReport,
  getAuthToken,
  autoLoginAsInvestigator,
  DuplicateInvestigationError,
  WorkerWarmupError,
  type ArbiterStatusResponse,
  type HITLDecision
} from "@/lib/api";
import { toast } from "./use-toast";
import {
  AGENTS as AGENTS_DATA,
  INVESTIGATION_REQUEST_TIMEOUT_MS,
  ARBITER_POLL_INTERVAL_MS,
  UI_STRINGS,
} from "@/lib/constants";
import { __pendingFileStore } from "@/lib/pendingFileStore";
import { arbiterControl } from "@/lib/arbiterControl";
import { type SoundType } from "@/hooks/useSound";
import { type AgentUpdate } from "@/components/evidence/types";
import { storage, sessionOnlyStorage } from "@/lib/storage";
import { supportedAgentIdsForMime } from "@/lib/agentSupport";
import { clearInvestigationPersistence } from "@/lib/investigationStorage";
import { validateEvidenceFile } from "@/lib/fileValidation";
import { clearPendingEvidenceFile, loadPendingEvidenceFile } from "@/lib/pendingFilePersistence";
import { STORAGE_KEYS } from "@/lib/storageKeys";

function withTimeout<T>(p: Promise<T>, ms: number, cleanup?: () => void): Promise<T> {
  return new Promise((resolve, reject) => {
    const t = setTimeout(() => {
      cleanup?.();
      reject(new Error("request timed out"));
    }, ms);
    p.then(
      (v) => {
        clearTimeout(t);
        resolve(v);
      },
      (e) => {
        clearTimeout(t);
        cleanup?.();
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
  const cleanArbiterMessage = (message: string | undefined): string => {
    const text = String(message || "").trim();
    if (!text) return "";
    if (/awaiting analyst decision|initial analysis complete/i.test(text)) {
      return "Final report synthesis requested. Waiting for the Council Arbiter to start.";
    }
    return text
      .replace(/Speculative synthesis complete\.?\s*/gi, "Council evidence weights are ready. ")
      .replace(/\.\.\./g, ".")
      .replace(/â€¦/g, ".")
      .trim();
  };
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

      const liveMessage = cleanArbiterMessage(st.message);
      if (liveMessage) onLiveMessage(liveMessage);
      if (st.status === "error") {
        throw new Error(st.message || "Council synthesis failed.");
      }
      if (st.status === "complete") {
        consecutiveNotFound = 0;
        for (let attempt = 0; attempt < 5; attempt++) {
          if (signal?.aborted) return false;
          try {
            const res = await withTimeout(getReport(sessionId), 30_000);
            // ReportDTO has report_id; a 202 in-progress response has status:"in_progress"
            const asAny = res as unknown as Record<string, unknown>;
            if (asAny.report_id || (asAny.status === "complete" && asAny.report)) return true;
          } catch {
            /* report may not be ready yet — keep polling */
          }
          if (attempt < 4) {
            await new Promise<void>((r) => {
              const t = setTimeout(r, 800);
              signal?.addEventListener("abort", () => clearTimeout(t), { once: true });
            });
          }
        }
      }
      if (st.status === "not_found" || st.status === "unreachable") {
        if (st.status === "not_found") consecutiveNotFound++;
        if (consecutiveNotFound >= 5) {
          throw new Error("Investigation session not found. The session may have expired.");
        }
      } else {
        consecutiveNotFound = 0;
      }
    } catch (e: unknown) {
      if (e instanceof Error && e.message.includes("Council synthesis"))
        throw e;
      if (e instanceof Error && (e.message.includes("not found") || e.message.includes("session may have expired")))
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
    const stored = storage.getItem(STORAGE_KEYS.INVESTIGATOR_ID);
    const validIdPattern = /^REQ-\d{5,10}$/;
    if (stored && validIdPattern.test(stored)) return stored;
    const fresh = "REQ-" + (Math.floor(Math.random() * 900000) + 100000);
    storage.setItem(STORAGE_KEYS.INVESTIGATOR_ID, fresh);
    return fresh;
  };

  const investigatorIdRef = useRef<string>(_initInvestigatorId());
  const warmupTimeoutRef = useRef<NodeJS.Timeout | null>(null);
  const [file, setFile] = useState<File | null>(null);
  const [validationError, setValidationError] = useState<string | null>(null);
  const [isUploading, setIsUploading] = useState(false);
  const [uploadPhaseText, setUploadPhaseText] = useState<string>("");
  const [autoStartBlocking, setAutoStartBlocking] = useState(() => {
    if (typeof window === "undefined") return false;
    return sessionOnlyStorage.getItem(STORAGE_KEYS.AUTO_START) === "true";
  });
  const [showLoadingOverlay, setShowLoadingOverlay] = useState(() => {
    if (typeof window === "undefined") return false;
    // Guard: if a session existed before auto-start, don't carry over the loading flag
    const isAutoStart = sessionOnlyStorage.getItem(STORAGE_KEYS.AUTO_START) === "true";
    const hasSession = !!storage.getItem(STORAGE_KEYS.SESSION_ID);
    const showLoading = sessionOnlyStorage.getItem(STORAGE_KEYS.FC_SHOW_LOADING) === "true";
    if (showLoading && hasSession && !isAutoStart) {
      sessionOnlyStorage.removeItem(STORAGE_KEYS.FC_SHOW_LOADING);
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
  const arbiterAbortControllerRef = useRef<AbortController | null>(null);
  const resumeInFlightRef = useRef(false);

  useEffect(() => {
    const onQuota = () => {
      toast.destructive({
        title: "Storage limit reached",
        description: "Local investigation data could not be saved. Clear browser storage and retry.",
      });
    };
    window.addEventListener("fc_storage_quota_exceeded", onQuota);
    return () => window.removeEventListener("fc_storage_quota_exceeded", onQuota);
  }, []);

  useEffect(() => {
    return () => {
      if (arbiterAbortControllerRef.current) {
        arbiterAbortControllerRef.current.abort();
        arbiterAbortControllerRef.current = null;
      }
      if (warmupTimeoutRef.current) {
        clearTimeout(warmupTimeoutRef.current);
        warmupTimeoutRef.current = null;
      }
    };
  }, []);

  const {
    status = "idle",
    agentUpdates = {}, // Add strict default
    completedAgents = [], // Add strict default
    pipelineMessage = "",
    pipelineThinking = "",
    startSimulation,
    connectWebSocket,
    resumeInvestigation,
    resetSimulation: resetSimulationHook,
    hitlCheckpoint,
    errorMessage: _errorMessage,
    dismissCheckpoint,
    clearCompletedAgents,
    clearPipelineThinking,
    revealQueue,
    revealPending,
    restoreSimulationState,
    isReconnecting,
    arbiterStatus,
    arbiterThinking,
    setSimulationPhase,
  } = useSimulation({
    playSound,
  });

  useEffect(() => {
    completedAgentsRef.current = completedAgents;
    const sid = storage.getItem(STORAGE_KEYS.SESSION_ID);
    if (completedAgents.length > 0 && status !== "idle" && sid) {
      const key = phase === "deep" && status !== "awaiting_decision"
        ? `${STORAGE_KEYS.DEEP_AGENTS}:${sid}`
        : phase === "initial"
          ? `${STORAGE_KEYS.INITIAL_AGENTS}:${sid}`
          : null;
      if (key) {
        try {
          storage.setItem(key, completedAgents, true);
        } catch (_writeErr) {
          // Truncate findings_preview to fit within localStorage quota (~5MB)
          const truncated = completedAgents.map((a) => ({
            ...a,
            findings_preview: (a.findings_preview ?? []).slice(0, 10).map((f) => ({
              ...f,
              summary: f.summary.length > 200 ? f.summary.slice(0, 200) + "…" : f.summary,
            })),
          }));
          try {
            storage.setItem(key, truncated, true);
          } catch (_quotaErr) {
            console.warn("[Investigation] localStorage quota exceeded — agent state not persisted");
          }
        }
      }
    }
  }, [completedAgents, phase, status]);

  const sessionExistsRef = useRef(typeof window !== "undefined" && !!storage.getItem(STORAGE_KEYS.SESSION_ID));

  const [_authError, setAuthError] = useState<string | null>(null);

  const authReadyRef = useRef<Promise<void> | null>(null);

  // Fresh-mount guard: if we arrived here with a pending file in the store,
  // it is always a new investigation — reset the autoStart ref and purge any
  // stale session so Effect A always fires triggerAnalysis cleanly.
  // Guarded against Strict Mode double-mount (Next 15 dev) so we don't
  // pay clearInvestigationPersistence twice on the same render pass.
  const freshMountDoneRef = useRef(false);
  useEffect(() => {
    if (freshMountDoneRef.current) return;
    freshMountDoneRef.current = true;
    if (__pendingFileStore.file) {
      autoStartFiredRef.current = false;
      clearInvestigationPersistence();
      sessionExistsRef.current = false;
    }
  }, []); // intentionally empty — runs once on mount only

  useEffect(() => {
    if (typeof window === "undefined" || authReadyRef.current) return;

    const initAuth = async () => {
      if (getAuthToken() !== null) {
        return; // token in sessionStorage — session is current
      } else if (__pendingFileStore.authPromise) {
        await __pendingFileStore.authPromise
          .then(() => {
            storage.setItem(STORAGE_KEYS.AUTH_OK, "1");
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
            throw err;
          });
      } else if (__pendingFileStore.file || sessionOnlyStorage.getItem(STORAGE_KEYS.AUTO_START) === "true") {
        __pendingFileStore.authPromise = autoLoginAsInvestigator();
        await __pendingFileStore.authPromise
          .then(() => {
            storage.setItem(STORAGE_KEYS.AUTH_OK, "1");
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
            throw err;
          });
      }
    };
    authReadyRef.current = initAuth();
  }, []);


  const resetSimulation = useCallback(() => {
    arbiterControl.abort();
    if (warmupTimeoutRef.current) {
      clearTimeout(warmupTimeoutRef.current);
      warmupTimeoutRef.current = null;
    }
    setIsUploading(false);
    setPhase("initial");
    setAnalysisStreamReady(false);
    setArbiterDeliberating(false);
    setArbiterLiveText("");
    setWsConnectionError(null);
    sessionOnlyStorage.removeItem(STORAGE_KEYS.FC_SHOW_LOADING);
    sessionOnlyStorage.removeItem(STORAGE_KEYS.FC_HANDOFF_FIRED);
    const sid = storage.getItem(STORAGE_KEYS.SESSION_ID);
    if (sid) {
      sessionOnlyStorage.removeItem(`${STORAGE_KEYS.FC_RESUME_REQUESTED}:${sid}`);
    }
    clearInvestigationPersistence();
    lastSessionIdRef.current = null;
    completedAgentsRef.current = [];
    analysisCompleteSoundedRef.current = false;
    sessionExistsRef.current = false;
    resetSimulationHook();
  }, [resetSimulationHook]);

  // Pipe live WebSocket/resume arbiter text into the overlay while it is visible
  useEffect(() => {
    if (!arbiterDeliberating || !arbiterThinking) return;
    setArbiterLiveText(arbiterThinking);
  }, [arbiterDeliberating, arbiterThinking]);

  const [mimeType, setMimeType] = useState<string | null>(() => {
    if (typeof window === "undefined") return null;
    if (__pendingFileStore.file?.type) return __pendingFileStore.file.type;
    return storage.getItem(STORAGE_KEYS.MIME_TYPE) || null;
  });

  useEffect(() => {
    setMimeType(storage.getItem(STORAGE_KEYS.MIME_TYPE) || file?.type || null);
  }, [file]);

  const triggerAnalysis = useCallback(
    async (targetFile: File) => {
      if (!targetFile) return;
      // Synchronous ref guard — prevents concurrent submissions from rapid clicks
      // or retry button spam before React re-renders with isUploading=true.
      if (investigationInFlightRef.current) return;
      investigationInFlightRef.current = true;

      arbiterControl.abort();
      resetSimulationHook();
      clearInvestigationPersistence();
      lastSessionIdRef.current = null;
      completedAgentsRef.current = [];
      analysisCompleteSoundedRef.current = false;
      sessionExistsRef.current = false;

      setMimeType(targetFile.type);
      storage.setItem(STORAGE_KEYS.MIME_TYPE, targetFile.type);

      playSound("scan");
      setIsUploading(true);
      setWsConnectionError(null);
      setPhase("initial");
      setAnalysisStreamReady(false);
      setAutoStartBlocking(false);
      setUploadPhaseText("Uploading evidence to secure pipeline");
      setArbiterLiveText("");
      setArbiterDeliberating(false);
      setSimulationPhase("initial");
      startSimulation();

      const investigatorId = investigatorIdRef.current;
      const uuid = (typeof crypto !== "undefined" && "randomUUID" in crypto)
        ? crypto.randomUUID()
        : Math.random().toString(36).slice(2) + Date.now().toString(36);
      const caseId = "CASE-" + uuid;

      if (sessionOnlyStorage.getItem(STORAGE_KEYS.FC_SHOW_LOADING) !== "true") {
        setShowLoadingOverlay(true);
        sessionOnlyStorage.setItem(STORAGE_KEYS.FC_SHOW_LOADING, "true");
      }

      try {
        await (__pendingFileStore.authPromise ?? Promise.resolve());
        if (getAuthToken() === null) {
          await autoLoginAsInvestigator().then(() => {
            storage.setItem(STORAGE_KEYS.AUTH_OK, "1");
          });
          // autoLoginAsInvestigator uses httpOnly cookies — getAuthToken() remains
          // null even after success. If it resolved without throwing, the session
          // cookie is established and subsequent credentialed requests will work.
        }
      } catch (authErr) {
        setIsUploading(false);
        setShowLoadingOverlay(false);
        sessionOnlyStorage.removeItem(STORAGE_KEYS.FC_SHOW_LOADING);
        resetSimulation();
        investigationInFlightRef.current = false;
        toast.destructive({ title: "Authentication failed", description: authErr instanceof Error ? authErr.message : "Could not establish session." });
        return;
      }

      // Capture image thumbnail before upload so it's available on the result page
      let thumbnailDataUrl: string | null = null;
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
            thumbnailDataUrl = canvas.toDataURL("image/jpeg", 0.72);
            storage.setItem(STORAGE_KEYS.THUMBNAIL, thumbnailDataUrl);
          }
          URL.revokeObjectURL(thumbUrl);
        } catch {
          // thumbnail is cosmetic — never block upload on failure
        }
      } else {
        storage.removeItem(STORAGE_KEYS.THUMBNAIL);
      }

      let sessionIdToUse: string | undefined;
      let isDuplicateSession = false;
      try {
        const investigationRes = await startInvestigation(targetFile, caseId, investigatorId);
        sessionIdToUse = investigationRes.session_id;
      } catch (err) {
        if (err instanceof DuplicateInvestigationError) {
          sessionIdToUse = err.existingSessionId;
          isDuplicateSession = true;
        } else if (err instanceof WorkerWarmupError) {
          setUploadPhaseText("System is warming up, please try again in a moment...");
          toast.warning({
            title: "System Warmup",
            description: "The forensic worker is starting/warming up. Retrying automatically in 15 seconds...",
          });
          investigationInFlightRef.current = false;
          warmupTimeoutRef.current = setTimeout(() => {
            warmupTimeoutRef.current = null;
            triggerAnalysis(targetFile);
          }, 15000);
          return;
        } else {
          const errorMsg = err instanceof Error ? err.message : "Failed to start investigation";
          setIsUploading(false);
          setShowLoadingOverlay(false);
          sessionOnlyStorage.removeItem(STORAGE_KEYS.FC_SHOW_LOADING);
          resetSimulation();
          setWsConnectionError(errorMsg);
          playSound("error");
          toast.destructive({ title: "Investigation Failed", description: errorMsg });
          investigationInFlightRef.current = false;
          return;
        }
      } finally {
        if (!sessionIdToUse || isDuplicateSession) {
          investigationInFlightRef.current = false;
        }
      }

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
      storage.setItem(STORAGE_KEYS.INVESTIGATION_CTX, investigationCtx, true);
      storage.setItem(`${STORAGE_KEYS.INVESTIGATION_CTX}:${sessionIdToUse}`, investigationCtx, true);
      // Individual keys kept for hooks that read them directly
      storage.setItem(STORAGE_KEYS.SESSION_ID, sessionIdToUse);
      if (typeof document !== "undefined") {
        document.cookie = `${STORAGE_KEYS.SESSION_ID}=${sessionIdToUse}; path=/; max-age=3600; SameSite=Lax`;
      }
      storage.setItem(STORAGE_KEYS.FILE_NAME, targetFile.name);
      storage.setItem(`${STORAGE_KEYS.FILE_NAME}:${sessionIdToUse}`, targetFile.name);
      storage.setItem(STORAGE_KEYS.CASE_ID, caseId);
      storage.setItem(STORAGE_KEYS.INVESTIGATOR_ID, investigatorId);
      storage.setItem(STORAGE_KEYS.MIME_TYPE, targetFile.type);
      storage.setItem(`${STORAGE_KEYS.MIME_TYPE}:${sessionIdToUse}`, targetFile.type);

      storage.setItem(STORAGE_KEYS.PIPELINE_START, pipelineStart);
      storage.setItem(`${STORAGE_KEYS.PIPELINE_START}:${sessionIdToUse}`, pipelineStart);

      if (thumbnailDataUrl && !isDuplicateSession) {
        storage.setItem(`${STORAGE_KEYS.THUMBNAIL}:${sessionIdToUse}`, thumbnailDataUrl);
      }

      lastSessionIdRef.current = sessionIdToUse;

      if (isDuplicateSession) {
        try {
          const st = await getArbiterStatus(sessionIdToUse);
          if (st.status === "complete") {
            sessionOnlyStorage.setItem(STORAGE_KEYS.FC_REPORT_READY, "1");
            setIsUploading(false);
            setShowLoadingOverlay(false);
            sessionOnlyStorage.removeItem(STORAGE_KEYS.FC_SHOW_LOADING);
            router.push(`/result/${sessionIdToUse}`, { scroll: true });
            return;
          }
        } catch {
          // ignore status errors, fall through to WS reconnect
        }

        const savedDeepAgents = storage.getItem<AgentUpdate[]>(`${STORAGE_KEYS.DEEP_AGENTS}:${sessionIdToUse}`, true, []);
        const savedInitialAgents = storage.getItem<AgentUpdate[]>(`${STORAGE_KEYS.INITIAL_AGENTS}:${sessionIdToUse}`, true, []);
        const savedAgents = (savedDeepAgents?.length ? savedDeepAgents : savedInitialAgents) ?? [];
        const restoredPhase = savedDeepAgents?.length ? "deep" : "initial";
        setPhase(restoredPhase as "initial" | "deep");
        if (savedAgents.length > 0) {
          restoreSimulationState(savedAgents, "awaiting_decision");
        }
        connectWebSocket(sessionIdToUse, true)
        .then(() => {
          setAnalysisStreamReady(true);
          setIsUploading(false);
          setUploadPhaseText("Reconnected to existing analysis");
          __pendingFileStore.file = null;
          clearPendingEvidenceFile().catch(() => {});
          sessionOnlyStorage.removeItem(STORAGE_KEYS.FC_PENDING_FILE_META);
          sessionExistsRef.current = true;
        })
        .catch((wsErr: unknown) => {
          const wsErrMsg = wsErr instanceof Error ? wsErr.message : "Failed to reconnect to stream";
          setIsUploading(false);
          setShowLoadingOverlay(false);
          sessionOnlyStorage.removeItem(STORAGE_KEYS.FC_SHOW_LOADING);
          sessionOnlyStorage.removeItem(STORAGE_KEYS.FC_HANDOFF_FIRED);
          storage.removeItem(STORAGE_KEYS.SESSION_ID);
          lastSessionIdRef.current = null;
          setWsConnectionError(wsErrMsg);
          playSound("error");
          toast.destructive({
            title: "Reconnection Failed",
            description: `${wsErrMsg}. Please try uploading again.`,
          });
        })
        .finally(() => {
          investigationInFlightRef.current = false;
          sessionOnlyStorage.removeItem(STORAGE_KEYS.FC_HANDOFF_FIRED);
        });
        return;
      }

      setIsUploading(false);
      setUploadPhaseText("Connecting to analysis stream");

      connectWebSocket(sessionIdToUse)
        .then(() => {
          setAnalysisStreamReady(true);
          setUploadPhaseText("Agents dispatching");
          // Overlay dismissal is handled by the status-tracking effect below,
          // which enforces a 2.5s minimum display duration.
        })
        .catch((wsErr: unknown) => {
          const wsErrMsg = wsErr instanceof Error ? wsErr.message : "Failed to connect to stream";
          setIsUploading(false);
          setShowLoadingOverlay(false);
          sessionOnlyStorage.removeItem(STORAGE_KEYS.FC_SHOW_LOADING);
          sessionOnlyStorage.removeItem(STORAGE_KEYS.FC_HANDOFF_FIRED);
          storage.removeItem(STORAGE_KEYS.SESSION_ID);
          lastSessionIdRef.current = null;
          resetSimulation();
          setWsConnectionError(wsErrMsg);
          playSound("error");
          toast.destructive({
            title: "Connection Failed",
            description: `${wsErrMsg}. Please try uploading again.`,
          });
        })
        .finally(() => {
          investigationInFlightRef.current = false;
          __pendingFileStore.file = null;
          clearPendingEvidenceFile().catch(() => {});
          sessionOnlyStorage.removeItem(STORAGE_KEYS.FC_PENDING_FILE_META);
          sessionOnlyStorage.removeItem(STORAGE_KEYS.FC_HANDOFF_FIRED);
          sessionExistsRef.current = true; // Update ref snapshot
        });
    },
    [playSound, startSimulation, connectWebSocket, resetSimulation, resetSimulationHook, restoreSimulationState, setSimulationPhase, router]
  );


  // Effect A — Auto-start from pending file (set by HeroAuthActions before navigating here)
  useEffect(() => {
    // Guard: sessionStorage flag survives Strict Mode double-mount where refs
    // are re-initialized. Prevents triggerAnalysis from firing twice.
    if (sessionOnlyStorage.getItem(STORAGE_KEYS.FC_HANDOFF_FIRED) === "1") return;
    if (autoStartFiredRef.current) return;
    let cancelled = false;

    const startPendingAnalysis = async () => {
    let pending = __pendingFileStore.file;
    if (!pending && sessionOnlyStorage.getItem(STORAGE_KEYS.AUTO_START) === "true") {
      pending = await loadPendingEvidenceFile().catch(() => null);
      if (pending) __pendingFileStore.file = pending;
    }
    if (cancelled) return;
    if (!pending) {
      if (autoStartBlocking || sessionOnlyStorage.getItem(STORAGE_KEYS.AUTO_START) === "true") {
        const pendingMeta = sessionOnlyStorage.getItem(STORAGE_KEYS.FC_PENDING_FILE_META, true, null) as { name: string } | null;
        toast.destructive({
          title: "File selection was lost after refresh",
          description: pendingMeta?.name
            ? `Please reselect "${pendingMeta.name}" to continue. Browsers do not allow restoring file handles after a hard refresh.`
            : "Please select the evidence file again to continue.",
        });
        clearInvestigationPersistence();
        sessionOnlyStorage.removeItem(STORAGE_KEYS.AUTO_START);
        sessionOnlyStorage.removeItem(STORAGE_KEYS.FC_SHOW_LOADING);
        setAutoStartBlocking(false);
        setShowLoadingOverlay(false);
        return;
      }
      sessionOnlyStorage.removeItem(STORAGE_KEYS.AUTO_START);
      sessionOnlyStorage.removeItem(STORAGE_KEYS.FC_SHOW_LOADING);
      setAutoStartBlocking(false);
      setShowLoadingOverlay(false);
      return;
    }

    const validationError = validateEvidenceFile(pending);
    if (validationError) {
      sessionOnlyStorage.removeItem(STORAGE_KEYS.AUTO_START);
      sessionOnlyStorage.removeItem(STORAGE_KEYS.FC_SHOW_LOADING);
      sessionOnlyStorage.removeItem(STORAGE_KEYS.FC_HANDOFF_FIRED);
      setAutoStartBlocking(false);
      setShowLoadingOverlay(false);
      toast.destructive({ title: "Evidence file rejected", description: validationError });
      return;
    }

    autoStartFiredRef.current = true;
    sessionOnlyStorage.setItem(STORAGE_KEYS.FC_HANDOFF_FIRED, "1");
    setFile(pending);
    sessionOnlyStorage.removeItem(STORAGE_KEYS.AUTO_START);
    sessionOnlyStorage.setItem(STORAGE_KEYS.FC_PENDING_FILE_META, JSON.stringify({
      name: pending.name,
      type: pending.type,
      size: pending.size,
      updatedAt: Date.now(),
    }), true);
    triggerAnalysis(pending);
    };

    startPendingAnalysis();
    return () => { cancelled = true; };
  }, [autoStartBlocking, triggerAnalysis]);

  // Effect B — Reconnect existing session
  useEffect(() => {
    if (autoStartFiredRef.current) return;
    if (sessionOnlyStorage.getItem(STORAGE_KEYS.AUTO_START) === "true") return;
    if (__pendingFileStore.file || autoStartBlocking || isUploading) return;

    // fc_show_loading guard on reconnect
    if (sessionOnlyStorage.getItem(STORAGE_KEYS.FC_SHOW_LOADING) === "true") {
      sessionOnlyStorage.removeItem(STORAGE_KEYS.FC_SHOW_LOADING);
      setShowLoadingOverlay(false);
    }

    const existingSessionId = storage.getItem(STORAGE_KEYS.SESSION_ID);
    const noReconnect = sessionOnlyStorage.getItem(STORAGE_KEYS.FC_NO_RECONNECT);

    if (!existingSessionId || noReconnect) {
      if (noReconnect) sessionOnlyStorage.removeItem(STORAGE_KEYS.FC_NO_RECONNECT);
      return;
    }

    autoStartFiredRef.current = true;
    const savedDeepAgents = storage.getItem<AgentUpdate[]>(`${STORAGE_KEYS.DEEP_AGENTS}:${existingSessionId}`, true, []);
    const savedInitialAgents = storage.getItem<AgentUpdate[]>(`${STORAGE_KEYS.INITIAL_AGENTS}:${existingSessionId}`, true, []);
    const savedAgents = (savedDeepAgents?.length ? savedDeepAgents : savedInitialAgents) ?? [];
    const restoredPhase = savedDeepAgents?.length ? "deep" : "initial";

    setPhase(restoredPhase);
    startSimulation();
    if (savedAgents.length > 0) {
      restoreSimulationState(savedAgents, "awaiting_decision");
    }
    setAnalysisStreamReady(false);
    setUploadPhaseText("Reconnecting to analysis stream");
    setShowLoadingOverlay(false);
    sessionOnlyStorage.removeItem(STORAGE_KEYS.FC_SHOW_LOADING);

    let effectCancelled = false;
    (async () => {
      try {
        const st = await withTimeout(getArbiterStatus(existingSessionId), 8_000);
        if (effectCancelled) return;
        if (st.status === "not_found") {
          storage.removeItem(STORAGE_KEYS.SESSION_ID);
          storage.removeItem(STORAGE_KEYS.INVESTIGATION_CTX);
          resetSimulation();
          setShowLoadingOverlay(false);
          sessionOnlyStorage.setItem(STORAGE_KEYS.FC_OPEN_UPLOAD_ONCE, "1");
          sessionOnlyStorage.setItem(STORAGE_KEYS.FC_NO_RECONNECT, "1");
          router.push("/?upload=1");
          return;
        }
        if (st.status === "complete") {
          sessionOnlyStorage.setItem(STORAGE_KEYS.FC_REPORT_READY, "1");
          router.push(`/result/${existingSessionId}`, { scroll: true });
          return;
        }
      } catch { /* ignore poll errors during reconnect */ }

      if (effectCancelled) return;
      connectWebSocket(existingSessionId, true)
        .then(() => { if (!effectCancelled) setAnalysisStreamReady(true); })
        .catch((wsErr: unknown) => {
          if (effectCancelled) return;
          const wsErrMsg = wsErr instanceof Error ? wsErr.message : "Failed to connect to stream";
          setWsConnectionError(wsErrMsg);
          setShowLoadingOverlay(false);
        });
    })();
    return () => { effectCancelled = true; };
  }, [autoStartBlocking, isUploading, startSimulation, connectWebSocket, resetSimulation, restoreSimulationState, router]);

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
      playSound("success-chime");
    } catch {
      toast.destructive({ title: "Decision Failed", description: "Could not submit decision." });
    } finally {
      setIsSubmittingHITL(false);
    }
  };

  const handleAcceptAnalysis = useCallback(async () => {
    if (isNavigating || resumeInFlightRef.current || investigationInFlightRef.current) return;
    resumeInFlightRef.current = true;
    playSound("click");
    playSound("arbiter_start");
    storage.setItem(STORAGE_KEYS.IS_DEEP, "false");
    const sid = storage.getItem(STORAGE_KEYS.SESSION_ID);
    if (sid) {
      storage.setItem(`${STORAGE_KEYS.RESULT_PHASE}:${sid}`, "initial");
      storage.setItem(`${STORAGE_KEYS.INITIAL_AGENTS}:${sid}`, completedAgentsRef.current, true);
      sessionOnlyStorage.setItem(`${STORAGE_KEYS.FC_RESUME_REQUESTED}:${sid}`, "initial");
    }
    arbiterControl.abort();
    setIsNavigating(true);
    setArbiterDeliberating(true);
    setArbiterLiveText(UI_STRINGS.COMPILING_FINDINGS);
    const ARBITER_MIN_DISPLAY_MS = 1500;
    const _arbiterStartTime = Date.now();
    let navigationStarted = false;
    try {
      if (!sid) throw new Error("No active session");
      await resumeInvestigation(false);
      arbiterAbortControllerRef.current = new AbortController();
      const ok = await waitForFinalReport(sid, setArbiterLiveText, 300_000, arbiterAbortControllerRef.current.signal);
      if (!ok) {
        sessionOnlyStorage.setItem(STORAGE_KEYS.FC_REPORT_READY, "1");
        sessionOnlyStorage.setItem(STORAGE_KEYS.FC_ARBITER_TRANSITIONING, "1");
        document.body.setAttribute("data-fc-loading", "1");
        navigationStarted = true;
        router.push(`/result/${encodeURIComponent(sid)}`);
        return;
      }

      // Ensure minimum overlay display time so the arbiter transition doesn't
      // flash-dismiss when the pre-warmed report resolves in <1s.
      const _elapsed = Date.now() - _arbiterStartTime;
      if (_elapsed < ARBITER_MIN_DISPLAY_MS) {
        await new Promise<void>((r) => setTimeout(r, ARBITER_MIN_DISPLAY_MS - _elapsed));
      }

      sessionOnlyStorage.setItem(STORAGE_KEYS.FC_REPORT_READY, "1");
      sessionOnlyStorage.setItem(STORAGE_KEYS.FC_ARBITER_TRANSITIONING, "1");
      document.body.setAttribute("data-fc-loading", "1");
      navigationStarted = true;
      await new Promise<void>((r) => requestAnimationFrame(() => r()));
      router.push(`/result/${sid}`, { scroll: true });
    } catch (err) {
      sessionOnlyStorage.removeItem(STORAGE_KEYS.FC_ARBITER_TRANSITIONING);
      sessionOnlyStorage.removeItem(STORAGE_KEYS.FC_REPORT_READY);
      toast.destructive({
        title: "Could not start synthesis",
        description: err instanceof Error ? err.message : "Could not resume the investigation.",
      });
    } finally {
      resumeInFlightRef.current = false;
      setIsNavigating(false);
      // Only clear the overlay if navigation never started. If it did,
      // the component will unmount when the result page loads — clearing
      // state here would drop the overlay while the old page is still visible.
      if (!navigationStarted) {
        setArbiterDeliberating(false);
      }
    }
  }, [playSound, resumeInvestigation, router, isNavigating]);

  const handleDeepAnalysis = useCallback(async () => {
    if (investigationInFlightRef.current || resumeInFlightRef.current) return;
    investigationInFlightRef.current = true;
    resumeInFlightRef.current = true;
    playSound("click");
    playSound("scan");
    storage.setItem(STORAGE_KEYS.IS_DEEP, "true");
    const sid = storage.getItem(STORAGE_KEYS.SESSION_ID);
    // Capture the final initial-phase snapshot before any clearing
    const initialAgentSnapshot = (completedAgentsRef.current as AgentUpdate[]).filter(
      (a) => a.status !== "skipped",
    );
    if (sid) {
      storage.setItem(`${STORAGE_KEYS.RESULT_PHASE}:${sid}`, "deep");
      storage.setItem(`${STORAGE_KEYS.INITIAL_AGENTS}:${sid}`, initialAgentSnapshot, true);
      sessionOnlyStorage.setItem(`${STORAGE_KEYS.FC_RESUME_REQUESTED}:${sid}`, "deep");
      storage.removeItem(`${STORAGE_KEYS.DEEP_AGENTS}:${sid}`);
    }
    analysisCompleteSoundedRef.current = false;
    clearPipelineThinking();
    clearCompletedAgents();
    completedAgentsRef.current = [];
    setPhase("deep");
    try {
      setSimulationPhase("deep");
      await resumeInvestigation(true);
      // Do NOT reconnect the WebSocket here — the existing connection is still live
      // after PIPELINE_PAUSED and will receive deep-phase AGENT_UPDATE messages.
      // Closing and reopening creates a race window where backend messages sent
      // immediately after /resume are lost, leaving all agents stuck in "checking".
    } catch (err) {
      playSound("error");
      toast.destructive({
        title: "Deep analysis failed to start",
        description: err instanceof Error ? err.message : "Could not resume the investigation.",
      });
    } finally {
      investigationInFlightRef.current = false;
      resumeInFlightRef.current = false;
    }
  }, [playSound, resumeInvestigation, clearCompletedAgents, clearPipelineThinking, setSimulationPhase]);

  const retryWsConnection = useCallback(() => {
    const sid = lastSessionIdRef.current || storage.getItem(STORAGE_KEYS.SESSION_ID);
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
        setUploadPhaseText("Agents dispatching");
        setShowLoadingOverlay(false);
        sessionOnlyStorage.removeItem(STORAGE_KEYS.FC_SHOW_LOADING);
      })
      .catch((wsErr: unknown) => {
        const wsErrMsg = wsErr instanceof Error ? wsErr.message : "Failed to connect to stream";
        setWsConnectionError(wsErrMsg);
        resetSimulation();
      });
  }, [file, triggerAnalysis, startSimulation, connectWebSocket, resetSimulation]);

  const handleFile = useCallback((targetFile: File) => {
    const error = validateEvidenceFile(targetFile);
    if (error) {
      setValidationError(error);
      setFile(null);
      playSound("error");
      return;
    }

    setValidationError(null);
    setFile(targetFile);
  }, [playSound]);

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
    analysisCompleteSoundedRef.current = false;
    completedAgentsRef.current = [];
    clearInvestigationPersistence();
    resetSimulation();
    sessionOnlyStorage.removeItem(STORAGE_KEYS.AUTO_START);
    sessionOnlyStorage.setItem(STORAGE_KEYS.FC_OPEN_UPLOAD_ONCE, "1");
    sessionOnlyStorage.setItem(STORAGE_KEYS.FC_NO_RECONNECT, "1");
    router.push("/?upload=1");
  }, [resetSimulation, playSound, router]);

  const handleViewResults = useCallback(async () => {
    if (isNavigating || resumeInFlightRef.current || investigationInFlightRef.current) return;
    resumeInFlightRef.current = true;
    playSound("click");
    playSound("arbiter_start");
    const sid = storage.getItem(STORAGE_KEYS.SESSION_ID);
    if (sid) {
      storage.setItem(`${STORAGE_KEYS.RESULT_PHASE}:${sid}`, "deep");
      storage.setItem(`${STORAGE_KEYS.DEEP_AGENTS}:${sid}`, completedAgentsRef.current, true);
    }
    setIsNavigating(true);
    setArbiterDeliberating(true);
    setArbiterLiveText(UI_STRINGS.FINAL_SYNTHESIS);
    const ARBITER_MIN_DISPLAY_MS = 1500;
    const _arbiterStartTime = Date.now();
    let navigationStarted = false;
    try {
      if (!sid) throw new Error("No active session");
      const arbiterSt = await getArbiterStatus(sid).catch(() => null);
      if (arbiterSt?.status !== "complete") {
        await resumeInvestigation(false);
      }
      arbiterAbortControllerRef.current = new AbortController();
      const ok = await waitForFinalReport(sid, setArbiterLiveText, 300_000, arbiterAbortControllerRef.current.signal);
      if (!ok) {
        sessionOnlyStorage.setItem(STORAGE_KEYS.FC_REPORT_READY, "1");
        sessionOnlyStorage.setItem(STORAGE_KEYS.FC_ARBITER_TRANSITIONING, "1");
        document.body.setAttribute("data-fc-loading", "1");
        navigationStarted = true;
        router.push(`/result/${encodeURIComponent(sid)}`);
        return;
      }

      // Ensure minimum overlay display time so the arbiter transition doesn't
      // flash-dismiss when the pre-warmed report resolves in <1s.
      const _elapsed = Date.now() - _arbiterStartTime;
      if (_elapsed < ARBITER_MIN_DISPLAY_MS) {
        await new Promise<void>((r) => setTimeout(r, ARBITER_MIN_DISPLAY_MS - _elapsed));
      }

      sessionOnlyStorage.setItem(STORAGE_KEYS.FC_REPORT_READY, "1");
      sessionOnlyStorage.setItem(STORAGE_KEYS.FC_ARBITER_TRANSITIONING, "1");
      document.body.setAttribute("data-fc-loading", "1");
      navigationStarted = true;
      await new Promise<void>((r) => requestAnimationFrame(() => r()));
      router.push(`/result/${encodeURIComponent(sid)}`);
    } catch (err) {
      sessionOnlyStorage.removeItem(STORAGE_KEYS.FC_ARBITER_TRANSITIONING);
      sessionOnlyStorage.removeItem(STORAGE_KEYS.FC_REPORT_READY);
      toast.destructive({
        title: "Could not start synthesis",
        description: err instanceof Error ? err.message : "Could not resume the investigation.",
      });
    } finally {
      resumeInFlightRef.current = false;
      setIsNavigating(false);
      if (!navigationStarted) {
        setArbiterDeliberating(false);
      }
    }
  }, [playSound, resumeInvestigation, router, isNavigating]);

  const validAgentsData = AGENTS_DATA.filter((a) => a.name !== "Council Arbiter");
  const validCompletedAgents = completedAgents.filter((c: AgentUpdate) =>
    validAgentsData.some((v) => v.id === c.agent_id)
  );

  const expectedAgentIds = useMemo(() => supportedAgentIdsForMime(mimeType), [mimeType]);

  const expectedCompletedCount = validCompletedAgents.filter((c: AgentUpdate) =>
    expectedAgentIds.has(c.agent_id)
  ).length;

  const awaitingDecision =
    !isNavigating &&
    !arbiterDeliberating &&
    status === "awaiting_decision" &&
    phase === "initial";
  const allAgentsDone = phase === "deep"
    ? (status === "complete" || expectedCompletedCount >= expectedAgentIds.size)
    : (status === "awaiting_decision" || expectedCompletedCount >= expectedAgentIds.size);

  useEffect(() => {
    if ((awaitingDecision || (phase === "deep" && allAgentsDone)) && !analysisCompleteSoundedRef.current) {
      analysisCompleteSoundedRef.current = true;
      playSound("analysis_done");
    }
  }, [awaitingDecision, phase, allAgentsDone, playSound]);

  const hasStartedAnalysis =
    status !== "idle" ||
    isUploading ||
    validCompletedAgents.length > 0 ||
    autoStartBlocking ||
    !!wsConnectionError;

  // Overlay dismissal: dismiss as soon as the WebSocket connection is
  // established (analysisStreamReady) OR the pipeline sends its first
  // real status update. An 800ms minimum keeps UX smooth.
  const SAFETY_TIMEOUT_MS = 5_000;
  const MIN_DISPLAY_MS = 800;
  useEffect(() => {
    if (!showLoadingOverlay) return;

    const shouldDismiss =
      analysisStreamReady ||
      (status !== "idle" && status !== "initiating");

    if (shouldDismiss) {
      const timer = setTimeout(() => {
        setShowLoadingOverlay(false);
        sessionOnlyStorage.removeItem(STORAGE_KEYS.FC_SHOW_LOADING);
        sessionOnlyStorage.removeItem(STORAGE_KEYS.FC_LOADING_TEXT);
        sessionOnlyStorage.removeItem(STORAGE_KEYS.FC_LOADING_DISPATCHED);
      }, MIN_DISPLAY_MS);
      return () => clearTimeout(timer);
    }

    const safety = setTimeout(() => {
      setShowLoadingOverlay(false);
      sessionOnlyStorage.removeItem(STORAGE_KEYS.FC_SHOW_LOADING);
      sessionOnlyStorage.removeItem(STORAGE_KEYS.FC_LOADING_TEXT);
      sessionOnlyStorage.removeItem(STORAGE_KEYS.FC_LOADING_DISPATCHED);
    }, SAFETY_TIMEOUT_MS);
    return () => clearTimeout(safety);
  }, [showLoadingOverlay, analysisStreamReady, status]);

  // Sync loading state and progress messages to storage for GlobalLoadingOverlay
  useEffect(() => {
    if (showLoadingOverlay) {
      sessionOnlyStorage.setItem(STORAGE_KEYS.FC_SHOW_LOADING, "true");
      const currentText = uploadPhaseText || pipelineMessage || "Initializing workspace";
      sessionOnlyStorage.setItem(STORAGE_KEYS.FC_LOADING_TEXT, currentText);
      const dispatchedCount = Math.min(
        Object.keys(agentUpdates).filter((k) => k !== "Arbiter").length,
        5
      );
      sessionOnlyStorage.setItem(STORAGE_KEYS.FC_LOADING_DISPATCHED, String(dispatchedCount));
    } else {
      sessionOnlyStorage.removeItem(STORAGE_KEYS.FC_SHOW_LOADING);
      sessionOnlyStorage.removeItem(STORAGE_KEYS.FC_LOADING_TEXT);
      sessionOnlyStorage.removeItem(STORAGE_KEYS.FC_LOADING_DISPATCHED);
    }
  }, [showLoadingOverlay, uploadPhaseText, pipelineMessage, agentUpdates]);

  return {
    file, setFile,
    validationError,
    handleFile,
    showUploadForm: !hasStartedAnalysis,
    isUploading,
    uploadPhaseText,
    showLoadingOverlay,
    phase,
    isSubmittingHITL,
    isNavigating,
    status,
    agentUpdates,
    completedAgents,
    pipelineMessage,
    pipelineThinking,
    hitlCheckpoint,
    dismissCheckpoint,
    revealQueue,
    revealPending,
    isReconnecting,
    arbiterStatus,
    arbiterThinking,
    validCompletedAgents,
    wsConnectionError,
    retryWsConnection,
    handleHITLDecision,
    handleAcceptAnalysis,
    handleDeepAnalysis,
    handleNewUpload,
    handleViewResults,
    arbiterDeliberating,
    arbiterLiveText,
    hasStartedAnalysis,
    allAgentsDone,
    awaitingDecision,
    mimeType,
    handoffRecovering: autoStartBlocking || showLoadingOverlay,
  };
}
