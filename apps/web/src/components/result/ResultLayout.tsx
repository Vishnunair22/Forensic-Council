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
import { motion, AnimatePresence, useReducedMotion } from "framer-motion";
import { type Tab, useResult } from "@/hooks/useResult";
import { getVerdictConfig } from "@/lib/verdict";
import type { AgentFindingDTO, ReportDTO } from "@/lib/api";
import { API_BASE } from "@/lib/api";
import type { Finding } from "@/lib/types";
import { cleanFindingText } from "@/lib/findingText";
import { toast } from "@/hooks/use-toast";
import { ForensicProgressOverlay } from "@/components/ui/ForensicProgressOverlay";
import { ForensicErrorModal } from "@/components/ui/ForensicErrorModal";
import { ResultStateView } from "./ResultStateView";
import { EvidenceHeader } from "./EvidenceHeader";
import { VerdictSection } from "./VerdictSection";
import { AgentsStrip } from "./AgentsStrip";
import { IntelligenceBrief } from "./IntelligenceBrief";
import { FindingsMetadata } from "./FindingsMetadata";
import { ExecutionTimeline } from "./ExecutionTimeline";
import { ReportIntegrity } from "./ReportIntegrity";
import { PageNavigation } from "./PageNavigation";
import { DegradationBanner } from "./DegradationBanner";
import { DeepModelTelemetry } from "./DeepModelTelemetry";

function AgentAnalysisTabSkeleton() {
  return <div className="skeleton h-64 rounded-2xl" />;
}

const AgentAnalysisTab = dynamic(
  () => import("./AgentAnalysisTab").then((m) => m.AgentAnalysisTab),
  { ssr: false, loading: () => <AgentAnalysisTabSkeleton /> },
);
const HistoryPanel = dynamic(
  () => import("./HistoryPanel").then((m) => m.HistoryPanel),
  { ssr: false },
);

interface ResultLayoutProps {
  initialSessionId?: string;
}

// Hoisted outside component to prevent new object allocation on each render
const REPORT_CONTAINER_VARIANTS = {
  hidden: { opacity: 0 },
  visible: { opacity: 1, transition: { staggerChildren: 0.05, delayChildren: 0.05 } },
} as const;

const REPORT_ITEM_VARIANTS = {
  hidden: { opacity: 0, y: 4 },
  visible: { opacity: 1, y: 0, transition: { duration: 0.16 } },
} as const;

const EMPTY_VARIANTS = {} as const;

export function ResultLayout({ initialSessionId }: ResultLayoutProps = {}) {
  const rs = useResult(initialSessionId);
  const prefersReduced = useReducedMotion();

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

  return (
    <div className="min-h-screen pb-24 pt-20 sm:pt-12 relative">
      {/* ── Arbiter/Loading overlay ── */}
      {/* Cover the whole "no report yet" window with a single continuous overlay.
          When "Accept Baseline" set FC_REPORT_READY, useResult optimistically
          starts in state="ready" while the report is still being fetched — without
          this the page would render nothing (blank) until the fetch resolves. */}
      <AnimatePresence>
        {(rs.state === "arbiter" || (rs.state === "ready" && !rs.report)) && (
          <ForensicProgressOverlay
            title="Consensus Synthesis"
            liveText={rs.arbiterMsg || "Decrypting forensic ledger…"}
            telemetryLabel="Compiling agent findings"
            showElapsed
            variant="arbiter"
          />
        )}
        {rs.state === "loading" && !rs.report && (
          <div className="fixed inset-0 z-modal flex items-center justify-center fc-surface-overlay">
            <AgentAnalysisTabSkeleton />
          </div>
        )}
      </AnimatePresence>

      {/* ── Tab Nav ── */}
      <nav
        className="fixed top-16 left-0 right-0 z-modal border-b border-white/[0.06] bg-background/95"
        aria-label="Report sections"
      >
        <div className="max-w-4xl mx-auto px-4 sm:px-6 h-12 flex items-center gap-2">
          {/* Centered pill tabs */}
          <div role="tablist" aria-label="Report sections" className="flex-1 flex items-center justify-center gap-1">
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
                  "px-4 py-1.5 text-xs font-mono font-bold tracking-wider flex items-center gap-1.5 rounded-full transition-all duration-[160ms] border",
                  rs.activeTab === tab
                    ? "bg-white/[0.08] text-white border-white/20"
                    : "fc-text-muted hover:text-white hover:bg-white/[0.05] border-transparent"
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
        {/* History tab panel — always rendered; toggled with hidden for ARIA correctness */}
        <div
          role="tabpanel"
          id="tabpanel-history"
          aria-labelledby="tab-history"
          hidden={rs.activeTab !== "history"}
        >
          <HistoryPanel
            onSelect={(sid) => {
              rs.selectSession(sid);
              rs.setActiveTab("analysis");
            }}
            currentSessionId={originalSessionIdRef.current}
          />
        </div>

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

          {rs.state === "error" && !rs.errorMsg && (
            <div className="flex flex-col items-center justify-center py-32 opacity-20">
              <p className="font-mono text-xs">Analysis Pipeline Halted</p>
            </div>
          )}

          {rs.state === "empty" && (
            <ResultStateView type="empty" onNew={rs.handleNew} onHome={rs.handleHome} />
          )}

          {rs.state === "ready" && rs.report && (
            <motion.div
              initial={prefersReduced ? false : "hidden"}
              animate="visible"
              variants={prefersReduced ? EMPTY_VARIANTS : REPORT_CONTAINER_VARIANTS}
              className="space-y-4"
            >
              {/* 1. Evidence Header */}
              <motion.div variants={prefersReduced ? EMPTY_VARIANTS : REPORT_ITEM_VARIANTS}>
                <EvidenceHeader
                  fileName={rs.fileName}
                  mimeType={rs.mimeType}
                  thumbnail={rs.thumbnail}
                  pipelineStartAt={rs.pipelineStartAt}
                  caseId={rs.report.case_id}
                />
              </motion.div>

              {/* 2. Verdict + Metric Strip */}
              <motion.div variants={prefersReduced ? EMPTY_VARIANTS : REPORT_ITEM_VARIANTS}>
                <VerdictSection
                  vc={getVerdictConfig(rs.report.overall_verdict ?? "")}
                  confPct={toPct(rs.report.overall_confidence)}
                  manipPct={toPct(rs.report.manipulation_probability)}
                  errPct={toPct(rs.report.overall_error_rate)}
                  discordPct={toPct(rs.report.confidence_std_dev)}
                  isDeepPhase={rs.isDeepPhase}
                  agentCount={activeAgentIds.length}
                />
              </motion.div>

              {/* 3. Degradation Banner — only when analysis was degraded */}
              {(rs.report.degradation_flags ?? []).length > 0 && (
                <motion.div variants={prefersReduced ? EMPTY_VARIANTS : REPORT_ITEM_VARIANTS}>
                  <DegradationBanner flags={rs.report.degradation_flags ?? []} />
                </motion.div>
              )}

              {/* 4. Intelligence Brief */}
              {(keyFindings.length > 0 || rs.report.verdict_sentence || rs.report.executive_summary) && (
                <motion.div variants={prefersReduced ? EMPTY_VARIANTS : REPORT_ITEM_VARIANTS}>
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
              )}

              {/* 4.5. Agents Strip — after narrative so verdict context is established */}
              <motion.div variants={prefersReduced ? EMPTY_VARIANTS : REPORT_ITEM_VARIANTS}>
                <AgentsStrip
                  perAgentMetrics={rs.report.per_agent_metrics}
                  perAgentSummary={rs.report.per_agent_summary}
                  skippedAgents={rs.report.skipped_agents}
                  activeAgentIds={activeAgentIds}
                />
              </motion.div>

              {/* 5. Agent Findings */}
              <motion.div variants={prefersReduced ? EMPTY_VARIANTS : REPORT_ITEM_VARIANTS}>
                <AgentAnalysisTab
                  report={rs.report}
                  activeAgentIds={activeAgentIds}
                  isDeepPhase={rs.isDeepPhase}
                />
              </motion.div>

              {/* 5.5. Deep Model Telemetry — only when cross-modal fusion actually ran */}
              {rs.report?.cross_modal_fusion && Object.keys(rs.report.cross_modal_fusion).length > 0 && (
                <motion.div variants={prefersReduced ? EMPTY_VARIANTS : REPORT_ITEM_VARIANTS}>
                  <DeepModelTelemetry report={rs.report} />
                </motion.div>
              )}

              {/* 6. Analysis Metrics */}
              <motion.div variants={prefersReduced ? EMPTY_VARIANTS : REPORT_ITEM_VARIANTS}>
                <FindingsMetadata
                  report={rs.report}
                  activeAgentIds={activeAgentIds}
                />
              </motion.div>

              {/* 7. Execution Timeline */}
              <motion.div variants={prefersReduced ? EMPTY_VARIANTS : REPORT_ITEM_VARIANTS}>
                <ExecutionTimeline
                  report={rs.report}
                  activeAgentIds={activeAgentIds}
                  agentTimeline={rs.agentTimeline}
                  pipelineStartAt={rs.pipelineStartAt}
                />
              </motion.div>

              {/* 8. Report Integrity */}
              <motion.div variants={prefersReduced ? EMPTY_VARIANTS : REPORT_ITEM_VARIANTS}>
                <ReportIntegrity
                  report={rs.report}
                  sessionId={rs.sessionId}
                  isDeepPhase={rs.isDeepPhase}
                />
              </motion.div>

              {/* 9. Navigation */}
              <motion.div variants={prefersReduced ? EMPTY_VARIANTS : REPORT_ITEM_VARIANTS}>
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

function getFileExtension(contentType: string | null, headers: Headers): string {
  if (contentType?.includes("application/pdf")) return ".pdf";
  if (headers.get("X-PDF-Fallback") === "true") {
    if (contentType?.includes("text/html")) return ".html";
    return ".json";
  }
  if (contentType?.includes("text/html")) return ".html";
  if (contentType?.includes("application/json")) return ".json";
  return ".pdf";
}

function getFileTypeLabel(contentType: string | null, headers: Headers): string {
  if (contentType?.includes("application/pdf")) return "PDF";
  if (headers.get("X-PDF-Fallback") === "true") {
    if (contentType?.includes("text/html")) return "HTML";
    return "JSON";
  }
  if (contentType?.includes("text/html")) return "HTML";
  if (contentType?.includes("application/json")) return "JSON";
  return "PDF";
}

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
  const menuRef = useRef<HTMLDivElement>(null);
  const triggerRef = useRef<HTMLButtonElement>(null);
  const prefersReduced = useReducedMotion();

  // Close on outside click
  useEffect(() => {
    if (!open) return;
    const handler = (e: MouseEvent) => {
      if (ref.current && !ref.current.contains(e.target as Node)) setOpen(false);
    };
    document.addEventListener("mousedown", handler);
    return () => document.removeEventListener("mousedown", handler);
  }, [open]);

  // Close on Escape; arrow-key navigation within the menu
  useEffect(() => {
    if (!open) return;
    const handler = (e: KeyboardEvent) => {
      if (e.key === "Escape") {
        e.preventDefault();
        setOpen(false);
        triggerRef.current?.focus();
        return;
      }
      if (e.key === "ArrowDown" || e.key === "ArrowUp") {
        e.preventDefault();
        const items = menuRef.current?.querySelectorAll<HTMLElement>('[role="menuitem"]');
        if (!items || items.length === 0) return;
        const focused = document.activeElement as HTMLElement;
        const idx = Array.from(items).indexOf(focused);
        const next = e.key === "ArrowDown"
          ? (idx + 1) % items.length
          : (idx - 1 + items.length) % items.length;
        items[next]?.focus();
      }
    };
    document.addEventListener("keydown", handler);
    return () => document.removeEventListener("keydown", handler);
  }, [open]);

  // Focus first menu item when opened
  useEffect(() => {
    if (open) {
      requestAnimationFrame(() => {
        menuRef.current?.querySelector<HTMLElement>('[role="menuitem"]')?.focus();
      });
    }
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
        const contentType = res.headers.get("Content-Type");
        const ext = getFileExtension(contentType, res.headers);
        const label = getFileTypeLabel(contentType, res.headers);
        const blob = await res.blob();
        const url = URL.createObjectURL(blob);
        const a = document.createElement("a");
        a.href = url;
        a.download = `forensic-report-${(report.report_id ?? sessionId).slice(0, 8)}${ext}`;
        a.click();
        URL.revokeObjectURL(url);
        if (ext !== ".pdf") {
          toast.warning({
            title: `PDF unavailable — downloaded ${label}`,
            description: "Install WeasyPrint on the server for PDF generation.",
          });
        }
        return;
      }
      toast.warning({
        title: "PDF export unavailable",
        description: "Downloading the report as JSON instead.",
      });
      onExportJson();
    } catch {
      toast.warning({
        title: "PDF export unavailable",
        description: "Downloading the report as JSON instead.",
      });
      onExportJson();
    } finally {
      setExporting(false);
    }
  }, [sessionId, exporting, report, onExportJson]);

  const handleJson = useCallback(() => {
    setOpen(false);
    onExportJson();
  }, [onExportJson]);

  const handleDocx = useCallback(async () => {
    if (!sessionId || exporting) return;
    setExporting(true);
    setOpen(false);
    try {
      const res = await fetch(
        `${API_BASE}/api/v1/sessions/${encodeURIComponent(sessionId)}/report/docx`,
        { credentials: "include" },
      );
      if (res.ok) {
        const blob = await res.blob();
        const url = URL.createObjectURL(blob);
        const a = document.createElement("a");
        a.href = url;
        a.download = `forensic-report-${(report.report_id ?? sessionId).slice(0, 8)}.docx`;
        a.click();
        URL.revokeObjectURL(url);
        return;
      }
      if (res.status === 503) {
        toast.warning({
          title: "DOCX export unavailable",
          description: "Install python-docx on the server.",
        });
      }
    } catch {
      toast.warning({
        title: "DOCX export unavailable",
        description: "Could not download the DOCX file.",
      });
    } finally {
      setExporting(false);
    }
  }, [sessionId, exporting, report]);

  return (
    <div className="relative shrink-0" ref={ref}>
      <button
        ref={triggerRef}
        type="button"
        onClick={() => setOpen((v) => !v)}
        disabled={exporting}
        className="flex items-center gap-1.5 px-3 py-1.5 rounded-full border border-border-muted fc-text-muted hover:fc-text-primary hover:bg-white/[0.05] hover:border-border-strong transition-all duration-[160ms] fc-eyebrow focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary/50 disabled:opacity-50"
        aria-label="Export report"
        aria-haspopup="menu"
        aria-expanded={open}
        aria-controls="export-menu"
      >
        <Download className="w-3.5 h-3.5" />
        Export
        <ChevronDown className={clsx("w-3 h-3 transition-transform duration-150", open && "rotate-180")} />
      </button>

      <AnimatePresence>
        {open && (
          <motion.div
            ref={menuRef}
            id="export-menu"
            role="menu"
            aria-label="Export format options"
            initial={prefersReduced ? false : { opacity: 0, y: -4 }}
            animate={{ opacity: 1, y: 0 }}
            exit={prefersReduced ? {} : { opacity: 0, y: -4 }}
            transition={{ duration: 0.16, ease: "easeOut" }}
            className="absolute right-0 top-full mt-1.5 w-52 py-1.5 z-tooltip fc-surface-elevated overflow-hidden"
          >
            <button
              type="button"
              role="menuitem"
              onClick={handlePdf}
              className="w-full flex items-center gap-2.5 px-4 py-2.5 text-xs fc-text-muted hover:fc-text-primary hover:bg-white/[0.05] transition-colors focus-visible:outline-none focus-visible:bg-white/[0.05]"
            >
              <FileText className="w-3.5 h-3.5 shrink-0" aria-hidden="true" />
              <span className="flex flex-col items-start text-left">
                <span>PDF Report</span>
                <span className="fc-text-muted opacity-70">Best for printing</span>
              </span>
            </button>
            <button
              type="button"
              role="menuitem"
              onClick={handleDocx}
              className="w-full flex items-center gap-2.5 px-4 py-2.5 text-xs fc-text-muted hover:fc-text-primary hover:bg-white/[0.05] transition-colors focus-visible:outline-none focus-visible:bg-white/[0.05]"
            >
              <FileText className="w-3.5 h-3.5 shrink-0" aria-hidden="true" />
              <span className="flex flex-col items-start text-left">
                <span>Word (.docx)</span>
                <span className="fc-text-muted opacity-70">Editable document</span>
              </span>
            </button>
            <button
              type="button"
              role="menuitem"
              onClick={handleJson}
              className="w-full flex items-center gap-2.5 px-4 py-2.5 text-xs fc-text-muted hover:fc-text-primary hover:bg-white/[0.05] transition-colors focus-visible:outline-none focus-visible:bg-white/[0.05]"
            >
              <FileJson className="w-3.5 h-3.5 shrink-0" aria-hidden="true" />
              <span className="flex flex-col items-start text-left">
                <span>JSON Export</span>
                <span className="fc-text-muted opacity-70">Raw structured data</span>
              </span>
            </button>
          </motion.div>
        )}
      </AnimatePresence>
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
  const seen = new Set<string>();

  const push = (value: string | null | undefined) => {
    const cleaned = cleanFindingText(value);
    if (!cleaned || isLowValueFinding(cleaned)) return;
    const key = cleaned.toLowerCase().replace(/[^a-z0-9]+/g, " ").trim().slice(0, 80);
    if (seen.has(key)) return;
    seen.add(key);
    findings.push(cleaned);
  };

  // ── Backend key_findings are the canonical source of truth ───────────────────
  // The arbiter already synthesized and deduped these. Only when the backend
  // provides too few do we fall through to local re-derivation from tool
  // findings + statistical narrative (the fallback path below).
  (report.key_findings ?? []).forEach((f) => push(f));
  if (findings.length >= 3) {
    return findings.slice(0, 6);
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

  if (findings.length >= 3) {
    return findings.slice(0, 6);
  }

  const conf    = typeof report.overall_confidence === "number" ? report.overall_confidence : null;
  const manip   = typeof report.manipulation_probability === "number" ? report.manipulation_probability : null;
  const errRate = typeof report.overall_error_rate === "number" ? report.overall_error_rate : null;
  const stdDev  = typeof report.confidence_std_dev === "number" ? report.confidence_std_dev : null;
  const perAgentMetrics = report.per_agent_metrics ?? {};
  
  const AGENT_LABELS: Record<string, string> = {
    Agent1: "image forensics",
    Agent2: "audio forensics",
    Agent3: "scene analysis",
    Agent4: "video forensics",
    Agent5: "metadata analysis",
  };

  const alertAgents: string[] = [];
  const highConfAuthAgents: string[] = [];
  for (const [agentId, m] of Object.entries(perAgentMetrics)) {
    const agentConf    = m.confidence_score ?? 0;
    const agentErr     = m.error_rate ?? 0;
    const agentVerdict = (
      report.per_agent_summary?.[agentId]?.verdict ??
      (m as unknown as Record<string, unknown>).agent_verdict as string ??
      ""
    ).toUpperCase();
    const label = AGENT_LABELS[agentId] ?? agentId;
    // Per-agent summary verdicts are SUSPICIOUS / INCONCLUSIVE / AUTHENTIC / NOT_APPLICABLE
    // (arbiter._get_agent_summary never emits MANIPULATED/LIKELY_MANIPULATED at per-agent level).
    if (agentVerdict === "SUSPICIOUS" || agentVerdict === "MANIPULATED" || agentVerdict === "LIKELY_MANIPULATED") {
      alertAgents.push(`${label} (${Math.round(agentConf * 100)}% confidence)`);
    } else if (agentVerdict === "AUTHENTIC" && agentConf >= 0.80 && agentErr < 0.10) {
      highConfAuthAgents.push(label);
    }
  }

  // 1. Structural integrity / manipulation probability narrative
  if (manip !== null) {
    if (manip >= 0.75) {
      push(`Structural and statistical analysis produced a ${Math.round(manip * 100)}% manipulation probability — a critically high signal indicating the file has likely been altered or fabricated. Multiple independent domains corroborate this finding.`);
    } else if (manip >= 0.50) {
      push(`Analysis returned a ${Math.round(manip * 100)}% manipulation probability, placing this file in contested territory. Significant anomalies were identified that are inconsistent with an authentic, unaltered source.`);
    } else if (manip >= 0.20) {
      push(`Manipulation probability stands at ${Math.round(manip * 100)}%, within an uncertain range. Some forensic signals are ambiguous and full authenticity cannot be confirmed or excluded without additional context.`);
    } else if (manip < 0.10) {
      push(`File structure, binary composition, and embedded data were examined and returned a ${Math.round(manip * 100)}% manipulation probability. The file's makeup is consistent with an unmodified original and shows no signs of synthetic or AI-generated content.`);
    }
  }

  // 2. Agent domain narrative
  if (alertAgents.length > 0) {
    push(`Tampering signals were specifically flagged by ${alertAgents.join(" and ")}, each identifying anomalies in their domain that are inconsistent with an authentic, unmodified file.`);
  } else if (highConfAuthAgents.length >= 2) {
    const listed = highConfAuthAgents.length > 2
      ? `${highConfAuthAgents.slice(0, -1).join(", ")}, and ${highConfAuthAgents.slice(-1)}`
      : highConfAuthAgents.join(" and ");
    push(`Specialist examination by ${listed} confirmed authentic characteristics across each domain, with no anomalies detected in file structure, statistical patterns, or embedded metadata.`);
  } else if (highConfAuthAgents.length === 1) {
    const label = highConfAuthAgents[0];
    push(`${label.charAt(0).toUpperCase()}${label.slice(1)} examined its domain and confirmed authentic characteristics with no anomalies detected.`);
  }

  // 3. Agent discord
  if (stdDev !== null && stdDev >= 0.20) {
    push(`Specialist agents showed substantial disagreement, with a ${Math.round(stdDev * 100)}% confidence spread across the panel. This level of discord suggests contested or ambiguous evidence that warrants human review before any determination is relied upon.`);
  }

  // 4. Coverage / error rate
  if (errRate !== null && errRate < 0.05 && conf !== null && conf >= 0.80) {
    push(`All forensic examination tools ran to completion without errors, achieving full coverage across every analytical domain. The determination is supported by complete, uncompromised toolchain output.`);
  } else if (errRate !== null && errRate >= 0.30) {
    push(`A ${Math.round(errRate * 100)}% tool error rate was recorded during this analysis. Reduced coverage in affected domains may limit the completeness of the determination, and results should be interpreted accordingly.`);
  }

  // ── TIER 2: High-confidence tool findings ────────────────────────────────────
  if (findings.length < 5) {
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
  }

  return findings.slice(0, 6);
}

function cleanToolSummary(finding: AgentFindingDTO): string {
  const metadata = finding.metadata ?? {};
  const llmSummary = typeof metadata.llm_refined_summary === "string" ? metadata.llm_refined_summary : "";
  const details = typeof metadata.details === "string" ? metadata.details : "";
  return cleanFindingText(llmSummary || finding.reasoning_summary || finding.court_statement || details);
}



function isLowValueFinding(text: string): boolean {
  const lower = text.toLowerCase();
  if (lower.length < 24) return true;
  // Boilerplate / template strings
  if (lower.includes("template")) return true;
  if (lower.includes("lorem ipsum")) return true;
  if (lower.includes("no significant findings were identified")) return true;
  if (lower.includes("review the detailed findings below")) return true;
  if (lower.includes("forensic council has completed its multi-agent evaluation")) return true;
  
  // Specific noisy negative/clean findings
  if (lower.includes("anomalies: 0 — none")) return true;
  if (lower.includes("0 exif field(s)")) return true;
  if (lower.includes("no exif metadata block")) return true;
  if (lower.includes("hex signature scan found no")) return true;
  if (lower.includes("matches the chain-of-custody record") || lower.includes("sha-256 intake hash matches")) return true;
  if (lower.includes("file: the submitted file ()")) return true;
  if (lower.includes("header valid, trailer valid, appended data: none")) return true;

  // Tool-echo negative results — these confirm tools ran, not that evidence is meaningful
  if (/^(file structure|exif metadata|file hash|hash verification|metadata extraction|structure analysis)\s+(found|confirmed|detected|showed|revealed)\s+(no|no anomalies|no changes|nothing)/.test(lower)) return true;
  if (/found no (anomalies|issues|problems|changes|tampering|records|results|editing software)/.test(lower)) return true;
  if (/confirmed no (changes|anomalies|issues|tampering)/.test(lower)) return true;
  if (/no (device|capture time|gps|location) records/.test(lower)) return true;
  if (/^(no|none|n\/a|not applicable|not available|not detected|nothing)/i.test(lower)) return true;
  return false;
}



function severityRank(s: string): number {
  if (s === "CRITICAL") return 5;
  if (s === "HIGH") return 4;
  if (s === "MEDIUM") return 3;
  if (s === "LOW") return 2;
  return 1;
}
