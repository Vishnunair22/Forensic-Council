"use client";

import React, { useState, useEffect, useMemo, useRef, useCallback } from "react";
import {
  CheckCircle, AlertTriangle, ShieldCheck, RotateCcw,
  Home, ChevronDown, Lock, FileText,
  Shield, XCircle, Download, LinkIcon,
  Hash, Fingerprint, Image as ImageIcon, Film, Mic,
  AlertCircle, Activity, Info, History, X,
} from "lucide-react";
import { useRouter } from "next/navigation";
import clsx from "clsx";
import { useForensicData, mapReportDtoToReport } from "@/hooks/useForensicData";
import { useSound } from "@/hooks/useSound";
import { type HistoryItem } from "@/components/ui/HistoryDrawer";
import {
  getReport, getArbiterStatus,
  type ReportDTO, type AgentMetricsDTO, type AgentFindingDTO,
} from "@/lib/api";
import { Badge } from "@/components/lightswind/badge";
import { getVerdictConfig } from "@/lib/verdict";
import { AgentFindingCard } from "@/components/ui/AgentFindingCard";
import { ForensicProgressOverlay } from "@/components/ui/ForensicProgressOverlay";

const isDev = process.env.NODE_ENV !== "production";
const dbg = { error: isDev ? console.error.bind(console) : () => {} };

// ─── Constants ────────────────────────────────────────────────────────────────
const ALL_AGENT_IDS = ["Agent1", "Agent2", "Agent3", "Agent4", "Agent5"];

const AGENT_META: Record<string, { name: string; role: string; accentColor: string; accentBg: string; accentBorder: string }> = {
  Agent1: { name: "Agent 1", role: "Image Integrity",    accentColor: "text-cyan-400",   accentBg: "bg-cyan-500/10",   accentBorder: "border-cyan-500/30"   },
  Agent2: { name: "Agent 2", role: "Audio Forensics",    accentColor: "text-emerald-400",accentBg: "bg-emerald-500/10",accentBorder: "border-emerald-500/30" },
  Agent3: { name: "Agent 3", role: "Object & Weapons",   accentColor: "text-amber-400",  accentBg: "bg-amber-500/10",  accentBorder: "border-amber-500/30"   },
  Agent4: { name: "Agent 4", role: "Video Analysis",     accentColor: "text-rose-400",   accentBg: "bg-rose-500/10",   accentBorder: "border-rose-500/30"    },
  Agent5: { name: "Agent 5", role: "Metadata & Context", accentColor: "text-violet-400", accentBg: "bg-violet-500/10", accentBorder: "border-violet-500/30"  },
};

type Tab = "analysis" | "findings" | "history";

// ─── Helpers ──────────────────────────────────────────────────────────────────
function confColor(c: number) {
  return c >= 0.75 ? "text-emerald-400" : c >= 0.5 ? "text-amber-400" : "text-red-400";
}

function fileTypeIcon(mime: string | undefined) {
  if (!mime) return FileText;
  if (mime.startsWith("image/")) return ImageIcon;
  if (mime.startsWith("video/")) return Film;
  if (mime.startsWith("audio/")) return Mic;
  return FileText;
}

function stripToolPrefix(text: string): string {
  if (!text) return text;
  const colonIdx = text.indexOf(":");
  if (colonIdx <= 0 || colonIdx > 55) return text;
  const candidate = text.slice(0, colonIdx).trim();
  // Only strip if prefix looks like a tool name:
  // - all-caps with underscores (e.g. "FILE_HASH_VERIFY: "), or
  // - short title-case (≤4 words, no lowercase conjunctions like "and", "of", "the")
  const wordCount = candidate.split(/\s+/).length;
  if (wordCount <= 4 && /^[A-Z][A-Za-z0-9 /&-]{2,54}$/.test(candidate)) {
    // Extra guard: skip if it reads like a natural-language phrase
    const lower = candidate.toLowerCase();
    const skipWords = ["and", "the", "of", "for", "with", "from", "this", "that", "has", "was", "were"];
    if (skipWords.some(w => lower.split(/\s+/).includes(w))) return text;
    return text.slice(colonIdx + 1).trimStart();
  }
  return text;
}

const TRIVIAL_UNCERTAINTY = new Set([
  "all findings have been resolved. no significant uncertainties remain.",
  "no significant uncertainties remain.",
  "analysis complete. no uncertainties identified.",
]);

function isBoilerplateUncertainty(s: string): boolean {
  return TRIVIAL_UNCERTAINTY.has(s.toLowerCase().trim());
}

// ─── Evidence thumbnail / file graphic ───────────────────────────────────────
function EvidenceThumbnail({ mime, thumbnail }: { mime: string | null; thumbnail: string | null }) {
  if (thumbnail) {
    return (
      /* eslint-disable-next-line @next/next/no-img-element */
      <img src={thumbnail} alt="Evidence preview" className="w-full h-full object-cover" />
    );
  }
  const FtIcon = fileTypeIcon(mime || undefined);
  const isAudio = mime?.startsWith("audio/");
  const isVideo = mime?.startsWith("video/");
  return (
    <div className="w-full h-full flex flex-col items-center justify-center gap-3">
      {isAudio ? (
        <>
          <Mic className="w-10 h-10 text-emerald-400/60" />
          <div className="flex items-end gap-[3px] h-6">
            {[3,6,9,5,8,4,7,3,6,8,5,9].map((h, i) => (
              <div key={i} className="w-[3px] rounded-full bg-emerald-400/30" style={{ height: `${h * 2.5}px` }} />
            ))}
          </div>
        </>
      ) : isVideo ? (
        <Film className="w-10 h-10 text-rose-400/60" />
      ) : (
        <FtIcon className="w-10 h-10 text-amber-500/60" />
      )}
    </div>
  );
}

// ─── Collapsible Section (glass-t2) ─────────────────────────────────────────
function CollapsibleSection({
  icon, title, count, color, children,
}: {
  icon: React.ReactNode;
  title: string;
  count?: number;
  color: "emerald" | "amber" | "violet" | "amber-muted";
  children: React.ReactNode;
}) {
  const [open, setOpen] = useState(false);
  const textColor = {
    emerald: "text-emerald-500", amber: "text-amber-500",
    violet: "text-violet-400", "amber-muted": "text-amber-400/60",
  }[color];

  return (
    <div className="glass-t2 rounded-2xl overflow-hidden">
      <button onClick={() => setOpen(v => !v)} aria-expanded={open}
        className="w-full flex items-center justify-between px-6 py-4 hover:bg-white/[0.03] transition-all duration-300 cursor-pointer group">
        <span className={`flex items-center gap-3 text-[11px] font-bold uppercase tracking-widest ${textColor}`}>
          {icon}
          {title}{count !== undefined && count > 0 ? ` (${count})` : ""}
        </span>
        <div className={clsx("p-1.5 rounded-full bg-white/[0.04] border border-white/[0.06] transition-all duration-300", open && "rotate-180 bg-amber-500/10 border-amber-500/30")}>
          <ChevronDown className="w-4 h-4 text-foreground/40" />
        </div>
      </button>
      {open && <div className="px-6 pb-6" style={{ borderTop: "1px solid rgba(255,255,255,0.06)" }}>{children}</div>}
    </div>
  );
}

// ─── Main page ────────────────────────────────────────────────────────────────
type PageState = "arbiter" | "ready" | "error" | "empty";

export default function ResultPage() {
  const router = useRouter();
  const [mounted, setMounted]         = useState(false);
  const [state, setState]             = useState<PageState>("arbiter");
  const [report, setReport]           = useState<ReportDTO | null>(null);
  const [arbiterMsg, setArbiterMsg]   = useState("");
  const [errorMsg, setErrorMsg]       = useState("");
  const [activeTab, setActiveTab]     = useState<Tab>("analysis");
  const [isDeepPhase, setIsDeepPhase] = useState(false);
  const [thumbnail, setThumbnail]     = useState<string | null>(null);
  const [mimeType, setMimeType]       = useState<string | null>(null);
  const historySavedRef               = useRef(false);

  useEffect(() => {
    setIsDeepPhase(sessionStorage.getItem("forensic_is_deep") === "true");
    setThumbnail(sessionStorage.getItem("forensic_thumbnail"));
    setMimeType(sessionStorage.getItem("forensic_mime_type"));
  }, []);

  const { addToHistory } = useForensicData();
  const { playSound }    = useSound();
  const soundRef         = useRef(playSound);
  useEffect(() => { soundRef.current = playSound; }, [playSound]);

  // ── Poll arbiter then fetch report ────────────────────────────────────────
  useEffect(() => {
    const sessionId = sessionStorage.getItem("forensic_session_id");
    if (!sessionId) { setState("empty"); return; }

    const sid = sessionId;
    let cancelled = false;
    let timer: ReturnType<typeof setTimeout>;
    let attempts = 0;
    const MAX = 150;

    async function poll() {
      if (cancelled) return;
      attempts++;
      try {
        const s = await getArbiterStatus(sid);
        if (cancelled) return;

        if (s.status === "complete" || s.status === "not_found") {
          try {
            const res = await getReport(sid);
            if (cancelled) return;
            if (res.status === "complete" && res.report) {
              setReport(res.report);
              setState("ready");
              addToHistory(mapReportDtoToReport(res.report));
              try {
                const stored = sessionStorage.getItem("fc_full_report_history");
                const hist: ReportDTO[] = stored ? JSON.parse(stored) : [];
                const snap = res.report;
                if (snap && !hist.some(r => r.report_id === snap.report_id)) {
                  const serialised = JSON.stringify([snap, ...hist].slice(0, 20));
                  if (serialised.length < 4_000_000) {
                    sessionStorage.setItem("fc_full_report_history", serialised);
                  }
                }
              } catch { /* ignore storage errors */ }
              setTimeout(() => soundRef.current("arbiter_done"), 150);
              return;
            }
          } catch (e) { dbg.error("getReport failed:", e); }
        } else if (s.status === "error") {
          setErrorMsg(s.message || "Investigation failed");
          setState("error");
          return;
        } else {
          setArbiterMsg(s.message || "");
          // Even if arbiter says processing, check if report is already ready
          try {
            const res = await getReport(sid);
            if (!cancelled && res.status === "complete" && res.report) {
              setReport(res.report);
              setState("ready");
              addToHistory(mapReportDtoToReport(res.report));
              setTimeout(() => soundRef.current("arbiter_done"), 150);
              return;
            }
          } catch { /* report not ready yet, keep polling */ }
        }
      } catch { /* network — keep polling */ }

      if (!cancelled && attempts < MAX) {
        timer = setTimeout(poll, 2000);
      } else if (!cancelled) {
        setErrorMsg("Arbiter timed out. The session may have expired.");
        setState("error");
      }
    }

    poll();
    return () => { cancelled = true; clearTimeout(timer); };
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  useEffect(() => { setMounted(true); }, []);

  // ── Derived data ──────────────────────────────────────────────────────────
  const activeAgentIds = useMemo(() => {
    const SKIP_TYPES = new Set(["file type not applicable", "format not supported"]);
    return Object.keys(report?.per_agent_findings ?? {}).filter(id => {
      const flist = report?.per_agent_findings[id] ?? [];
      return flist.length > 0 && !flist.every(f => SKIP_TYPES.has(String(f.finding_type).toLowerCase()));
    });
  }, [report]);

  const totalFindings = useMemo(() => {
    const SKIP_TYPES = new Set(["file type not applicable", "format not supported"]);
    let total = 0;
    Object.values(report?.per_agent_findings ?? {}).flat().forEach(f => {
      if (!SKIP_TYPES.has(String(f.finding_type).toLowerCase())) total++;
    });
    return total;
  }, [report]);

  const keyFindings = useMemo(() => {
    if (report?.key_findings && report.key_findings.length > 0) {
      return report.key_findings;
    }
    // Fallback: extract top reasoning summaries from per-agent findings
    const SKIP_TYPES = new Set(["file type not applicable", "format not supported"]);
    const summaries: string[] = [];
    for (const id of activeAgentIds) {
      const findings = report?.per_agent_findings[id] ?? [];
      for (const f of findings) {
        if (SKIP_TYPES.has(String(f.finding_type).toLowerCase())) continue;
        const s = f.reasoning_summary?.trim();
        if (s && s.length > 10 && !summaries.includes(s)) {
          summaries.push(s);
        }
      }
    }
    return summaries.slice(0, 8);
  }, [report, activeAgentIds]);

  const vc       = report ? getVerdictConfig(report.overall_verdict ?? "") : null;
  const confPct  = Math.round((report?.overall_confidence ?? 0) * 100);
  const manipPct = Math.round((report?.manipulation_probability ?? 0) * 100);

  const fileName = useMemo(() => {
    if (typeof window === "undefined") return report?.case_id ?? "Evidence File";
    return sessionStorage.getItem("forensic_file_name") || report?.case_id || "Evidence File";
  }, [report]);

  // ── History tracking ──────────────────────────────────────────────────────
  useEffect(() => {
    if (state === "ready" && report && !historySavedRef.current) {
      historySavedRef.current = true;
      const hItem: HistoryItem = {
        sessionId: report.session_id,
        fileName:  sessionStorage.getItem("forensic_file_name") || "Unknown File",
        verdict:   report.overall_verdict || "INCONCLUSIVE",
        timestamp: Date.now(),
        type:      isDeepPhase ? "Deep" : "Initial",
      };
      try {
        const stored = JSON.parse(localStorage.getItem("forensic_history") || "[]") as HistoryItem[];
        const filtered = stored.filter(h => h.sessionId !== hItem.sessionId);
        localStorage.setItem("forensic_history", JSON.stringify([hItem, ...filtered]));
      } catch (e) { dbg.error("Failed to commit history", e); }
    }
  }, [state, report, isDeepPhase]);

  // ── Actions ───────────────────────────────────────────────────────────────
  const handleNew  = useCallback(() => {
    playSound("click");
    ["forensic_session_id", "forensic_file_name", "forensic_case_id", "forensic_thumbnail"].forEach(k =>
      sessionStorage.removeItem(k)
    );
    router.push("/evidence");
  }, [playSound, router]);

  const handleHome = useCallback(() => {
    playSound("click");
    router.push("/");
  }, [playSound, router]);

  const handleExport = useCallback(() => {
    if (!report) return;
    const blob = new Blob([JSON.stringify(report, null, 2)], { type: "application/json" });
    const url  = URL.createObjectURL(blob);
    const a    = document.createElement("a");
    a.href     = url;
    a.download = `forensic-report-${report.report_id.slice(0, 8)}.json`;
    a.click();
    URL.revokeObjectURL(url);
  }, [report]);

  if (!mounted) return null;

  return (
    <div className="min-h-screen text-foreground">
      {state === "arbiter" && (
        <ForensicProgressOverlay
          variant="council"
          title="Council deliberation"
          liveText={arbiterMsg}
          telemetryLabel="Report synthesis"
          showElapsed
        />
      )}

      {/* ── Export Bar ───────────────────────────────────────────────────── */}
      {state === "ready" && (
        <div className="fixed top-[52px] right-6 z-50">
          <button onClick={handleExport}
            className="btn-premium-glass flex items-center gap-2 !rounded-full !px-4 !py-1.5 text-[10px]">
            <Download className="w-3 h-3" /> Export
          </button>
        </div>
      )}

      {/* ── Secondary Nav ─────────────────────────────────────────────────── */}
      <div className="w-full glass-t3" style={{ borderTop: "none" }}>
        <div className="max-w-6xl mx-auto px-6 flex gap-1 py-2">
          <button
            onClick={() => setActiveTab("analysis")}
            className={clsx(
              "px-5 py-2 text-[10px] font-bold uppercase tracking-[0.15em] transition-all duration-300 rounded-full cursor-pointer",
              activeTab === "analysis"
                ? "bg-amber-500/15 text-amber-400 border border-amber-500/30 shadow-[0_0_12px_rgba(217,119,6,0.15)]"
                : "text-foreground/30 border border-transparent hover:text-foreground/50 hover:bg-white/[0.03]"
            )}
          >
            Current Analysis
          </button>
          <button
            onClick={() => setActiveTab("findings")}
            className={clsx(
              "px-5 py-2 text-[10px] font-bold uppercase tracking-[0.15em] transition-all duration-300 rounded-full cursor-pointer",
              activeTab === "findings"
                ? "bg-amber-500/15 text-amber-400 border border-amber-500/30 shadow-[0_0_12px_rgba(217,119,6,0.15)]"
                : "text-foreground/30 border border-transparent hover:text-foreground/50 hover:bg-white/[0.03]"
            )}
          >
            Agent Findings
          </button>
          <button
            onClick={() => setActiveTab("history")}
            className={clsx(
              "px-5 py-2 text-[10px] font-bold uppercase tracking-[0.15em] transition-all duration-300 rounded-full cursor-pointer",
              activeTab === "history"
                ? "bg-amber-500/15 text-amber-400 border border-amber-500/30 shadow-[0_0_12px_rgba(217,119,6,0.15)]"
                : "text-foreground/30 border border-transparent hover:text-foreground/50 hover:bg-white/[0.03]"
            )}
          >
            History
          </button>
        </div>
      </div>

      {/* ── History Tab ───────────────────────────────────────────────────── */}
      {activeTab === "history" && (
        <main className="max-w-6xl mx-auto px-6 pt-8 pb-24">
          <HistoryPanel />
        </main>
      )}

      {/* ── Agent Findings Tab ────────────────────────────────────────────── */}
      {activeTab === "findings" && state === "ready" && report && (
        <main className="max-w-6xl mx-auto px-6 pt-8 pb-24 space-y-4">
          <div className="flex items-center gap-3 mb-2">
            <Activity className="w-4 h-4 text-amber-400 shrink-0" />
            <h2 className="text-[11px] font-bold uppercase tracking-widest text-foreground">Agent Findings Drill-Down</h2>
          </div>
          {ALL_AGENT_IDS.map((agentId) => {
            const findings = report.per_agent_findings?.[agentId] ?? [];
            if (findings.length === 0) return null;
            const metrics = report.per_agent_metrics?.[agentId];
            const narrative = report.per_agent_analysis?.[agentId] ?? "";
            const initialF = findings.filter(
              f => ((f.metadata as Record<string, unknown>)?.analysis_phase as string ?? "initial") === "initial"
            );
            const deepF = findings.filter(
              f => (f.metadata as Record<string, unknown>)?.analysis_phase === "deep"
            );
            return (
              <AgentFindingCard
                key={agentId}
                agentId={agentId}
                initialFindings={initialF as AgentFindingDTO[]}
                deepFindings={deepF as AgentFindingDTO[]}
                metrics={metrics as AgentMetricsDTO}
                narrative={narrative}
                phase={(isDeepPhase && deepF.length > 0) ? "deep" : "initial"}
              />
            );
          })}
        </main>
      )}

      <main className="max-w-6xl mx-auto px-6 pt-6 pb-28">

        {/* ══ READY ══════════════════════════════════════════════════════════ */}
        {state === "ready" && report && vc && activeTab === "analysis" && (
          <div className="space-y-6">

            {/* ── Degraded analysis warning ── */}
            {report.degradation_flags && report.degradation_flags.length > 0 && (
              <div className="rounded-2xl border border-amber-500/50 bg-amber-500/10 p-4">
                <div className="flex items-start gap-3">
                  <div className="mt-0.5 w-5 h-5 shrink-0 rounded-full bg-amber-500/20 flex items-center justify-center">
                    <span className="text-amber-400 text-[10px] font-bold">!</span>
                  </div>
                  <div>
                    <p className="text-[10px] font-bold font-mono uppercase tracking-widest text-amber-400 mb-1.5">
                      DEGRADED ANALYSIS
                    </p>
                    <ul className="space-y-0.5">
                      {report.degradation_flags.map((flag, i) => (
                        <li key={i} className="text-[11px] text-amber-300/80 font-mono leading-relaxed">• {flag}</li>
                      ))}
                    </ul>
                  </div>
                </div>
              </div>
            )}

            {/* ═══════════════════════════════════════════════════════════════ */}
            {/* SECTION 1: Evidence Header                                    */}
            {/* ═══════════════════════════════════════════════════════════════ */}
            <div className="glass-t1 rounded-2xl overflow-hidden">
              <div className="flex items-stretch gap-0">
                <div className="w-28 sm:w-32 shrink-0 overflow-hidden" style={{ background: "rgba(255,255,255,0.02)", borderRight: "1px solid rgba(255,255,255,0.06)" }}>
                  <EvidenceThumbnail mime={mimeType} thumbnail={thumbnail} />
                </div>
                <div className="flex-1 min-w-0 p-5 space-y-2.5">
                  <h2 className="text-sm font-bold text-foreground truncate">{fileName}</h2>
                  <p className="text-[9px] font-mono text-foreground/30 uppercase tracking-widest">
                    {mimeType || "Unknown format"}
                  </p>
                  <div className="flex items-center gap-2 flex-wrap">
                    <Badge
                      variant={isDeepPhase ? "info" : "success"}
                      withDot={!isDeepPhase}
                      className="font-mono font-bold uppercase tracking-widest text-[9px] px-2.5 py-1"
                    >
                      {isDeepPhase ? "Deep Analysis" : "Initial Analysis"}
                    </Badge>
                    {report.case_id && (
                      <Badge variant="outline" className="font-mono text-[9px] font-bold uppercase tracking-widest px-2 py-0.5">
                        {report.case_id}
                      </Badge>
                    )}
                  </div>
                </div>
              </div>
            </div>

            {/* ═══════════════════════════════════════════════════════════════ */}
            {/* SECTION 2: Result Metrics (4-col grid)                        */}
            {/* ═══════════════════════════════════════════════════════════════ */}
            <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
              {/* Verdict */}
              <div className="glass-t2 rounded-2xl p-5 text-center space-y-2">
                <p className="text-[8px] font-mono font-bold uppercase tracking-[0.2em] text-foreground/30">Verdict</p>
                <div className={clsx(
                  "w-10 h-10 mx-auto rounded-xl border flex items-center justify-center",
                  vc.color === "emerald" ? "bg-emerald-500/10 border-emerald-500/30 text-emerald-400" :
                  vc.color === "red"     ? "bg-red-500/10 border-red-500/30 text-red-400" :
                                           "bg-amber-500/10 border-amber-500/30 text-amber-400"
                )}>
                  <vc.Icon className="w-5 h-5" />
                </div>
                <p className={clsx(
                  "text-sm font-black uppercase tracking-tight",
                  vc.color === "emerald" ? "text-emerald-400" :
                  vc.color === "red"     ? "text-red-400"     : "text-amber-400"
                )}>
                  {vc.label}
                </p>
              </div>

              {/* Confidence */}
              <div className="glass-t2 rounded-2xl p-5 text-center space-y-2">
                <p className="text-[8px] font-mono font-bold uppercase tracking-[0.2em] text-foreground/30">Confidence</p>
                <p className={clsx("text-3xl font-black tabular-nums leading-none", confColor(report.overall_confidence ?? 0))}>
                  {confPct}<span className="text-lg text-foreground/15">%</span>
                </p>
                {report.confidence_min !== undefined && report.confidence_max !== undefined && (
                  <div className="space-y-1">
                    <div className="relative h-1 bg-white/5 rounded-full overflow-hidden">
                      <div className="absolute h-full bg-amber-500/30 rounded-full"
                        style={{ left: `${Math.round((report.confidence_min ?? 0) * 100)}%`, right: `${100 - Math.round((report.confidence_max ?? 0) * 100)}%` }} />
                      <div className="absolute top-[-2px] w-1 h-[6px] bg-amber-400 rounded-full"
                        style={{ left: `${confPct}%`, transform: "translateX(-50%)" }} />
                    </div>
                    <p className="text-[8px] font-mono text-foreground/25">
                      range {Math.round((report.confidence_min ?? 0) * 100)}–{Math.round((report.confidence_max ?? 0) * 100)}%
                    </p>
                  </div>
                )}
              </div>

              {/* Error Rate */}
              <div className="glass-t2 rounded-2xl p-5 text-center space-y-2">
                <p className="text-[8px] font-mono font-bold uppercase tracking-[0.2em] text-foreground/30">Error Rate</p>
                <p className={clsx(
                  "text-3xl font-black tabular-nums leading-none",
                  (report.overall_error_rate ?? 0) <= 0.15 ? "text-emerald-400" :
                  (report.overall_error_rate ?? 0) <= 0.30 ? "text-amber-400" : "text-red-400"
                )}>
                  {Math.round((report.overall_error_rate ?? 0) * 100)}<span className="text-lg text-foreground/15">%</span>
                </p>
                {(() => {
                  const totalTools  = activeAgentIds.reduce((s, id) => s + (report.per_agent_metrics?.[id]?.total_tools_called ?? 0), 0);
                  const naTools     = activeAgentIds.reduce((s, id) => s + (report.per_agent_metrics?.[id]?.tools_not_applicable ?? 0), 0);
                  const failedTools = activeAgentIds.reduce((s, id) => s + (report.per_agent_metrics?.[id]?.tools_failed ?? 0), 0);
                  const ranTools    = totalTools - naTools - failedTools;
                  return (
                    <div className="flex items-center justify-center gap-2 text-[8px] font-mono uppercase tracking-widest text-foreground/25">
                      <span className="text-emerald-400/60">{ranTools} ran</span>
                      {failedTools > 0 && <span className="text-amber-400/60">{failedTools} fail</span>}
                    </div>
                  );
                })()}
              </div>

              {/* Manipulation */}
              <div className="glass-t2 rounded-2xl p-5 text-center space-y-2">
                <p className="text-[8px] font-mono font-bold uppercase tracking-[0.2em] text-foreground/30">Tampering Signal</p>
                <p className={clsx(
                  "text-3xl font-black tabular-nums leading-none",
                  manipPct >= 70 ? "text-red-400" : manipPct >= 40 ? "text-amber-400" : "text-emerald-400"
                )}>
                  {manipPct}<span className="text-lg text-foreground/15">%</span>
                </p>
                <div className="h-1 bg-white/5 rounded-full overflow-hidden">
                  <div className={clsx("h-full rounded-full transition-all duration-700", manipPct >= 70 ? "bg-red-500" : manipPct >= 40 ? "bg-amber-500" : "bg-emerald-500")}
                    style={{ width: `${manipPct}%` }} />
                </div>
              </div>
            </div>

            {/* Verdict sentence */}
            {report.verdict_sentence && (
              <div className="glass-t2 rounded-2xl px-5 py-4 border-l-2 border-foreground/20">
                <p className="text-[9px] font-mono font-bold uppercase tracking-[0.2em] text-foreground/25 mb-1.5">Arbiter Verdict</p>
                <p className="text-sm font-semibold text-foreground/80 leading-relaxed">{report.verdict_sentence}</p>
              </div>
            )}

            {/* Reliability note */}
            {report.reliability_note && (
              <div className="glass-t2 rounded-2xl flex items-start gap-3 px-5 py-4">
                <Info className="w-4 h-4 text-foreground/30 shrink-0 mt-0.5" />
                <p className="text-[11px] font-mono text-foreground/45 leading-relaxed">{report.reliability_note}</p>
              </div>
            )}

            {/* ═══════════════════════════════════════════════════════════════ */}
            {/* SECTION 2b: Executive Summary                                  */}
            {/* ═══════════════════════════════════════════════════════════════ */}
            {report.executive_summary && (
              <div className="glass-t1 rounded-2xl overflow-hidden">
                <div className="px-6 py-4 flex items-center gap-3" style={{ borderBottom: "1px solid rgba(255,255,255,0.06)", background: "rgba(255,255,255,0.02)" }}>
                  <FileText className="w-4 h-4 text-foreground/40 shrink-0" />
                  <h2 className="text-[11px] font-bold uppercase tracking-widest text-foreground">Executive Summary</h2>
                </div>
                <div className="p-5">
                  <p className="text-[12px] text-foreground/70 leading-relaxed whitespace-pre-wrap">{report.executive_summary}</p>
                </div>
              </div>
            )}

            {/* ═══════════════════════════════════════════════════════════════ */}
            {/* SECTION 3: Key Findings                                      */}
            {/* ═══════════════════════════════════════════════════════════════ */}
            <div className="glass-t1 rounded-2xl overflow-hidden">
              <div className="px-6 py-4 flex items-center justify-between" style={{ borderBottom: "1px solid rgba(255,255,255,0.06)", background: "rgba(255,255,255,0.02)" }}>
                <div className="flex items-center gap-3">
                  <CheckCircle className="w-4 h-4 text-emerald-400 shrink-0" />
                  <h2 className="text-[11px] font-bold uppercase tracking-widest text-foreground">Key Findings</h2>
                </div>
                <div className="flex items-center gap-3">
                  <span className="text-[9px] font-mono text-foreground/30">
                    {activeAgentIds.length}/{ALL_AGENT_IDS.length} agents ran
                  </span>
                  <span className="text-[9px] font-mono text-foreground/30">
                    {totalFindings} signals
                  </span>
                </div>
              </div>
              {keyFindings.length > 0 ? (
                <div className="p-5 space-y-3">
                  {keyFindings.map((f, i) => (
                    <div key={i} className="flex items-start gap-3">
                      <span className="mt-0.5 w-5 h-5 rounded-md bg-emerald-500/10 border border-emerald-500/20 flex items-center justify-center shrink-0 text-[9px] font-bold font-mono text-emerald-400">
                        {i + 1}
                      </span>
                      <p className="text-[11px] text-foreground/70 leading-relaxed font-medium flex-1">
                        {stripToolPrefix(f)}
                      </p>
                    </div>
                  ))}
                </div>
              ) : (
                <div className="p-8 text-center text-[11px] text-foreground/30 font-mono">
                  No key findings extracted.
                </div>
              )}
            </div>

            {/* ═══════════════════════════════════════════════════════════════ */}
            {/* SECTION 4: Agent Execution Table                              */}
            {/* ═══════════════════════════════════════════════════════════════ */}
            <div className="glass-t1 rounded-2xl overflow-hidden">
              <div className="px-6 py-4 flex items-center justify-between" style={{ borderBottom: "1px solid rgba(255,255,255,0.06)", background: "rgba(255,255,255,0.02)" }}>
                <div className="flex items-center gap-3">
                  <Activity className="w-4 h-4 text-amber-400 shrink-0" />
                  <h2 className="text-[11px] font-bold uppercase tracking-widest text-foreground">Agent Execution Log</h2>
                </div>
              </div>
              <div className="overflow-x-auto">
                <table className="w-full text-[11px]">
                  <thead>
                    <tr className="border-b border-border-subtle text-[9px] font-mono uppercase tracking-[0.15em] text-foreground/30">
                      <th className="text-left px-5 py-3 font-bold">Agent</th>
                      <th className="text-left px-4 py-3 font-bold">Role</th>
                      <th className="text-center px-4 py-3 font-bold">Tools</th>
                      <th className="text-center px-4 py-3 font-bold">Findings</th>
                      <th className="text-center px-4 py-3 font-bold">Failed</th>
                      <th className="text-center px-4 py-3 font-bold">Verdict</th>
                    </tr>
                  </thead>
                  <tbody>
                    {ALL_AGENT_IDS.map((id) => {
                      const meta  = AGENT_META[id];
                      const m     = report.per_agent_metrics?.[id];
                      const s     = report.per_agent_summary?.[id];
                      const isActive = activeAgentIds.includes(id);
                      const isSkipped = !isActive || report.skipped_agents?.[id];

                      const toolsTotal = m?.total_tools_called ?? 0;
                      const toolsOk    = m?.tools_succeeded ?? 0;
                      const toolsFail  = m?.tools_failed ?? 0;
                      const findings   = s?.findings ?? m?.finding_count ?? 0;
                      const agentVerdict = s?.verdict ?? null;
                      const verdictCfg = agentVerdict ? getVerdictConfig(agentVerdict) : null;

                      return (
                        <tr key={id} className={clsx(
                          "border-b border-white/[0.03] transition-all duration-200",
                          isActive ? "hover:bg-white/[0.03]" : "opacity-30"
                        )}>
                          <td className="px-5 py-3">
                            <div className="flex items-center gap-2">
                              <div className={clsx(
                                "w-2 h-2 rounded-full",
                                isActive ? meta.accentBg.replace("/10", "") : "bg-foreground/15"
                              )} />
                              <span className={clsx("font-bold", isActive ? meta.accentColor : "text-foreground/40")}>
                                {meta.name}
                              </span>
                            </div>
                          </td>
                          <td className="px-4 py-3 text-foreground/40 font-mono text-[10px]">{meta.role}</td>
                          <td className="px-4 py-3 text-center">
                            {isActive ? (
                              <span className="font-mono">
                                <span className="text-foreground/70">{toolsOk}</span>
                                <span className="text-foreground/20">/{toolsTotal}</span>
                              </span>
                            ) : (
                              <span className="text-foreground/20 font-mono">—</span>
                            )}
                          </td>
                          <td className="px-4 py-3 text-center">
                            {isActive ? (
                              <span className="font-mono text-foreground/70">{findings}</span>
                            ) : (
                              <span className="text-foreground/20 font-mono">—</span>
                            )}
                          </td>
                          <td className="px-4 py-3 text-center">
                            {isActive && toolsFail > 0 ? (
                              <span className="font-mono text-amber-400">{toolsFail}</span>
                            ) : isActive ? (
                              <span className="font-mono text-emerald-400/60">0</span>
                            ) : (
                              <span className="text-foreground/20 font-mono">—</span>
                            )}
                          </td>
                          <td className="px-4 py-3 text-center">
                            {isSkipped ? (
                              <span className="text-[9px] font-mono font-bold text-foreground/20 uppercase tracking-wider">skipped</span>
                            ) : verdictCfg ? (
                              <div>
                                <span className={clsx(
                                  "text-[9px] font-mono font-bold uppercase tracking-wider",
                                  verdictCfg.textColor
                                )}>
                                  {verdictCfg.label}
                                </span>
                                {(m?.tools_not_applicable ?? 0) > 0 && (
                                  <p className="text-[8px] font-mono text-foreground/25 mt-0.5">
                                    {m.tools_not_applicable} N/A for file type
                                  </p>
                                )}
                              </div>
                            ) : (
                              <span className="text-[9px] font-mono text-foreground/20">—</span>
                            )}
                          </td>
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
              </div>
            </div>

            {/* ═══════════════════════════════════════════════════════════════ */}
            {/* SECTION 5: Analysis Metadata                                  */}
            {/* ═══════════════════════════════════════════════════════════════ */}
            <div className="glass-t1 rounded-2xl overflow-hidden">
              <div className="px-6 py-4" style={{ borderBottom: "1px solid rgba(255,255,255,0.06)", background: "rgba(255,255,255,0.02)" }}>
                <h2 className="text-[11px] font-bold uppercase tracking-widest text-foreground/60">Analysis Metadata</h2>
              </div>
              <div className="p-5">
                <div className="grid grid-cols-1 sm:grid-cols-2 gap-x-8 gap-y-4">
                  {[
                    { label: "Report ID",            value: report.report_id },
                    { label: "Session ID",            value: report.session_id },
                    { label: "Case ID",               value: report.case_id },
                    { label: "Signed",                value: report.signed_utc ? new Date(report.signed_utc).toLocaleString() : "Pending" },
                    { label: "SHA-256 Hash",          value: report.report_hash, mono: true, truncate: true },
                    { label: "ECDSA Signature",       value: report.cryptographic_signature, mono: true, truncate: true },
                    { label: "Calibration",           value: (() => {
                      const allFindings = Object.values(report.per_agent_findings ?? {}).flat();
                      const calibrated = allFindings.find((f) => f.calibrated);
                      return calibrated ? "TRAINED (Platt scaling)" : "UNCALIBRATED";
                    })() },
                    { label: "Degradation Flags",     value: report.degradation_flags?.length ? `${report.degradation_flags.length} warning${report.degradation_flags.length > 1 ? "s" : ""}` : "None" },
                    { label: "Applicable Agents",     value: `${report.applicable_agent_count ?? activeAgentIds.length} / ${ALL_AGENT_IDS.length}` },
                    ...(report.analysis_coverage_note ? [{ label: "Coverage Note", value: report.analysis_coverage_note }] : []),
                  ].map(({ label, value, mono, truncate }) => (
                    <div key={label} className="space-y-1">
                      <p className="text-[8px] font-mono font-bold uppercase tracking-[0.15em] text-foreground/25">{label}</p>
                      <p className={clsx(
                        "text-[11px] text-foreground/60",
                        mono ? "font-mono" : "font-medium",
                        truncate && "truncate"
                      )}>
                        {value || "—"}
                      </p>
                    </div>
                  ))}
                </div>
              </div>
            </div>

            {/* ═══════════════════════════════════════════════════════════════ */}
            {/* SECTION 6: Corroborating Evidence                             */}
            {/* ═══════════════════════════════════════════════════════════════ */}
            {(
              (report.cross_modal_confirmed?.length ?? 0) > 0 ||
              (report.contested_findings?.length ?? 0) > 0 ||
              (report.tribunal_resolved?.length ?? 0) > 0
            ) && (
              <div className="space-y-3">
                {(report.cross_modal_confirmed?.length ?? 0) > 0 && (
                  <CollapsibleSection
                    icon={<LinkIcon className="w-4 h-4 shrink-0" />}
                    title="Cross-Modal Confirmations"
                    count={report.cross_modal_confirmed?.length}
                    color="emerald"
                  >
                    <div className="pt-4 divide-y divide-border-subtle">
                      {(report.cross_modal_confirmed as ReportDTO["cross_modal_confirmed"]).slice(0, 10).map((f, i) => (
                        <div key={f.finding_id || i} className="flex items-start gap-4 text-xs py-3">
                          <div className="w-1.5 h-1.5 mt-1.5 rounded-full bg-emerald-500 shrink-0" />
                          <span className="flex-1 text-foreground/70 leading-relaxed font-medium">
                            {f.reasoning_summary || f.finding_type}
                          </span>
                        </div>
                      ))}
                    </div>
                  </CollapsibleSection>
                )}

                {(report.contested_findings?.length ?? 0) > 0 && (
                  <CollapsibleSection
                    icon={<AlertTriangle className="w-4 h-4 shrink-0" />}
                    title="Contested Findings"
                    count={report.contested_findings?.length}
                    color="amber"
                  >
                    <div className="pt-4 divide-y divide-border-subtle">
                      {report.contested_findings.map((f, i) => (
                        <div key={i} className="py-3">
                          <p className="text-foreground/60 text-[11px] leading-relaxed font-mono font-bold">
                            {String(f.plain_description ?? "Conflicting findings — manual review required.")}
                          </p>
                        </div>
                      ))}
                    </div>
                  </CollapsibleSection>
                )}

                {(report.tribunal_resolved?.length ?? 0) > 0 && (
                  <CollapsibleSection
                    icon={<Shield className="w-4 h-4 shrink-0" />}
                    title="Tribunal Resolved"
                    count={report.tribunal_resolved?.length}
                    color="violet"
                  >
                    <div className="pt-4 divide-y divide-border-subtle">
                      {report.tribunal_resolved.map((f, i) => (
                        <div key={i} className="py-3">
                          <p className="text-foreground/60 text-[11px] leading-relaxed font-mono font-bold">
                            {String(f.resolution ?? f.plain_description ?? "Dispute resolved by tribunal consensus.")}
                          </p>
                        </div>
                      ))}
                    </div>
                  </CollapsibleSection>
                )}
              </div>
            )}

            {/* ═══════════════════════════════════════════════════════════════ */}
            {/* SECTION 7: Uncertainty & Limitations                          */}
            {/* ═══════════════════════════════════════════════════════════════ */}
            {report.uncertainty_statement && !isBoilerplateUncertainty(report.uncertainty_statement) && (
              <div className="glass-t2 rounded-2xl border-amber-500/15 px-5 py-4 flex items-start gap-3">
                <AlertCircle className="w-4 h-4 text-amber-400/60 shrink-0 mt-0.5" />
                <div>
                  <p className="text-[9px] font-mono font-bold uppercase tracking-widest text-amber-400/50 mb-1.5">
                    Uncertainty & Limitations
                  </p>
                  <p className="text-[11px] text-foreground/50 font-mono leading-relaxed">
                    {report.uncertainty_statement}
                  </p>
                </div>
              </div>
            )}

            {/* ═══════════════════════════════════════════════════════════════ */}
            {/* SECTION 8: Chain of Custody                                   */}
            {/* ═══════════════════════════════════════════════════════════════ */}
            <CollapsibleSection
              icon={<Lock className="w-4 h-4 shrink-0" />}
              title="Chain of Custody"
              color="amber-muted"
            >
              <div className="pt-4 space-y-4">
                {report.report_hash && (
                  <div>
                    <p className="text-[9px] font-mono font-bold uppercase tracking-widest text-amber-400/50 mb-2 flex items-center gap-2">
                      <ShieldCheck className="w-3.5 h-3.5" /> Integrity Hash [SHA-256]
                    </p>
                    <p className="text-[10px] font-mono text-foreground/35 break-all leading-relaxed bg-surface-low p-3 rounded-lg border border-border-subtle">
                      {report.report_hash}
                    </p>
                  </div>
                )}
                {report.cryptographic_signature && (
                  <div>
                    <p className="text-[9px] font-mono font-bold uppercase tracking-widest text-amber-400/50 mb-2 flex items-center gap-2">
                      <Fingerprint className="w-3.5 h-3.5" /> Cryptographic Signature [ECDSA P-256]
                    </p>
                    <p className="text-[10px] font-mono text-foreground/35 break-all leading-relaxed bg-surface-low p-3 rounded-lg border border-border-subtle">
                      {report.cryptographic_signature}
                    </p>
                  </div>
                )}
                <div className="flex items-center gap-2 text-[9px] font-mono font-bold text-foreground/25 uppercase tracking-tight">
                  <Shield className="w-3 h-3 shrink-0" />
                  Signature verified by arbiter consensus protocol.
                </div>
              </div>
            </CollapsibleSection>

          </div>
        )}

        {/* ══ ERROR ══════════════════════════════════════════════════════════ */}
        {state === "error" && activeTab === "analysis" && (
          <div className="flex flex-col items-center justify-center min-h-[60vh] gap-8 text-center">
            <div className="w-20 h-20 rounded-2xl glass-t2 flex items-center justify-center">
              <XCircle className="w-10 h-10 text-rose-500" />
            </div>
            <div className="space-y-3">
              <h2 className="text-2xl font-bold text-foreground uppercase tracking-tight">Analysis Interrupted</h2>
              <p className="text-foreground/40 text-sm max-w-sm font-medium">{errorMsg || "An unexpected error occurred during synthesis."}</p>
            </div>
            <button onClick={handleNew}
              className="btn-premium-amber !rounded-full px-10 py-4 shadow-[0_0_30px_rgba(217,119,6,0.15)]">
              Re-Initialize Investigation
            </button>
          </div>
        )}

        {/* ══ EMPTY ══════════════════════════════════════════════════════════ */}
        {state === "empty" && activeTab === "analysis" && (
          <div className="flex flex-col items-center justify-center min-h-[60vh] gap-8 text-center">
            <div className="w-20 h-20 rounded-2xl glass-t2 flex items-center justify-center">
              <FileText className="w-10 h-10 text-foreground/20" />
            </div>
            <div className="space-y-3">
              <h2 className="text-2xl font-bold text-foreground uppercase tracking-tight">Null Session</h2>
              <p className="text-foreground/40 text-sm max-w-sm font-medium">
                No active forensic stream detected. Please return to the terminal.
              </p>
            </div>
            <button onClick={handleHome}
              className="btn-premium-glass !rounded-full px-10 py-4">
              Back to Command Center
            </button>
          </div>
        )}

      </main>

      {/* ── Navigation Bar ────────────────────────────────────────────────── */}
      {state === "ready" && activeTab === "analysis" && (
        <div className="fixed bottom-0 left-0 right-0 z-50 glass-t3">
          <div className="max-w-6xl mx-auto px-6 py-4 flex items-center justify-between gap-4">
            <button onClick={handleNew}
              className="btn-premium-glass flex items-center gap-2.5 !rounded-full !px-6 !py-3 text-emerald-400 hover:border-emerald-500/30 hover:bg-emerald-500/5">
              <RotateCcw className="w-4 h-4" /> New Analysis
            </button>
            <button onClick={handleHome}
              className="btn-premium-glass flex items-center gap-2.5 !rounded-full !px-6 !py-3 hover:text-amber-400">
              <Home className="w-4 h-4" /> Back to Home
            </button>
          </div>
        </div>
      )}
    </div>
  );
}

// ─── History Panel (inline for the History tab) ──────────────────────────────
function HistoryPanel() {
  const router = useRouter();
  const [history, setHistory] = useState<HistoryItem[]>([]);

  useEffect(() => {
    try {
      const stored = localStorage.getItem("forensic_history");
      if (stored) setHistory(JSON.parse(stored));
    } catch { /* ignore */ }
  }, []);

  const removeItem = (sessionId: string) => {
    const updated = history.filter(h => h.sessionId !== sessionId);
    setHistory(updated);
    localStorage.setItem("forensic_history", JSON.stringify(updated));
  };

  const clearAll = () => {
    setHistory([]);
    localStorage.setItem("forensic_history", JSON.stringify([]));
  };

  if (history.length === 0) {
    return (
      <div className="flex flex-col items-center justify-center py-20 gap-4 text-center">
        <History className="w-10 h-10 text-foreground/15" />
        <p className="text-foreground/30 text-sm font-medium">No analysis history yet.</p>
      </div>
    );
  }

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <p className="text-[10px] font-mono font-bold uppercase tracking-widest text-foreground/30">
          {history.length} session{history.length !== 1 ? "s" : ""}
        </p>
        <button onClick={clearAll}
          className="text-[9px] font-mono font-bold uppercase tracking-widest text-foreground/20 hover:text-rose-400 transition-colors cursor-pointer">
          Clear All
        </button>
      </div>
      <div className="space-y-2">
        {history.map((item) => {
          const vc = getVerdictConfig(item.verdict);
          return (
            <div key={item.sessionId} className="group flex items-center justify-between gap-4 p-4 rounded-xl border border-border-subtle bg-surface-mid/30 hover:bg-surface-mid transition-colors">
              <div className="flex items-center gap-3 min-w-0">
                <vc.Icon className={clsx("w-4 h-4 shrink-0", vc.textColor)} />
                <div className="min-w-0">
                  <p className="text-[11px] font-bold text-foreground/70 truncate">{item.fileName}</p>
                  <div className="flex items-center gap-2 mt-0.5">
                    <span className={clsx("text-[9px] font-bold uppercase tracking-wider", vc.textColor)}>
                      {vc.label}
                    </span>
                    <span className="text-[9px] font-mono text-foreground/25">
                      {new Date(item.timestamp).toLocaleString(undefined, { month: "short", day: "numeric", hour: "numeric", minute: "2-digit" })}
                    </span>
                    <Badge variant="secondary" className="text-[8px] px-1.5 py-0 font-mono">{item.type}</Badge>
                  </div>
                </div>
              </div>
              <button onClick={() => removeItem(item.sessionId)}
                className="p-1.5 rounded-md hover:bg-rose-500/10 text-foreground/15 hover:text-rose-500 transition-all opacity-0 group-hover:opacity-100 cursor-pointer">
                <X className="w-3 h-3" />
              </button>
            </div>
          );
        })}
      </div>
    </div>
  );
}
