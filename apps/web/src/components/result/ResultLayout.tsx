"use client";

import React, { useMemo, useEffect, useRef } from "react";
import { clsx } from "clsx";
import dynamic from "next/dynamic";
import {
  FileSearch,
  History as HistoryIcon,
  Home as HomeIcon,
  Plus,
  ShieldAlert,
} from "lucide-react";
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

  const sessionChangeRef = useRef<string | undefined>(initialSessionId);
  useEffect(() => {
    if (typeof window === "undefined") return;
    if (sessionChangeRef.current === initialSessionId) return;
    sessionChangeRef.current = initialSessionId;
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
    return (
      <ResultLoadingView
        title="Consensus Synthesis"
        liveText="Final report synthesis requested. Compiling initial agent findings."
      />
    );
  }

  return (
    <div className="min-h-screen pb-48 pt-36 sm:pt-28 relative">
      {/* ── Arbiter/Loading overlay ── */}
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

      {/* ── Secondary Tab Nav (Analysis / History) ── */}
      <nav
        className="fixed top-16 left-0 right-0 z-[40] border-b border-white/[0.06] bg-[#02040A]/85 backdrop-blur-md"
        aria-label="Report sections"
      >
        <div className="max-w-7xl mx-auto px-4 sm:px-6 h-12 flex items-center gap-1">
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
              onKeyDown={(e) => {
                if (e.key !== "ArrowLeft" && e.key !== "ArrowRight") return;
                e.preventDefault();
                const next = rs.activeTab === "analysis" ? "history" : "analysis";
                rs.setActiveTab(next);
                requestAnimationFrame(() => tabRefs.current[next]?.focus());
              }}
              className={clsx(
                "px-4 py-2 text-xs font-mono font-bold tracking-wider flex items-center gap-1.5 rounded-full transition-all duration-150 border",
                rs.activeTab === tab
                  ? "bg-white/[0.08] text-white border-white/20"
                  : "text-white/45 hover:text-white hover:bg-white/[0.05] border-transparent"
              )}
            >
              {tab === "analysis" ? <FileSearch className="w-3.5 h-3.5" /> : <HistoryIcon className="w-3.5 h-3.5" />}
              {tab === "analysis" ? "Analysis" : "History"}
            </button>
          ))}

          {/* Spacer + inline nav shortcuts */}
          <div className="ml-auto flex items-center gap-2">
            <button
              type="button"
              onClick={rs.handleHome}
              className="px-3 py-1.5 text-xs font-mono font-bold tracking-wider flex items-center gap-1.5 text-white/55 hover:text-white transition-colors rounded-full hover:bg-white/[0.04]"
              aria-label="Back to Home"
            >
              <HomeIcon className="w-3 h-3" />
              Home
            </button>
            <button
              type="button"
              onClick={rs.handleNew}
              className="px-3 py-1.5 text-xs font-mono font-bold tracking-wider flex items-center gap-1.5 text-white/55 hover:text-white transition-colors rounded-full hover:bg-white/[0.04]"
              aria-label="New Analysis"
            >
              <Plus className="w-3 h-3" />
              New
            </button>
          </div>
        </div>
      </nav>

      {/* ── Main Content ── */}
      <div className="max-w-7xl mx-auto px-4 sm:px-6 pt-4 space-y-0">
        {/* History tab panel */}
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

        {/* Analysis tab panel */}
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

          {rs.state === "arbiter" && <ResultInlineStatus message={rs.arbiterMsg} />}

          {rs.state === "ready" && rs.report && (
            <motion.div
              initial="hidden"
              animate="visible"
              variants={{
                hidden: { opacity: 0 },
                visible: { opacity: 1, transition: { staggerChildren: 0.1 } },
              }}
              className="space-y-8"
            >
              {/* ── SECTION 1: Verdict Header ── */}
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

              {/* ── SECTION 2: Executive Brief + Key Findings ── */}
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

              {/* ── SECTION 3: Degradation Warnings (conditional) ── */}
              {rs.report.degradation_flags && rs.report.degradation_flags.length > 0 && (
                <motion.div variants={{ hidden: { opacity: 0, y: 15 }, visible: { opacity: 1, y: 0 } }}>
                  <DegradationBanner flags={rs.report.degradation_flags} />
                </motion.div>
              )}

              {/* ── SECTION 4: Deep Model Telemetry (deep phase only) ── */}
              {rs.isDeepPhase && (
                <motion.div variants={{ hidden: { opacity: 0, y: 15 }, visible: { opacity: 1, y: 0 } }}>
                  <DeepModelTelemetry report={rs.report} />
                </motion.div>
              )}

              {/* ── SECTION 5: Agent Forensic Findings ── */}
              <motion.div variants={{ hidden: { opacity: 0, y: 15 }, visible: { opacity: 1, y: 0 } }}>
                <AgentAnalysisTab
                  report={rs.report}
                  activeAgentIds={activeAgentIds}
                  isDeepPhase={rs.isDeepPhase}
                />
              </motion.div>

              {/* ── SECTION 6: Forensic Execution Timeline ── */}
              <motion.div variants={{ hidden: { opacity: 0, y: 15 }, visible: { opacity: 1, y: 0 } }}>
                <TimelineTab
                  report={rs.report}
                  activeAgentIds={activeAgentIds}
                  agentTimeline={rs.agentTimeline}
                  pipelineStartAt={rs.pipelineStartAt}
                />
              </motion.div>

              {/* ── SECTION 7: Footer ── */}
              <motion.div variants={{ hidden: { opacity: 0, y: 15 }, visible: { opacity: 1, y: 0 } }}>
                <ReportFooter handleHome={rs.handleHome} />
              </motion.div>
            </motion.div>
          )}
        </div>
      </div>

      {/* ── Action Dock: always visible when analysis tab is active and not loading ── */}
      {rs.activeTab === "analysis" && (rs.state === "ready" || rs.state === "empty") && (
        <ActionDock
          onHome={rs.handleHome}
          onNew={rs.handleNew}
          onExport={rs.handleExport}
          sessionId={rs.sessionId ?? undefined}
          showExport={rs.state === "ready"}
        />
      )}
    </div>
  );
}

// ── Sub-components ──────────────────────────────────────────────────────────

function ResultLoadingView({
  title,
  liveText,
}: {
  title: string;
  liveText: string;
}) {
  return (
    <div className="min-h-screen bg-background" aria-busy="true" aria-label={title}>
      <ForensicProgressOverlay
        title={title}
        liveText={liveText}
        telemetryLabel="Compiling agent findings"
        showElapsed
      />
      <ResultSkeletonView />
    </div>
  );
}

function ResultInlineStatus({ message }: { message: string }) {
  return (
    <div className="min-h-[54vh] flex items-center justify-center">
      <div className="w-full max-w-md fc-surface-quiet px-8 py-10 text-center">
        <ShieldAlert className="w-12 h-12 text-[var(--color-primary)]/70 mx-auto mb-6 animate-pulse" />
        <div className="mt-6 fc-eyebrow text-primary/70">
          Consensus Synthesis
        </div>
        <p className="mt-3 font-mono text-xs font-semibold leading-relaxed text-white/70">
          {message || "Arbiter is compiling agent findings..."}
        </p>
      </div>
    </div>
  );
}

function ResultSkeletonView() {
  return (
    <div className="min-h-screen opacity-35" aria-hidden="true">
      <div className="max-w-7xl mx-auto px-6 pt-28 space-y-6">
        <div className="p-8 space-y-8 fc-surface-quiet">
          <div className="flex flex-col md:flex-row gap-6 items-center">
            <div className="skeleton w-32 h-32 rounded-2xl" />
            <div className="flex-1 space-y-4 w-full">
              <div className="skeleton h-3.5 w-44 rounded-2xl" />
              <div className="skeleton h-9 w-72 rounded-2xl" />
              <div className="skeleton h-16 w-full rounded-2xl" />
            </div>
            <div className="skeleton w-28 h-28 rounded-2xl" />
          </div>
        </div>
        <div className="skeleton h-52 fc-surface-quiet" />
        <div className="skeleton h-72 fc-surface-quiet" />
      </div>
    </div>
  );
}

// ── Helpers ─────────────────────────────────────────────────────────────────

function toPct(value: number | null | undefined): number {
  return Math.max(0, Math.min(100, Math.round(Number(value ?? 0) * 100)));
}

function buildKeyFindings(report: ReportDTO | null | undefined): string[] {
  if (!report) return [];

  const findings: string[] = [];
  const summaryText = cleanFindingText(report.verdict_sentence || report.executive_summary);
  const push = (value: string | null | undefined) => {
    const cleaned = cleanFindingText(value);
    if (!cleaned || isLowValueFinding(cleaned)) return;
    if (summaryText && sameFinding(summaryText, cleaned)) return;
    if (!findings.some((existing) => sameFinding(existing, cleaned))) {
      findings.push(cleaned);
    }
  };

  (report.key_findings ?? []).forEach((finding) => push(finding));

  if (findings.length > 0) {
    return findings.slice(0, 4);
  }

  if (findings.length === 0) {
    const agentNarratives = Object.entries(report.per_agent_analysis ?? {})
      .map(([agentId, text]) => ({
        agentId,
        text: cleanFindingText(text),
        priority: agentPriority(agentId),
      }))
      .filter((item) => item.text && !isLowValueFinding(item.text))
      .sort((a, b) => a.priority - b.priority);

    for (const item of agentNarratives) {
      if (findings.length >= 3) break;
      push(item.text);
    }
  }

  if (findings.length === 0) {
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
      if (findings.length >= 3) break;
      push(item.text);
    }
  }

  return findings.slice(0, 3);
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
  if (!na || !nb) return false;
  const aSlice = na.slice(0, Math.min(90, na.length));
  const bSlice = nb.slice(0, Math.min(90, nb.length));
  return na === nb || na.includes(bSlice) || nb.includes(aSlice);
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
