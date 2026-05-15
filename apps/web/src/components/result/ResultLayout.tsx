"use client";

import React, { useMemo, useEffect, useRef } from "react";
import { clsx } from "clsx";
import dynamic from "next/dynamic";
import { Activity, FileSearch, History as HistoryIcon, Home as HomeIcon } from "lucide-react";
import { motion, AnimatePresence } from "framer-motion";
import { type Tab, useResult } from "@/hooks/useResult";
import { getVerdictConfig } from "@/lib/verdict";
import type { AgentFindingDTO, ReportDTO } from "@/lib/api";
import type { Finding } from "@/lib/types";
import { cleanFindingText } from "@/lib/findingText";
import { fmtDuration } from "@/lib/fmt";
import { ForensicProgressOverlay } from "@/components/ui/ForensicProgressOverlay";
import { ForensicErrorModal } from "@/components/ui/ForensicErrorModal";
import { ReportFooter } from "./ReportFooter";
import { IntelligenceBrief } from "./IntelligenceBrief";
import { DegradationBanner } from "./DegradationBanner";
import { ActionDock } from "./ActionDock";
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

  // Scroll-to-top on session change is owned by RouteExperience for the
  // initial /result/{sid} mount. We only need to handle the case where
  // initialSessionId changes WITHIN the same mounted ResultLayout (e.g.
  // selectSession from the History panel switching between session ids).
  // RouteExperience already sets scrollRestoration = "manual" globally.
  const sessionChangeRef = useRef<string | undefined>(initialSessionId);
  useEffect(() => {
    if (typeof window === "undefined") return;
    // Skip the first run (RouteExperience handles initial mount scroll).
    if (sessionChangeRef.current === initialSessionId) return;
    sessionChangeRef.current = initialSessionId;
    // Synchronous scroll — we're inside the same mount, no animation needed.
    window.scrollTo(0, 0);
  }, [initialSessionId]);

  const activeAgentIds = useMemo(() => {
    const SKIP_TYPES = new Set(["file type not applicable", "format not supported"]);
    const findingsRecord = rs.report?.per_agent_findings;
    if (!findingsRecord || typeof findingsRecord !== "object" || Array.isArray(findingsRecord)) {
      return [];
    }
    return Object.keys(findingsRecord).filter((id) => {
      const flist = findingsRecord[id];
      if (!Array.isArray(flist) || flist.length === 0) return false;
      return !flist.every((f: Finding) => {
        const fType = String(f?.finding_type || "").toLowerCase();
        return SKIP_TYPES.has(fType);
      });
    });
  }, [rs.report]);

  const keyFindings = useMemo(() => buildKeyFindings(rs.report), [rs.report]);
  const tabRefs = useRef<Record<Tab, HTMLButtonElement | null>>({ analysis: null, history: null });

  if (!rs.mounted) {
    return <ResultSkeletonView />;
  }

  return (
    <div className="min-h-screen pb-48 pt-36 sm:pt-28 relative">
      <AnimatePresence initial={false}>
        {(rs.state === "arbiter" || rs.state === "loading") && (
          <ForensicProgressOverlay
            title={rs.state === "arbiter" ? "Consensus Synthesis" : "Loading Report"}
            liveText={rs.arbiterMsg || "Preparing final forensic report..."}
            telemetryLabel="Compiling agent findings"
            showElapsed
          />
        )}
      </AnimatePresence>

      <nav className="fixed top-24 left-1/2 -translate-x-1/2 z-[40] w-full max-w-3xl px-4 sm:px-6">
        <div className="flex items-center justify-between gap-2 p-2 bg-[#06090E] border border-[#333333]">

          <button
            type="button"
            onClick={rs.handleHome}
            className="px-6 py-3 text-[10px] font-mono font-bold tracking-widest uppercase flex items-center gap-2 transition-colors text-white/50 hover:text-white hover:bg-[#111111]"
          >
            <HomeIcon className="w-3.5 h-3.5" />
            Hub
          </button>

          <div
            role="tablist"
            aria-label="Report sections"
            tabIndex={-1}
            className="flex items-center gap-1"
            onKeyDown={(e) => {
              if (e.key !== "ArrowLeft" && e.key !== "ArrowRight") return;
              e.preventDefault();
              const next = rs.activeTab === "analysis" ? "history" : "analysis";
              rs.setActiveTab(next);
              requestAnimationFrame(() => tabRefs.current[next]?.focus());
            }}
          >
            {(["analysis", "history"] as Tab[]).map((tab) => (
              <button
                type="button"
                key={tab}
                role="tab"
                id={`tab-${tab}`}
                aria-selected={rs.activeTab === tab}
                aria-controls={`tabpanel-${tab}`}
                tabIndex={rs.activeTab === tab ? 0 : -1}
                ref={(node) => { tabRefs.current[tab] = node; }}
                onClick={() => rs.setActiveTab(tab)}
                className={clsx(
                  "px-6 py-3 text-[10px] font-mono font-bold transition-colors tracking-widest flex items-center gap-2 uppercase",
                  rs.activeTab === tab
                    ? "bg-white text-black"
                    : "text-white/50 hover:text-white hover:bg-[#111111]"
                )}

              >
                {tab === "analysis" ? <FileSearch className="w-3.5 h-3.5" /> : <HistoryIcon className="w-3.5 h-3.5" />}
                {tab === "analysis" ? "Analysis" : "History"}
              </button>
            ))}
          </div>
        </div>
      </nav>

      <div className="max-w-7xl mx-auto px-6 pt-16 space-y-10">
        {/* F-H-8: only mount HistoryPanel when the History tab is active.
            Previously we used `hidden={...}` which still mounts the panel
            and triggers its sessionStorage reads on every result-page visit. */}
        {rs.activeTab === "history" && (
          <div
            role="tabpanel"
            id="tabpanel-history"
            aria-labelledby="tab-history"
          >
            <HistoryPanel
              onDismiss={() => rs.setActiveTab("analysis")}
              onSelect={(sid) => {
                rs.selectSession(sid);
                rs.setActiveTab("analysis");
              }}
            />
          </div>
        )}

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
              <p className="font-mono text-xs font-semibold tracking-wide text-white/60">
                {rs.arbiterMsg || "Arbiter is compiling agent findings..."}
              </p>
            </div>
          )}

          {rs.state === "ready" && rs.report && (
            <motion.div
              initial="hidden"
              animate="visible"
              variants={{
                hidden: { opacity: 0 },
                visible: { opacity: 1, transition: { staggerChildren: 0.12 } },
              }}
              className="space-y-10"
            >
              <motion.div variants={{ hidden: { opacity: 0, y: 15 }, visible: { opacity: 1, y: 0 } }}>
                <ResultHeader
                  report={rs.report}
                  fileName={rs.fileName || rs.report.case_id || "Evidence"}
                  mimeType={rs.mimeType}
                  thumbnail={rs.thumbnail}
                  isDeepPhase={rs.isDeepPhase}
                  vc={getVerdictConfig(rs.report.overall_verdict ?? "")}
                  confPct={toPct(rs.report.overall_confidence)}
                  manipPct={toPct(rs.report.manipulation_probability)}
                  errPct={toPct(rs.report.overall_error_rate)}
                  discordPct={toPct(rs.report.confidence_std_dev)}
                  activeAgentIds={activeAgentIds}
                  pipelineDuration={
                    rs.pipelineStartAt && rs.report.signed_utc
                      ? fmtDuration(rs.pipelineStartAt, rs.report.signed_utc)
                      : null
                  }
                />
              </motion.div>

              <motion.div variants={{ hidden: { opacity: 0, y: 15 }, visible: { opacity: 1, y: 0 } }}>
                <IntelligenceBrief
                  verdictSentence={rs.report.verdict_sentence || rs.report.executive_summary}
                  keyFindings={keyFindings}
                  reliabilityNote={rs.report.reliability_note}
                  uncertaintyStatement={rs.report.uncertainty_statement}
                  coverageNote={rs.report.analysis_coverage_note}
                  skippedAgents={rs.report.skipped_agents}
                  isDeepPhase={rs.isDeepPhase}
                />
              </motion.div>

              {rs.report.degradation_flags && rs.report.degradation_flags.length > 0 && (
                <motion.div variants={{ hidden: { opacity: 0, y: 15 }, visible: { opacity: 1, y: 0 } }}>
                  <DegradationBanner flags={rs.report.degradation_flags} />
                </motion.div>
              )}

              {rs.isDeepPhase && (
                <motion.div variants={{ hidden: { opacity: 0, y: 15 }, visible: { opacity: 1, y: 0 } }}>
                  <DeepModelTelemetry report={rs.report} />
                </motion.div>
              )}

              <motion.div variants={{ hidden: { opacity: 0, y: 15 }, visible: { opacity: 1, y: 0 } }}>
                <AgentAnalysisTab report={rs.report} activeAgentIds={activeAgentIds} isDeepPhase={rs.isDeepPhase} />
              </motion.div>

              <motion.div variants={{ hidden: { opacity: 0, y: 15 }, visible: { opacity: 1, y: 0 } }}>
                <TimelineTab
                  report={rs.report}
                  activeAgentIds={activeAgentIds}
                  agentTimeline={rs.agentTimeline}
                  pipelineStartAt={rs.pipelineStartAt}
                />
              </motion.div>

              <motion.div variants={{ hidden: { opacity: 0, y: 15 }, visible: { opacity: 1, y: 0 } }}>
                <ReportFooter handleHome={rs.handleHome} />
              </motion.div>
            </motion.div>
          )}
        </div>
      </div>

      {rs.state === "ready" && rs.activeTab === "analysis" && (
        <ActionDock
          onHome={rs.handleHome}
          onNew={rs.handleNew}
          onExport={rs.handleExport}
          sessionId={rs.sessionId ?? undefined}
        />
      )}
    </div>
  );
}

function ResultSkeletonView() {
  return (
    <div className="min-h-screen" aria-busy="true" aria-label="Loading report">
      <div className="fixed top-24 left-1/2 -translate-x-1/2 z-[40] w-full max-w-3xl px-6">
        <div
          className="flex items-center justify-between gap-4 p-4 bg-[#06090E] border border-[#333333]"
        >
          <div className="skeleton h-10 w-20 rounded-none" />
          <div className="skeleton h-10 w-64 rounded-none" />
        </div>
      </div>
      <div className="max-w-7xl mx-auto px-6 pt-16 space-y-6">
        <div className="p-8 space-y-8 bg-[#06090E] border border-[#333333]">
          <div className="flex flex-col md:flex-row gap-6 items-center">
            <div className="skeleton w-32 h-32 rounded-none" />
            <div className="flex-1 space-y-4 w-full">
              <div className="skeleton h-3.5 w-44 rounded-none" />
              <div className="skeleton h-9 w-72 rounded-none" />
              <div className="skeleton h-16 w-full rounded-none" />
            </div>
            <div className="skeleton w-28 h-28 rounded-none" />
          </div>
        </div>
        <div className="skeleton h-52 rounded-none bg-[#06090E] border border-[#333333]" />
        <div className="skeleton h-72 rounded-none bg-[#06090E] border border-[#333333]" />
      </div>
    </div>
  );
}


function toPct(value: number | null | undefined): number {
  return Math.max(0, Math.min(100, Math.round(Number(value ?? 0) * 100)));
}

function buildKeyFindings(report: ReportDTO | null | undefined): string[] {
  if (!report) return [];

  const findings: string[] = [];
  // Don't truncate the key-findings paragraphs. Arbiter-produced narratives
  // are already concise; mid-sentence "..." cuts hide critical signals.
  const push = (value: string | null | undefined) => {
    const cleaned = cleanFindingText(value);
    if (!cleaned || isLowValueFinding(cleaned)) return;
    if (!findings.some((existing) => sameFinding(existing, cleaned))) {
      findings.push(cleaned);
    }
  };

  (report.key_findings ?? []).forEach((finding) => push(finding));

  if (findings.length < 4) push(report.verdict_sentence);
  if (findings.length < 4) push(report.executive_summary);

  const agentNarratives = Object.entries(report.per_agent_analysis ?? {})
    .map(([agentId, text]) => ({
      agentId,
      text: cleanFindingText(text),
      priority: agentPriority(agentId),
    }))
    .filter((item) => item.text && !isLowValueFinding(item.text))
    .sort((a, b) => a.priority - b.priority);

  for (const item of agentNarratives) {
    if (findings.length >= 5) break;
    push(item.text);
  }

  const toolFindings = Object.values(report.per_agent_findings ?? {})
    .flat()
    .filter(Boolean)
    .map((finding) => ({
      text: cleanToolSummary(finding),
      confidence: Number(finding.raw_confidence_score ?? finding.confidence_raw ?? 0),
      severity: finding.severity_tier ?? "INFO",
    }))
    .filter((item) => item.text && !isLowValueFinding(item.text))
    .sort((a, b) => severityRank(b.severity) - severityRank(a.severity) || b.confidence - a.confidence);

  for (const item of toolFindings) {
    if (findings.length >= 6) break;
    push(item.text);
  }

  return findings.slice(0, 6);
}

function cleanToolSummary(finding: AgentFindingDTO): string {
  const metadata = finding.metadata ?? {};
  const llmSummary = typeof metadata.llm_refined_summary === "string" ? metadata.llm_refined_summary : "";
  const details = typeof metadata.details === "string" ? metadata.details : "";
  return cleanFindingText(llmSummary || finding.reasoning_summary || finding.court_statement || details);
}

function sameFinding(a: string, b: string): boolean {
  const normalize = (value: string) => value.toLowerCase().replace(/[^a-z0-9]+/g, " ").trim();
  const na = normalize(a);
  const nb = normalize(b);
  return na === nb || na.includes(nb.slice(0, 90)) || nb.includes(na.slice(0, 90));
}

function isLowValueFinding(text: string): boolean {
  const lower = text.toLowerCase();
  return (
    lower.length < 24 ||
    lower.includes("template") ||
    lower.includes("lorem ipsum") ||
    lower.includes("no significant findings were identified") ||
    lower.includes("review the detailed findings below") ||
    lower.includes("forensic council has completed its multi-agent evaluation")
  );
}

function agentPriority(agentId: string): number {
  if (agentId === "Agent1") return 1;
  if (agentId === "Agent5") return 2;
  if (agentId === "Agent3") return 3;
  if (agentId === "Agent2") return 4;
  if (agentId === "Agent4") return 5;
  return 10;
}

function severityRank(severity: string): number {
  switch (severity) {
    case "CRITICAL": return 5;
    case "HIGH": return 4;
    case "MEDIUM": return 3;
    case "LOW": return 2;
    default: return 1;
  }
}
