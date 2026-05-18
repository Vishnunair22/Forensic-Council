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

function readResultPhase(sid: string | null): "initial" | "deep" {
  if (!sid) return "initial";
  const phase = storage.getItem(`forensic_result_phase:${sid}`);
  return phase === "deep" ? "deep" : "initial";
}

function loadAgentTimelineForSession(sid: string | null, isDeep: boolean): AgentUpdate[] {
  if (!sid) return [];
  const deep = storage.getItem<AgentUpdate[]>(`forensic_deep_agents:${sid}`, true);
  const initial = storage.getItem<AgentUpdate[]>(`forensic_initial_agents:${sid}`, true);
  if (isDeep && Array.isArray(deep) && deep.length) return deep;
  if (Array.isArray(initial) && initial.length) return initial;
  return [];
}

export function useResult(initialSessionId?: string) {
  const router = useRouter();

  // All storage-dependent state initialized to SSR-safe defaults.
  // Hydration from storage happens once after mount (see effect below) to
  // avoid server/client mismatch on first paint.
  const [mounted, setMounted] = useState(false);
  const [reportAlreadyReady, setReportAlreadyReady] = useState(false);
  const [state, setState] = useState<PageState>("arbiter");
  const [report, setReport] = useState<ReportDTO | null>(null);
  const [arbiterMsg, setArbiterMsg] = useState("Council deliberating on evidence...");
  const [errorMsg, setErrorMsg] = useState("");
  const [activeTab, setActiveTab] = useState<Tab>("analysis");
  const [isDeepPhase, setIsDeepPhase] = useState(false);
  const [thumbnail, setThumbnail] = useState<string | null>(null);
  const [mimeType, setMimeType] = useState<string | null>(null);
  const [pipelineStartAt, setPipelineStartAt] = useState<string | null>(null);
  const [fileName, setFileName] = useState<string | null>(null);
  const [agentTimeline, setAgentTimeline] = useState<AgentUpdate[]>([]);
  const [sessionId, setSessionId] = useState<string | null>(initialSessionId ?? null);
  const [minOverlayDone, setMinOverlayDone] = useState(false);
  const [arbiterComplete, setArbiterComplete] = useState(false);

  const historySavedRef = useRef(false);
  const { playSound } = useSound();
  const soundRef = useRef(playSound);

  // Mount + hydrate from storage (client only). Runs once.
  useEffect(() => {
    const ready = sessionOnlyStorage.getItem("fc_report_ready") === "1";
    const sid = initialSessionId ?? storage.getItem("forensic_session_id");
    const ctx = readSessionContext(sid);
    const deep = readResultPhase(sid) === "deep";

    setReportAlreadyReady(ready);
    if (sid) setSessionId(sid);
    setIsDeepPhase(deep);
    if (sid) {
      setThumbnail(storage.getItem(`forensic_thumbnail:${sid}`) ?? storage.getItem("forensic_thumbnail"));
    } else {
      setThumbnail(storage.getItem("forensic_thumbnail"));
    }
    setMimeType(ctx?.mime_type ?? storage.getItem("forensic_mime_type"));
    setPipelineStartAt(ctx?.pipeline_start ?? storage.getItem("forensic_pipeline_start"));
    setFileName(ctx?.file_name ?? storage.getItem("forensic_file_name"));
    setAgentTimeline(loadAgentTimelineForSession(sid, deep));

    if (ready) {
      setState("loading");
      setArbiterMsg("Decrypting forensic ledger...");
      setMinOverlayDone(true);
      setArbiterComplete(true);
    }

    setMounted(true);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // Transition smoothness: ensure overlay shows for at least 800ms.
  useEffect(() => {
    if (!mounted) return;
    document.body.removeAttribute("data-fc-loading");
    if (reportAlreadyReady) {
      sessionOnlyStorage.removeItem("fc_report_ready");
      return;
    }
    if (minOverlayDone) return;
    const timer = setTimeout(() => setMinOverlayDone(true), 800);
    return () => clearTimeout(timer);
  }, [mounted, sessionId, reportAlreadyReady, minOverlayDone]);

  // Sync sessionId if initialSessionId changes (e.g. dynamic route navigation)
  useEffect(() => {
    if (!mounted) return;
    if (initialSessionId && initialSessionId !== sessionId) {
      const ctx = readSessionContext(initialSessionId);
      setSessionId(initialSessionId);
      setReport(null);
      setArbiterComplete(false);
      setMinOverlayDone(false);
      historySavedRef.current = false;
      setState("arbiter");
      setArbiterMsg("Council deliberating on evidence...");
      setIsDeepPhase(readResultPhase(initialSessionId) === "deep");
      setThumbnail(
        storage.getItem(`forensic_thumbnail:${initialSessionId}`) ??
        storage.getItem("forensic_thumbnail")
      );
      setMimeType(ctx?.mime_type ?? storage.getItem("forensic_mime_type"));
      setPipelineStartAt(ctx?.pipeline_start ?? storage.getItem("forensic_pipeline_start"));
      setFileName(ctx?.file_name ?? storage.getItem("forensic_file_name"));
      setAgentTimeline(loadAgentTimelineForSession(initialSessionId, readResultPhase(initialSessionId) === "deep"));
    }
  }, [mounted, initialSessionId, sessionId]);

  const selectSession = useCallback((sid: string) => {
    storage.setItem("forensic_session_id", sid);
    const ctx = readSessionContext(sid);
    const nextIsDeep = readResultPhase(sid) === "deep";
    setSessionId(sid);
    setArbiterComplete(false);
    setMinOverlayDone(false);
    setReport(null);
    setState("arbiter");
    historySavedRef.current = false;
    setArbiterMsg("Council deliberating on evidence...");
    setIsDeepPhase(nextIsDeep);
    setThumbnail(storage.getItem(`forensic_thumbnail:${sid}`) ?? storage.getItem("forensic_thumbnail"));
    setMimeType(ctx?.mime_type ?? storage.getItem("forensic_mime_type"));
    setPipelineStartAt(ctx?.pipeline_start ?? storage.getItem("forensic_pipeline_start"));
    setFileName(ctx?.file_name ?? storage.getItem("forensic_file_name"));
    setAgentTimeline(loadAgentTimelineForSession(sid, nextIsDeep));
  }, []);

  useEffect(() => {
    soundRef.current = playSound;
  }, [playSound]);

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

  const finalReportData = useMemo(() => {
    if (!reportQueryData) return null;
    const asAny = reportQueryData as unknown as Record<string, unknown>;
    if (isReportDTO(asAny)) return reportQueryData as unknown as ReportDTO;
    if (asAny.status === "complete" && asAny.report) {
      const reportValue = asAny.report as Record<string, unknown>;
      if (isReportDTO(reportValue)) return reportValue as unknown as ReportDTO;
    }
    return null;
  }, [reportQueryData]);

  useEffect(() => {
    if (!finalReportData) return;
    setArbiterComplete(true);
    setReport(finalReportData);
    setState("ready");
    const id = setTimeout(() => {
      soundRef.current("arbiter_done");
      soundRef.current("result_reveal");
    }, 200);
    return () => clearTimeout(id);
  }, [finalReportData]);

  useEffect(() => {
    if (reportQueryError && arbiterComplete) {
      setErrorMsg("Failed to retrieve report. Please refresh.");
      setState("error");
    }
  }, [reportQueryError, arbiterComplete]);

  // ── Arbiter status polling ───────────────────────────────────────────────────
  useEffect(() => {
    if (!mounted) return;

    if (!sessionId) {
      setState("empty");
      return;
    }

    if (arbiterComplete) return; // report already confirmed complete; skip polling

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
  }, [mounted, sessionId, arbiterComplete]);

  // History Persistence (Client Side Only)
  // F-H-10: mark historySavedRef true only AFTER the storage write succeeds,
  // so a thrown setItem (quota / JSON corruption) doesn't silently mark
  // history as saved without actually persisting.
  useEffect(() => {
    if (state === "ready" && report && !historySavedRef.current) {
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
        // P-H-2: cap client-side history at 50 entries to prevent
        // unbounded localStorage growth and limit PII retention. Older
        // entries are dropped FIFO; the most recent investigations stay
        // visible in the History panel.
        const HISTORY_MAX = 50;
        const next = [hItem, ...filtered].slice(0, HISTORY_MAX);
        storage.setItem("forensic_history", next, true);
        historySavedRef.current = true;
      } catch (e: unknown) {
        dbg.error("SessionStorage persistence failed", e);
      }
    }
  }, [state, report, isDeepPhase, thumbnail, mimeType, sessionId, fileName]);

  const _resetAndNavigate = useCallback((path: string) => {
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
    router.push(path);
  }, [playSound, router]);

  const handleNew = useCallback(() => _resetAndNavigate("/?upload=1"), [_resetAndNavigate]);
  const handleHome = useCallback(() => _resetAndNavigate("/#hero"), [_resetAndNavigate]);

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

function isReportDTO(value: Record<string, unknown> | null | undefined): boolean {
  return (
    !!value &&
    typeof value.report_id === "string" &&
    typeof value.session_id === "string" &&
    typeof value.overall_verdict === "string"
  );
}
