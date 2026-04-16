"use client";

import React, { useRef, useEffect, useState } from "react";
import { motion, AnimatePresence } from "framer-motion";
import { 
  Loader2, 
  ShieldAlert, 
  Ban, 
  Zap, 
  AlertTriangle, 
  ChevronRight,
  Clock,
  LayoutGrid,
  ShieldCheck,
  Search,
  ChevronDown,
  ChevronUp
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
  waiting:     { color: "text-white/20",   bg: "bg-white/[0.02]",    border: "border-white/[0.05]", label: "Queued"    },
  checking:    { color: "text-cyan-400",   bg: "bg-cyan-500/5",      border: "border-cyan-500/20",  label: "Linking"   },
  running:     { color: "text-cyan-400",   bg: "bg-cyan-500/10",     border: "border-cyan-500/30",  label: "Scanning"  },
  complete:    { color: "text-emerald-400",bg: "bg-emerald-500/10",   border: "border-emerald-500/20",label: "Finished"  },
  error:       { color: "text-rose-400",   bg: "bg-rose-500/10",     border: "border-rose-500/20",  label: "Aborted"   },
  unsupported: { color: "text-white/25",   bg: "bg-white/[0.02]",    border: "border-white/[0.04]", label: "Skipped"   },
};

export function AgentStatusCard({
  agentId,
  name,
  badge,
  status,
  thinking,
  completedData,
  isRevealed,
  isFadingOut,
  fileMime,
}: AgentStatusCardProps) {
  const cfg = statusConfig[status];
  const scrollRef = useRef<HTMLDivElement>(null);
  const [showAllFindings, setShowAllFindings] = React.useState(false);
  const [expandedFindings, setExpandedFindings] = React.useState<Set<number>>(new Set());
  
  // Real elapsed time computation
  const [elapsed, setElapsed] = useState(0);
  useEffect(() => {
    if (status === "running") {
      const start = Date.now();
      const interval = setInterval(() => {
        setElapsed(Math.floor((Date.now() - start) / 1000));
      }, 1000);
      return () => clearInterval(interval);
    }
  }, [status]);

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

  const manipulationScore = findings.length > 0 ? Math.round((flaggedCount / findings.length) * 100) : 0;
  
  // Use dynamically calculated elapsed time or placeholder based on state
  const timeTakenDisplay = completedData?.completed_at ? `${elapsed || 5}s` : `${elapsed}s`; 

  const isActive = status === "running" || status === "checking" || status === "waiting";
  const isSkipped = status === "unsupported";

  return (
    <motion.div
      layout
      initial={{ opacity: 0, scale: 0.95 }}
      animate={{
        opacity: isFadingOut ? 0 : isRevealed ? (status === "waiting" ? 0.3 : 1) : 0,
        scale: isFadingOut ? 0.85 : 1,
      }}
      exit={{ opacity: 0, scale: 0.85 }}
      transition={{ duration: 0.6, ease: [0.16, 1, 0.3, 1] }}
      className={clsx(
        "relative flex flex-col rounded-[2.5rem] transition-all duration-700 overflow-hidden w-full",
        isSkipped ? "glass-panel" : "glass-panel",
        status === "running" && "shadow-[0_0_60px_-15px_rgba(34,211,238,0.25)] border-cyan-400/30",
        status === "complete" && flaggedCount > 0 && "border-rose-500/30 shadow-[0_0_50px_-15px_rgba(244,63,94,0.2)]",
      )}
    >
      {/* ── Tier 1: Graphic & Agent Name + Status ───────────────────────── */}
      <div className="flex items-center gap-4 px-6 pt-6 pb-4 border-b border-white/[0.05] bg-black/20">
        <div className={clsx(
          "w-12 h-12 rounded-2xl flex items-center justify-center shrink-0 border transition-all duration-700 relative",
          status === "running"
            ? "bg-cyan-500/20 border-cyan-500/40 shadow-[0_0_20px_rgba(34,211,238,0.3)]"
            : isSkipped
            ? "bg-amber-500/10 border-amber-500/20"
            : "bg-white/[0.08] border-white/10"
        )}>
          <AgentIcon
            agentId={agentId}
            className={clsx("w-6 h-6", status === "running" ? "text-cyan-400" : isSkipped ? "text-amber-400/70" : "text-white/60")}
          />
          {status === "running" && (
            <motion.div
              className="absolute inset-0 rounded-2xl border-2 border-cyan-400/50"
              animate={{ scale: [1, 1.3, 1], opacity: [0.6, 0, 0.6] }}
              transition={{ duration: 2.5, repeat: Infinity }}
            />
          )}
        </div>
        <div className="min-w-0 flex-1">
          <div className="flex items-center justify-between gap-2">
            <h3 className={clsx(
              "text-base font-black uppercase tracking-tight leading-tight whitespace-normal break-words",
              isSkipped ? "text-white/80" : "text-white"
            )}>
              {name}
            </h3>
            {/* Status Pill */}
            <div className={clsx(
              "flex justify-center items-center gap-1.5 px-3 py-1.5 rounded-lg text-[9px] font-black uppercase tracking-widest shrink-0 border",
              status === "running" ? "bg-cyan-500/10 border-cyan-500/30 text-cyan-400" : 
              status === "complete" ? "bg-emerald-500/10 border-emerald-500/30 text-emerald-400" :
              isSkipped ? "bg-amber-500/10 border-amber-500/30 text-amber-400" :
              "bg-white/5 border-white/10 text-white/40"
            )}>
              {status === "running" && <Loader2 className="w-2.5 h-2.5 animate-spin" />}
              {cfg.label}
            </div>
          </div>
          <div className="flex items-center justify-between mt-1">
            <span className="text-[9px] font-black tracking-[0.4em] text-white/40 uppercase block">{badge}</span>
            {!isSkipped && status !== "waiting" && status !== "checking" && (
              <div className="flex items-center gap-1.5 text-white/40 shrink-0">
                 <Clock className="w-3.5 h-3.5" />
                 <span className="text-[10px] font-mono font-bold">{timeTakenDisplay}</span>
              </div>
            )}
          </div>
        </div>
      </div>

      <div className="flex-1 flex flex-col min-h-0 bg-transparent">
        <AnimatePresence mode="wait">
          
          {/* RUNNING STATE */}
          {status === "running" && (
            <motion.div
              key="running"
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
              exit={{ opacity: 0 }}
              className="p-6 flex flex-col gap-4"
            >
              <div className="relative rounded-2xl glass-panel p-5 font-mono text-[11px] leading-relaxed min-h-[140px] overflow-hidden">
                <div className="absolute inset-0 pointer-events-none opacity-[0.03] bg-[linear-gradient(rgba(18,16,16,0)_50%,rgba(0,0,0,0.25)_50%),linear-gradient(90deg,rgba(255,0,0,0.06),rgba(0,255,0,0.02),rgba(0,0,255,0.06))] bg-[length:100%_4px,4px_100%]" />
                <div className="relative z-10 flex flex-col gap-2">
                  <div className="flex items-center gap-2 text-cyan-400/60">
                    <span className="w-1.5 h-1.5 rounded-full bg-cyan-400 animate-pulse" />
                    <span>SYSTEM_SCAN_IN_PROGRESS</span>
                  </div>
                  <div className="text-white/40">{">> "} INITIALIZING NEURAL_LAYER_04</div>
                  <div className="text-cyan-400 mt-2 break-words">
                    {">> "} {thinking || "Calibrating forensic analysis tools..."}
                  </div>
                </div>
              </div>
              <div className="h-1 bg-white/5 rounded-full overflow-hidden">
                <motion.div 
                  className="h-full bg-cyan-400"
                  animate={{ left: ["-100%", "100%"] }}
                  initial={{ left: "-100%", position: "relative", width: "50%" }}
                  transition={{ duration: 1.5, repeat: Infinity, ease: "linear" }}
                />
              </div>
            </motion.div>
          )}

          {/* COMPLETE STATE */}
          {status === "complete" && completedData && (
            <motion.div
              key="complete"
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
              className="flex flex-col flex-1"
            >
              {/* ── Tier 3: Core Metrics Grid ────────────────────────────── */}
              <div className="grid grid-cols-3 border-b border-white/[0.05] bg-black/10">
                {[
                  { label: "Confidence", value: `${Math.round((completedData.confidence || 0) * 100)}%`, icon: ShieldCheck },
                  { label: "Error Rate", value: `${Math.round((completedData.tool_error_rate || 0) * 100)}%`, icon: AlertTriangle },
                  { label: "Tools Run", value: completedData.tools_ran || 0, icon: LayoutGrid },
                ].map((m, i) => (
                  <div key={m.label} className={clsx(
                    "p-4 flex flex-col gap-1 items-center justify-center text-center border-white/[0.05]",
                    i < 2 && "border-r",
                  )}>
                    <div className="flex items-center gap-1.5 text-white/20 mb-1">
                      <m.icon className="w-3 h-3" />
                      <span className="text-[8px] font-black uppercase tracking-widest">{m.label}</span>
                    </div>
                    <span className="text-xl font-black text-white font-heading">{m.value}</span>
                  </div>
                ))}
              </div>

              {/* ── Tier 4: Forensic Signal Feed ────────────────────────── */}
              <div className="flex-1 p-6 space-y-4">
                <div className="space-y-4">
                  {findings.slice(0, 2).map((f, i) => {
                    const Icon = getToolIcon(f.tool);
                    const isAlert = f.verdict === "FLAGGED" || f.severity === "CRITICAL" || f.severity === "HIGH";
                    const isExpanded = expandedFindings.has(i);
                    return (
                      <div key={i} className="flex flex-col gap-2 glass-panel p-4 rounded-2xl bg-white/[0.01]">
                        <div className="flex items-start gap-4">
                          <div className={clsx(
                            "w-10 h-10 rounded-xl flex items-center justify-center shrink-0 border",
                            isAlert ? "bg-rose-500/10 border-rose-500/30 text-rose-400" : "bg-white/5 border-white/10 text-white/40"
                          )}>
                            <Icon className="w-5 h-5" />
                          </div>
                          <div className="flex-1 min-w-0">
                            <div className="flex items-center justify-between mb-1">
                              <span className="text-[11px] font-black uppercase tracking-wider text-white/90 truncate">{fmtTool(f.tool)}</span>
                            </div>
                            <p className={clsx(
                              "text-xs leading-relaxed text-white/60",
                              !isExpanded && "line-clamp-2"
                            )}>
                              {f.summary}
                            </p>
                            {f.summary.length > 80 && (
                              <button 
                                onClick={() => toggleFinding(i)}
                                className="text-[9px] font-black uppercase tracking-widest text-cyan-400/60 hover:text-cyan-400 mt-2 flex items-center gap-1"
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
                    <div className="pt-2">
                       <button 
                        onClick={() => setShowAllFindings(!showAllFindings)}
                        className="w-full py-3 rounded-xl glass-panel hover:border-white/20 transition-all flex items-center justify-center gap-2 text-[10px] font-black uppercase tracking-widest text-white/50 hover:text-white"
                       >
                         {showAllFindings ? "Collapse Signals" : `Show ${findings.length - 2} More Findings`}
                         {showAllFindings ? <ChevronUp className="w-4 h-4" /> : <ChevronDown className="w-4 h-4" />}
                       </button>

                       <AnimatePresence>
                         {showAllFindings && (
                           <motion.div 
                            initial={{ height: 0, opacity: 0 }}
                            animate={{ height: "auto", opacity: 1 }}
                            exit={{ height: 0, opacity: 0 }}
                            className="overflow-hidden"
                           >
                             <div className="space-y-4 pt-4">
                               {findings.slice(2).map((f, i) => {
                                 const fullIdx = i + 2;
                                 const Icon = getToolIcon(f.tool);
                                 const isAlert = f.verdict === "FLAGGED" || f.severity === "CRITICAL" || f.severity === "HIGH";
                                 return (
                                   <div key={fullIdx} className="flex items-start gap-4 glass-panel p-3 rounded-xl bg-white/[0.01]">
                                      <div className={clsx(
                                        "w-8 h-8 rounded-lg flex items-center justify-center shrink-0 border",
                                        isAlert ? "bg-rose-500/10 border-rose-500/20 text-rose-400" : "bg-white/5 border-white/10 text-white/30"
                                      )}>
                                        <Icon className="w-4 h-4" />
                                      </div>
                                      <div className="flex-1">
                                        <div className="flex items-center justify-between mb-0.5">
                                          <span className="text-[10px] font-black uppercase text-white/80">{fmtTool(f.tool)}</span>
                                        </div>
                                        <p className="text-[10px] text-white/50 line-clamp-2">{f.summary}</p>
                                      </div>
                                   </div>
                                 );
                               })}
                             </div>
                           </motion.div>
                         )}
                       </AnimatePresence>
                    </div>
                  )}
                </div>
              </div>
            </motion.div>
          )}

          {isSkipped && (
            <motion.div
              key="skipped"
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
              className="p-8 flex flex-col items-center justify-center text-center gap-4 min-h-[200px]"
            >
              <div className="w-16 h-16 rounded-3xl bg-amber-500/[0.08] border border-amber-500/20 flex items-center justify-center shrink-0 mb-2">
                <Ban className="w-8 h-8 text-amber-400/60" />
              </div>
              <div className="min-w-0 space-y-2 max-w-[80%] mx-auto">
                <p className="text-sm text-white/70 font-medium leading-relaxed font-mono">
                  <span className="text-white font-black uppercase">{name}</span> does not support <span className="text-amber-400 font-black uppercase">{fileMime || "this file type"}</span>.
                </p>
                <p className="text-sm text-white/70 font-medium leading-relaxed font-mono">
                  <span className="text-white font-black uppercase">{name}</span> skipped forensic analysis.
                </p>
              </div>
            </motion.div>
          )}

          {/* ERROR STATE */}
          {status === "error" && (
            <motion.div
              key="error"
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
              className="p-8 flex flex-col justify-center gap-5 flex-1"
            >
              <div className="flex items-center gap-4">
                <div className="w-14 h-14 rounded-2xl bg-rose-500/5 border border-rose-500/20 flex items-center justify-center shrink-0">
                  <ShieldAlert className="w-7 h-7 text-rose-400/50" />
                </div>
                <div className="min-w-0">
                  <p className="text-[13px] font-black text-rose-400/60 uppercase tracking-wider mb-1">Protocol Failure</p>
                  <p className="text-xs text-white/30 font-medium leading-relaxed">
                    {completedData?.error || "Investigation terminated due to neural link instability."}
                  </p>
                </div>
              </div>
            </motion.div>
          )}

        </AnimatePresence>
      </div>
    </motion.div>
  );
}
