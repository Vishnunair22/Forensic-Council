"use client";

import React, { useMemo } from "react";
import dynamic from "next/dynamic";
import { Home as HomeIcon, Activity } from "lucide-react";
import { motion } from "framer-motion";
import clsx from "clsx";
import { type Tab, useResult } from "@/hooks/useResult";
import { getVerdictConfig } from "@/lib/verdict";
import { ForensicProgressOverlay } from "@/components/ui/ForensicProgressOverlay";
import { ReportFooter } from "./ReportFooter";
import { IntelligenceBrief } from "./IntelligenceBrief";
import { DegradationBanner } from "./DegradationBanner";
import { ActionDock } from "./ActionDock";
import { ForensicErrorModal } from "@/components/ui/ForensicErrorModal";
import { ResultStateView } from "./ResultStateView";

const AgentAnalysisTab = dynamic(
  () => import("./AgentAnalysisTab").then((m) => m.AgentAnalysisTab),
  { ssr: false },
);
const DeepModelTelemetry = dynamic(
  () => import("@/components/result/DeepModelTelemetry").then((m) => m.DeepModelTelemetry),
  { ssr: false },
);
const HistoryPanel = dynamic(
  () => import("./HistoryPanel").then((m) => m.HistoryPanel),
  { ssr: false },
);
const TimelineTab = dynamic(
  () => import("./TimelineTab").then((m) => m.TimelineTab),
  { ssr: false },
);
const ResultHeader = dynamic(
  () => import("./ResultHeader").then((m) => m.ResultHeader),
  { ssr: false },
);

interface ResultLayoutProps {
  initialSessionId?: string;
}

export function ResultLayout({ initialSessionId }: ResultLayoutProps = {}) {
  const rs = useResult(initialSessionId);

  const activeAgentIds = useMemo(() => {
    const SKIP_TYPES = new Set(["file type not applicable", "format not supported"]);
    return Object.keys(rs.report?.per_agent_findings ?? {}).filter((id) => {
      const flist = rs.report?.per_agent_findings[id] ?? [];
      return flist.length > 0 && !flist.every((f) => SKIP_TYPES.has(f.finding_type.toLowerCase()));
    });
  }, [rs.report]);

  if (!rs.mounted) {
    return <ResultSkeletonView />;
  }

  return (
    <div className="min-h-screen pb-48 pt-32 relative">
      {(rs.state === "arbiter" || rs.state === "loading") && (
        <ForensicProgressOverlay
          title={rs.state === "arbiter" ? "Consensus Synthesis" : "Loading Report"}
          liveText={rs.arbiterMsg || "Decrypting forensic report..."}
          telemetryLabel="Analyzing Agent Intersections"
          showElapsed
        />
      )}

      {/* ── Horizon Navigation Dock ──────────────────────────────────── */}
      <nav className="fixed top-24 left-1/2 -translate-x-1/2 z-[40] w-full max-w-2xl px-6">
        <div className="glass-panel p-2 rounded-full flex items-center justify-between gap-4 bg-[#020203]/80 border-white/10 shadow-[0_32px_64px_rgba(0,0,0,0.6)]">
          <button
            onClick={rs.handleHome}
            className="px-6 py-2.5 text-[10px] font-mono font-bold text-white/40 hover:text-white transition-all uppercase tracking-[0.2em] flex items-center gap-3"
          >
            <HomeIcon className="w-3.5 h-3.5" />
            HUB
          </button>

          <div
            role="tablist"
            aria-label="Report sections"
            className="flex items-center gap-2 pr-1 focus:outline-none"
            tabIndex={0}
            onKeyDown={(e) => {
              if (e.key === "ArrowLeft" || e.key === "ArrowRight") {
                e.preventDefault();
                rs.setActiveTab(rs.activeTab === "analysis" ? "history" : "analysis");
              }
            }}
          >
            {(["analysis", "history"] as Tab[]).map((tab) => (
              <button
                key={tab}
                role="tab"
                id={`tab-${tab}`}
                aria-selected={rs.activeTab === tab}
                aria-controls={`tabpanel-${tab}`}
                onClick={() => rs.setActiveTab(tab)}
                className={clsx(
                  "px-8 py-2.5 text-[10px] font-mono font-bold transition-all duration-300 rounded-full uppercase tracking-[0.2em]",
                  rs.activeTab === tab
                    ? "bg-[var(--color-primary)] text-[#020617] shadow-[0_0_20px_rgba(var(--color-primary-rgb),0.3)]"
                    : "text-white/30 hover:text-white/60 hover:bg-white/5"
                )}
              >
                {tab === "analysis" ? "OVERVIEW" : "LOGS"}
              </button>
            ))}
          </div>
        </div>
      </nav>

      {/* ── Main Investigative Surface ─────────────────────────────────── */}
      <div className="max-w-7xl mx-auto px-6 pt-12 space-y-16">

        <div
          role="tabpanel"
          id="tabpanel-history"
          aria-labelledby="tab-history"
          hidden={rs.activeTab !== "history"}
        >
          <HistoryPanel onDismiss={() => rs.setActiveTab("analysis")} onSelect={(sid) => {
            rs.selectSession(sid);        // drives sessionId state + resets arbiter poll
            rs.setActiveTab("analysis");
          }} />
        </div>
        <div
          role="tabpanel"
          id="tabpanel-analysis"
          aria-labelledby="tab-analysis"
          hidden={rs.activeTab !== "analysis"}
        >
            <ForensicErrorModal
              isVisible={rs.state === "error"}
              message={rs.errorMsg}
              onHome={rs.handleHome}
              onRetry={rs.handleNew}
            />
            {rs.state === "error" && (
              <div className="flex flex-col items-center justify-center py-32 opacity-20">
                <p className="font-mono text-xs">Analysis Pipeline Halted</p>
              </div>
            )}
            {rs.state === "empty" && (
              <ResultStateView type="empty" onNew={rs.handleNew} onHome={rs.handleHome} />
            )}
            {rs.state === "arbiter" && (
              <div className="flex flex-col items-center justify-center py-32 gap-6 opacity-40">
                <Activity className="w-8 h-8 text-primary animate-pulse" />
                <p className="font-mono text-xs font-semibold tracking-wide text-white/60">Awaiting Neural Synthesis...</p>
              </div>
            )}
            {rs.state === "ready" && rs.report && (
              <motion.div
                initial="hidden"
                animate="visible"
                variants={{
                  hidden: { opacity: 0 },
                  visible: { opacity: 1, transition: { staggerChildren: 0.15 } }
                }}
                className="space-y-12"
              >
                {/* 0. Degradation Notice (if any) */}
                {rs.report.degradation_flags && rs.report.degradation_flags.length > 0 && (
                  <motion.div variants={{ hidden: { opacity: 0, y: 15 }, visible: { opacity: 1, y: 0 } }}>
                    <DegradationBanner flags={rs.report.degradation_flags} />
                  </motion.div>
                )}

                {/* 1. Verdict & Identity */}
                <motion.div variants={{ hidden: { opacity: 0, y: 15 }, visible: { opacity: 1, y: 0 } }}>
                  <ResultHeader
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
                </motion.div>

                {/* 2. Intelligence Briefing (Prominent Findings) */}
                <motion.div variants={{ hidden: { opacity: 0, y: 15 }, visible: { opacity: 1, y: 0 } }}>
                  <IntelligenceBrief
                    verdictSentence={rs.report.verdict_sentence}
                    keyFindings={rs.report.key_findings}
                    isDeepPhase={rs.isDeepPhase}
                  />
                </motion.div>

                {/* 3. Detailed Forensic Panels */}
                {rs.isDeepPhase && (
                  <motion.div variants={{ hidden: { opacity: 0, y: 15 }, visible: { opacity: 1, y: 0 } }}>
                    <DeepModelTelemetry report={rs.report} />
                  </motion.div>
                )}

                <motion.div variants={{ hidden: { opacity: 0, y: 15 }, visible: { opacity: 1, y: 0 } }}>
                  <AgentAnalysisTab report={rs.report} activeAgentIds={activeAgentIds} isDeepPhase={rs.isDeepPhase} />
                </motion.div>
                <motion.div variants={{ hidden: { opacity: 0, y: 15 }, visible: { opacity: 1, y: 0 } }}>
                  <TimelineTab report={rs.report} activeAgentIds={activeAgentIds} agentTimeline={rs.agentTimeline} pipelineStartAt={rs.pipelineStartAt} />
                </motion.div>

                <motion.div variants={{ hidden: { opacity: 0, y: 15 }, visible: { opacity: 1, y: 0 } }}>
                  <ReportFooter handleHome={rs.handleHome} />
                </motion.div>
              </motion.div>
            )}
        </div>
      </div>

      {/* ── Sticky Action Dock ─────────────────────────────────────────── */}
      {rs.state === "ready" && rs.activeTab === "analysis" && (
        <ActionDock
          onHome={rs.handleHome}
          onNew={rs.handleNew}
          onExport={rs.handleExport}
        />
      )}
    </div>
  );
}

/** Skeleton shown while the page hydrates / session restores */
function ResultSkeletonView() {
  return (
    <div className="min-h-screen" aria-busy="true" aria-label="Loading report…">
      {/* Fake nav */}
      <div className="sticky top-[60px] z-40 w-full bg-black/60 backdrop-blur-xl border-b border-white/[0.05]">
        <div className="max-w-5xl mx-auto px-10 py-6 flex items-center justify-between gap-4">
          <div className="skeleton h-5 w-40 rounded-full" />
          <div className="skeleton h-10 w-64 rounded-2xl" />
        </div>
      </div>
      <div className="max-w-5xl mx-auto px-6 pt-12 space-y-12">
        {/* Verdict card skeleton — matches ResultHeader layout */}
        <div className="rounded-3xl border border-white/5 glass-panel p-10 space-y-8">
          <div className="grid grid-cols-1 md:grid-cols-[auto_1fr] gap-8 items-center">
            {/* ArcGauge placeholder */}
            <div className="skeleton w-40 h-40 rounded-2xl mx-auto" />
            {/* Right column: verdict + discord + 3 metric cards */}
            <div className="flex-1 space-y-6">
              <div className="space-y-3 text-center md:text-left">
                <div className="skeleton h-4 w-28 mx-auto md:mx-0" />
                <div className="skeleton h-10 w-64 rounded-2xl mx-auto md:mx-0" />
              </div>
              <div className="flex gap-3 justify-center md:justify-start">
                <div className="skeleton h-7 w-28 rounded-full" />
                <div className="skeleton h-7 w-28 rounded-full" />
              </div>
              {/* 3 metric cards matching MetricsPanel */}
              <div className="grid grid-cols-3 gap-3 pt-6 border-t border-white/5">
                {[1,2,3].map(i => <div key={i} className="skeleton h-20 rounded-2xl" />)}
              </div>
            </div>
          </div>
        </div>
        {/* Agent tabs skeleton */}
        <div className="space-y-6">
          <div className="skeleton h-10 w-80 rounded-full" />
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            {[1,2,3,4].map(i => <div key={i} className="skeleton h-48 rounded-2xl" />)}
          </div>
        </div>
      </div>
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
