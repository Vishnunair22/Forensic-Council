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
  ListChecks,
  CheckCircle2,
  HelpCircle,
  ShieldAlert,
  type LucideIcon,
} from "lucide-react";
import { clsx } from "clsx";
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
}

const statusConfig = {
  waiting:     { color: "fc-text-muted",   label: "Waiting"   },
  queued:      { color: "fc-text-muted",   label: "Queued"    },
  checking:    { color: "text-primary",    label: "Syncing"   },
  running:     { color: "text-primary",    label: "Scanning"  },
  complete:    { color: "text-success",    label: "Verified"  },
  error:       { color: "fc-text-danger",  label: "Error"     },
  unsupported: { color: "fc-text-muted",   label: "Skipped"   },
  validating:  { color: "text-primary",    label: "Verifying" },
};

// Verdict tiers for cross-checking a brief's stated assessment against the card's
// authoritative verdict. A later arbiter grounding pass can elevate the verdict
// after the brief was written, leaving a stale claim ("assessed as suspicious")
// beside a higher card verdict ("Manipulated"). Strip such contradicting sentences.
const VERDICT_TIER: Record<string, number> = {
  authentic: 0, clean: 0, genuine: 0, unmodified: 0, pristine: 0, negative: 0,
  inconclusive: 1,
  suspicious: 2,
  manipulated: 3, tampered: 3, fabricated: 3, fake: 3, synthetic: 3,
  deepfake: 3, forged: 3,
};

function verdictTier(verdict?: string | null): number | null {
  const s = (verdict || "").toLowerCase();
  for (const k of Object.keys(VERDICT_TIER)) {
    if (s.includes(k)) return VERDICT_TIER[k];
  }
  return null;
}

function stripContradictingVerdictClaims(text: string, verdict?: string | null): string {
  const actual = verdictTier(verdict);
  if (actual == null || !text) return text;
  const sentences = text.split(/(?<=[.!?])\s+/);
  const kept = sentences.filter((s) => {
    const m = s.toLowerCase().match(
      /(?:assessed as|deemed|classified as|rated|evidence is|appears to be)\s+(?:likely\s+|an?\s+|to be\s+)?(authentic|clean|genuine|unmodified|pristine|inconclusive|suspicious|manipulated|tampered|fabricated|fake|synthetic|deepfake|forged)/,
    );
    if (!m) return true;
    const t = VERDICT_TIER[m[1]];
    return t == null || t === actual;
  });
  return kept.join(" ").trim();
}

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
// Tools that produce meaningless or misleading findings on screenshots —
// all are camera-physics-based and assume a photographic sensor chain.
const SCREENSHOT_CAMERA_TOOLS = new Set([
  "noiseprint_cluster",
  "noise_fingerprint",
  "prnu_analysis",
  "prnu_sensor_verification",
  "neural_ela",
  "ela_full_image",
  "jpeg_ghost_detect",
  "frequency_domain_analysis",
  "deepfake_frequency_check",
  "neural_splicing",
  "splicing_detect",
  "neural_copy_move",
  "copy_move_detect",
  "adversarial_robustness_check",
  "camera_profile_match",
  "roi_extract",
]);

// Match any label that describes a screen-rendered or UI-generated image.
// Agent1's CLIP/visual-profile tool can return many variants of these concepts.
const SCREENSHOT_TOKENS = [
  "screenshot",
  "screen capture",
  "screen shot",
  "screengrab",
  "digital ui",
  "browser",
  "web page",
  "webpage",
  "website",
  "whatsapp",
  "telegram",
  "app interface",
  "mobile app",
  "application interface",
  "application screenshot",
  "social media",
  "chat interface",
  "news article",
  "ui mockup",
  "user interface",
  "desktop",
  "document screenshot",
  "rendered image",
  "screen recording",
];

function isScreenshotContext(text?: string | null) {
  const lower = String(text || "").toLowerCase();
  return SCREENSHOT_TOKENS.some((token) => lower.includes(token));
}

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

function KeyFindingItem({ f, i }: { f: FindingPreview; i: number }) {
  const prefersReduced = useReducedMotion();
  const isAlert = isAlertFinding(f);
  const isCritical = (f.severity || "").toUpperCase() === "CRITICAL";
  const isHigh = (f.severity || "").toUpperCase() === "HIGH";
  const isDiscovery = f.finding_kind === "discovery";
  const isNeedsReview = f.verdict === "NEEDS_REVIEW";

  const text = (() => {
    const sig = cleanFindingText(f.key_signal || "").trim();
    const sum = cleanFindingText(f.summary || "").trim();
    if (!sig && !sum) return null;
    if (sig && sum && sum.toLowerCase().includes(sig.toLowerCase().slice(0, 40))) return sum;
    if (sig && sum) return sum.length >= sig.length ? sum : sig;
    return sum || sig;
  })();

  if (!text) return null;

  const dotClass = (isCritical || isHigh)
    ? "bg-danger"
    : isAlert
    ? "bg-warning"
    : isNeedsReview
    ? "bg-warning/60"
    : isDiscovery
    ? "bg-primary"
    : "bg-white/20";

  return (
    <motion.li
      initial={prefersReduced ? false : { opacity: 0, x: -4 }}
      animate={{ opacity: 1, x: 0 }}
      transition={{ delay: prefersReduced ? 0 : i * 0.04, duration: 0.14 }}
      className="flex items-start gap-2.5"
    >
      <span
        className={`mt-1.5 w-1.5 h-1.5 rounded-full shrink-0 ${dotClass}`}
        aria-hidden="true"
      />
      <span className={clsx(
        "text-sm leading-relaxed",
        (isCritical || isHigh) ? "fc-text-primary" : "fc-text-secondary"
      )}>
        {text}
        {f.degraded && (
          <span className="ml-1.5 text-xs fc-text-muted font-mono">(fallback)</span>
        )}
      </span>
    </motion.li>
  );
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

interface AgentBriefProps {
  completedData: AgentUpdate;
  findings: FindingPreview[];
  toolsRan: number;
  imageContext?: string | null;
}

function AgentBrief({ completedData, findings, toolsRan, imageContext }: AgentBriefProps) {
  const _prefersReduced = useReducedMotion();
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
  // Drop any brief sentence whose stated assessment tier contradicts the card's
  // authoritative verdict (e.g. a stale "assessed as suspicious" left by an
  // earlier synthesis after grounding elevated the verdict to Manipulated).
  synthSummary = stripContradictingVerdictClaims(synthSummary, verdict);
  const isAlert = ALERT_VERDICTS.has(verdict) || (completedData.verdict_score ?? 0) > 0.6;
  const isInconclusive = verdict === "INCONCLUSIVE";
  const isClean = verdict === "AUTHENTIC" || verdict === "CLEAN" || verdict === "NEGATIVE";

  // ── Part A: What the agent understood this file to be ──────────────────
  const fileIdentityLine = (() => {
    const raw = (imageContext || "").trim();
    if (!raw || raw.toLowerCase() === "unknown") return null;
    const normalised = raw.charAt(0).toUpperCase() + raw.slice(1);
    return normalised.endsWith(".") ? normalised : `${normalised}.`;
  })();

  // ── Part B: What the agent concluded ──────────────────────────────────
  const outcomeText = (() => {
    if (synthSummary && !isTemplateSummary(synthSummary)) return synthSummary;

    const FLAG_RANK: Record<string, number> = { bad: 0, warn: 1, ok: 2, info: 3 };
    const sections = [...(completedData.section_flags ?? [])].sort(
      (a, b) => (FLAG_RANK[a.flag] ?? 4) - (FLAG_RANK[b.flag] ?? 4),
    );
    for (const sec of sections) {
      const s = cleanFindingText(sec.key_signal || "").trim();
      if (s && !isTemplateSummary(s)) return s;
    }
    for (const f of findings) {
      const s = cleanFindingText(f.key_signal || "").trim();
      if (s && !isTemplateSummary(s)) return s;
    }

    const conf = Math.round(completedData.confidence * 100);
    const n = completedData.tools_ran ?? findings.length;
    const alertCount = findings.filter(isAlertFinding).length;

    if (isAlert) {
      if (alertCount > 0) {
        return `${alertCount} anomal${alertCount === 1 ? "y" : "ies"} flagged across ${n} forensic check${n !== 1 ? "s" : ""} (${conf}% confidence).`;
      }
      // Alert verdict but no discrete tool-level alert in this phase's set — the
      // signal is holistic or carried from an earlier phase, not from these
      // checks. Don't claim anomalies the listed checks did not find.
      return `Flagged for review on the holistic assessment; the ${n} tool-level check${n !== 1 ? "s" : ""} here isolated no new discrete signal (${conf}% confidence).`;
    }
    if (isClean) {
      if (isScreenshotContext(imageContext)) {
        return `Screenshot-specific checks completed cleanly across ${n} applicable tool${n !== 1 ? "s" : ""}: UI layout, visible text, hash custody, and provenance signals found no supported manipulation indicator (${conf}% confidence).`;
      }
      return `${n} applicable forensic check${n !== 1 ? "s" : ""} completed cleanly with no supported manipulation indicator (${conf}% confidence).`;
    }
    if (isInconclusive) {
      return `Analysis of ${n} forensic check${n !== 1 ? "s" : ""} is inconclusive (${conf}% confidence). Some signals are ambiguous or limited by available data.`;
    }
    return `${n} forensic check${n !== 1 ? "s" : ""} completed (${conf}% confidence).`;
  })();

  const failedCount = completedData.tools_failed ?? 0;

  const outcomeStyle = isAlert
    ? "bg-danger/[0.04] border-danger/20 text-danger-light"
    : isInconclusive
    ? "bg-warning/[0.04] border-warning/20 text-warning-light"
    : isClean
    ? "bg-success/[0.04] border-success/20 text-success-light"
    : "bg-white/[0.01] border-white/5 fc-text-primary";

  const iconColor = isAlert ? "text-danger"
    : isInconclusive ? "text-warning"
    : isClean ? "text-success"
    : "text-primary";

  const StatusIcon = isAlert ? ShieldAlert
    : isInconclusive ? HelpCircle
    : isClean ? CheckCircle2
    : ListChecks;

  return (
    <div className="border-t border-white/[0.07] pt-4 mt-3 space-y-3">
      {/* Visual Context — the agent's visual axis (Agent1 integrity, Agent3
          object/scene, Agent5 metadata), sourced from the shared visual context. */}
      {fileIdentityLine && (
        <div className="space-y-1">
          <span className="fc-eyebrow fc-text-muted block">Visual Context</span>
          <p className="text-xs fc-text-secondary leading-relaxed">
            {fileIdentityLine}
          </p>
        </div>
      )}

      {/* Agent Overview — the tools that ran and the verdict arrived. */}
      <div className="space-y-1">
        <span className="fc-eyebrow fc-text-muted block">Agent Overview</span>
        <div className="flex items-start gap-2">
          <StatusIcon className={`w-3.5 h-3.5 mt-0.5 shrink-0 ${iconColor}`} />
          <div className="flex-1 space-y-1">
          <div className={`text-sm leading-relaxed border px-3 py-2.5 rounded-xl ${outcomeStyle}`}>
            {outcomeText}
          </div>
          {(toolsRan > 0 || failedCount > 0) && (
            <div className="flex items-center gap-1.5 text-xs font-mono fc-text-muted px-0.5">
              <span>{toolsRan} tool{toolsRan !== 1 ? "s" : ""} ran</span>
              {failedCount > 0 && (
                <>
                  <span>·</span>
                  <span className="text-warning">{failedCount} degraded</span>
                </>
              )}
            </div>
          )}
          </div>
        </div>
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

  // Debounced thinking text — prevents AnimatePresence from firing exit/enter
  // on every rapid backend message. 80ms matches the LoadingOverlay debounce.
  const [debouncedThinking, setDebouncedThinking] = React.useState(() =>
    sanitizeThinking(liveUpdate?.thinking || thinking)
  );
  const thinkingDebounceRef = React.useRef<ReturnType<typeof setTimeout> | null>(null);
  React.useEffect(() => {
    const raw = sanitizeThinking(liveUpdate?.thinking || thinking);
    if (thinkingDebounceRef.current) clearTimeout(thinkingDebounceRef.current);
    thinkingDebounceRef.current = setTimeout(() => setDebouncedThinking(raw), 80);
    return () => {
      if (thinkingDebounceRef.current) clearTimeout(thinkingDebounceRef.current);
    };
  }, [liveUpdate?.thinking, thinking]);

  // Phrase interval: only resets when status or agentId changes, NOT on every
  // thinking update. Previously liveUpdate?.thinking was in the dep array which
  // restarted the 3.5s timer on every backend message — phrases never cycled.
  React.useEffect(() => {
    if (status !== "running") {
      setFallbackPhraseIndex(0);
      return;
    }
    const phraseInterval = setInterval(() => {
      setFallbackPhraseIndex(prev => (prev + 1) % (FALLBACK_PHRASES[agentId]?.length || 5));
    }, 3500);
    return () => clearInterval(phraseInterval);
  }, [status, agentId]);

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
      const screenshotContext = isScreenshotContext(completedData?.image_context);
      const deduped: FindingPreview[] = [];
      const seen = new Set<string>();
      for (const f of raw) {
        if (!f) continue;
        const rawSummary = typeof f.summary === "string" ? f.summary : (f.summary ? String(f.summary) : "");
        const rawKeySignal = typeof f.key_signal === "string" ? f.key_signal : (f.key_signal ? String(f.key_signal) : "");
        const rawVerdict = typeof f.verdict === "string" ? f.verdict : (f.verdict ? String(f.verdict) : "");
        const rawSeverity = typeof f.severity === "string" ? f.severity : (f.severity ? String(f.severity) : "");
        const rawTool = typeof f.tool === "string" ? f.tool : (f.tool ? String(f.tool) : "");
        if (screenshotContext && SCREENSHOT_CAMERA_TOOLS.has(rawTool.toLowerCase())) continue;

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
  const backendKnowsTotal = typeof liveUpdate?.tools_total === "number";
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
        "relative flex flex-col overflow-hidden transition-all duration-[160ms] fc-surface-quiet",
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
                    : (backendKnowsTotal && Math.max(liveTotal, currentToolIndex, 1) > 1
                        ? `${progressDescriptor.label} ${currentToolIndex}/${Math.max(liveTotal, currentToolIndex, 1)}`
                        : progressDescriptor.label
                      )}
                  <motion.span
                    animate={prefersReduced ? undefined : { opacity: [1, 0] }}
                    transition={prefersReduced ? undefined : { duration: 0.5, repeat: Infinity, repeatType: "reverse" }}
                    className="ml-1 inline-block w-1.5 h-3 bg-primary"
                  />
                </span>
              </div>

              {/* Cyber-Tactical Progress Bar */}
              <div className="relative w-full h-2 bg-white/[0.06] rounded-full overflow-hidden border border-white/10">
                {/* Segmented hash marks background */}
                <div className="absolute inset-0 bg-[url('data:image/svg+xml;base64,PHN2ZyB3aWR0aD0iNCIgaGVpZ2h0PSI0IiB4bWxucz0iaHR0cDovL3d3dy53My5vcmcvMjAwMC9zdmciPjxyZWN0IHdpZHRoPSIxIiBoZWlnaHQ9IjQiIGZpbGw9InJnYmEoMjU1LDI1NSwyNTUsMC4wNSkiLz48L3N2Zz4=')] opacity-50" />

                <motion.div
                  className="absolute top-0 bottom-0 bg-primary rounded-full relative overflow-hidden"
                  animate={{
                    width: status === "checking" ? "100%" : `${(currentToolIndex / liveTotal) * 100}%`,
                  }}
                  transition={{ duration: 0.3, ease: "easeOut" }}
                >
                  {/* Infinite Light Sweep effect — suppressed under reduced-motion */}
                  {!prefersReduced && (
                    <motion.div
                      className="absolute top-0 bottom-0 left-0 w-full bg-gradient-to-r from-transparent via-white/40 to-transparent"
                      animate={{ x: ["-100%", "200%"] }}
                      transition={{ duration: 1.5, repeat: Infinity, ease: "linear" }}
                    />
                  )}
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
                 imageContext={completedData.image_context}
               />
            </motion.div>
          )}
        </AnimatePresence>
      </div>

      {/* --- Findings Surface --- */}
      <div className="px-7 pb-6 pt-0 relative z-10">
        <AnimatePresence mode="wait">
          {status === "complete" && findings.length > 0 ? (
            <motion.div
              initial={prefersReduced ? false : { opacity: 0 }}
              animate={{ opacity: 1 }}
              transition={{ duration: 0.16, delay: 0.05 }}
            >
              {/* Header row */}
              <div className="flex items-center justify-between mb-3 px-0.5 border-t border-white/[0.06] pt-4">
                <span className="fc-eyebrow fc-text-muted">
                  Key Findings
                </span>
                {completedData && typeof completedData.tools_failed === "number" && completedData.tools_failed > 0 && (
                  <span className="fc-badge fc-badge-warning">
                    {completedData.tools_failed} degraded
                  </span>
                )}
              </div>

              {/* Finding list — always fully open */}
              <ul className="space-y-2.5" aria-label="Key findings">
                {findings.map((f, i) => (
                  <KeyFindingItem key={`${f.tool}-${i}`} f={f} i={i} />
                ))}
              </ul>
            </motion.div>
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
                  key={debouncedThinking || FALLBACK_PHRASES[agentId]?.[fallbackPhraseIndex] || (status === "validating" ? "Verifying chain of custody..." : "Processing evidence...")}
                  initial={prefersReduced ? false : { opacity: 0, y: 4 }}
                  animate={{ opacity: 1, y: 0 }}
                  exit={prefersReduced ? {} : { opacity: 0, transition: { duration: 0.1 } }}
                  transition={{ duration: 0.16 }}
                  className="max-w-[280px] text-sm fc-text-muted font-normal leading-relaxed"
                >
                  {debouncedThinking || FALLBACK_PHRASES[agentId]?.[fallbackPhraseIndex] || (status === "validating" ? "Verifying chain of custody..." : "Processing evidence...")}
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
            </div>
          ) : null}
        </AnimatePresence>
      </div>
    </motion.div>
  );
}
