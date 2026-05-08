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
  ChevronDown,
  ChevronUp,
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
  onComplete?: () => void;
  phase?: "initial" | "deep";
  isExpanded?: boolean;
  onToggleExpand?: () => void;
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

const SEVERITY_RANK: Record<string, number> = { CRITICAL: 0, HIGH: 1, MEDIUM: 2, LOW: 3 };

function normalizeVerdict(verdict?: string) {
  const value = (verdict || "INCONCLUSIVE").replace(/_/g, " ");
  return value.toLowerCase().split(' ').map(word => word.charAt(0).toUpperCase() + word.slice(1)).join(' ');
}

function isAlertFinding(finding: FindingPreview) {
  return ALERT_VERDICTS.has(finding.verdict ?? "") || ["CRITICAL", "HIGH", "MEDIUM"].includes(finding.severity ?? "");
}

function rankFinding(f: FindingPreview): number {
  const sv = (f.severity || "").toUpperCase();
  if (sv in SEVERITY_RANK) return SEVERITY_RANK[sv];
  if (isAlertFinding(f)) return 1.5;
  return 4;
}

function extractHeadline(f: FindingPreview): string {
  if (f.key_signal?.trim()) return f.key_signal.trim();
  const summary = (f.summary || "").trim();
  const firstSentence = summary.split(/(?<=\.)\s+/)[0];
  return firstSentence.length <= 180 ? firstSentence : firstSentence.slice(0, 160) + "…";
}

function extractDetail(f: FindingPreview, headline: string): string {
  const summary = (f.summary || "").trim();
  if (!summary || summary === headline) return "";
  if (f.key_signal?.trim() === headline) return summary;
  const after = summary.slice(headline.replace(/…$/, "").length).replace(/^[.\s]+/, "").trim();
  return after;
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

const SEV_DOT: Record<string, string> = {
  CRITICAL: "bg-red-400",
  HIGH:     "bg-danger",
  MEDIUM:   "bg-amber-400",
  LOW:      "bg-white/30",
};

const SEV_LABEL: Record<string, string> = {
  CRITICAL: "text-red-400",
  HIGH:     "text-danger",
  MEDIUM:   "text-amber-400",
  LOW:      "text-white/35",
};

function FindingRow({ f, i }: { f: FindingPreview; i: number }) {
  const [expanded, setExpanded] = useState(false);
  const isAlert = isAlertFinding(f);
  const sev = (f.severity || "").toUpperCase();

  const dotColor = SEV_DOT[sev] ?? (isAlert ? "bg-danger/80" : "bg-white/20");
  const sevLabelColor = SEV_LABEL[sev] ?? (isAlert ? "text-danger/70" : "text-white/40");

  const headline = extractHeadline(f);
  const detail = extractDetail(f, headline);
  const MAX = 200;
  const needsExpand = detail.length > MAX;
  const visibleDetail = needsExpand && !expanded ? detail.slice(0, MAX).trimEnd() + "…" : detail;

  return (
    <motion.div
      data-testid={`agent-finding-${i}`}
      initial={{ opacity: 0, y: 4 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ delay: i * 0.05, duration: 0.25 }}
      className="flex gap-3 py-3.5"
    >
      {/* Severity indicator bar */}
      <div className={clsx(
        "w-[3px] self-stretch rounded-full shrink-0 min-h-[16px]",
        sev === "CRITICAL" ? "bg-red-400/80" :
        sev === "HIGH" ? "bg-danger/70" :
        sev === "MEDIUM" ? "bg-amber-400/60" :
        isAlert ? "bg-danger/50" : "bg-white/12"
      )} />

      <div className="flex-1 min-w-0 space-y-1.5">
        {/* Top row: tool name chip + severity badge + confidence */}
        <div className="flex items-center gap-2 flex-wrap">
          {f.tool && (
            <span className={clsx(
              "inline-flex items-center px-2 py-0.5 rounded text-[10px] font-mono font-bold uppercase tracking-wide",
              isAlert
                ? "bg-danger/10 text-danger/80 border border-danger/20"
                : "bg-white/6 text-white/60 border border-white/10"
            )}>
              {fmtTool(f.tool)}
            </span>
          )}
          {sev && SEV_LABEL[sev] && (
            <span className={clsx("text-[10px] font-mono font-semibold uppercase tracking-wide", sevLabelColor)}>
              {sev}
            </span>
          )}
          {f.degraded && (
            <span className="text-[10px] font-mono text-amber-400/60 uppercase" title={f.fallback_reason || ""}>
              degraded
            </span>
          )}
          {typeof f.confidence === "number" && (
            <span className={clsx(
              "ml-auto text-[11px] font-mono font-bold tabular-nums shrink-0",
              isAlert ? "text-danger/90" : "text-white/50"
            )}>
              {Math.round(f.confidence * 100)}%
            </span>
          )}
        </div>

        {/* Headline — primary finding statement */}
        <p className={clsx(
          "text-[13px] font-medium leading-snug",
          isAlert ? "text-white" : "text-white/85"
        )}>
          {headline}
        </p>

        {/* Detail — supporting evidence */}
        {detail && (
          <div className="space-y-1">
            <p className="text-[12px] text-white/55 leading-relaxed">{visibleDetail}</p>
            {needsExpand && (
              <button
                type="button"
                onClick={() => setExpanded(e => !e)}
                className="inline-flex items-center gap-1 text-[10px] font-mono text-[var(--color-primary)]/60 hover:text-[var(--color-primary)] transition-colors"
              >
                {expanded
                  ? <><ChevronUp className="w-3 h-3" /><span>less</span></>
                  : <><ChevronDown className="w-3 h-3" /><span>more</span></>
                }
              </button>
            )}
          </div>
        )}

        {/* Trailing meta: section label */}
        {f.section && (
          <span className="text-[10px] font-mono text-white/25 uppercase tracking-wide">
            {f.section}
          </span>
        )}
      </div>
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
}: AgentStatusCardProps) {
  const sanitizeThinking = (text?: string) => {
    if (!text) return "";
    const s = text
      .replace(/^(Thinking|THOUGHT|ACTION):\s*/i, "")
      .replace(/_/g, " ")
      .trim();
    if (s.length < 12) return "";
    return s;
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
      const key = f.tool || (f.summary || "").slice(0, 90).toLowerCase().trim();
      if (!seen.has(key)) {
        deduped.push(f);
        seen.add(key);
      }
    }
    // Highest-severity / alert findings first
    return deduped.sort((a, b) => rankFinding(a) - rankFinding(b));
  }, [completedData]);
  const verdictScore = completedData?.verdict_score;
  const agentVerdict = completedData?.agent_verdict;
  const isAgentAlert =
    (typeof verdictScore === "number" && verdictScore > 0.6) ||
    ALERT_VERDICTS.has(agentVerdict || "");
  const toolsRan = completedData?.tools_ran || findings.length || 0;
  const fallbackTotal = getDefaultProgressTotal(agentId);
  const liveTotal = liveUpdate?.tools_total || toolsRan || fallbackTotal;
  // Once the backend has emitted a concrete tool, trust that progress instead
  // of cycling through synthetic stages. This keeps live text from advancing
  // after the agent has already produced findings.
  const hasBackendToolProgress = Boolean(liveUpdate?.tool_name);
  const liveDone =
    typeof liveUpdate?.tools_done === "number"
      ? liveUpdate.tools_done
      : hasBackendToolProgress
        ? 1
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
        "relative flex flex-col overflow-hidden transition-all duration-500 min-h-[480px] max-h-[720px] rounded-2xl border border-white/8 bg-surface-1",
        (status === "running" || status === "checking") 
          ? "shadow-[0_8px_40px_rgba(0,0,0,0.4),_0_0_0_1px_rgba(59,130,246,0.15),_0_1px_0_rgba(255,255,255,0.04)_inset]"
          : "shadow-[0_8px_32px_rgba(0,0,0,0.3),_0_1px_0_rgba(255,255,255,0.03)_inset]",
        (status === "waiting" || status === "queued") && "opacity-50"
      )}
      data-testid={`agent-card-${agentId}`}
    >
      {/* --- Card Header --- */}
      <div className="p-8 pb-6 border-b border-white/5 rounded-t-2xl bg-surface-2 relative z-10">
        <div className="flex items-start justify-between mb-8">
          <div className="flex items-center gap-5">
            {/* Aperture Icon */}
            <div className="relative w-16 h-16 flex items-center justify-center">
              <div className="absolute inset-0 rounded-full border border-[var(--color-primary)]/20 border-dashed [animation:spin_15s_linear_infinite]" />
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
                <p className="text-[12px] text-white/60 leading-relaxed border-t border-white/5 pt-3">
                  {(completedData.summary || completedData.message || "").slice(0, 280)}
                  {(completedData.summary || completedData.message || "").length > 280 ? "…" : ""}
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
            <div>
              <div className="divide-y divide-white/[0.05]">
                {(isExpanded ? findings : findings.slice(0, 3)).map((f, i) => (
                  <FindingRow key={`${f.tool}-${i}`} f={f} i={i} />
                ))}
              </div>

              {findings.length > 3 && (
                <button
                  type="button"
                  onClick={() => onToggleExpand?.()}
                  className={clsx(
                    "mt-4 w-full py-2.5 rounded-lg flex items-center justify-center gap-1.5",
                    "text-[11px] font-mono font-semibold uppercase tracking-wider",
                    "border transition-all duration-200",
                    isExpanded
                      ? "bg-white/[0.04] border-white/10 text-white/40 hover:text-white/60 hover:border-white/20"
                      : "bg-[var(--color-primary)]/6 border-[var(--color-primary)]/20 text-[var(--color-primary)]/70 hover:bg-[var(--color-primary)]/10 hover:border-[var(--color-primary)]/35 hover:text-[var(--color-primary)]"
                  )}
                >
                  {isExpanded
                    ? <><ChevronUp className="w-3.5 h-3.5" /><span>Show less</span></>
                    : <><ChevronDown className="w-3.5 h-3.5" /><span>{findings.length - 3} more {findings.length - 3 === 1 ? "signal" : "signals"}</span></>
                  }
                </button>
              )}
            </div>
          ) : (status === "running" || status === "checking" || status === "validating") ? (
            <div className="flex flex-col items-center justify-center h-full text-center gap-4 py-12">
              <div className="w-12 h-12 rounded-xl bg-[var(--color-primary)]/5 border border-[var(--color-primary)]/20 flex items-center justify-center text-[var(--color-primary)]">
                {status === "running" ? (
                  <ProgressIcon className="w-6 h-6" />
                ) : (
                  <Activity className="w-6 h-6 animate-pulse" />
                )}
              </div>
              <AnimatePresence mode="wait">
                <motion.p
                  key={sanitizeThinking(liveUpdate?.thinking || thinking) || FALLBACK_PHRASES[agentId]?.[fallbackPhraseIndex] || (status === "validating" ? "Verifying chain of custody..." : "Processing evidence...")}
                  initial={{ opacity: 0, y: 4 }}
                  animate={{ opacity: 1, y: 0 }}
                  exit={{ opacity: 0, y: -4 }}
                  transition={{ duration: 0.35 }}
                  className="max-w-[280px] text-xs text-white/55 font-medium leading-relaxed"
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
          ) : status === "unsupported" ? (
            <div className="flex flex-col items-center justify-center h-full text-center gap-3 py-12">
              <div className="w-12 h-12 rounded-xl bg-white/[0.03] border border-white/10 flex items-center justify-center text-white/35">
                <AlertTriangle className="w-6 h-6" />
              </div>
              <p className="max-w-xs text-xs text-white/55 font-medium leading-relaxed">
                {sanitizeThinking(liveUpdate?.thinking || thinking) ||
                  completedData?.message ||
                  "This specialist does not support the submitted file type."}
              </p>
              <span className="text-[10px] font-mono uppercase tracking-widest text-white/25">
                Hidden after 10s
              </span>
            </div>
          ) : null}
        </AnimatePresence>
      </div>

      {/* Decorative Bezel Highlight */}
      <div className="absolute top-0 left-0 right-0 h-[1px] bg-gradient-to-r from-transparent via-white/10 to-transparent pointer-events-none" />
    </motion.div>
  );
}
