"use client";

import { useState, useEffect, useRef, useCallback } from "react";
import { useRouter } from "next/navigation";
import { 
  getArbiterStatus, 
  getReport, 
  type ReportDTO 
} from "@/lib/api";
import { useForensicData, mapReportDtoToReport } from "@/hooks/useForensicData";
import { useSound } from "@/hooks/useSound";
import { type HistoryItem } from "@/components/ui/HistoryDrawer";
import { type AgentResult } from "@/types";

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
  const getInitial = (key: string) => typeof window !== "undefined" ? sessionStorage.getItem(key) : null;

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
  const [agentTimeline] = useState<AgentResult[]>(() => {
    try {
      const isDeep = getInitial("forensic_is_deep") === "true";
      const key = isDeep ? "forensic_deep_agents" : "forensic_initial_agents";
      const stored = getInitial(key);
      return stored ? JSON.parse(stored) : [];
    } catch { return []; }
  });
  
  const historySavedRef = useRef(false);
  const { addToHistory } = useForensicData();
  const { playSound } = useSound();
  const soundRef = useRef(playSound);

  useEffect(() => {
    setMounted(true);
    soundRef.current = playSound;
  }, [playSound]);

  // Polling Logic
  useEffect(() => {
    if (!mounted) return;
    
    const sessionId = sessionStorage.getItem("forensic_session_id");
    if (!sessionId) {
      setState("empty");
      return;
    }

    let cancelled = false;
    let timer: ReturnType<typeof setTimeout>;
    let attempts = 0;
    const MAX_ATTEMPTS = 720; // 30 minutes (720 * 2.5s) for high-fidelity Deep Video analysis
    const POLL_INTERVAL = 2500; // Slightly slower polling for better thread breathing

    async function poll() {
      if (cancelled) return;
      attempts++;
      try {
        const s = await getArbiterStatus(sessionId!);
        if (cancelled) return;

        if (s.status === "complete") {
          const res = await getReport(sessionId!);
          if (!cancelled && res.status === "complete" && res.report) {
            handleComplete(res.report);
            return;
          }
        } else if (s.status === "error") {
          setErrorMsg(s.message || "Investigation failed");
          setState("error");
          return;
        } else {
          setArbiterMsg(s.message || "Council deliberating...");
        }
      } catch (e) {
        dbg.error("Polling error", e);
      }

      if (!cancelled && attempts < MAX_ATTEMPTS) {
        timer = setTimeout(poll, POLL_INTERVAL);
      } else if (!cancelled) {
        setErrorMsg("Arbiter timed out. Session expired.");
        setState("error");
      }
    }

    const handleComplete = (rep: ReportDTO) => {
      setReport(rep);
      setState("ready");
      try {
        addToHistory(mapReportDtoToReport(rep));
      } catch (e) {
        dbg.error("History addition skipped", e);
      }
      // Delay sound slightly to ensure UI has rendered and is ready
      setTimeout(() => soundRef.current("arbiter_done"), 200);
    };

    poll();
    return () => {
      cancelled = true;
      clearTimeout(timer);
    };
  }, [mounted, addToHistory]);

  // History Persistence (Client Side Only)
  useEffect(() => {
    if (state === "ready" && report && !historySavedRef.current) {
      historySavedRef.current = true;
      const hItem: HistoryItem = {
        sessionId: report.session_id,
        fileName: sessionStorage.getItem("forensic_file_name") || "Unknown File",
        verdict: report.overall_verdict || "INCONCLUSIVE",
        timestamp: Date.now(),
        type: isDeepPhase ? "Deep" : "Initial",
        thumbnail: thumbnail || undefined,
        mime: mimeType || undefined,
      };
      
      try {
        const stored = JSON.parse(localStorage.getItem("forensic_history") || "[]") as HistoryItem[];
        const filtered = stored.filter((h) => h.sessionId !== hItem.sessionId);
        localStorage.setItem("forensic_history", JSON.stringify([hItem, ...filtered]));
      } catch (e) {
        dbg.error("LocalStorage persistence failed", e);
      }
    }
  }, [state, report, isDeepPhase, thumbnail, mimeType]);

  const handleNew = useCallback(() => {
    playSound("click");
    ["forensic_session_id", "forensic_file_name", "forensic_case_id", "forensic_thumbnail"].forEach(k => sessionStorage.removeItem(k));
    router.push("/evidence");
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
