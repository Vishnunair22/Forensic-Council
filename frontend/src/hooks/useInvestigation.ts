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
  type HITLCheckpoint,
  type ArbiterStatusResponse,
  type HITLDecision
} from "@/lib/api";
import { toast } from "./use-toast";
import { AGENTS as AGENTS_DATA, ALLOWED_MIME_TYPES, INVESTIGATION_REQUEST_TIMEOUT_MS } from "@/lib/constants";
import { __pendingFileStore } from "@/lib/pendingFileStore";
import { type SoundType } from "@/hooks/useSound";
import { type AgentUpdate } from "@/components/evidence/AgentProgressDisplay";


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
  let pollInterval = 1000;
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
          const res = await withTimeout(getReport(sessionId, 30_000), 30_000);
          if (res.status === "complete" && res.report) return true;
        } catch {
          /* in progress */
        }
      }
    } catch (e) {
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
    const stored = sessionStorage.getItem("forensic_investigator_id");
    const validIdPattern = /^REQ-\d{5,10}$/;
    if (stored && validIdPattern.test(stored)) return stored;
    const fresh = "REQ-" + (Math.floor(Math.random() * 900000) + 100000);
    sessionStorage.setItem("forensic_investigator_id", fresh);
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
  const [showArbiterOverlay] = useState(false);
  const analysisCompleteSoundedRef = useRef(false);
  const autoStartFiredRef = useRef(false);
  const investigationInFlightRef = useRef(false);

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
  } = useSimulation({
    playSound,
    onComplete: () => {},
  });

  useLayoutEffect(() => {
    try {
      setAutoStartBlocking(sessionStorage.getItem("forensic_auto_start") === "true");
      if (sessionStorage.getItem("fc_show_loading") === "true") {
        setShowLoadingOverlay(true);
      }
    } catch {
      setAutoStartBlocking(false);
    }
  }, []);

  const authReadyRef = useRef<Promise<void>>(
    typeof document !== "undefined" &&
      (document.cookie.includes("access_token") ||
        sessionStorage.getItem("forensic_auth_ok") === "1")
      ? Promise.resolve()
      : autoLoginAsInvestigator().then(() => {}).catch(() => {})
  );

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
      setIsUploading(true);
      setValidationError(null);
      setPhase("initial");
      setAnalysisStreamReady(false);
      setAutoStartBlocking(false);
      setUploadPhaseText("Uploading evidence to secure pipeline…");

      const investigatorId = investigatorIdRef.current;
      const caseId = sessionStorage.getItem("forensic_case_id") || "CASE-" + Date.now();

      setShowLoadingOverlay(true);
      sessionStorage.setItem("fc_show_loading", "true");

      await authReadyRef.current;

      let sessionIdToUse: string | undefined;
      try {
        const investigationRes = await startInvestigation(targetFile, caseId, investigatorId);
        sessionIdToUse = investigationRes.session_id;
      } catch (err) {
        if (err instanceof DuplicateInvestigationError) {
          const sid = err.existingSessionId;
          sessionStorage.setItem("forensic_session_id", sid);
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
      }

      if (!sessionIdToUse) {
        investigationInFlightRef.current = false;
        return;
      }

      sessionStorage.setItem("forensic_session_id", sessionIdToUse);
      sessionStorage.setItem("forensic_file_name", targetFile.name);
      sessionStorage.setItem("forensic_case_id", caseId);
      sessionStorage.setItem("forensic_investigator_id", investigatorId);
      sessionStorage.setItem("forensic_mime_type", targetFile.type);

      startSimulation();
      setIsUploading(false);
      setUploadPhaseText("Connecting to analysis stream…");

      connectWebSocket(sessionIdToUse)
        .then(() => {
          setAnalysisStreamReady(true);
          setUploadPhaseText("Agents dispatching…");
        })
        .catch((wsErr: unknown) => {
          const wsErrMsg = wsErr instanceof Error ? wsErr.message : "Failed to connect to stream";
          setValidationError(wsErrMsg);
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
      if (sessionStorage.getItem("forensic_auto_start") === "true") {
        sessionStorage.removeItem("forensic_auto_start");
        setAutoStartBlocking(false);
        triggerAnalysis(pending);
      }
    }
  }, [triggerAnalysis]);

  const handleFile = (f: File) => {
    if (f.size > 50 * 1024 * 1024) {
      setValidationError("File must be under 50MB");
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
    if (!hitlCheckpoint) return;
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
    sessionStorage.setItem("forensic_is_deep", "false");
    sessionStorage.setItem("forensic_initial_agents", JSON.stringify(completedAgents));
    setIsNavigating(true);
    try {
      await resumeInvestigation(false);
      router.push("/result", { scroll: true });
    } catch {
      setIsNavigating(false);
    }
  }, [playSound, resumeInvestigation, router, isNavigating, completedAgents]);

  const handleDeepAnalysis = useCallback(async () => {
    playSound("think");
    sessionStorage.setItem("forensic_is_deep", "true");
    analysisCompleteSoundedRef.current = false;
    setPhase("deep");
    try {
      await resumeInvestigation(true);
    } catch {
      playSound("error");
    }
  }, [playSound, resumeInvestigation]);

  const handleNewUpload = useCallback(() => {
    playSound("click");
    setFile(null);
    setPhase("initial");
    resetSimulation();
  }, [resetSimulation, playSound]);

  const handleViewResults = useCallback(async () => {
    if (isNavigating) return;
    playSound("arbiter_start");
    sessionStorage.setItem("forensic_deep_agents", JSON.stringify(completedAgents));
    setIsNavigating(true);
    const sid = sessionStorage.getItem("forensic_session_id");
    try {
      if (sid) await waitForFinalReport(sid, setArbiterLiveText, 120_000);
      router.push("/result", { scroll: true });
    } finally {
      setIsNavigating(false);
    }
  }, [playSound, router, isNavigating, completedAgents]);

  const validAgentsData = AGENTS_DATA.filter((a) => a.name !== "Council Arbiter");
  const validCompletedAgents = completedAgents.filter((c: AgentUpdate) =>
    validAgentsData.some((v) => v.id === c.agent_id)
  );
  
  const awaitingDecision = status === "awaiting_decision";
  const allAgentsDone = phase === "deep" 
    ? status === "complete" 
    : validCompletedAgents.length >= validAgentsData.length;

  useEffect(() => {
    if (awaitingDecision && !analysisCompleteSoundedRef.current) {
      analysisCompleteSoundedRef.current = true;
      playSound("analysis_done");
    }
  }, [awaitingDecision, playSound]);

  const hasStartedAnalysis = status !== "idle" || isUploading || validCompletedAgents.length > 0;
  const showUploadForm = !autoStartBlocking && status === "idle" && !isUploading;

  useEffect(() => {
    if (showLoadingOverlay && analysisStreamReady) {
      setShowLoadingOverlay(false);
      sessionStorage.removeItem("fc_show_loading");
    }
  }, [showLoadingOverlay, analysisStreamReady]);

  return {
    file, setFile,
    isDragging, setIsDragging,
    validationError, setValidationError,
    isUploading,
    uploadPhaseText,
    showLoadingOverlay, setShowLoadingOverlay,
    analysisStreamReady,
    arbiterLiveText,
    autoStartBlocking, setAutoStartBlocking,
    phase,
    isSubmittingHITL,
    isNavigating,
    showArbiterOverlay,
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
  };
}
