"use client";

import React, { useRef, useEffect, useState } from "react";
import { motion, AnimatePresence } from "framer-motion";
import { 
  ShieldAlert, 
  Ban, 
  Clock,
  ShieldCheck,
  ChevronDown,
  ChevronUp,
  Activity,
  Cpu,
  Scan,
  Search,
  FileText
} from "lucide-react";
import { clsx } from "clsx";
import { AgentIcon } from "@/components/ui/AgentIcon";
import { fmtTool } from "@/lib/fmtTool";
import { getToolIcon } from "@/lib/tool-icons";
import type { AgentUpdate, FindingPreview } from "./AgentProgressDisplay";

interface AgentStatusCardProps {
  agentId: string;
  name: string;
  badge: string;
  status: "waiting" | "checking" | "running" | "complete" | "error" | "unsupported";
  thinking?: string;
  completedData?: AgentUpdate;
  isRevealed: boolean;
  isFadingOut?: boolean;
  fileMime?: string;
}

const statusConfig = {
  waiting:     { color: "text-white/50",   label: "Waiting"   },
  checking:    { color: "text-cyan-500",   label: "Connecting" },
  running:     { color: "text-cyan-400",   label: "Analyzing" },
  complete:    { color: "text-emerald-500",label: "Complete"  },
  error:       { color: "text-rose-500",   label: "Error"     },
  unsupported: { color: "text-white/50",   label: "Skipped"   },
};

const FORENSIC_STAGES = [
  { id: "init",    label: "Initializing Protocols", icon: Cpu,      color: "text-cyan-500" },
  { id: "scan",    label: "Scanning Evidence",      icon: Scan,     color: "text-emerald-500" },
  { id: "compute", label: "Computing Signals",      icon: Activity, color: "text-blue-500" },
  { id: "validate",label: "Validating Results",     icon: Search,   color: "text-amber-500" },
  { id: "report",  label: "Synthesizing Report",    icon: FileText, color: "text-purple-500" },
];

const ALERT_VERDICTS = new Set(["FLAGGED", "SUSPICIOUS", "LIKELY_MANIPULATED", "LIKELY_AI_GENERATED", "LIKELY_SPOOFED"]);

function normalizeVerdict(verdict?: string) {
  const value = (verdict || "INCONCLUSIVE").replace(/_/g, " ").toUpperCase();
  if (value === "ERROR") return "NEEDS REVIEW";
  if (value === "CLEAN") return "CLEAN";
  return value;
}

function isAlertFinding(finding: FindingPreview) {
  return ALERT_VERDICTS.has(finding.verdict ?? "") || ["CRITICAL", "HIGH", "MEDIUM"].includes(finding.severity ?? "");
}

function cleanFindingSummary(summary?: string) {
  const cleaned = (summary || "No diagnostic summary was returned.")
    .replace(/\bObjectWeapon\b/g, "object/weapon")
    .replace(/\bobjectWeapon\b/g, "object/weapon")
    .replace(/\bEXIF\b/g, "metadata")
    .replace(/\s+/g, " ")
    .trim();
  return cleaned.length > 280 ? `${cleaned.slice(0, 277).trim()}...` : cleaned;
}

export function AgentStatusCard({
  agentId,
  name,
  badge,
  status,
  thinking,
  completedData,
  isRevealed,
  isFadingOut,
  fileMime: _fileMime,
}: AgentStatusCardProps) {
  const cfg = statusConfig[status];
  const scrollRef = useRef<HTMLDivElement>(null);
  const [showAllFindings, setShowAllFindings] = React.useState(false);
  const [expandedFindings, setExpandedFindings] = React.useState<Set<number>>(new Set());
  
  const [elapsed, setElapsed] = useState(0);
  const [startTime] = useState(() => Date.now());
  const agentStartRef = useRef<number | null>(null);
  const [agentElapsed, setAgentElapsed] = useState(0);
  const [stageIndex, setStageIndex] = useState(0);

  // Cycle through forensic stages while running
  useEffect(() => {
    if (status === "running") {
      const stageTimer = setInterval(() => {
        setStageIndex((prev) => (prev + 1) % FORENSIC_STAGES.length);
      }, 3500); // 3.5s per stage
      return () => clearInterval(stageTimer);
    }
  }, [status]);

  useEffect(() => {
    if (status === "running" && !agentStartRef.current) {
      agentStartRef.current = Date.now();
    }
  }, [status]);

  useEffect(() => {
    if (status === "running") {
      const interval = setInterval(() => {
        const from = agentStartRef.current || startTime;
        setAgentElapsed(Math.floor((Date.now() - from) / 1000));
        setElapsed(Math.floor((Date.now() - startTime) / 1000));
      }, 1000);
      return () => clearInterval(interval);
    }
  }, [status, startTime]);

  useEffect(() => {
    if (scrollRef.current && status === "running") {
      scrollRef.current.scrollTop = scrollRef.current.scrollHeight;
    }
  }, [thinking, status]);

  const findings: FindingPreview[] = completedData?.findings_preview || [];
  const flaggedCount = findings.filter(isAlertFinding).length;

  const toggleFinding = (idx: number) => {
    const next = new Set(expandedFindings);
    if (next.has(idx)) next.delete(idx);
    else next.add(idx);
    setExpandedFindings(next);
  };
  
  const timeTakenDisplay = status === "complete" ? `${agentElapsed || elapsed}s` : `${elapsed}s`; 
  const isSkipped = status === "unsupported";

  return (
    <motion.div
      layout
      initial={{ opacity: 0, scale: 0.95 }}
      animate={{
        opacity: isFadingOut ? 0 : isRevealed ? (status === "waiting" ? 0.45 : 1) : 0,
        scale: isFadingOut ? 0.85 : 1,
      }}
      exit={{ opacity: 0, scale: 0.85 }}
      transition={{ duration: 0.6, ease: [0.16, 1, 0.3, 1] }}
      className={clsx(
        "relative flex flex-col premium-glass rounded-xl transition-all duration-500 overflow-hidden w-full min-h-[360px]",
        status === "running" && "border-primary/30 shadow-[0_0_40px_rgba(34,211,238,0.1)] ring-1 ring-primary/10",
        status === "complete" && flaggedCount > 0 && "border-danger/30 shadow-[0_0_40px_rgba(244,63,94,0.1)]",
        isSkipped && "opacity-60 grayscale",
      )}
    >
      {/* ── Header Area ────────────────────────────────────────────────────── */}
      <div className="flex items-center gap-4 px-5 py-4 border-b border-white/5">
        <div className={clsx(
          "w-11 h-11 rounded-lg flex items-center justify-center shrink-0 border transition-all duration-500",
          status === "running" ? "bg-primary/10 border-primary/30 text-primary shadow-[0_0_15px_rgba(34,211,238,0.2)]" : "bg-surface-1 border-border-subtle text-white/40"
        )}>
          <AgentIcon
            agentId={agentId}
            className="w-6 h-6"
          />
        </div>
        <div className="min-w-0 flex-1">
          <div className="flex items-center justify-between gap-2 mb-1">
            <h3 className="text-sm font-black text-white truncate">
              {name}
            </h3>
            <div className="flex items-center gap-1.5 bg-surface-low px-2.5 py-1 rounded-full border border-border-subtle shadow-inner">
              <div className={clsx(
                "w-1.5 h-1.5 rounded-full",
                status === "running" ? "bg-primary animate-pulse" : (status === "complete" ? "bg-primary" : "bg-white/20")
              )} aria-hidden="true" />
              <span className={clsx(
                "text-[10px] font-black tracking-widest uppercase",
                status === "running" ? "text-primary" : (status === "complete" ? "text-primary" : "text-white/40")
              )}>
                {cfg.label}
              </span>
            </div>
          </div>
          <div className="flex items-center justify-between">
            <span className="text-[11px] font-semibold text-white/55 truncate max-w-[180px]">{badge}</span>
            {!isSkipped && status !== "waiting" && status !== "checking" && (
              <div className="flex items-center gap-1.5 text-white/50 shrink-0">
                 <Clock className="w-3 h-3" aria-hidden="true" />
                 <span className="text-[11px] font-mono font-bold">{timeTakenDisplay}</span>
              </div>
            )}
          </div>
        </div>
      </div>

      <div className="flex-1 flex flex-col min-h-0">
        <AnimatePresence mode="wait">
          
          {/* RUNNING STATE */}
          {status === "running" && (
            <motion.div
              key="running"
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
              exit={{ opacity: 0 }}
              className="p-5"
            >
              <div className="relative rounded-lg border border-primary/10 p-4 font-mono text-[10px] leading-relaxed min-h-[132px] overflow-hidden bg-surface-low/50">
                <div className="absolute inset-0 pointer-events-none opacity-[0.05] bg-[linear-gradient(transparent_50%,rgba(34,211,238,0.25)_50%)] bg-[length:100%_4px] animate-scan" />
                
                <div className="relative z-10 space-y-4">
                  <div className="flex items-center justify-between">
                    <div className="flex items-center gap-2">
                       <AnimatePresence mode="wait">
                         <motion.div
                           key={FORENSIC_STAGES[stageIndex].id}
                           initial={{ opacity: 0, scale: 0.8 }}
                           animate={{ opacity: 1, scale: 1 }}
                           exit={{ opacity: 0, scale: 1.2 }}
                           className={clsx("p-1.5 rounded-lg bg-surface-mid border border-border-subtle shadow-md", FORENSIC_STAGES[stageIndex].color)}
                         >
                           {React.createElement(FORENSIC_STAGES[stageIndex].icon, { className: "w-3.5 h-3.5" })}
                         </motion.div>
                       </AnimatePresence>
                       <div className="flex flex-col">
                        <span className="font-black tracking-widest text-[9px] text-white/40 uppercase">Phase 0{stageIndex + 1}</span>
                        <AnimatePresence mode="wait">
                          <motion.span 
                            key={FORENSIC_STAGES[stageIndex].id}
                            initial={{ opacity: 0, x: -5 }}
                            animate={{ opacity: 1, x: 0 }}
                            exit={{ opacity: 0, x: 5 }}
                            className="font-black text-[11px] text-primary uppercase"
                          >
                            {FORENSIC_STAGES[stageIndex].label}
                          </motion.span>
                        </AnimatePresence>
                       </div>
                    </div>
                  </div>

                  <div className="h-px bg-gradient-to-r from-primary/30 to-transparent w-full" />

                  <div 
                    className="text-primary/90 break-words leading-relaxed min-h-[40px] flex flex-col gap-1 font-mono uppercase tracking-tight"
                    aria-live="polite"
                    aria-atomic="false"
                  >
                    <div>
                      {thinking || "Initializing..."}
                      <motion.span
                        animate={{ opacity: [0, 1, 0] }}
                        transition={{ duration: 0.8, repeat: Infinity }}
                        className="inline-block ml-1 w-1.5 h-3 bg-primary align-middle shadow-[0_0_8px_rgba(34,211,238,0.5)]"
                      />
                    </div>
                    <span className="text-primary/30 text-[9px] tracking-widest">[{new Date().toLocaleTimeString([], { hour12: false })}] PROTOCOL &gt;&gt; </span>
                  </div>
                </div>
              </div>
            </motion.div>
          )}

          {/* COMPLETE STATE */}
          {status === "complete" && completedData && (
            <motion.div
              key="complete"
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
              className="flex flex-col flex-1 p-5 space-y-4"
            >
              <div className="space-y-3">
                {findings.slice(0, showAllFindings ? undefined : 2).map((f, i) => {
                  const Icon = getToolIcon(f.tool);
                  const isAlert = isAlertFinding(f);
                  const isExpanded = expandedFindings.has(i);
                  const summary = cleanFindingSummary(f.summary);
                  const keySignal = (f.key_signal || "").trim();
                  return (
                    <div key={`${f.tool}-${i}`} className={clsx(
                        "group/row relative p-3.5 rounded-lg border transition-all duration-300 bg-white/[0.015]",
                        isAlert ? "border-rose-500/20" : "border-white/5"
                    )}>
                      <div className="flex items-start gap-3">
                        <div className={clsx(
                          "w-8 h-8 rounded-lg flex items-center justify-center shrink-0 border transition-colors",
                          isAlert ? "bg-rose-500/10 border-rose-500/20 text-rose-500" : "bg-white/5 border-white/5 text-white/20"
                        )}>
                          <Icon className="w-4 h-4" />
                        </div>
                        <div className="flex-1 min-w-0">
                          <div className="flex items-start justify-between gap-2 mb-1">
                            <span className="text-[11px] font-black text-white/85 leading-tight">{fmtTool(f.tool)}</span>
                            <span className={clsx(
                                "text-[9px] font-black px-1.5 py-0.5 rounded shrink-0",
                                isAlert ? "bg-rose-500/10 text-rose-300" : "bg-emerald-500/10 text-emerald-300"
                            )}>{normalizeVerdict(f.verdict)}</span>
                          </div>
                          <p className={clsx(
                            "text-xs leading-relaxed text-slate-300/90 font-medium",
                            !isExpanded && "line-clamp-3"
                          )}>
                            {summary}
                          </p>
                          {keySignal && (
                            <p className="mt-2 text-[10px] leading-relaxed text-cyan-200/55 font-mono">
                              Signal: {keySignal}
                            </p>
                          )}
                          {summary.length > 120 && (
                            <button 
                              onClick={() => toggleFinding(i)}
                              className="text-[10px] font-black tracking-widest text-cyan-500/60 hover:text-cyan-300 mt-2 flex items-center gap-1 transition-colors"
                            >
                              {isExpanded ? "Show Less" : "Show More"}
                              {isExpanded ? <ChevronUp className="w-2.5 h-2.5" /> : <ChevronDown className="w-2.5 h-2.5" />}
                            </button>
                          )}
                        </div>
                      </div>
                    </div>
                  );
                })}

                {findings.length > 2 && (
                   <button 
                    onClick={() => setShowAllFindings(!showAllFindings)}
                    className="w-full py-2.5 rounded-lg border border-white/5 hover:border-white/10 transition-all text-[10px] font-black tracking-[0.24em] text-white/30 hover:text-white/55 flex items-center justify-center gap-2"
                   >
                     {showAllFindings ? "Show Fewer" : `${findings.length - 2} More Finding${findings.length - 2 !== 1 ? "s" : ""}`}
                     {showAllFindings ? <ChevronUp className="w-3.5 h-3.5" /> : <ChevronDown className="w-3.5 h-3.5" />}
                   </button>
                )}
              </div>
            </motion.div>
          )}

          {isSkipped && (
            <motion.div
              key="skipped"
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
              className="p-6 flex flex-col items-center justify-center text-center gap-5 flex-1"
            >
              <div className="relative">
                <div className="w-14 h-14 rounded-xl border border-white/5 flex items-center justify-center text-white/15">
                  <Ban className="w-6 h-6" />
                </div>
              </div>
              <div className="max-w-[200px]">
                <p className="text-xs font-bold text-white/50 tracking-widest mb-2">Not Applicable</p>
                <p className="text-sm text-white/40 font-medium leading-relaxed">
                  This file type is not supported by this agent.
                </p>
              </div>
            </motion.div>
          )}

          {status === "error" && (
            <motion.div
              key="error"
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
              className="p-6 flex flex-col items-center justify-center text-center gap-5 flex-1"
            >
               <div className="w-14 h-14 rounded-2xl border border-rose-500/10 flex items-center justify-center text-rose-500/40">
                  <ShieldAlert className="w-7 h-7" />
                </div>
                <div className="max-w-[200px]">
                  <p className="text-xs font-bold text-rose-400 tracking-widest mb-1">Analysis Failed</p>
                  <p className="text-sm text-white/40 font-medium leading-relaxed">
                    {completedData?.error || "An error occurred during analysis."}
                  </p>
                </div>
            </motion.div>
          )}

        </AnimatePresence>
      </div>

      {/* ── Footer Metadata ────────────────────────────────────────────────── */}
      <div className="mt-auto p-4 border-t border-white/5">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-4">
            {[
              { label: "Confidence", value: completedData ? `${Math.round((completedData.confidence || 0) * 100)}%` : "—", color: "text-emerald-400" },
              { label: "Findings",   value: completedData ? completedData.findings_count : "—", color: "text-cyan-400" },
              { label: "Module",     value: agentId, color: "text-cyan-400" },
            ].map((m) => (
              <div key={m.label} className="flex flex-col">
                <span className="text-[10px] font-semibold text-white/50 tracking-widest mb-0.5">{m.label}</span>
                <span className={clsx("text-[13px] font-black font-mono tracking-tight", completedData ? m.color : "text-white/20")}>{m.value}</span>
              </div>
            ))}
          </div>

          <div className="flex items-center gap-2">
             <ShieldCheck className="w-4 h-4 text-emerald-500/50" aria-hidden="true" />
             <span className="text-[11px] font-semibold text-white/50 tracking-widest">Verified</span>
          </div>
        </div>
      </div>
    </motion.div>
  );
}
