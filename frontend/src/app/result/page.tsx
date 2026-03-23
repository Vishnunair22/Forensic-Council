"use client";

import React, { useState, useEffect, useMemo, useRef, useCallback } from "react";
import { motion, AnimatePresence } from "framer-motion";
import {
  CheckCircle, AlertTriangle, ShieldCheck, RotateCcw,
  Home, ChevronDown, Lock, Hash, FileText,
  Shield, Cpu, AlertCircle, XCircle, Download, Activity, LinkIcon, ArrowLeft
} from "lucide-react";
import { useRouter } from "next/navigation";
import clsx from "clsx";
import { useForensicData, mapReportDtoToReport } from "@/hooks/useForensicData";
import { useSound } from "@/hooks/useSound";
import { HistoryDrawer, type HistoryItem } from "@/components/ui/HistoryDrawer";
import {
  getReport, getArbiterStatus,
  type ReportDTO, type AgentFindingDTO, type AgentMetricsDTO,
} from "@/lib/api";

const isDev = process.env.NODE_ENV !== "production";
const dbg = { error: isDev ? console.error.bind(console) : () => {} };

function fmtTool(raw: string): string {
  return raw
    .replace(/_/g, " ")
    .toLowerCase()
    .replace(/\b\w/g, c => c.toUpperCase());
}

// ─── Agent meta config ────────────────────────────────────────────────────────
const AGENT_META: Record<string, { name: string; color: "emerald" | "cyan" | "indigo" | "pink" | "amber" }> = {
  Agent1: { name: "Image Forensics",   color: "emerald" },
  Agent2: { name: "Audio Forensics",   color: "cyan"    },
  Agent3: { name: "Object Detection",  color: "indigo"  },
  Agent4: { name: "Video Forensics",   color: "pink"    },
  Agent5: { name: "Metadata Analysis", color: "amber"   },
};

const COLOR_MAP = {
  emerald: { ring: "border-emerald-500/20", accent: "text-emerald-400", bg: "bg-emerald-500/[0.04]" },
  cyan:    { ring: "border-cyan-500/20",    accent: "text-cyan-400",    bg: "bg-cyan-500/[0.04]"    },
  indigo:  { ring: "border-indigo-500/20",  accent: "text-indigo-400",  bg: "bg-indigo-500/[0.04]"  },
  pink:    { ring: "border-pink-500/20",    accent: "text-pink-400",    bg: "bg-pink-500/[0.04]"    },
  amber:   { ring: "border-amber-500/20",   accent: "text-amber-400",   bg: "bg-amber-500/[0.04]"   },
};

// ─── Severity config ──────────────────────────────────────────────────────────
const SEVERITY = {
  CRITICAL: { color: "text-red-400",    dot: "bg-red-400",    bar: "bg-red-500",    label: "Critical" },
  HIGH:     { color: "text-orange-400", dot: "bg-orange-400", bar: "bg-orange-500", label: "High"     },
  MEDIUM:   { color: "text-amber-400",  dot: "bg-amber-400",  bar: "bg-amber-500",  label: "Medium"   },
  LOW:      { color: "text-slate-400",  dot: "bg-slate-500",  bar: "bg-slate-600",  label: "Low"      },
  INFO:     { color: "text-slate-600",  dot: "bg-slate-700",  bar: "bg-slate-700",  label: "Info"     },
} as const;

type SeverityKey = keyof typeof SEVERITY;
const SEVERITY_TIERS: SeverityKey[] = ["CRITICAL", "HIGH", "MEDIUM", "LOW", "INFO"];

// ─── Arbiter overlay ──────────────────────────────────────────────────────────
const ARBITER_STEPS = [
  "Gathering agent findings…",
  "Running cross-modal analysis…",
  "Resolving contested evidence…",
  "Calibrating confidence scores…",
  "Synthesising executive summary…",
  "Signing forensic report…",
];

function ArbiterOverlay({ liveMsg }: { liveMsg: string }) {
  const [step, setStep] = useState(0);
  const [elapsed, setElapsed] = useState(0);
  useEffect(() => {
    const t = setInterval(() => setStep(p => (p + 1) % ARBITER_STEPS.length), 1800);
    return () => clearInterval(t);
  }, []);
  useEffect(() => {
    const t = setInterval(() => setElapsed(p => p + 1), 1000);
    return () => clearInterval(t);
  }, []);
  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/80 backdrop-blur-lg">
      <motion.div
        initial={{ opacity: 0, scale: 0.92 }}
        animate={{ opacity: 1, scale: 1 }}
        className="flex flex-col items-center gap-6 px-8 py-10 rounded-3xl bg-[#0d0d14] border border-violet-500/25 shadow-[0_20px_80px_rgba(0,0,0,0.85)] max-w-xs w-full mx-4"
      >
        <div className="relative w-20 h-20 flex items-center justify-center">
          <motion.div
            animate={{ scale: [1, 1.25, 1], opacity: [0.15, 0.4, 0.15] }}
            transition={{ duration: 2.5, repeat: Infinity }}
            className="absolute inset-0 rounded-full bg-violet-500/20 border border-violet-500/30"
          />
          <div className="relative z-10 w-12 h-12 rounded-full bg-violet-950/80 border border-violet-500/40 flex items-center justify-center">
            <ShieldCheck className="w-6 h-6 text-violet-300" />
          </div>
          <motion.div
            animate={{ rotate: 360 }}
            transition={{ duration: 3, repeat: Infinity, ease: "linear" }}
            className="absolute inset-0 pointer-events-none"
          >
            <div className="absolute top-0.5 left-1/2 -translate-x-1/2 w-1.5 h-1.5 rounded-full bg-violet-400 shadow-[0_0_8px_rgba(139,92,246,1)]" />
          </motion.div>
        </div>
        <div className="text-center space-y-2">
          <p className="text-white font-bold text-base">Council Arbiter Deliberating</p>
          <AnimatePresence mode="wait">
            <motion.p
              key={liveMsg || ARBITER_STEPS[step]}
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
              exit={{ opacity: 0 }}
              className="text-violet-300/70 text-sm font-mono min-h-5"
            >
              {liveMsg || ARBITER_STEPS[step]}
            </motion.p>
          </AnimatePresence>
          <p className="text-slate-700 text-xs font-mono">{elapsed}s — typically 15–60s</p>
        </div>
        <div className="relative w-full h-0.5 bg-white/5 rounded-full overflow-hidden">
          <div
            className="absolute h-full w-[40%] bg-gradient-to-r from-transparent via-violet-400 to-transparent"
            style={{ animation: "bar-slide 2.2s ease-in-out infinite" }}
          />
        </div>
      </motion.div>
    </div>
  );
}

// ─── Verdict config ───────────────────────────────────────────────────────────
function verdictConfig(v: string) {
  const u = v?.toUpperCase() ?? "";
  if (u === "AUTHENTIC" || u === "CERTAIN")
    return { label: "Authentic", color: "emerald" as const, Icon: CheckCircle, desc: "No forensic evidence of manipulation found." };
  if (u === "LIKELY_AUTHENTIC" || u === "LIKELY")
    return { label: "Likely Authentic", color: "emerald" as const, Icon: CheckCircle, desc: "Evidence is consistent with authenticity." };
  if (u === "MANIPULATED" || u === "MANIPULATION DETECTED")
    return { label: "Manipulation Detected", color: "red" as const, Icon: AlertTriangle, desc: "Forensic signals confirm tampering." };
  if (u === "LIKELY_MANIPULATED")
    return { label: "Likely Manipulated", color: "red" as const, Icon: AlertTriangle, desc: "Significant manipulation signals detected." };
  if (u === "INCONCLUSIVE")
    return { label: "Inconclusive", color: "amber" as const, Icon: AlertCircle, desc: "Insufficient signal strength for a verdict." };
  return { label: "Review Required", color: "amber" as const, Icon: AlertTriangle, desc: "Manual expert review is recommended." };
}

function confColor(c: number) {
  return c >= 0.75 ? "text-emerald-400" : c >= 0.5 ? "text-amber-400" : "text-red-400";
}

// ─── Severity breakdown bar ───────────────────────────────────────────────────
function SeverityBar({ counts, total }: { counts: Record<SeverityKey, number>; total: number }) {
  if (total === 0) return null;
  return (
    <div className="space-y-4">
      <h3 className="text-[11px] font-semibold text-slate-500 uppercase tracking-[0.15em] flex items-center gap-2">
        <Activity className="w-3.5 h-3.5" aria-hidden="true" /> Finding Severity Breakdown
      </h3>
      {/* Proportional bar */}
      <div className="flex h-1.5 rounded-full overflow-hidden gap-px">
        {SEVERITY_TIERS.filter(t => counts[t] > 0).map(t => (
          <div
            key={t}
            className={SEVERITY[t].bar}
            style={{ width: `${(counts[t] / total) * 100}%` }}
          />
        ))}
      </div>
      {/* Pill counts */}
      <div className="flex flex-wrap gap-2">
        {SEVERITY_TIERS.map(t => counts[t] > 0 && (
          <span
            key={t}
            className={clsx(
              "inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-xs font-mono border border-white/[0.06] bg-white/[0.03]",
              SEVERITY[t].color
            )}
          >
            <span className={clsx("w-1.5 h-1.5 rounded-full flex-shrink-0", SEVERITY[t].dot)} />
            {counts[t]} {SEVERITY[t].label}
          </span>
        ))}
      </div>
    </div>
  );
}

// ─── Agent card ───────────────────────────────────────────────────────────────
type AgentSummary = {
  verdict: string;
  confidence_pct: number;
  tools_ok: number;
  tools_total: number;
  findings: number;
  error_rate_pct: number;
  skipped: boolean;
};

function AgentCard({
  agentId,
  findings,
  metrics,
  narrative,
  agentSummary,
}: {
  agentId: string;
  findings: AgentFindingDTO[];
  metrics?: AgentMetricsDTO;
  narrative?: string;
  agentSummary?: AgentSummary;
}) {
  const [open, setOpen] = useState(false);
  const meta = AGENT_META[agentId];
  if (!meta) return null;

  const SKIP_TYPES = new Set(["file type not applicable", "format not supported"]);
  const isSkipped = agentSummary?.skipped
    ?? metrics?.skipped
    ?? findings.every(f => SKIP_TYPES.has(String(f.finding_type).toLowerCase()));

  // Real (non-stub) findings only
  const realFindings = findings.filter(f => !SKIP_TYPES.has(String(f.finding_type).toLowerCase()));

  // Prefer per_agent_summary for stats; fall back to raw metrics
  const summaryVerdict = agentSummary?.verdict ?? "INCONCLUSIVE";
  const confRatio = agentSummary !== undefined
    ? agentSummary.confidence_pct / 100
    : (metrics?.confidence_score ?? 0);
  const errPct = agentSummary?.error_rate_pct ?? Math.round((metrics?.error_rate ?? 0) * 100);
  const toolsOk    = agentSummary?.tools_ok    ?? metrics?.tools_succeeded    ?? 0;
  const toolsTotal = agentSummary?.tools_total  ?? metrics?.total_tools_called ?? 0;

  const verdLabel =
    isSkipped              ? { text: "Not Applicable", dot: "bg-slate-600",   textColor: "text-slate-500"   } :
    summaryVerdict === "AUTHENTIC"  ? { text: "No Anomalies",    dot: "bg-emerald-400", textColor: "text-emerald-300" } :
    summaryVerdict === "SUSPICIOUS" ? { text: "Anomalies Found", dot: "bg-red-400",     textColor: "text-red-300"     } :
                                      { text: "Inconclusive",    dot: "bg-amber-400",   textColor: "text-amber-300"   };

  const c = COLOR_MAP[meta.color];

  // Per-agent severity counts
  const sevCounts: Record<SeverityKey, number> = { CRITICAL: 0, HIGH: 0, MEDIUM: 0, LOW: 0, INFO: 0 };
  realFindings.forEach(f => {
    const t = ((f.severity_tier ?? "LOW").toUpperCase()) as SeverityKey;
    if (t in sevCounts) sevCounts[t]++;
  });
  const hasSevere = sevCounts.CRITICAL > 0 || sevCounts.HIGH > 0;

  // Group findings by tool / finding_type for per-tool breakdown
  const toolGroups = realFindings.reduce<Record<string, AgentFindingDTO[]>>((acc, f) => {
    const key = f.finding_type || "Unknown Tool";
    if (!acc[key]) acc[key] = [];
    acc[key].push(f);
    return acc;
  }, {});

  return (
    <motion.div layout className={clsx(
      "rounded-2xl border overflow-hidden transition-all duration-300 relative",
      "bg-gradient-to-b from-white/[0.04] to-white/[0.015]",
      "shadow-[0_4px_20px_rgba(0,0,0,0.4),inset_0_1px_0_rgba(255,255,255,0.06)]",
      isSkipped ? "border-white/[0.05] opacity-50" : `${c.ring} hover:shadow-[0_6px_28px_rgba(0,0,0,0.55),inset_0_1px_0_rgba(255,255,255,0.08)]`
    )}>
      {/* Subtle top accent line */}
      {!isSkipped && (
        <div className={clsx(
          "absolute inset-x-0 top-0 h-[1.5px] opacity-60",
          meta.color === "emerald" ? "bg-gradient-to-r from-transparent via-emerald-500/50 to-transparent" :
          meta.color === "cyan"    ? "bg-gradient-to-r from-transparent via-cyan-500/50 to-transparent" :
          meta.color === "indigo"  ? "bg-gradient-to-r from-transparent via-indigo-500/50 to-transparent" :
          meta.color === "pink"    ? "bg-gradient-to-r from-transparent via-pink-500/50 to-transparent" :
                                     "bg-gradient-to-r from-transparent via-amber-500/50 to-transparent"
        )} />
      )}
      {/* Card header — click to expand */}
      <button
        onClick={() => !isSkipped && setOpen(v => !v)}
        disabled={isSkipped}
        aria-expanded={isSkipped ? undefined : open}
        className={clsx(
          "w-full flex items-center justify-between px-5 py-4 text-left transition-colors duration-200 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-cyan-500 rounded-xl",
          isSkipped ? "cursor-default" : `hover:${c.bg} cursor-pointer`
        )}
      >
        <div className="flex items-center gap-3 min-w-0">
          <span className={clsx("w-2 h-2 rounded-full shrink-0 mt-0.5", verdLabel.dot)} />
          <div className="min-w-0">
            <p className={clsx("font-semibold text-sm", c.accent)}>{meta.name}</p>
            <p className={clsx("text-xs", verdLabel.textColor)}>{verdLabel.text}</p>
          </div>
        </div>

        <div className="flex items-center gap-3 shrink-0">
          {/* Severity badges for severe findings */}
          {!isSkipped && hasSevere && (
            <div className="hidden sm:flex items-center gap-1">
              {sevCounts.CRITICAL > 0 && (
                <span className="text-[10px] font-mono px-1.5 py-0.5 rounded bg-red-500/15 text-red-400 border border-red-500/20">
                  {sevCounts.CRITICAL}×CRIT
                </span>
              )}
              {sevCounts.HIGH > 0 && (
                <span className="text-[10px] font-mono px-1.5 py-0.5 rounded bg-orange-500/15 text-orange-400 border border-orange-500/20">
                  {sevCounts.HIGH}×HIGH
                </span>
              )}
            </div>
          )}
          {!isSkipped && (
            <div className="text-right hidden sm:block">
              <p className={clsx("font-bold text-sm", confColor(confRatio))}>{Math.round(confRatio * 100)}%</p>
              <p className="text-slate-600 text-[10px] font-mono">conf</p>
            </div>
          )}
          {!isSkipped && (
            <ChevronDown className={clsx("w-4 h-4 text-slate-500 transition-transform duration-200", open && "rotate-180")} />
          )}
        </div>
      </button>

      {/* Expandable body */}
      <AnimatePresence initial={false}>
        {open && !isSkipped && (
          <motion.div
            initial={{ height: 0, opacity: 0 }}
            animate={{ height: "auto", opacity: 1 }}
            exit={{ height: 0, opacity: 0 }}
            transition={{ duration: 0.22 }}
            className="overflow-hidden"
          >
            <div className="px-5 pb-5 pt-4 space-y-4 border-t border-white/[0.05]">
              {/* Stats row */}
              <div className="flex flex-wrap gap-2 text-xs">
                <span className={clsx(
                  "px-2.5 py-1 rounded-full font-mono border border-white/5",
                  confRatio >= 0.75 ? "bg-emerald-500/10 text-emerald-300" :
                  confRatio >= 0.5  ? "bg-amber-500/10 text-amber-300" :
                                      "bg-red-500/10 text-red-300"
                )}>
                  {Math.round(confRatio * 100)}% confidence
                </span>
                {toolsTotal > 0 && (
                  <span className="px-2.5 py-1 rounded-full bg-white/[0.04] text-slate-400 font-mono border border-white/5">
                    {toolsOk}/{toolsTotal} tools ok
                  </span>
                )}
                {errPct > 0 && (
                  <span className={clsx(
                    "px-2.5 py-1 rounded-full font-mono border border-white/5",
                    errPct < 30 ? "bg-amber-500/10 text-amber-300" : "bg-red-500/10 text-red-300"
                  )}>
                    {errPct}% error rate
                  </span>
                )}
                <span className="px-2.5 py-1 rounded-full bg-white/[0.04] text-slate-400 font-mono border border-white/5">
                  {realFindings.length} finding{realFindings.length !== 1 ? "s" : ""}
                </span>
              </div>

              {/* Mini severity bar for this agent */}
              {realFindings.length > 0 && (
                <div className="flex gap-px h-1 rounded-full overflow-hidden">
                  {SEVERITY_TIERS.filter(t => sevCounts[t] > 0).map(t => (
                    <div
                      key={t}
                      className={SEVERITY[t].bar}
                      style={{ width: `${(sevCounts[t] / realFindings.length) * 100}%` }}
                    />
                  ))}
                </div>
              )}

              {/* Arbiter narrative */}
              {narrative ? (
                <div className="rounded-xl bg-white/[0.03] border border-white/[0.06] p-4">
                  <p className="text-[10px] text-slate-600 font-mono uppercase tracking-widest mb-2 flex items-center gap-1.5">
                    <span className="text-violet-400">✦</span> Arbiter Analysis
                  </p>
                  <p className="text-slate-300 text-sm leading-relaxed">{narrative}</p>
                </div>
              ) : (
                <p className="text-slate-600 text-xs italic">
                  Narrative synthesis unavailable — see individual findings below.
                </p>
              )}

              {/* Per-tool breakdown */}
              {Object.keys(toolGroups).length > 0 && (
                <div className="space-y-2">
                  <p className="text-[10px] text-slate-600 font-mono uppercase tracking-widest flex items-center gap-1.5">
                    <Cpu className="w-3 h-3" aria-hidden="true" /> Tool Results ({realFindings.length} finding{realFindings.length !== 1 ? "s" : ""})
                  </p>
                  <div className="rounded-xl border border-white/[0.07] overflow-hidden divide-y divide-white/[0.04]">
                    {Object.entries(toolGroups).map(([toolName, toolFindings]) => {
                      const avgConf = toolFindings.reduce((s, f) => s + (f.calibrated_probability ?? f.confidence_raw ?? 0), 0) / toolFindings.length;
                      const worstSevTier = (SEVERITY_TIERS.find(t =>
                        toolFindings.some(f => (f.severity_tier ?? "LOW").toUpperCase() === t)
                      ) ?? "LOW") as SeverityKey;
                      const sev = SEVERITY[worstSevTier];
                      // Best one-line summary from this tool's findings
                      const summary = toolFindings.find(f => f.reasoning_summary)?.reasoning_summary;
                      return (
                        <div key={toolName} className="px-3 py-2.5 space-y-0.5">
                          <div className="flex items-center gap-2.5">
                            <span className={clsx("w-1.5 h-1.5 rounded-full shrink-0", sev.dot)} aria-hidden="true" />
                            <span className="flex-1 text-xs font-medium text-slate-200 truncate">{fmtTool(toolName)}</span>
                            <span className="text-[10px] text-slate-600 font-mono shrink-0">
                              {toolFindings.length} finding{toolFindings.length !== 1 ? "s" : ""}
                            </span>
                            <span className={clsx("text-xs font-bold font-mono tabular-nums shrink-0 w-9 text-right", confColor(avgConf))}>
                              {Math.round(avgConf * 100)}%
                            </span>
                          </div>
                          {summary && (
                            <p className="text-[11px] text-slate-500 leading-relaxed pl-4 line-clamp-2">
                              {summary.slice(0, 180)}
                            </p>
                          )}
                        </div>
                      );
                    })}
                  </div>
                </div>
              )}
            </div>
          </motion.div>
        )}
      </AnimatePresence>
    </motion.div>
  );
}

// ─── Agent deployment overview table ─────────────────────────────────────────
const ALL_AGENT_IDS = Object.keys(AGENT_META) as Array<keyof typeof AGENT_META>;

function AgentDeploymentTable({
  activeIds,
  metrics,
  summaries,
  skippedAgents,
}: {
  activeIds: string[];
  metrics?: Record<string, AgentMetricsDTO>;
  summaries?: Record<string, AgentSummary>;
  skippedAgents?: Record<string, unknown>;
}) {
  const activeSet  = new Set(activeIds);
  const skippedSet = new Set(Object.keys(skippedAgents ?? {}));

  return (
    <div className="rounded-xl border border-white/[0.07] overflow-hidden overflow-x-auto">
      <div className="min-w-[480px]">
      {/* Header row */}
      <div className="grid items-center px-4 py-2 border-b border-white/[0.05] bg-white/[0.02]"
        style={{ gridTemplateColumns: "1fr 90px 52px 52px 60px" }}>
        {["Agent", "Status", "Conf", "Error", "Tools"].map((h, i) => (
          <span key={h} className={clsx(
            "text-[10px] font-mono text-slate-600 uppercase tracking-widest",
            i > 0 && "text-right"
          )}>{h}</span>
        ))}
      </div>

      {ALL_AGENT_IDS.map((id) => {
        const meta = AGENT_META[id];
        if (!meta) return null;
        const isActive  = activeSet.has(id);
        const isSkipped = skippedSet.has(id) || (!isActive);
        const summary   = summaries?.[id] as AgentSummary | undefined;
        const m         = metrics?.[id] as AgentMetricsDTO | undefined;
        const confRatio = summary ? summary.confidence_pct / 100 : (m?.confidence_score ?? 0);
        const errPct    = summary ? summary.error_rate_pct : Math.round((m?.error_rate ?? 0) * 100);
        const toolsOk   = summary?.tools_ok    ?? m?.tools_succeeded    ?? 0;
        const toolsTotal= summary?.tools_total ?? m?.total_tools_called ?? 0;
        const c = COLOR_MAP[meta.color];

        return (
          <div
            key={id}
            className={clsx(
              "grid items-center px-4 py-3 border-b border-white/[0.04] last:border-0 transition-colors",
              isSkipped ? "opacity-40" : "hover:bg-white/[0.015]"
            )}
            style={{ gridTemplateColumns: "1fr 90px 52px 52px 60px" }}
          >
            {/* Agent name + role */}
            <div className="flex items-center gap-2.5 min-w-0">
              <span className={clsx(
                "w-2 h-2 rounded-full shrink-0",
                isActive ? c.accent.replace("text-", "bg-") : "bg-slate-700"
              )} aria-hidden="true" />
              <div className="min-w-0">
                <p className={clsx("text-sm font-medium truncate", isActive ? c.accent : "text-slate-600")}>
                  {meta.name}
                </p>
              </div>
            </div>

            {/* Status badge */}
            <div className="flex justify-end">
              {isActive ? (
                <span className="inline-flex items-center gap-1 text-[10px] px-2 py-0.5 rounded-full bg-emerald-500/10 text-emerald-300 border border-emerald-500/20 font-mono">
                  <CheckCircle className="w-2.5 h-2.5" aria-hidden="true" /> Active
                </span>
              ) : (
                <span className="inline-flex items-center text-[10px] px-2 py-0.5 rounded-full bg-white/[0.04] text-slate-600 border border-white/[0.07] font-mono">
                  Skipped
                </span>
              )}
            </div>

            {/* Conf */}
            <span className={clsx(
              "text-right text-sm font-bold font-mono tabular-nums",
              isActive ? confColor(confRatio) : "text-slate-700"
            )}>
              {isActive ? `${Math.round(confRatio * 100)}%` : "—"}
            </span>

            {/* Error rate */}
            <span className={clsx(
              "text-right text-xs font-mono",
              !isActive ? "text-slate-700" :
              errPct > 30 ? "text-red-400" :
              errPct > 0  ? "text-amber-400" : "text-slate-600"
            )}>
              {isActive ? (errPct > 0 ? `${errPct}%` : "0%") : "—"}
            </span>

            {/* Tools run */}
            <span className={clsx(
              "text-right text-xs font-mono",
              isActive ? "text-slate-400" : "text-slate-700"
            )}>
              {isActive && toolsTotal > 0 ? `${toolsOk}/${toolsTotal}` : isActive ? "—" : "—"}
            </span>
          </div>
        );
      })}
      </div>
    </div>
  );
}

// ─── Cross-modal confirmations ────────────────────────────────────────────────
function CrossModalSection({ findings }: { findings: AgentFindingDTO[] }) {
  const [open, setOpen] = useState(false);
  if (!findings || findings.length === 0) return null;
  return (
    <div className="rounded-2xl bg-emerald-950/15 border border-emerald-500/20 overflow-hidden">
      <button
        onClick={() => setOpen(v => !v)}
        aria-expanded={open}
        className="w-full flex items-center justify-between px-5 py-4 hover:bg-white/[0.02] transition-colors cursor-pointer"
      >
        <span className="flex items-center gap-2 text-sm font-medium text-emerald-300">
          <LinkIcon className="w-3.5 h-3.5 shrink-0" />
          {findings.length} Cross-Modal Confirmation{findings.length !== 1 ? "s" : ""}
          <span className="hidden sm:inline text-[10px] text-emerald-600 font-normal">
            — independently confirmed by multiple agents
          </span>
        </span>
        <ChevronDown className={clsx("w-4 h-4 text-slate-600 shrink-0 transition-transform duration-200", open && "rotate-180")} />
      </button>
      <AnimatePresence initial={false}>
        {open && (
          <motion.div
            initial={{ height: 0 }} animate={{ height: "auto" }} exit={{ height: 0 }}
            transition={{ duration: 0.22 }}
            className="overflow-hidden"
          >
            <div className="px-5 pb-5 border-t border-emerald-500/10 divide-y divide-white/[0.04]">
              {findings.slice(0, 10).map((f, i) => (
                <div key={f.finding_id || i} className="flex items-start gap-2 text-xs py-2.5">
                  <span className="w-1.5 h-1.5 mt-1.5 rounded-full bg-emerald-400 shrink-0" />
                  <span className="flex-1 text-slate-300 leading-relaxed">
                    {f.reasoning_summary?.slice(0, 200) || f.finding_type}
                  </span>
                  <span className="text-slate-600 font-mono shrink-0 ml-2">
                    {AGENT_META[f.agent_id]?.name ?? f.agent_id}
                  </span>
                </div>
              ))}
              {findings.length > 10 && (
                <p className="text-slate-600 text-xs pt-2.5">+{findings.length - 10} more</p>
              )}
            </div>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
}

// ─── Contested findings ───────────────────────────────────────────────────────
function ContestedSection({ findings }: { findings: Record<string, unknown>[] }) {
  const [open, setOpen] = useState(false);
  if (!findings || findings.length === 0) return null;
  return (
    <div className="rounded-2xl bg-amber-950/15 border border-amber-500/20 overflow-hidden">
      <button
        onClick={() => setOpen(v => !v)}
        aria-expanded={open}
        className="w-full flex items-center justify-between px-5 py-4 hover:bg-white/[0.02] transition-colors cursor-pointer"
      >
        <span className="flex items-center gap-2 text-sm font-medium text-amber-300">
          <AlertTriangle className="w-3.5 h-3.5 shrink-0" />
          {findings.length} Contested Finding{findings.length !== 1 ? "s" : ""}
          <span className="hidden sm:inline text-[10px] text-amber-600 font-normal">
            — agents reached conflicting conclusions
          </span>
        </span>
        <ChevronDown className={clsx("w-4 h-4 text-slate-600 shrink-0 transition-transform duration-200", open && "rotate-180")} />
      </button>
      <AnimatePresence initial={false}>
        {open && (
          <motion.div
            initial={{ height: 0 }} animate={{ height: "auto" }} exit={{ height: 0 }}
            transition={{ duration: 0.22 }}
            className="overflow-hidden"
          >
            <div className="px-5 pb-5 border-t border-amber-500/10 divide-y divide-white/[0.04]">
              {findings.map((f, i) => {
                const desc = String(f.plain_description ?? "Conflicting findings — manual review required before use in official proceedings.");
                return (
                  <div key={i} className="py-3">
                    <p className="text-slate-400 text-xs leading-relaxed">{desc}</p>
                  </div>
                );
              })}
            </div>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
}

// ─── Main page ────────────────────────────────────────────────────────────────
type PageState = "arbiter" | "ready" | "error" | "empty";

export default function ResultPage() {
  const router = useRouter();
  const [mounted, setMounted]       = useState(false);
  const [state, setState]           = useState<PageState>("arbiter");
  const [report, setReport]         = useState<ReportDTO | null>(null);
  const [arbiterMsg, setArbiterMsg] = useState("");
  const [errorMsg, setErrorMsg]     = useState("");
  const [chainOpen, setChainOpen]   = useState(false);
  
  const [isDeepPhase, setIsDeepPhase] = useState(false);
  const historySavedRef = useRef(false);

  useEffect(() => {
    setIsDeepPhase(sessionStorage.getItem("forensic_is_deep") === "true");
  }, []);

  const { addToHistory } = useForensicData();
  const { playSound }    = useSound();
  const soundRef         = useRef(playSound);
  useEffect(() => { soundRef.current = playSound; }, [playSound]);

  // ── Poll arbiter then fetch report ───────────────────────────────────────────
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
                if (!hist.some(r => r.report_id === res.report!.report_id)) {
                  sessionStorage.setItem(
                    "fc_full_report_history",
                    JSON.stringify([res.report!, ...hist].slice(0, 20))
                  );
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

  // ── Derived data ──────────────────────────────────────────────────────────────

  // Severity counts across all findings from active agents
  const { severityCounts, totalFindings } = useMemo(() => {
    const counts: Record<SeverityKey, number> = { CRITICAL: 0, HIGH: 0, MEDIUM: 0, LOW: 0, INFO: 0 };
    const SKIP_TYPES = new Set(["file type not applicable", "format not supported"]);
    Object.values(report?.per_agent_findings ?? {}).flat().forEach(f => {
      if (SKIP_TYPES.has(String(f.finding_type).toLowerCase())) return;
      const tier = ((f.severity_tier ?? "LOW").toUpperCase()) as SeverityKey;
      if (tier in counts) counts[tier]++;
    });
    const total = Object.values(counts).reduce((a, b) => a + b, 0);
    return { severityCounts: counts, totalFindings: total };
  }, [report]);

  // Fallback verdict sentence when Groq synthesis produced nothing
  const effectiveVerdictSentence = useMemo(() => {
    if (report?.verdict_sentence) return report.verdict_sentence;
    if (!report) return "";
    const v = (report.overall_verdict ?? "").toUpperCase();
    const conf = Math.round((report.overall_confidence ?? 0) * 100);
    const mp   = Math.round((report.manipulation_probability ?? 0) * 100);
    const n    = report.applicable_agent_count ?? 0;
    if (v === "AUTHENTIC")
      return `Forensic analysis across ${n} active agent${n !== 1 ? "s" : ""} found no evidence of manipulation (${conf}% aggregate confidence).`;
    if (v === "LIKELY_AUTHENTIC")
      return `Analysis indicates the evidence is likely authentic with ${conf}% aggregate confidence — no significant manipulation signals detected.`;
    if (v === "MANIPULATED")
      return `Analysis detected manipulation with ${mp}% reliability-weighted probability confirmed by multiple independent forensic signals.`;
    if (v === "LIKELY_MANIPULATED")
      return `Analysis raised a ${mp}% manipulation probability — one or more forensic signals are consistent with evidence tampering.`;
    return `Forensic analysis returned inconclusive results (${conf}% confidence). Manual expert review is recommended before use in official proceedings.`;
  }, [report]);

  // Active agents = those with at least one non-skip finding
  const activeAgentIds = useMemo(() => {
    const SKIP_TYPES = new Set(["file type not applicable", "format not supported"]);
    return Object.keys(report?.per_agent_findings ?? {}).filter(id => {
      const flist = report?.per_agent_findings[id] ?? [];
      return flist.length > 0 && !flist.every(f => SKIP_TYPES.has(String(f.finding_type).toLowerCase()));
    });
  }, [report]);

  const vc             = report ? verdictConfig(report.overall_verdict ?? "") : null;
  const confPct        = Math.round((report?.overall_confidence ?? 0) * 100);
  const manipPct       = Math.round((report?.manipulation_probability ?? 0) * 100);
  const contestedCount = report?.contested_findings?.length ?? 0;
  const crossCount     = report?.cross_modal_confirmed?.length ?? 0;
  const skippedCount   = Object.keys(report?.skipped_agents ?? {}).length;

  const fileName = useMemo(() => {
    if (typeof window === "undefined") return report?.case_id ?? "Evidence File";
    return sessionStorage.getItem("forensic_file_name") || report?.case_id || "Evidence File";
  }, [report]);

  // ── Actions ───────────────────────────────────────────────────────────────────
  const handleNew  = useCallback(() => {
    playSound("click");
    ["forensic_session_id", "forensic_file_name", "forensic_case_id"].forEach(k =>
      sessionStorage.removeItem(k)
    );
    router.push("/evidence");
  }, [playSound, router]);

  const handleHome = useCallback(() => {
    playSound("click");
    router.push("/");
  }, [playSound, router]);

  const handleViewAnalysis = useCallback(() => {
    playSound("click");
    sessionStorage.setItem("forensic_restore_view", "true");
    router.push("/evidence");
  }, [playSound, router]);

  // History Tracker
  useEffect(() => {
    if (state === "ready" && report && !historySavedRef.current) {
      historySavedRef.current = true;
      const hItem: HistoryItem = {
        sessionId: report.session_id,
        fileName: sessionStorage.getItem("forensic_file_name") || "Unknown File",
        verdict: report.overall_verdict || "INCONCLUSIVE",
        timestamp: Date.now(),
        type: (sessionStorage.getItem("forensic_is_deep") === "true") ? "Deep" : "Initial"
      };
      
      try {
        const stored = JSON.parse(localStorage.getItem("forensic_history") || "[]");
        const filtered = stored.filter((h: any) => h.sessionId !== hItem.sessionId);
        localStorage.setItem("forensic_history", JSON.stringify([hItem, ...filtered]));
      } catch (e) {
        console.error("Failed to commit history", e);
      }
    }
  }, [state, report]);

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
    <div className="min-h-screen bg-[#030308] text-white overflow-x-hidden">
      {/* Background */}
      <div className="fixed inset-0 -z-50 pointer-events-none">
        <div className="absolute inset-0 bg-[#030308]" />
        <div className="absolute top-0 left-1/3 w-[600px] h-[400px] bg-violet-900/[0.10] rounded-full blur-[120px]" />
        <div className="absolute bottom-0 right-1/4 w-[400px] h-[300px] bg-emerald-900/[0.08] rounded-full blur-[100px]" />
        <div className="absolute inset-0 bg-[linear-gradient(to_right,#ffffff02_1px,transparent_1px),linear-gradient(to_bottom,#ffffff02_1px,transparent_1px)] bg-[size:44px_44px]" />
      </div>

      {state === "arbiter" && <ArbiterOverlay liveMsg={arbiterMsg} />}

      {/* Sticky header */}
      <header className="sticky top-0 z-30 w-full border-b border-white/[0.06] bg-[#030308]/88 backdrop-blur-2xl">
        <div className="max-w-4xl mx-auto px-5 h-14 flex items-center justify-between">
          <button onClick={handleHome} className="flex items-center gap-2 group cursor-pointer">
            <div className="w-7 h-7 bg-gradient-to-br from-emerald-400/20 to-cyan-500/10 border border-emerald-500/30 rounded-lg flex items-center justify-center font-bold text-emerald-400 text-[10px] group-hover:border-emerald-400/50 transition-colors">
              FC
            </div>
            <span className="hidden sm:block text-sm font-bold text-white/60 group-hover:text-white transition-colors">
              Forensic Council
            </span>
          </button>

          <div className="flex items-center gap-3">
            <HistoryDrawer />
            <div
              role="status"
              aria-live="polite"
              aria-label={state === "arbiter" ? "Arbiter deliberating" : state === "ready" ? "Report ready" : "Analysis failed"}
              className="flex items-center gap-2 text-xs font-mono"
            >
              <span className="relative flex h-2 w-2" aria-hidden="true">
                <span className={clsx(
                  "animate-ping absolute inline-flex h-full w-full rounded-full opacity-60",
                  state === "arbiter" ? "bg-violet-400" : state === "ready" ? "bg-emerald-400" : "bg-red-400"
                )} />
                <span className={clsx(
                  "relative inline-flex rounded-full h-2 w-2",
                  state === "arbiter" ? "bg-violet-500" : state === "ready" ? "bg-emerald-500" : "bg-red-500"
                )} />
              </span>
              <span className="text-slate-500">
                {state === "arbiter" ? "Arbiter deliberating…" : state === "ready" ? "Report ready" : "Analysis failed"}
              </span>
            </div>
            {state === "ready" && report && (
              <button
                onClick={handleExport}
                aria-label="Export report as JSON"
                className="flex items-center gap-1.5 text-xs text-slate-500 hover:text-slate-300 transition-colors px-2.5 py-1.5 rounded-lg hover:bg-white/[0.05] border border-transparent hover:border-white/[0.06] cursor-pointer"
              >
                <Download className="w-3.5 h-3.5" aria-hidden="true" /> Export
              </button>
            )}
          </div>
        </div>
      </header>

      <main className="max-w-4xl mx-auto px-5 pt-8 pb-32 space-y-4">
        <AnimatePresence mode="wait">

          {/* ─── READY ──────────────────────────────────────────────────────── */}
          {state === "ready" && report && (
            <motion.div
              key="ready"
              initial={{ opacity: 0, y: 10 }}
              animate={{ opacity: 1, y: 0 }}
              className="space-y-4"
            >
              {/* ── Verdict Hero ── */}
              {vc && (
                <motion.div
                  initial={{ opacity: 0, scale: 0.97 }}
                  animate={{ opacity: 1, scale: 1 }}
                  className={clsx(
                    "rounded-2xl border p-6 sm:p-8 relative overflow-hidden backdrop-blur-sm",
                    "shadow-[0_8px_40px_rgba(0,0,0,0.55),inset_0_1px_0_rgba(255,255,255,0.08)]",
                    vc.color === "emerald" ? "bg-gradient-to-br from-emerald-950/35 to-emerald-950/15 border-emerald-500/28" :
                    vc.color === "red"     ? "bg-gradient-to-br from-red-950/35 to-red-950/15 border-red-500/28" :
                                            "bg-gradient-to-br from-amber-950/35 to-amber-950/15 border-amber-500/28"
                  )}
                >
                  {/* Top edge shine */}
                  <div className={clsx(
                    "absolute inset-x-0 top-0 h-px",
                    vc.color === "emerald" ? "bg-gradient-to-r from-transparent via-emerald-400/40 to-transparent" :
                    vc.color === "red"     ? "bg-gradient-to-r from-transparent via-red-400/40 to-transparent" :
                                            "bg-gradient-to-r from-transparent via-amber-400/40 to-transparent"
                  )} />
                  {/* Entry shimmer */}
                  <motion.div
                    initial={{ x: "-100%" }}
                    animate={{ x: "200%", opacity: [0, 0.5, 0] }}
                    transition={{ duration: 1.4, delay: 0.1 }}
                    className="absolute inset-y-0 w-1/4 bg-gradient-to-r from-transparent via-white/[0.06] to-transparent pointer-events-none"
                  />

                  {/* Two-col header: verdict info left, confidence % right */}
                  <div className="flex items-start justify-between gap-4 mb-5">
                    {/* Left: icon + verdict label + description */}
                    <div className="flex items-start gap-3 min-w-0">
                      <div className={clsx(
                        "p-2.5 rounded-xl shrink-0 mt-0.5",
                        vc.color === "emerald" ? "bg-emerald-500/15 text-emerald-400" :
                        vc.color === "red"     ? "bg-red-500/15 text-red-400" :
                                                "bg-amber-500/15 text-amber-400"
                      )}>
                        <vc.Icon className="w-5 h-5" />
                      </div>
                      <div className="min-w-0">
                        <p className="text-[10px] text-slate-500 font-mono uppercase tracking-[0.18em] mb-0.5">Forensic Verdict</p>
                        <h1 className={clsx(
                          "text-xl sm:text-2xl font-black tracking-tight leading-none",
                          vc.color === "emerald" ? "text-emerald-300" :
                          vc.color === "red"     ? "text-red-300" :
                                                  "text-amber-300"
                        )}>
                          {vc.label}
                        </h1>
                        <p className="text-slate-500 text-xs leading-relaxed mt-1.5 max-w-xs">{vc.desc}</p>
                      </div>
                    </div>

                    {/* Right: big confidence % */}
                    <div className="text-right shrink-0">
                      <p className="text-[10px] text-slate-600 font-mono uppercase tracking-widest mb-0.5">
                        Confidence
                      </p>
                      <p className={clsx("text-4xl sm:text-5xl font-black tabular-nums leading-none", confColor(report.overall_confidence ?? 0))}>
                        {confPct}%
                      </p>
                      {(report.confidence_min ?? 0) > 0 &&
                       (report.confidence_max ?? 0) > 0 &&
                       (report.confidence_min ?? 0) !== (report.confidence_max ?? 0) && (
                        <p className="text-[10px] text-slate-600 font-mono mt-1">
                          {Math.round((report.confidence_min ?? 0) * 100)}–{Math.round((report.confidence_max ?? 0) * 100)}% range
                        </p>
                      )}
                    </div>
                  </div>

                  {/* Manipulation probability bar — full width below */}
                  {manipPct > 0 && (
                    <div className="mb-5">
                      <div className="flex items-center justify-between mb-1.5">
                        <p className="text-[10px] text-slate-600 font-mono uppercase tracking-widest">
                          Manipulation Probability
                        </p>
                        <span className={clsx(
                          "text-sm font-black tabular-nums font-mono",
                          manipPct >= 70 ? "text-red-400" :
                          manipPct >= 40 ? "text-amber-400" :
                                         "text-emerald-400"
                        )}>
                          {manipPct}%
                        </span>
                      </div>
                      <div className="h-1.5 bg-white/[0.06] rounded-full overflow-hidden">
                        <motion.div
                          initial={{ width: 0 }}
                          animate={{ width: `${manipPct}%` }}
                          transition={{ duration: 0.9, ease: "easeOut", delay: 0.4 }}
                          className={clsx(
                            "h-full rounded-full",
                            manipPct >= 70 ? "bg-red-500" :
                            manipPct >= 40 ? "bg-amber-500" :
                                            "bg-emerald-500"
                          )}
                        />
                      </div>
                    </div>
                  )}

                  {/* Divider */}
                  <div className="h-px bg-white/[0.05] mb-4" />

                  {/* Quick stats row */}
                  <div className="flex flex-wrap gap-x-5 gap-y-2 text-[11px] font-mono text-slate-500">
                    <span>
                      <span className="text-white font-bold">{report.applicable_agent_count ?? activeAgentIds.length}</span>
                      {" "}agents active
                    </span>
                    <span>
                      <span className="text-white font-bold">{totalFindings}</span>
                      {" "}findings
                    </span>
                    {crossCount > 0 && (
                      <span className="text-emerald-400">
                        <span className="font-bold">{crossCount}</span> cross-confirmed
                      </span>
                    )}
                    {contestedCount > 0 && (
                      <span className="text-amber-400">
                        <span className="font-bold">{contestedCount}</span> contested
                      </span>
                    )}
                    {skippedCount > 0 && (
                      <span>{skippedCount} agent{skippedCount !== 1 ? "s" : ""} skipped</span>
                    )}
                    <span className="truncate max-w-[200px] text-slate-600">{fileName}</span>
                  </div>
                </motion.div>
              )}

              {/* ══════════════════════════════════════════════════════════ */}
              {/* ── 2. ANALYSIS REPORT ─────────────────────────────────── */}
              {/* ══════════════════════════════════════════════════════════ */}
              <div className="rounded-2xl overflow-hidden relative glass-panel">
                {/* Card top-edge shine */}
                <div className="absolute inset-x-0 top-0 h-px bg-gradient-to-r from-transparent via-white/20 to-transparent pointer-events-none" />

                {/* ── Card header ── */}
                <div className="px-6 py-4 border-b border-white/[0.06] flex items-center gap-2.5">
                  <FileText className="w-4 h-4 text-emerald-400 shrink-0" aria-hidden="true" />
                  <h2 className="text-sm font-semibold text-white">Analysis Report</h2>
                  <span className="ml-auto text-[10px] font-mono text-slate-600 truncate max-w-[160px]">
                    {report.case_id}
                  </span>
                </div>

                {/* ── 2a. Executive Summary ── */}
                <div className="p-6 border-b border-white/[0.05] space-y-3">
                  <h3 className="text-[11px] font-semibold text-slate-500 uppercase tracking-[0.15em] flex items-center gap-2">
                    <FileText className="w-3.5 h-3.5" aria-hidden="true" /> Executive Summary
                  </h3>
                  <p className="text-slate-200 text-sm font-medium leading-relaxed">
                    {effectiveVerdictSentence}
                  </p>
                  {report.key_findings && report.key_findings.length > 0 ? (
                    <ul className="space-y-2 pt-1">
                      {report.key_findings.map((f, i) => (
                        <li key={i} className="flex items-start gap-2.5 text-sm text-slate-400">
                          <span className="mt-2 w-1.5 h-1.5 rounded-full bg-emerald-500/50 shrink-0" aria-hidden="true" />
                          <span className="leading-relaxed">{f}</span>
                        </li>
                      ))}
                    </ul>
                  ) : report.executive_summary ? (
                    <p className="text-slate-400 text-sm leading-relaxed">{report.executive_summary}</p>
                  ) : null}
                  {report.reliability_note && (
                    <p className="text-slate-600 text-xs leading-relaxed border-t border-white/[0.06] pt-3 italic">
                      {report.reliability_note}
                    </p>
                  )}
                </div>

                {/* ── 2b. Agent Deployment Overview ── */}
                <div className="p-6 border-b border-white/[0.05] space-y-3">
                  <h3 className="text-[11px] font-semibold text-slate-500 uppercase tracking-[0.15em] flex items-center gap-2">
                    <Cpu className="w-3.5 h-3.5" aria-hidden="true" /> Agent Deployment
                  </h3>
                  <AgentDeploymentTable
                    activeIds={activeAgentIds}
                    metrics={report.per_agent_metrics as Record<string, AgentMetricsDTO> | undefined}
                    summaries={report.per_agent_summary as Record<string, AgentSummary> | undefined}
                    skippedAgents={report.skipped_agents}
                  />
                </div>

                {/* ── 2c. Finding Severity Breakdown ── */}
                {totalFindings > 0 && (
                  <div className="p-6 border-b border-white/[0.05]">
                    <SeverityBar counts={severityCounts} total={totalFindings} />
                  </div>
                )}

                {/* ── 2d. Coverage & Limitations ── */}
                {(report.analysis_coverage_note || report.uncertainty_statement) && (
                  <div className="px-6 py-5 flex gap-3">
                    <AlertCircle className="w-4 h-4 text-amber-400/80 shrink-0 mt-0.5" aria-hidden="true" />
                    <div className="space-y-1.5 min-w-0">
                      <p className="text-[11px] font-semibold text-amber-400/80 uppercase tracking-[0.15em]">
                        Limitations
                      </p>
                      {report.analysis_coverage_note && (
                        <p className="text-slate-400 text-sm leading-relaxed">{report.analysis_coverage_note}</p>
                      )}
                      {report.uncertainty_statement &&
                       report.uncertainty_statement !== report.analysis_coverage_note && (
                        <p className="text-slate-500 text-xs leading-relaxed">{report.uncertainty_statement}</p>
                      )}
                    </div>
                  </div>
                )}
              </div>

              {/* ══════════════════════════════════════════════════════════ */}
              {/* ── 3. AGENT FINDINGS ──────────────────────────────────── */}
              {/* ══════════════════════════════════════════════════════════ */}
              {activeAgentIds.length > 0 && (
                <div className="space-y-2.5">
                  <div className="flex items-center justify-between px-1 pt-2">
                    <h2 className="text-xs font-bold text-slate-400 uppercase tracking-[0.15em] flex items-center gap-2">
                      <Activity className="w-3.5 h-3.5 text-cyan-400" aria-hidden="true" /> Agent Findings
                    </h2>
                    <span className="text-[10px] text-slate-600 font-mono">
                      tap card to expand ↓
                    </span>
                  </div>
                  {activeAgentIds.map(id => (
                    <AgentCard
                      key={id}
                      agentId={id}
                      findings={report.per_agent_findings[id] ?? []}
                      metrics={report.per_agent_metrics?.[id] as AgentMetricsDTO | undefined}
                      narrative={report.per_agent_analysis?.[id]}
                      agentSummary={report.per_agent_summary?.[id] as AgentSummary | undefined}
                    />
                  ))}
                </div>
              )}

              {/* ══════════════════════════════════════════════════════════ */}
              {/* ── 4. CORROBORATING EVIDENCE ──────────────────────────── */}
              {/* ══════════════════════════════════════════════════════════ */}
              {(crossCount > 0 || contestedCount > 0) && (
                <div className="space-y-2.5">
                  <h2 className="text-xs font-bold text-slate-400 uppercase tracking-[0.15em] flex items-center gap-2 px-1 pt-2">
                    <LinkIcon className="w-3.5 h-3.5 text-emerald-400" aria-hidden="true" /> Corroborating Evidence
                  </h2>
                  {crossCount > 0 && (
                    <CrossModalSection findings={report.cross_modal_confirmed as AgentFindingDTO[]} />
                  )}
                  {contestedCount > 0 && (
                    <ContestedSection findings={report.contested_findings} />
                  )}
                </div>
              )}

              {/* ══════════════════════════════════════════════════════════ */}
              {/* ── 5. CHAIN OF CUSTODY ────────────────────────────────── */}
              {/* ══════════════════════════════════════════════════════════ */}
              <div className="rounded-2xl overflow-hidden
                bg-gradient-to-b from-white/[0.035] to-white/[0.012]
                border border-white/[0.07]
                shadow-[0_4px_16px_rgba(0,0,0,0.30),inset_0_1px_0_rgba(255,255,255,0.06)]">
                <button
                  onClick={() => setChainOpen(v => !v)}
                  className="w-full flex items-center justify-between px-5 py-4 hover:bg-white/[0.025] transition-colors duration-200 cursor-pointer"
                >
                  <span className="flex items-center gap-2 text-sm text-slate-400 font-medium">
                    <Lock className="w-3.5 h-3.5 text-cyan-400" aria-hidden="true" /> Chain of Custody &amp; Signature
                  </span>
                  <ChevronDown className={clsx("w-4 h-4 text-slate-600 transition-transform duration-200", chainOpen && "rotate-180")} aria-hidden="true" />
                </button>
                <AnimatePresence initial={false}>
                  {chainOpen && (
                    <motion.div
                      initial={{ height: 0 }}
                      animate={{ height: "auto" }}
                      exit={{ height: 0 }}
                      transition={{ duration: 0.22 }}
                      className="overflow-hidden"
                    >
                      <div className="px-5 pb-5 space-y-4 border-t border-white/[0.05]">
                        <div className="pt-4 space-y-3 text-sm text-slate-400">
                          {[
                            { label: "Report ID",  value: report.report_id,  mono: true },
                            { label: "Session ID", value: report.session_id, mono: true },
                            { label: "Case ID",    value: report.case_id,    mono: true },
                            ...(report.signed_utc ? [{ label: "Signed", value: report.signed_utc, mono: true }] : []),
                          ].map(({ label, value, mono }) => (
                            <div key={label} className="flex items-start gap-2">
                              <Hash className="w-3.5 h-3.5 shrink-0 mt-0.5 text-slate-600" />
                              <span>
                                <span className="text-slate-600">{label}: </span>
                                <span className={clsx("text-slate-300 break-all", mono && "font-mono text-xs")}>
                                  {value}
                                </span>
                              </span>
                            </div>
                          ))}
                        </div>
                        {report.report_hash && (
                          <div>
                            <p className="text-[10px] text-slate-600 font-mono uppercase tracking-widest mb-1.5">
                              Report Hash (SHA-256)
                            </p>
                            <p className="text-xs font-mono text-slate-500 break-all bg-black/30 rounded-xl p-3 leading-relaxed">
                              {report.report_hash}
                            </p>
                          </div>
                        )}
                        {report.cryptographic_signature && (
                          <div>
                            <p className="text-[10px] text-slate-600 font-mono uppercase tracking-widest mb-1.5">
                              Arbiter Signature
                            </p>
                            <p className="text-xs font-mono text-slate-600 break-all bg-black/30 rounded-xl p-3 leading-relaxed">
                              {report.cryptographic_signature}
                            </p>
                          </div>
                        )}
                        <div className="flex items-center justify-between gap-4 pt-1">
                          <div className="flex items-center gap-1.5 text-[10px] text-slate-700">
                            <Shield className="w-3 h-3 shrink-0" />
                            Signature guarantees this report has not been altered since generation.
                          </div>
                          <button
                            onClick={handleExport}
                            className="flex items-center gap-1.5 text-[10px] text-slate-600 hover:text-slate-400 transition-colors font-mono shrink-0 cursor-pointer"
                          >
                            <Download className="w-3 h-3" /> Export JSON
                          </button>
                        </div>
                      </div>
                    </motion.div>
                  )}
                </AnimatePresence>
              </div>

            </motion.div>
          )}

          {/* ─── ERROR ──────────────────────────────────────────────────────── */}
          {state === "error" && (
            <motion.div
              key="err"
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
              className="flex flex-col items-center justify-center min-h-[55vh] gap-6 text-center"
            >
              <div className="w-16 h-16 rounded-full bg-red-500/10 border border-red-500/20 flex items-center justify-center">
                <XCircle className="w-8 h-8 text-red-400" />
              </div>
              <div>
                <h2 className="text-xl font-bold text-white mb-2">Analysis Failed</h2>
                <p className="text-slate-500 text-sm max-w-sm">{errorMsg || "An unexpected error occurred."}</p>
              </div>
              <button
                onClick={handleNew}
                className="btn btn-violet px-6 py-3 rounded-xl text-sm font-semibold"
              >
                New Investigation
              </button>
            </motion.div>
          )}

          {/* ─── EMPTY ──────────────────────────────────────────────────────── */}
          {state === "empty" && (
            <motion.div
              key="empty"
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
              className="flex flex-col items-center justify-center min-h-[55vh] gap-6 text-center"
            >
              <div className="w-16 h-16 rounded-full bg-slate-500/10 border border-slate-500/20 flex items-center justify-center">
                <FileText className="w-8 h-8 text-slate-400" />
              </div>
              <div>
                <h2 className="text-xl font-bold text-white mb-2">No Report Found</h2>
                <p className="text-slate-500 text-sm max-w-sm">
                  No investigation data found for this session. It may have expired or not been started.
                </p>
              </div>
              <button
                onClick={handleHome}
                className="btn btn-emerald px-6 py-3 rounded-xl text-sm font-semibold"
              >
                Back to Home
              </button>
            </motion.div>
          )}

        </AnimatePresence>
      </main>

      {/* Fixed footer action bar */}
      {state === "ready" && (
        <div className="fixed bottom-0 left-0 right-0 z-20 border-t border-white/[0.06]"
          style={{ background: "rgba(3,3,3,0.88)", backdropFilter: "blur(24px)" }}>
          <div className="max-w-4xl mx-auto px-5 py-3 flex items-center justify-center gap-4 relative">
            
            {/* Left Button */}
            {!isDeepPhase ? (
              <button
                onClick={handleViewAnalysis}
                className="btn btn-ghost px-5 py-2.5 rounded-xl text-sm border border-white/10 hover:border-violet-500/30 font-medium flex items-center gap-2"
              >
                <ArrowLeft className="w-4 h-4" aria-hidden="true" /> View Analysis
              </button>
            ) : (
              <button
                onClick={handleNew}
                className="btn btn-emerald px-5 py-2.5 rounded-xl text-sm font-semibold flex items-center gap-2"
              >
                <RotateCcw className="w-4 h-4" aria-hidden="true" /> New Investigation
              </button>
            )}

            {/* Right Button */}
            <button
              onClick={handleHome}
              className="btn btn-ghost px-5 py-2.5 rounded-xl text-sm flex items-center gap-2"
            >
              <Home className="w-4 h-4" aria-hidden="true" /> Back to Home
            </button>
          </div>
        </div>
      )}
    </div>
  );
}
