"use client";

import { useState, useEffect, useRef, useCallback, useMemo } from "react";
import { useRouter } from "next/navigation";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import {
  getArbiterStatus,
  getReport,
  type ReportDTO,
  type ReportResponse,
  dbg
} from "@/lib/api";
import { ARBITER_POLL_INTERVAL_MS, ARBITER_POLL_MAX_ATTEMPTS, UI_STRINGS } from "@/lib/constants";
import { useSound } from "@/hooks/useSound";
import { type HistoryItem } from "@/lib/types";
import type { AgentUpdate } from "@/components/evidence/types";
import { storage, sessionOnlyStorage } from "@/lib/storage";
import { STORAGE_KEYS } from "@/lib/storageKeys";

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
  return storage.getItem<SessionContext>(`${STORAGE_KEYS.INVESTIGATION_CTX}:${sid}`, true) ?? null;
}

function readResultPhase(sid: string | null): "initial" | "deep" {
  if (!sid) return "initial";
  const phase = storage.getItem(`${STORAGE_KEYS.RESULT_PHASE}:${sid}`);
  return phase === "deep" ? "deep" : "initial";
}

function loadAgentTimelineForSession(sid: string | null, isDeep: boolean): AgentUpdate[] {
  if (!sid) return [];
  const deep = storage.getItem<AgentUpdate[]>(`${STORAGE_KEYS.DEEP_AGENTS}:${sid}`, true);
  const initial = storage.getItem<AgentUpdate[]>(`${STORAGE_KEYS.INITIAL_AGENTS}:${sid}`, true);
  // When deep phase is active, ONLY return deep agents. Never fall back to initial agents
  // because that would cause initial findings to show as "deep analysis" findings.
  if (isDeep) {
    return Array.isArray(deep) && deep.length ? deep : [];
  }
  if (Array.isArray(initial) && initial.length) return initial;
  return [];
}

export function useResult(initialSessionId?: string) {
  const router = useRouter();
  const queryClient = useQueryClient();

  // All storage-dependent state initialized to SSR-safe defaults.
  // Hydration from storage happens once after mount (see effect below) to
  // avoid server/client mismatch on first paint.
  const [mounted, setMounted] = useState(false);
  const [reportAlreadyReady, setReportAlreadyReady] = useState(false);
  const [state, setState] = useState<PageState>(() => {
    if (typeof window === "undefined") return "arbiter";
    return sessionOnlyStorage.getItem(STORAGE_KEYS.FC_REPORT_READY) === "1"
      ? "ready"
      : "arbiter";
  });
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
  const [minOverlayDone, setMinOverlayDone] = useState(() => {
    if (typeof window === "undefined") return false;
    return sessionOnlyStorage.getItem(STORAGE_KEYS.FC_REPORT_READY) === "1";
  });
  const [arbiterComplete, setArbiterComplete] = useState(() => {
    if (typeof window === "undefined") return false;
    return sessionOnlyStorage.getItem(STORAGE_KEYS.FC_REPORT_READY) === "1";
  });

  const historySavedRef = useRef(false);
  const { playSound } = useSound();
  const soundRef = useRef(playSound);

  // Mount + hydrate from storage (client only). Runs once.
  useEffect(() => {
    const ready = sessionOnlyStorage.getItem(STORAGE_KEYS.FC_REPORT_READY) === "1";
    const sid = initialSessionId ?? storage.getItem(STORAGE_KEYS.SESSION_ID);
    const ctx = readSessionContext(sid);
    const deep = readResultPhase(sid) === "deep";

    setReportAlreadyReady(ready);
    if (sid) setSessionId(sid);
    setIsDeepPhase(deep);
    if (sid) {
      setThumbnail(storage.getItem(`${STORAGE_KEYS.THUMBNAIL}:${sid}`) ?? storage.getItem(STORAGE_KEYS.THUMBNAIL));
    } else {
      setThumbnail(storage.getItem(STORAGE_KEYS.THUMBNAIL));
    }
    setMimeType(ctx?.mime_type ?? storage.getItem(STORAGE_KEYS.MIME_TYPE));
    setPipelineStartAt(ctx?.pipeline_start ?? storage.getItem(STORAGE_KEYS.PIPELINE_START));
    setFileName(ctx?.file_name ?? storage.getItem(STORAGE_KEYS.FILE_NAME));
    setAgentTimeline(loadAgentTimelineForSession(sid, deep));

    if (ready) {
      setArbiterMsg(UI_STRINGS.DECRYPTING_LEDGER);
      sessionOnlyStorage.removeItem(STORAGE_KEYS.FC_REPORT_READY);
      sessionOnlyStorage.removeItem(STORAGE_KEYS.FC_ARBITER_TRANSITIONING);
    }

    setMounted(true);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // Transition smoothness: ensure overlay shows for at least 800ms.
  // data-fc-loading CSS backstop is removed only AFTER the minimum overlay
  // timer fires (or when reportAlreadyReady skips it), so the body::before
  // bridge stays in place until result content is visible.
  useEffect(() => {
    if (!mounted) return;
    if (reportAlreadyReady || minOverlayDone) {
      document.body.removeAttribute("data-fc-loading");
      if (reportAlreadyReady) return;
    }
    if (minOverlayDone) return;
    const timer = setTimeout(() => {
      setMinOverlayDone(true);
      document.body.removeAttribute("data-fc-loading");
    }, 800);
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
        storage.getItem(`${STORAGE_KEYS.THUMBNAIL}:${initialSessionId}`) ??
        storage.getItem(STORAGE_KEYS.THUMBNAIL)
      );
      setMimeType(ctx?.mime_type ?? storage.getItem(STORAGE_KEYS.MIME_TYPE));
      setPipelineStartAt(ctx?.pipeline_start ?? storage.getItem(STORAGE_KEYS.PIPELINE_START));
      setFileName(ctx?.file_name ?? storage.getItem(STORAGE_KEYS.FILE_NAME));
      setAgentTimeline(loadAgentTimelineForSession(initialSessionId, readResultPhase(initialSessionId) === "deep"));
    }
  }, [mounted, initialSessionId, sessionId]);

  const selectSession = useCallback((sid: string) => {
    storage.setItem(STORAGE_KEYS.SESSION_ID, sid);
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
    setThumbnail(storage.getItem(`${STORAGE_KEYS.THUMBNAIL}:${sid}`) ?? storage.getItem(STORAGE_KEYS.THUMBNAIL));
    setMimeType(ctx?.mime_type ?? storage.getItem(STORAGE_KEYS.MIME_TYPE));
    setPipelineStartAt(ctx?.pipeline_start ?? storage.getItem(STORAGE_KEYS.PIPELINE_START));
    setFileName(ctx?.file_name ?? storage.getItem(STORAGE_KEYS.FILE_NAME));
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
    // Use the report's authoritative is_deep_analysis field when available
    if (finalReportData.is_deep_analysis === true || finalReportData.is_deep_analysis === false) {
      setIsDeepPhase(finalReportData.is_deep_analysis);
    }
    setState("ready");
    const id = setTimeout(() => {
      soundRef.current("arbiter_done");
      soundRef.current("result_reveal");
    }, 200);
    return () => clearTimeout(id);
  }, [finalReportData]);

  useEffect(() => {
    if (reportQueryError && arbiterComplete) {
      const msg = reportQueryError instanceof Error ? reportQueryError.message : "";
      if (msg.includes("404")) {
        router.push("/session-expired");
        return;
      }
      setErrorMsg("Failed to retrieve report. Please refresh.");
      setState("error");
    }
  }, [reportQueryError, arbiterComplete, router]);

// ── Arbiter status polling ───────────────────────────────────────────────────
   useEffect(() => {
    if (!mounted) return;

    // Pre-flight session validation: ensure sessionId maps to a valid investigation
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
          setState("ready");
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
        router.push("/session-expired");
      }
    }

    poll();
    return () => {
      cancelled = true;
      if (timer) clearTimeout(timer);
    };
  }, [mounted, sessionId, arbiterComplete, router]);

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
        confidence: report.overall_confidence ?? undefined,
        timestamp: Date.now(),
        type: isDeepPhase ? "Deep" : "Initial",
        thumbnail: thumbnail || undefined,
        mime: mimeType || undefined,
      };

      try {
        const stored = storage.getItem<HistoryItem[]>(STORAGE_KEYS.HISTORY, true, []);
        const filtered = (stored ?? []).filter((h) => !(h.sessionId === hItem.sessionId && h.type === hItem.type));
        const HISTORY_MAX = 50;
        const THUMBNAIL_MAX_AGE_MS = 7 * 24 * 60 * 60 * 1000;
        const now = Date.now();
        const next = [hItem, ...filtered]
          .slice(0, HISTORY_MAX)
          .map((h) =>
            h.thumbnail && now - h.timestamp > THUMBNAIL_MAX_AGE_MS
              ? { ...h, thumbnail: undefined }
              : h,
          );
        storage.setItem(STORAGE_KEYS.HISTORY, next, true);
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
        return storage.getItem<HistoryItem[]>(STORAGE_KEYS.HISTORY, true, []) ?? [];
      } catch { return [] as HistoryItem[]; }
    })();
    queryClient.clear();
    storage.clearAllForensicKeys();
    sessionOnlyStorage.clearAllForensicKeys();
    if (savedHistory.length > 0) {
      storage.setItem(STORAGE_KEYS.HISTORY, savedHistory, true);
    }
    document.cookie = `${STORAGE_KEYS.SESSION_ID}=; path=/; max-age=0; SameSite=Lax`;

    window.dispatchEvent(new Event("fc:reset-home"));
    router.push(path);
  }, [playSound, router, queryClient]);

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
