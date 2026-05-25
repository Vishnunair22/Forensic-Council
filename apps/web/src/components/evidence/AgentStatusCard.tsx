"use client";

import React, { useEffect, useState } from "react";
import { motion, AnimatePresence, useReducedMotion } from "framer-motion";
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
  CheckCircle2,
  HelpCircle,
  ShieldAlert,
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
  // Backend-generated formulaic summaries — not meaningful LLM synthesis
  /\bis the strongest agent signal:/i,
  /\bat \d+%? confidence across \d+ applicable findings/i,
  /\bagent (?:returned|determined|concluded):\s*\w/i,
  /^negative at \d+%? confidence/i,
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
  waiting:     { color: "fc-text-muted",   label: "Standby"   },
  queued:      { color: "fc-text-muted",   label: "Queued"    },
  checking:    { color: "text-primary",    label: "Syncing"   },
  running:     { color: "text-primary",    label: "Scanning"  },
  complete:    { color: "text-success",    label: "Verified"  },
  error:       { color: "fc-text-danger",  label: "Error"     },
  unsupported: { color: "fc-text-muted",   label: "Skipped"   },
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
  const value = (typeof verdict === "string" ? verdict : (verdict ? String(verdict) : "INCONCLUSIVE")).replace(/_/g, " ");
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
  if (c >= 0.8) return { label: "High", colorClass: "text-success" };
  if (c >= 0.55) return { label: "Medium", colorClass: "text-warning" };
  return { label: "Low", colorClass: "fc-text-muted" };
}

function buildUnifiedFindingText(f: FindingPreview): string {
  const signal = cleanFindingText(f.key_signal || "").trim();
  const full = cleanFindingText(f.summary || "").trim();

  if (!signal && !full) {
    if (f.verdict && !["INCONCLUSIVE", "CLEAN", "AUTHENTIC", "NEGATIVE", "NOT_APPLICABLE"].includes(f.verdict.toUpperCase())) {
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
  LOW:      "fc-text-muted",
};

function FindingRow({ f, i }: { f: FindingPreview; i: number }) {
  const [expanded, setExpanded] = useState(false);
  const prefersReduced = useReducedMotion();
  const isAlert = isAlertFinding(f);
  const isCritical = (f.severity || "").toUpperCase() === "CRITICAL";
  const isHigh = (f.severity || "").toUpperCase() === "HIGH";
  const isMedium = (f.severity || "").toUpperCase() === "MEDIUM";
  const confidence = typeof f.confidence === "number" ? f.confidence : null;
  const elapsed = formatElapsed(f.elapsed_s);

  const unifiedText = buildUnifiedFindingText(f);
  const MAX_TEXT = 240;
  const needsExpand = unifiedText.length > MAX_TEXT;
  const visibleText = needsExpand && !expanded
    ? unifiedText.slice(0, MAX_TEXT).trimEnd() + "…"
    : unifiedText;


  return (
    <motion.div
      data-testid={`agent-finding-${i}`}
      initial={prefersReduced ? false : { opacity: 0, y: 4 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ delay: prefersReduced ? 0 : i * 0.05, duration: 0.16 }}
      className={clsx(
        "group rounded-xl border border-white/[0.05] bg-white/[0.02] px-3.5 py-3 transition-colors",
        (isCritical || isHigh) && "bg-danger/[0.03] border-danger/[0.10]",
        isMedium && "bg-warning/[0.02] border-warning/[0.08]",
      )}
    >
      {/* Row 1: Tool label + tier + confidence */}
      <div className="flex items-center justify-between gap-2 mb-2">
        <div className="flex items-center gap-1.5 min-w-0 flex-wrap">
          {f.tool && (
            <span className="inline-flex items-center px-2 py-0.5 rounded-md bg-white/[0.04] border border-white/[0.08] text-xs font-mono font-medium fc-text-secondary shrink-0 tracking-wider">
              {fmtTool(f.tool)}
            </span>
          )}
          {confidence !== null && (
            <span className={clsx("fc-badge shrink-0 border", confidenceTier(confidence).colorClass,
              confidence >= 0.8 ? "border-primary/30 bg-primary/5"
              : confidence >= 0.55 ? "border-warning/30 bg-warning/5"
              : "border-white/20 bg-white/[0.03]"
            )}>
              {confidenceTier(confidence).label}
            </span>
          )}
          {f.degraded && (
            <span className="fc-badge fc-badge-warning shrink-0" title={f.fallback_reason || ""}>
              Degraded
            </span>
          )}
        </div>
        {confidence !== null && (
          <span className={clsx(
            "text-xs font-mono font-bold tabular-nums shrink-0",
            (isCritical || isHigh || isAlert) ? "text-danger" :
            confidence >= 0.75 ? "text-success" :
            confidence >= 0.5 ? "text-warning" : "fc-text-muted"
          )}>
            {Math.round(confidence * 100)}%
          </span>
        )}
      </div>

      {/* Row 2: Finding text */}
      {unifiedText && (
        <p className={clsx(
          "text-base leading-relaxed",
          (isCritical || isHigh || isAlert) ? "fc-text-primary" : "fc-text-secondary"
        )}>
          {visibleText}
          {needsExpand && (
            <button
              type="button"
              onClick={() => setExpanded(e => !e)}
              className="ml-1.5 inline-flex items-center gap-0.5 text-xs font-mono font-bold text-primary/70 hover:text-primary fc-transition rounded align-baseline"
            >
              {expanded
                ? <><ChevronUp className="w-3 h-3" /><span>less</span></>
                : <><ChevronDown className="w-3 h-3" /><span>more</span></>
              }
            </button>
          )}
        </p>
      )}

      {/* Row 3: Footer metadata — only render if there's meaningful content */}
      {elapsed && (
        <div className="flex items-center gap-2 mt-2 fc-eyebrow fc-text-faint">
          {elapsed && <span className="ml-auto normal-case tracking-normal">{elapsed}</span>}
        </div>
      )}
    </motion.div>
  );
}

interface AgentBriefProps {
  completedData: AgentUpdate;
  findings: FindingPreview[];
  toolsRan: number;
}

function AgentBrief({ completedData, findings, toolsRan }: AgentBriefProps) {
  const rawSummary = typeof completedData.summary === "string"
    ? completedData.summary
    : completedData.summary ? JSON.stringify(completedData.summary) : "";

  let synthSummary = cleanFindingText(rawSummary).trim();

  const jsonMatch = rawSummary.match(/\{[\s\S]*\}/);
  if (jsonMatch) {
    try {
      const parsed = JSON.parse(jsonMatch[0]);
      if (parsed.evidence_assessment && parsed.reliability_verdict) {
        synthSummary = `${parsed.evidence_assessment} ${parsed.reliability_verdict}`;
      }
    } catch { /* ignore */ }
  }

  const verdict = (completedData.agent_verdict ?? "").toUpperCase();
  const isAlert = ALERT_VERDICTS.has(verdict) || (completedData.verdict_score ?? 0) > 0.6;
  const isInconclusive = verdict === "INCONCLUSIVE";
  const isClean = verdict === "AUTHENTIC" || verdict === "CLEAN" || verdict === "NEGATIVE";

  // Pick a single high-impact statement.
  // Priority: real LLM synthesis → worst section flag key_signal → top finding signal.
  const brief = (() => {
    if (synthSummary && !isTemplateSummary(synthSummary)) return synthSummary;

    // Section flags are already section-level synthesis — prefer over raw tool text.
    const FLAG_RANK: Record<string, number> = { bad: 0, warn: 1, ok: 2, info: 3 };
    const sections = [...(completedData.section_flags ?? [])].sort(
      (a, b) => (FLAG_RANK[a.flag] ?? 4) - (FLAG_RANK[b.flag] ?? 4),
    );
    for (const sec of sections) {
      const s = cleanFindingText(sec.key_signal || "").trim();
      if (s && !isTemplateSummary(s)) return s;
    }

    // Last resort: the single highest-ranked finding that has its own key_signal.
    for (const f of findings) {
      const s = cleanFindingText(f.key_signal || "").trim();
      if (s && !isTemplateSummary(s)) return s;
    }

    // Synthesise from agent-level data — never duplicates a tool finding.
    const conf = Math.round(completedData.confidence * 100);
    const n = completedData.tools_ran ?? findings.length;
    const alertCount = findings.filter(isAlertFinding).length;

    // Use section labels to name what was examined; fall back to a check count.
    const sectionLabels = sections
      .map(s => cleanFindingText(s.label || "").trim())
      .filter(Boolean)
      .slice(0, 3);
    const domainPhrase = sectionLabels.length >= 2
      ? `${sectionLabels.slice(0, -1).join(", ")} and ${sectionLabels.at(-1)}`
      : sectionLabels.length === 1
        ? sectionLabels[0]
        : `${n} forensic check${n !== 1 ? "s" : ""}`;

    if (isAlert) {
      const anomalyClause = alertCount > 0
        ? `${alertCount} active anomaly flag${alertCount === 1 ? "" : "s"} raised`
        : `critical anomalies flagged`;
      return `Critical anomalies detected in ${domainPhrase} (${conf}% confidence). ${anomalyClause} — structural composition and metadata analysis indicate active manipulation or synthetic tampering.`;
    }
    if (isClean) {
      return `Verification of ${domainPhrase} completed successfully (${conf}% confidence). All specialized scans returned clean signals, showing no indications of digital alteration, AI generation, or structural anomalies.`;
    }
    if (isInconclusive) {
      return `Specialist analysis of ${domainPhrase} is inconclusive (${conf}% confidence). Sensor noise, metadata gaps, or compression artifacts limit detection confidence, yielding ambiguous signals.`;
    }
    if (n > 0) {
      return `Intake screening of ${domainPhrase} completed (${conf}% confidence). ${n} diagnostic scans executed, establishing baseline parameters without flagging decisive manipulation indicators.`;
    }

    return null;
  })();

  const failedCount = completedData.tools_failed ?? 0;

  if (!brief) return null;

  // Render styling based on status
  const containerStyle = isAlert
    ? "bg-danger/[0.04] border-danger/20 text-[#fca5a5]"
    : isInconclusive
    ? "bg-warning/[0.04] border-warning/20 text-[#fde68a]"
    : isClean
    ? "bg-success/[0.04] border-success/20 text-[#bbf7d0]"
    : "bg-white/[0.01] border-white/5 fc-text-primary";

  const iconColor = isAlert
    ? "text-danger"
    : isInconclusive
    ? "text-warning"
    : isClean
    ? "text-success"
    : "text-primary";

  const StatusIcon = isAlert
    ? ShieldAlert
    : isInconclusive
    ? HelpCircle
    : isClean
    ? CheckCircle2
    : ListChecks;

  return (
    <div className="border-t border-white/[0.07] pt-4 mt-3 space-y-3">
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2 fc-eyebrow fc-text-muted">
          <StatusIcon className={`w-3.5 h-3.5 ${iconColor} shrink-0`} />
          <span>Agent Brief</span>
        </div>
        {(toolsRan > 0 || failedCount > 0) && (
          <div className="flex items-center gap-1.5 text-xs font-mono fc-text-muted tracking-wider">
            <span>{toolsRan} tool{toolsRan !== 1 ? "s" : ""} active</span>
            {failedCount > 0 && (
              <>
                <span>·</span>
                <span className="text-warning">{failedCount} degraded</span>
              </>
            )}
          </div>
        )}
      </div>

      <div className={`text-sm leading-relaxed border p-3.5 rounded-xl transition-all duration-[160ms] ${containerStyle}`}>
        {brief}
      </div>
    </div>
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
  const prefersReduced = useReducedMotion();
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
      const raw = Array.isArray(completedData?.findings_preview) ? completedData.findings_preview : [];
      const deduped: FindingPreview[] = [];
      const seen = new Set<string>();
      for (const f of raw) {
        if (!f) continue;
        const rawSummary = typeof f.summary === "string" ? f.summary : (f.summary ? String(f.summary) : "");
        const rawKeySignal = typeof f.key_signal === "string" ? f.key_signal : (f.key_signal ? String(f.key_signal) : "");
        const rawVerdict = typeof f.verdict === "string" ? f.verdict : (f.verdict ? String(f.verdict) : "");
        const rawSeverity = typeof f.severity === "string" ? f.severity : (f.severity ? String(f.severity) : "");
        const rawTool = typeof f.tool === "string" ? f.tool : (f.tool ? String(f.tool) : "");

        const summaryText = rawSummary.trim();
        const hasKeySignal = rawKeySignal.trim().length > 0;
        const hasVerdict = rawVerdict.length > 0 && rawVerdict !== "INCONCLUSIVE" && rawVerdict !== "CLEAN";

        // Only drop the finding if it has no signal at all:
        // - summary is a template AND no key_signal AND no flagged verdict
        if (!hasKeySignal && !hasVerdict && isTemplateSummary(summaryText)) continue;

        const toolPart = rawTool || summaryText.slice(0, 90).toLowerCase().trim();
        const fp = summaryFingerprint(summaryText || rawKeySignal);
        const key = `${toolPart}::${rawVerdict.toUpperCase()}::${rawSeverity.toUpperCase()}::${fp}`;
        if (!seen.has(key)) {
          deduped.push({
            ...f,
            summary: rawSummary,
            key_signal: rawKeySignal,
            verdict: rawVerdict,
            severity: rawSeverity,
            tool: rawTool,
          });
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
      layout={prefersReduced ? false : true}
      className={clsx(
        "relative flex flex-col overflow-hidden transition-all duration-[160ms]",
        isExpanded ? "fc-surface-elevated" : "fc-surface-quiet",
        (status === "running" || status === "checking" || status === "validating") && "fc-agent-active",
        status === "complete" && "fc-agent-complete",
        status === "error" && "fc-agent-error"
      )}
      data-testid={`agent-card-${agentId}`}
    >
      {/* --- Card Header --- */}
      <div className="p-7 pb-5 border-b border-white/5 relative z-10 bg-transparent">
        <div className="flex items-start justify-between mb-8">
          <div className="flex items-center gap-5">
            {/* Agent Icon */}
            <div className="relative w-16 h-16 flex items-center justify-center bg-transparent border border-white/5 rounded-2xl">
              <Icon className={clsx("w-7 h-7 relative z-10", accent.textClass)} />
            </div>

            <div>
              <div className="flex items-center gap-2 mb-1.5">
                <h3 className="text-xl font-heading font-bold fc-text-primary tracking-tight">{name}</h3>
                {completedData?.degraded && (
                  <motion.div
                    initial={prefersReduced ? false : { opacity: 0 }}
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
                <span className="fc-eyebrow fc-text-muted">
                  {badge || `Node ${agentId}`}
                </span>
              </div>
            </div>
          </div>
        </div>


        {/* --- Upgraded Progress Section --- */}
        <AnimatePresence mode="wait">
          {(status === "running" || status === "checking") && (
            <motion.div
              initial={prefersReduced ? false : { opacity: 0, y: 4 }}
              animate={{ opacity: 1, y: 0 }}
              exit={prefersReduced ? {} : { opacity: 0, y: 4 }}
              transition={{ duration: 0.16 }}
              className="space-y-4"
            >
              <div className="flex items-center gap-3 min-w-0">
                <motion.div
                  key={progressDescriptor.label}
                  initial={prefersReduced ? false : { opacity: 0, scale: 0.8 }}
                  animate={{ opacity: 1, scale: 1 }}
                  className="shrink-0 relative"
                >
                  {/* Pulsing ring behind icon */}
                  <div className="absolute inset-0 rounded-full bg-primary/20 animate-ping" />
                  {status === "checking" ? (
                    <Activity className="w-4 h-4 text-primary relative z-10" />
                  ) : (
                    <ProgressIcon className="w-4 h-4 text-primary relative z-10" />
                  )}
                </motion.div>

                {/* Terminal-style text */}
                <span className="text-sm font-medium min-w-0 break-words text-primary flex items-center">
                  <span className="mr-2 opacity-50">&gt;</span>
                  {status === "checking"
                    ? (phase === "deep" ? "Re-arming for deep analysis..." : "Synchronizing with pipeline...")
                    : (Math.max(liveTotal, currentToolIndex, 1) > 1
                        ? `${progressDescriptor.label} ${currentToolIndex}/${Math.max(liveTotal, currentToolIndex, 1)}`
                        : progressDescriptor.label
                      )}
                  <motion.span
                    animate={{ opacity: [1, 0] }}
                    transition={{ duration: 0.5, repeat: Infinity, repeatType: "reverse" }}
                    className="ml-1 inline-block w-1.5 h-3 bg-primary"
                  />
                </span>
              </div>

              {/* Cyber-Tactical Progress Bar */}
              <div className="relative w-full h-2 bg-black/40 rounded-full overflow-hidden border border-white/10 shadow-[inset_0_1px_3px_rgba(0,0,0,0.5)]">
                {/* Segmented hash marks background */}
                <div className="absolute inset-0 bg-[url('data:image/svg+xml;base64,PHN2ZyB3aWR0aD0iNCIgaGVpZ2h0PSI0IiB4bWxucz0iaHR0cDovL3d3dy53My5vcmcvMjAwMC9zdmciPjxyZWN0IHdpZHRoPSIxIiBoZWlnaHQ9IjQiIGZpbGw9InJnYmEoMjU1LDI1NSwyNTUsMC4wNSkiLz48L3N2Zz4=')] opacity-50" />

                <motion.div
                  className="absolute top-0 bottom-0 bg-primary rounded-full relative overflow-hidden"
                  animate={{
                    width: status === "checking" ? "100%" : `${(currentToolIndex / liveTotal) * 100}%`,
                  }}
                  transition={{ duration: 0.3, ease: "easeOut" }}
                  style={{ boxShadow: "0 0 10px rgba(var(--color-primary-rgb), 0.5)" }}
                >
                  {/* Infinite Light Sweep effect */}
                  <motion.div
                    className="absolute top-0 bottom-0 left-0 w-full bg-gradient-to-r from-transparent via-white/40 to-transparent"
                    animate={{ x: ["-100%", "200%"] }}
                    transition={{ duration: 1.5, repeat: Infinity, ease: "linear" }}
                  />
                </motion.div>
              </div>
            </motion.div>
          )}

          {status === "complete" && completedData && (
            <motion.div
              initial={prefersReduced ? false : { opacity: 0, y: 4 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ duration: 0.16 }}
              className="space-y-4"
            >
              <div className="flex items-end justify-between">
                <div>
                  <span className="fc-eyebrow fc-text-muted block mb-1.5">Final Verdict</span>
                  <span className={clsx(
                    "text-2xl font-heading font-bold tracking-tight",
                    isAgentAlert ? "text-danger" : agentVerdict === "INCONCLUSIVE" ? "text-warning" : "text-success"
                  )}>
                    {normalizeVerdict(completedData.agent_verdict)}
                  </span>
                </div>
                <div className="text-right">
                  <span className="fc-eyebrow fc-text-muted block mb-1.5">Confidence</span>
                  <span className="text-2xl font-mono font-bold fc-text-primary tabular-nums">
                    {Math.round(completedData.confidence * 100)}%
                  </span>
                </div>
              </div>
               <AgentBrief
                 completedData={completedData}
                 findings={findings}
                 toolsRan={toolsRan}
               />
            </motion.div>
          )}
        </AnimatePresence>
      </div>

      {/* --- Findings Surface --- */}
      <div className="px-5 pb-5 pt-0 relative z-10">
        <AnimatePresence mode="wait">
           {status === "complete" && findings.length > 0 ? (
             <>
               {/* Findings header */}
               <div className="flex items-center justify-between mb-3 px-0.5">
                 <div className="flex items-center gap-2">
                   <span className="fc-eyebrow fc-text-muted">
                     {findings.length} finding{findings.length !== 1 ? "s" : ""}
                   </span>
                   {toolsRan > 0 && (
                     <>
                       <span className="fc-text-faint fc-eyebrow">·</span>
                       <span className="fc-eyebrow fc-text-faint">{toolsRan} tool{toolsRan !== 1 ? "s" : ""} ran</span>
                     </>
                   )}
                 </div>
                 {completedData && typeof completedData.tools_failed === "number" && completedData.tools_failed > 0 && (
                   <span className="fc-badge fc-badge-warning">
                     {completedData.tools_failed} degraded
                   </span>
                 )}
               </div>
               <div className="space-y-2">
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
                     <FindingRow key={`${f.tool}-${i}`} f={f} i={i} />
                   ));
                 })()}

                 {findings.length > 2 && (
                   <button
                     type="button"
                     onClick={() => onToggleExpand?.()}
                      className="fc-btn-secondary w-full gap-2 mt-2 text-sm"
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
              <div className="w-12 h-12 rounded-2xl bg-primary/5 border border-primary/20 flex items-center justify-center text-primary">
                {status === "running" ? (
                  <ProgressIcon className="w-6 h-6" />
                ) : (
                  <Activity className="w-6 h-6" />
                )}
              </div>
              <AnimatePresence mode="wait">
                <motion.p
                  key={sanitizeThinking(liveUpdate?.thinking || thinking) || FALLBACK_PHRASES[agentId]?.[fallbackPhraseIndex] || (status === "validating" ? "Verifying chain of custody..." : "Processing evidence...")}
                  initial={prefersReduced ? false : { opacity: 0, y: 4 }}
                  animate={{ opacity: 1, y: 0 }}
                  exit={prefersReduced ? {} : { opacity: 0, transition: { duration: 0.1 } }}
                  transition={{ duration: 0.16 }}
                  className="max-w-[280px] text-sm fc-text-muted font-normal leading-relaxed"
                >
                  {sanitizeThinking(liveUpdate?.thinking || thinking) || FALLBACK_PHRASES[agentId]?.[fallbackPhraseIndex] || (status === "validating" ? "Verifying chain of custody..." : "Processing evidence...")}
                </motion.p>
              </AnimatePresence>
            </div>


          ) : status === "queued" ? (
            <div className="flex flex-col items-center justify-center h-full text-center gap-4 py-12">
               <div className="w-12 h-12 rounded-2xl bg-transparent border border-white/5 flex items-center justify-center fc-text-muted">
                  <Activity className="w-6 h-6" />
               </div>
               <p className="max-w-xs text-sm fc-text-muted font-normal leading-relaxed">
                  {sanitizeThinking(thinking) || "Investigation is queued. Waiting for an available forensic worker..."}
               </p>
            </div>
          ) : status === "waiting" ? (
            <div className="flex flex-col items-center justify-center h-full text-center py-12">
               <span className="text-sm fc-text-muted font-normal">Standing by — payload not yet received</span>
            </div>
          ) : status === "unsupported" ? (
            <div className="flex flex-col items-center justify-center h-full text-center gap-3 py-12">
              <div className="w-12 h-12 rounded-2xl bg-transparent border border-white/5 flex items-center justify-center fc-text-muted">
                <AlertTriangle className="w-6 h-6" />
              </div>
              <p className="max-w-xs text-sm fc-text-muted font-normal leading-relaxed">
                {sanitizeThinking(liveUpdate?.thinking || thinking) ||
                  completedData?.message ||
                  "This specialist does not support the submitted file type."}
              </p>
              <span className="fc-eyebrow fc-text-muted">
                Hidden after 10s
              </span>
            </div>
          ) : null}
        </AnimatePresence>
      </div>
    </motion.div>
  );
}
