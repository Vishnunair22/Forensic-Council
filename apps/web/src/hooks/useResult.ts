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

/**
 * Hook for managing the result page state and polling logic.
 * Optimized for performance and flicker-free transitions.
 */
export function useResult(initialSessionId?: string) {
  const router = useRouter();

  // Initialize states from sessionStorage immediately if in browser to avoid flickers
  const getInitial = (key: string) => storage.getItem(key);

  const [mounted, setMounted] = useState(false);
  const [state, setState] = useState<PageState>("arbiter");
  const [report, setReport] = useState<ReportDTO | null>(null);
  const [arbiterMsg, setArbiterMsg] = useState("Council deliberating on evidence...");
  const [errorMsg, setErrorMsg] = useState("");
  const [activeTab, setActiveTab] = useState<Tab>("analysis");

  // Investigation Meta
  const [isDeepPhase, setIsDeepPhase] = useState(() => getInitial("forensic_is_deep") === "true");
  const [thumbnail, setThumbnail] = useState(() => getInitial("forensic_thumbnail"));
  const [mimeType, setMimeType] = useState(() => getInitial("forensic_mime_type"));
  const [pipelineStartAt, setPipelineStartAt] = useState(() => getInitial("forensic_pipeline_start"));
  const [agentTimeline] = useState<AgentUpdate[]>(() => {
    try {
      const sid = typeof window !== "undefined" ? storage.getItem("forensic_session_id") : null;
      const isDeep = getInitial("forensic_is_deep") === "true";
      
      // Try scoped keys first (new pattern)
      if (sid) {
        const scopedKey = isDeep ? `forensic_deep_agents:${sid}` : `forensic_initial_agents:${sid}`;
        const scopedData = storage.getItem<AgentUpdate[]>(scopedKey, true);
        if (scopedData && Array.isArray(scopedData)) return scopedData;

        // Scoped fallback: if deep, try scoped initial agents
        if (isDeep) {
          const scopedFallback = storage.getItem<AgentUpdate[]>(`forensic_initial_agents:${sid}`, true);
          if (scopedFallback && Array.isArray(scopedFallback)) return scopedFallback;
        }
      }

      // Fallback to legacy non-scoped keys
      const key = isDeep ? "forensic_deep_agents" : "forensic_initial_agents";
      const stored = storage.getItem<AgentUpdate[]>(key, true);
      if (stored && Array.isArray(stored)) return stored;
      
      if (isDeep) {
        const fallback = storage.getItem<AgentUpdate[]>("forensic_initial_agents", true);
        if (fallback && Array.isArray(fallback)) return fallback;
      }
      return [];
    } catch { return []; }
  });

  // Session ID
  const [sessionId, setSessionId] = useState<string | null>(() =>
    initialSessionId ?? (typeof window !== "undefined"
      ? storage.getItem("forensic_session_id")
      : null)
  );

  // Sync sessionId if initialSessionId changes (e.g. dynamic route navigation)
  useEffect(() => {
    if (initialSessionId && initialSessionId !== sessionId) {
      setSessionId(initialSessionId);
      setReport(null);
      setArbiterComplete(false);
      setState("arbiter");
      setArbiterMsg("Council deliberating on evidence...");
      
      // Also sync metadata
      setIsDeepPhase(getInitial("forensic_is_deep") === "true");
      setThumbnail(getInitial("forensic_thumbnail"));
      setMimeType(getInitial("forensic_mime_type"));
      setPipelineStartAt(getInitial("forensic_pipeline_start"));
    }
  }, [initialSessionId, sessionId]);

  const selectSession = useCallback((sid: string) => {
    storage.setItem("forensic_session_id", sid);
    setSessionId(sid);
    setArbiterComplete(false);
    setReport(null);
    setState("arbiter");
    setArbiterMsg("Council deliberating on evidence...");
  }, []);

  // Set to true when the arbiter status polling confirms the investigation is done
  const [arbiterComplete, setArbiterComplete] = useState(false);

  const historySavedRef = useRef(false);
  const { playSound } = useSound();
  const soundRef = useRef(playSound);

  // Lifecycle
  useEffect(() => {
    setMounted(true);
    soundRef.current = playSound;
  }, [playSound]);

  // ── Report fetch via TanStack Query ─────────────────────────────────────────
  // Enabled only once the arbiter confirms completion. Results are cached by
  // sessionId so navigating back to this page never re-fetches the same report.
  const {
    data: reportQueryData,
    error: reportQueryError,
  } = useQuery({
    queryKey: ["report", sessionId],
    queryFn: () => {
      if (!sessionId) throw new Error("Missing session ID");
      return getReport(sessionId);
    },
    enabled: !!sessionId && arbiterComplete,
    staleTime: 60_000, // Allow some stale time but not Infinity until we are sure it is done
    retry: 3,
    refetchInterval: (query) => {
      const data = query.state.data as ReportResponse | undefined;
      if (data && data.status === "in_progress") return 2000;
      return false;
    },
  });

  // Derived state to check if we actually have the report data
  const finalReportData = useMemo(() => {
    if (reportQueryData && "status" in reportQueryData && reportQueryData.status === "complete") {
      return reportQueryData.report;
    }
    return null;
  }, [reportQueryData]);

  // React to the report query resolving
  useEffect(() => {
    if (!finalReportData) return;
    setReport(finalReportData);
    setState("ready");
    setTimeout(() => {
      soundRef.current("arbiter_done");
      soundRef.current("result_reveal");
    }, 200);
  }, [finalReportData]); // addToHistory removed — effect #2 owns all history writes

  useEffect(() => {
    if (reportQueryError) {
      setErrorMsg("Failed to retrieve report. Please refresh.");
      setState("error");
    }
  }, [reportQueryError]);

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

      attempts++;
      try {
        const s = await getArbiterStatus(activeSessionId);
        if (cancelled) return;

        if (s.status === "complete") {
          // Hand off to the useQuery above — it will fetch and cache the report
          setArbiterComplete(true);
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
      const hItem: HistoryItem = {
        sessionId: report.session_id,
        fileName: storage.getItem("forensic_file_name") || "Unknown File",
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
  }, [state, report, isDeepPhase, thumbnail, mimeType]);

  const handleNew = useCallback(() => {
    playSound("reset");
    storage.clearAllForensicKeys();
    sessionOnlyStorage.clearAllForensicKeys();

    window.dispatchEvent(new Event("fc:reset-home"));
    // Route to home with upload param which HeroAuthActions handles
    router.push("/?upload=1");
  }, [playSound, router]);

  const handleHome = useCallback(() => {
    playSound("reset");
    storage.clearAllForensicKeys();
    sessionOnlyStorage.clearAllForensicKeys();

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
    report,
    arbiterMsg,
    errorMsg,
    activeTab,
    setActiveTab,
    isDeepPhase,
    thumbnail,
    mimeType,
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
