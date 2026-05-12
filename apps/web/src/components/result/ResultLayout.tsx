"use client";

import React, { useMemo, useEffect } from "react";
import dynamic from "next/dynamic";
import { Activity, FileSearch, History as HistoryIcon, Home as HomeIcon } from "lucide-react";
import { motion, AnimatePresence } from "framer-motion";
import { type Tab, useResult } from "@/hooks/useResult";
import { getVerdictConfig } from "@/lib/verdict";
import type { AgentFindingDTO, ReportDTO } from "@/lib/api";
import type { Finding } from "@/lib/types";
import { cleanFindingText } from "@/lib/findingText";
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

  // Restore manual scroll position on back-navigation; scroll to top on new session
  useEffect(() => {
    if (typeof window === "undefined") return;
    if ("scrollRestoration" in history) {
      history.scrollRestoration = "manual";
    }
    window.scrollTo({ top: 0, behavior: "instant" });
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
        <div
          className="flex items-center justify-between gap-2 p-1.5 rounded-2xl backdrop-blur-2xl"
          style={{
            background: "rgba(5,9,18,0.92)",
            border: "1px solid rgba(165,200,255,0.08)",
            boxShadow: "0 20px 60px rgba(0,0,0,0.6), inset 0 1px 0 rgba(255,255,255,0.04)",
          }}
        >
          <button
            type="button"
            onClick={rs.handleHome}
            className="px-4 py-2.5 text-[10px] font-mono font-bold uppercase tracking-[0.18em] flex items-center gap-2 rounded-xl transition-all duration-200"
            style={{ color: "rgba(255,255,255,0.35)" }}
            onMouseEnter={(e) => {
              (e.currentTarget as HTMLElement).style.color = "rgba(255,255,255,0.75)";
              (e.currentTarget as HTMLElement).style.background = "rgba(255,255,255,0.04)";
            }}
            onMouseLeave={(e) => {
              (e.currentTarget as HTMLElement).style.color = "rgba(255,255,255,0.35)";
              (e.currentTarget as HTMLElement).style.background = "";
            }}
          >
            <HomeIcon className="w-3.5 h-3.5" />
            Hub
          </button>

          <div
            role="tablist"
            aria-label="Report sections"
            className="flex items-center gap-1 focus:outline-none"
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
                type="button"
                key={tab}
                role="tab"
                id={`tab-${tab}`}
                aria-selected={rs.activeTab === tab}
                aria-controls={`tabpanel-${tab}`}
                onClick={() => rs.setActiveTab(tab)}
                className="px-4 sm:px-6 py-2.5 text-[10px] font-mono font-bold transition-all duration-250 rounded-xl uppercase tracking-[0.14em] flex items-center gap-2"
                style={
                  rs.activeTab === tab
                    ? {
                        background: "var(--color-primary)",
                        color: "#020810",
                        boxShadow: `0 0 18px rgba(79,142,247,0.28)`,
                      }
                    : { color: "rgba(255,255,255,0.28)" }
                }
                onMouseEnter={(e) => {
                  if (rs.activeTab !== tab) {
                    (e.currentTarget as HTMLElement).style.color = "rgba(255,255,255,0.6)";
                    (e.currentTarget as HTMLElement).style.background = "rgba(255,255,255,0.04)";
                  }
                }}
                onMouseLeave={(e) => {
                  if (rs.activeTab !== tab) {
                    (e.currentTarget as HTMLElement).style.color = "rgba(255,255,255,0.28)";
                    (e.currentTarget as HTMLElement).style.background = "";
                  }
                }}
              >
                {tab === "analysis" ? <FileSearch className="w-3.5 h-3.5" /> : <HistoryIcon className="w-3.5 h-3.5" />}
                {tab === "analysis" ? "Analysis" : "History"}
              </button>
            ))}
          </div>
        </div>
      </nav>

      <div className="max-w-7xl mx-auto px-6 pt-16 space-y-10">
        <div
          role="tabpanel"
          id="tabpanel-history"
          aria-labelledby="tab-history"
          hidden={rs.activeTab !== "history"}
        >
          <HistoryPanel
            onDismiss={() => rs.setActiveTab("analysis")}
            onSelect={(sid) => {
              rs.selectSession(sid);
              rs.setActiveTab("analysis");
            }}
          />
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
          className="flex items-center justify-between gap-4 p-1.5 rounded-2xl backdrop-blur-2xl"
          style={{
            background: "rgba(5,9,18,0.9)",
            border: "1px solid rgba(165,200,255,0.07)",
            boxShadow: "0 24px 60px rgba(0,0,0,0.6)",
          }}
        >
          <div className="skeleton h-10 w-20 rounded-xl" />
          <div className="skeleton h-10 w-64 rounded-xl" />
        </div>
      </div>
      <div className="max-w-7xl mx-auto px-6 pt-16 space-y-6">
        <div
          className="rounded-2xl p-8 space-y-8"
          style={{
            background: "rgba(6,10,20,0.85)",
            border: "1px solid rgba(165,200,255,0.06)",
          }}
        >
          <div className="flex flex-col md:flex-row gap-6 items-center">
            <div className="skeleton w-32 h-32 rounded-xl" />
            <div className="flex-1 space-y-4 w-full">
              <div className="skeleton h-3.5 w-44 rounded-full" />
              <div className="skeleton h-9 w-72 rounded-xl" />
              <div className="skeleton h-16 w-full rounded-xl" />
            </div>
            <div className="skeleton w-28 h-28 rounded-full" />
          </div>
        </div>
        <div className="skeleton h-52 rounded-2xl" />
        <div className="skeleton h-72 rounded-2xl" />
      </div>
    </div>
  );
}

function fmtDuration(from: string | null, to?: string): string {
  if (!from || !to) return "-";
  try {
    const ms = new Date(to).getTime() - new Date(from).getTime();
    if (ms < 0) return "-";
    if (ms < 1000) return `${ms}ms`;
    if (ms < 60000) return `${(ms / 1000).toFixed(1)}s`;
    return `${Math.floor(ms / 60000)}m ${Math.floor((ms % 60000) / 1000)}s`;
  } catch {
    return "-";
  }
}

function toPct(value: number | null | undefined): number {
  return Math.max(0, Math.min(100, Math.round(Number(value ?? 0) * 100)));
}

function buildKeyFindings(report: ReportDTO | null | undefined): string[] {
  if (!report) return [];

  const findings: string[] = [];
  const push = (value: string | null | undefined, maxLen = 230) => {
    const cleaned = cleanFindingText(value, maxLen);
    if (!cleaned || isLowValueFinding(cleaned)) return;
    if (!findings.some((existing) => sameFinding(existing, cleaned))) {
      findings.push(cleaned);
    }
  };

  (report.key_findings ?? []).forEach((finding) => push(finding));

  if (findings.length < 4) push(report.verdict_sentence, 260);
  if (findings.length < 4) push(report.executive_summary, 260);

  const agentNarratives = Object.entries(report.per_agent_analysis ?? {})
    .map(([agentId, text]) => ({
      agentId,
      text: cleanFindingText(text, 240),
      priority: agentPriority(agentId),
    }))
    .filter((item) => item.text && !isLowValueFinding(item.text))
    .sort((a, b) => a.priority - b.priority);

  for (const item of agentNarratives) {
    if (findings.length >= 5) break;
    push(item.text, 240);
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
    push(item.text, 220);
  }

  return findings.slice(0, 6);
}

function cleanToolSummary(finding: AgentFindingDTO): string {
  const metadata = finding.metadata ?? {};
  const llmSummary = typeof metadata.llm_refined_summary === "string" ? metadata.llm_refined_summary : "";
  const details = typeof metadata.details === "string" ? metadata.details : "";
  return cleanFindingText(llmSummary || finding.reasoning_summary || finding.court_statement || details, 220);
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
