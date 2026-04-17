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
  const flaggedCount = findings.filter(
    (f) => f.verdict === "FLAGGED" || f.severity === "CRITICAL" || f.severity === "HIGH"
  ).length;

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
        opacity: isFadingOut ? 0 : isRevealed ? (status === "waiting" ? 0.2 : 1) : 0,
        scale: isFadingOut ? 0.85 : 1,
      }}
      exit={{ opacity: 0, scale: 0.85 }}
      transition={{ duration: 0.6, ease: [0.16, 1, 0.3, 1] }}
      className={clsx(
        "relative flex flex-col rounded-[2rem] transition-all duration-500 overflow-hidden w-full border border-white/5",
        status === "running" && "border-cyan-500/20 shadow-[0_0_40px_rgba(6,182,212,0.1)]",
        status === "complete" && flaggedCount > 0 && "border-rose-500/20 shadow-[0_0_40px_rgba(244,63,94,0.1)]",
        isSkipped && "opacity-40 grayscale",
      )}
    >
      {/* ── Header Area ────────────────────────────────────────────────────── */}
      <div className="flex items-center gap-4 px-6 py-5 border-b border-white/5">
        <div className={clsx(
          "w-12 h-12 rounded-2xl flex items-center justify-center shrink-0 border transition-all duration-500",
          status === "running" ? "bg-cyan-500/10 border-cyan-500/30 text-cyan-400" : "bg-white/[0.03] border-white/10 text-white/40"
        )}>
          <AgentIcon
            agentId={agentId}
            className="w-6 h-6"
          />
        </div>
        <div className="min-w-0 flex-1">
          <div className="flex items-center justify-between gap-2 mb-1">
            <h3 className="text-sm font-black tracking-tighter text-white truncate">
              {name}
            </h3>
            <div className="flex items-center gap-1.5 bg-black/40 px-2.5 py-1 rounded-full border border-white/5">
              <div className={clsx(
                "w-1.5 h-1.5 rounded-full",
                status === "running" ? "bg-cyan-400 animate-pulse" : (status === "complete" ? "bg-emerald-400" : "bg-white/20")
              )} aria-hidden="true" />
              <span className={clsx(
                "text-[11px] font-bold tracking-widest",
                cfg.color
              )}>
                {cfg.label}
              </span>
            </div>
          </div>
          <div className="flex items-center justify-between">
            <span className="text-[11px] font-semibold tracking-widest text-white/50 truncate max-w-[140px]">{badge}</span>
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
              className="p-6"
            >
              <div className="relative rounded-2xl border border-cyan-500/10 p-5 font-mono text-[10px] leading-relaxed min-h-[160px] overflow-hidden bg-black/20">
                {/* Tactical Scan Line overlay */}
                <div className="absolute inset-0 pointer-events-none opacity-[0.05] bg-[linear-gradient(transparent_50%,rgba(6,182,212,0.25)_50%),linear-gradient(90deg,transparent,transparent)] bg-[length:100%_4px,4px_100%] animate-scan" />
                
                <div className="relative z-10 space-y-4">
                  <div className="flex items-center justify-between">
                    <div className="flex items-center gap-2">
                       <AnimatePresence mode="wait">
                         <motion.div
                           key={FORENSIC_STAGES[stageIndex].id}
                           initial={{ opacity: 0, scale: 0.8, rotate: -10 }}
                           animate={{ opacity: 1, scale: 1, rotate: 0 }}
                           exit={{ opacity: 0, scale: 1.2, rotate: 10 }}
                           className={clsx("p-1.5 rounded-lg bg-black/40 border border-white/5", FORENSIC_STAGES[stageIndex].color)}
                         >
                           {React.createElement(FORENSIC_STAGES[stageIndex].icon, { className: "w-3.5 h-3.5" })}
                         </motion.div>
                       </AnimatePresence>
                       <div className="flex flex-col">
                        <span className="font-black tracking-[0.2em] text-[11px] text-white/40 capitalize tracking-wide">Stage 0{stageIndex + 1}</span>
                        <AnimatePresence mode="wait">
                          <motion.span 
                            key={FORENSIC_STAGES[stageIndex].id}
                            initial={{ opacity: 0, x: -5 }}
                            animate={{ opacity: 1, x: 0 }}
                            exit={{ opacity: 0, x: 5 }}
                            className="font-bold tracking-widest text-[10px] text-cyan-400"
                          >
                            {FORENSIC_STAGES[stageIndex].label}
                          </motion.span>
                        </AnimatePresence>
                       </div>
                    </div>
                  </div>

                  <div className="h-px bg-gradient-to-r from-cyan-500/20 to-transparent w-full" />

                  <div 
                    className="text-cyan-400/90 break-words leading-relaxed min-h-[40px] flex flex-col gap-1"
                    aria-live="polite"
                    aria-atomic="false"
                  >
                    <div>
                      {thinking || "Establishing forensic baseline..."}
                      <motion.span
                        animate={{ opacity: [0, 1, 0] }}
                        transition={{ duration: 0.8, repeat: Infinity }}
                        className="inline-block ml-1 w-1.5 h-3 bg-cyan-500 align-middle shadow-[0_0_8px_rgba(6,182,212,0.5)]"
                      />
                    </div>
                    <span className="text-cyan-500/40 text-[10px] tracking-widest">[{new Date().toLocaleTimeString([], { hour12: false })}] INF &gt;&gt; </span>
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
              className="flex flex-col flex-1 p-6 space-y-4"
            >
              <div className="space-y-3">
                {findings.slice(0, showAllFindings ? undefined : 2).map((f, i) => {
                  const Icon = getToolIcon(f.tool);
                  const isAlert = f.verdict === "FLAGGED" || f.severity === "CRITICAL" || f.severity === "HIGH";
                  const isExpanded = expandedFindings.has(i);
                  return (
                    <div key={`${f.tool}-${i}`} className={clsx(
                        "group/row relative p-4 rounded-2xl border transition-all duration-300",
                        isAlert ? "border-rose-500/10" : "border-white/5"
                    )}>
                      <div className="flex items-start gap-4">
                        <div className={clsx(
                          "w-9 h-9 rounded-xl flex items-center justify-center shrink-0 border transition-colors",
                          isAlert ? "bg-rose-500/10 border-rose-500/20 text-rose-500" : "bg-white/5 border-white/5 text-white/20"
                        )}>
                          <Icon className="w-4 h-4" />
                        </div>
                        <div className="flex-1 min-w-0">
                          <div className="flex items-center justify-between mb-1">
                            <span className="text-[10px] font-black tracking-tighter text-white/80">{fmtTool(f.tool)}</span>
                            <span className={clsx(
                                "text-[10px] font-black px-1.5 py-0.5 rounded",
                                isAlert ? "bg-rose-500/10 text-rose-500" : "bg-emerald-500/10 text-emerald-500"
                            )}>{f.verdict}</span>
                          </div>
                          <p className={clsx(
                            "text-[11px] leading-relaxed text-slate-400 font-medium",
                            !isExpanded && "line-clamp-2"
                          )}>
                            {f.summary}
                          </p>
                          {f.summary.length > 70 && (
                            <button 
                              onClick={() => toggleFinding(i)}
                              className="text-[10px] font-black tracking-[0.2em] text-cyan-500/40 hover:text-cyan-400 mt-2 flex items-center gap-1 transition-colors"
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
                    className="w-full py-3 rounded-2xl border border-white/5 hover:border-white/10 transition-all text-[10px] font-black tracking-[0.3em] text-white/20 hover:text-white/40 flex items-center justify-center gap-2"
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
              className="p-8 flex flex-col items-center justify-center text-center gap-6 flex-1"
            >
              <div className="relative">
                <div className="w-16 h-16 rounded-3xl border border-white/5 flex items-center justify-center text-white/5">
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
              className="p-8 flex flex-col items-center justify-center text-center gap-5 flex-1"
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
      <div className="mt-auto p-5 border-t border-white/5">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-5">
            {[
              { label: "Confidence", value: completedData ? `${Math.round((completedData.confidence || 0) * 100)}%` : "—", color: "text-emerald-400" },
              { label: "Flags",      value: completedData ? completedData.findings_count : "—", color: "text-rose-400" },
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
