"use client";

/**
 * Result Page — Forensic Council
 * ================================
 * Renders the arbiter-compiled forensic report after initial or deep analysis.
 *
 * Flow:
 *  1. Page mounts → reads session_id from sessionStorage
 *  2. Polls /arbiter-status (lightweight) until status = "complete" | "error"
 *  3. On complete → fetches full /report and renders structured sections
 *  4. Overlay shown while arbiter compiles so user knows something is happening
 */

import React, { useState, useEffect, useMemo, useRef, useCallback } from "react";
import { motion, AnimatePresence } from "framer-motion";
import {
  FileCheck, CheckCircle, AlertTriangle, Lock,
  ChevronDown, ChevronUp, MonitorPlay, Mic2,
  Image as ImageIcon, Binary, Home, RotateCcw,
  ShieldCheck, Search, Layers, XCircle, Shield,
  Hash, Clock, FileText, Cpu, AlertCircle,
} from "lucide-react";
import { PageTransition } from "@/components/ui/PageTransition";
import { GlobalFooter } from "@/components/ui/GlobalFooter";
import { useRouter } from "next/navigation";
import clsx from "clsx";
import { useForensicData, mapReportDtoToReport } from "@/hooks/useForensicData";
import { useSound } from "@/hooks/useSound";
import { getReport, getArbiterStatus, type ReportDTO, type AgentFindingDTO, type AgentMetricsDTO } from "@/lib/api";

/** Dev-only logger — silenced in production builds */
const isDev = process.env.NODE_ENV !== "production";
const dbg = {
  error: isDev ? console.error.bind(console) : () => {},
};

// ─────────────────────────────────────────────────────────────
// AGENT CONFIG
// ─────────────────────────────────────────────────────────────

const AGENT_CFG: Record<string, {
  name: string; role: string; icon: React.ReactNode;
  accent: string; border: string; headerBg: string;
}> = {
  Agent1: {
    name: "Image Forensics", role: "Visual Analysis & Authenticity",
    icon: <ImageIcon className="w-4 h-4" />,
    accent: "text-emerald-400", border: "border-emerald-500/20",
    headerBg: "bg-emerald-500/8",
  },
  Agent2: {
    name: "Audio Forensics", role: "Sound & Voice Analysis",
    icon: <Mic2 className="w-4 h-4" />,
    accent: "text-cyan-400", border: "border-cyan-500/20",
    headerBg: "bg-cyan-500/8",
  },
  Agent3: {
    name: "Object Detection", role: "Content & Scene Recognition",
    icon: <Search className="w-4 h-4" />,
    accent: "text-indigo-400", border: "border-indigo-500/20",
    headerBg: "bg-indigo-500/8",
  },
  Agent4: {
    name: "Video Forensics", role: "Temporal & Motion Analysis",
    icon: <MonitorPlay className="w-4 h-4" />,
    accent: "text-pink-400", border: "border-pink-500/20",
    headerBg: "bg-pink-500/8",
  },
  Agent5: {
    name: "Metadata Analysis", role: "Digital Provenance & Footprints",
    icon: <Binary className="w-4 h-4" />,
    accent: "text-amber-400", border: "border-amber-500/20",
    headerBg: "bg-amber-500/8",
  },
};

// ─────────────────────────────────────────────────────────────
// HELPERS
// ─────────────────────────────────────────────────────────────

function confColor(c: number) {
  if (c >= 0.78) return "text-emerald-400";
  if (c >= 0.52) return "text-amber-400";
  return "text-red-400";
}

function confBadge(c: number) {
  if (c >= 0.78) return "bg-emerald-500/12 border-emerald-500/25 text-emerald-300";
  if (c >= 0.52) return "bg-amber-500/12 border-amber-500/25 text-amber-300";
  return "bg-red-500/12 border-red-500/25 text-red-300";
}

function PhasePill({ phase }: { phase?: string }) {
  if (phase === "deep")
    return <span className="text-[9px] px-1.5 py-0.5 rounded-full bg-purple-500/18 text-purple-300 border border-purple-500/25 font-mono leading-none">DEEP</span>;
  if (phase === "initial")
    return <span className="text-[9px] px-1.5 py-0.5 rounded-full bg-slate-500/15 text-slate-400 border border-slate-600/20 font-mono leading-none">INIT</span>;
  return null;
}

function StatusDot({ status }: { status: string }) {
  if (status === "CONFIRMED") return <span className="w-1.5 h-1.5 rounded-full bg-emerald-400 shrink-0 mt-1.5" />;
  if (status === "CONTESTED") return <span className="w-1.5 h-1.5 rounded-full bg-amber-400 shrink-0 mt-1.5" />;
  return <span className="w-1.5 h-1.5 rounded-full bg-slate-500 shrink-0 mt-1.5" />;
}

// ─────────────────────────────────────────────────────────────
// ARBITER OVERLAY (shown while deliberating)
// ─────────────────────────────────────────────────────────────

const ARBITER_STEPS = [
  "Gathering all agent findings…",
  "Running cross-modal comparison…",
  "Resolving contested evidence…",
  "Calibrating confidence scores…",
  "Generating executive summary via Groq…",
  "Signing cryptographic hash…",
  "Finalising court-ready report…",
];

function ArbiterOverlay({ liveMessage }: { liveMessage: string }) {
  const [step, setStep] = useState(0);
  const [elapsed, setElapsed] = useState(0);

  useEffect(() => {
    const id = setInterval(() => setStep(p => (p + 1) % ARBITER_STEPS.length), 1600);
    return () => clearInterval(id);
  }, []);

  useEffect(() => {
    const id = setInterval(() => setElapsed(p => p + 1), 1000);
    return () => clearInterval(id);
  }, []);

  const displayMsg = liveMessage || ARBITER_STEPS[step];

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/75 backdrop-blur-md">
      <motion.div
        initial={{ opacity: 0, scale: 0.9, y: 10 }}
        animate={{ opacity: 1, scale: 1, y: 0 }}
        className="flex flex-col items-center gap-7 px-8 py-10 rounded-3xl bg-[#090910]/95 border border-white/10 shadow-[0_20px_80px_rgba(0,0,0,0.8)] max-w-[340px] w-full mx-4"
      >
        {/* Pulsing shield */}
        <div className="relative w-24 h-24 flex items-center justify-center">
          <motion.div
            animate={{ scale: [1, 1.2, 1], opacity: [0.2, 0.45, 0.2] }}
            transition={{ duration: 2.4, repeat: Infinity, ease: "easeInOut" }}
            className="absolute inset-0 rounded-full bg-purple-500/20 border border-purple-500/30"
          />
          <motion.div
            animate={{ scale: [1, 1.1, 1], opacity: [0.35, 0.6, 0.35] }}
            transition={{ duration: 2.4, repeat: Infinity, ease: "easeInOut", delay: 0.5 }}
            className="absolute inset-3 rounded-full border border-purple-400/20"
          />
          <div className="relative z-10 w-14 h-14 rounded-full bg-purple-950/80 border border-purple-500/40 flex items-center justify-center shadow-[0_0_40px_rgba(168,85,247,0.4)]">
            <ShieldCheck className="w-7 h-7 text-purple-300" />
          </div>
          {/* Orbiting dot */}
          <motion.div
            animate={{ rotate: 360 }}
            transition={{ duration: 2.8, repeat: Infinity, ease: "linear" }}
            className="absolute inset-0 pointer-events-none"
          >
            <div className="absolute top-0.5 left-1/2 -translate-x-1/2 w-2 h-2 rounded-full bg-purple-400 shadow-[0_0_8px_rgba(168,85,247,1)]" />
          </motion.div>
        </div>

        <div className="text-center space-y-2 w-full">
          <p className="text-white font-bold text-lg">Council Arbiter Deliberating</p>
          <AnimatePresence mode="wait">
            <motion.p
              key={displayMsg}
              initial={{ opacity: 0, y: 5 }}
              animate={{ opacity: 1, y: 0 }}
              exit={{ opacity: 0, y: -5 }}
              transition={{ duration: 0.3 }}
              className="text-purple-300/75 text-sm font-mono min-h-[1.4rem]"
            >
              {displayMsg}
            </motion.p>
          </AnimatePresence>
        </div>

        {/* Progress bar */}
        <div className="w-full h-0.5 bg-white/5 rounded-full overflow-hidden">
          <motion.div
            animate={{ x: ["-100%", "220%"] }}
            transition={{ duration: 2.6, repeat: Infinity, ease: "easeInOut" }}
            className="h-full w-1/3 bg-gradient-to-r from-transparent via-purple-400 to-transparent"
          />
        </div>

        <p className="text-xs text-slate-700 font-mono">{elapsed}s elapsed — typically 10–60s</p>
      </motion.div>
    </div>
  );
}

// ─────────────────────────────────────────────────────────────
// FINDING CARD
// ─────────────────────────────────────────────────────────────

function FindingCard({ f, accent }: { f: AgentFindingDTO; accent: string }) {
  const [expanded, setExpanded] = useState(false);
  const phase = f.metadata?.analysis_phase as string | undefined;
  const toolName = (f.metadata?.tool_name as string | undefined) ?? "";
  const isGemini = toolName.toLowerCase().includes("gemini");
  const conf = f.calibrated_probability ?? f.confidence_raw ?? 0;
  const confPct = Math.round(conf * 100);
  const summary = f.reasoning_summary || "";
  const LIMIT = 240;
  const isLong = summary.length > LIMIT;

  return (
    <div className="flex gap-3 py-3 border-b border-white/[0.05] last:border-0">
      <StatusDot status={f.status} />
      <div className="flex-1 min-w-0">
        {/* Row: type + badges */}
        <div className="flex flex-wrap items-center gap-1.5 mb-1">
          <span className={clsx("text-sm font-semibold", accent)}>{f.finding_type}</span>
          <PhasePill phase={phase} />
          {isGemini && (
            <span className="text-[9px] px-1.5 py-0.5 rounded-full bg-violet-500/18 text-violet-300 border border-violet-500/25 font-mono leading-none">AI-VISION</span>
          )}
        </div>
        {/* Summary */}
        <p className="text-slate-400 text-xs leading-relaxed">
          {isLong && !expanded ? summary.slice(0, LIMIT) + "…" : summary}
        </p>
        {isLong && (
          <button
            onClick={() => setExpanded(v => !v)}
            className="mt-1 flex items-center gap-1 text-[11px] text-slate-600 hover:text-slate-300 transition-colors cursor-pointer"
          >
            {expanded
              ? <><ChevronUp className="w-3 h-3" />Show less</>
              : <><ChevronDown className="w-3 h-3" />Show more</>}
          </button>
        )}
      </div>
      {/* Confidence badge */}
      <div className={clsx(
        "shrink-0 self-start text-xs font-bold px-2 py-1 rounded-lg border",
        confBadge(conf)
      )}>
        {confPct}%
      </div>
    </div>
  );
}

// ─────────────────────────────────────────────────────────────
// AGENT SECTION (collapsible)
// ─────────────────────────────────────────────────────────────

function AgentSection({ agentId, findings, metrics, narrative }: {
  agentId: string;
  findings: AgentFindingDTO[];
  metrics?: AgentMetricsDTO;
  narrative?: string;
}) {
  const [open, setOpen] = useState(true);
  const [showRaw, setShowRaw] = useState(!narrative); // show raw by default when no Groq narrative
  const cfg = AGENT_CFG[agentId];
  if (!cfg || findings.length === 0) return null;

  const initialFindings = findings.filter(f => (f.metadata?.analysis_phase ?? "initial") === "initial");
  const deepFindings    = findings.filter(f => f.metadata?.analysis_phase === "deep");
  const confScore  = metrics?.confidence_score ?? 0;
  const errRate    = metrics?.error_rate ?? 0;
  const toolsOk    = metrics?.tools_succeeded ?? 0;
  const toolsTotal = metrics?.total_tools_called ?? 0;

  // Deduplicate findings by finding_id to prevent UI duplication
  const seen = new Set<string>();
  const dedupedFindings = findings.filter(f => {
    const key = f.finding_id || `${f.finding_type}-${f.confidence_raw}`;
    if (seen.has(key)) return false;
    seen.add(key);
    return true;
  });

  return (
    <div className={clsx("rounded-2xl border overflow-hidden", cfg.border)}>
      {/* Header */}
      <button
        onClick={() => setOpen(v => !v)}
        className={clsx(
          "w-full flex items-center justify-between px-5 py-4 transition-colors cursor-pointer",
          cfg.headerBg, "hover:brightness-110"
        )}
      >
        <div className="flex items-center gap-3">
          <span className={clsx("p-2 rounded-lg bg-black/20", cfg.accent)}>{cfg.icon}</span>
          <div className="text-left">
            <p className={clsx("font-bold text-sm", cfg.accent)}>{cfg.name}</p>
            <p className="text-slate-500 text-xs">{cfg.role}</p>
          </div>
        </div>
        <div className="flex items-center gap-3 text-xs">
          {deepFindings.length > 0 && (
            <span className="hidden sm:inline text-purple-400 font-mono">
              {initialFindings.length}i + {deepFindings.length}d
            </span>
          )}
          {!deepFindings.length && (
            <span className="text-slate-500 hidden sm:inline">
              {initialFindings.length} finding{initialFindings.length !== 1 ? "s" : ""}
            </span>
          )}
          {toolsTotal > 0 && (
            <span className={clsx("hidden sm:inline font-mono",
              errRate === 0 ? "text-emerald-400" : errRate < 0.3 ? "text-amber-400" : "text-red-400"
            )}>
              {toolsOk}/{toolsTotal} ✓
            </span>
          )}
          <span className={clsx("font-bold", confColor(confScore))}>{Math.round(confScore * 100)}%</span>
          <motion.div animate={{ rotate: open ? 180 : 0 }} transition={{ duration: 0.2 }}>
            <ChevronDown className="w-4 h-4 text-slate-500" />
          </motion.div>
        </div>
      </button>

      <AnimatePresence initial={false}>
        {open && (
          <motion.div
            initial={{ height: 0, opacity: 0 }}
            animate={{ height: "auto", opacity: 1 }}
            exit={{ height: 0, opacity: 0 }}
            transition={{ duration: 0.25 }}
            className="overflow-hidden"
          >
            <div className="px-5 pb-5 space-y-4">

              {/* Metrics row */}
              <div className="flex flex-wrap gap-3 pt-3 text-xs border-t border-white/[0.05]">
                <span className={clsx("px-2.5 py-1 rounded-full font-mono border border-white/5",
                  confScore >= 0.75 ? "bg-emerald-500/10 text-emerald-300" :
                  confScore >= 0.5 ? "bg-amber-500/10 text-amber-300" :
                  "bg-red-500/10 text-red-300"
                )}>Confidence: {Math.round(confScore * 100)}%</span>
                <span className={clsx("px-2.5 py-1 rounded-full font-mono border border-white/5",
                  errRate === 0 ? "bg-emerald-500/10 text-emerald-300" :
                  errRate < 0.3 ? "bg-amber-500/10 text-amber-300" :
                  "bg-red-500/10 text-red-300"
                )}>Error rate: {Math.round(errRate * 100)}%</span>
                {toolsTotal > 0 && (
                  <span className="px-2.5 py-1 rounded-full bg-white/[0.04] text-slate-400 font-mono border border-white/5">
                    {toolsOk}/{toolsTotal} tools succeeded
                  </span>
                )}
              </div>

              {/* Groq narrative — primary display */}
              {narrative ? (
                <div className="rounded-xl bg-white/[0.025] border border-white/[0.06] p-4">
                  <p className="text-[10px] text-slate-500 font-mono uppercase tracking-widest mb-2 flex items-center gap-1.5">
                    <span className="text-violet-400">✦</span> Arbiter Analysis
                    {deepFindings.length > 0 && (
                      <span className="ml-2 text-purple-400 normal-case tracking-normal">— initial + deep comparison</span>
                    )}
                  </p>
                  <p className="text-slate-300 text-sm leading-relaxed whitespace-pre-wrap">{narrative}</p>
                </div>
              ) : null}

              {/* Toggle raw findings */}
              <button
                onClick={() => setShowRaw(v => !v)}
                className="flex items-center gap-1.5 text-xs text-slate-500 hover:text-slate-300 transition-colors cursor-pointer"
              >
                <motion.div animate={{ rotate: showRaw ? 180 : 0 }} transition={{ duration: 0.15 }}>
                  <ChevronDown className="w-3.5 h-3.5" />
                </motion.div>
                {showRaw ? "Hide" : "Show"} raw tool findings ({dedupedFindings.length})
              </button>

              {/* Raw findings — collapsed by default when narrative present */}
              <AnimatePresence initial={false}>
                {showRaw && (
                  <motion.div
                    initial={{ height: 0, opacity: 0 }}
                    animate={{ height: "auto", opacity: 1 }}
                    exit={{ height: 0, opacity: 0 }}
                    transition={{ duration: 0.2 }}
                    className="overflow-hidden"
                  >
                    {/* Initial findings */}
                    {initialFindings.length > 0 && (
                      <div className="mb-3">
                        {deepFindings.length > 0 && (
                          <p className="text-[10px] text-slate-600 font-mono uppercase tracking-widest mb-1 px-0.5">
                            Initial Analysis
                          </p>
                        )}
                        {initialFindings.map((f, i) => (
                          <FindingCard key={f.finding_id || `init-${i}`} f={f} accent={cfg.accent} />
                        ))}
                      </div>
                    )}
                    {/* Deep findings */}
                    {deepFindings.length > 0 && (
                      <div>
                        <p className="text-[10px] text-purple-500 font-mono uppercase tracking-widest mb-1 px-0.5">
                          Deep Analysis
                        </p>
                        {deepFindings.map((f, i) => (
                          <FindingCard key={f.finding_id || `deep-${i}`} f={f} accent={cfg.accent} />
                        ))}
                      </div>
                    )}
                  </motion.div>
                )}
              </AnimatePresence>

            </div>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
}

// ─────────────────────────────────────────────────────────────
// VERDICT BANNER
// ─────────────────────────────────────────────────────────────

function VerdictBanner({ report }: { report: ReportDTO }) {
  // Use precomputed values from the arbiter — do not recompute on frontend
  const avg   = report.overall_confidence ?? 0;
  const errR  = report.overall_error_rate ?? 0;
  const v     = report.overall_verdict ?? "REVIEW REQUIRED";
  const contested    = report.contested_findings?.length ?? 0;
  const totalFindings = Object.values(report.per_agent_findings).flat().length;

  type VColor = "emerald" | "amber" | "red";
  let label: string, color: VColor, subtitle: string;

  if (v === "CERTAIN") {
    label = "CERTAIN — AUTHENTIC"; color = "emerald";
    subtitle = `${Math.round(avg * 100)}% confidence, ${(errR * 100).toFixed(0)}% tool error rate. All forensic dimensions consistent. No manipulation signals detected.`;
  } else if (v === "LIKELY") {
    label = "LIKELY AUTHENTIC"; color = "emerald";
    subtitle = `${Math.round(avg * 100)}% confidence, ${(errR * 100).toFixed(0)}% tool error rate. Evidence appears authentic with minor uncertainties.`;
  } else if (v === "MANIPULATION DETECTED") {
    label = "MANIPULATION DETECTED"; color = "red";
    subtitle = `${Math.round(avg * 100)}% confidence. Multiple independent forensic signals indicate evidence tampering or manipulation.`;
  } else if (v === "INCONCLUSIVE") {
    label = "INCONCLUSIVE"; color = "red";
    subtitle = `${Math.round(avg * 100)}% confidence, ${(errR * 100).toFixed(0)}% tool error rate. Insufficient data for a reliable verdict.`;
  } else {
    // UNCERTAIN or REVIEW REQUIRED
    label = v === "UNCERTAIN" ? "UNCERTAIN" : "REVIEW REQUIRED"; color = "amber";
    subtitle = `${Math.round(avg * 100)}% confidence, ${(errR * 100).toFixed(0)}% error rate.${contested > 0 ? ` ${contested} contested finding${contested > 1 ? "s" : ""} require human review.` : " Findings require human review before use in proceedings."}`;
  }

  const cls = {
    emerald: { wrap: "bg-emerald-950/35 border-emerald-500/35", iconWrap: "bg-emerald-500/15", icon: "text-emerald-400", text: "text-emerald-400", badge: "bg-emerald-500/12 text-emerald-300" },
    amber:   { wrap: "bg-amber-950/35 border-amber-500/35",     iconWrap: "bg-amber-500/15",   icon: "text-amber-400",   text: "text-amber-400",   badge: "bg-amber-500/12 text-amber-300"   },
    red:     { wrap: "bg-red-950/35 border-red-500/35",         iconWrap: "bg-red-500/15",     icon: "text-red-400",     text: "text-red-400",     badge: "bg-red-500/12 text-red-300"       },
  }[color];

  const Icon = color === "emerald" ? CheckCircle : AlertTriangle;

  return (
    <motion.div
      initial={{ opacity: 0, y: -8 }}
      animate={{ opacity: 1, y: 0 }}
      className={clsx("relative overflow-hidden rounded-2xl border p-6 flex items-center gap-5", cls.wrap)}
    >
      <div className="absolute inset-x-0 top-0 h-px bg-gradient-to-r from-transparent via-white/15 to-transparent" />
      <motion.div
        initial={{ x: "-100%" }} animate={{ x: "220%", opacity: [0.5, 0] }}
        transition={{ duration: 1.5, ease: "easeOut", delay: 0.15 }}
        className="absolute inset-y-0 w-1/3 bg-gradient-to-r from-transparent via-white/5 to-transparent pointer-events-none"
      />
      <div className={clsx("p-3.5 rounded-xl shrink-0", cls.iconWrap, cls.icon)}>
        <Icon className="w-7 h-7" />
      </div>
      <div className="flex-1 min-w-0">
        <h1 className={clsx("text-2xl sm:text-3xl font-black tracking-tight", cls.text)}>{label}</h1>
        <p className="text-slate-400 text-sm mt-1">{subtitle}</p>
      </div>
      <div className="hidden sm:flex flex-col items-end gap-1.5 shrink-0">
        <span className={clsx("text-xs px-2.5 py-1 rounded-full font-mono border border-white/5", cls.badge)}>
          {Math.round(avg * 100)}% avg confidence
        </span>
        <span className="text-xs text-slate-600 font-mono">{totalFindings} total findings</span>
      </div>
    </motion.div>
  );
}

// ─────────────────────────────────────────────────────────────
// STATS STRIP
// ─────────────────────────────────────────────────────────────

function StatsStrip({ report }: { report: ReportDTO }) {
  const allFindings = Object.values(report.per_agent_findings).flat();
  const totalFindings = allFindings.length;
  const activeAgents = Object.values(report.per_agent_metrics ?? {}).filter((m: AgentMetricsDTO) => !m.skipped).length
    || Object.values(report.per_agent_findings).filter(a => a.length > 0).length;
  const contested = report.contested_findings?.length ?? 0;

  const confPct  = Math.round((report.overall_confidence ?? 0) * 100);
  const errorPct = Math.round((report.overall_error_rate ?? 0) * 100);

  const stats = [
    { icon: <Cpu className="w-3.5 h-3.5" />,           label: "Active Agents",   value: activeAgents      },
    { icon: <Layers className="w-3.5 h-3.5" />,         label: "Total Findings",  value: totalFindings     },
    { icon: <CheckCircle className="w-3.5 h-3.5" />,    label: "Confidence",      value: `${confPct}%`     },
    { icon: <AlertCircle className="w-3.5 h-3.5" />,    label: "Tool Error Rate", value: `${errorPct}%`    },
    { icon: <AlertTriangle className="w-3.5 h-3.5" />,  label: "Contested",       value: contested         },
  ];

  return (
    <div className="grid grid-cols-5 gap-2">
      {stats.map((s, i) => (
        <motion.div
          key={s.label}
          initial={{ opacity: 0, y: 6 }} animate={{ opacity: 1, y: 0 }}
          transition={{ delay: i * 0.04 }}
          className="bg-white/[0.025] border border-white/7 rounded-xl p-3 text-center"
        >
          <div className="flex justify-center text-slate-600 mb-1">{s.icon}</div>
          <div className="text-white font-bold text-lg leading-none">{s.value}</div>
          <div className="text-slate-600 text-[10px] mt-0.5">{s.label}</div>
        </motion.div>
      ))}
    </div>
  );
}

// ─────────────────────────────────────────────────────────────
// MAIN PAGE
// ─────────────────────────────────────────────────────────────

type PageState = "arbiter" | "ready" | "error" | "empty";

export default function ResultPage() {
  const router = useRouter();
  const [mounted, setMounted]         = useState(false);
  const [state, setState]             = useState<PageState>("arbiter");
  const [report, setReport]           = useState<ReportDTO | null>(null);
  const [arbiterMsg, setArbiterMsg]   = useState("");
  const [errorMsg, setErrorMsg]       = useState("");
  const [activeTab, setActiveTab]     = useState<"summary" | "agents" | "chain">("summary");

  const { addToHistory } = useForensicData();
  const { playSound }    = useSound();
  const soundRef         = useRef(playSound);
  useEffect(() => { soundRef.current = playSound; }, [playSound]);

  // ── Poll arbiter, then fetch full report ────────────────────
  useEffect(() => {
    const sessionId = sessionStorage.getItem("forensic_session_id");
    if (!sessionId) { setState("empty"); return; }

    let cancelled = false;
    let timer: ReturnType<typeof setTimeout>;
    let attempts = 0;
    const MAX = 90; // 90 × 2 s ≈ 3 min max wait

    async function poll() {
      if (cancelled) return;
      attempts++;
      try {
        const s = await getArbiterStatus(sessionId);
        if (cancelled) return;

        if (s.status === "complete") {
          // Fetch full report body
          try {
            const res = await getReport(sessionId);
            if (cancelled) return;
            if (res.status === "complete" && res.report) {
              setReport(res.report);
              setState("ready");
              addToHistory(mapReportDtoToReport(res.report));
              setTimeout(() => soundRef.current("complete"), 150);
              return;
            }
          } catch (e) {
            dbg.error("getReport failed:", e);
          }
          // report endpoint not ready yet — retry
        } else if (s.status === "error") {
          setErrorMsg(s.message || "Investigation failed");
          setState("error");
          return;
        } else if (s.status === "not_found") {
          // Fallback: try direct getReport (handles restart / cache scenarios)
          try {
            const res = await getReport(sessionId);
            if (cancelled) return;
            if (res.status === "complete" && res.report) {
              setReport(res.report);
              setState("ready");
              addToHistory(mapReportDtoToReport(res.report));
              setTimeout(() => soundRef.current("complete"), 150);
              return;
            }
          } catch { /* not ready */ }
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

  const fileName = useMemo(() =>
    sessionStorage.getItem("forensic_file_name") || report?.case_id || "Evidence File",
  [report]);

  const handleNew  = useCallback(() => { playSound("click"); sessionStorage.removeItem("forensic_session_id"); sessionStorage.removeItem("forensic_file_name"); sessionStorage.removeItem("forensic_case_id"); router.push("/evidence"); }, [playSound, router]);
  const handleHome = useCallback(() => { playSound("click"); router.push("/"); }, [playSound, router]);

  if (!mounted) return null;

  const activeAgents = Object.entries(report?.per_agent_findings ?? {})
    .filter(([, arr]) => arr.length > 0)
    .map(([id]) => id);

  return (
    <div className="min-h-screen bg-[#050505] text-white overflow-x-hidden">

      {/* Background ambience */}
      <div className="fixed inset-0 -z-50 pointer-events-none">
        <div className="absolute inset-0 bg-[#030303]" />
        <div className="absolute top-0 left-1/4 w-[500px] h-[500px] bg-emerald-900/8 rounded-full blur-[110px]" />
        <div className="absolute bottom-0 right-1/4 w-[400px] h-[400px] bg-cyan-900/6 rounded-full blur-[90px]" />
        <div className="absolute inset-0 bg-[linear-gradient(to_right,#ffffff02_1px,transparent_1px),linear-gradient(to_bottom,#ffffff02_1px,transparent_1px)] bg-[size:40px_40px]" />
      </div>

      {/* Arbiter overlay while compiling */}
      {state === "arbiter" && <ArbiterOverlay liveMessage={arbiterMsg} />}

      {/* ── Header ────────────────────────────────────────────── */}
      <header className="w-full border-b border-white/[0.05]">
        <div className="max-w-5xl mx-auto flex items-center justify-between py-4 px-5">
          <button onClick={handleHome} className="flex items-center gap-2.5 group cursor-pointer">
            <div className="w-8 h-8 bg-gradient-to-br from-emerald-400/20 to-cyan-500/10 border border-emerald-500/30 rounded-lg flex items-center justify-center font-bold text-emerald-400 text-xs group-hover:border-emerald-400/50 transition-colors">
              FC
            </div>
            <span className="text-sm font-bold text-white/70 group-hover:text-white transition-colors hidden sm:block">
              Forensic Council
            </span>
          </button>

          <div className="flex items-center gap-2 text-xs font-mono text-slate-600">
            <span className="relative flex h-2 w-2">
              <span className={clsx(
                "animate-ping absolute inline-flex h-full w-full rounded-full opacity-60",
                state === "arbiter" ? "bg-purple-400" : state === "ready" ? "bg-emerald-400" : "bg-red-400"
              )} />
              <span className={clsx(
                "relative inline-flex rounded-full h-2 w-2",
                state === "arbiter" ? "bg-purple-500" : state === "ready" ? "bg-emerald-500" : "bg-red-500"
              )} />
            </span>
            {state === "arbiter" ? "Arbiter deliberating…" : state === "ready" ? "Report ready" : "Analysis failed"}
          </div>
        </div>
      </header>

      {/* ── Main content ──────────────────────────────────────── */}
      <main className="max-w-5xl mx-auto px-5 pt-8 pb-36">
        <AnimatePresence mode="wait">

          {/* ── REPORT READY ────────────────────────────────── */}
          {state === "ready" && report && (
            <motion.div
              key="report"
              initial={{ opacity: 0, y: 12 }}
              animate={{ opacity: 1, y: 0 }}
              className="space-y-5"
            >
              {/* Verdict */}
              <VerdictBanner report={report} />

              {/* Stats */}
              <StatsStrip report={report} />

              {/* Evidence details row */}
              <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
                {[
                  { label: "File Analyzed",  value: fileName,           mono: false },
                  { label: "Case ID",        value: report.case_id,     mono: true  },
                  { label: "Report ID",      value: report.report_id.slice(0, 18) + "…", mono: true  },
                ].map(item => (
                  <div key={item.label} className="bg-white/[0.025] border border-white/7 rounded-xl px-4 py-3">
                    <p className="text-[10px] text-slate-600 font-mono uppercase tracking-widest mb-1">{item.label}</p>
                    <p className={clsx("text-sm text-white truncate", item.mono && "font-mono")}>{item.value}</p>
                  </div>
                ))}
              </div>

              {/* Section tabs */}
              <div className="flex gap-1 p-1 rounded-xl bg-white/[0.03] border border-white/7">
                {(["summary", "agents", "chain"] as const).map(tab => {
                  const labels = { summary: "📋 Summary", agents: "🔬 Agent Analysis", chain: "🔐 Chain & Signature" };
                  return (
                    <button
                      key={tab}
                      onClick={() => { playSound("click"); setActiveTab(tab); }}
                      className={clsx(
                        "flex-1 text-sm py-2.5 rounded-lg font-medium transition-all cursor-pointer select-none",
                        activeTab === tab
                          ? "bg-emerald-500/15 text-emerald-300 border border-emerald-500/20 shadow-[0_0_12px_rgba(16,185,129,0.1)]"
                          : "text-slate-500 hover:text-slate-300 hover:bg-white/[0.04]"
                      )}
                    >
                      {labels[tab]}
                    </button>
                  );
                })}
              </div>

              {/* Tab content */}
              <AnimatePresence mode="wait">

                {/* ── SUMMARY TAB ── */}
                {activeTab === "summary" && (
                  <motion.div key="sum" initial={{ opacity: 0, y: 6 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0 }} className="space-y-5">

                    {/* Executive summary */}
                    <div className="bg-white/[0.02] border border-white/7 rounded-2xl p-6">
                      <h3 className="text-xs font-semibold text-slate-500 uppercase tracking-widest mb-3 flex items-center gap-2">
                        <FileCheck className="w-3.5 h-3.5 text-emerald-400" /> Executive Summary
                      </h3>
                      <p className="text-slate-300 text-sm leading-relaxed">
                        {report.executive_summary || "Summary not generated. Review per-agent findings for details."}
                      </p>
                    </div>

                    {/* Cross-confirmed */}
                    {(report.cross_modal_confirmed?.length ?? 0) > 0 && (
                      <div className="bg-white/[0.02] border border-white/7 rounded-2xl p-6">
                        <h3 className="text-xs font-semibold text-slate-500 uppercase tracking-widest mb-4 flex items-center gap-2">
                          <CheckCircle className="w-3.5 h-3.5 text-emerald-400" /> Cross-Confirmed Findings
                          <span className="normal-case tracking-normal font-normal text-slate-600 ml-1">
                            — {report.cross_modal_confirmed.length} confirmed by multiple agents
                          </span>
                        </h3>
                        <div className="space-y-0">
                          {report.cross_modal_confirmed.map((f, i) => (
                            <div key={i} className="flex items-start gap-3 py-2.5 border-b border-white/[0.04] last:border-0">
                              <CheckCircle className="w-3.5 h-3.5 text-emerald-400 shrink-0 mt-0.5" />
                              <div className="flex-1 min-w-0">
                                <p className="text-sm font-medium text-white">{f.finding_type}</p>
                                <p className="text-xs text-slate-500 mt-0.5 line-clamp-2">{f.reasoning_summary}</p>
                              </div>
                              <span className={clsx("text-xs font-bold shrink-0", confColor(f.calibrated_probability ?? f.confidence_raw ?? 0))}>
                                {Math.round((f.calibrated_probability ?? f.confidence_raw ?? 0) * 100)}%
                              </span>
                            </div>
                          ))}
                        </div>
                      </div>
                    )}

                    {/* Contested */}
                    {(report.contested_findings?.length ?? 0) > 0 && (
                      <div className="bg-amber-950/15 border border-amber-500/20 rounded-2xl p-5">
                        <h3 className="text-xs font-semibold text-amber-400 uppercase tracking-widest mb-2 flex items-center gap-2">
                          <AlertTriangle className="w-3.5 h-3.5" /> Contested Findings
                          <span className="normal-case tracking-normal font-normal text-slate-600 ml-1">
                            — agents disagree on {report.contested_findings.length} point{report.contested_findings.length > 1 ? "s" : ""}
                          </span>
                        </h3>
                        <p className="text-slate-400 text-sm">
                          Contested findings indicate areas where agents reached different conclusions. These require
                          human review or tribunal escalation before use in official proceedings.
                        </p>
                      </div>
                    )}

                    {/* Uncertainty */}
                    {report.uncertainty_statement && (
                      <div className="bg-white/[0.015] border border-white/7 rounded-2xl p-5">
                        <h3 className="text-xs font-semibold text-slate-500 uppercase tracking-widest mb-2 flex items-center gap-2">
                          <AlertCircle className="w-3.5 h-3.5" /> Limitations & Uncertainty
                        </h3>
                        <p className="text-slate-400 text-sm">{report.uncertainty_statement}</p>
                      </div>
                    )}
                  </motion.div>
                )}

                {/* ── AGENTS TAB ── */}
                {activeTab === "agents" && (
                  <motion.div key="agents" initial={{ opacity: 0, y: 6 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0 }} className="space-y-3">
                    {activeAgents.length === 0 ? (
                      <div className="py-16 text-center text-slate-500 text-sm bg-white/[0.02] border border-white/7 rounded-2xl">
                        No agent findings are available for this file type.
                      </div>
                    ) : (
                      activeAgents.map(id => (
                        <AgentSection
                          key={id}
                          agentId={id}
                          findings={report.per_agent_findings[id] ?? []}
                          metrics={report.per_agent_metrics?.[id] as AgentMetricsDTO | undefined}
                          narrative={report.per_agent_analysis?.[id]}
                        />
                      ))
                    )}
                  </motion.div>
                )}

                {/* ── CHAIN TAB ── */}
                {activeTab === "chain" && (
                  <motion.div key="chain" initial={{ opacity: 0, y: 6 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0 }} className="space-y-4">
                    <div className="bg-white/[0.02] border border-white/7 rounded-2xl p-6 space-y-4">
                      <h3 className="text-xs font-semibold text-slate-500 uppercase tracking-widest flex items-center gap-2">
                        <Lock className="w-3.5 h-3.5 text-cyan-400" /> Cryptographic Signature
                      </h3>
                      {report.report_hash && (
                        <div>
                          <p className="text-[10px] text-slate-600 font-mono uppercase mb-1">Report Hash (SHA-256)</p>
                          <p className="text-xs font-mono text-slate-400 break-all bg-black/30 rounded-xl p-3 leading-relaxed">{report.report_hash}</p>
                        </div>
                      )}
                      {report.cryptographic_signature && (
                        <div>
                          <p className="text-[10px] text-slate-600 font-mono uppercase mb-1">Arbiter Signature</p>
                          <p className="text-xs font-mono text-slate-500 break-all bg-black/30 rounded-xl p-3 leading-relaxed">{report.cryptographic_signature}</p>
                        </div>
                      )}
                      {report.signed_utc && (
                        <div className="flex items-center gap-2 text-xs text-slate-600">
                          <Clock className="w-3.5 h-3.5" />
                          <span className="font-mono">Signed: {report.signed_utc}</span>
                        </div>
                      )}
                      {!report.report_hash && !report.cryptographic_signature && (
                        <p className="text-slate-500 text-sm">No cryptographic signature was generated for this report.</p>
                      )}
                    </div>

                    <div className="bg-white/[0.02] border border-white/7 rounded-2xl p-6">
                      <h3 className="text-xs font-semibold text-slate-500 uppercase tracking-widest mb-3 flex items-center gap-2">
                        <Shield className="w-3.5 h-3.5 text-emerald-400" /> Chain of Custody
                      </h3>
                      <div className="space-y-2 text-sm text-slate-400">
                        <div className="flex items-start gap-2">
                          <Hash className="w-3.5 h-3.5 shrink-0 mt-0.5 text-slate-600" />
                          <span>Report ID: <span className="font-mono text-slate-300">{report.report_id}</span></span>
                        </div>
                        <div className="flex items-start gap-2">
                          <Hash className="w-3.5 h-3.5 shrink-0 mt-0.5 text-slate-600" />
                          <span>Session ID: <span className="font-mono text-slate-300 text-xs">{report.session_id}</span></span>
                        </div>
                        <div className="flex items-start gap-2">
                          <FileText className="w-3.5 h-3.5 shrink-0 mt-0.5 text-slate-600" />
                          <span>Case: <span className="font-mono text-slate-300">{report.case_id}</span></span>
                        </div>
                        <p className="text-slate-600 text-xs mt-3 pt-3 border-t border-white/5">
                          The cryptographic signature guarantees this report has not been altered since generation
                          by the Council Arbiter. All evidence and analysis data is preserved in the chain of custody log.
                        </p>
                      </div>
                    </div>
                  </motion.div>
                )}
              </AnimatePresence>
            </motion.div>
          )}

          {/* ── ERROR STATE ─────────────────────────────────── */}
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
              <button onClick={handleNew}
                className="px-6 py-3 rounded-xl bg-emerald-500/15 border border-emerald-500/30 text-emerald-300 hover:bg-emerald-500/25 transition-all font-semibold text-sm">
                Start New Analysis
              </button>
            </motion.div>
          )}

          {/* ── EMPTY STATE ─────────────────────────────────── */}
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
                  No investigation data was found for this session. It may have expired or not been started.
                </p>
              </div>
              <button onClick={handleHome}
                className="px-6 py-3 rounded-xl bg-emerald-500/15 border border-emerald-500/30 text-emerald-300 hover:bg-emerald-500/25 transition-all font-semibold text-sm">
                Back to Home
              </button>
            </motion.div>
          )}

        </AnimatePresence>
      </main>

      {/* ── Fixed bottom bar ──────────────────────────────────── */}
      <div className="fixed bottom-0 inset-x-0 z-40">
        <div className="max-w-5xl mx-auto px-5 pb-5">
          <div className="flex gap-3 p-2.5 rounded-2xl bg-black/85 backdrop-blur-xl border border-white/[0.07] shadow-[0_-8px_40px_rgba(0,0,0,0.7)]">
            <motion.button whileHover={{ scale: 1.02 }} whileTap={{ scale: 0.97 }}
              onClick={handleNew}
              className="flex-1 flex items-center justify-center gap-2 px-4 py-3 rounded-xl bg-white/[0.04] border border-white/8 text-slate-300 font-semibold text-sm hover:bg-white/[0.08] hover:text-white transition-all">
              <RotateCcw className="w-4 h-4" /> New Analysis
            </motion.button>
            <motion.button whileHover={{ scale: 1.02 }} whileTap={{ scale: 0.97 }}
              onClick={handleHome}
              className="flex-1 flex items-center justify-center gap-2 px-4 py-3 rounded-xl bg-gradient-to-r from-emerald-500 to-cyan-500 text-white font-bold text-sm hover:from-emerald-400 hover:to-cyan-400 transition-all shadow-[0_4px_20px_rgba(16,185,129,0.2)] border border-white/10">
              <Home className="w-4 h-4" /> Home
            </motion.button>
          </div>
        </div>
      </div>

    </div>
  );
}
