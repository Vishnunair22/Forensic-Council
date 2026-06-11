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
import {
  ARBITER_MIN_DISPLAY_MS,
  ARBITER_WAIT_MAX_MS,
  WARMUP_RETRY_DELAY_MS,
  REPORT_POLL_DELAY_MS,
} from "@/lib/timings";
import { __pendingFileStore } from "@/lib/pendingFileStore";
import { arbiterControl } from "@/lib/arbiterControl";
import { type SoundType } from "@/hooks/useSound";
import { type AgentUpdate } from "@/components/evidence/types";
import { storage, sessionOnlyStorage } from "@/lib/storage";
import { supportedAgentIdsForMime } from "@/lib/agentSupport";
import { useCapabilities } from "@/hooks/useCapabilities";
import { clearInvestigationPersistence } from "@/lib/investigationStorage";
import { validateEvidenceFile, resolveMimeType } from "@/lib/fileValidation";
import { clearPendingEvidenceFile } from "@/lib/pendingFilePersistence";
import { STORAGE_KEYS } from "@/lib/storageKeys";
import { authService } from "@/lib/upload/authService";
import { fileHandoffManager } from "@/lib/upload/fileHandoffManager";
import { loadingOverlayController } from "@/lib/upload/loadingOverlayController";
import { computeFileSha256 } from "@/lib/crypto/fileHash";



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

const _MAX_ARBITER_POLLS = 300;

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
  let pollCount = 0;
  while (Date.now() < deadline && pollCount < _MAX_ARBITER_POLLS) {
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
              const t = setTimeout(r, REPORT_POLL_DELAY_MS);
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
    pollCount++;
  }
  return false;
}

export function useInvestigation(playSound: (type: SoundType) => void) {
  const router = useRouter();
  const { capabilities } = useCapabilities();

  // Resolve the investigator id WITHOUT writing storage — a render-phase
  // storage.setItem dispatches `fc_storage_update`, which makes GlobalNavbar
  // setState while EvidenceUploadClient is still rendering (React "Cannot update
  // a component while rendering a different component" warning). The freshly
  // generated id is persisted in an effect below instead.
  const _resolveInvestigatorId = () => {
    if (typeof window === "undefined") return "REQ-000000";
    const stored = storage.getItem(STORAGE_KEYS.INVESTIGATOR_ID);
    const validIdPattern = /^REQ-\d{5,10}$/;
    if (stored && validIdPattern.test(stored)) return stored;
    return "REQ-" + (Math.floor(Math.random() * 900000) + 100000);
  };

  const investigatorIdRef = useRef<string>(_resolveInvestigatorId());

  useEffect(() => {
    if (typeof window === "undefined") return;
    const stored = storage.getItem(STORAGE_KEYS.INVESTIGATOR_ID);
    if (stored !== investigatorIdRef.current) {
      storage.setItem(STORAGE_KEYS.INVESTIGATOR_ID, investigatorIdRef.current);
    }
  }, []);
  const warmupTimeoutRef = useRef<NodeJS.Timeout | null>(null);
  const [file, setFile] = useState<File | null>(null);
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
        } catch {
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
          } catch {
            console.warn("[Investigation] localStorage quota exceeded — agent state not persisted");
          }
        }
      }
    }
  }, [completedAgents, phase, status]);

  const sessionExistsRef = useRef(typeof window !== "undefined" && !!storage.getItem(STORAGE_KEYS.SESSION_ID));

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
      if (getAuthToken() !== null) return;
      try {
        await authService.ensureAuthenticated();
      } catch (err: unknown) {
        const msg = err instanceof Error ? err.message : "Authentication failed";
        toast.destructive({
          title: "Authentication Error",
          description: `Could not establish session: ${msg}. Please refresh the page.`,
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
      try { storage.removeItem(STORAGE_KEYS.HITL_CHECKPOINT); } catch {}
      lastSessionIdRef.current = null;
      completedAgentsRef.current = [];
      analysisCompleteSoundedRef.current = false;
      sessionExistsRef.current = false;

      // Use the resolved MIME (extension fallback for empty/generic browser
      // types) so client-side agent filtering matches the backend's libmagic
      // detection — prevents audio/video files briefly showing agents as
      // "not applicable" when the browser reports an empty file.type.
      const resolvedMime = resolveMimeType(targetFile);
      setMimeType(resolvedMime);
      storage.setItem(STORAGE_KEYS.MIME_TYPE, resolvedMime);

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
        await authService.ensureAuthenticated();
      } catch (authErr) {
        setIsUploading(false);
        setShowLoadingOverlay(false);
        sessionOnlyStorage.removeItem(STORAGE_KEYS.FC_SHOW_LOADING);
        // Clear the handoff-fired flag so the auto-start effect can retry on a
        // page refresh — otherwise a transient auth failure permanently
        // short-circuits the effect and strands the pending file.
        sessionOnlyStorage.removeItem(STORAGE_KEYS.FC_HANDOFF_FIRED);
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
      let contentHash: string | null = null;
      // When a warmup retry is scheduled we deliberately keep the in-flight
      // guard held across the 15s window — the finally must not clear it.
      let warmupRetryScheduled = false;
      try {
        let pendingClientSha256 = fileHandoffManager.getPendingClientSha256();

        if (!pendingClientSha256) {
          try {
            const computed = await computeFileSha256(targetFile);
            pendingClientSha256 = computed.hex.toLowerCase();

            const existingMeta = fileHandoffManager.getFileMeta();
            sessionOnlyStorage.setItem(
              STORAGE_KEYS.FC_PENDING_FILE_META,
              JSON.stringify({
                ...existingMeta,
                name: targetFile.name,
                type: targetFile.type,
                size: targetFile.size,
                updatedAt: Date.now(),
                clientSha256: pendingClientSha256,
              }),
            );
          } catch {
            throw new Error("Could not compute SHA-256 custody hash before upload.");
          }
        }

        const investigationRes = await startInvestigation(targetFile, caseId, investigatorId, pendingClientSha256);
        sessionIdToUse = investigationRes.session_id;
        contentHash = investigationRes.content_hash ?? null;

        if (investigationRes.content_hash) {
          storage.setItem(`${STORAGE_KEYS.EVIDENCE_SHA256}:${sessionIdToUse}`, investigationRes.content_hash);
        }
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
          // Keep investigationInFlightRef = true for the entire warmup window so
          // an external click cannot slip a concurrent submission through the
          // top-of-function guard. The flag is released synchronously inside the
          // timer callback immediately before the recursive retry re-acquires it
          // (no await between the two, so the gap is zero async ticks).
          warmupRetryScheduled = true;
          warmupTimeoutRef.current = setTimeout(() => {
            warmupTimeoutRef.current = null;
            investigationInFlightRef.current = false;
            triggerAnalysis(targetFile);
          }, WARMUP_RETRY_DELAY_MS);
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
          fileHandoffManager.cleanup();
          return;
        }
      } finally {
        if (!sessionIdToUse && !warmupRetryScheduled) {
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
        evidence_sha256: contentHash,
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

      if (contentHash) {
        storage.setItem(`${STORAGE_KEYS.EVIDENCE_SHA256}:${sessionIdToUse}`, contentHash);
      }

      if (thumbnailDataUrl) {
        storage.setItem(`${STORAGE_KEYS.THUMBNAIL}:${sessionIdToUse}`, thumbnailDataUrl);
      }

      lastSessionIdRef.current = sessionIdToUse;

      if (isDuplicateSession) {
        try {
          const st = await getArbiterStatus(sessionIdToUse);
          if (st.status === "complete") {
            sessionOnlyStorage.setItem(`${STORAGE_KEYS.FC_REPORT_READY}:${sessionIdToUse}`, "1");
            setIsUploading(false);
            setShowLoadingOverlay(false);
            sessionOnlyStorage.removeItem(STORAGE_KEYS.FC_SHOW_LOADING);
            router.push(`/result/${sessionIdToUse}`, { scroll: true });
            return;
          }
        } catch {
          // ignore status errors, fall through to WS reconnect
        }

        // Re-uploading the same evidence dedups to an existing session. Do NOT
        // optimistically replay this browser's locally-cached agent findings —
        // that cache can be STALE (from a prior run of the same content with older
        // code) and was the cause of stale findings resurfacing. Purge it and let
        // the server's WebSocket replay buffer deliver the AUTHORITATIVE current
        // findings (the backend re-sends all buffered agent cards on reconnect).
        storage.removeItem(`${STORAGE_KEYS.INITIAL_AGENTS}:${sessionIdToUse}`);
        storage.removeItem(`${STORAGE_KEYS.DEEP_AGENTS}:${sessionIdToUse}`);
        resetSimulation();
        // FLOW FIX: rejoin the session in the phase it actually reached. The
        // RESULT_PHASE scoped key survives the cache purge above; without this
        // a duplicate upload into a mid-deep session pinned the phase ref to
        // "initial" and the cross-phase guard dropped every replayed deep
        // event from the server's buffer.
        const dupPhase: "initial" | "deep" =
          storage.getItem(`${STORAGE_KEYS.RESULT_PHASE}:${sessionIdToUse}`) === "deep"
            ? "deep"
            : "initial";
        setPhase(dupPhase);
        setSimulationPhase(dupPhase);
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
          // Overlay dismissal is handled by the status-tracking effect below.
          // The dismiss effect enforces an 800ms minimum display duration via
          // both the controller's internal timer and a React setTimeout.
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
    [playSound, startSimulation, connectWebSocket, resetSimulation, resetSimulationHook, setSimulationPhase, router]
  );


  // Effect A — Auto-start from pending file (set by HeroAuthActions before navigating here)
  useEffect(() => {
    // F-H-4: clear stale FC_HANDOFF_FIRED when there is no pending file
    // (retry after page refresh or SPA re-navigation).  The flag survives
    // Strict Mode double-mount because __pendingFileStore.file is still
    // set during both mounts.
    if (sessionOnlyStorage.getItem(STORAGE_KEYS.FC_HANDOFF_FIRED) === "1" && !__pendingFileStore.file && !autoStartBlocking) {
      sessionOnlyStorage.removeItem(STORAGE_KEYS.FC_HANDOFF_FIRED);
    }
    if (sessionOnlyStorage.getItem(STORAGE_KEYS.FC_HANDOFF_FIRED) === "1") return;
    if (autoStartFiredRef.current) return;
    let cancelled = false;

    const startPendingAnalysis = async () => {
    const pending = await fileHandoffManager.recoverFile();
    if (cancelled) return;
    if (!pending) {
      if (autoStartBlocking || sessionOnlyStorage.getItem(STORAGE_KEYS.AUTO_START) === "true") {
        const pendingMeta = fileHandoffManager.getFileMeta();
        toast.destructive({
          title: "File selection was lost",
          description: pendingMeta?.name
            ? `"${pendingMeta.name}" could not be restored after refresh. Please return to the home page and select it again. Browsers cannot retain file access across hard refreshes.`
            : "The evidence file could not be restored. Please return to the home page and select it again.",
        });
        fileHandoffManager.cleanup();
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
      fileHandoffManager.cleanup();
      setAutoStartBlocking(false);
      setShowLoadingOverlay(false);
      toast.destructive({ title: "Evidence file rejected", description: validationError });
      return;
    }

    autoStartFiredRef.current = true;
    sessionOnlyStorage.setItem(STORAGE_KEYS.FC_HANDOFF_FIRED, "1");
    setFile(pending);
    sessionOnlyStorage.removeItem(STORAGE_KEYS.AUTO_START);
    const existingMeta = fileHandoffManager.getFileMeta();
    sessionOnlyStorage.setItem(
      STORAGE_KEYS.FC_PENDING_FILE_META,
      JSON.stringify({
        name: pending.name,
        type: pending.type,
        size: pending.size,
        updatedAt: Date.now(),
        clientSha256: existingMeta?.clientSha256 ?? null,
      }),
    );
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
    // FLOW FIX: sync the simulation's phase ref to the restored phase AFTER
    // startSimulation() (which force-resets it to "initial"). Without this, a
    // refresh mid-deep reconnected with activePhaseRef="initial", so every
    // replayed deep-phase AGENT_UPDATE/AGENT_COMPLETE was dropped by the
    // cross-phase guard ("Ignoring deep-phase AGENT_COMPLETE during initial
    // analysis") and the deep findings never repopulated.
    setSimulationPhase(restoredPhase);
    const savedAgentCount = savedAgents.length;
    const restoredStatus: "awaiting_decision" | "analyzing" = 
      savedAgentCount > 0 ? "awaiting_decision" : "analyzing";
    if (savedAgentCount > 0) {
      restoreSimulationState(savedAgents, restoredStatus);
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
          // The backend no longer has this session (expired or wiped). Purge ALL
          // per-session client caches so its STALE agent findings can never be
          // re-restored into the view — this was the root cause of stale findings
          // resurfacing after a backend wipe.
          storage.removeItem(`${STORAGE_KEYS.INITIAL_AGENTS}:${existingSessionId}`);
          storage.removeItem(`${STORAGE_KEYS.DEEP_AGENTS}:${existingSessionId}`);
          storage.removeItem(STORAGE_KEYS.SESSION_ID);
          storage.removeItem(STORAGE_KEYS.INVESTIGATION_CTX);
          if (typeof document !== "undefined") {
            document.cookie = `${STORAGE_KEYS.SESSION_ID}=; path=/; max-age=0; SameSite=Lax`;
          }
          resetSimulation();
          setShowLoadingOverlay(false);
          sessionOnlyStorage.setItem(STORAGE_KEYS.FC_OPEN_UPLOAD_ONCE, "1");
          sessionOnlyStorage.setItem(STORAGE_KEYS.FC_NO_RECONNECT, "1");
          // Route home; the FC_OPEN_UPLOAD_ONCE flag makes HeroAuthActions open the
          // upload modal immediately, so the user lands ready to re-upload rather
          // than seeing a stale/expired session view.
          router.push("/");
          return;
        }
        if (st.status === "complete") {
          sessionOnlyStorage.setItem(`${STORAGE_KEYS.FC_REPORT_READY}:${existingSessionId}`, "1");
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
  }, [autoStartBlocking, isUploading, startSimulation, connectWebSocket, resetSimulation, restoreSimulationState, setSimulationPhase, router]);

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

  // Shared navigation tail — polls for the final report, enforces minimum
  // overlay display time, then pushes to the result page.
  // Returns true so callers can track that navigation was initiated.
  const _navigateToResult = useCallback(async (
    sid: string,
    arbiterStartTime: number,
  ): Promise<boolean> => {
    arbiterAbortControllerRef.current = new AbortController();
    // FLOW FIX: register the controller on the GLOBAL arbiterControl handle.
    // Every arbiterControl.abort() call site (navbar reset, app reset, new
    // upload, deep-analysis switch) was a silent no-op before this line —
    // nothing ever assigned abortController, so "aborting the arbiter wait"
    // only actually happened on component unmount via the local ref cleanup.
    arbiterControl.abortController = arbiterAbortControllerRef.current;
    const ok = await waitForFinalReport(
      sid,
      setArbiterLiveText,
      ARBITER_WAIT_MAX_MS,
      arbiterAbortControllerRef.current.signal,
    );
    if (ok) {
      const elapsed = Date.now() - arbiterStartTime;
      if (elapsed < ARBITER_MIN_DISPLAY_MS) {
        await new Promise<void>((r) => setTimeout(r, ARBITER_MIN_DISPLAY_MS - elapsed));
      }
      await new Promise<void>((r) => requestAnimationFrame(() => r()));
      // Only mark the report "ready" when it ACTUALLY finalized. On an arbiter-wait
      // timeout (ok=false — e.g. a wedged worker) setting this told the result page
      // to reveal immediately against a report that isn't there; navigating WITHOUT
      // it lets the result page show its normal loading state and its own deadline
      // resolve a true wedge to an actionable error instead of a stuck overlay.
      sessionOnlyStorage.setItem(`${STORAGE_KEYS.FC_REPORT_READY}:${sid}`, "1");
      sessionOnlyStorage.setItem(`${STORAGE_KEYS.FC_ARBITER_TRANSITIONING}:${sid}`, "1");
    }
    // No data-fc-loading bridge: the route's loading.tsx (a solid branded dark
    // cover) is the Suspense fallback that fills the navigation, and the App Router
    // transition holds the evidence arbiter overlay until it's ready. The old
    // body::before bridge sat ABOVE the app's stacking context and obscured BOTH
    // the loading cover and the result overlay with an empty dark blur — the
    // "blank before the result loads". Branded covers now hand off seamlessly.
    router.push(`/result/${sid}`);
    return true;
  }, [router]);

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
    const arbiterStartTime = Date.now();
    let navigationStarted = false;
    try {
      if (!sid) throw new Error("No active session");
      await resumeInvestigation(false);
      navigationStarted = await _navigateToResult(sid, arbiterStartTime);
    } catch (err) {
      sessionOnlyStorage.removeItem(`${STORAGE_KEYS.FC_ARBITER_TRANSITIONING}:${sid}`);
      sessionOnlyStorage.removeItem(`${STORAGE_KEYS.FC_REPORT_READY}:${sid}`);
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
  }, [playSound, resumeInvestigation, isNavigating, _navigateToResult]);

  const handleDeepAnalysis = useCallback(async () => {
    if (investigationInFlightRef.current || resumeInFlightRef.current) return;
    investigationInFlightRef.current = true;
    resumeInFlightRef.current = true;
    playSound("click");
    playSound("scan");
    storage.setItem(STORAGE_KEYS.IS_DEEP, "true");
    const sid = storage.getItem(STORAGE_KEYS.SESSION_ID);
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
    } catch (err) {
      // Roll back to initial phase so the user can retry
      const rollbackSid = lastSessionIdRef.current || storage.getItem(STORAGE_KEYS.SESSION_ID);
      if (rollbackSid) {
        storage.setItem(`${STORAGE_KEYS.RESULT_PHASE}:${rollbackSid}`, "initial");
        sessionOnlyStorage.removeItem(`${STORAGE_KEYS.FC_RESUME_REQUESTED}:${rollbackSid}`);
      }
      setPhase("initial");
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
    const arbiterStartTime = Date.now();
    let navigationStarted = false;
    try {
      if (!sid) throw new Error("No active session");
      const arbiterSt = await getArbiterStatus(sid).catch(() => null);
      if (arbiterSt?.status !== "complete") {
        await resumeInvestigation(false);
      }
      navigationStarted = await _navigateToResult(sid, arbiterStartTime);
    } catch (err) {
      sessionOnlyStorage.removeItem(`${STORAGE_KEYS.FC_ARBITER_TRANSITIONING}:${sid}`);
      sessionOnlyStorage.removeItem(`${STORAGE_KEYS.FC_REPORT_READY}:${sid}`);
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
  }, [playSound, resumeInvestigation, isNavigating, _navigateToResult]);

  const validAgentsData = AGENTS_DATA.filter((a) => a.name !== "Council Arbiter");
  const validCompletedAgents = completedAgents.filter((c: AgentUpdate) =>
    validAgentsData.some((v) => v.id === c.agent_id)
  );

  const expectedAgentIds = useMemo(() => supportedAgentIdsForMime(mimeType, capabilities), [mimeType, capabilities]);

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

  // The "analysis_done" cue must follow the findings, not the status flip. The
  // PIPELINE_PAUSED status change can land a beat before the agent finding cards
  // have rendered/revealed, so gate the sound on the findings actually being
  // present (all expected agents surfaced) and defer one paint so it plays after
  // the cards are on screen — matching "the sound indicates initial analysis
  // finished" only once the user can see the findings.
  // awaiting_decision already means the backend finished every initial agent, so
  // requiring at least one finding card present (rather than an exact count that
  // could under-count when an agent is skipped/not-applicable) is enough to know
  // the findings have surfaced — and avoids a never-fire edge case.
  const findingsSurfaced = validCompletedAgents.length > 0;

  useEffect(() => {
    const ready =
      (awaitingDecision && findingsSurfaced) || (phase === "deep" && allAgentsDone);
    if (ready && !analysisCompleteSoundedRef.current) {
      analysisCompleteSoundedRef.current = true;
      const t = setTimeout(() => playSound("analysis_done"), 420);
      return () => clearTimeout(t);
    }
  }, [awaitingDecision, findingsSurfaced, phase, allAgentsDone, playSound]);

  const hasStartedAnalysis =
    status !== "idle" ||
    isUploading ||
    validCompletedAgents.length > 0 ||
    autoStartBlocking ||
    !!wsConnectionError;

  useEffect(() => {
    if (!showLoadingOverlay) return;

    // Drop the overlay only once the initial analysis has ACTUALLY started
    // producing work — the first agent/tool/pipeline update flips status from
    // "idle"/"initiating" to "analyzing" (or a later/terminal state). Dismissing
    // on the bare WebSocket connection (analysisStreamReady) dropped the overlay
    // a beat before any agent was visibly running, leaving a dead-wait gap on the
    // analysis page. A genuinely stuck start is still bounded by
    // GlobalLoadingOverlay's EVIDENCE_MAX_DISPLAY_MS safety timer; a failed socket
    // dismisses via wsConnectionError.
    const shouldDismiss =
      (status !== "idle" && status !== "initiating") ||
      !!wsConnectionError;

    if (shouldDismiss) {
      loadingOverlayController.dismiss();
      const timer = setTimeout(() => {
        setShowLoadingOverlay(false);
      }, 800);
      return () => clearTimeout(timer);
    }
  }, [showLoadingOverlay, status, wsConnectionError]);

  useEffect(() => {
    if (showLoadingOverlay && !analysisStreamReady) {
      const text = uploadPhaseText || pipelineMessage || "Initializing workspace";
      // Use updateText() when the overlay is already visible so we don't reset
      // showTime (which would re-arm the MIN_DISPLAY guard on every pipeline message).
      // show() is only called when visibility is first established.
      if (loadingOverlayController.getState().visible) {
        loadingOverlayController.updateText(text);
      } else {
        loadingOverlayController.show(text);
      }
      const dispatchedCount = Math.min(
        Object.keys(agentUpdates).filter((k) => k !== "Arbiter").length,
        5
      );
      loadingOverlayController.updateDispatchedCount(dispatchedCount);
    }
  }, [showLoadingOverlay, uploadPhaseText, pipelineMessage, agentUpdates, analysisStreamReady]);

  return {
    isUploading,
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
    capabilities,
    handoffRecovering: autoStartBlocking || showLoadingOverlay,
  };
}
