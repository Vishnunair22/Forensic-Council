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
  ListChecks,
  type LucideIcon,
} from "lucide-react";
import { clsx } from "clsx";
import { fmtTool } from "@/lib/fmtTool";
import { cleanFindingText } from "@/lib/findingText";
import {
  getDefaultProgressTotal,
  getLiveProgressDescriptor,
} from "@/lib/tool-progress";
import { accentFor } from "@/lib/agentTheme";
import type { AgentUpdate, FindingPreview } from "./types";

const TEMPLATE_SUMMARY_RE = [
  /^analysis (?:complete|completed|finished)\.?$/i,
  /^tool (?:execution )?(?:complete|completed|finished)(?:\s+successfully)?\.?$/i,
  /^checked:?\s*$/i,
  /^no diagnostic output\.?$/i,
  /^(?:check|scan|run)\s+(?:ok|complete|finished)\.?$/i,
];

function isTemplateSummary(text: string): boolean {
  const t = text.trim();
  if (!t) return true;
  if (t.length < 12) return true;    // reduced from 18 to 12
  return TEMPLATE_SUMMARY_RE.some((re) => re.test(t));
}

function summaryFingerprint(text: string): string {
  return cleanFindingText(text || "")
    .toLowerCase()
    .replace(/\d+(?:\.\d+)?/g, "#")
    .replace(/\s+/g, " ")
    .slice(0, 120)
    .trim();
}

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
  phase?: "initial" | "deep";
  isExpanded?: boolean;
  onToggleExpand?: () => void;
}

const statusConfig = {
  waiting:     { color: "fc-text-faint",   label: "Standby"   },
  queued:      { color: "fc-text-faint",   label: "Queued"    },
  checking:    { color: "text-primary",    label: "Syncing" },
  running:     { color: "text-primary",    label: "Scanning" },
  complete:    { color: "text-primary",    label: "Verified"  },
  error:       { color: "text-danger",     label: "Error"     },
  unsupported: { color: "fc-text-faint",   label: "Skipped"   },
  validating:  { color: "text-primary",    label: "Verifying" },
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

function confidenceTier(c: number): { label: string; colorClass: string } {
  if (c >= 0.8) return { label: "High", colorClass: "text-primary" };
  if (c >= 0.55) return { label: "Med", colorClass: "text-warning" };
  return { label: "Low", colorClass: "fc-text-faint" };
}

function buildUnifiedFindingText(f: FindingPreview): string {
  const signal = cleanFindingText(f.key_signal || "").trim();
  const full = cleanFindingText(f.summary || "").trim();

  if (!signal && !full) {
    if (f.verdict && f.verdict !== "INCONCLUSIVE" && f.verdict !== "CLEAN") {
      return `${normalizeVerdict(f.verdict)} signal detected.`;
    }
    return "";
  }

  if (signal && full) {
    // If the full summary already contains the signal, prefer the full text
    const fp = summaryFingerprint(signal).slice(0, 60);
    if (fp && summaryFingerprint(full).includes(fp)) return full;
    if (summaryFingerprint(signal) === summaryFingerprint(full)) {
      return full.length >= signal.length ? full : signal;
    }
    // Distinct content — join naturally
    const sep = /[.!?]$/.test(signal) ? " " : ". ";
    return `${signal}${sep}${full}`;
  }

  return full || signal;
}

function formatElapsed(seconds?: number | null): string | null {
  if (typeof seconds !== "number" || !Number.isFinite(seconds) || seconds <= 0) return null;
  if (seconds < 1) return `${Math.round(seconds * 1000)}ms`;
  return `${seconds.toFixed(seconds >= 10 ? 0 : 1)}s`;
}

// V-H-3: agent accent palette resolves to shared lib/agentTheme tokens so the
// same agent reads with the same accent across both AgentStatusCard and
// TimelineTab. Icon assignment stays here (the only place that needs it).
export const AGENT_ICONS: Record<string, LucideIcon> = {
  Agent1: ScanEye,
  Agent2: AudioWaveform,
  Agent3: Boxes,
  Agent4: Film,
  Agent5: Database,
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

// V-H-2: semantic Tailwind palette → semantic tokens.
const _SEV_LABEL: Record<string, string> = {
  CRITICAL: "text-danger",
  HIGH:     "text-danger",
  MEDIUM:   "text-warning",
  LOW:      "fc-text-faint",
};

function FindingRow({ f, i, total }: { f: FindingPreview; i: number; total: number }) {
  const [expanded, setExpanded] = useState(false);
  const isAlert = isAlertFinding(f);
  const sev = (f.severity || "").toUpperCase();
  const verdict = normalizeVerdict(f.verdict);
  const elapsed = formatElapsed(f.elapsed_s);
  const confidence = typeof f.confidence === "number" ? f.confidence : null;
  const tier = confidence !== null ? confidenceTier(confidence) : null;

  const unifiedText = buildUnifiedFindingText(f);
  const MAX_TEXT = 260;
  const needsExpand = unifiedText.length > MAX_TEXT;
  const visibleText = needsExpand && !expanded
    ? unifiedText.slice(0, MAX_TEXT).trimEnd() + "…"
    : unifiedText;

  const showVerdictBadge = f.verdict && f.verdict !== "CLEAN" && f.verdict !== "NOT_APPLICABLE";
  const showSeverityBadge = sev && ["CRITICAL", "HIGH", "MEDIUM"].includes(sev);

  return (
    <motion.div
      data-testid={`agent-finding-${i}`}
      initial={{ opacity: 0, y: 4 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ delay: i * 0.05, duration: 0.16 }}
      className={clsx(
        "py-3.5 pl-3 border-l-2 transition-colors",
        i > 0 && "border-t border-white/5",
        isAlert ? "border-l-danger/40" : "border-l-white/10"
      )}
    >
      {/* Header row: tool name left · confidence tier + % right */}
      <div className="flex items-center justify-between gap-3 mb-2">
        <div className="flex items-center gap-2 flex-wrap min-w-0">
          {f.tool && (
            <span className="text-xs font-mono font-bold fc-text-secondary tracking-wide">
              {fmtTool(f.tool)}
            </span>
          )}
          {showVerdictBadge && (
            <span className={clsx("fc-badge", isAlert ? "fc-badge-danger" : "fc-badge-success")}>
              {verdict}
            </span>
          )}
          {showSeverityBadge && (
            <span className={clsx(
              "fc-badge",
              (sev === "CRITICAL" || sev === "HIGH") ? "fc-badge-danger" : "fc-badge-warning"
            )}>
              {sev}
            </span>
          )}
          {f.degraded && (
            <span className="fc-badge fc-badge-warning" title={f.fallback_reason || ""}>
              Degraded
            </span>
          )}
        </div>
        {tier && confidence !== null && (
          <div className="flex items-center gap-1.5 shrink-0">
            <span className={clsx("fc-eyebrow", tier.colorClass)}>{tier.label}</span>
            <span className={clsx(
              "text-xs font-mono font-black tabular-nums",
              isAlert ? "text-danger" :
              confidence >= 0.75 ? "text-primary" :
              confidence >= 0.5 ? "text-warning" : "fc-text-faint"
            )}>
              {Math.round(confidence * 100)}%
            </span>
          </div>
        )}
      </div>

      {/* Unified finding paragraph — single cohesive block, no bold/normal split */}
      {unifiedText && (
        <p className={clsx(
          "text-sm leading-relaxed",
          isAlert ? "fc-text-secondary" : "fc-text-muted"
        )}>
          {visibleText}
          {needsExpand && (
            <button
              type="button"
              onClick={() => setExpanded(e => !e)}
              className="ml-1.5 inline-flex items-center gap-0.5 text-xs font-mono font-bold text-primary/75 hover:text-primary transition-colors align-baseline"
            >
              {expanded
                ? <><ChevronUp className="w-3 h-3" /><span>less</span></>
                : <><ChevronDown className="w-3 h-3" /><span>more</span></>
              }
            </button>
          )}
        </p>
      )}

      {/* Footer: position · section · timing */}
      <div className="flex items-center gap-2 mt-2 fc-eyebrow fc-text-faint">
        <span>{i + 1}/{total}</span>
        {f.section && (
          <><span className="text-white/15">·</span><span className="truncate">{f.section}</span></>
        )}
        {elapsed && <span className="ml-auto normal-case tracking-normal">{elapsed}</span>}
      </div>
    </motion.div>
  );
}

function AgentSummaryText({ text, sourceText }: { text: string; sourceText?: string }) {
  const [expanded, setExpanded] = useState(false);
  const source = cleanFindingText(sourceText || "").trim();
  const hasSource = source && summaryFingerprint(source) !== summaryFingerprint(text);
  if (!text) return null;
  return (
    <div className="border-t border-white/7 pt-3.5 space-y-2.5">
      <div className="flex items-center gap-2 fc-eyebrow fc-text-faint">
        <ListChecks className="w-3.5 h-3.5 text-primary/70" />
        Agent Brief
      </div>
      <p className="text-sm fc-text-secondary leading-relaxed font-medium">
        {text}
      </p>
       {hasSource && (
         <button
           type="button"
           onClick={() => setExpanded((e) => !e)}
           className="inline-flex items-center gap-1 text-xs font-mono font-bold text-primary/80 hover:text-primary transition-colors"
         >
           {expanded ? (
             <>
               <ChevronUp className="w-3.5 h-3.5" />
               <span>Hide detail</span>
             </>
           ) : (
             <>
               <ChevronDown className="w-3.5 h-3.5" />
               <span>Show tool basis</span>
             </>
           )}
         </button>
       )}
      {expanded && hasSource && (
        <p className="rounded-lg border border-white/8 bg-white/2 px-3 py-2.5 text-xs leading-relaxed fc-text-faint">
          {source}
        </p>
      )}
    </div>
  );
}

function buildAgentBrief(
  completedData: AgentUpdate | undefined,
  findings: FindingPreview[],
  toolsRan: number,
): string {
  if (!completedData) return "";

  // 1. Prefer the backend synthesis narrative — it was purpose-built as the
  //    agent-level summary and is more accurate than a tool-level construction.
  const synthSummary = cleanFindingText(completedData.summary || "").trim();
  if (synthSummary && !isTemplateSummary(synthSummary)) {
    return synthSummary;
  }

  // 2. Structural fallback — counts and aggregate signals only; never copies finding text.
  const verdict = normalizeVerdict(completedData.agent_verdict);
  const confidence = Math.round((completedData.confidence || 0) * 100);
  const toolText = toolsRan === 1 ? "1 tool" : `${toolsRan} tools`;
  const alertCount = findings.filter(isAlertFinding).length;
  const failedCount = completedData.tools_failed ?? 0;
  const parts = [`${verdict} at ${confidence}% confidence across ${toolText}`];
  if (alertCount > 0) {
    parts.push(`${alertCount} flagged signal${alertCount > 1 ? "s" : ""} detected`);
  } else if (findings.length > 0) {
    parts.push("no critical signals detected");
  }
  if (failedCount > 0) {
    parts.push(`${failedCount} tool${failedCount > 1 ? "s" : ""} degraded`);
  }
  return parts.join(" · ") + ".";
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
    if (status !== "running") {
      // Reset so the next run starts from the first phrase, not wherever the
      // last run was when the interval cleared.
      setFallbackPhraseIndex(0);
      return;
    }
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

  const accent = accentFor(agentId);
  const Icon = AGENT_ICONS[agentId] ?? Cpu;

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
       const summaryText = (f.summary || "").trim();
       const hasKeySignal = !!f.key_signal?.trim();
       const hasVerdict = !!f.verdict && f.verdict !== "INCONCLUSIVE" && f.verdict !== "CLEAN";
       const _confidence = typeof f.confidence === "number" ? f.confidence : 0;
       
       // Only drop the finding if it has no signal at all:
       // - summary is a template AND no key_signal AND no flagged verdict
       if (!hasKeySignal && !hasVerdict && isTemplateSummary(summaryText)) continue;
       
       // Dedup logic unchanged
       const toolPart = f.tool || summaryText.slice(0, 90).toLowerCase().trim();
       const fp = summaryFingerprint(summaryText || f.key_signal || "");
       const key = `${toolPart}::${(f.verdict || "").toUpperCase()}::${(f.severity || "").toUpperCase()}::${fp}`;
       if (!seen.has(key)) {
         deduped.push(f);
         seen.add(key);
       }
     }
     return deduped.sort((a, b) => rankFinding(a) - rankFinding(b));
   }, [completedData]);
  const verdictScore = completedData?.verdict_score;
  const agentVerdict = completedData?.agent_verdict;
  const isAgentAlert =
    (typeof verdictScore === "number" && verdictScore > 0.6) ||
    ALERT_VERDICTS.has(agentVerdict || "");
   // Use the backend-reported count of successful tool executions as the authoritative
   // number. Fall back to findings.length only if the backend didn't send tools_ran.
   const toolsRan =
     typeof completedData?.tools_ran === "number"
       ? completedData.tools_ran
       : findings.length;
  const agentBrief = buildAgentBrief(completedData, findings, toolsRan);
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
      className="relative flex flex-col overflow-hidden fc-surface-quiet border-none"
      data-testid={`agent-card-${agentId}`}
    >
      {/* --- Card Header --- */}
      <div className="p-7 pb-5 border-b border-white/5 relative z-10 bg-transparent">
        <div className="flex items-start justify-between mb-8">
          <div className="flex items-center gap-5">
            {/* Agent Icon */}
            <div className="relative w-16 h-16 flex items-center justify-center bg-transparent border border-white/5 rounded-xl">
              <Icon className={clsx("w-7 h-7 relative z-10", accent.textClass)} />
            </div>

            <div>
              <div className="flex items-center gap-2 mb-1.5">
                <h3 className="text-2xl font-heading font-bold fc-text-primary tracking-tight">{name}</h3>
                {completedData?.degraded && (
                  <motion.div
                    initial={{ opacity: 0 }}
                    animate={{ opacity: 1 }}
                    transition={{ duration: 0.16, ease: "easeOut" }}
                    className="fc-badge fc-badge-warning flex items-center gap-1.5"
                    title={completedData.fallback_reason || "Analysis degraded"}
                  >
                    <AlertTriangle className="w-3 h-3" />
                    Degraded
                  </motion.div>
                )}
              </div>
              <div className="flex items-center gap-2">
                <span className={clsx(
                  "fc-badge",
                  (status === "complete" || status === "checking" || status === "running") ? "fc-badge-active" :
                  status === "error" ? "fc-badge-danger" : ""
                )}>
                  {cfg.label}
                </span>
                <span className="fc-eyebrow fc-text-faint">
                  {badge || `Node ${agentId}`}
                </span>
              </div>
            </div>
          </div>
        </div>


        {/* --- Progress Section --- */}
        <AnimatePresence mode="wait">
          {(status === "running" || status === "checking") && (
            <motion.div
              initial={{ opacity: 0, y: 4 }}
              animate={{ opacity: 1, y: 0 }}
              exit={{ opacity: 0, y: 4 }}
              transition={{ duration: 0.16 }}
              className="space-y-4"
            >
              <div className="flex items-center gap-3 fc-text-muted">
                <motion.div key={progressDescriptor.label} initial={{ opacity: 0 }} animate={{ opacity: 1 }} transition={{ duration: 0.16 }}>
                  {status === "checking" ? (
                    <Activity className="w-4 h-4 text-primary" />
                  ) : (
                    <ProgressIcon className="w-4 h-4 text-primary" />
                  )}
                </motion.div>
                <span className="fc-eyebrow truncate">
                  {status === "checking"
                    ? (phase === "deep" ? "Re-arming for deep analysis..." : "Synchronizing with pipeline...")
                    : (Math.max(liveTotal, currentToolIndex, 1) > 1 
                        ? `${progressDescriptor.label} ${currentToolIndex}/${Math.max(liveTotal, currentToolIndex, 1)}`
                        : progressDescriptor.label
                      )}
                </span>
              </div>
              <div className="relative w-full h-[4px] bg-white/10 overflow-hidden">
                <motion.div
                  className="absolute top-0 bottom-0 bg-white"
                  animate={{
                    width: status === "checking" ? "100%" : `${(currentToolIndex / liveTotal) * 100}%`,
                  }}
                  transition={{ duration: 0.2 }}
                />
              </div>

            </motion.div>
          )}

          {status === "complete" && completedData && (
            <motion.div
              initial={{ opacity: 0, y: 4 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ duration: 0.16 }}
              className="space-y-4"
            >
              <div className="flex items-end justify-between">
                <div>
                  <span className="fc-eyebrow fc-text-faint block mb-1.5">Final Verdict</span>
                  <span className={clsx(
                    "text-2xl font-heading font-bold tracking-tight",
                    isAgentAlert ? "text-danger" : agentVerdict === "INCONCLUSIVE" ? "text-warning" : "text-success"
                  )}>
                    {normalizeVerdict(completedData.agent_verdict)}
                  </span>
                </div>
                <div className="text-right">
                  <span className="fc-eyebrow fc-text-faint block mb-1.5">Confidence</span>
                  <span className="text-2xl font-mono font-bold text-white tabular-nums">
                    {Math.round(completedData.confidence * 100)}%
                  </span>
                </div>
              </div>
               <AgentSummaryText
                 text={agentBrief}           // buildAgentBrief now returns synthesis first
                 sourceText={
                   // Only offer the toggle when brief was a fallback construction
                   // (i.e. synthesis was missing and we built from tool data)
                   !cleanFindingText(completedData.summary || "").trim()
                     ? (completedData.message || "")
                     : ""
                 }
               />
            </motion.div>
          )}
        </AnimatePresence>
      </div>

      {/* --- Findings Surface --- */}
      <div className="px-6 py-5 relative z-10">
        <AnimatePresence mode="wait">
           {status === "complete" && findings.length > 0 ? (
             <>
               <div className="flex items-center justify-between mb-3 px-1">
                 <span className="fc-eyebrow fc-text-faint">
                   {findings.length} finding{findings.length !== 1 ? "s" : ""}
                   {toolsRan > findings.length ? ` · ${toolsRan} tools` : ""}
                 </span>
                 {(completedData?.tools_failed ?? 0) > 0 && (
                   <span className="fc-badge fc-badge-warning">
                     {completedData!.tools_failed} tool{completedData!.tools_failed! > 1 ? "s" : ""} degraded
                   </span>
                 )}
               </div>
               <div className="space-y-3">
                 {(() => {
                   const MAX_COLLAPSED = 2;
                   const alertFindings = findings.filter(isAlertFinding);
                   const nonAlertFindings = findings.filter(f => !isAlertFinding(f));

                   const collapsedFindings = isExpanded
                     ? findings
                     : alertFindings.length > 0
                       ? [
                           ...alertFindings.slice(0, Math.min(2, alertFindings.length)),
                           ...nonAlertFindings.slice(0, Math.max(0, MAX_COLLAPSED - Math.min(2, alertFindings.length))),
                         ]
                       : findings.slice(0, MAX_COLLAPSED);

                   return collapsedFindings.map((f, i) => (
                     <FindingRow key={`${f.tool}-${i}`} f={f} i={i} total={findings.length} />
                   ));
                 })()}

                 {findings.length > 2 && (
                   <button
                     type="button"
                     onClick={() => onToggleExpand?.()}
                     className="fc-btn-secondary w-full gap-2 mt-3 text-xs"
                     aria-expanded={isExpanded}
                   >
                     {isExpanded
                       ? <><ChevronUp className="w-4 h-4" /><span>See fewer findings</span></>
                       : <><ChevronDown className="w-4 h-4" /><span>Show {findings.length - 2} more finding{findings.length - 2 !== 1 ? "s" : ""}</span></>
                     }
                   </button>
                 )}
               </div>
             </>
           ) : (status === "running" || status === "checking" || status === "validating") ? (
            <div
              className="flex flex-col items-center justify-center h-full text-center gap-4 py-12"
              aria-live="polite"
              aria-atomic="true"
            >
              <div className="w-12 h-12 rounded-xl bg-primary/5 border border-primary/20 flex items-center justify-center text-primary">
                {status === "running" ? (
                  <ProgressIcon className="w-6 h-6" />
                ) : (
                  <Activity className="w-6 h-6" />
                )}
              </div>
              <AnimatePresence mode="wait">
                <motion.p
                  key={sanitizeThinking(liveUpdate?.thinking || thinking) || FALLBACK_PHRASES[agentId]?.[fallbackPhraseIndex] || (status === "validating" ? "Verifying chain of custody..." : "Processing evidence...")}
                  initial={{ opacity: 0, y: 4 }}
                  animate={{ opacity: 1, y: 0 }}
                  exit={{ opacity: 0, transition: { duration: 0.1 } }}
                  transition={{ duration: 0.16 }}
                  className="max-w-[280px] text-xs fc-text-faint font-medium leading-relaxed"
                >
                  {sanitizeThinking(liveUpdate?.thinking || thinking) || FALLBACK_PHRASES[agentId]?.[fallbackPhraseIndex] || (status === "validating" ? "Verifying chain of custody..." : "Processing evidence...")}
                </motion.p>
              </AnimatePresence>
            </div>


          ) : status === "queued" ? (
            <div className="flex flex-col items-center justify-center h-full text-center gap-4 py-12">
               <div className="w-12 h-12 rounded-xl bg-transparent border border-white/5 flex items-center justify-center fc-text-faint">
                  <Activity className="w-6 h-6" />
               </div>
               <p className="max-w-xs text-xs fc-text-faint font-medium leading-relaxed">
                 {sanitizeThinking(thinking) || "Investigation is queued. Waiting for an available forensic worker..."}
               </p>
            </div>
          ) : status === "waiting" ? (
            <div className="flex flex-col items-center justify-center h-full text-center py-12">
               <span className="text-xs fc-text-faint font-medium">Standing by — payload not yet received</span>
            </div>
          ) : status === "unsupported" ? (
            <div className="flex flex-col items-center justify-center h-full text-center gap-3 py-12">
              <div className="w-12 h-12 rounded-xl bg-transparent border border-white/5 flex items-center justify-center fc-text-faint">
                <AlertTriangle className="w-6 h-6" />
              </div>
              <p className="max-w-xs text-xs fc-text-faint font-medium leading-relaxed">
                {sanitizeThinking(liveUpdate?.thinking || thinking) ||
                  completedData?.message ||
                  "This specialist does not support the submitted file type."}
              </p>
              <span className="fc-eyebrow fc-text-faint">
                Hidden after 10s
              </span>
            </div>
          ) : null}
        </AnimatePresence>
      </div>
    </motion.div>
  );
}
