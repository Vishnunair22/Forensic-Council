"use client";

import { useState, useEffect, useRef, useCallback, useMemo } from "react";
import { useRouter } from "next/navigation";
import { useQuery } from "@tanstack/react-query";
import {
  getArbiterStatus,
  getReport,
  type ReportDTO,
  type ReportResponse,
  dbg
} from "@/lib/api";
import { ARBITER_POLL_INTERVAL_MS, ARBITER_POLL_MAX_ATTEMPTS } from "@/lib/constants";
import { useSound } from "@/hooks/useSound";
import { type HistoryItem } from "@/lib/types";
import type { AgentUpdate } from "@/components/evidence/AgentProgressDisplay";
import { storage, sessionOnlyStorage } from "@/lib/storage";

export type Tab = "analysis" | "history";
export type PageState = "loading" | "arbiter" | "ready" | "error" | "empty";

interface SessionContext {
  session_id: string;
  file_name?: string;
  case_id?: string;
  investigator_id?: string;
  mime_type?: string;
  pipeline_start?: string;
}

function readSessionContext(sid: string | null): SessionContext | null {
  if (!sid) return null;
  return storage.getItem<SessionContext>(`forensic_investigation_ctx:${sid}`, true) ?? null;
}

function loadAgentTimelineForSession(sid: string | null, isDeep: boolean): AgentUpdate[] {
  if (!sid) return [];
  const deep = storage.getItem<AgentUpdate[]>(`forensic_deep_agents:${sid}`, true);
  const initial = storage.getItem<AgentUpdate[]>(`forensic_initial_agents:${sid}`, true);
  if (isDeep && Array.isArray(deep) && deep.length) return deep;
  if (Array.isArray(initial) && initial.length) return initial;
  return [];
}

/**
 * Hook for managing the result page state and polling logic.
 * Optimized for performance and flicker-free transitions.
 */
export function useResult(initialSessionId?: string) {
  const router = useRouter();

  const getInitialSid = () => initialSessionId ?? (typeof window !== "undefined" ? storage.getItem("forensic_session_id") : null);

  const initialSid = getInitialSid();
  const initialCtx = readSessionContext(initialSid);

  const [mounted, setMounted] = useState(false);
  const [reportAlreadyReady] = useState(() =>
    typeof window !== "undefined" && sessionOnlyStorage.getItem("fc_report_ready") === "1"
  );
  const [state, setState] = useState<PageState>(() => reportAlreadyReady ? "loading" : "arbiter");
  const [report, setReport] = useState<ReportDTO | null>(null);
  const [arbiterMsg, setArbiterMsg] = useState(() =>
    reportAlreadyReady ? "Decrypting forensic ledger..." : "Council deliberating on evidence..."
  );
  const [errorMsg, setErrorMsg] = useState("");
  const [activeTab, setActiveTab] = useState<Tab>("analysis");

  // Investigation Meta — initialized from session-scoped keys (falls back to global for backward compat)
  const initialIsDeep = storage.getItem("forensic_is_deep") === "true";
  const [isDeepPhase, setIsDeepPhase] = useState(initialIsDeep);
  const [thumbnail, setThumbnail] = useState<string | null>(() => {
    if (initialSid) return storage.getItem(`forensic_thumbnail:${initialSid}`) ?? storage.getItem("forensic_thumbnail");
    return storage.getItem("forensic_thumbnail");
  });
  const [mimeType, setMimeType] = useState<string | null>(() =>
    initialCtx?.mime_type ?? storage.getItem("forensic_mime_type")
  );
  const [pipelineStartAt, setPipelineStartAt] = useState<string | null>(() =>
    initialCtx?.pipeline_start ?? storage.getItem("forensic_pipeline_start")
  );
  const [fileName, setFileName] = useState<string | null>(() =>
    initialCtx?.file_name ?? storage.getItem("forensic_file_name")
  );
  const [agentTimeline, setAgentTimeline] = useState<AgentUpdate[]>(() =>
    loadAgentTimelineForSession(initialSid, initialIsDeep)
  );

  const [sessionId, setSessionId] = useState<string | null>(() => initialSid);

  // Transition smoothness: ensure overlay shows for at least 800ms.
  // Skipped if report is already ready (fc_report_ready was set by handleAcceptAnalysis).
  const [minOverlayDone, setMinOverlayDone] = useState(reportAlreadyReady);
  useEffect(() => {
    // Remove the CSS bridge overlay — React overlay takes over now.
    document.body.removeAttribute("data-fc-loading");
    if (reportAlreadyReady) {
      // Clear the flag so refresh doesn't skip polling incorrectly.
      sessionOnlyStorage.removeItem("fc_report_ready");
      return;
    }
    const timer = setTimeout(() => setMinOverlayDone(true), 800);
    return () => clearTimeout(timer);
  }, [sessionId, reportAlreadyReady]); // reset on session change

  // Sync sessionId if initialSessionId changes (e.g. dynamic route navigation)
  useEffect(() => {
    if (initialSessionId && initialSessionId !== sessionId) {
      const ctx = readSessionContext(initialSessionId);
      setSessionId(initialSessionId);
      setReport(null);
      setArbiterComplete(false);
      setMinOverlayDone(false);
      setState("arbiter");
      setArbiterMsg("Council deliberating on evidence...");
      setIsDeepPhase(storage.getItem("forensic_is_deep") === "true");
      setThumbnail(
        storage.getItem(`forensic_thumbnail:${initialSessionId}`) ??
        storage.getItem("forensic_thumbnail")
      );
      setMimeType(ctx?.mime_type ?? storage.getItem("forensic_mime_type"));
      setPipelineStartAt(ctx?.pipeline_start ?? storage.getItem("forensic_pipeline_start"));
      setFileName(ctx?.file_name ?? storage.getItem("forensic_file_name"));
      setAgentTimeline(loadAgentTimelineForSession(initialSessionId, storage.getItem("forensic_is_deep") === "true"));
    }
  }, [initialSessionId, sessionId]);

  const selectSession = useCallback((sid: string) => {
    storage.setItem("forensic_session_id", sid);
    const ctx = readSessionContext(sid);
    const nextIsDeep = storage.getItem("forensic_is_deep") === "true";
    setSessionId(sid);
    setArbiterComplete(false);
    setMinOverlayDone(false);
    setReport(null);
    setState("arbiter");
    setArbiterMsg("Council deliberating on evidence...");
    setIsDeepPhase(nextIsDeep);
    setThumbnail(storage.getItem(`forensic_thumbnail:${sid}`) ?? storage.getItem("forensic_thumbnail"));
    setMimeType(ctx?.mime_type ?? storage.getItem("forensic_mime_type"));
    setPipelineStartAt(ctx?.pipeline_start ?? storage.getItem("forensic_pipeline_start"));
    setFileName(ctx?.file_name ?? storage.getItem("forensic_file_name"));
    setAgentTimeline(loadAgentTimelineForSession(sid, nextIsDeep));
  }, []);

  // Set to true when the arbiter status polling confirms the investigation is done
  const [arbiterComplete, setArbiterComplete] = useState(reportAlreadyReady);

  const historySavedRef = useRef(false);
  const { playSound } = useSound();
  const soundRef = useRef(playSound);

  // Lifecycle
  useEffect(() => {
    setMounted(true);
    soundRef.current = playSound;
  }, [playSound]);

  // ── Report fetch via TanStack Query ─────────────────────────────────────────
  // Probe the report endpoint as soon as the result page mounts. Arbiter status
  // is useful progress text, but the signed report is the real readiness signal.
  const {
    data: reportQueryData,
    error: reportQueryError,
  } = useQuery({
    queryKey: ["report", sessionId],
    queryFn: () => {
      if (!sessionId) throw new Error("Missing session ID");
      return getReport(sessionId);
    },
    enabled: !!sessionId && minOverlayDone && arbiterComplete,
    staleTime: 60_000, 
    retry: 3,
    refetchInterval: (query) => {
      const data = query.state.data as ReportResponse | undefined;
      if (data && data.status === "in_progress") return 2000;
      return false;
    },
  });

  // Derived state to check if we actually have the report data
  const finalReportData = useMemo(() => {
    if (!reportQueryData) return null;
    // The API returns ReportDTO directly when ready, or {status:"in_progress"} as 202.
    // ReportDTO has report_id; the in-progress wrapper has status = "in_progress".
    const asAny = reportQueryData as unknown as Record<string, unknown>;
    if (asAny.report_id) return reportQueryData as unknown as ReportDTO;
    if (asAny.status === "complete" && asAny.report) return asAny.report as ReportDTO;
    return null;
  }, [reportQueryData]);

  // React to the report query resolving
  useEffect(() => {
    if (!finalReportData) return;
    setArbiterComplete(true);
    setReport(finalReportData);
    setState("ready");
    setTimeout(() => {
      soundRef.current("arbiter_done");
      soundRef.current("result_reveal");
    }, 200);
  }, [finalReportData]); // addToHistory removed — effect #2 owns all history writes

  useEffect(() => {
    if (reportQueryError && arbiterComplete) {
      setErrorMsg("Failed to retrieve report. Please refresh.");
      setState("error");
    }
  }, [reportQueryError, arbiterComplete]);

  // ── Arbiter status polling ───────────────────────────────────────────────────
  // Polls getArbiterStatus until complete/error, then enables the report query.
  useEffect(() => {
    if (!mounted) return;

    if (!sessionId) {
      setState("empty");
      return;
    }

    let cancelled = false;
    let timer: ReturnType<typeof setTimeout> | undefined;
    let attempts = 0;
    let pollInterval = ARBITER_POLL_INTERVAL_MS;

    const activeSessionId = sessionId;

    async function poll() {
      if (cancelled) return;

      try {
        const s = await getArbiterStatus(activeSessionId);
        if (cancelled) return;

        if (s.status === "complete") {
          setArbiterComplete(true);
          setArbiterMsg("Decrypting forensic ledger...");
          setState("loading"); 
          return;
        } else if (s.status === "error") {
          setErrorMsg(s.message || "Investigation failed");
          setState("error");
          return;
        } else {
          setArbiterMsg(s.message || "Council deliberating...");
        }
      } catch (e: unknown) {
        if (cancelled) return;
        dbg.error("Polling error", e);
      }

      attempts++;
      if (!cancelled && attempts < ARBITER_POLL_MAX_ATTEMPTS) {
        timer = setTimeout(poll, pollInterval);
        pollInterval = Math.min(pollInterval * 1.3, 3000);
      } else if (!cancelled) {
        setErrorMsg("Arbiter timed out. Session expired.");
        setState("error");
      }
    }

    poll();
    return () => {
      cancelled = true;
      if (timer) clearTimeout(timer);
    };
  }, [mounted, sessionId]);

  // History Persistence (Client Side Only)
  useEffect(() => {
    if (state === "ready" && report && !historySavedRef.current) {
      historySavedRef.current = true;
      const ctx = readSessionContext(sessionId);
      const hItem: HistoryItem = {
        sessionId: report.session_id,
        fileName: ctx?.file_name ?? fileName ?? "Unknown File",
        verdict: report.overall_verdict || "INCONCLUSIVE",
        timestamp: Date.now(),
        type: isDeepPhase ? "Deep" : "Initial",
        thumbnail: thumbnail || undefined,
        mime: mimeType || undefined,
      };

      try {
        const stored = storage.getItem<HistoryItem[]>("forensic_history", true, []);
        const filtered = (stored ?? []).filter((h) => !(h.sessionId === hItem.sessionId && h.type === hItem.type));
        storage.setItem("forensic_history", [hItem, ...filtered], true);
      } catch (e: unknown) {
        dbg.error("SessionStorage persistence failed", e);
      }
    }
  }, [state, report, isDeepPhase, thumbnail, mimeType, sessionId, fileName]);

  const handleNew = useCallback(() => {
    playSound("reset");
    const savedHistory = (() => {
      try {
        return storage.getItem<HistoryItem[]>("forensic_history", true, []) ?? [];
      } catch { return [] as HistoryItem[]; }
    })();
    storage.clearAllForensicKeys();
    sessionOnlyStorage.clearAllForensicKeys();
    if (savedHistory.length > 0) {
      storage.setItem("forensic_history", savedHistory, true);
    }
    document.cookie = "forensic_session_id=; path=/; max-age=0; SameSite=Lax";

    window.dispatchEvent(new Event("fc:reset-home"));
    router.push("/?upload=1");
  }, [playSound, router]);

  const handleHome = useCallback(() => {
    playSound("reset");
    const savedHistory = (() => {
      try {
        return storage.getItem<HistoryItem[]>("forensic_history", true, []) ?? [];
      } catch { return [] as HistoryItem[]; }
    })();
    storage.clearAllForensicKeys();
    sessionOnlyStorage.clearAllForensicKeys();
    if (savedHistory.length > 0) {
      storage.setItem("forensic_history", savedHistory, true);
    }
    document.cookie = "forensic_session_id=; path=/; max-age=0; SameSite=Lax";

    window.dispatchEvent(new Event("fc:reset-home"));
    router.push("/#hero");
  }, [playSound, router]);

  const handleExport = useCallback(() => {
    if (!report) return;
    const blob = new Blob([JSON.stringify(report, null, 2)], { type: "application/json" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = `forensic-report-${(report.report_id ?? "unknown").slice(0, 8)}.json`;
    a.click();
    URL.revokeObjectURL(url);
  }, [report]);

  return {
    state,
    arbiterComplete,
    report,
    arbiterMsg,
    errorMsg,
    activeTab,
    setActiveTab,
    isDeepPhase,
    thumbnail,
    mimeType,
    fileName,
    agentTimeline,
    pipelineStartAt,
    sessionId,
    mounted,
    handleNew,
    handleHome,
    handleExport,
    selectSession,
  };
}
