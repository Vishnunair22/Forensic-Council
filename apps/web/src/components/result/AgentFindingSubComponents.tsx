"use client";

import {
 Clock,
 AlertTriangle,
 CheckCircle2,
 XCircle,
 MinusCircle,
} from "lucide-react";
import { clsx } from "clsx";
import { fmtTool } from "@/lib/fmtTool";
import { getToolIcon } from "@/lib/tool-icons";
import { cleanFindingText } from "@/lib/findingText";
import type { AgentFindingDTO } from "@/lib/api";

const HIDE_KEYS = new Set([
 "tool_name",
 "llm_reasoning",
 "llm_synthesis",
 "llm_refined_summary",
 "raw_tool_summary",
 "section_key_signal",
 "section_id",
 "section_label",
 "section_flag",
 "analysis_phase",
 "court_defensible",
 "evidence_verdict",
 "artifact_id",
 "session_id",
 "case_id",
 "degraded",
 "fallback_reason",
 "available",
 "severity_tier",
 "risk_level",
 "risk_tier",
 "analysis_summary",
 "summary",
 "notes",
 "rationale",
 "explanation",
]);

const METRIC_LABELS: Record<string, string> = {
 max_anomaly: "Peak Anomaly",
 num_anomaly_regions: "Anomaly Regions",
 avg_confidence: "OCR Confidence",
 confidence: "Confidence",
 word_count: "Word Count",
 page_count: "Pages",
 clone_probability: "Clone Prob",
 spoof_score: "Spoof Score",
 synthetic_probability: "Synthetic Prob",
 re_encoding_detected: "Re-encoded",
 manipulation_detected: "Manipulation",
 is_ai_generated: "AI Generated",
 splicing_detected: "Splicing",
 copy_move_detected: "Copy-Move",
 gan_artifact_detected: "GAN Artifact",
 diffusion_detected: "Diffusion Trace",
 method: "OCR Method",
 analysis_source: "Analysis Source",
 speaker_count: "Speaker Count",
 dominant_emotion: "Dominant Emotion",
 flagged_frames: "Flagged Frames",
 execution_time_ms: "Time",
};

interface Metric {
 label: string;
 value: string;
 numeric: number | null;
 emphasis: "danger" | "warn" | "ok" | "neutral";
}

function classifyMetric(key: string, raw: unknown): "danger" | "warn" | "ok" | "neutral" {
 if (typeof raw === "boolean") {
  const flaggers = /detect|manipulation|spoof|splic|copy[_-]?move|gan|synthetic|ai[_-]?generat|re[_-]?encod|diffusion|fake/i;
  if (flaggers.test(key)) return raw ? "danger" : "ok";
  return "neutral";
 }
 if (typeof raw === "number") {
  if (key.includes("probability") || key.includes("anomaly") || key.includes("spoof") || /score/i.test(key)) {
   if (raw >= 0.7) return "danger";
   if (raw >= 0.4) return "warn";
   return "ok";
  }
  if (/confidence/i.test(key)) {
   if (raw >= 0.75) return "ok";
   if (raw >= 0.5) return "warn";
   return "danger";
  }
 }
 return "neutral";
}

function metricHighlights(metadata: Record<string, unknown> | null | undefined): Metric[] {
 if (!metadata) return [];
 const items: Metric[] = [];

 for (const [key, value] of Object.entries(metadata)) {
  if (items.length >= 12) break;
  if (key.startsWith("_") || HIDE_KEYS.has(key)) continue;
  if (key === "execution_time_ms") continue;
  if (value === null || value === undefined || typeof value === "object") continue;

  const label = METRIC_LABELS[key] ?? key.replace(/_/g, " ").replace(/\b\w/g, (c) => c.toUpperCase());
  let text = "";
  let numeric: number | null = null;
  if (typeof value === "boolean") {
   text = value ? "Yes" : "No";
  } else if (typeof value === "number") {
   numeric = value;
   if (key.includes("probability") || key.includes("confidence") || key.includes("score") || key === "max_anomaly") {
    text = `${Math.round(value * 100)}%`;
   } else {
    text = Math.abs(value) < 1 ? value.toFixed(3) : String(Math.round(value * 100) / 100);
   }
  } else if (typeof value === "string" && value.length <= 140) {
   text = value;
  }
  if (text) items.push({ label, value: text, numeric, emphasis: classifyMetric(key, value) });
 }

 return items;
}

function escapeRegex(input: string): string {
 return input.replace(/[\\^$.*+?()[\]{}|]/g, "\\$&");
}

function stripToolNamePrefix(text: string, toolLabel: string): string {
 if (!text) return "";
 if (toolLabel) {
  const exact = new RegExp("^" + escapeRegex(toolLabel) + "\\s*:\\s*", "i");
  text = text.replace(exact, "");
 }
 return text.replace(/^(?:[A-Z][a-z]+\s+){1,5}[A-Z][a-z]+:\s+/, "");
}

const TEMPLATE_PATTERNS = [
 /^analysis complete\.?$/i,
 /^checked:?\s*$/i,
 /^no diagnostic output\.?$/i,
 /^[^.]{0,80}completed\.?$/i,
 /^[^.]{0,80}completed;\s*review detailed tool metrics\.?$/i,
 /^tool (?:execution )?(?:completed|finished)(?:\s+successfully)?\.?$/i,
 /^(?:check|scan|analysis|run)\s+(?:complete|completed|finished|ok)\.?$/i,
 /^no (?:issues?|anomal(?:y|ies))\s+(?:found|detected)\.?$/i,
];

function isTemplateText(text: string): boolean {
 const t = text.trim();
 if (!t) return true;
 if (t.length < 14) return true;
 return TEMPLATE_PATTERNS.some((re) => re.test(t));
}

export function deriveSummary(finding: AgentFindingDTO): string {
 const metadata = finding.metadata || {};
 const candidates = [
  metadata.llm_refined_summary,
  metadata.raw_tool_summary,
  metadata.analysis_summary,
  metadata.summary,
  finding.reasoning_summary,
 ]
  .map((v) => String(v || "").trim())
  .filter(Boolean);
 const picked = candidates.find((text) => !isTemplateText(text)) || "";
 if (picked) {
  const toolLabel = fmtTool((metadata.tool_name as string) || finding.finding_type);
  const stripped = stripToolNamePrefix(picked.replace(/^Checked:\s*/i, ""), toolLabel);
  return cleanFindingText(stripped);
 }

 const tool = fmtTool((metadata.tool_name as string) || finding.finding_type);
 const verdict = String(finding.evidence_verdict || "").toUpperCase();
 if (verdict === "POSITIVE") return `${tool} reported a manipulation signal — review the metrics below.`;
 if (verdict === "NEGATIVE") return `${tool} found no anomaly for its specific test.`;
 if (verdict === "ERROR") return `${tool} did not complete — treat as a coverage limitation.`;
 if (verdict === "NOT_APPLICABLE") return `${tool} is not applicable to this file type.`;
 return `${tool} returned an inconclusive result.`;
}

export function summaryRichness(finding: AgentFindingDTO): number {
 const summary = deriveSummary(finding);
 const metrics = metricHighlights(finding.metadata);
 const verdict = String(finding.evidence_verdict || "").toUpperCase();
 let score = 0;
 if (summary && summary.length > 30) score += 2;
 if (summary && summary.length > 90) score += 1;
 score += Math.min(metrics.length, 6);
 if (verdict === "POSITIVE") score += 2;
 if (verdict === "ERROR") score -= 1;
 const conf = finding.raw_confidence_score ?? finding.confidence_raw ?? 0;
 score += Math.round(conf * 2);
 return score;
}

function getStatus(finding: AgentFindingDTO) {
 const na = finding.metadata?.ela_not_applicable || finding.metadata?.ghost_not_applicable;
 const verdict = String(finding.evidence_verdict || "").toUpperCase();
 if (na || verdict === "NOT_APPLICABLE") return "na" as const;
 if (verdict === "ERROR" || finding.status === "ERROR") return "error" as const;
 if (verdict === "POSITIVE") return "flagged" as const;
 if (finding.status === "CONFIRMED" || verdict === "NEGATIVE") return "clean" as const;
 return "inconclusive" as const;
}

const STATUS_CONFIG = {
 flagged: {
  badge: "Flagged",
  badgeCls: "bg-warning/15 border-warning/35 text-warning",
  iconCls: "bg-warning/12 border-warning/30 text-warning",
  rowAccent: "border-l-warning/55",
 },
 clean: {
  badge: "Clean",
  badgeCls: "bg-primary/15 border-primary/30 text-primary",
  iconCls: "bg-primary/12 border-primary/25 text-primary",
  rowAccent: "border-l-primary/40",
 },
 error: {
  badge: "Error",
  badgeCls: "bg-danger/15 border-danger/35 text-danger",
  iconCls: "bg-danger/12 border-danger/30 text-danger",
  rowAccent: "border-l-danger/45",
 },
 na: {
  badge: "N/A",
  badgeCls: "bg-white/8 border-white/12 text-white/35",
  iconCls: "bg-white/8 border-white/10 text-white/30",
  rowAccent: "border-l-white/10",
 },
 inconclusive: {
  badge: "Inconclusive",
  badgeCls: "bg-white/10 border-white/15 text-white/55",
  iconCls: "bg-white/10 border-white/12 text-white/50",
  rowAccent: "border-l-white/20",
 },
};

const METRIC_EMPHASIS_CLS: Record<Metric["emphasis"], { wrap: string; label: string; value: string }> = {
 danger: {
  wrap: "bg-danger/12 border-danger/30",
  label: "text-danger/80",
  value: "text-danger",
 },
 warn: {
  wrap: "bg-warning/10 border-warning/25",
  label: "text-warning/80",
  value: "text-warning",
 },
 ok: {
  wrap: "bg-primary/10 border-primary/22",
  label: "text-primary/80",
  value: "text-primary",
 },
 neutral: {
  wrap: "bg-white/[0.05] border-white/[0.10]",
  label: "text-white/55",
  value: "text-white/85",
 },
};

// ─── Confidence Bar ──────────────────────────────────────────────────────────
export function ConfidenceBar({ value }: { value: number }) {
 const filled = Math.round(value * 5);
 const color = value >= 0.75 ? "bg-primary" : value >= 0.5 ? "bg-warning" : "bg-danger";
 const textColor = value >= 0.75 ? "text-primary" : value >= 0.5 ? "text-warning" : "text-danger";

 return (
  <div className="flex items-center gap-3">
   <div className="flex gap-1.5">
    {Array.from({ length: 5 }).map((_, i) => (
     <div
      key={i}
      className={clsx(
       "h-2 rounded-full transition-all duration-700",
       i < filled ? color : "bg-white/8",
       i < filled ? "w-8 shadow-[0_0_10px_rgba(var(--color-primary-rgb),0.45)]" : "w-2.5"
      )}
     />
    ))}
   </div>
   <span className={clsx("text-sm font-black font-mono tabular-nums", textColor)}>
    {Math.round(value * 100)}%
   </span>
  </div>
 );
}

// ─── Tool Row ────────────────────────────────────────────────────────────────
export function ToolRow({ finding, isLast }: { finding: AgentFindingDTO; isLast: boolean }) {
 const toolName = (finding.metadata?.tool_name as string) || finding.finding_type;
 const status = getStatus(finding);
 const cfg = STATUS_CONFIG[status];
 const Icon = getToolIcon(toolName);
 const timingMs = (finding.metadata?.execution_time_ms as number) || null;
 const confidence = finding.raw_confidence_score ?? 0;
 const metrics = metricHighlights(finding.metadata);
 const summary = deriveSummary(finding);
 const isDegraded = !!(finding.metadata?.degraded || finding.metadata?.fallback_reason);
 const isIncomplete = finding.status === "INCOMPLETE";

 return (
  <div
   className={clsx(
    "group transition-colors px-5 py-5 space-y-3.5 border-l-2",
    cfg.rowAccent,
    !isLast && "border-b border-white/[0.06]",
   )}
  >
   {/* Header row */}
   <div className="flex items-start gap-3.5">
    <div className={clsx("w-10 h-10 rounded-xl flex items-center justify-center shrink-0 border", cfg.iconCls)}>
     <Icon className="w-[18px] h-[18px]" />
    </div>

    <div className="flex-1 min-w-0">
     <div className="flex items-center gap-2 flex-wrap">
      <span className="text-[15px] font-bold text-white truncate">
       {fmtTool(toolName)}
      </span>
      {isDegraded && (
       <span className="text-[10px] font-black tracking-wide text-white/55 border border-white/20 rounded px-1.5 py-0.5 shrink-0">
        DEGRADED
       </span>
      )}
      {isIncomplete && (
       <span className="flex items-center gap-1 text-[10px] font-black tracking-wide text-warning border border-warning/35 bg-warning/12 rounded px-1.5 py-0.5 shrink-0">
        <AlertTriangle className="w-3 h-3" /> INCOMPLETE
       </span>
      )}
     </div>
    </div>

    <div className="flex items-center gap-3 shrink-0">
     {timingMs && (
      <span className="hidden sm:flex items-center gap-1 text-[12px] font-mono text-white/45">
       <Clock className="w-3.5 h-3.5" />{timingMs >= 1000 ? `${(timingMs / 1000).toFixed(1)}s` : `${timingMs}ms`}
      </span>
     )}
     <span className={clsx("px-2.5 py-1 rounded-full border text-[11px] font-black tracking-wide", cfg.badgeCls)}>
      {cfg.badge}
     </span>
     {status !== "na" && (
      <span className={clsx(
       "text-[13px] font-black font-mono w-11 text-right tabular-nums",
       confidence >= 0.75 ? "text-primary" : confidence >= 0.5 ? "text-warning" : "text-danger"
      )}>
       {Math.round(confidence * 100)}%
      </span>
     )}
    </div>
   </div>

   {/* Summary */}
   {summary && status !== "na" && (
    <p className="text-[14px] text-white/80 leading-relaxed font-medium pl-[54px]">
     {summary}
    </p>
   )}

   {/* Metric chips */}
   {metrics.length > 0 && (
    <div className="pl-[54px] grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-4 gap-2">
     {metrics.map((m) => {
      const cls = METRIC_EMPHASIS_CLS[m.emphasis];
      return (
       <div
        key={`${toolName}-${m.label}`}
        className={clsx(
         "flex flex-col gap-0.5 px-3 py-2 rounded-lg border min-w-0",
         cls.wrap,
        )}
       >
        <span className={clsx("text-[10px] font-black tracking-wide uppercase truncate", cls.label)}>
         {m.label}
        </span>
        <span className={clsx("text-[14px] font-mono font-bold truncate", cls.value)}>
         {m.value}
        </span>
       </div>
      );
     })}
    </div>
   )}

   {/* Status context */}
   {status === "na" && (
    <div className="pl-[54px] flex items-center gap-2 text-[13px] text-white/50 font-medium">
     <MinusCircle className="w-4 h-4 shrink-0" />
     Not applicable to this file type — excluded from analysis.
    </div>
   )}
   {status === "error" && (
    <div className="pl-[54px] flex items-center gap-2 text-[13px] text-danger/85 font-semibold">
     <XCircle className="w-4 h-4 shrink-0" />
     Tool error — counts as a coverage gap, not a manipulation signal.
    </div>
   )}
   {status === "flagged" && (
    <div className="pl-[54px] flex items-center gap-2 text-[13px] text-warning/90 font-medium">
     <AlertTriangle className="w-4 h-4 shrink-0" />
     Active signal — weigh with other tools before concluding.
    </div>
   )}
   {status === "clean" && (
    <div className="pl-[54px] flex items-center gap-2 text-[13px] text-primary/75 font-medium">
     <CheckCircle2 className="w-4 h-4 shrink-0" />
     Supports absence of this specific manipulation pattern.
    </div>
   )}
  </div>
 );
}
