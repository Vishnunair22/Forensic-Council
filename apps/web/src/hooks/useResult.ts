"use client";

import { useState, useEffect, useRef, useCallback } from "react";
import { useRouter } from "next/navigation";
import { useQuery } from "@tanstack/react-query";
import {
  getArbiterStatus,
  getReport,
  type ReportDTO
} from "@/lib/api";
import { ARBITER_POLL_INTERVAL_MS, ARBITER_POLL_MAX_ATTEMPTS } from "@/lib/constants";
import { useForensicData, mapReportDtoToReport } from "@/hooks/useForensicData";
import { useSound } from "@/hooks/useSound";
import { type HistoryItem } from "@/lib/types";
import type { AgentUpdate } from "@/components/evidence/AgentProgressDisplay";
import { storage, persistentStorage } from "@/lib/storage";

export type Tab = "analysis" | "history";
export type PageState = "arbiter" | "ready" | "error" | "empty";

const isDev = process.env.NODE_ENV !== "production";
const dbg = { error: isDev ? console.error.bind(console) : () => {} };

/**
 * Hook for managing the result page state and polling logic.
 * Optimized for performance and flicker-free transitions.
 */
export function useResult() {
  const router = useRouter();
  
  // Initialize states from sessionStorage immediately if in browser to avoid flickers
  const getInitial = (key: string) => persistentStorage.getItem<string>(key, false, null);

  const [mounted, setMounted] = useState(false);
  const [state, setState] = useState<PageState>("arbiter");
  const [report, setReport] = useState<ReportDTO | null>(null);
  const [arbiterMsg, setArbiterMsg] = useState("");
  const [errorMsg, setErrorMsg] = useState("");
  const [activeTab, setActiveTab] = useState<Tab>("analysis");
  
  // Investigation Meta
  const [isDeepPhase] = useState(() => getInitial("forensic_is_deep") === "true");
  const [thumbnail] = useState(() => getInitial("forensic_thumbnail"));
  const [mimeType] = useState(() => getInitial("forensic_mime_type"));
  const [pipelineStartAt] = useState(() => getInitial("forensic_pipeline_start"));
  const [agentTimeline] = useState<AgentUpdate[]>(() => {
    try {
      const isDeep = getInitial("forensic_is_deep") === "true";
      const key = isDeep ? "forensic_deep_agents" : "forensic_initial_agents";
      const stored = getInitial(key);
      if (stored) return JSON.parse(stored);
      if (isDeep) {
        const fallback = getInitial("forensic_initial_agents");
        if (fallback) return JSON.parse(fallback);
      }
      return [];
    } catch { return []; }
  });
  
  // Session ID — read once when mounted (stable for the lifetime of the result page)
  const [sessionId] = useState<string | null>(() =>
    typeof window !== "undefined"
      ? storage.getItem<string>("forensic_session_id", false, null)
      : null
  );

  // Set to true when the arbiter status polling confirms the investigation is done
  const [arbiterComplete, setArbiterComplete] = useState(false);

  const historySavedRef = useRef(false);
  const { addToHistory } = useForensicData();
  const { playSound } = useSound();
  const soundRef = useRef(playSound);

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
    staleTime: Infinity,      // A signed forensic report never goes stale
    retry: 2,
    select: (res) => (res.status === "complete" ? res.report ?? null : null),
  });

  // React to the report query resolving
  useEffect(() => {
    if (!reportQueryData) return;
    setReport(reportQueryData);
    setState("ready");
    try {
      addToHistory(mapReportDtoToReport(reportQueryData));
    } catch (e: unknown) {
      dbg.error("History addition skipped", e);
    }
    setTimeout(() => {
      soundRef.current("arbiter_done");
      soundRef.current("result_reveal");
    }, 200);
  }, [reportQueryData, addToHistory]);

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
        fileName: storage.getItem<string>("forensic_file_name", false, "Unknown File") || "Unknown File",
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
    playSound("click");
    ["forensic_session_id", "forensic_file_name", "forensic_case_id", "forensic_thumbnail", "forensic_is_deep", "forensic_initial_agents", "forensic_deep_agents"].forEach(k => storage.removeItem(k));
    // Route to home and trigger the upload modal opening via an event
    router.push("/");
    setTimeout(() => {
      window.dispatchEvent(new Event("fc:open-upload"));
    }, 500);
  }, [playSound, router]);

  const handleHome = useCallback(() => {
    playSound("click");
    router.push("/");
  }, [playSound, router]);

  const handleExport = useCallback(() => {
    if (!report) return;
    const blob = new Blob([JSON.stringify(report, null, 2)], { type: "application/json" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = `forensic-report-${report.report_id.slice(0, 8)}.json`;
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
    mounted,
    handleNew,
    handleHome,
    handleExport,
  };
}
