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
import type { AgentUpdate, FindingPreview } from "./AgentProgressDisplay";

const TEMPLATE_SUMMARY_RE = [
  /^analysis (?:complete|completed|finished)\.?$/i,
  /^tool (?:execution )?(?:complete|completed|finished)(?:\s+successfully)?\.?$/i,
  /^checked:?\s*$/i,
  /^no diagnostic output\.?$/i,
  /^[^.]{0,80}completed\.?$/i,
  /^[^.]{0,80}completed;\s*review detailed tool metrics\.?$/i,
  /^(?:check|scan|run)\s+(?:ok|complete|finished)\.?$/i,
];

function isTemplateSummary(text: string): boolean {
  const t = text.trim();
  if (!t) return true;
  if (t.length < 18) return true;
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
  const ks = cleanFindingText(f.key_signal || "").trim();
  if (ks) return ks;
  const summary = cleanFindingText(f.summary || "").trim();
  const firstSentence = summary.split(/(?<=\.)\s+/)[0];
  if (firstSentence) return firstSentence;
  if (f.verdict && f.verdict !== "INCONCLUSIVE") return `${normalizeVerdict(f.verdict)} signal reported.`;
  if (f.tool) return `${fmtTool(f.tool)} completed without a detailed narrative.`;
  return "Tool completed without a detailed narrative.";
}

function extractDetail(f: FindingPreview, headline: string): string {
  const summary = cleanFindingText(f.summary || "").trim();
  if (!summary || summary === headline) return "";
  if (cleanFindingText(f.key_signal || "").trim() === headline) return summary;
  const after = summary.slice(headline.length).replace(/^[.\s]+/, "").trim();
  return after;
}

function compactText(text: string, maxLen = 190): string {
  const cleaned = cleanFindingText(text || "").trim();
  if (!cleaned || cleaned.length <= maxLen) return cleaned;
  const clipped = cleaned.slice(0, maxLen);
  const sentenceMatch = clipped.match(/^(.{80,}?[.!?])\s/);
  if (sentenceMatch?.[1]) return sentenceMatch[1];
  const lastSpace = clipped.lastIndexOf(" ");
  return `${lastSpace > 80 ? clipped.slice(0, lastSpace) : clipped}...`;
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
const SEV_LABEL: Record<string, string> = {
  CRITICAL: "text-danger",
  HIGH:     "text-danger",
  MEDIUM:   "text-warning",
  LOW:      "text-white/35",
};

function FindingRow({ f, i, total }: { f: FindingPreview; i: number; total: number }) {
  const [expanded, setExpanded] = useState(false);
  const isAlert = isAlertFinding(f);
  const sev = (f.severity || "").toUpperCase();
  const verdict = normalizeVerdict(f.verdict);
  const elapsed = formatElapsed(f.elapsed_s);

  const sevLabelColor = SEV_LABEL[sev] ?? (isAlert ? "text-danger" : "text-white/45");

  const headline = extractHeadline(f);
  const detail = extractDetail(f, headline);
  const MAX = 180;
  const needsExpand = detail.length > MAX;
  const visibleDetail = needsExpand && !expanded ? detail.slice(0, MAX).trimEnd() + "…" : detail;

  return (
    <motion.div
      data-testid={`agent-finding-${i}`}
      initial={{ opacity: 0, y: 4 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ delay: i * 0.05, duration: 0.25 }}
      className={clsx(
        "relative border-l-4 bg-surface-2 hover:bg-surface-3 transition-colors border-y border-r border-border-muted",
        "px-4 py-3",
        isAlert
          ? "border-l-red-500"
          : "border-l-[#555555]"
      )}
    >


      <div className="flex flex-col gap-2.5 min-w-0">
        {/* Top row */}
        <div className="flex items-center gap-2 flex-wrap">
          {f.tool && (
            <span className={clsx(
              "inline-flex items-center max-w-full px-2.5 py-1 rounded-md text-[11px] font-bold tracking-wide",
              isAlert
                ? "bg-danger/15 text-danger border border-danger/30"
                : "bg-white/[0.06] text-white/80 border border-white/[0.12]"
            )}>
              {fmtTool(f.tool)}
            </span>
          )}
          {f.verdict && (
            <span className={clsx(
              "text-[10px] font-mono font-black tracking-wide px-1.5 py-0.5 rounded border",
              isAlert
                ? "bg-danger/10 border-danger/25 text-danger"
                : "bg-emerald-400/10 border-emerald-400/20 text-emerald-200/80"
            )}>
              {verdict}
            </span>
          )}
          {sev && SEV_LABEL[sev] && (
            <span className={clsx(
              "text-[11px] font-mono font-black tracking-wide px-1.5 py-0.5 rounded",
              sevLabelColor,
              sev === "CRITICAL" || sev === "HIGH" ? "bg-danger/10 border border-danger/25" :
              sev === "MEDIUM" ? "bg-warning/10 border border-warning/25" :
              "bg-white/[0.04] border border-white/10"
            )}>
              {sev}
            </span>
          )}
          {f.degraded && (
            <span className="text-[11px] font-mono font-bold text-warning border border-warning/30 bg-warning/10 rounded px-1.5 py-0.5" title={f.fallback_reason || ""}>
              DEGRADED
            </span>
          )}
          {typeof f.confidence === "number" && (
            <span className={clsx(
              "ml-auto text-[12px] font-mono font-black tabular-nums shrink-0",
              isAlert ? "text-danger" :
              f.confidence >= 0.75 ? "text-[var(--color-primary)]" :
              f.confidence >= 0.5 ? "text-warning" :
              "text-white/60"
            )}>
              {Math.round(f.confidence * 100)}%
            </span>
          )}
        </div>

        {/* Headline — full text, two-line clamp until expanded */}
        {headline && (
          <p className={clsx(
            "text-[14px] font-semibold leading-snug",
            isAlert ? "text-white" : "text-white/90",
            !expanded && "line-clamp-2",
          )}>
            {headline}
          </p>
        )}

        {/* Detail */}
        {detail && (
          <div className="space-y-1.5">
            <p className="text-[13px] text-white/65 leading-relaxed">{visibleDetail}</p>
            {needsExpand && (
              <button
                type="button"
                onClick={() => setExpanded(e => !e)}
                className="inline-flex items-center gap-1 text-[11px] font-mono font-bold text-[var(--color-primary)]/75 hover:text-[var(--color-primary)] transition-colors"
              >
                {expanded
                  ? <><ChevronUp className="w-3.5 h-3.5" /><span>Show less</span></>
                  : <><ChevronDown className="w-3.5 h-3.5" /><span>Show more</span></>
                }
              </button>
            )}
          </div>
        )}

        <div className="flex items-center gap-2 pt-1 text-[10px] font-mono font-bold text-white/32 tracking-widest uppercase">
          <span>Finding {i + 1}/{total}</span>
          {f.section && <span className="truncate">/ {f.section}</span>}
          {elapsed && <span className="ml-auto text-white/38 normal-case tracking-normal">{elapsed}</span>}
        </div>
      </div>
    </motion.div>
  );
}

function AgentSummaryText({ text, sourceText }: { text: string; sourceText?: string }) {
  const [expanded, setExpanded] = useState(false);
  const cleaned = compactText(text || "", 220);
  const source = cleanFindingText(sourceText || "").trim();
  const hasSource = source && summaryFingerprint(source) !== summaryFingerprint(cleaned);
  if (!cleaned) return null;
  return (
    <div className="border-t border-white/[0.07] pt-3.5 space-y-2.5">
      <div className="flex items-center gap-2 text-[10px] font-mono font-black uppercase tracking-[0.22em] text-white/35">
        <ListChecks className="w-3.5 h-3.5 text-[var(--color-primary)]/70" />
        Agent Brief
      </div>
      <p className="text-[13px] text-white/76 leading-relaxed font-medium">
        {cleaned}
      </p>
      {hasSource && (
        <button
          type="button"
          onClick={() => setExpanded((e) => !e)}
          className="inline-flex items-center gap-1 text-[11px] font-mono font-bold text-[var(--color-primary)]/80 hover:text-[var(--color-primary)] transition-colors"
        >
          {expanded ? (
            <>
              <ChevronUp className="w-3.5 h-3.5" />
              <span>Hide source summary</span>
            </>
          ) : (
            <>
              <ChevronDown className="w-3.5 h-3.5" />
              <span>Show source summary</span>
            </>
          )}
        </button>
      )}
      {expanded && hasSource && (
        <p className="rounded-lg border border-white/[0.08] bg-black/15 px-3 py-2.5 text-[12px] leading-relaxed text-white/55">
          {source}
        </p>
      )}
    </div>
  );
}

function buildAgentBrief(completedData: AgentUpdate | undefined, findings: FindingPreview[], toolsRan: number): string {
  if (!completedData) return "";
  const verdict = normalizeVerdict(completedData.agent_verdict);
  const confidence = Math.round((completedData.confidence || 0) * 100);
  const alertFindings = findings.filter(isAlertFinding);
  const topFinding = findings[0];
  const topSignal = topFinding ? compactText(extractHeadline(topFinding), 120) : "";
  const toolText = toolsRan === 1 ? "1 tool check" : `${toolsRan} tool checks`;

  if (alertFindings.length > 0) {
    return `${verdict} at ${confidence}% confidence after ${toolText}. Highest-priority signal: ${topSignal || "review the flagged tool output below."}`;
  }

  if (findings.length > 0) {
    return `${verdict} at ${confidence}% confidence after ${toolText}. No high-severity tool signal surfaced; most relevant note: ${topSignal}`;
  }

  return `${verdict} at ${confidence}% confidence after ${toolText}. The backend did not return detailed tool findings for this specialist.`;
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
      // Skip stub/template findings entirely.
      if (!f.key_signal?.trim() && isTemplateSummary(summaryText)) continue;
      // Dedup on tool + verdict + severity + a normalised summary fingerprint,
      // so two emits of the same finding (re-runs, partial updates) collapse,
      // but a real shift (ELA NEGATIVE → ELA SUSPICIOUS) still surfaces.
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
  const toolsRan = completedData?.tools_ran || findings.length || 0;
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
      className={clsx(
        "relative flex flex-col overflow-hidden min-h-[520px] max-h-[860px] bg-surface-1 border border-border-muted rounded-2xl",
        (status === "waiting" || status === "queued") && "opacity-50"
      )}
      data-testid={`agent-card-${agentId}`}
    >
      {/* --- Card Header --- */}
      <div className="p-7 pb-5 border-b border-border-muted relative z-10 bg-surface-1">
        <div className="flex items-start justify-between mb-8">
          <div className="flex items-center gap-5">
            {/* Agent Icon */}
            <div className="relative w-16 h-16 flex items-center justify-center bg-surface-2 border border-border-muted rounded-xl">
              <Icon className={clsx("w-7 h-7 relative z-10", accent.textClass)} />
            </div>

            <div>
              <div className="flex items-center gap-2 mb-1.5">
                <h3 className="text-2xl font-heading font-bold text-white tracking-tight">{name}</h3>
                {completedData?.degraded && (
                  <motion.div
                    initial={{ scale: 0 }}
                    animate={{ scale: 1 }}
                    className="flex items-center gap-1.5 px-2 py-0.5 rounded bg-warning/10 border border-warning/30"
                    title={completedData.fallback_reason || "Analysis degraded"}
                  >
                    <AlertTriangle className="w-3.5 h-3.5 text-warning" />
                    <span className="text-[10px] font-mono font-bold text-warning tracking-widest">
                      Degraded
                    </span>
                  </motion.div>
                )}
              </div>
              <div className="flex items-center gap-2">
                <span className={clsx(
                  "px-3 py-1 rounded-md text-[11px] font-mono font-bold border",
                  (status === "complete" || status === "checking" || status === "running") ? "bg-[var(--color-primary)]/12 border-[var(--color-primary)]/40 text-[var(--color-primary)]" :
                  status === "error" ? "bg-danger/12 border-danger/40 text-danger" :
                  "bg-white/[0.06] border-white/15 text-white/55"
                )}>
                  {cfg.label}
                </span>
                <span className="text-[11px] font-mono font-semibold text-white/50 tracking-wider">
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
              <div className="relative w-full h-[4px] bg-surface-3 overflow-hidden">
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
              initial={{ opacity: 0, y: 10 }}
              animate={{ opacity: 1, y: 0 }}
              className="space-y-4"
            >
              <div className="flex items-end justify-between">
                <div>
                  <span className="text-[11px] font-mono font-bold text-white/45 tracking-widest block mb-1.5">Final Verdict</span>
                  <span className={clsx(
                    "text-2xl font-heading font-bold tracking-tight",
                    isAgentAlert ? "text-danger" : agentVerdict === "INCONCLUSIVE" ? "text-warning" : "text-success"
                  )}>
                    {normalizeVerdict(completedData.agent_verdict)}
                  </span>
                </div>
                <div className="text-right">
                  <span className="text-[11px] font-mono font-bold text-white/45 tracking-widest block mb-1.5">Confidence</span>
                  <span className="text-2xl font-mono font-bold text-white tabular-nums">
                    {Math.round(completedData.confidence * 100)}%
                  </span>
                </div>
              </div>
              <AgentSummaryText
                text={agentBrief}
                sourceText={completedData.summary || completedData.message || ""}
              />
            </motion.div>
          )}
        </AnimatePresence>
      </div>

      {/* --- Findings Surface --- */}
      <div className="flex-1 overflow-y-auto overflow-x-hidden custom-scrollbar scroll-smooth px-6 py-5 relative z-10">
        <AnimatePresence mode="wait">
          {status === "complete" && findings.length > 0 ? (
            <div className="space-y-3">
              {(isExpanded ? findings : findings.slice(0, 3)).map((f, i) => (
                <FindingRow key={`${f.tool}-${i}`} f={f} i={i} total={findings.length} />
              ))}

              {findings.length > 3 && (
                <button
                  type="button"
                  onClick={() => onToggleExpand?.()}
                  className={clsx(
                    "mt-3 w-full py-3.5 rounded-lg flex items-center justify-center gap-2",
                    "text-[12px] font-black tracking-wide",
                    "border transition-all duration-200 shadow-[inset_0_1px_0_rgba(255,255,255,0.04)]",
                    isExpanded
                      ? "bg-white/[0.04] border-white/15 text-white/65 hover:text-white hover:border-white/25"
                      : "bg-[var(--color-primary)]/12 border-[var(--color-primary)]/40 text-[var(--color-primary)] hover:bg-[var(--color-primary)]/18 hover:border-[var(--color-primary)]/60"
                  )}
                  aria-expanded={isExpanded}
                >
                  {isExpanded
                    ? <><ChevronUp className="w-4 h-4" /><span>Collapse to top 3 findings</span></>
                    : <><ChevronDown className="w-4 h-4" /><span>Show all {findings.length} tool findings ({findings.length - 3} hidden)</span></>
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
              <span className="text-[10px] font-mono tracking-widest text-white/25">
                Hidden after 10s
              </span>
            </div>
          ) : null}
        </AnimatePresence>
      </div>
    </motion.div>
  );
}
