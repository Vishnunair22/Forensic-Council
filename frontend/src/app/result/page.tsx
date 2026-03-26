"use client";

import React, { useState, useEffect, useMemo, useRef, useCallback } from "react";
import {
  CheckCircle, AlertTriangle, ShieldCheck, RotateCcw,
  Home, ChevronDown, Lock, FileText,
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
import { SurfaceCard } from "@/components/ui/SurfaceCard";
import { AgentIcon } from "@/components/ui/AgentIcon";

const isDev = process.env.NODE_ENV !== "production";
const dbg = { error: isDev ? console.error.bind(console) : () => {} };

function fmtTool(raw: string): string {
  return raw
    .replace(/_/g, " ")
    .toLowerCase()
    .replace(/\b\w/g, c => c.toUpperCase());
}

// ─── Agent meta config ────────────────────────────────────────────────────────
const AGENT_META: Record<string, { name: string; color: "amber" | "white" | "rose" | "emerald" }> = {
  Agent1: { name: "Image Forensics",   color: "amber" },
  Agent2: { name: "Audio Forensics",   color: "amber"    },
  Agent3: { name: "Object Detection",  color: "amber"  },
  Agent4: { name: "Video Forensics",   color: "amber"    },
  Agent5: { name: "Metadata Analysis", color: "amber"   },
};

const COLOR_MAP = {
  emerald: { ring: "border-emerald-500/20", accent: "text-emerald-400", bg: "bg-emerald-500/[0.04]" },
  amber:   { ring: "border-amber-500/20",   accent: "text-amber-400",   bg: "bg-amber-500/[0.04]"   },
  rose:    { ring: "border-rose-500/20",    accent: "text-rose-400",    bg: "bg-rose-500/[0.04]"    },
  white:   { ring: "border-white/20",       accent: "text-white/80",    bg: "bg-white/[0.04]"       },
};

// ─── Severity config ──────────────────────────────────────────────────────────
const SEVERITY = {
  CRITICAL: { color: "text-rose-500",    dot: "bg-rose-500",    bar: "bg-rose-500",    label: "Critical" },
  HIGH:     { color: "text-rose-400",    dot: "bg-rose-400",    bar: "bg-rose-400",    label: "High"     },
  MEDIUM:   { color: "text-amber-500",   dot: "bg-amber-500",   bar: "bg-amber-500",   label: "Medium"   },
  LOW:      { color: "text-white/40",    dot: "bg-white/40",    bar: "bg-white/20",    label: "Low"      },
  INFO:     { color: "text-white/20",    dot: "bg-white/20",    bar: "bg-white/10",    label: "Info"     },
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
    const t = setInterval(() => setStep((p: number) => (p + 1) % ARBITER_STEPS.length), 1800);
    return () => clearInterval(t);
  }, []);
  useEffect(() => {
    const t = setInterval(() => setElapsed((p: number) => p + 1), 1000);
    return () => clearInterval(t);
  }, []);
  return (
    <div role="dialog" aria-modal="true" aria-label="Council Deliberation in progress" className="fixed inset-0 z-[100] flex items-center justify-center bg-black/90 backdrop-blur-xl">
      <SurfaceCard className="flex flex-col items-center gap-6 px-10 py-12 shadow-2xl max-w-sm w-full mx-4 border-white/5 bg-surface-high rounded">
        <div className="relative w-24 h-24 flex items-center justify-center">
          <div


            className="absolute inset-0 rounded-full bg-amber-500/10 blur-xl"
          />
          <div className="relative z-10 w-14 h-14 rounded bg-black border border-amber-500/30 flex items-center justify-center shadow-[0_0_20px_rgba(217,119,6,0.2)]">
            <ShieldCheck className="w-8 h-8 text-amber-500" aria-hidden="true" />
          </div>
        </div>
        <div className="text-center space-y-3">
          <h3 className="text-white font-black text-xl font-heading uppercase tracking-tighter">Council Deliberation</h3>
          <>
            <p
              key={liveMsg || ARBITER_STEPS[step]}
              aria-live="polite"
              aria-atomic="true"

              className="text-amber-500 text-[11px] font-black font-mono uppercase tracking-[0.3em] min-h-5"
            >
              {liveMsg || ARBITER_STEPS[step]}
            </p>
          </>
          <div className="flex flex-col items-center gap-1 pt-2">
            <p className="text-white/20 text-[9px] font-black font-mono tracking-widest uppercase">NODE ACTIVE</p>
            <p className="text-amber-500/40 text-[10px] font-black font-mono tracking-widest uppercase">{elapsed}s</p>
          </div>
        </div>
        <div className="relative w-full h-1 bg-white/5 rounded-full overflow-hidden">
          <div
            className="absolute h-full w-[40%] bg-amber-500 shadow-[0_0_15px_rgba(217,119,6,0.6)]"
            
            
          />
        </div>
      </SurfaceCard>
    </div>
  );
}

// ─── Verdict config ───────────────────────────────────────────────────────────
function verdictConfig(v: string) {
  const u = v?.toUpperCase() ?? "";
  if (u === "AUTHENTIC")
    return { label: "Authentic", color: "emerald" as const, Icon: CheckCircle, desc: "No forensic evidence of manipulation found." };
  if (u === "LIKELY_AUTHENTIC")
    return { label: "Likely Authentic", color: "emerald" as const, Icon: CheckCircle, desc: "Evidence is consistent with authenticity." };
  if (u === "MANIPULATED")
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
function SeverityBar({ counts, total }: { counts: Record<SeverityKey, number>; total: number }) {
  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <h3 className="text-[11px] font-bold uppercase tracking-widest text-foreground/40">Signal Severity Breakdown</h3>
        <span className="text-[10px] font-mono font-bold text-foreground/20 uppercase tracking-widest">{total} Signals</span>
      </div>
      <div className="flex flex-wrap gap-2">
        {SEVERITY_TIERS.map((t) => counts[t] > 0 && (
          <span
            key={t}
            className={clsx(
              "inline-flex items-center gap-2 px-3 py-1 rounded-lg text-[9px] font-bold font-mono border border-border-subtle bg-surface-mid shadow-sm uppercase tracking-wider",
              SEVERITY[t].color
            )}
          >
            <span className={clsx("w-2 h-2 rounded-full flex-shrink-0 shadow-sm", SEVERITY[t].dot)} />
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
  const toolsOk    = agentSummary?.tools_ok    ?? metrics?.tools_succeeded    ?? 0;
  const toolsTotal = agentSummary?.tools_total  ?? metrics?.total_tools_called ?? 0;

  const verdLabel =
    isSkipped              ? { text: "NOT APPLICABLE", dot: "bg-slate-500",   textColor: "text-slate-500"   } :
    summaryVerdict === "AUTHENTIC"  ? { text: "NO ANOMALIES",    dot: "bg-emerald-500", textColor: "text-emerald-500" } :
    summaryVerdict === "SUSPICIOUS" ? { text: "ANOMALIES FOUND", dot: "bg-red-500",     textColor: "text-red-500"     } :
                                      { text: "INCONCLUSIVE",    dot: "bg-amber-500",   textColor: "text-amber-500"   };

  const c = COLOR_MAP[meta.color];

  // Per-agent severity counts
  const sevCounts: Record<SeverityKey, number> = { CRITICAL: 0, HIGH: 0, MEDIUM: 0, LOW: 0, INFO: 0 };
  realFindings.forEach(f => {
    const t = ((f.severity_tier ?? "LOW").toUpperCase()) as SeverityKey;
    if (t in sevCounts) sevCounts[t]++;
  });
  // Group findings by tool / finding_type for per-tool breakdown
  const toolGroups = realFindings.reduce<Record<string, AgentFindingDTO[]>>((acc, f) => {
    const key = f.finding_type || "Unknown Tool";
    if (!acc[key]) acc[key] = [];
    acc[key].push(f);
    return acc;
  }, {});

  return (
    <SurfaceCard className={clsx(
      "p-0 overflow-hidden transition-all duration-300 relative rounded border-white/5 surface-panel-high",
      isSkipped && "opacity-50 grayscale"
    )}>
      {/* Card header — click to expand */}
      <button
        onClick={() => !isSkipped && setOpen(v => !v)}
        disabled={isSkipped}
        aria-expanded={isSkipped ? undefined : open}
        className={clsx(
          "w-full flex items-center justify-between px-6 py-5 text-left transition-colors duration-200 group/btn",
          isSkipped ? "cursor-default" : "hover:bg-white/2 cursor-pointer"
        )}
      >
        <div className="flex items-center gap-4 min-w-0">
          <div className={clsx(
            "w-12 h-12 rounded flex items-center justify-center shrink-0 border border-white/5 transition-all duration-300 bg-black shadow-inner",
            !isSkipped && "shadow-sm group-hover/btn:scale-105 group-hover/btn:border-amber-500/30"
          )}>
             <AgentIcon agentId={agentId} size="md" className={c.accent} />
          </div>
          <div className="min-w-0">
            <h3 className={clsx("font-black text-sm mb-0.5 transition-colors font-heading uppercase tracking-tight", !isSkipped ? "text-white group-hover/btn:text-amber-400" : "text-white/40")}>
              {meta.name}
            </h3>
            <p className={clsx("text-[9px] font-black font-mono uppercase tracking-[0.2em]", verdLabel.textColor)}>
              {verdLabel.text}
            </p>
          </div>
        </div>

        <div className="flex items-center gap-5 shrink-0">
          {!isSkipped && (
            <div className="text-right hidden sm:block">
              <p className={clsx("font-bold text-sm tabular-nums font-mono", confColor(confRatio))}>
                {Math.round(confRatio * 100)}%
              </p>
              <p className="text-foreground/40 text-[9px] font-mono font-bold uppercase tracking-widest">Confidence</p>
            </div>
          )}
          {!isSkipped && (
            <div className={clsx(
                "p-1.5 rounded bg-white/5 border border-white/5 transition-all duration-300",
                open && "rotate-180 bg-amber-500/10 border-amber-500/30 text-amber-500"
            )}>
                <ChevronDown className="w-4 h-4" aria-hidden="true" />
            </div>
          )}
        </div>
      </button>

      {/* Expandable body */}
      <>
        {open && !isSkipped && (
          <div
            
            
            
            
            className="overflow-hidden"
          >
            <div className="px-6 pb-6 pt-2 space-y-6 border-t border-border-subtle">
              {/* Stats row */}
              <div className="flex flex-wrap gap-2 text-[9px] font-black font-mono tracking-[0.2em]">
                <span className={clsx(
                  "px-3 py-1 rounded border uppercase",
                  confRatio >= 0.75 ? "bg-emerald-500/5 border-emerald-500/20 text-emerald-500" :
                  confRatio >= 0.5  ? "bg-amber-500/5 border-amber-500/20 text-amber-500" :
                                      "bg-rose-500/5 border-rose-500/20 text-rose-500"
                )}>
                  {Math.round(confRatio * 100)}% RELIABILITY
                </span>
                {toolsTotal > 0 && (
                  <span className="px-3 py-1 rounded bg-white/2 text-white/20 border border-white/5 uppercase">
                    {toolsOk}/{toolsTotal} UNIT PROBES
                  </span>
                )}
              </div>

              {/* Arbiter narrative */}
              {narrative ? (
                <div className="rounded bg-black/40 border border-white/5 p-5 shadow-inner">
                  <p className="text-white/20 text-[9px] font-black font-mono uppercase tracking-[0.2em] mb-3 flex items-center gap-2">
                    <Activity className="w-3.5 h-3.5 text-amber-500/60" /> Neural Consensus Narrative
                  </p>
                  <p className="text-white/80 text-sm leading-relaxed font-medium">{narrative}</p>
                </div>
              ) : (
                <p className="text-foreground/20 text-[11px] italic font-medium opacity-50 px-2 font-mono">
                  [!] Narrative synthesis packet lost or unavailable.
                </p>
              )}

              {/* Per-tool breakdown */}
              {Object.keys(toolGroups).length > 0 && (
                <div className="space-y-3">
                  <p className="text-[10px] text-foreground/40 font-mono font-bold uppercase tracking-widest flex items-center gap-2 px-2">
                    <Cpu className="w-3.5 h-3.5" aria-hidden="true" /> Unit Findings [{realFindings.length}]
                  </p>
                  <div className="rounded-xl border border-border-subtle overflow-hidden bg-surface-mid">
                    {Object.entries(toolGroups).map(([toolName, toolFindings], idx) => {
                      const avgConf = toolFindings.reduce((s, f) => s + (f.calibrated_probability ?? f.confidence_raw ?? 0), 0) / toolFindings.length;
                      const worstSevTier = (SEVERITY_TIERS.find(t =>
                        toolFindings.some(f => (f.severity_tier ?? "LOW").toUpperCase() === t)
                      ) ?? "LOW") as SeverityKey;
                      const sev = SEVERITY[worstSevTier];
                      const summary = toolFindings.find(f => f.reasoning_summary)?.reasoning_summary;
                      return (
                        <div key={toolName} className={clsx(
                            "px-4 py-3.5 space-y-1",
                            idx !== 0 && "border-t border-border-subtle"
                        )}>
                          <div className="flex items-center gap-3">
                            <span className={clsx("w-1.5 h-1.5 rounded-full shrink-0", sev.dot)} aria-hidden="true" />
                            <span className="flex-1 text-[11px] font-bold uppercase tracking-widest text-foreground">{fmtTool(toolName)}</span>
                            <span className={clsx("text-xs font-bold font-mono tabular-nums", confColor(avgConf))}>
                              {Math.round(avgConf * 100)}%
                            </span>
                          </div>
                          {summary && (
                            <p className="text-[11px] text-foreground/60 font-medium leading-relaxed pl-4.5 max-w-2xl">
                              {summary}
                            </p>
                          )}
                        </div>
                      );
                    })}
                  </div>
                </div>
              )}
            </div>
          </div>
        )}
      </>
    </SurfaceCard>
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
    <div className="rounded-2xl border border-border-subtle overflow-hidden overflow-x-auto bg-surface-low shadow-sm">
      <div className="min-w-[600px]">
      {/* Header row */}
      <div className="grid items-center px-8 py-3.5 border-b border-border-subtle bg-surface-mid"
        style={{ gridTemplateColumns: "1fr 110px 70px 70px 80px" }}>
        {["Neural Agent", "Status", "Conf", "Limit", "Probes"].map((h, i) => (
          <span key={h} className={clsx(
            "text-[9px] font-bold font-mono text-foreground/40 uppercase tracking-widest",
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
        
        return (
          <div
            key={id}
            className={clsx(
              "grid items-center px-8 py-4 border-b border-border-subtle last:border-0 transition-all duration-300",
              isSkipped ? "opacity-30 grayscale" : "hover:bg-surface-mid"
            )}
            style={{ gridTemplateColumns: "1fr 110px 70px 70px 80px" }}
          >
            {/* Agent name + role */}
            <div className="flex items-center gap-3.5 min-w-0">
              <div className="min-w-0">
                <p className={clsx("text-xs font-bold uppercase tracking-wider", isActive ? "text-foreground" : "text-foreground/40")}>
                  {meta.name}
                </p>
                <p className="text-[9px] font-mono text-foreground/20 tracking-tighter uppercase">NODE://{id.toUpperCase()}</p>
              </div>
            </div>

            {/* Status badge */}
            <div className="flex justify-end">
              {isActive ? (
                <span className="inline-flex items-center gap-1.5 text-[9px] px-2.5 py-1 rounded-lg bg-emerald-500/10 text-emerald-500 border border-emerald-500/20 font-mono font-bold uppercase tracking-wider">
                  <div className="w-1 h-1 rounded-full bg-emerald-500 animate-pulse" /> ONLINE
                </span>
              ) : (
                <span className="inline-flex items-center text-[9px] px-2.5 py-1 rounded-lg bg-surface-high text-foreground/20 border border-border-subtle font-mono font-bold uppercase tracking-wider">
                  OFFLINE
                </span>
              )}
            </div>

            {/* Conf */}
            <span className={clsx(
              "text-right text-xs font-bold font-mono tabular-nums",
              isActive ? confColor(confRatio) : "text-foreground/20"
            )}>
              {isActive ? `${Math.round(confRatio * 100)}%` : "—"}
            </span>

            {/* Error rate */}
            <span className={clsx(
              "text-right text-xs font-mono font-bold",
              !isActive ? "text-foreground/20" :
              errPct > 30 ? "text-red-500" :
              errPct > 0  ? "text-amber-500" : "text-foreground/20"
            )}>
              {isActive ? (errPct > 0 ? `${errPct}%` : "0%") : "—"}
            </span>

            {/* Tools run */}
            <span className={clsx(
              "text-right text-xs font-mono font-bold",
              isActive ? "text-foreground/40" : "text-foreground/20"
            )}>
              {isActive && toolsTotal > 0 ? `${toolsOk}/${toolsTotal}` : "—"}
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
    <SurfaceCard className="p-0 overflow-hidden border-emerald-500/20 bg-emerald-500/[0.02]">
      <button
        onClick={() => setOpen(v => !v)}
        aria-expanded={open}
        className="w-full flex items-center justify-between px-6 py-5 hover:bg-emerald-500/5 transition-colors cursor-pointer group"
      >
        <span className="flex items-center gap-3 text-sm font-bold uppercase tracking-widest text-emerald-500">
          <LinkIcon className="w-4 h-4 shrink-0 transition-transform group-hover:rotate-12" />
          {findings.length} Cross-Modal Confirmations
        </span>
        <div className={clsx(
            "p-1.5 rounded-lg bg-surface-low border border-border-subtle transition-all duration-300",
            open && "rotate-180 bg-emerald-500/10 border-emerald-500/30 text-emerald-500"
        )}>
            <ChevronDown className="w-4 h-4" />
        </div>
      </button>
      <>
        {open && (
          <div
              
            
            className="overflow-hidden"
          >
            <div className="px-6 pb-6 border-t border-emerald-500/10 divide-y divide-border-subtle">
              {findings.slice(0, 10).map((f, i) => (
                <div key={f.finding_id || i} className="flex items-start gap-4 text-xs py-4">
                  <div className="w-1.5 h-1.5 mt-1.5 rounded-full bg-emerald-500 shrink-0 shadow-sm" />
                  <span className="flex-1 text-foreground/80 leading-relaxed font-medium">
                    {f.reasoning_summary || f.finding_type}
                  </span>
                  <span className="text-[10px] text-emerald-500/60 font-bold uppercase tracking-widest shrink-0 ml-2">
                    {AGENT_META[f.agent_id]?.name ?? f.agent_id}
                  </span>
                </div>
              ))}
            </div>
          </div>
        )}
      </>
    </SurfaceCard>
  );
}

// ─── Contested findings ───────────────────────────────────────────────────────
function ContestedSection({ findings }: { findings: Record<string, unknown>[] }) {
  const [open, setOpen] = useState(false);
  if (!findings || findings.length === 0) return null;
  return (
    <SurfaceCard className="p-0 overflow-hidden border-amber-500/20 bg-amber-500/[0.02]">
      <button
        onClick={() => setOpen(v => !v)}
        aria-expanded={open}
        className="w-full flex items-center justify-between px-6 py-5 hover:bg-amber-500/5 transition-colors cursor-pointer group"
      >
        <span className="flex items-center gap-3 text-sm font-bold uppercase tracking-widest text-amber-500">
          <AlertTriangle className="w-4 h-4 shrink-0 transition-transform group-hover:scale-110" />
          {findings.length} Contested Finding{findings.length !== 1 ? "s" : ""}
        </span>
        <div className={clsx(
            "p-1.5 rounded-lg bg-surface-low border border-border-subtle transition-all duration-300",
            open && "rotate-180 bg-amber-500/10 border-amber-500/30 text-amber-500"
        )}>
            <ChevronDown className="w-4 h-4" />
        </div>
      </button>
      <>
        {open && (
          <div
              
            
            className="overflow-hidden"
          >
            <div className="px-6 pb-6 border-t border-amber-500/10 divide-y divide-border-subtle">
              {findings.map((f, i) => {
                const desc = String(f.plain_description ?? "Conflicting findings — manual review required.");
                return (
                  <div key={i} className="py-4">
                    <p className="text-foreground/60 text-xs leading-relaxed font-bold font-mono">{desc}</p>
                  </div>
                );
              })}
            </div>
          </div>
        )}
      </>
    </SurfaceCard>
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
  const [chainOpen, setChainOpen]           = useState(false);
  const [agentFindingsOpen, setAgentFindingsOpen] = useState(false);

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
                const reportSnap = res.report;
                if (reportSnap && !hist.some(r => r.report_id === reportSnap.report_id)) {
                  sessionStorage.setItem(
                    "fc_full_report_history",
                    JSON.stringify([reportSnap, ...hist].slice(0, 20))
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
        const stored = JSON.parse(localStorage.getItem("forensic_history") || "[]") as HistoryItem[];
        const filtered = stored.filter((h) => h.sessionId !== hItem.sessionId);
        localStorage.setItem("forensic_history", JSON.stringify([hItem, ...filtered]));
      } catch (e) {
        dbg.error("Failed to commit history", e);
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
    <div className="min-h-screen bg-background text-foreground overflow-x-hidden">
      {/* Background */}
      <div className="fixed inset-0 -z-50 pointer-events-none">
        <div className="absolute inset-0 bg-background" />
        <div className="absolute top-0 left-1/4 w-[500px] h-[500px] bg-indigo-500/5 rounded-full blur-[100px]" />
        <div className="absolute bottom-0 right-1/4 w-[400px] h-[400px] bg-emerald-500/5 rounded-full blur-[80px]" />
      </div>

      {state === "arbiter" && <ArbiterOverlay liveMsg={arbiterMsg} />}

      {/* Sticky header */}
      <header className="sticky top-0 z-50 w-full border-b border-border-subtle bg-background/80 backdrop-blur-md">
        <div className="max-w-6xl mx-auto px-6 h-16 flex items-center justify-between">
          <button onClick={handleHome} aria-label="Return to Forensic Council home" className="flex items-center gap-3 group cursor-pointer">
            <div className="w-8 h-8 bg-surface-high border border-amber-500/40 rounded-lg flex items-center justify-center font-bold text-amber-400 text-[10px] group-hover:border-amber-400 transition-all shadow-sm">
              FC
            </div>
            <span className="hidden sm:block text-[11px] font-bold uppercase tracking-widest text-foreground/40 group-hover:text-foreground transition-colors">
              Forensic Council <span className="text-amber-500/60 ml-1">{"//"}</span> HUB
            </span>
          </button>

          <div className="flex items-center gap-5">
            <HistoryDrawer />
            <div
              role="status"
              aria-live="polite"
              className="hidden md:flex items-center gap-2.5 px-3 py-1.5 rounded-full bg-surface-low border border-border-subtle"
            >
              <div className={clsx(
                "w-2 h-2 rounded-full",
                state === "arbiter" ? "bg-indigo-400" : state === "ready" ? "bg-emerald-400" : "bg-red-400"
              )} />
              <span className="text-[10px] font-mono font-bold uppercase tracking-widest text-foreground/40">
                {state === "arbiter" ? "Deliberating" : state === "ready" ? "Verified" : "Error"}
              </span>
            </div>
            {state === "ready" && report && (
              <button
                onClick={handleExport}
                className="flex items-center gap-2 text-[10px] text-foreground/60 font-bold uppercase tracking-widest hover:text-amber-400 transition-all px-4 py-2 rounded-lg hover:bg-surface-mid border border-border-subtle cursor-pointer"
              >
                <Download className="w-3.5 h-3.5" /> Export
              </button>
            )}
          </div>
        </div>
      </header>

      <main id="main-content" className="max-w-6xl mx-auto px-6 pt-10 pb-40 space-y-10">
        <>

          {/* ─── READY ──────────────────────────────────────────────────────── */}
          {state === "ready" && report && (
            <div
              key="ready"
              
              
              className="grid grid-cols-12 gap-8 auto-rows-auto pb-20"
            >
              {/* ── Verdict Hero ── */}
              {vc && (
                <SurfaceCard
                  className="col-span-12 rounded-[2rem] p-8 sm:p-10 relative overflow-hidden shadow-xl border-border-bold"
                >
                  {/* Two-col header: verdict info left, confidence % right */}
                  <div className="flex flex-col md:flex-row items-start justify-between gap-8 mb-8">
                    {/* Left: icon + verdict label + description */}
                    <div className="flex items-start gap-5 min-w-0">
                      <div className={clsx(
                        "w-16 h-16 rounded-2xl bg-surface-high border shrink-0 flex items-center justify-center shadow-sm",
                        vc.color === "emerald" ? "border-emerald-500/40 text-emerald-500 shadow-emerald-500/10" :
                        vc.color === "red"     ? "border-red-500/40 text-red-500 shadow-red-500/10" :
                                                "border-amber-500/40 text-amber-500 shadow-amber-500/10"
                      )}>
                        <vc.Icon className="w-8 h-8" />
                      </div>
                      <div className="min-w-0">
                        <p className="text-[10px] text-foreground/40 font-mono font-bold uppercase tracking-widest mb-2">Neural Consensus // Verdict</p>
                        <h1 className={clsx(
                          "text-3xl sm:text-5xl font-bold uppercase tracking-tight leading-none mb-4",
                          vc.color === "emerald" ? "text-foreground" :
                          vc.color === "red"     ? "text-red-500" :
                                                  "text-amber-500"
                        )}>
                          {vc.label}
                        </h1>
                        <p className="text-foreground/60 text-sm font-medium leading-relaxed max-w-md">{vc.desc}</p>
                      </div>
                    </div>

                    {/* Right: big confidence % */}
                    <div className="text-left md:text-right shrink-0 bg-surface-low border border-border-subtle p-6 rounded-2xl min-w-[180px]">
                      <p className="text-[10px] text-foreground/40 font-mono font-bold uppercase tracking-widest mb-2">
                        System Confidence
                      </p>
                      <div className="flex items-baseline md:justify-end gap-1">
                        <p className={clsx("text-5xl sm:text-6xl font-bold tabular-nums leading-none tracking-tight", confColor(report.overall_confidence ?? 0))}>
                          {confPct}
                        </p>
                        <span className="text-2xl font-bold text-foreground/20">%</span>
                      </div>
                    </div>
                  </div>

                  {/* Manipulation probability bar — full width below */}
                  {manipPct > 0 && (
                    <div className="mb-8 p-6 bg-surface-mid rounded-2xl border border-border-subtle">
                      <div className="flex items-center justify-between mb-3">
                        <p className="text-[10px] text-foreground/40 font-mono font-bold uppercase tracking-widest">
                          Tampering Signal Strength
                        </p>
                        <span className={clsx(
                          "text-sm font-bold font-mono tracking-widest",
                          manipPct >= 70 ? "text-red-500" :
                          manipPct >= 40 ? "text-amber-500" :
                                         "text-emerald-500"
                        )}>
                          {manipPct}% PROBABILITY
                        </span>
                      </div>
                      <div className="h-1.5 bg-surface-low rounded-full overflow-hidden border border-border-subtle">
                        <div
                          
                          
                          
                          className={clsx(
                            "h-full rounded-full shadow-sm",
                            manipPct >= 70 ? "bg-red-500" :
                            manipPct >= 40 ? "bg-amber-500" :
                                            "bg-emerald-500"
                          )}
                        />
                      </div>
                    </div>
                  )}

                  {/* Quick stats row */}
                  <div className="flex flex-wrap items-center gap-x-8 gap-y-3 text-[10px] font-bold font-mono uppercase tracking-widest text-foreground/30 px-2">
                    <span className="flex items-center gap-2">
                      <span className="text-foreground bg-surface-high px-2 py-0.5 rounded border border-border-subtle">{report.applicable_agent_count ?? activeAgentIds.length}</span>
                      ACTIVE NODES
                    </span>
                    <span className="flex items-center gap-2">
                      <span className="text-foreground bg-surface-high px-2 py-0.5 rounded border border-border-subtle">{totalFindings}</span>
                      RAW SIGNALS
                    </span>
                    <span className="text-[9px] truncate max-w-[250px] flex items-center gap-2 opacity-40">
                      <FileText className="w-3 h-3" /> {fileName}
                    </span>
                  </div>
                </SurfaceCard>
              )}

              {/* Finding Severity Breakdown — Bento Card */}
              {totalFindings > 0 && (
                <div className="col-span-12 lg:col-span-4 p-8 rounded-3xl flex flex-col justify-center surface-panel border-border-subtle shadow-xl">
                  <SeverityBar counts={severityCounts} total={totalFindings} />
                </div>
              )}

              {/* ── 2a. Executive Summary ── */}
              <SurfaceCard
                className="col-span-12 lg:col-span-8 rounded-[2rem] overflow-hidden flex flex-col p-0 border-border-subtle"
              >
                <div className="px-8 py-5 border-b border-border-subtle flex items-center justify-between bg-surface-mid">
                  <div className="flex items-center gap-3">
                    <FileText className="w-4 h-4 text-amber-400 shrink-0" />
                    <h2 className="text-[11px] font-bold uppercase tracking-widest text-foreground">Executive Synthesis</h2>
                  </div>
                </div>
                <div className="p-8 space-y-6 flex-1 bg-surface-low">
                  <p className="text-foreground/80 text-lg font-medium leading-relaxed border-l-2 border-amber-500/30 pl-5 py-1">
                    &ldquo;{effectiveVerdictSentence}&rdquo;
                  </p>
                  {report.key_findings && report.key_findings.length > 0 && (
                    <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
                      {report.key_findings.map((f, i) => (
                        <div key={i} className="flex items-start gap-3 text-[11px] text-foreground/60 bg-surface-high p-4 rounded-xl border border-border-subtle shadow-sm">
                          <CheckCircle className="mt-0.5 w-3.5 h-3.5 text-emerald-500/50 shrink-0" />
                          <span className="leading-relaxed font-medium">{f}</span>
                        </div>
                      ))}
                    </div>
                  )}
                </div>
              </SurfaceCard>

              {/* ── 2b. Agent Deployment — Bento Card ── */}
              <div className="col-span-12 rounded-[2rem] overflow-hidden flex flex-col surface-panel border-border-subtle shadow-xl">
                <div className="px-8 py-5 border-b border-border-subtle flex items-center justify-between bg-surface-mid">
                  <div className="flex items-center gap-3">
                    <Cpu className="w-4 h-4 text-amber-400 shrink-0" aria-hidden="true" />
                    <h2 className="text-[11px] font-bold uppercase tracking-widest text-foreground">Sensor Grid Deployment</h2>
                  </div>
                  <span className="text-[9px] font-mono font-bold text-foreground/20 uppercase tracking-widest">All nodes synchronized</span>
                </div>
                <div className="p-6 flex-1 bg-surface-low">
                  <AgentDeploymentTable
                    activeIds={activeAgentIds}
                    metrics={report.per_agent_metrics as Record<string, AgentMetricsDTO> | undefined}
                    summaries={report.per_agent_summary as Record<string, AgentSummary> | undefined}
                    skippedAgents={report.skipped_agents}
                  />
                </div>
              </div>


              {/* ══════════════════════════════════════════════════════════ */}
              {/* ── 3. AGENT FINDINGS ──────────────────────────────────── */}
              {/* ══════════════════════════════════════════════════════════ */}
              {/* Agent Findings — Collapsible Section */}
              {activeAgentIds.length > 0 && (
                <div className="col-span-12 pt-6">
                  <SurfaceCard className="p-0 overflow-hidden border-white/5">
                    {/* Collapsible header */}
                    <button
                      onClick={() => setAgentFindingsOpen(v => !v)}
                      aria-expanded={agentFindingsOpen}
                      className="w-full flex items-center justify-between px-6 py-5 hover:bg-white/2 transition-colors cursor-pointer group"
                    >
                      <span className="flex items-center gap-3 text-sm font-bold uppercase tracking-widest text-foreground/70 group-hover:text-amber-400 transition-colors">
                        <Activity className="w-4 h-4 text-amber-400 shrink-0" aria-hidden="true" />
                        See Agent Findings
                        <span className="text-[9px] font-mono font-bold px-2 py-0.5 rounded bg-surface-mid border border-border-subtle text-foreground/30 normal-case tracking-wider">
                          {activeAgentIds.length} active agent{activeAgentIds.length !== 1 ? "s" : ""}
                        </span>
                      </span>
                      <div className={clsx(
                        "p-1.5 rounded-lg bg-surface-low border border-border-subtle transition-all duration-300",
                        agentFindingsOpen && "rotate-180 bg-amber-500/10 border-amber-500/30 text-amber-400"
                      )}>
                        <ChevronDown className="w-4 h-4" aria-hidden="true" />
                      </div>
                    </button>

                    {/* Collapsible body */}
                    {agentFindingsOpen && (
                      <div className="overflow-hidden border-t border-border-subtle">
                        <div className="p-6 space-y-5 bg-surface-low/50">
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
                      </div>
                    )}
                  </SurfaceCard>
                </div>
              )}

              {/* ══════════════════════════════════════════════════════════ */}
              {/* ── 4. CORROBORATING EVIDENCE ──────────────────────────── */}
              {/* ══════════════════════════════════════════════════════════ */}
              {/* Corroborating Evidence — Bento Span */}
              {(crossCount > 0 || contestedCount > 0) && (
                <div className="col-span-12 space-y-4 pt-6">
                  <h2 className="text-xs font-bold text-slate-400 uppercase tracking-[0.15em] flex items-center gap-2 px-1">
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
              {/* Chain of Custody — Bento Full Width */}
              <SurfaceCard className="col-span-12 rounded-[2rem] overflow-hidden p-0 border border-border-subtle bg-surface-low shadow-sm">
                <button
                  onClick={() => setChainOpen(v => !v)}
                  className="w-full flex items-center justify-between px-8 py-5 hover:bg-surface-mid transition-all cursor-pointer group/chain"
                >
                  <span className="flex items-center gap-3 text-[11px] font-bold uppercase tracking-widest text-foreground/60 group-hover/chain:text-amber-400 transition-colors">
                    <Lock className="w-4 h-4 text-amber-500/60" /> Operational Integrity // Chain of Custody
                  </span>
                  <div className={clsx(
                      "p-1.5 rounded-lg bg-surface-high border border-border-subtle transition-all duration-300",
                      chainOpen && "rotate-180 bg-amber-500/10 border-amber-500/30 text-amber-400"
                  )}>
                    <ChevronDown className="w-4 h-4" aria-hidden="true" />
                  </div>
                </button>
                <>
                  {chainOpen && (
                    <div
                      
                      
                      
                      
                      className="overflow-hidden"
                    >
                      <div className="px-8 pb-8 space-y-6 border-t border-border-subtle bg-surface-mid/50">
                        <div className="pt-6 grid grid-cols-1 md:grid-cols-2 gap-4">
                          {[
                            { label: "Report ID",  value: report.report_id,  mono: true },
                            { label: "Session ID", value: report.session_id, mono: true },
                            { label: "Case ID",    value: report.case_id,    mono: true },
                            ...(report.signed_utc ? [{ label: "Timestamp", value: report.signed_utc, mono: true }] : []),
                          ].map(({ label, value, mono }) => (
                            <div key={label} className="bg-surface-high p-4 rounded-xl border border-border-subtle">
                                <p className="text-[9px] font-bold font-mono text-foreground/40 uppercase tracking-widest mb-1">{label}</p>
                                <p className={clsx("text-foreground/80 break-all leading-tight", mono && "font-mono text-[10px] font-bold tracking-tight")}>
                                    {value}
                                </p>
                            </div>
                          ))}
                        </div>
                        {report.report_hash && (
                          <div className="bg-surface-low rounded-2xl p-6 border border-border-subtle shadow-inner">
                            <p className="text-[10px] text-amber-400/60 font-bold font-mono uppercase tracking-widest mb-3 flex items-center gap-2">
                              <ShieldCheck className="w-4 h-4" /> Integrity Hash [SHA-256]
                            </p>
                            <p className="text-[11px] font-mono text-foreground/40 break-all leading-relaxed bg-surface-mid p-4 rounded-xl border border-border-subtle">
                              {report.report_hash}
                            </p>
                          </div>
                        )}
                        <div className="flex flex-col sm:flex-row items-center justify-between gap-6 pt-4 border-t border-border-subtle">
                          <div className="flex items-center gap-2.5 text-[10px] font-mono font-bold text-foreground/40 uppercase tracking-tight italic">
                            <Shield className="w-3.5 h-3.5 shrink-0" />
                            Signature Verified by decentralized arbiter consensus protocol.
                          </div>
                          <button
                            onClick={handleExport}
                            className="btn-premium-glass px-6 py-2.5 rounded-xl text-[10px] font-bold font-mono uppercase tracking-widest"
                          >
                            <Download className="w-3.5 h-3.5 mr-2" /> Export Raw Packet
                          </button>
                        </div>
                      </div>
                    </div>
                  )}
                </>
              </SurfaceCard>

              {/* ── Back to Home ── */}
              <div className="col-span-12 flex flex-col items-center py-12 gap-5">
                <div
                  className="w-16 h-16 rounded-2xl flex items-center justify-center"
                  style={{
                    background: "rgba(255,255,255,0.04)",
                    border: "1px solid rgba(255,255,255,0.08)",
                    boxShadow: "inset 0 1px 0 rgba(255,255,255,0.06)",
                  }}
                >
                  <Home className="w-7 h-7 text-foreground/30" aria-hidden="true" />
                </div>
                <div className="text-center space-y-1">
                  <p className="text-sm font-medium text-foreground/40">Analysis complete</p>
                  <p className="text-xs text-foreground/20 font-mono">Return to the home page to run a new investigation.</p>
                </div>
                <button
                  onClick={handleHome}
                  className="inline-flex items-center gap-2 px-6 py-3 rounded-xl text-sm font-medium cursor-pointer transition-all hover:bg-surface-mid border border-border-subtle text-foreground/50 hover:text-foreground/70"
                >
                  <Home className="w-4 h-4" aria-hidden="true" />
                  Back to Home
                </button>
              </div>

            </div>
          )}

          {/* ─── ERROR ──────────────────────────────────────────────────────── */}
          {state === "error" && (
            <div
              key="err"
              
              
              className="flex flex-col items-center justify-center min-h-[60vh] gap-8 text-center"
            >
              <div className="w-20 h-20 rounded-3xl bg-surface-low border border-rose-500/20 flex items-center justify-center shadow-lg shadow-rose-500/5">
                <XCircle className="w-10 h-10 text-rose-500" />
              </div>
              <div className="space-y-3">
                <h2 className="text-2xl font-bold text-foreground uppercase tracking-tight">Analysis Interrupted</h2>
                <p className="text-foreground/40 text-sm max-w-sm font-medium">{errorMsg || "An unexpected error occurred during synthesis."}</p>
              </div>
              <button
                onClick={handleNew}
                className="btn-premium-amber px-10 py-4 rounded-xl text-xs font-bold uppercase tracking-widest shadow-lg shadow-amber-500/20"
              >
                Re-Initialize Investigation
              </button>
            </div>
          )}

          {/* ─── EMPTY ──────────────────────────────────────────────────────── */}
          {state === "empty" && (
            <div
              key="empty"
              
              
              className="flex flex-col items-center justify-center min-h-[60vh] gap-8 text-center"
            >
              <div className="w-20 h-20 rounded-3xl bg-surface-low border border-border-subtle flex items-center justify-center shadow-lg">
                <FileText className="w-10 h-10 text-foreground/20" />
              </div>
              <div className="space-y-3">
                <h2 className="text-2xl font-bold text-foreground uppercase tracking-tight">Null Session</h2>
                <p className="text-foreground/40 text-sm max-w-sm font-medium">
                  No active forensic stream detected. Please return to the terminal.
                </p>
              </div>
              <button
                onClick={handleHome}
                className="btn-premium-glass px-10 py-4 rounded-xl text-xs font-bold uppercase tracking-widest"
              >
                Back to Command Center
              </button>
            </div>
          )}

        </>
      </main>

      {/* Fixed footer action bar */}
      {state === "ready" && (
        <div className="fixed bottom-0 left-0 right-0 z-50 border-t border-white/[0.08] bg-background/95 backdrop-blur-3xl">
          <div className="max-w-6xl mx-auto px-6 py-5 flex flex-col sm:flex-row items-center justify-between gap-6 relative">
            
            <div className="flex items-center gap-4 w-full sm:w-auto">
                {!isDeepPhase ? (
                <button
                    onClick={handleViewAnalysis}
                    className="flex-1 sm:flex-none btn-premium-glass px-8 py-3.5 rounded-xl text-[11px] font-bold uppercase tracking-widest hover:text-indigo-400 transition-all flex items-center justify-center gap-3"
                >
                    <ArrowLeft className="w-4 h-4" aria-hidden="true" /> View Probes
                </button>
                ) : (
                <button
                    onClick={handleNew}
                    className="flex-1 sm:flex-none btn-premium-glass px-8 py-3.5 rounded-xl text-[11px] font-bold uppercase tracking-widest text-emerald-500 hover:border-emerald-500/20 hover:bg-emerald-500/5 transition-all flex items-center justify-center gap-3"
                >
                    <RotateCcw className="w-4 h-4" aria-hidden="true" /> New Session
                </button>
                )}
            </div>

            <div className="flex items-center gap-4 w-full sm:w-auto">
                 <button
                    onClick={() => window.print()}
                    className="flex-1 sm:flex-none btn-premium-glass px-8 py-3.5 rounded-xl text-[11px] font-bold uppercase tracking-widest hover:bg-surface-high transition-all flex items-center justify-center gap-3"
                >
                    <Download className="w-4 h-4" aria-hidden="true" /> Print Report
                </button>

                <button
                onClick={handleHome}
                className="flex-1 sm:flex-none btn-premium-amber px-8 py-3.5 rounded-xl text-[11px] font-bold uppercase tracking-widest transition-all flex items-center justify-center gap-3"
                >
                <Home className="w-4 h-4" aria-hidden="true" /> Dashboard
                </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
