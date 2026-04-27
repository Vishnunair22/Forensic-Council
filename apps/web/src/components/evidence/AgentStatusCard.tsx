"use client";

import React, { useEffect, useState } from "react";
import { motion, AnimatePresence } from "framer-motion";
import {
  ShieldAlert,
  Activity,
  Cpu,
  Scan,
  Microscope,
  type LucideIcon,
} from "lucide-react";
import { clsx } from "clsx";
import { fmtTool } from "@/lib/fmtTool";
import {
  getDefaultProgressTotal,
  getLiveProgressDescriptor,
  getAgentPrefix,
} from "@/lib/tool-progress";
import type { AgentUpdate, FindingPreview } from "./AgentProgressDisplay";

export interface AgentStatusCardProps {
  agentId: string;
  name: string;
  badge: string;
  status: "waiting" | "checking" | "running" | "complete" | "error" | "unsupported" | "validating";
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
  phase?: "initial" | "deep";
}

const statusConfig = {
  waiting:     { color: "text-white/20",   label: "Standby"   },
  checking:    { color: "text-[var(--color-success-light)]",    label: "Syncing" },
  running:     { color: "text-[var(--color-success-light)]",    label: "Scanning" },
  complete:    { color: "text-[var(--color-success-light)]",    label: "Verified"  },
  error:       { color: "text-danger",     label: "Error"     },
  unsupported: { color: "text-white/30",   label: "Bypassed"   },
  validating:  { color: "text-[var(--color-success-light)]",    label: "Validating" },
};

const ALERT_VERDICTS = new Set(["FLAGGED", "SUSPICIOUS", "LIKELY_MANIPULATED", "LIKELY_AI_GENERATED", "LIKELY_SPOOFED"]);

function normalizeVerdict(verdict?: string) {
  const value = (verdict || "INCONCLUSIVE").replace(/_/g, " ");
  return value.toLowerCase().split(' ').map(word => word.charAt(0).toUpperCase() + word.slice(1)).join(' ');
}

function isAlertFinding(finding: FindingPreview) {
  return ALERT_VERDICTS.has(finding.verdict ?? "") || ["CRITICAL", "HIGH", "MEDIUM"].includes(finding.severity ?? "");
}

const AGENT_GRAPHICS: Record<string, { icon: LucideIcon; color: string; bg: string }> = {
  "Agent1": { icon: Scan, color: "text-[var(--color-success-light)]", bg: "bg-[var(--color-success-light)]/10" },
  "Agent2": { icon: Activity, color: "text-[var(--color-success-light)]", bg: "bg-[var(--color-success-light)]/10" },
  "Agent3": { icon: Microscope, color: "text-[var(--color-success-light)]", bg: "bg-[var(--color-success-light)]/10" },
  "Agent4": { icon: Cpu, color: "text-[var(--color-success-light)]", bg: "bg-[var(--color-success-light)]/10" },
  "Agent5": { icon: ShieldAlert, color: "text-[var(--color-success-light)]", bg: "bg-[var(--color-success-light)]/10" },
};

function FindingRow({ f, i }: { f: FindingPreview; i: number }) {
  const [expanded, setExpanded] = useState(false);
  const isAlert = isAlertFinding(f);
  const text = f.summary || "";
  const isLong = text.length > 180;
  const visible = expanded || !isLong ? text : text.slice(0, 180) + "…";

  return (
    <motion.div
      data-testid={`agent-card-${i}`}
      initial={{ opacity: 0, x: -10 }}
      animate={{ opacity: 1, x: 0 }}
      className={clsx(
        "p-4 rounded-xl border transition-all duration-300",
        isAlert ? "bg-danger/5 border-danger/20" : "bg-white/[0.02] border-white/5"
      )}
    >
      <div className="flex items-center justify-between mb-2">
        <span className="text-[10px] font-mono font-bold text-white/30">SIG_{i.toString().padStart(2, "0")}</span>
        <span className={clsx("text-[10px] font-mono font-bold", isAlert ? "text-danger" : "text-success")}>
          {Math.round((f.confidence || 0) * 100)}% Match
        </span>
      </div>
      <p className="text-xs text-white/70 font-medium leading-relaxed mb-1">
        <span className="text-white font-bold">{fmtTool(f.tool)}:</span> {visible}
      </p>
      {isLong && (
        <button
          onClick={() => setExpanded((e) => !e)}
          className="mt-2 text-[10px] font-mono text-[var(--color-success-light)] uppercase tracking-widest"
        >
          {expanded ? "Show less" : "Show more"}
        </button>
      )}
    </motion.div>
  );
}

export function AgentStatusCard({
  agentId,
  name,
  status,
  liveUpdate,
  completedData,
  fileMime,
  phase = "initial",
}: AgentStatusCardProps) {
  const fileCategory = fileMime?.startsWith("image/") ? "image"
    : fileMime?.startsWith("audio/") ? "audio"
    : fileMime?.startsWith("video/") ? "video"
    : "this file type";
  const cfg = statusConfig[status] || statusConfig.running;
  const [stageIndex, setStageIndex] = useState(0);
  const [showAllTools, setShowAllTools] = useState(false);

  const agentGraphic = AGENT_GRAPHICS[agentId] || { icon: Cpu, color: "text-[var(--color-success-light)]", bg: "bg-[var(--color-success-light)]/10" };
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
  // Take the max of the backend value and the cycling stageIndex so the display
  // always advances even when the backend sends a stale tools_done (e.g. stuck at 0 or 1).
  const liveDone =
    typeof liveUpdate?.tools_done === "number"
      ? Math.max(liveUpdate.tools_done, stageIndex + 1)
      : stageIndex + 1;
  const currentToolIndex = Math.min(Math.max(1, liveDone), liveTotal);
  const progressDescriptor = getLiveProgressDescriptor(
    agentId,
    liveUpdate?.tool_name,
    currentToolIndex - 1,
  );
  const ProgressIcon = progressDescriptor.icon;
  
  return (
    <motion.div
      layout
      className={clsx(
        "glass-panel relative flex flex-col overflow-hidden min-h-[540px] transition-all duration-500",
        (status === "running" || status === "validating" || status === "checking") && "border-[var(--color-success-light)]/30 shadow-[0_0_30px_rgba(167,255,210,0.1)]",
        status === "waiting" && "opacity-40"
      )}
      data-testid={`agent-card-${agentId}`}
    >
      {/* --- Card Header --- */}
      <div className="p-8 pb-6 border-b border-white/5 relative z-10">
        <div className="flex items-start justify-between mb-8">
          <div className="flex items-center gap-5">
            {/* Aperture Icon */}
            <div className="relative w-16 h-16 flex items-center justify-center">
              <motion.div 
                animate={{ rotate: 360 }}
                transition={{ duration: 15, repeat: Infinity, ease: "linear" }}
                className="absolute inset-0 rounded-full border border-[var(--color-success-light)]/20 border-dashed"
              />
              <Icon className={clsx("w-7 h-7 relative z-10", agentGraphic.color)} />
            </div>

            <div>
              <h3 className="text-xl font-heading font-bold text-white mb-1 tracking-tight">{name}</h3>
              <div className="flex items-center gap-2">
                <span className={clsx(
                  "px-2 py-0.5 rounded text-[9px] font-mono font-bold border",
                  (status === "complete" || status === "validating" || status === "checking" || status === "running") ? "bg-[var(--color-success-light)]/10 border-[var(--color-success-light)]/30 text-[var(--color-success-light)]" :
                  status === "error" ? "bg-danger/10 border-danger/30 text-danger" :
                  "bg-white/5 border-white/10 text-white/40"
                )}>
                  {cfg.label.toUpperCase()}
                </span>
                <span className="text-[9px] font-mono text-white/20 tracking-widest uppercase">
                  NODE_{agentId}
                </span>
              </div>
            </div>
          </div>
        </div>


        {/* --- Progress Section --- */}
        <AnimatePresence mode="wait">
          {(status === "running" || status === "checking" || status === "validating") && (
            <motion.div
              initial={{ opacity: 0, y: 10 }}
              animate={{ opacity: 1, y: 0 }}
              exit={{ opacity: 0, y: -10 }}
              className="space-y-4"
            >
              <div className="flex items-center gap-3 text-white/60">
                {(status === "validating" || status === "checking") ? (
                  <Activity className="w-4 h-4 text-[var(--color-success-light)] animate-pulse" />
                ) : (
                  <ProgressIcon className="w-4 h-4 text-[var(--color-success-light)]" />
                )}
                <span className="text-[10px] font-mono font-bold tracking-[0.1em] truncate">
                  {status === "validating"
                    ? "Validating forensic modules…"
                    : status === "checking"
                    ? (phase === "deep" ? "Re-arming for deep analysis…" : "Synchronizing with pipeline…")
                    : `${progressDescriptor.label} ${currentToolIndex}/${liveTotal}`}
                </span>
              </div>
              <div className="relative w-full h-[2px] bg-white/5 rounded-full overflow-hidden">
                <motion.div
                  className="absolute top-0 bottom-0 bg-[var(--color-success-light)] shadow-[0_0_15px_rgba(167,255,210,0.5)]"
                  animate={{
                    width: (status === "validating" || status === "checking") ? "60%" : `${(currentToolIndex / liveTotal) * 100}%`,
                    opacity: (status === "validating" || status === "checking") ? [0.3, 1, 0.3] : 1,
                  }}
                  transition={(status === "validating" || status === "checking") ? { duration: 1.5, repeat: Infinity } : undefined}
                />
              </div>

            </motion.div>
          )}

          {status === "complete" && completedData && (
            <motion.div
              initial={{ opacity: 0, y: 10 }}
              animate={{ opacity: 1, y: 0 }}
              className="space-y-4"
            >
              <div className="flex items-end justify-between">
                <div>
                  <span className="text-[10px] font-mono font-bold text-white/30 uppercase tracking-widest block mb-1">Final Verdict</span>
                  <span className={clsx(
                    "text-xl font-heading font-bold tracking-tight",
                    (completedData.verdict_score ?? 0) > 0.6 ? "text-danger" : "text-success"
                  )}>
                    {normalizeVerdict(completedData.agent_verdict)}
                  </span>
                </div>
                <div className="text-right">
                  <span className="text-[10px] font-mono font-bold text-white/30 uppercase tracking-widest block mb-1">Confidence</span>
                  <span className="text-xl font-mono font-bold text-white">
                    {Math.round(completedData.confidence * 100)}%
                  </span>
                </div>
              </div>
              {(completedData.summary || completedData.message) && (
                <p className="text-xs text-white/60 leading-relaxed border-t border-white/5 pt-3">
                  {completedData.summary || completedData.message}
                </p>
              )}
            </motion.div>
          )}
        </AnimatePresence>
      </div>

      {/* --- Findings Surface --- */}
      <div className="flex-1 overflow-y-auto custom-scrollbar p-8 pt-4 relative z-10">
        <AnimatePresence mode="wait">
          {status === "complete" && findings.length > 0 ? (
            <div className="space-y-4">
              {(showAllTools ? findings : findings.slice(0, 2)).map((f, i) => (
                <FindingRow key={`${f.tool}-${i}`} f={f} i={i} />
              ))}
              
              {findings.length > 2 && (
                <button
                  onClick={() => setShowAllTools(!showAllTools)}
                  className="w-full py-3 rounded-lg border border-dashed border-white/10 text-white/30 hover:text-white/60 hover:border-white/20 transition-all text-[10px] font-mono uppercase tracking-widest"
                >
                  {showAllTools ? "Collapse_Logs" : `View_${findings.length - 2}_More_Signals`}
                </button>
              )}
            </div>
          ) : status === "checking" ? (
            <div className="flex flex-col items-center justify-center h-full text-center gap-4 py-12">
               <div className="w-12 h-12 rounded-xl bg-[var(--color-success-light)]/5 border border-[var(--color-success-light)]/20 flex items-center justify-center text-[var(--color-success-light)] animate-pulse">
                  <Activity className="w-6 h-6" />
               </div>
            </div>

          ) : status === "waiting" ? (
            <div className="flex flex-col items-center justify-center h-full text-center opacity-20 py-12">
               <span className="text-[10px] font-mono font-bold text-white tracking-[0.3em] uppercase">Awaiting_Payload</span>
            </div>
          ) : status === "unsupported" ? (
            <div className="py-4 space-y-3">
               <p className="text-sm text-white/60 leading-relaxed">
                 {name} does not support {fileCategory} files.
               </p>
               <p className="text-[10px] font-mono text-white/30 uppercase tracking-widest">
                 Agent skipped — initial analysis
               </p>
            </div>
          ) : null}
        </AnimatePresence>
      </div>

      {/* Decorative Bezel Highlight */}
      <div className="absolute top-0 left-0 right-0 h-[1px] bg-gradient-to-r from-transparent via-white/10 to-transparent pointer-events-none" />
    </motion.div>
  );
}
