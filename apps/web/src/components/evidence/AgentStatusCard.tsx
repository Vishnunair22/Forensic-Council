"use client";

import React, { useEffect, useState } from "react";
import { motion, AnimatePresence } from "framer-motion";
import {
  Activity,
  Cpu,
  ScanEye,
  AudioWaveform,
  Boxes,
  Film,
  Database,
  AlertTriangle,
  type LucideIcon,
} from "lucide-react";
import { clsx } from "clsx";
import { fmtTool } from "@/lib/fmtTool";
import {
  getDefaultProgressTotal,
  getLiveProgressDescriptor,
} from "@/lib/tool-progress";
import type { AgentUpdate, FindingPreview } from "./AgentProgressDisplay";

export interface AgentStatusCardProps {
  agentId: string;
  name: string;
  badge: string;
  status: "waiting" | "queued" | "checking" | "running" | "complete" | "error" | "unsupported" | "validating";
  thinking?: string;
  liveUpdate?: {
    status: string;
    thinking: string;
    tools_done?: number;
    tools_total?: number;
    tool_name?: string;
  };
  completedData?: AgentUpdate;
  isFadingOut?: boolean;
  onComplete?: () => void;
  phase?: "initial" | "deep";
  isExpanded?: boolean;
  onToggleExpand?: () => void;
  onAnimationStart?: () => void;
}

const statusConfig = {
  waiting:     { color: "text-white/20",   label: "Standby"   },
  queued:      { color: "text-white/30",   label: "Queued"    },
  checking:    { color: "text-[var(--color-primary)]",    label: "Syncing" },
  running:     { color: "text-[var(--color-primary)]",    label: "Scanning" },
  complete:    { color: "text-[var(--color-primary)]",    label: "Verified"  },
  error:       { color: "text-danger",     label: "Error"     },
  unsupported: { color: "text-white/20",   label: "Skipped"   },
  validating:  { color: "text-[var(--color-primary)]",    label: "Verifying" },
};

const ALERT_VERDICTS = new Set([
  "FLAGGED",
  "SUSPICIOUS",
  "TAMPERED",
  "NEEDS_REVIEW",
  "LIKELY_MANIPULATED",
  "LIKELY_AI_GENERATED",
  "LIKELY_SPOOFED",
  "LIKELY_SYNTHETIC",
]);

function normalizeVerdict(verdict?: string) {
  const value = (verdict || "INCONCLUSIVE").replace(/_/g, " ");
  return value.toLowerCase().split(' ').map(word => word.charAt(0).toUpperCase() + word.slice(1)).join(' ');
}

function isAlertFinding(finding: FindingPreview) {
  return ALERT_VERDICTS.has(finding.verdict ?? "") || ["CRITICAL", "HIGH", "MEDIUM"].includes(finding.severity ?? "");
}

export const AGENT_GRAPHICS: Record<string, { icon: LucideIcon; color: string; bg: string }> = {
  "Agent1": { icon: ScanEye,  color: "text-[#60A5FA]", bg: "bg-[#60A5FA]/10" },
  "Agent2": { icon: AudioWaveform, color: "text-[#38BDF8]", bg: "bg-[#38BDF8]/10" },
  "Agent3": { icon: Boxes,    color: "text-[#818CF8]", bg: "bg-[#818CF8]/10" },
  "Agent4": { icon: Film,     color: "text-[#22D3EE]", bg: "bg-[#22D3EE]/10" },
  "Agent5": { icon: Database, color: "text-[#93C5FD]", bg: "bg-[#93C5FD]/10" },
};

const FALLBACK_PHRASES: Record<string, string[]> = {
  Agent1: [
    "Scanning pixel density distributions...",
    "Analyzing compression artifacts...",
    "Cross-referencing noise signatures...",
    "Validating spectral consistency...",
    "Running ELA differential analysis...",
  ],
  Agent2: [
    "Analyzing vocal prosody features...",
    "Scanning for splice boundaries...",
    "Comparing audio codec fingerprints...",
    "Running ENF frequency analysis...",
    "Detecting AI voice synthesis markers...",
  ],
  Agent3: [
    "Mapping scene object relationships...",
    "Checking lighting consistency...",
    "Validating shadow geometry...",
    "Analyzing depth coherence...",
    "Cross-referencing object metadata...",
  ],
  Agent4: [
    "Analyzing inter-frame motion vectors...",
    "Checking temporal consistency...",
    "Scanning for face-swap artifacts...",
    "Validating rolling shutter signatures...",
    "Running deepfake frequency analysis...",
  ],
  Agent5: [
    "Extracting EXIF metadata fields...",
    "Cross-referencing GPS coordinates...",
    "Analyzing software fingerprints...",
    "Validating timestamp consistency...",
    "Detecting metadata anomalies...",
  ],
};

function FindingRow({ f, i }: { f: FindingPreview; i: number }) {
  const [expanded, setExpanded] = useState(false);
  const isAlert = isAlertFinding(f);
  const text = f.summary || "";
  const isLong = text.length > 260;
  const visible = expanded || !isLong ? text : text.slice(0, 260) + "...";

  return (
    <motion.div
      data-testid={`agent-card-${i}`}
      initial={{ opacity: 0, x: -10 }}
      animate={{ opacity: 1, x: 0 }}
      className={clsx(
        "p-4 rounded-xl border transition-all duration-300",
        isAlert 
          ? "bg-danger/5 border-danger/20 hover:bg-danger/8" 
          : "bg-[#0C111E] border-white/8 hover:bg-[#111830] hover:border-white/12"
      )}
    >
      <div className="flex items-center justify-between gap-3 mb-3">
        <span className="min-w-0 truncate text-[11px] font-mono font-bold text-white/55 uppercase tracking-[0.08em]">
          {fmtTool(f.tool)}
        </span>
        <div className="flex items-center gap-2">
          {f.degraded && (
            <span className="px-1.5 py-0.5 rounded text-[8px] font-mono font-bold bg-amber-500/10 border border-amber-500/30 text-amber-500" title={f.fallback_reason || "Tool degraded"}>
              DEGRADED
            </span>
          )}
          {typeof f.confidence === "number" && (
            <span className={clsx("text-[11px] font-mono font-bold", isAlert ? "text-danger" : "text-success")}>
              {Math.round(f.confidence * 100)}% confidence
            </span>
          )}
        </div>
      </div>
      <p className="text-sm text-white/85 font-medium leading-6 mb-1">
        {visible}
      </p>
      {f.degraded && f.fallback_reason && (
        <p className="text-[11px] text-amber-400/80 font-mono mt-2 leading-relaxed">
          Tool fallback used: {f.fallback_reason}
        </p>
      )}
      {isLong && (
        <button
          onClick={() => setExpanded((e) => !e)}
          className="mt-3 text-[11px] font-mono text-[var(--color-primary)] uppercase tracking-widest"
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
  badge,
  status,
  thinking,
  liveUpdate,
  completedData,
  phase = "initial",
  isExpanded = false,
  onToggleExpand,
  onAnimationStart,
}: AgentStatusCardProps) {
  const sanitizeThinking = (text?: string) => {
    if (!text) return "";
    const s = text
      .replace(/^(Thinking|THOUGHT|ACTION):\s*/i, "")
      .replace(/_/g, " ")
      .trim();
    if (s.length < 12) return "";
    return s.length > 160 ? s.slice(0, 160) + "..." : s;
  };

  const [fallbackPhraseIndex, setFallbackPhraseIndex] = React.useState(0);
  const lastThinkingRef = React.useRef<string>("");
  const thinkingStaleTimerRef = React.useRef<ReturnType<typeof setTimeout> | null>(null);

  React.useEffect(() => {
    if (status !== "running") return;
    const currentThinking = liveUpdate?.thinking || "";
    if (currentThinking !== lastThinkingRef.current) {
      lastThinkingRef.current = currentThinking;
      if (thinkingStaleTimerRef.current) clearTimeout(thinkingStaleTimerRef.current);
    }
    // Cycle fallback phrases every 3.5s
    const phraseInterval = setInterval(() => {
      setFallbackPhraseIndex(prev => (prev + 1) % (FALLBACK_PHRASES[agentId]?.length || 5));
    }, 3500);
    return () => clearInterval(phraseInterval);
  }, [status, liveUpdate?.thinking, agentId]);

  const cfg = statusConfig[status] || statusConfig.running;
  const [stageIndex, setStageIndex] = useState(0);

  const agentGraphic = AGENT_GRAPHICS[agentId] || { icon: Cpu, color: "text-[var(--color-primary)]", bg: "bg-[var(--color-primary)]/10" };
  const Icon = agentGraphic.icon;

  useEffect(() => {
    if (status === "running") {
      const interval = setInterval(() => {
        setStageIndex((prev) => (prev + 1) % 5);
      }, 3000);
      return () => clearInterval(interval);
    }
  }, [status]);


  const findings = React.useMemo(() => {
    const raw = completedData?.findings_preview || [];
    const deduped: FindingPreview[] = [];
    const seen = new Set<string>();
    for (const f of raw) {
      const key = `${f.tool}-${f.summary.slice(0, 100)}`;
      if (!seen.has(key)) {
        deduped.push(f);
        seen.add(key);
      }
    }
    return deduped;
  }, [completedData]);
  const verdictScore = completedData?.verdict_score;
  const agentVerdict = completedData?.agent_verdict;
  const isAgentAlert =
    (typeof verdictScore === "number" && verdictScore > 0.6) ||
    ALERT_VERDICTS.has(agentVerdict || "");
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
      onAnimationStart={() => onAnimationStart?.()}
      className={clsx(
        "relative flex flex-col overflow-hidden transition-all duration-500 min-h-[480px] max-h-[720px] rounded-2xl border border-white/8 bg-[#070A12]",
        (status === "running" || status === "checking") 
          ? "shadow-[0_4px_24px_rgba(0,0,0,0.5),_0_0_0_1px_rgba(59,130,246,0.2),_0_1px_0_rgba(255,255,255,0.04)_inset]"
          : "shadow-[0_4px_24px_rgba(0,0,0,0.5),_0_1px_0_rgba(255,255,255,0.04)_inset]",
        (status === "waiting" || status === "queued") && "opacity-50"
      )}
      data-testid={`agent-card-${agentId}`}
    >
      {/* --- Card Header --- */}
      <div className="p-8 pb-6 border-b border-white/6 rounded-t-2xl bg-[#0C111E] relative z-10">
        <div className="flex items-start justify-between mb-8">
          <div className="flex items-center gap-5">
            {/* Aperture Icon */}
            <div className="relative w-16 h-16 flex items-center justify-center">
              <motion.div
                animate={{ rotate: 360 }}
                transition={{ duration: 15, repeat: Infinity, ease: "linear" }}
                className="absolute inset-0 rounded-full border border-[var(--color-primary)]/20 border-dashed"
              />
              <Icon className={clsx("w-7 h-7 relative z-10", agentGraphic.color)} />
            </div>

            <div>
              <div className="flex items-center gap-2 mb-1">
                <h3 className="text-xl font-heading font-bold text-white tracking-tight">{name}</h3>
                {completedData?.degraded && (
                  <motion.div
                    initial={{ scale: 0 }}
                    animate={{ scale: 1 }}
                    className="flex items-center gap-1.5 px-2 py-0.5 rounded bg-amber-500/10 border border-amber-500/30"
                    title={completedData.fallback_reason || "Analysis degraded"}
                  >
                    <AlertTriangle className="w-3 h-3 text-amber-500" />
                    <span className="text-[8px] font-mono font-bold text-amber-500 uppercase tracking-widest">
                      Degraded_Mode
                    </span>
                  </motion.div>
                )}
              </div>
              <div className="flex items-center gap-2">
                <span className={clsx(
                  "px-3 py-0.5 rounded text-[10px] font-mono font-bold border",
                  (status === "complete" || status === "checking" || status === "running") ? "bg-[var(--color-primary)]/10 border-[var(--color-primary)]/30 text-[var(--color-primary)]" :
                  status === "error" ? "bg-danger/10 border-danger/30 text-danger" :
                  "bg-white/5 border-white/10 text-white/40"
                )}>
                  {cfg.label.toUpperCase()}
                </span>
                <span className="text-[9px] font-mono text-white/30 tracking-widest uppercase">
                  {badge || `NODE_${agentId}`}
                </span>
              </div>
            </div>
          </div>
        </div>


        {/* --- Progress Section --- */}
        <AnimatePresence mode="wait">
          {(status === "running" || status === "checking") && (
            <motion.div
              initial={{ opacity: 0, y: 10 }}
              animate={{ opacity: 1, y: 0 }}
              exit={{ opacity: 0, y: -10 }}
              className="space-y-4"
            >
              <div className="flex items-center gap-3 text-white/60">
                <motion.div key={progressDescriptor.label} initial={{ opacity: 0, scale: 0.8 }} animate={{ opacity: 1, scale: 1 }}>
                  {status === "checking" ? (
                    <Activity className="w-4 h-4 text-[var(--color-primary)] animate-pulse" />
                  ) : (
                    <ProgressIcon className="w-4 h-4 text-[var(--color-primary)]" />
                  )}
                </motion.div>
                <span className="text-[10px] font-mono font-bold tracking-[0.1em] truncate">
                  {status === "checking"
                    ? (phase === "deep" ? "Re-arming for deep analysis..." : "Synchronizing with pipeline...")
                    : (Math.max(liveTotal, currentToolIndex, 1) > 1 
                        ? `${progressDescriptor.label} ${currentToolIndex}/${Math.max(liveTotal, currentToolIndex, 1)}`
                        : progressDescriptor.label
                      )}
                </span>
              </div>
              <div className="relative w-full h-[2px] bg-white/5 rounded-full overflow-hidden">
                <motion.div
                  className="absolute top-0 bottom-0 bg-[var(--color-primary)] shadow-[0_0_15px_rgba(var(--color-primary-rgb),0.5)]"
                  animate={{
                    width: status === "checking" ? "60%" : `${(currentToolIndex / liveTotal) * 100}%`,
                    opacity: status === "checking" ? [0.3, 1, 0.3] : 1,
                  }}
                  transition={status === "checking" ? { duration: 1.5, repeat: Infinity } : undefined}
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
                    isAgentAlert ? "text-danger" : agentVerdict === "INCONCLUSIVE" ? "text-warning" : "text-success"
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
                <p className="text-sm text-white/75 leading-6 border-t border-white/5 pt-3">
                  {completedData.summary || completedData.message}
                </p>
              )}
            </motion.div>
          )}
        </AnimatePresence>
      </div>

      {/* --- Findings Surface --- */}
      <div className="flex-1 overflow-y-auto overflow-x-hidden custom-scrollbar scroll-smooth p-8 pt-4 relative z-10">
        <AnimatePresence mode="wait">
          {status === "complete" && findings.length > 0 ? (
            <div className="space-y-4">
              {(isExpanded ? findings : findings.slice(0, 2)).map((f, i) => (
                <FindingRow key={`${f.tool}-${i}`} f={f} i={i} />
              ))}

              {findings.length > 2 && (
                <button
                  onClick={() => onToggleExpand?.()}
                  className="w-full py-3 rounded-lg border border-dashed border-white/10 text-white/30 hover:text-white/60 hover:border-white/20 transition-all text-[10px] font-mono uppercase tracking-widest"
                >
                  {isExpanded ? "Collapse_Logs" : `View_${findings.length - 2}_More_Signals`}
                </button>
              )}
            </div>
          ) : (status === "checking" || status === "validating") ? (
            <div className="flex flex-col items-center justify-center h-full text-center gap-4 py-12">
               <div className="w-12 h-12 rounded-xl bg-[var(--color-primary)]/5 border border-[var(--color-primary)]/20 flex items-center justify-center text-[var(--color-primary)] animate-pulse">
                  <Activity className="w-6 h-6" />
               </div>
              <AnimatePresence mode="wait">
                <motion.p
                  key={sanitizeThinking(liveUpdate?.thinking || thinking) || FALLBACK_PHRASES[agentId]?.[fallbackPhraseIndex] || (status === "validating" ? "Verifying chain of custody..." : "Processing evidence...")}
                  initial={{ opacity: 0, y: 4 }}
                  animate={{ opacity: 1, y: 0 }}
                  exit={{ opacity: 0, y: -4 }}
                  transition={{ duration: 0.35 }}
                  className="max-w-xs text-xs text-white/50 font-medium leading-relaxed"
                >
                  {sanitizeThinking(liveUpdate?.thinking || thinking) || FALLBACK_PHRASES[agentId]?.[fallbackPhraseIndex] || (status === "validating" ? "Verifying chain of custody..." : "Processing evidence...")}
                </motion.p>
              </AnimatePresence>
            </div>


          ) : status === "queued" ? (
            <div className="flex flex-col items-center justify-center h-full text-center gap-4 py-12">
               <div className="w-12 h-12 rounded-xl bg-white/[0.03] border border-white/10 flex items-center justify-center text-white/35">
                  <Activity className="w-6 h-6" />
               </div>
               <p className="max-w-xs text-xs text-white/45 font-medium leading-relaxed">
                 {sanitizeThinking(thinking) || "Investigation is queued. Waiting for an available forensic worker..."}
               </p>
            </div>
          ) : status === "waiting" ? (
            <div className="flex flex-col items-center justify-center h-full text-center py-12">
               <span className="text-xs text-white/35 font-medium tracking-wide">Standing by — payload not yet received</span>
            </div>
          ) : null}
        </AnimatePresence>
      </div>

      {/* Decorative Bezel Highlight */}
      <div className="absolute top-0 left-0 right-0 h-[1px] bg-gradient-to-r from-transparent via-white/10 to-transparent pointer-events-none" />
    </motion.div>
  );
}
