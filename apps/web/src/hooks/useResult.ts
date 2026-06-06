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
import { ARBITER_POLL_INTERVAL_MS, UI_STRINGS } from "@/lib/constants";
import { useSound } from "@/hooks/useSound";
import { type HistoryItem } from "@/lib/types";
import type { AgentUpdate } from "@/components/evidence/types";
import { storage, sessionOnlyStorage } from "@/lib/storage";
import { STORAGE_KEYS } from "@/lib/storageKeys";
import { resetActiveInvestigation } from "@/lib/appReset";

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

function readHistoryItem(sid: string | null): HistoryItem | null {
  if (!sid) return null;
  const hist = storage.getItem<HistoryItem[]>(STORAGE_KEYS.HISTORY, true, []) ?? [];
  return hist.find((h) => h.sessionId === sid) ?? null;
}

interface SessionDisplayContext {
  fileName: string | null;
  mimeType: string | null;
  thumbnail: string | null;
  pipelineStart: string | null;
}

// Resolve a session's file/display context from the most authoritative source
// available, in order: per-session context blob → per-session scoped keys →
// History item (survives full resets) → active-session base keys. This ensures
// a revisited session always renders ITS OWN metadata and never inherits the
// currently-active session's file name/thumbnail when its scoped keys were
// pruned.
function resolveSessionDisplayContext(sid: string | null): SessionDisplayContext {
  const ctx = readSessionContext(sid);
  const hist = readHistoryItem(sid);
  const scoped = (base: string) => (sid ? storage.getItem(`${base}:${sid}`) : null);
  return {
    fileName:
      ctx?.file_name ?? scoped(STORAGE_KEYS.FILE_NAME) ?? hist?.fileName ?? storage.getItem(STORAGE_KEYS.FILE_NAME),
    mimeType:
      ctx?.mime_type ?? scoped(STORAGE_KEYS.MIME_TYPE) ?? hist?.mime ?? storage.getItem(STORAGE_KEYS.MIME_TYPE),
    thumbnail:
      scoped(STORAGE_KEYS.THUMBNAIL) ?? hist?.thumbnail ?? storage.getItem(STORAGE_KEYS.THUMBNAIL),
    pipelineStart:
      ctx?.pipeline_start ?? scoped(STORAGE_KEYS.PIPELINE_START) ?? storage.getItem(STORAGE_KEYS.PIPELINE_START),
  };
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

function buildAgentTimelineFromReport(report: ReportDTO): AgentUpdate[] {
  if (!report.agent_summaries || !Array.isArray(report.agent_summaries)) return [];
  return (report.agent_summaries as Array<Record<string, unknown>>)
    .filter((s) => typeof s === "object" && s !== null && typeof s.agent_id === "string")
    .map((s) => ({
      agent_id: s.agent_id as string,
      agent_name: (s.agent_name as string) ?? (s.agent_id as string),
      status: ((s.status as string) ?? "complete") as AgentUpdate["status"],
      completed_at: (s.completed_at as string) ?? null,
      message: (s.message as string) ?? "",
      confidence: (s.confidence as number) ?? 0,
      findings_count: (s.findings_count as number) ?? 0,
    }));
}

export { buildAgentTimelineFromReport };

export function useResult(initialSessionId?: string) {
  const router = useRouter();
  const queryClient = useQueryClient();

  // All storage-dependent state initialized to SSR-safe defaults.
  // Hydration from storage happens once after mount (see effect below) to
  // avoid server/client mismatch on first paint.
  const [mounted, setMounted] = useState(false);
  const [reportAlreadyReady, setReportAlreadyReady] = useState(false);
  // Use SSR-safe defaults for all state — reading localStorage in useState
  // initializers causes server/client hydration mismatches. Storage is read
  // in the mount useEffect below, which is client-only.
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
  const revealSoundedRef = useRef(false);
  const { playSound } = useSound();
  const soundRef = useRef(playSound);

  // Mount + hydrate from storage (client only). Runs once.
  useEffect(() => {
    const sid = initialSessionId ?? storage.getItem(STORAGE_KEYS.SESSION_ID);
    const ready = sid ? sessionOnlyStorage.getItem(`${STORAGE_KEYS.FC_REPORT_READY}:${sid}`) === "1" : false;
    const deep = readResultPhase(sid) === "deep";

    setReportAlreadyReady(ready);
    if (sid) setSessionId(sid);
    setIsDeepPhase(deep);
    const dctx = resolveSessionDisplayContext(sid);
    setThumbnail(dctx.thumbnail);
    setMimeType(dctx.mimeType);
    setPipelineStartAt(dctx.pipelineStart);
    setFileName(dctx.fileName);
    setAgentTimeline(loadAgentTimelineForSession(sid, deep));

    if (ready && sid) {
      setArbiterMsg(UI_STRINGS.DECRYPTING_LEDGER);
      sessionOnlyStorage.removeItem(`${STORAGE_KEYS.FC_REPORT_READY}:${sid}`);
      sessionOnlyStorage.removeItem(`${STORAGE_KEYS.FC_ARBITER_TRANSITIONING}:${sid}`);
    }

    setMounted(true);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // Transition smoothness: ensure the arbiter overlay shows for at least 400ms
  // on the result page before allowing state to flip to "ready". This prevents
  // a perceptible flash when the report is already cached and arrives in <100ms.
  // data-fc-loading CSS backstop is removed only AFTER this timer fires (or
  // when reportAlreadyReady skips it), so the body::before bridge stays in
  // place until result content is actually visible.
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
      // When minOverlayDone becomes true, the finalReportData effect re-runs
      // (minOverlayDone is in its dep array) and calls setState("ready") if
      // the report is already available — covering the race where the report
      // arrived while this timer was running.
    }, 400);
    return () => clearTimeout(timer);
  }, [mounted, sessionId, reportAlreadyReady, minOverlayDone]);

  // Sync sessionId if initialSessionId changes (e.g. dynamic route navigation)
  useEffect(() => {
    if (!mounted) return;
    if (initialSessionId && initialSessionId !== sessionId) {
      setSessionId(initialSessionId);
      setReport(null);
      setArbiterComplete(false);
      setMinOverlayDone(false);
      historySavedRef.current = false;
      revealSoundedRef.current = false;
      setState("arbiter");
      setArbiterMsg("Council deliberating on evidence...");
      setIsDeepPhase(readResultPhase(initialSessionId) === "deep");
      const dctx = resolveSessionDisplayContext(initialSessionId);
      setThumbnail(dctx.thumbnail);
      setMimeType(dctx.mimeType);
      setPipelineStartAt(dctx.pipelineStart);
      setFileName(dctx.fileName);
      setAgentTimeline(loadAgentTimelineForSession(initialSessionId, readResultPhase(initialSessionId) === "deep"));
    }
  }, [mounted, initialSessionId, sessionId]);

  const selectSession = useCallback((sid: string) => {
    storage.setItem(STORAGE_KEYS.SESSION_ID, sid);
    const nextIsDeep = readResultPhase(sid) === "deep";
    setSessionId(sid);
    setArbiterComplete(false);
    setMinOverlayDone(false);
    setReport(null);
    setState("arbiter");
    historySavedRef.current = false;
    revealSoundedRef.current = false;
    setArbiterMsg("Council deliberating on evidence...");
    setIsDeepPhase(nextIsDeep);
    const dctx = resolveSessionDisplayContext(sid);
    setThumbnail(dctx.thumbnail);
    setMimeType(dctx.mimeType);
    setPipelineStartAt(dctx.pipelineStart);
    setFileName(dctx.fileName);
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
    enabled: !!sessionId && mounted,
    // The report is an authoritative, point-in-time backend artifact that can
    // change for the same session (initial → deep analysis, or a re-run). Treat
    // it as always stale and refetch on every result-page mount so revisiting a
    // session (history, deep completion) never shows a cached older report.
    staleTime: 0,
    refetchOnMount: "always",
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
    setErrorMsg("");
    // Use the report's authoritative is_deep_analysis field when available
    if (finalReportData.is_deep_analysis === true || finalReportData.is_deep_analysis === false) {
      setIsDeepPhase(finalReportData.is_deep_analysis);
    }
    // The report's agent_summaries are the authoritative execution timeline.
    // Prefer them over any locally-persisted streaming snapshot so a stale
    // localStorage timeline can never override fresh backend data; the persisted
    // snapshot remains only as a fallback when the report carries no summaries.
    const fromReport = buildAgentTimelineFromReport(finalReportData);
    if (fromReport.length > 0) {
      setAgentTimeline(fromReport);
    }
    // Only transition to "ready" after the min overlay duration has elapsed
    // to prevent blank flash during overlay exit animation.
    if (minOverlayDone) {
      setState("ready");
      // ONE reveal sound, synced to the moment the report content actually
      // appears, fired at most once per session (guarded against React Query
      // refetches). Previously three sounds (mount-time stamp + arbiter_done +
      // result_reveal) clashed and the stamp fired during loading. The 220ms
      // delay aligns the seal with the content paint / flash clearing.
      if (!revealSoundedRef.current) {
        revealSoundedRef.current = true;
        const id = setTimeout(() => {
          soundRef.current("stamp");
        }, 220);
        return () => clearTimeout(id);
      }
    }
  }, [finalReportData, minOverlayDone]);

  useEffect(() => {
    if (!reportQueryError) return;
    // Handle errors regardless of arbiterComplete — silencing them when
    // arbiterComplete=false left users stuck on the arbiter overlay indefinitely.
    const msg = reportQueryError instanceof Error ? reportQueryError.message : "";
    if (msg.includes("404")) {
      router.push("/session-expired");
      return;
    }
    setErrorMsg("Failed to retrieve report. Please refresh.");
    setState("error");
  }, [reportQueryError, router]);

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
    const pollStart = Date.now();
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
          return;
        } else if (s.status === "error") {
          setErrorMsg(s.message || "Investigation failed");
          setState("error");
          return;
        } else if (s.status === "not_found") {
          if (Date.now() - pollStart > 30000) {
            setErrorMsg("Investigation session not found. It may have expired.");
            setState("error");
            return;
          }
          setArbiterMsg("Initializing investigation...");
        } else {
          setArbiterMsg(s.message || "Council deliberating...");
        }
      } catch (e: unknown) {
        if (cancelled) return;
        dbg.error("Polling error", e);
      }

      if (!cancelled) {
        timer = setTimeout(poll, pollInterval);
        pollInterval = Math.min(pollInterval * 1.3, 3000);
      }
    }

    poll();
    return () => {
      cancelled = true;
      if (timer) clearTimeout(timer);
    };
  // reportQueryData intentionally excluded: the finalReportData effect handles
  // the reportQueryData → arbiterComplete transition, so including it here
  // would cancel and restart the entire poll on every React Query refetch.
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
    void resetActiveInvestigation(queryClient);
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
    a.download = `forensic-report-${(report.report_id || sessionId || "unknown").slice(0, 8)}.json`;
    a.click();
    URL.revokeObjectURL(url);
  }, [report, sessionId]);

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
