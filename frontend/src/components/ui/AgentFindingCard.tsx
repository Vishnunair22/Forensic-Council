"use client";

import React, { useState, useMemo } from "react";
import {
  ChevronDown,
  Shield, Eye, Search, Database, Layers, Activity, Cpu,
  Hash, Zap, ImageIcon, Scan, FileSearch, Fingerprint,
  Wifi, Globe, Binary, Crosshair, Gauge, Brain,
  Clock, AlertTriangle, CheckCircle2, XCircle, Minus,
} from "lucide-react";
import clsx from "clsx";
import { SurfaceCard } from "./SurfaceCard";
import { Badge } from "@/components/lightswind/badge";
import { fmtTool } from "@/lib/fmtTool";
import { AgentFindingDTO, AgentMetricsDTO } from "@/lib/api";

// ─── Tool icon map ────────────────────────────────────────────────────────────
const TOOL_ICONS: Record<string, React.ElementType> = {
  ela_full_image: ImageIcon,
  ela_anomaly_classify: Scan,
  jpeg_ghost_detect: Eye,
  frequency_domain_analysis: Activity,
  deepfake_frequency_check: Brain,
  perceptual_hash: Hash,
  file_hash_verify: Fingerprint,
  analyze_image_content: Eye,
  extract_text_from_image: FileSearch,
  extract_evidence_text: FileSearch,
  noise_fingerprint: Gauge,
  copy_move_detect: Crosshair,
  splicing_detect: Layers,
  adversarial_robustness_check: Shield,
  sensor_db_query: Database,
  prnu_analysis: Fingerprint,
  cfa_demosaicing: Scan,
  gemini_deep_forensic: Brain,
  object_detection: Search,
  secondary_classification: Cpu,
  scale_validation: Gauge,
  lighting_consistency: Zap,
  scene_incongruence: Eye,
  contraband_database: Database,
  object_text_ocr: FileSearch,
  document_authenticity: FileSearch,
  image_splice_check: Layers,
  inter_agent_call: Wifi,
  exif_extract: Hash,
  metadata_anomaly_score: Brain,
  gps_timezone_validate: Globe,
  steganography_scan: Binary,
  file_structure_analysis: Layers,
  hex_signature_scan: Binary,
  timestamp_analysis: Clock,
  astronomical_api: Globe,
  reverse_image_search: Search,
  device_fingerprint_db: Fingerprint,
  c2pa_verify: Shield,
  thumbnail_mismatch: ImageIcon,
  extract_deep_metadata: Hash,
  get_physical_address: Globe,
  mediainfo_profile: Activity,
  av_file_identity: Activity,
};

function getToolIcon(toolName: string) {
  return TOOL_ICONS[toolName] || Cpu;
}

// ─── Agent meta ───────────────────────────────────────────────────────────────
const AGENT_META: Record<string, {
  name: string;
  role: string;
  accentColor: string;
  accentBg: string;
  accentBorder: string;
  verdictColor: string;
  icon: React.ElementType;
}> = {
  Agent1: {
    name: "Agent 1",
    role: "Image Integrity",
    accentColor: "text-cyan-400",
    accentBg: "bg-cyan-500/10",
    accentBorder: "border-cyan-500/30",
    verdictColor: "text-cyan-300",
    icon: Shield,
  },
  Agent3: {
    name: "Agent 3",
    role: "Object & Weapon Analysis",
    accentColor: "text-amber-400",
    accentBg: "bg-amber-500/10",
    accentBorder: "border-amber-500/30",
    verdictColor: "text-amber-300",
    icon: Crosshair,
  },
  Agent5: {
    name: "Agent 5",
    role: "Metadata & Context",
    accentColor: "text-violet-400",
    accentBg: "bg-violet-500/10",
    accentBorder: "border-violet-500/30",
    verdictColor: "text-violet-300",
    icon: Database,
  },
};

// ─── Verdict display text ─────────────────────────────────────────────────────
function getVerdictDisplay(verdict: string): { label: string; color: string } {
  switch (verdict) {
    case "NO ANOMALIES":      return { label: "Authentic",             color: "text-emerald-400" };
    case "ANOMALIES DETECTED": return { label: "Manipulation Detected", color: "text-rose-400"    };
    case "ANALYSIS FAILED":   return { label: "Analysis Failed",       color: "text-rose-500"    };
    case "NOT APPLICABLE":    return { label: "Not Applicable",        color: "text-slate-400"   };
    default:                  return { label: verdict,                 color: "text-foreground/60" };
  }
}

// ─── Status badge (operational state) ────────────────────────────────────────
function deriveStatus(
  isSkipped: boolean,
  allFailed: boolean,
  hasErrors: boolean,
): { label: string; variant: "success" | "destructive" | "secondary" | "warning" } {
  if (isSkipped)  return { label: "Skipped",  variant: "secondary"   };
  if (allFailed)  return { label: "Failed",   variant: "destructive" };
  if (hasErrors)  return { label: "Partial",  variant: "warning"     };
  return               { label: "Finished",  variant: "success"     };
}

// ─── Finding status helpers ───────────────────────────────────────────────────
function getFindingStatus(f: AgentFindingDTO): "success" | "warning" | "error" | "na" {
  const na = f.metadata?.ela_not_applicable
    || f.metadata?.ghost_not_applicable
    || f.metadata?.noise_fingerprint_not_applicable
    || f.metadata?.prnu_not_applicable;
  if (na) return "na";
  if (f.status === "CONFIRMED" || f.status === "CONFIRMED_CLEAN") return "success";
  if (f.status === "ERROR" || f.metadata?.court_defensible === false) return "error";
  return "warning";
}

function toolBadgeConfig(status: "success" | "warning" | "error" | "na") {
  switch (status) {
    case "success": return { variant: "success"     as const, label: "Clean"   };
    case "warning": return { variant: "warning"     as const, label: "Flagged" };
    case "error":   return { variant: "destructive" as const, label: "Failed"  };
    case "na":      return { variant: "secondary"   as const, label: "N/A"     };
  }
}

function confColor(c: number): string {
  return c >= 0.75 ? "text-emerald-400" : c >= 0.5 ? "text-amber-400" : "text-rose-400";
}

// ─── Confidence bar (5 segments) ─────────────────────────────────────────────
function ConfidenceBar({ value, accentColor }: { value: number; accentColor: string }) {
  const filled = Math.round(value * 5); // 0–5 segments
  const color = value >= 0.75
    ? "bg-emerald-400"
    : value >= 0.5
      ? "bg-amber-400"
      : "bg-rose-400";

  return (
    <div className="flex items-center gap-1.5">
      <div className="flex gap-[3px]">
        {Array.from({ length: 5 }).map((_, i) => (
          <div
            key={i}
            className={clsx(
              "h-[6px] rounded-full transition-all duration-300",
              i < filled ? color : "bg-white/10",
              i < filled ? "w-5" : "w-3",
            )}
          />
        ))}
      </div>
      <span className={clsx("text-[11px] font-black font-mono tabular-nums", confColor(value))}>
        {Math.round(value * 100)}%
      </span>
    </div>
  );
}

// ─── Extract tool timing ──────────────────────────────────────────────────────
function extractTimingMs(f: AgentFindingDTO): number | null {
  const m = f.metadata || {};
  if (typeof m.execution_time_ms === "number") return m.execution_time_ms as number;
  if (typeof m.tool_duration_ms  === "number") return m.tool_duration_ms  as number;
  return null;
}

function fmtMs(ms: number): string {
  return ms >= 1000 ? `${(ms / 1000).toFixed(1)}s` : `${Math.round(ms)}ms`;
}

// ─── Phase badge ──────────────────────────────────────────────────────────────
function PhaseBadge({ phase }: { phase: "initial" | "deep" }) {
  if (phase === "deep") {
    return (
      <Badge variant="info" className="font-mono font-bold uppercase tracking-widest text-[8px] px-1.5 py-0">
        DEEP
      </Badge>
    );
  }
  return (
    <Badge variant="success" withDot className="font-mono font-bold uppercase tracking-widest text-[8px] px-1.5 py-0">
      INITIAL
    </Badge>
  );
}

// ─── Expandable text ──────────────────────────────────────────────────────────
function ExpandableText({ text, maxLen = 180 }: { text: string; maxLen?: number }) {
  const [expanded, setExpanded] = useState(false);
  if (!text) return null;
  const isLong = text.length > maxLen;
  return (
    <div>
      <p className={clsx(
        "text-[11px] text-foreground/65 leading-relaxed",
        !expanded && isLong && "line-clamp-2"
      )}>
        {text}
      </p>
      {isLong && (
        <button
          onClick={(e) => { e.stopPropagation(); setExpanded(v => !v); }}
          className="text-[9px] font-mono font-bold text-amber-500/60 hover:text-amber-400 uppercase tracking-widest mt-1 cursor-pointer transition-colors"
          aria-expanded={expanded}
        >
          {expanded ? "Show Less ↑" : "Show More ↓"}
        </button>
      )}
    </div>
  );
}

// ─── Tool row ─────────────────────────────────────────────────────────────────
const VISIBLE_TOOLS_THRESHOLD = 3;

function ToolRow({
  finding,
  isLast,
  defaultExpanded = false,
}: {
  finding: AgentFindingDTO;
  isLast: boolean;
  defaultExpanded?: boolean;
}) {
  const [expanded, setExpanded] = useState(defaultExpanded);
  const toolName  = (finding.metadata?.tool_name as string) || finding.finding_type;
  const status    = getFindingStatus(finding);
  const badgeCfg  = toolBadgeConfig(status);
  const Icon      = getToolIcon(toolName);
  // Use reasoning_summary — already human-readable from _build_readable_summary()
  const summary   = finding.reasoning_summary || "Analysis completed.";
  const timingMs  = extractTimingMs(finding);
  const confidence = finding.raw_confidence_score ?? finding.calibrated_probability ?? finding.confidence_raw ?? 0;
  const isNa      = status === "na";

  const iconColor = isNa
    ? "bg-slate-800/40 border-slate-700/30 text-slate-500"
    : status === "success"
      ? "bg-emerald-500/10 border-emerald-500/20 text-emerald-400"
      : status === "warning"
        ? "bg-amber-500/10 border-amber-500/20 text-amber-400"
        : "bg-rose-500/10 border-rose-500/20 text-rose-400";

  return (
    <div className={clsx(!isLast && "border-b border-border-subtle/40")}>
      {/* ── Row header ── */}
      <button
        onClick={() => setExpanded(v => !v)}
        aria-expanded={expanded}
        className={clsx(
          "w-full flex items-center gap-3 px-4 py-3 text-left transition-colors cursor-pointer",
          expanded ? "bg-white/[0.025]" : "hover:bg-white/[0.015]"
        )}
      >
        {/* Tool icon */}
        <div className={clsx("w-8 h-8 rounded-lg flex items-center justify-center shrink-0 border", iconColor)}>
          <Icon className="w-4 h-4" />
        </div>

        {/* Tool name */}
        <span className="flex-1 text-[11px] font-bold uppercase tracking-wider text-foreground min-w-0 truncate">
          {fmtTool(toolName)}
        </span>

        {/* Timing */}
        {timingMs !== null && (
          <span className="flex items-center gap-1 text-[10px] font-mono text-foreground/30 shrink-0">
            <Clock className="w-3 h-3" />
            {fmtMs(timingMs)}
          </span>
        )}

        {/* Status badge */}
        <Badge
          variant={badgeCfg.variant}
          className="font-mono font-bold uppercase tracking-widest text-[8px] px-1.5 py-0 shrink-0"
        >
          {badgeCfg.label}
        </Badge>

        {/* Confidence */}
        {!isNa && (
          <span className={clsx("text-xs font-bold font-mono tabular-nums shrink-0 w-10 text-right", confColor(confidence))}>
            {Math.round(confidence * 100)}%
          </span>
        )}

        {/* Chevron */}
        <div className={clsx(
          "p-1 rounded transition-all duration-200 shrink-0",
          expanded ? "rotate-180 bg-white/5" : ""
        )}>
          <ChevronDown className="w-3 h-3 text-foreground/30" />
        </div>
      </button>

      {/* ── Expanded analysis ── */}
      {expanded && (
        <div className="px-4 pb-4 pl-[3.75rem]">
          <div className="rounded-xl bg-black/25 border border-border-subtle/40 p-4 space-y-2">
            <p className="text-[9px] font-mono font-bold uppercase tracking-widest text-foreground/30 mb-2">
              Analysis Output
            </p>
            <ExpandableText text={summary} maxLen={220} />
            {finding.metadata?.court_defensible === false && !isNa && (
              <p className="text-[9px] text-rose-400/70 font-mono mt-1">
                Not court-defensible — excluded from confidence weighting.
              </p>
            )}
            {String(finding.metadata?.limitation_note || "") && (
              <p className="text-[9px] text-amber-400/60 font-mono mt-1">
                {String(finding.metadata?.limitation_note)}
              </p>
            )}
          </div>
        </div>
      )}
    </div>
  );
}

// ─── Collapsible "N more findings" section ────────────────────────────────────
function MoreFindingsToggle({
  findings,
  count,
}: {
  findings: AgentFindingDTO[];
  count: number;
}) {
  const [open, setOpen] = useState(false);
  const warnCount     = findings.filter(f => getFindingStatus(f) === "warning").length;
  const errCount      = findings.filter(f => getFindingStatus(f) === "error").length;

  return (
    <div>
      <button
        onClick={() => setOpen(v => !v)}
        aria-expanded={open}
        className="w-full flex items-center justify-between px-4 py-2.5 border-t border-border-subtle/40 hover:bg-white/[0.015] transition-colors cursor-pointer group"
      >
        <div className="flex items-center gap-2.5">
          <span className="text-[10px] font-mono font-bold uppercase tracking-widest text-foreground/40 group-hover:text-foreground/60 transition-colors">
            {open ? "Hide" : `+${count} more finding${count !== 1 ? "s" : ""}`}
          </span>
          {!open && (warnCount > 0 || errCount > 0) && (
            <div className="flex items-center gap-1.5">
              {warnCount > 0 && (
                <span className="flex items-center gap-1 text-[9px] font-mono text-amber-400/70">
                  <AlertTriangle className="w-2.5 h-2.5" />{warnCount}
                </span>
              )}
              {errCount > 0 && (
                <span className="flex items-center gap-1 text-[9px] font-mono text-rose-400/70">
                  <XCircle className="w-2.5 h-2.5" />{errCount}
                </span>
              )}
            </div>
          )}
        </div>
        <div className={clsx("p-1 rounded transition-all duration-200 shrink-0", open && "rotate-180 bg-white/5")}>
          <ChevronDown className="w-3 h-3 text-foreground/30" />
        </div>
      </button>

      {open && (
        <div>
          {findings.map((f, idx) => (
            <ToolRow
              key={f.finding_id || idx}
              finding={f}
              isLast={idx === findings.length - 1}
              defaultExpanded={false}
            />
          ))}
        </div>
      )}
    </div>
  );
}

// ─── Main AgentFindingCard ────────────────────────────────────────────────────
export interface AgentFindingCardProps {
  agentId: string;
  initialFindings: AgentFindingDTO[];
  deepFindings: AgentFindingDTO[];
  metrics?: AgentMetricsDTO;
  narrative?: string;
  phase?: "initial" | "deep";
  defaultOpen?: boolean;
}

export function AgentFindingCard({
  agentId,
  initialFindings,
  deepFindings,
  metrics,
  narrative,
  phase = "initial",
  defaultOpen = false,
}: AgentFindingCardProps) {
  const [open,     setOpen]     = useState(defaultOpen);
  const [showOther, setShowOther] = useState(false);
  const meta = AGENT_META[agentId];

  const SKIP_TYPES = new Set(["file type not applicable", "format not supported"]);
  const findings      = phase === "deep" ? deepFindings : initialFindings;
  const otherFindings = phase === "deep" ? initialFindings : deepFindings;

  const realFindings = findings.filter(
    f => !SKIP_TYPES.has(String(f.finding_type).toLowerCase())
  );
  const otherReal = otherFindings.filter(
    f => !SKIP_TYPES.has(String(f.finding_type).toLowerCase())
  );

  const isSkipped  = realFindings.length === 0 && findings.some(f => SKIP_TYPES.has(String(f.finding_type).toLowerCase()));
  const hasErrors  = realFindings.some(f => getFindingStatus(f) === "error");
  const allFailed  = hasErrors && realFindings.every(f => getFindingStatus(f) === "error");

  // ── Stats ──
  const toolsTotal  = metrics?.total_tools_called ?? realFindings.length;
  const toolsOk     = metrics?.tools_succeeded   ?? realFindings.filter(f => getFindingStatus(f) === "success").length;
  const errorRate   = metrics?.error_rate        ?? 0;
  const confidence  = metrics?.confidence_score  ?? (
    realFindings.reduce((s, f) => s + (f.raw_confidence_score ?? f.calibrated_probability ?? f.confidence_raw ?? 0), 0)
    / Math.max(realFindings.length, 1)
  );

  // ── Total run time from tool metadata ──
  const totalMs = useMemo(() => {
    const sum = realFindings.reduce((acc, f) => {
      const t = extractTimingMs(f);
      return acc + (t ?? 0);
    }, 0);
    return sum > 0 ? sum : null;
  }, [realFindings]);

  // ── Verdict ──
  const verdictKey = useMemo(() => {
    if (isSkipped) return "NOT APPLICABLE";
    if (allFailed) return "ANALYSIS FAILED";
    if (realFindings.some(f => getFindingStatus(f) === "warning")) return "ANOMALIES DETECTED";
    return "NO ANOMALIES";
  }, [realFindings, isSkipped, allFailed]);

  const verdictDisplay = getVerdictDisplay(verdictKey);
  const statusBadge    = deriveStatus(isSkipped, allFailed, hasErrors);

  // ── Tool list split: first 3 visible, rest collapsed ──
  const visibleFindings = realFindings.slice(0, VISIBLE_TOOLS_THRESHOLD);
  const hiddenFindings  = realFindings.slice(VISIBLE_TOOLS_THRESHOLD);

  if (!meta) return null;
  const Icon = meta.icon;

  return (
    <SurfaceCard className={clsx(
      "p-0 overflow-hidden transition-all duration-300",
      isSkipped && "opacity-50 grayscale"
    )}>

      {/* ══ HEADER ══════════════════════════════════════════════════════════ */}
      <button
        onClick={() => !isSkipped && setOpen(v => !v)}
        disabled={isSkipped}
        aria-expanded={isSkipped ? undefined : open}
        className={clsx(
          "w-full px-5 py-5 text-left transition-colors duration-200",
          isSkipped ? "cursor-default" : "hover:bg-white/[0.02] cursor-pointer"
        )}
      >
        <div className="flex items-start justify-between gap-4">

          {/* Left: icon + name/verdict/stats */}
          <div className="flex items-start gap-4 min-w-0">
            {/* Agent icon */}
            <div className={clsx(
              "w-11 h-11 rounded-xl flex items-center justify-center shrink-0 border mt-0.5 transition-all duration-300",
              isSkipped
                ? "bg-slate-800/40 border-slate-700/30 text-slate-500"
                : `${meta.accentBg} ${meta.accentBorder} ${meta.accentColor}`
            )}>
              <Icon className="w-5 h-5" />
            </div>

            <div className="min-w-0 space-y-1.5">
              {/* Row 1: name + role + operational status + phase */}
              <div className="flex items-center gap-2 flex-wrap">
                <h3 className={clsx(
                  "font-black text-sm font-heading uppercase tracking-tight",
                  !isSkipped ? "text-white" : "text-white/40"
                )}>
                  {meta.name}
                </h3>
                <span className="text-[9px] font-mono text-foreground/30 tracking-tighter">
                  {"// "}{meta.role}
                </span>
                <Badge
                  variant={statusBadge.variant}
                  className="font-mono font-bold uppercase tracking-widest text-[8px] px-1.5 py-0"
                >
                  {statusBadge.label}
                </Badge>
                <PhaseBadge phase={phase} />
              </div>

              {/* Row 2: verdict — prominent, no italic */}
              {!isSkipped && (
                <p className={clsx(
                  "text-base font-black tracking-tight leading-none",
                  verdictDisplay.color
                )}>
                  {verdictDisplay.label}
                </p>
              )}

              {/* Row 3: tools ran · total time */}
              {!isSkipped && (
                <p className="text-[10px] font-mono text-foreground/35 flex items-center gap-1.5">
                  <span className="text-foreground/55 font-bold">{toolsOk}/{toolsTotal}</span>
                  <span>tools ran</span>
                  {totalMs !== null && (
                    <>
                      <span className="text-foreground/20">·</span>
                      <Clock className="w-2.5 h-2.5 text-foreground/30" />
                      <span>{fmtMs(totalMs)}</span>
                    </>
                  )}
                </p>
              )}
            </div>
          </div>

          {/* Right: confidence bar + error rate + chevron */}
          {!isSkipped && (
            <div className="flex flex-col items-end gap-2 shrink-0">
              {/* Confidence bar */}
              <ConfidenceBar value={confidence} accentColor={meta.accentColor} />

              {/* Error rate */}
              <div className="flex items-center gap-1.5">
                {errorRate > 0 ? (
                  <span className="flex items-center gap-1 text-[9px] font-mono font-bold text-amber-400/70">
                    <AlertTriangle className="w-2.5 h-2.5" />
                    {Math.round(errorRate * 100)}% errors
                  </span>
                ) : (
                  <span className="flex items-center gap-1 text-[9px] font-mono font-bold text-emerald-400/50">
                    <CheckCircle2 className="w-2.5 h-2.5" />
                    No errors
                  </span>
                )}
              </div>

              {/* Chevron */}
              <div className={clsx(
                "p-1.5 rounded bg-white/5 border border-white/5 transition-all duration-300 mt-1",
                open && "rotate-180 bg-amber-500/10 border-amber-500/30 text-amber-500"
              )}>
                <ChevronDown className="w-3.5 h-3.5" aria-hidden="true" />
              </div>
            </div>
          )}
        </div>
      </button>

      {/* ══ BODY ════════════════════════════════════════════════════════════ */}
      {open && !isSkipped && (
        <div className="border-t border-border-subtle">

          {/* ── Agent narrative ── */}
          {narrative ? (
            <div className="px-5 pt-4 pb-2">
              <div className="rounded-xl bg-black/30 border border-white/5 px-5 py-4">
                <p className="text-[9px] font-mono font-bold uppercase tracking-[0.2em] text-foreground/30 mb-2 flex items-center gap-1.5">
                  <Activity className="w-3 h-3 text-amber-500/60" />
                  Agent Narrative
                </p>
                <p className="text-white/75 text-[13px] leading-relaxed font-medium">
                  {narrative}
                </p>
              </div>
            </div>
          ) : (
            <div className="px-5 pt-4 pb-2">
              <p className="text-foreground/20 text-[11px] font-mono italic">
                Narrative synthesis pending…
              </p>
            </div>
          )}

          {/* ── Tool findings ── */}
          {realFindings.length > 0 && (
            <div className="px-5 pt-2 pb-4 space-y-2">
              <p className="text-[10px] text-foreground/35 font-mono font-bold uppercase tracking-widest flex items-center gap-2 px-1">
                <Cpu className="w-3 h-3" aria-hidden="true" />
                {phase === "deep" ? "Deep Analysis" : "Initial Analysis"}
                <span className="text-foreground/20">—</span>
                {realFindings.length} probe{realFindings.length !== 1 ? "s" : ""}
              </p>

              <div className="rounded-xl border border-border-subtle overflow-hidden bg-surface-mid/40">
                {/* First N tools always visible */}
                {visibleFindings.map((f, idx) => (
                  <ToolRow
                    key={f.finding_id || idx}
                    finding={f}
                    isLast={idx === visibleFindings.length - 1 && hiddenFindings.length === 0}
                    defaultExpanded={idx === 0}
                  />
                ))}

                {/* Collapse hidden tools behind toggle */}
                {hiddenFindings.length > 0 && (
                  <MoreFindingsToggle
                    findings={hiddenFindings}
                    count={hiddenFindings.length}
                  />
                )}
              </div>
            </div>
          )}

          {/* ── See other phase findings ── */}
          {otherReal.length > 0 && (
            <div className="px-5 pb-5">
              <button
                onClick={() => setShowOther(v => !v)}
                className="w-full flex items-center justify-between px-4 py-3 rounded-xl border border-border-subtle/50 bg-white/[0.012] hover:bg-white/[0.025] transition-colors cursor-pointer group"
                aria-expanded={showOther}
              >
                <span className="flex items-center gap-2 text-[10px] font-mono font-bold uppercase tracking-widest text-foreground/35 group-hover:text-foreground/55 transition-colors">
                  <Layers className="w-3 h-3" />
                  See {phase === "deep" ? "Initial" : "Deep"} Findings ({otherReal.length})
                </span>
                <div className={clsx(
                  "p-1 rounded transition-all duration-200",
                  showOther ? "rotate-180 bg-white/5" : ""
                )}>
                  <ChevronDown className="w-3 h-3 text-foreground/30" />
                </div>
              </button>

              {showOther && (
                <div className="mt-2 rounded-xl border border-border-subtle overflow-hidden bg-surface-mid/40">
                  {otherReal.map((f, idx) => (
                    <ToolRow
                      key={f.finding_id || idx}
                      finding={f}
                      isLast={idx === otherReal.length - 1}
                      defaultExpanded={false}
                    />
                  ))}
                </div>
              )}
            </div>
          )}

        </div>
      )}
    </SurfaceCard>
  );
}
