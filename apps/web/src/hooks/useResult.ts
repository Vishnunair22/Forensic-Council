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
  // Preferred: an explicit agent_summaries array, if the backend ever emits one.
  if (Array.isArray(report.agent_summaries) && report.agent_summaries.length) {
    return (report.agent_summaries as Array<Record<string, unknown>>)
      .filter((s) => typeof s === "object" && s !== null && typeof s.agent_id === "string")
      .map((s) => ({
        agent_id: s.agent_id as string,
        agent_name: (s.agent_name as string) ?? (s.agent_id as string),
        status: ((s.status as string) ?? "complete") as AgentUpdate["status"],
        message: (s.message as string) ?? "",
        confidence: (s.confidence as number) ?? 0,
        findings_count: (s.findings_count as number) ?? 0,
      }));
  }
  // Authoritative fallback: derive from per_agent_metrics, which IS part of the
  // signed ReportDTO contract. agent_summaries is NOT — relying on it alone left
  // this timeline permanently empty, so a stale localStorage streaming snapshot
  // always won. per_agent_metrics gives the real, completed-run execution state.
  const metrics = report.per_agent_metrics;
  if (metrics && typeof metrics === "object") {
    const summary = (report.per_agent_summary ?? {}) as Record<
      string,
      { verdict?: string } | undefined
    >;
    return Object.values(metrics)
      .filter((m) => m && typeof m.agent_id === "string")
      .map((m) => {
        const verdict = summary[m.agent_id]?.verdict;
        return {
          agent_id: m.agent_id,
          agent_name: m.agent_name ?? m.agent_id,
          status: (m.skipped ? "skipped" : "complete") as AgentUpdate["status"],
          message: "",
          confidence: m.confidence_score ?? 0,
          findings_count: m.finding_count ?? 0,
          ...(verdict ? { agent_verdict: verdict as AgentUpdate["agent_verdict"] } : {}),
        };
      });
  }
  return [];
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

  // Transition smoothness: hold the arbiter overlay for at least 400ms before
  // flipping to "ready" so a report that arrives in <100ms doesn't flash. When
  // the report is ALREADY confirmed ready (Accept Baseline / View Results set
  // FC_REPORT_READY and the evidence page already showed the overlay for its
  // minimum), skip the artificial delay and reveal immediately — the
  // finalReportData effect treats reportAlreadyReady as satisfying this gate.
  useEffect(() => {
    if (!mounted || reportAlreadyReady || minOverlayDone) return;
    const timer = setTimeout(() => setMinOverlayDone(true), 400);
    return () => clearTimeout(timer);
  }, [mounted, reportAlreadyReady, minOverlayDone]);

  // Remove the full-screen loading bridge (body[data-fc-loading]) ONLY once the
  // report (or a terminal state) is actually on screen. Removing it earlier — on
  // mount, as the previous code did for reportAlreadyReady — exposed the empty
  // result scaffold for a frame ("blank before the report loads"). Keeping it up
  // under the arbiter overlay until state="ready" makes the hand-off seamless:
  // bridge + overlay cover continuously, then the overlay fades out to reveal the
  // report in one fluid step.
  useEffect(() => {
    if (state === "ready" || state === "error" || state === "empty") {
      document.body.removeAttribute("data-fc-loading");
    }
  }, [state]);

  // Sync sessionId if initialSessionId changes (e.g. dynamic route navigation)
  useEffect(() => {
    if (!mounted) return;
    if (initialSessionId && initialSessionId !== sessionId) {
      setSessionId(initialSessionId);
      setReport(null);
      setArbiterComplete(false);
      setMinOverlayDone(false);
      setReportAlreadyReady(
        sessionOnlyStorage.getItem(`${STORAGE_KEYS.FC_REPORT_READY}:${initialSessionId}`) === "1",
      );
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
    setReportAlreadyReady(
      sessionOnlyStorage.getItem(`${STORAGE_KEYS.FC_REPORT_READY}:${sid}`) === "1",
    );
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
    // Reveal once the min-overlay window has elapsed OR the report was already
    // confirmed ready before navigation (Accept Baseline / View Results). Without
    // the reportAlreadyReady branch, minOverlayDone never becomes true on that
    // path (the timer effect is skipped), so the page hung on the arbiter overlay
    // and the report never appeared — the broken accept→arbiter→result flow.
    if (minOverlayDone || reportAlreadyReady) {
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
  }, [finalReportData, minOverlayDone, reportAlreadyReady]);

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

    // Overall escape hatch: the result page is shown AFTER the agents complete
    // (Accept Baseline / View Results), so the report should finalize in seconds.
    // If the backend wedges (e.g. a worker OOM-crash during arbiter deliberation),
    // metadata.status stays a non-terminal value and the status endpoint returns
    // "running" forever — leaving the user stuck on the deliberation overlay. This
    // generous deadline guarantees the overlay always resolves to an actionable
    // error instead of hanging. It cannot false-fire: a real report finalizes far
    // inside this window, and the awaiting-decision wait happens on the EVIDENCE
    // page, never here.
    const RESULT_REPORT_DEADLINE_MS = 240_000; // 4 min

    async function poll() {
      if (cancelled) return;

      if (Date.now() - pollStart > RESULT_REPORT_DEADLINE_MS) {
        setErrorMsg(
          "The report is taking longer than expected — the investigation may have stalled. Please refresh, or start a new analysis.",
        );
        setState("error");
        return;
      }

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
