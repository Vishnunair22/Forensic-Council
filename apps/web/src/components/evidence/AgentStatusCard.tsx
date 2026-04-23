"use client";

import React, { useEffect, useState } from "react";
import { motion, AnimatePresence } from "framer-motion";
import { 
  ShieldAlert, 
  Ban, 
  Activity,
  Cpu,
  Scan,
  Microscope,
  type LucideIcon
} from "lucide-react";
import { clsx } from "clsx";
import { fmtTool } from "@/lib/fmtTool";
import {
  getDefaultProgressTotal,
  getLiveProgressDescriptor,
} from "@/lib/tool-progress";
import type { AgentUpdate, FindingPreview } from "./AgentProgressDisplay";

interface AgentStatusCardProps {
  agentId: string;
  name: string;
  badge: string;
  status: "waiting" | "checking" | "running" | "complete" | "error" | "unsupported";
  thinking?: string;
  liveUpdate?: {
    status: string;
    thinking: string;
    tools_done?: number;
    tools_total?: number;
    tool_name?: string;
  };
  completedData?: AgentUpdate;
  isRevealed: boolean;
  isFadingOut?: boolean;
  fileMime?: string;
  onComplete?: () => void;
}

const statusConfig = {
  waiting:     { color: "text-white/50",   label: "Waiting"   },
  checking:    { color: "text-cyan-500",   label: "Connecting" },
  running:     { color: "text-cyan-400",   label: "Analyzing" },
  complete:    { color: "text-emerald-500",label: "Complete"  },
  error:       { color: "text-rose-500",   label: "Error"     },
  unsupported: { color: "text-white/50",   label: "Skipped"   },
};

const ALERT_VERDICTS = new Set(["FLAGGED", "SUSPICIOUS", "LIKELY_MANIPULATED", "LIKELY_AI_GENERATED", "LIKELY_SPOOFED"]);

function normalizeVerdict(verdict?: string) {
  const value = (verdict || "INCONCLUSIVE").replace(/_/g, " ");
  // Simple Title Case conversion
  return value.toLowerCase().split(' ').map(word => word.charAt(0).toUpperCase() + word.slice(1)).join(' ');
}

function isAlertFinding(finding: FindingPreview) {
  return ALERT_VERDICTS.has(finding.verdict ?? "") || ["CRITICAL", "HIGH", "MEDIUM"].includes(finding.severity ?? "");
}

const AGENT_GRAPHICS: Record<string, { icon: LucideIcon; color: string; bg: string }> = {
  "Agent1": { icon: Scan, color: "text-cyan-400", bg: "bg-cyan-500/10" },
  "Agent2": { icon: Activity, color: "text-emerald-400", bg: "bg-emerald-500/10" },
  "Agent3": { icon: Microscope, color: "text-purple-400", bg: "bg-purple-500/10" },
  "Agent4": { icon: Cpu, color: "text-amber-400", bg: "bg-amber-500/10" },
  "Agent5": { icon: ShieldAlert, color: "text-rose-400", bg: "bg-rose-500/10" },
};

export function AgentStatusCard({
  agentId,
  name,
  status,
  liveUpdate,
  completedData,
  isRevealed,
  isFadingOut,
}: AgentStatusCardProps) {
  const cfg = statusConfig[status];
  const [stageIndex, setStageIndex] = useState(0);
  const [showAllTools, setShowAllTools] = useState(false);
  const [expandedFindings, setExpandedFindings] = useState<Record<string, boolean>>({});

  const agentGraphic = AGENT_GRAPHICS[agentId] || { icon: Cpu, color: "text-primary", bg: "bg-primary/10" };
  const Icon = agentGraphic.icon;

  useEffect(() => {
    if (status === "running") {
      const interval = setInterval(() => {
        setStageIndex((prev) => (prev + 1) % 5);
      }, 3000);
      return () => clearInterval(interval);
    }
  }, [status]);

  const findings = completedData?.findings_preview || [];
  const toolsRan = completedData?.tools_ran || findings.length || 0;
  const fallbackTotal = getDefaultProgressTotal(agentId);
  const liveTotal = liveUpdate?.tools_total || toolsRan || fallbackTotal;
  const liveDone =
    typeof liveUpdate?.tools_done === "number"
      ? liveUpdate.tools_done
      : stageIndex + 1;
  const currentToolIndex = Math.min(Math.max(1, liveDone), liveTotal);
  const progressDescriptor = getLiveProgressDescriptor(
    agentId,
    liveUpdate?.tool_name,
    currentToolIndex - 1,
  );
  const ProgressIcon = progressDescriptor.icon;
  const isSkipped = status === "unsupported";
  
  const toggleFinding = (id: string) => {
    setExpandedFindings(prev => ({ ...prev, [id]: !prev[id] }));
  };

  return (
    <motion.div
      layout
      initial={{ opacity: 0, y: 20 }}
      animate={{
        opacity: isFadingOut ? 0 : isRevealed ? (status === "waiting" ? 0.3 : 1) : 0,
        y: 0,
        scale: isFadingOut ? 0.95 : 1,
      }}
      className={clsx(
        "frosted-panel relative flex flex-col rounded-[2.5rem] overflow-hidden min-h-[520px] transition-all duration-500",
        status === "running" && "ring-2 ring-primary/40 shadow-[0_0_60px_rgba(34,211,238,0.15)]",
        status === "complete" && (completedData?.verdict_score ?? 0) > 0.5 && "ring-2 ring-rose-500/30 shadow-[0_0_60px_rgba(244,63,94,0.15)]"
      )}
    >
      <div className="absolute inset-0 scan-line-overlay opacity-[0.02]" />
      
      {/* ── Card Header ─────────────────────────────────────────────────── */}
      <div className="p-8 pb-6 border-b border-white/5 relative z-10">
        <div className="flex items-start justify-between mb-6">
          <div className="flex items-center gap-5">
            <div className={clsx(
              "w-16 h-16 rounded-2xl flex items-center justify-center relative overflow-hidden",
              agentGraphic.bg
            )}>
              <div className="absolute inset-0 bg-gradient-to-br from-white/10 to-transparent opacity-50" />
              <Icon className={clsx("w-8 h-8 relative z-10", agentGraphic.color)} />
            </div>
            <div>
              <h3 className="text-xl font-black text-white tracking-tight mb-1">{name}</h3>
              <div className="flex items-center gap-2">
                <span className={clsx(
                  "px-3 py-1 rounded-full text-[9px] font-black tracking-widest",
                  status === "running" ? "bg-primary/20 text-primary animate-pulse" :
                  status === "complete" ? "bg-emerald-500/20 text-emerald-400" :
                  "bg-white/5 text-white/30"
                )}>
                  {cfg.label}
                </span>
                {status === "complete" && completedData?.completed_at && (
                  <span className="text-[10px] font-mono text-white/20">
                    Phase Finalized
                  </span>
                )}
              </div>
            </div>
          </div>
        </div>

        {/* ── Live Progress Section ────────────────────────────────────────── */}
        <AnimatePresence mode="wait">
          {status === "running" && (
            <motion.div
              initial={{ opacity: 0, y: 10 }}
              animate={{ opacity: 1, y: 0 }}
              exit={{ opacity: 0, y: -10 }}
              className="flex items-center gap-4 bg-white/[0.02] border border-white/5 rounded-2xl p-4"
            >
              <div className="w-10 h-10 rounded-xl bg-primary/10 flex items-center justify-center shrink-0">
                <motion.div
                  key={liveUpdate?.tool_name || progressDescriptor.label}
                  initial={{ scale: 0.86, opacity: 0.4 }}
                  animate={{ scale: 1, opacity: 1 }}
                  transition={{ duration: 0.25 }}
                >
                  <ProgressIcon className="w-5 h-5 text-primary" />
                </motion.div>
              </div>
              <div className="flex-1 min-w-0">
                <p className="text-[11px] font-bold text-white/80 truncate">
                  {progressDescriptor.label}
                </p>
                <div className="flex items-center gap-2 mt-1">
                  <div className="flex-1 h-1 bg-white/5 rounded-full overflow-hidden">
                    <motion.div
                      className="h-full bg-primary"
                      animate={{ width: `${(currentToolIndex / liveTotal) * 100}%` }}
                    />
                  </div>
                  <span className="text-[9px] font-black text-primary/60 font-mono shrink-0">
                    {currentToolIndex}/{liveTotal}
                  </span>
                </div>
              </div>
            </motion.div>
          )}

          {status === "complete" && completedData && (
            <motion.div
              initial={{ opacity: 0, y: 10 }}
              animate={{ opacity: 1, y: 0 }}
              className="space-y-4"
            >
              <div className="flex items-end justify-between px-1">
                <div>
                  <span className="text-[10px] font-black text-white/30 tracking-[0.2em] block mb-1">Final Verdict</span>
                  <span className={clsx(
                    "text-2xl font-black tracking-tight",
                    (completedData.verdict_score ?? 0) > 0.6 ? "text-rose-500" : "text-emerald-400"
                  )}>
                    {normalizeVerdict(completedData.agent_verdict)}
                  </span>
                </div>
                <div className="text-right">
                  <span className="text-[10px] font-black text-white/30 tracking-[0.2em] block mb-1">Confidence</span>
                  <span className="text-2xl font-black text-white font-mono">
                    {Math.round(completedData.confidence * 100)}%
                  </span>
                </div>
              </div>
              
              <div className="p-4 rounded-2xl bg-white/[0.02] border border-white/5">
                <p className="text-xs leading-relaxed text-white/60 font-medium">
                  <span className="text-white font-bold">{name}</span> completed{" "}
                  <span className="text-primary font-bold">{toolsRan || completedData.findings_count} checks</span>{" "}
                  with <span className="text-white font-bold">{Math.round(completedData.confidence * 100)}%</span>{" "}
                  confidence. Tool error rate was{" "}
                  <span className="text-rose-400 font-bold">{Math.round((completedData.tool_error_rate || 0) * 100)}%</span>;
                  the agent&apos;s manipulation signal is{" "}
                  <span className={clsx("font-bold", (completedData.verdict_score ?? 0) > 0.5 ? "text-rose-500" : "text-emerald-400")}>
                    {Math.round((completedData.verdict_score || 0) * 100)}%
                  </span>.
                </p>
              </div>
            </motion.div>
          )}
        </AnimatePresence>
      </div>

      {/* ── Findings List ────────────────────────────────────────────────── */}
      <div className="flex-1 overflow-y-auto custom-scrollbar p-8 pt-4 relative z-10">
        <AnimatePresence mode="wait">
          {status === "complete" && findings.length > 0 ? (
            <div className="space-y-4">
              {(showAllTools ? findings : findings.slice(0, 2)).map((f, i) => {
                const isAlert = isAlertFinding(f);
                const isExpanded = expandedFindings[`${f.tool}-${i}`];
                return (
                  <motion.div
                    key={`${f.tool}-${i}`}
                    initial={{ opacity: 0, x: -10 }}
                    animate={{ opacity: 1, x: 0 }}
                    transition={{ delay: i * 0.1 }}
                    className={clsx(
                      "group/finding rounded-2xl border transition-all duration-300",
                      isAlert ? "bg-rose-500/[0.03] border-rose-500/10 hover:border-rose-500/30" : "bg-white/[0.01] border-white/5 hover:border-white/10"
                    )}
                  >
                    <div className="p-4 flex items-start gap-4">
                      <div className={clsx(
                        "w-10 h-10 rounded-xl flex items-center justify-center shrink-0",
                        isAlert ? "bg-rose-500/10 text-rose-500" : "bg-white/5 text-white/40"
                      )}>
                        <Scan className="w-5 h-5" />
                      </div>
                      <div className="flex-1 min-w-0">
                        <div className="flex items-center justify-between gap-2 mb-1">
                          <span className="text-[11px] font-black text-white/90 tracking-tight">
                            {fmtTool(f.tool)}
                          </span>
                          <span className={clsx(
                            "text-[10px] font-black font-mono",
                            isAlert ? "text-rose-400" : "text-emerald-400"
                          )}>
                            {Math.round((f.confidence || 0) * 100)}% Match
                          </span>
                        </div>
                        <p className={clsx(
                          "text-[11px] leading-relaxed text-white/50 font-medium",
                          !isExpanded && "line-clamp-2"
                        )}>
                          {f.summary}
                        </p>
                        {f.summary.length > 100 && (
                          <button
                            onClick={() => toggleFinding(`${f.tool}-${i}`)}
                            className="text-[10px] font-black text-primary/60 hover:text-primary mt-2 transition-colors tracking-widest"
                          >
                            {isExpanded ? "Show Less" : "Show More"}
                          </button>
                        )}
                      </div>
                    </div>
                  </motion.div>
                );
              })}
              
              {findings.length > 2 && (
                <button
                  onClick={() => setShowAllTools(!showAllTools)}
                  className="w-full py-4 rounded-2xl border border-dashed border-white/10 text-white/30 hover:text-white/60 hover:border-white/20 hover:bg-white/[0.01] transition-all text-[10px] font-black tracking-[0.2em]"
                >
                  {showAllTools ? "Collapse Findings" : `Show ${findings.length - 2} More Findings`}
                </button>
              )}
            </div>
          ) : status === "running" ? (
            <div className="flex flex-col items-center justify-center h-full opacity-20 gap-4">
              <div className="relative">
                <div className="absolute inset-0 bg-primary blur-2xl opacity-20 animate-pulse" />
                <Icon className="w-12 h-12 text-primary animate-pulse" />
              </div>
              <span className="text-[10px] font-black tracking-[0.3em]">Analyzing Stream...</span>
            </div>
          ) : isSkipped ? (
            <div className="flex flex-col items-center justify-center h-full text-center p-6 gap-4">
              <div className="w-16 h-16 rounded-full bg-white/5 flex items-center justify-center text-white/20">
                <Ban className="w-8 h-8" />
              </div>
              <div>
                <p className="text-xs font-black text-white/40 tracking-widest mb-1">Agent Bypassed</p>
                <p className="text-[11px] text-white/20 font-medium leading-relaxed">
                  File compatibility mismatch detected. This module was skipped to optimize performance.
                </p>
              </div>
            </div>
          ) : null}
        </AnimatePresence>
      </div>
    </motion.div>
  );
}
