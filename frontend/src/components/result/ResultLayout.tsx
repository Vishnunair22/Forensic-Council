"use client";

import React, { useState, useEffect, useMemo, useRef, useCallback } from "react";
import {
  AlertTriangle,
  ShieldCheck,
  RotateCcw,
  Home,
  ChevronDown,
  Lock,
  FileText,
  Shield,
  XCircle,
  Download,
  LinkIcon,
  Fingerprint,
  Image as ImageIcon,
  Film,
  Mic,
  AlertCircle,
  Activity,
  Info,
  History,
  X,
  Zap,
  Layers,
  Clock,
  Target,
  ArrowRight,
  BarChart2,
  Award,
  Search,
  Cpu,
  Hash,
  Trash2,
} from "lucide-react";
import { useRouter } from "next/navigation";
import clsx from "clsx";
import { useForensicData, mapReportDtoToReport } from "@/hooks/useForensicData";
import { useSound } from "@/hooks/useSound";
import { type HistoryItem } from "@/components/ui/HistoryDrawer";
import {
  getReport,
  getArbiterStatus,
  type ReportDTO,
  type AgentMetricsDTO,
  type AgentFindingDTO,
} from "@/lib/api";
import { getVerdictConfig } from "@/lib/verdict";
import { AgentFindingCard } from "@/components/ui/AgentFindingCard";
import { ForensicProgressOverlay } from "@/components/ui/ForensicProgressOverlay";
import type { AgentUpdate } from "@/components/evidence/AgentProgressDisplay";
import { DeepModelTelemetry } from "@/components/result/DeepModelTelemetry";
import { TribunalMatrix } from "@/components/result/TribunalMatrix";
import { EvidenceGraph } from "@/components/result/EvidenceGraph";
import { ResultHeader } from "./ResultHeader";
import { AgentAnalysisTab } from "./AgentAnalysisTab";
import { TimelineTab } from "./TimelineTab";
import { MetricsPanel } from "./MetricsPanel";
import { ReportFooter } from "./ReportFooter";

const isDev = process.env.NODE_ENV !== "production";
const dbg = { error: isDev ? console.error.bind(console) : () => {} };

const ALL_AGENT_IDS = ["Agent1", "Agent2", "Agent3", "Agent4", "Agent5"];

const AGENT_META: Record<
  string,
  {
    name: string;
    role: string;
    accentColor: string;
    accentBg: string;
    accentBorder: string;
    accentFill: string;
  }
> = {
  Agent1: {
    name: "Image Integrity Expert",
    role: "Image Integrity",
    accentColor: "text-cyan-400",
    accentBg: "bg-cyan-500/10",
    accentBorder: "border-cyan-500/30",
    accentFill: "#22d3ee",
  },
  Agent2: {
    name: "Audio Forensics Expert",
    role: "Audio Forensics",
    accentColor: "text-indigo-400",
    accentBg: "bg-indigo-500/10",
    accentBorder: "border-indigo-500/30",
    accentFill: "#818cf8",
  },
  Agent3: {
    name: "Object & Weapon Analyst",
    role: "Object & Weapons",
    accentColor: "text-sky-400",
    accentBg: "bg-sky-500/10",
    accentBorder: "border-sky-500/30",
    accentFill: "#38bdf8",
  },
  Agent4: {
    name: "Temporal Video Analyst",
    role: "Temporal Video",
    accentColor: "text-teal-400",
    accentBg: "bg-teal-500/10",
    accentBorder: "border-teal-500/30",
    accentFill: "#2dd4bf",
  },
  Agent5: {
    name: "Metadata & Context Expert",
    role: "Metadata & Context",
    accentColor: "text-blue-400",
    accentBg: "bg-blue-500/10",
    accentBorder: "border-blue-500/30",
    accentFill: "#60a5fa",
  },
};

type Tab = "analysis" | "history";
type PageState = "arbiter" | "ready" | "error" | "empty";

export function ResultLayout() {
  const router = useRouter();
  const [mounted, setMounted] = useState(false);
  const [state, setState] = useState<PageState>("arbiter");
  const [report, setReport] = useState<ReportDTO | null>(null);
  const [arbiterMsg, setArbiterMsg] = useState("");
  const [errorMsg, setErrorMsg] = useState("");
  const [activeTab, setActiveTab] = useState<Tab>("analysis");
  const [isDeepPhase, setIsDeepPhase] = useState(false);
  const [thumbnail, setThumbnail] = useState<string | null>(null);
  const [mimeType, setMimeType] = useState<string | null>(null);
  const [agentTimeline, setAgentTimeline] = useState<AgentUpdate[]>([]);
  const [pipelineStartAt, setPipelineStartAt] = useState<string | null>(null);
  const historySavedRef = useRef(false);
  const historyPanelRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    setIsDeepPhase(sessionStorage.getItem("forensic_is_deep") === "true");
    setThumbnail(sessionStorage.getItem("forensic_thumbnail"));
    setMimeType(sessionStorage.getItem("forensic_mime_type"));
    setPipelineStartAt(sessionStorage.getItem("forensic_pipeline_start"));
    try {
      const key =
        sessionStorage.getItem("forensic_is_deep") === "true"
          ? "forensic_deep_agents"
          : "forensic_initial_agents";
      const stored = sessionStorage.getItem(key);
      if (stored) setAgentTimeline(JSON.parse(stored));
    } catch {
    }
  }, []);

  const { addToHistory } = useForensicData();
  const { playSound } = useSound();
  const soundRef = useRef(playSound);
  useEffect(() => {
    soundRef.current = playSound;
  }, [playSound]);

  useEffect(() => {
    const sessionId = sessionStorage.getItem("forensic_session_id");
    if (!sessionId) {
      setState("empty");
      return;
    }

    const sid = sessionId;
    let cancelled = false;
    let timer: ReturnType<typeof setTimeout>;
    let attempts = 0;
    const MAX = 60;

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
              try {
                addToHistory(mapReportDtoToReport(res.report));
              } catch (e) {
                dbg.error("addToHistory failed:", e);
              }
              try {
                const stored = sessionStorage.getItem("fc_full_report_history");
                const hist: ReportDTO[] = stored ? JSON.parse(stored) : [];
                const snap = res.report;
                if (snap && !hist.some((r) => r.report_id === snap.report_id)) {
                  const serialised = JSON.stringify(
                    [snap, ...hist].slice(0, 20),
                  );
                  if (serialised.length < 4_000_000) {
                    sessionStorage.setItem(
                      "fc_full_report_history",
                      serialised,
                    );
                  }
                }
              } catch {
              }
              setTimeout(() => soundRef.current("arbiter_done"), 150);
              return;
            }
          } catch (e) {
            dbg.error("getReport failed:", e);
          }
        } else if (s.status === "error") {
          setErrorMsg(s.message || "Investigation failed");
          setState("error");
          return;
        } else {
          setArbiterMsg(s.message || "");
          try {
            const res = await getReport(sid);
            if (!cancelled && res.status === "complete" && res.report) {
              setReport(res.report);
              setState("ready");
              try {
                addToHistory(mapReportDtoToReport(res.report));
              } catch (e) {
                dbg.error("addToHistory failed:", e);
              }
              setTimeout(() => soundRef.current("arbiter_done"), 150);
              return;
            }
          } catch (e) {
            dbg.error("getReport during polling failed:", e);
          }
        }
      } catch (e) {
        dbg.error("getArbiterStatus failed:", e);
      }

      if (!cancelled && attempts < MAX) {
        timer = setTimeout(poll, 2000);
      } else if (!cancelled) {
        setErrorMsg("Arbiter timed out. The session may have expired.");
        setState("error");
      }
    }

    poll();
    return () => {
      cancelled = true;
      clearTimeout(timer);
    };
  }, []);

  useEffect(() => {
    setMounted(true);
  }, []);

  const activeAgentIds = useMemo(() => {
    const SKIP_TYPES = new Set([
      "file type not applicable",
      "format not supported",
    ]);
    return Object.keys(report?.per_agent_findings ?? {}).filter((id) => {
      const flist = report?.per_agent_findings[id] ?? [];
      return (
        flist.length > 0 &&
        !flist.every((f) =>
          SKIP_TYPES.has(String(f.finding_type).toLowerCase()),
        )
      );
    });
  }, [report]);

  const keyFindings = useMemo(() => {
    if (report?.key_findings && report.key_findings.length > 0)
      return report.key_findings;
    const SKIP_TYPES = new Set([
      "file type not applicable",
      "format not supported",
    ]);
    const summaries: string[] = [];
    for (const id of activeAgentIds) {
      const findings = report?.per_agent_findings[id] ?? [];
      for (const f of findings) {
        if (SKIP_TYPES.has(String(f.finding_type).toLowerCase())) continue;
        const s = f.reasoning_summary?.trim();
        if (s && s.length > 10 && !summaries.includes(s)) summaries.push(s);
      }
    }
    return summaries.slice(0, 8);
  }, [report, activeAgentIds]);

  const vc = report ? getVerdictConfig(report.overall_verdict ?? "") : null;
  const confPct = Math.round((report?.overall_confidence ?? 0) * 100);
  const errPct = Math.round((report?.overall_error_rate ?? 0) * 100);
  const manipPct = Math.round((report?.manipulation_probability ?? 0) * 100);

  const fileName = useMemo(() => {
    if (typeof window === "undefined")
      return report?.case_id ?? "Evidence File";
    return (
      sessionStorage.getItem("forensic_file_name") ||
      report?.case_id ||
      "Evidence File"
    );
  }, [report]);

  const pipelineDuration = useMemo(() => {
    if (pipelineStartAt && report?.signed_utc) {
      return fmtDuration(pipelineStartAt, report.signed_utc);
    }
    if (agentTimeline.length > 0 && pipelineStartAt) {
      const lastAgent = agentTimeline[agentTimeline.length - 1];
      if (lastAgent?.completed_at)
        return fmtDuration(pipelineStartAt, lastAgent.completed_at);
    }
    return null;
  }, [pipelineStartAt, report, agentTimeline]);

  useEffect(() => {
    if (state === "ready" && report && !historySavedRef.current) {
      historySavedRef.current = true;
      const hItem: HistoryItem = {
        sessionId: report.session_id,
        fileName:
          sessionStorage.getItem("forensic_file_name") || "Unknown File",
        verdict: report.overall_verdict || "INCONCLUSIVE",
        timestamp: Date.now(),
        type: isDeepPhase ? "Deep" : "Initial",
        thumbnail: sessionStorage.getItem("forensic_thumbnail") || undefined,
        mime: sessionStorage.getItem("forensic_mime_type") || undefined,
      };
      try {
        const stored = JSON.parse(
          localStorage.getItem("forensic_history") || "[]",
        ) as HistoryItem[];
        const filtered = stored.filter((h) => h.sessionId !== hItem.sessionId);
        localStorage.setItem(
          "forensic_history",
          JSON.stringify([hItem, ...filtered]),
        );
      } catch (e) {
        dbg.error("Failed to commit history", e);
      }
    }
  }, [state, report, isDeepPhase]);

  const handleNew = useCallback(() => {
    playSound("click");
    [
      "forensic_session_id",
      "forensic_file_name",
      "forensic_case_id",
      "forensic_thumbnail",
    ].forEach((k) => sessionStorage.removeItem(k));
    router.push("/evidence", { scroll: true });
  }, [playSound, router]);

  const handleHome = useCallback(() => {
    playSound("click");
    router.push("/", { scroll: true });
  }, [playSound, router]);

  const handleExport = useCallback(() => {
    if (!report) return;
    const blob = new Blob([JSON.stringify(report, null, 2)], {
      type: "application/json",
    });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = `forensic-report-${report.report_id.slice(0, 8)}.json`;
    a.click();
    URL.revokeObjectURL(url);
  }, [report]);

  if (!mounted) {
    return (
      <div className="min-h-screen text-foreground flex items-center justify-center px-6">
        <div className="w-full max-w-md rounded-3xl border border-white/[0.08] bg-white/[0.03] p-6 text-center backdrop-blur-xl">
          <p className="text-[11px] font-mono font-bold uppercase tracking-[0.22em] text-cyan-400/80">
            Loading Session
          </p>
          <p className="mt-3 text-sm text-foreground/55">
            Restoring the latest forensic view.
          </p>
        </div>
      </div>
    );
  }

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

      <div
        className="w-full sticky top-[60px] z-40 transition-all duration-300"
        style={{
          background: "rgba(8,8,12,0.85)",
          backdropFilter: "blur(20px)",
          WebkitBackdropFilter: "blur(20px)",
          borderBottom: "1px solid rgba(255,255,255,0.05)",
        }}
      >
        <div className="max-w-5xl mx-auto px-6 py-3 flex items-center justify-center gap-4">
          <button
            onClick={handleExport}
            className="flex items-center gap-1.5 px-3.5 py-1.5 rounded-full text-[10px] font-bold uppercase tracking-wider text-foreground/40 hover:text-foreground/70 border border-white/[0.07] bg-white/[0.03] hover:bg-white/[0.06] transition-all cursor-pointer"
          >
            <Download className="w-3 h-3" /> Export
          </button>

          <div
            role="tablist"
            aria-label="Analysis views"
            className="flex gap-1 p-1 rounded-full"
            style={{
              background: "rgba(255,255,255,0.02)",
              border: "1px solid rgba(255,255,255,0.05)",
              boxShadow: "inset 0 2px 10px rgba(0,0,0,0.5)",
            }}
            onKeyDown={(e) => {
              const tabs = ["analysis", "history"] as Tab[];
              const currentIndex = tabs.indexOf(activeTab);
              let newIndex = currentIndex;
              if (e.key === "ArrowRight") {
                e.preventDefault();
                newIndex = (currentIndex + 1) % tabs.length;
                setActiveTab(tabs[newIndex]);
              } else if (e.key === "ArrowLeft") {
                e.preventDefault();
                newIndex = (currentIndex - 1 + tabs.length) % tabs.length;
                setActiveTab(tabs[newIndex]);
              } else if (e.key === "Home") {
                e.preventDefault();
                setActiveTab(tabs[0]);
              } else if (e.key === "End") {
                e.preventDefault();
                setActiveTab(tabs[tabs.length - 1]);
              }
            }}
          >
            {(["analysis", "history"] as Tab[]).map((tab) => (
              <button
                key={tab}
                role="tab"
                id={`tab-${tab}`}
                aria-selected={activeTab === tab}
                aria-controls={`panel-${tab}`}
                onClick={() => setActiveTab(tab)}
                className={clsx(
                  "px-5 py-2 rounded-full text-[10px] font-bold uppercase tracking-[0.18em] transition-all duration-300 cursor-pointer flex items-center gap-2",
                  activeTab === tab
                    ? "bg-cyan-500/15 text-cyan-300 border border-cyan-500/25 shadow-[0_4px_20px_rgba(34,211,238,0.15)]"
                    : "text-foreground/40 hover:text-foreground/70 hover:bg-white/[0.04] border border-transparent",
                )}
              >
                {tab === "analysis" ? (
                  <Activity className="w-3.5 h-3.5" aria-hidden="true" />
                ) : (
                  <History className="w-3.5 h-3.5" aria-hidden="true" />
                )}
                {tab === "analysis" ? "Current Analysis" : "History"}
              </button>
            ))}
          </div>

          <div
            className={clsx(
              "text-[9px] font-mono font-bold uppercase tracking-widest px-3 py-1 rounded-full border",
              isDeepPhase
                ? "text-violet-400 border-violet-500/30 bg-violet-500/10"
                : "text-cyan-400 border-cyan-500/25 bg-cyan-500/10",
            )}
          >
            {isDeepPhase ? "Deep" : "Initial"}
          </div>
        </div>
      </div>

      {activeTab === "history" && (
        <main
          ref={historyPanelRef}
          role="tabpanel"
          id="panel-history"
          aria-labelledby="tab-history"
          className="max-w-5xl mx-auto px-6 pt-8 pb-24 relative"
        >
          <HistoryPanel onDismiss={() => setActiveTab("analysis")} />
        </main>
      )}

      {activeTab === "analysis" && (
        <main
          role="tabpanel"
          id="panel-analysis"
          aria-labelledby="tab-analysis"
          className="max-w-5xl mx-auto px-6 pt-6 pb-16 space-y-6"
        >
          {state === "arbiter" && (
            <div className="flex flex-col items-center justify-center min-h-[60vh] gap-6 text-center">
              <div className="w-16 h-16 rounded-2xl flex items-center justify-center bg-white/[0.03] border border-white/[0.06]">
                <Activity className="w-7 h-7 text-amber-400 animate-pulse" />
              </div>
              <p className="text-foreground/40 text-sm font-medium font-mono">
                Council deliberating…
              </p>
            </div>
          )}

          {state === "error" && (
            <div className="flex flex-col items-center justify-center min-h-[60vh] gap-8 text-center">
              <div className="w-20 h-20 rounded-2xl flex items-center justify-center bg-white/[0.03] border border-white/[0.06]">
                <XCircle className="w-10 h-10 text-rose-500" />
              </div>
              <div className="space-y-2">
                <h2 className="text-2xl font-bold text-foreground uppercase tracking-tight">
                  Analysis Interrupted
                </h2>
                <p className="text-foreground/40 text-sm max-w-sm font-medium">
                  {errorMsg || "An unexpected error occurred during synthesis."}
                </p>
              </div>
              <div className="flex gap-3">
                <button
                  onClick={handleNew}
                  className="btn-pill-primary text-xs"
                >
                  <RotateCcw className="w-4 h-4" /> New Analysis
                </button>
                <button
                  onClick={handleHome}
                  className="btn-pill-secondary text-xs"
                >
                  <Home className="w-4 h-4" /> Back to Home
                </button>
              </div>
            </div>
          )}

          {state === "empty" && (
            <div className="flex flex-col items-center justify-center min-h-[60vh] gap-8 text-center">
              <div className="w-20 h-20 rounded-2xl flex items-center justify-center bg-white/[0.03] border border-white/[0.06]">
                <FileText className="w-10 h-10 text-foreground/20" />
              </div>
              <div className="space-y-2">
                <h2 className="text-2xl font-bold text-foreground uppercase tracking-tight">
                  Null Session
                </h2>
                <p className="text-foreground/40 text-sm max-w-sm font-medium">
                  No active forensic stream detected. Please return to the
                  terminal.
                </p>
              </div>
              <div className="flex gap-3">
                <button
                  onClick={handleNew}
                  className="btn-pill-primary text-xs"
                >
                  <Search className="w-4 h-4" /> New Investigation
                </button>
                <button
                  onClick={handleHome}
                  className="btn-pill-secondary text-xs"
                >
                  <Home className="w-4 h-4" /> Back to Home
                </button>
              </div>
            </div>
          )}

          {state === "ready" && report && vc && (
            <div className="space-y-6">
              {report.degradation_flags &&
                report.degradation_flags.length > 0 && (
                  <div className="rounded-2xl border border-amber-500/40 bg-amber-500/[0.07] p-4 flex items-start gap-3">
                    <AlertCircle className="w-4 h-4 text-amber-400 shrink-0 mt-0.5" />
                    <div>
                      <p className="text-[9px] font-black font-mono uppercase tracking-[0.25em] text-amber-400 mb-1.5">
                        Degraded Analysis Mode
                      </p>
                      <ul className="space-y-0.5">
                        {report.degradation_flags.map((f, i) => (
                          <li
                            key={i}
                            className="text-[11px] text-amber-300/70 font-mono leading-relaxed"
                          >
                            • {f}
                          </li>
                        ))}
                      </ul>
                    </div>
                  </div>
                )}

              <ResultHeader
                report={report}
                fileName={fileName}
                mimeType={mimeType}
                thumbnail={thumbnail}
                isDeepPhase={isDeepPhase}
                vc={vc}
                confPct={confPct}
                errPct={errPct}
                manipPct={manipPct}
                activeAgentIds={activeAgentIds}
                pipelineDuration={pipelineDuration}
              />

              {isDeepPhase && <DeepModelTelemetry report={report} />}

              <AgentAnalysisTab
                report={report}
                activeAgentIds={activeAgentIds}
                isDeepPhase={isDeepPhase}
              />

              <TimelineTab
                report={report}
                activeAgentIds={activeAgentIds}
                agentTimeline={agentTimeline}
                pipelineStartAt={pipelineStartAt}
              />

              <MetricsPanel
                report={report}
                activeAgentIds={activeAgentIds}
                keyFindings={keyFindings}
              />

              <ReportFooter
                handleNew={handleNew}
                handleHome={handleHome}
              />
            </div>
          )}
        </main>
      )}
    </div>
  );
}

function fmtDuration(from: string, to: string): string {
  try {
    const ms = new Date(to).getTime() - new Date(from).getTime();
    if (ms < 1000) return `${ms}ms`;
    return `${(ms / 1000).toFixed(1)}s`;
  } catch {
    return "—";
  }
}

function HistoryPanel({ onDismiss }: { onDismiss: () => void }) {
  return (
    <div className="text-center text-foreground/50">
      <p>History panel placeholder</p>
      <button onClick={onDismiss} className="mt-4 text-cyan-400">
        Back to Analysis
      </button>
    </div>
  );
}
