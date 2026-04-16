"use client";

import React, { useMemo, memo } from "react";
import { 
  Home as HomeIcon, 
  XCircle, 
  Activity, 
  History as HistoryIcon, 
  Search,
  Download
} from "lucide-react";
import clsx from "clsx";
import { type Tab, useResult } from "@/hooks/useResult";
import { getVerdictConfig } from "@/lib/verdict";
import { ForensicProgressOverlay } from "@/components/ui/ForensicProgressOverlay";
import { DeepModelTelemetry } from "@/components/result/DeepModelTelemetry";
import { ResultHeader } from "./ResultHeader";
import { AgentAnalysisTab } from "./AgentAnalysisTab";
import { TimelineTab } from "./TimelineTab";
import { MetricsPanel } from "./MetricsPanel";
import { ReportFooter } from "./ReportFooter";

// We import the finding types to eliminate 'any' casts
interface BaseFinding {
  finding_type?: string;
  reasoning_summary?: string;
  [key: string]: unknown;
}

const MemoizedResultHeader = memo(ResultHeader);
const MemoizedAgentAnalysisTab = memo(AgentAnalysisTab);
const MemoizedTimelineTab = memo(TimelineTab);
const MemoizedMetricsPanel = memo(MetricsPanel);
const MemoizedReportFooter = memo(ReportFooter);
const MemoizedDeepModelTelemetry = memo(DeepModelTelemetry);

export function ResultLayout() {
  const rs = useResult();

  const activeAgentIds = useMemo(() => {
    const SKIP_TYPES = new Set(["file type not applicable", "format not supported"]);
    return Object.keys(rs.report?.per_agent_findings ?? {}).filter((id) => {
      const flist = (rs.report?.per_agent_findings[id] ?? []) as unknown as BaseFinding[];
      return flist.length > 0 && !flist.every((f) => SKIP_TYPES.has(String(f.finding_type).toLowerCase()));
    });
  }, [rs.report]);

  const keyFindings = useMemo(() => {
    if (rs.report?.key_findings && rs.report.key_findings.length > 0) return rs.report.key_findings;
    const summaries: string[] = [];
    for (const id of activeAgentIds) {
      const findings = (rs.report?.per_agent_findings[id] ?? []) as unknown as BaseFinding[];
      for (const f of findings) {
        const s = f.reasoning_summary?.trim();
        if (s && s.length > 10 && !summaries.includes(s)) summaries.push(s);
      }
    }
    return summaries.slice(0, 8);
  }, [rs.report, activeAgentIds]);

  if (!rs.mounted) {
    return <ResultStateView type="loading" />;
  }

  return (
    <div className="min-h-screen text-foreground selection:bg-cyan-500/20">
      {rs.state === "arbiter" && (
        <ForensicProgressOverlay 
          variant="council" 
          title="Council Deliberation" 
          liveText={rs.arbiterMsg} 
          telemetryLabel="Synthesizing Consensus" 
          showElapsed 
        />
      )}

      {/* Sticky Navigation */}
      <nav className="sticky top-[60px] z-40 w-full bg-[#06090F]/80 backdrop-blur-2xl border-b border-white/[0.05]">
        <div className="max-w-5xl mx-auto px-6 py-4 flex items-center justify-between gap-4">
          <div className="flex items-center gap-4">
            <button 
              onClick={rs.handleExport}
              className="flex items-center gap-2 px-4 py-2 rounded-full text-[10px] font-black uppercase tracking-widest text-white/40 hover:text-[#14b8a6] hover:bg-transparent border border-white/5 hover:border-[#14b8a6] transition-all"
            >
              <Download className="w-3 h-3" /> Export
            </button>
            <div className={clsx(
              "px-3 py-1 rounded-full border text-[9px] font-mono font-black uppercase tracking-widest",
              rs.isDeepPhase ? "text-violet-400 border-violet-500/20 bg-violet-500/5" : "text-[#14b8a6] border-[#14b8a6]/20 bg-[#14b8a6]/5"
            )}>
              {rs.isDeepPhase ? "Deep Analysis" : "Initial Scan"}
            </div>
          </div>

          <div role="tablist" className="bg-white/[0.02] border border-white/5 p-1 rounded-full flex gap-1 shadow-inner">
            {(["analysis", "history"] as Tab[]).map((tab) => (
              <button
                key={tab}
                role="tab"
                aria-selected={rs.activeTab === tab}
                onClick={() => rs.setActiveTab(tab)}
                className={clsx(
                  "px-6 py-2 rounded-full text-[10px] font-black uppercase tracking-[0.2em] transition-all flex items-center gap-2",
                  rs.activeTab === tab 
                    ? "bg-[#14b8a6]/10 text-[#14b8a6] border border-[#14b8a6]/30 shadow-[0_0_15px_rgba(20,184,166,0.1)]" 
                    : "text-white/20 hover:text-white/40 hover:bg-white/[0.02]"
                )}
              >
                {tab === "analysis" ? <Activity className="w-3.5 h-3.5" /> : <HistoryIcon className="w-3.5 h-3.5" />}
                {tab === "analysis" ? "Overview" : "History"}
              </button>
            ))}
          </div>
        </div>
      </nav>

      <main className="max-w-5xl mx-auto px-6 pt-10 pb-24 space-y-8">
        {rs.activeTab === "history" ? (
          <HistoryPanel onDismiss={() => rs.setActiveTab("analysis")} />
        ) : (
          <>
            {rs.state === "error" && (
              <ResultStateView type="error" message={rs.errorMsg} onNew={rs.handleNew} onHome={rs.handleHome} />
            )}
            {rs.state === "empty" && (
              <ResultStateView type="empty" onNew={rs.handleNew} onHome={rs.handleHome} />
            )}
            {rs.state === "arbiter" && (
              <div className="flex flex-col items-center justify-center py-32 gap-6 opacity-40">
                <Activity className="w-8 h-8 text-[#14b8a6] animate-pulse" />
                <p className="font-mono text-xs font-bold uppercase tracking-widest">Awaiting Arbiter Consensus...</p>
              </div>
            )}
            {rs.state === "ready" && rs.report && (
              <div 
                className="sr-only" 
                aria-live="assertive" 
                aria-atomic="true"
              >
                Forensic Analysis Complete. Verdict: {getVerdictConfig(rs.report.overall_verdict ?? "").label}. 
                {rs.report.verdict_sentence}
              </div>
            )}
            {rs.state === "ready" && rs.report && (
              <div className="animate-in fade-in slide-in-from-bottom-4 duration-1000 space-y-8">
                <MemoizedResultHeader 
                  report={rs.report} 
                  fileName={rs.report.case_id || "Evidence 01"} 
                  mimeType={rs.mimeType} 
                  thumbnail={rs.thumbnail} 
                  isDeepPhase={rs.isDeepPhase}
                  vc={getVerdictConfig(rs.report.overall_verdict ?? "")}
                  confPct={Math.round((rs.report.overall_confidence ?? 0) * 100)}
                  errPct={Math.round((rs.report.overall_error_rate ?? 0) * 100)}
                  manipPct={Math.round((rs.report.manipulation_probability ?? 0) * 100)}
                  activeAgentIds={activeAgentIds}
                  pipelineDuration={rs.pipelineStartAt && rs.report.signed_utc ? fmtDuration(rs.pipelineStartAt, rs.report.signed_utc) : "—"}
                />

                {rs.isDeepPhase && <MemoizedDeepModelTelemetry report={rs.report} />}

                <MemoizedAgentAnalysisTab report={rs.report} activeAgentIds={activeAgentIds} isDeepPhase={rs.isDeepPhase} />
                <MemoizedTimelineTab report={rs.report} activeAgentIds={activeAgentIds} agentTimeline={rs.agentTimeline} pipelineStartAt={rs.pipelineStartAt} />
                <MemoizedMetricsPanel report={rs.report} activeAgentIds={activeAgentIds} keyFindings={keyFindings} />
                
                <MemoizedReportFooter handleNew={rs.handleNew} handleHome={rs.handleHome} />
              </div>
            )}
          </>
        )}
      </main>
    </div>
  );
}

function ResultStateView({ type, message, onNew, onHome }: { type: "loading" | "error" | "empty", message?: string, onNew?: () => void, onHome?: () => void }) {
  const configs = {
    loading: { icon: Activity, title: "Restoring Session", desc: "Accessing secure forensic ledger...", color: "text-cyan-400" },
    error: { icon: XCircle, title: "Analysis Interrupted", desc: message || "Protocol violation detected during synthesis.", color: "text-rose-500" },
    empty: { icon: Search, title: "Null Stream", desc: "No active investigation session identified.", color: "text-white/20" }
  };
  const c = configs[type];
  const Icon = c.icon;

  return (
    <div className="min-h-[70vh] flex flex-col items-center justify-center text-center px-6">
      <div className="w-20 h-20 rounded-3xl glass-panel flex items-center justify-center mb-8 border-white/5">
        <Icon className={clsx("w-10 h-10", c.color, type === "loading" && "animate-pulse")} />
      </div>
      <h2 className="text-3xl font-black text-white uppercase tracking-tighter mb-3 font-heading">{c.title}</h2>
      <p className="text-sm font-medium text-white/30 max-w-sm mb-10">{c.desc}</p>
      
      {(onNew || onHome) && (
        <div className="flex gap-4">
          {onNew && <button onClick={onNew} className="btn-pill-primary px-8 py-3 text-[10px]">New Investigation</button>}
          {onHome && <button onClick={onHome} className="btn-pill-secondary px-8 py-3 text-[10px]"><HomeIcon className="w-4 h-4" /> Home</button>}
        </div>
      )}
    </div>
  );
}

function HistoryPanel({ onDismiss }: { onDismiss: () => void }) {
  return (
    <div className="glass-panel rounded-3xl p-12 text-center border-white/5 bg-white/[0.01]">
      <div className="inline-flex w-16 h-16 rounded-2xl bg-white/5 border border-white/10 items-center justify-center mb-6">
        <HistoryIcon className="w-8 h-8 text-white/20" />
      </div>
      <h3 className="text-xl font-black text-white uppercase tracking-tight mb-2">History Archive</h3>
      <p className="text-xs font-medium text-white/25 mb-8">Secure chronological log of past investigations.</p>
      <button onClick={onDismiss} className="text-[10px] font-black uppercase tracking-widest text-cyan-400 hover:text-cyan-300 transition-colors">
        Return to Current Analysis
      </button>
    </div>
  );
}

function fmtDuration(from: string | null, to?: string): string {
  if (!from || !to) return "—";
  try {
    const ms = new Date(to).getTime() - new Date(from).getTime();
    if (ms < 1000) return `${ms}ms`;
    if (ms < 60000) return `${(ms / 1000).toFixed(1)}s`;
    return `${Math.floor(ms / 60000)}m ${Math.floor((ms % 60000) / 1000)}s`;
  } catch {
    return "—";
  }
}
