"use client";

import React, { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { clsx } from "clsx";
import dynamic from "next/dynamic";
import {
  ChevronDown,
  Download,
  FileJson,
  FileText,
  FileSearch,
  History as HistoryIcon,
} from "lucide-react";
import { motion, AnimatePresence } from "framer-motion";
import { type Tab, useResult } from "@/hooks/useResult";
import { getVerdictConfig } from "@/lib/verdict";
import type { AgentFindingDTO, ReportDTO } from "@/lib/api";
import { API_BASE } from "@/lib/api";
import type { Finding } from "@/lib/types";
import { cleanFindingText } from "@/lib/findingText";
import { ForensicProgressOverlay } from "@/components/ui/ForensicProgressOverlay";
import { ForensicErrorModal } from "@/components/ui/ForensicErrorModal";
import { ResultStateView } from "./ResultStateView";
import { EvidenceHeader } from "./EvidenceHeader";
import { VerdictSection } from "./VerdictSection";
import { AgentsStrip } from "./AgentsStrip";
import { KeyFindings } from "./KeyFindings";
import { FindingsMetadata } from "./FindingsMetadata";
import { ExecutionTimeline } from "./ExecutionTimeline";
import { ReportIntegrity } from "./ReportIntegrity";
import { PageNavigation } from "./PageNavigation";

const AgentAnalysisTab = dynamic(
  () => import("./AgentAnalysisTab").then((m) => m.AgentAnalysisTab),
  { ssr: false },
);
const HistoryPanel = dynamic(
  () => import("./HistoryPanel").then((m) => m.HistoryPanel),
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

  // Capture the original session ID once — never overwritten when selectSession is called.
  // Used to show "Current" badge in HistoryPanel.
  const originalSessionIdRef = useRef<string | null>(null);
  if (!originalSessionIdRef.current && rs.sessionId) {
    originalSessionIdRef.current = rs.sessionId;
  }

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
    <div className="min-h-screen pb-24 pt-20 sm:pt-12 relative">
      {/* ── Arbiter/Loading overlay ── */}
      <AnimatePresence initial={false}>
        {(rs.state === "arbiter" || rs.state === "loading") && (
          <ForensicProgressOverlay
            title={rs.state === "arbiter" ? "Consensus Synthesis" : "Loading Report"}
            liveText={rs.arbiterMsg || "Preparing final forensic report..."}
            telemetryLabel="Compiling agent findings"
            showElapsed
            variant={rs.state === "arbiter" ? "arbiter" : "loading"}
          />
        )}
      </AnimatePresence>

      {/* ── Tab Nav ── */}
      <nav
        className="fixed top-16 left-0 right-0 z-[40] border-b border-white/[0.06] bg-background/85 backdrop-blur-md"
        aria-label="Report sections"
      >
        <div className="max-w-4xl mx-auto px-4 sm:px-6 h-12 flex items-center gap-2">
          {/* Centered pill tabs */}
          <div className="flex-1 flex items-center justify-center gap-1">
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
                  "px-4 py-1.5 text-xs font-mono font-bold tracking-wider flex items-center gap-1.5 rounded-full transition-all duration-150 border",
                  rs.activeTab === tab
                    ? "bg-white/[0.08] text-white border-white/20"
                    : "fc-text-faint hover:text-white hover:bg-white/[0.05] border-transparent"
                )}
              >
                {tab === "analysis" ? <FileSearch className="w-3.5 h-3.5" /> : <HistoryIcon className="w-3.5 h-3.5" />}
                {tab === "analysis" ? "Analysis" : "History"}
              </button>
            ))}
          </div>

          {/* Export dropdown — right side */}
          {rs.state === "ready" && rs.report && (
            <ExportDropdown
              report={rs.report}
              sessionId={rs.sessionId ?? undefined}
              onExportJson={rs.handleExport}
            />
          )}
        </div>
      </nav>

      {/* ── Main Content ── */}
      <div className="max-w-4xl mx-auto px-4 sm:px-6 pt-4 space-y-0">
        {/* History tab panel */}
        {rs.activeTab === "history" && (
          <div role="tabpanel" id="tabpanel-history" aria-labelledby="tab-history">
            <HistoryPanel
              onDismiss={() => rs.setActiveTab("analysis")}
              onSelect={(sid) => {
                rs.selectSession(sid);
                rs.setActiveTab("analysis");
              }}
              currentSessionId={originalSessionIdRef.current}
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

          {rs.state === "ready" && rs.report && (
            <motion.div
              initial="hidden"
              animate="visible"
              variants={{
                hidden: { opacity: 0 },
                visible: { opacity: 1, transition: { staggerChildren: 0.08, delayChildren: 0.12 } },
              }}
              className="space-y-4"
            >
              {/* 1. Evidence Header */}
              <motion.div variants={{ hidden: { opacity: 0, y: 4 }, visible: { opacity: 1, y: 0, transition: { duration: 0.16 } } }}>
                <EvidenceHeader
                  fileName={rs.fileName}
                  mimeType={rs.mimeType}
                  thumbnail={rs.thumbnail}
                  pipelineStartAt={rs.pipelineStartAt}
                  caseId={rs.report.case_id}
                />
              </motion.div>

              {/* 2. Verdict + Metric Strip */}
              <motion.div variants={{ hidden: { opacity: 0, y: 4 }, visible: { opacity: 1, y: 0, transition: { duration: 0.16 } } }}>
                <VerdictSection
                  vc={getVerdictConfig(rs.report.overall_verdict ?? "")}
                  confPct={toPct(rs.report.overall_confidence)}
                  manipPct={toPct(rs.report.manipulation_probability)}
                  errPct={toPct(rs.report.overall_error_rate)}
                  discordPct={toPct(rs.report.confidence_std_dev)}
                  isDeepPhase={rs.isDeepPhase}
                  agentCount={activeAgentIds.length}
                  verdictSentence={rs.report.verdict_sentence || rs.report.executive_summary}
                />
              </motion.div>

              {/* 3. Agents Strip */}
              <motion.div variants={{ hidden: { opacity: 0, y: 4 }, visible: { opacity: 1, y: 0, transition: { duration: 0.16 } } }}>
                <AgentsStrip
                  perAgentMetrics={rs.report.per_agent_metrics}
                  skippedAgents={rs.report.skipped_agents}
                  activeAgentIds={activeAgentIds}
                />
              </motion.div>

              {/* 4. Key Findings */}
              {keyFindings.length > 0 && (
                <motion.div variants={{ hidden: { opacity: 0, y: 4 }, visible: { opacity: 1, y: 0, transition: { duration: 0.16 } } }}>
                  <KeyFindings findings={keyFindings} />
                </motion.div>
              )}

              {/* 5. Agent Findings */}
              <motion.div variants={{ hidden: { opacity: 0, y: 4 }, visible: { opacity: 1, y: 0, transition: { duration: 0.16 } } }}>
                <AgentAnalysisTab
                  report={rs.report}
                  activeAgentIds={activeAgentIds}
                  isDeepPhase={rs.isDeepPhase}
                />
              </motion.div>

              {/* 6. Analysis Metrics */}
              <motion.div variants={{ hidden: { opacity: 0, y: 4 }, visible: { opacity: 1, y: 0, transition: { duration: 0.16 } } }}>
                <FindingsMetadata
                  report={rs.report}
                  activeAgentIds={activeAgentIds}
                />
              </motion.div>

              {/* 7. Execution Timeline */}
              <motion.div variants={{ hidden: { opacity: 0, y: 4 }, visible: { opacity: 1, y: 0, transition: { duration: 0.16 } } }}>
                <ExecutionTimeline
                  report={rs.report}
                  activeAgentIds={activeAgentIds}
                  agentTimeline={rs.agentTimeline}
                  pipelineStartAt={rs.pipelineStartAt}
                />
              </motion.div>

              {/* 8. Report Integrity */}
              <motion.div variants={{ hidden: { opacity: 0, y: 4 }, visible: { opacity: 1, y: 0, transition: { duration: 0.16 } } }}>
                <ReportIntegrity
                  report={rs.report}
                  sessionId={rs.sessionId}
                  isDeepPhase={rs.isDeepPhase}
                />
              </motion.div>

              {/* 9. Navigation */}
              <motion.div variants={{ hidden: { opacity: 0, y: 4 }, visible: { opacity: 1, y: 0, transition: { duration: 0.16 } } }}>
                <PageNavigation onHome={rs.handleHome} onNew={rs.handleNew} />
              </motion.div>
            </motion.div>
          )}
        </div>
      </div>
    </div>
  );
}

// ── ExportDropdown ───────────────────────────────────────────────────────────

function ExportDropdown({
  report,
  sessionId,
  onExportJson,
}: {
  report: ReportDTO;
  sessionId?: string;
  onExportJson: () => void;
}) {
  const [open, setOpen] = useState(false);
  const [exporting, setExporting] = useState(false);
  const ref = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!open) return;
    const handler = (e: MouseEvent) => {
      if (ref.current && !ref.current.contains(e.target as Node)) setOpen(false);
    };
    document.addEventListener("mousedown", handler);
    return () => document.removeEventListener("mousedown", handler);
  }, [open]);

  const handlePdf = useCallback(async () => {
    if (!sessionId || exporting) return;
    setExporting(true);
    setOpen(false);
    try {
      const res = await fetch(
        `${API_BASE}/api/v1/sessions/${encodeURIComponent(sessionId)}/report/pdf`,
        { credentials: "include" },
      );
      if (res.ok) {
        const blob = await res.blob();
        const url = URL.createObjectURL(blob);
        const a = document.createElement("a");
        a.href = url;
        a.download = `forensic-report-${(report.report_id ?? sessionId).slice(0, 8)}.pdf`;
        a.click();
        URL.revokeObjectURL(url);
        return;
      }
    } catch {
      // fall through to JSON
    } finally {
      setExporting(false);
    }
    onExportJson();
  }, [sessionId, exporting, report, onExportJson]);

  const handleJson = useCallback(() => {
    setOpen(false);
    onExportJson();
  }, [onExportJson]);

  return (
    <div className="relative shrink-0" ref={ref}>
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        disabled={exporting}
        className="flex items-center gap-1.5 px-3 py-1.5 rounded-full border border-white/[0.10] fc-text-faint hover:text-white hover:bg-white/[0.05] hover:border-white/[0.15] transition-all duration-150 fc-eyebrow focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary/50 disabled:opacity-50"
        aria-label="Export report"
        aria-expanded={open}
      >
        <Download className="w-3.5 h-3.5" />
        Export
        <ChevronDown className={clsx("w-3 h-3 transition-transform duration-150", open && "rotate-180")} />
      </button>

      <AnimatePresence>
        {open && (
          <motion.div
            initial={{ opacity: 0, y: -4, scale: 0.97 }}
            animate={{ opacity: 1, y: 0, scale: 1 }}
            exit={{ opacity: 0, y: -4, scale: 0.97 }}
            transition={{ duration: 0.1, ease: "easeOut" }}
            className="absolute right-0 top-full mt-1.5 w-44 rounded-xl border border-white/[0.10] bg-background/95 backdrop-blur-xl shadow-xl py-1.5 z-50"
          >
            <button
              type="button"
              onClick={handlePdf}
              className="w-full flex items-center gap-2.5 px-4 py-2 text-xs fc-text-muted hover:text-white hover:bg-white/[0.05] transition-colors"
            >
              <FileText className="w-3.5 h-3.5 shrink-0" />
              PDF Report
            </button>
            <button
              type="button"
              onClick={handleJson}
              className="w-full flex items-center gap-2.5 px-4 py-2 text-xs fc-text-muted hover:text-white hover:bg-white/[0.05] transition-colors"
            >
              <FileJson className="w-3.5 h-3.5 shrink-0" />
              JSON Export
            </button>
            <div className="mx-3 my-1 h-px bg-white/[0.06]" />
            <div className="flex items-center gap-2.5 px-4 py-2 text-xs fc-text-faint opacity-40 cursor-not-allowed select-none">
              <FileText className="w-3.5 h-3.5 shrink-0" />
              Docx — coming soon
            </div>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
}

// ── Sub-components ───────────────────────────────────────────────────────────

function ResultLoadingView({ title, liveText }: { title: string; liveText: string }) {
  return (
    <div className="min-h-screen bg-background" aria-busy="true" aria-label={title}>
      <ForensicProgressOverlay
        title={title}
        liveText={liveText}
        telemetryLabel="Compiling agent findings"
        showElapsed
        variant="arbiter"
      />
      <ResultSkeletonView />
    </div>
  );
}

function ResultSkeletonView() {
  return (
    <div className="min-h-screen opacity-35" aria-hidden="true">
      <div className="max-w-4xl mx-auto px-6 pt-28 space-y-4">
        <div className="skeleton h-28 rounded-2xl" />
        <div className="skeleton h-44 rounded-2xl" />
        <div className="skeleton h-12 rounded-2xl" />
        <div className="skeleton h-36 rounded-2xl" />
        <div className="skeleton h-64 rounded-2xl" />
      </div>
    </div>
  );
}

// ── Helpers ──────────────────────────────────────────────────────────────────

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

  if (findings.length > 0) return findings.slice(0, 5);

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
  return 9;
}

function severityRank(s: string): number {
  if (s === "CRITICAL") return 5;
  if (s === "HIGH") return 4;
  if (s === "MEDIUM") return 3;
  if (s === "LOW") return 2;
  return 1;
}
