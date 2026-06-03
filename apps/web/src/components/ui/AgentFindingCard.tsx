"use client";

import React, { useState, useMemo } from "react";
import { motion, AnimatePresence } from "framer-motion";
import {
  ChevronDown,
  Clock,
  Activity,
  Cpu,
  ShieldCheck,
  ShieldAlert,
  Shield,
  ShieldX,
  AlertTriangle,
  CheckCircle2,
  Info,
  type LucideIcon
} from "lucide-react";
import { clsx } from "clsx";
import { AgentFindingDTO, AgentMetricsDTO, ReportDTO } from "@/lib/api";
import type { Finding } from "@/lib/types";
import { cleanFindingText } from "@/lib/findingText";
import { fmtTool } from "@/lib/fmtTool";
import { accentFor } from "@/lib/agentTheme";
import {
  BulletedText,
  ConfidenceBar,
  ToolRow,
  deriveSummary,
  summaryRichness,
} from "@/components/result/AgentFindingSubComponents";

export interface AgentFindingCardProps {
  agentId: string;
  initialFindings: AgentFindingDTO[];
  deepFindings: AgentFindingDTO[];
  metrics?: AgentMetricsDTO;
  narrative?: string;
  narrativeStructured?: NonNullable<ReportDTO["per_agent_narrative_structured"]>[string];
  agentSummary?: NonNullable<ReportDTO["per_agent_summary"]>[string];
  phase?: "initial" | "deep";
  defaultOpen?: boolean;
}

// Boundary guard for residual low-value key-finding lines. The backend now emits
// clean, human key findings (no bare tool-name dumps), but this drops any leftover
// noise — empty lines, bare tool names, or "no X detected: toolA, toolB" echoes —
// so the card never shows a misleading/useless Key Finding.
function isNoiseKeyFinding(line: string): boolean {
  const t = line.replace(/^-\s*/, "").trim();
  if (t.length < 12) return true;
  const low = t.toLowerCase();
  // Tool-name dump pattern: "... detected across N check(s): a, b, c."
  if (/:\s*[a-z0-9 ]+(,\s*[a-z0-9 ]+)+\.?$/i.test(t) && /\b(check|forensic|tool)/i.test(low)) return true;
  if (/^(n\/a|none|not applicable|not available|tool name|unknown)\.?$/i.test(low)) return true;
  return false;
}

// Agent identity (name/role/icon). Accent color comes from the shared
// agentTheme tokens via accentFor(agentId) so the same agent reads with the
// same accent here as in AgentStatusCard / TimelineTab.
const AGENT_META: Record<string, { name: string; role: string; icon: LucideIcon }> = {
  "Agent1": { name: "Image Forensics", role: "Pixel Integrity & AI Detection", icon: ShieldCheck },
  "Agent2": { name: "Audio Forensics", role: "Acoustic Integrity", icon: Activity },
  "Agent3": { name: "Contextual Analysis", role: "Scene & Object Verification", icon: Shield },
  "Agent4": { name: "Video Forensics", role: "Temporal Analysis", icon: ShieldAlert },
  "Agent5": { name: "Metadata Expert", role: "Digital Provenance", icon: Cpu },
};

const FLAG_CONFIG = {
  bad:  { color: "text-danger",  bg: "bg-transparent", border: "border-danger/25",  icon: AlertTriangle, label: "Anomaly" },
  warn: { color: "text-warning", bg: "bg-transparent", border: "border-warning/25", icon: AlertTriangle, label: "Warning" },
  ok:   { color: "text-primary", bg: "bg-transparent", border: "border-primary/25", icon: CheckCircle2,  label: "Clean"   },
  info: { color: "fc-text-faint",bg: "bg-transparent", border: "border-white/[0.08]",icon: Info,         label: "Info"    },
};

interface Section {
  id: string;
  label: string;
  flag: string;
  keySignal: string;
  analysis: string;
  findings: AgentFindingDTO[];
}

type ParsedAgentNarrative = {
  agent_brief: string;
  visual_description: string;
  key_findings: string;
  opinion: string;
  synthesis_source?: string;
};

const SCREENSHOT_CAMERA_TOOLS = new Set([
  "noiseprint_cluster",
  "noise_fingerprint",
  "prnu_sensor_verification",
  "neural_ela",
  "ela_full_image",
  "jpeg_ghost_detect",
  "neural_splicing",
  "splicing_detect",
  "neural_copy_move",
  "copy_move_detect",
  "adversarial_robustness_check",
  "roi_extract",
]);

function toolNameForFinding(f: AgentFindingDTO): string {
  return String((f.metadata?.tool_name as string) || f.finding_type || "").toLowerCase();
}

function isScreenshotEvidence(findings: AgentFindingDTO[]): boolean {
  const visual = findings.find((f) => toolNameForFinding(f) === "visual_evidence_profile");
  const haystack = [
    visual?.reasoning_summary,
    visual?.metadata?.content_description,
    visual?.metadata?.contextual_narrative,
    visual?.metadata?.interface_identification,
    (visual?.metadata?.forensic_routing as { image_category?: string } | undefined)?.image_category,
    ...findings.map((f) => f.metadata?.image_type),
  ]
    .map((x) => String(x || "").toLowerCase())
    .join(" ");
  return ["screenshot", "screen capture", "digital ui", "browser", "whatsapp", "telegram", "web page"].some((token) =>
    haystack.includes(token),
  );
}

// ─── Dedup + stale/template filter ───────────────────────────────────────────
// Many runs leak duplicate tool entries (re-runs append new findings without
// retiring the prior ones) and stub findings whose entire content is a
// generic template. We pick the richest version per tool, then drop anything
// that has no actionable signal left.
export function dedupeAndFilter(findings: AgentFindingDTO[]): AgentFindingDTO[] {
  const byKey = new Map<string, AgentFindingDTO>();
  for (const f of findings) {
    const key =
      (f.metadata?.tool_name as string) ||
      f.finding_type ||
      f.finding_id;
    const existing = byKey.get(key);
    if (!existing) {
      byKey.set(key, f);
      continue;
    }
    // A deep-phase finding always supersedes an initial-phase one for the same
    // tool — the deep result is authoritative and the initial is stale. Only
    // when both share the same phase do we fall back to keeping the richer entry
    // (ties → the later one). This guarantees a stale initial reading can never
    // be displayed over its fresh deep replacement.
    const phaseOf = (x: AgentFindingDTO) =>
      String(x.metadata?.analysis_phase || "initial") === "deep" ? 1 : 0;
    const newPhase = phaseOf(f);
    const oldPhase = phaseOf(existing);
    if (newPhase !== oldPhase) {
      if (newPhase > oldPhase) byKey.set(key, f);
      continue;
    }
    const newScore = summaryRichness(f);
    const oldScore = summaryRichness(existing);
    if (newScore >= oldScore) byKey.set(key, f);
  }

  const deduped = Array.from(byKey.values());
  const screenshotEvidence = isScreenshotEvidence(deduped);

  return deduped.filter((f) => {
    const tool = toolNameForFinding(f);
    if (screenshotEvidence && SCREENSHOT_CAMERA_TOOLS.has(tool)) return false;
    const verdict = String(f.evidence_verdict || "").toUpperCase();
    // Keep flagged/error rows; not-applicable rows are shown only when they are not
    // screenshot camera-tool bypasses.
    if (verdict === "POSITIVE" || verdict === "ERROR" || verdict === "NOT_APPLICABLE") return true;
    const summary = deriveSummary(f);
    const hasReal =
      (summary && summary.length > 32) ||
      Object.keys(f.metadata || {}).some(
        (k) =>
          !k.startsWith("_") &&
          k !== "tool_name" &&
          k !== "execution_time_ms" &&
          k !== "analysis_phase" &&
          k !== "section_id" &&
          k !== "section_label" &&
          k !== "section_flag",
      );
    return hasReal;
  });
}

const FLAG_ORDER: Record<string, number> = { bad: 0, warn: 1, ok: 2, info: 3 };

function worstFlag(a: string, b: string): string {
  return (FLAG_ORDER[a] ?? 4) <= (FLAG_ORDER[b] ?? 4) ? a : b;
}

function groupFindingsBySection(findings: AgentFindingDTO[]): Section[] {
  const groupMap = new Map<string, Section>();

  for (const f of findings) {
    const sectionId = (f.metadata?.section_id as string) || "other";
    const sectionLabel = (f.metadata?.section_label as string) || "Other Analysis";
    const fFlag = (f.metadata?.section_flag as string) || "info";
    const keySignal = cleanFindingText((f.metadata?.section_key_signal as string) || "");
    const analysis = cleanFindingText((f.metadata?.llm_synthesis as string) || "");

    let group = groupMap.get(sectionId);
    if (!group) {
      group = {
        id: sectionId,
        label: sectionLabel,
        flag: fFlag,
        keySignal,
        analysis,
        findings: [],
      };
      groupMap.set(sectionId, group);
    } else {
      // Escalate section flag to the worst severity seen across all findings
      group.flag = worstFlag(group.flag, fFlag);
      // Use the first non-empty key signal and analysis we encounter
      if (!group.keySignal && keySignal) group.keySignal = keySignal;
      if (!group.analysis && analysis) group.analysis = analysis;
    }
    group.findings.push(f);
  }

  const sorted = Array.from(groupMap.values()).sort(
    (a, b) => (FLAG_ORDER[a.flag] ?? 4) - (FLAG_ORDER[b.flag] ?? 4)
  );
  // Within each section, surface richer findings first.
  for (const sec of sorted) {
    sec.findings.sort((a, b) => summaryRichness(b) - summaryRichness(a));
  }
  return sorted;
}

function cleanSummary(text: string, maxLen = 320) {
  const stripped = cleanFindingText(text.replace(/^[^:]{1,55}:\s*/, "").trim());
  if (stripped.length <= maxLen) return stripped;
  const clipped = stripped.slice(0, maxLen);
  const lastSpace = clipped.lastIndexOf(" ");
  return (lastSpace > 60 ? clipped.slice(0, lastSpace) : clipped) + "...";
}

function buildAgentOverview(findings: AgentFindingDTO[], metrics?: AgentMetricsDTO, narrative?: string) {
  if (narrative && narrative.trim().length > 0) {
    return cleanFindingText(narrative.trim());
  }

  const active = findings.filter((f) => f.evidence_verdict !== "NOT_APPLICABLE");
  const positives = active.filter((f) => f.evidence_verdict === "POSITIVE");
  const errors = active.filter((f) => f.evidence_verdict === "ERROR" || f.status === "INCOMPLETE");
  const negatives = active.filter((f) => f.evidence_verdict === "NEGATIVE");
  const top = [...positives, ...active]
    .filter((f, index, arr) => arr.findIndex((x) => x.finding_id === f.finding_id) === index)
    .sort((a, b) => (b.raw_confidence_score ?? b.confidence_raw ?? 0) - (a.raw_confidence_score ?? a.confidence_raw ?? 0))
    .slice(0, 2);

  const confidence = Math.round((metrics?.confidence_score ?? 0) * 100);
  const errorRate = Math.round((metrics?.error_rate ?? 0) * 100);
  const visual = findings.find((f) => toolNameForFinding(f) === "visual_evidence_profile");
  const visualText = cleanSummary(
    String(
      visual?.metadata?.content_description ||
      visual?.metadata?.contextual_narrative ||
      visual?.reasoning_summary ||
      "",
    ),
    220,
  );
  const lead =
    positives.length > 0
      ? `${positives.length} check${positives.length === 1 ? "" : "s"} reported manipulation signals`
      : negatives.length > 0
        ? `${negatives.length} check${negatives.length === 1 ? "" : "s"} supported clean evidence for their specific tests`
        : "The agent found no decisive manipulation signal";

  const highlights = top
    .map((f) => cleanSummary(deriveSummary(f), 220))
    .filter(Boolean)
    .join(" ");

  return cleanFindingText(
    `${visualText ? `Visual profile: ${visualText}. ` : ""}${lead}. Confidence is ${confidence}% with ${errorRate}% tool error rate. ${highlights || "Open each tool result for the exact diagnostic metrics."}${errors.length ? ` ${errors.length} check${errors.length === 1 ? "" : "s"} did not complete and are treated only as coverage limits.` : ""}`,
  );
}

function normalizeVerdict(verdict?: string) {
  return String(verdict || "").trim().toUpperCase();
}

function verdictClasses(verdict: string) {
  // Confidence tiers describe a CLEAN verdict's strength — they must not borrow
  // alert colors (warning/danger), which read as "something is wrong".
  if (verdict === "HIGH") return "fc-badge fc-badge-active";
  if (verdict === "MEDIUM") return "fc-badge";
  if (verdict === "LOW") return "fc-badge";
  if (["SUSPICIOUS", "LIKELY_MANIPULATED", "INCONCLUSIVE", "ABSTAIN"].includes(verdict)) {
    return "fc-badge fc-badge-warning";
  }
  if (["MANIPULATED", "TAMPERED"].includes(verdict)) {
    return "fc-badge fc-badge-danger";
  }
  return "fc-badge";
}

const INITIAL_TOOLS_PER_SECTION = 4;

function SectionGroup({ section, defaultExpanded }: { section: Section; defaultExpanded: boolean }) {
  const [open, setOpen] = useState(defaultExpanded);
  const [showAll, setShowAll] = useState(false);
  const flagCfg = FLAG_CONFIG[section.flag as keyof typeof FLAG_CONFIG] ?? FLAG_CONFIG.info;
  const FlagIcon = flagCfg.icon;

  const visibleFindings = showAll
    ? section.findings
    : section.findings.slice(0, INITIAL_TOOLS_PER_SECTION);
  const hiddenCount = section.findings.length - visibleFindings.length;

  return (
    <div className={clsx(
      "rounded-2xl border overflow-hidden bg-transparent transition-colors duration-300",
      flagCfg.border
    )}>
      {/* Section header */}
      <button
        type="button"
        onClick={() => setOpen(!open)}
        className="w-full flex items-center gap-3 px-5 py-4 text-left transition-all hover:bg-white/[0.03] group/section"
        aria-expanded={open}
      >
        <span className={clsx("w-8 h-8 rounded-lg flex items-center justify-center border", flagCfg.bg, flagCfg.border)}>
          <FlagIcon className={clsx("w-4 h-4", flagCfg.color)} />
        </span>
        <span className={clsx("flex-1 text-sm font-black tracking-wide", flagCfg.color)}>
          {section.label}
        </span>
        {section.keySignal && (
          <span className="hidden md:block text-xs font-mono fc-text-muted truncate max-w-[260px]">
            {section.keySignal}
          </span>
        )}
        <span className="text-xs font-mono font-black fc-text-muted shrink-0 px-2 py-0.5 rounded-md bg-white/[0.04] border border-white/[0.08]">
          {section.findings.length} {section.findings.length === 1 ? "tool" : "tools"}
        </span>
        <span
          className="flex items-center gap-1.5 text-xs font-black tracking-wide fc-text-muted group-hover/section:text-white transition-colors"
          aria-hidden="true"
        >
          {open ? "Hide" : "Show"}
          <ChevronDown
            className={clsx(
              "w-4 h-4 transition-transform duration-300",
              open && "rotate-180"
            )}
          />
        </span>
      </button>

      {/* Tools */}
      {open && (
        <div className="border-t border-white/[0.06] bg-transparent">
          {visibleFindings.map((f, i) => (
            <ToolRow
              key={f.finding_id ?? `${f.finding_type}-${i}`}
              finding={f}
              isLast={i === visibleFindings.length - 1 && hiddenCount === 0}
            />
          ))}

          {hiddenCount > 0 && (
            <button
              type="button"
              onClick={() => setShowAll(true)}
              className="w-full px-5 py-3.5 text-xs font-black tracking-wide text-primary/90 hover:text-primary hover:bg-primary/[0.06] transition-colors border-t border-white/[0.06] flex items-center justify-center gap-2"
            >
              Show {hiddenCount} more tool finding{hiddenCount === 1 ? "" : "s"}
              <ChevronDown className="w-3.5 h-3.5" />
            </button>
          )}

          {showAll && section.findings.length > INITIAL_TOOLS_PER_SECTION && (
            <button
              type="button"
              onClick={() => setShowAll(false)}
              className="w-full px-5 py-3 text-xs font-black tracking-wide fc-text-muted hover:text-white/75 hover:bg-white/[0.03] transition-colors border-t border-white/[0.06] flex items-center justify-center gap-2"
            >
              Collapse to top {INITIAL_TOOLS_PER_SECTION}
              <ChevronDown className="w-3.5 h-3.5 rotate-180" />
            </button>
          )}

          {section.analysis && section.analysis.length > 30 && (
            <div className="px-5 py-4 border-t border-white/[0.06] flex items-start gap-2.5 bg-white/[0.02]">
              <Activity className="w-4 h-4 text-primary/60 mt-0.5 shrink-0" />
              <div className="flex-1 italic">
                <BulletedText text={section.analysis} colorClass="bg-primary/30" />
              </div>
            </div>
          )}
        </div>
      )}
    </div>
  );
}

export function AgentFindingCard({
  agentId,
  initialFindings,
  deepFindings,
  metrics,
  narrative,
  narrativeStructured,
  agentSummary,
  phase = "initial",
  defaultOpen = false,
}: AgentFindingCardProps) {
  const [open, setOpen] = useState(defaultOpen);
  const meta = AGENT_META[agentId] || { name: agentId, role: "Unknown", icon: ShieldX };
  const accent = accentFor(agentId);

  const rawFindings = phase === "deep" ? [...initialFindings, ...deepFindings] : initialFindings;
  const SKIP_TYPES = new Set(["file type not applicable", "format not supported"]);
  const preBypassed = rawFindings.filter((f: Finding) => SKIP_TYPES.has(String(f?.finding_type || "").toLowerCase()));
  const preReal = rawFindings.filter((f: Finding) => !SKIP_TYPES.has(String(f?.finding_type || "").toLowerCase()));

  // Dedupe + drop stale/template noise BEFORE rendering.
  const realFindings = useMemo(() => dedupeAndFilter(preReal), [preReal]);
  const bypassedFindings = useMemo(() => {
    const seen = new Set<string>();
    return preBypassed.filter((f) => {
      const key = (f.metadata?.tool_name as string) || f.finding_type || f.finding_id;
      if (seen.has(key)) return false;
      seen.add(key);
      return true;
    });
  }, [preBypassed]);

  const isSkipped = realFindings.length === 0 && bypassedFindings.length > 0;
  const confidence = metrics?.confidence_score ?? 0;

  const totalTimingMs = useMemo(() => {
    return realFindings.reduce((acc, f) => acc + ((f.metadata?.execution_time_ms as number) || 0), 0);
  }, [realFindings]);

  const sections = useMemo(() => groupFindingsBySection(realFindings), [realFindings]);
  // Prefer the typed structured narrative from the backend DTO; fall back to JSON
  // parse of per_agent_analysis string (legacy path) if the field is absent.
  const parsedNarrative = useMemo(() => {
    const normalizeStructured = (value: unknown): ParsedAgentNarrative | null => {
      if (!value || typeof value !== "object") return null;
      const record = value as Record<string, unknown>;
      if (record.agent_brief || record.visual_description || record.opinion || record.key_findings) {
        return {
          agent_brief: String(record.agent_brief || ""),
          visual_description: String(record.visual_description || record.evidence_assessment || ""),
          key_findings: String(record.key_findings || record.deep_analysis || ""),
          opinion: String(record.opinion || record.reliability_verdict || ""),
          synthesis_source: String(record.synthesis_source || ""),
        };
      }
      if (record.evidence_assessment || record.deep_analysis || record.reliability_verdict) {
        return {
          agent_brief: "",
          visual_description: String(record.evidence_assessment || ""),
          key_findings: String(record.deep_analysis || ""),
          opinion: String(record.reliability_verdict || ""),
          synthesis_source: String(record.synthesis_source || ""),
        };
      }
      return null;
    };

    if (narrativeStructured) {
      const normalized = normalizeStructured(narrativeStructured);
      if (normalized) return normalized;
    }
    if (!narrative) return null;
    try {
      const cleanNarrative = narrative.trim();
      const firstBrace = cleanNarrative.indexOf("{");
      const lastBrace = cleanNarrative.lastIndexOf("}");
      if (firstBrace !== -1 && lastBrace !== -1) {
        const parsed = JSON.parse(cleanNarrative.slice(firstBrace, lastBrace + 1));
        const normalized = normalizeStructured(parsed);
        if (normalized) return normalized;
      }
    } catch {
      // Not valid JSON narrative format
    }
    return null;
  }, [narrative, narrativeStructured]);

  const overview = useMemo(() => {
    if (parsedNarrative) {
      return parsedNarrative.agent_brief || `${parsedNarrative.visual_description} ${parsedNarrative.opinion}`;
    }
    return buildAgentOverview(realFindings, metrics, narrative);
  }, [realFindings, metrics, narrative, parsedNarrative]);

  const anomalyCount = useMemo(
    () => realFindings.filter(f =>
      f.evidence_verdict === "POSITIVE" ||
      f.status === "CONTESTED" ||
      (f.metadata?.section_flag as string) === "bad" ||
      f.severity_tier === "HIGH" ||
      f.severity_tier === "CRITICAL"
    ).length,
    [realFindings]
  );
  const displayVerdict = useMemo(() => {
    const fromSummary = normalizeVerdict(agentSummary?.verdict);
    const isAuthenticLike = !fromSummary || ["AUTHENTIC", "LIKELY_AUTHENTIC", "VERIFIED"].includes(fromSummary);
    if (anomalyCount > 0) return fromSummary && !isAuthenticLike ? fromSummary : "SUSPICIOUS";
    if ((metrics?.error_rate ?? 0) > 0.2) return "INCONCLUSIVE";
    // Replace authentic verdicts with a confidence tier
    if (isAuthenticLike) {
      if (confidence >= 0.75) return "HIGH";
      if (confidence >= 0.5) return "MEDIUM";
      return "LOW";
    }
    return fromSummary;
  }, [agentSummary?.verdict, anomalyCount, metrics?.error_rate, confidence]);

  if (isSkipped) {
    return (
      <div className="p-6 opacity-40 flex items-center justify-between group grayscale hover:grayscale-0 transition-all duration-[160ms] fc-surface-quiet">
        <div className="flex items-center gap-4">
          <div className="w-12 h-12 rounded-2xl bg-white/5 border border-white/10 flex items-center justify-center">
            <meta.icon className="w-5 h-5" />
          </div>
          <div>
            <h3 className="text-sm font-bold fc-text-muted tracking-wide">{meta.name}</h3>
            <p className="text-xs font-mono font-bold fc-text-muted mt-0.5">{meta.role} · Protocol Skip</p>
          </div>
        </div>
        <span className="text-xs font-bold tracking-wide fc-text-muted px-3 py-1.5 rounded-full border border-white/10">Not Applicable</span>
      </div>
    );
  }

  return (
    <div
      className={clsx(
        "rounded-2xl overflow-hidden transition-all duration-[160ms] fc-surface-quiet",
        open
          ? clsx(accent.borderClass, "ring-1", accent.ringClass)
          : "hover:border-white/15"
      )}
    >
      {/* Header Button */}
      <button
        onClick={() => setOpen(!open)}
        className={clsx(
          "w-full px-6 py-5 text-left transition-all relative overflow-hidden group bg-transparent",
          open ? "" : "hover:bg-white/[0.02]"
        )}
        aria-expanded={open}
        aria-controls={`agent-content-${agentId}`}
        aria-label={`${open ? "Collapse" : "Expand"} ${meta.name} findings`}
      >
        <div className="flex items-center gap-4 relative z-10">
          {/* Agent icon */}
          <div className={clsx(
            "w-[52px] h-[52px] rounded-2xl flex items-center justify-center shrink-0 border-2 bg-transparent transition-all duration-[160ms]",
            accent.borderClass, accent.textClass
          )}>
            <meta.icon className="w-6 h-6" />
          </div>

          {/* Name + meta. Collapsed shows ONLY the agent name; all metrics,
              role, timing and badges are revealed on expand. */}
          <div className="flex-1 min-w-0 space-y-2">
            <div className="flex items-center gap-2 flex-wrap">
               <h3 className="text-lg font-black text-white tracking-tight">{meta.name}</h3>
              {open && metrics && (
                <span className={verdictClasses(displayVerdict)}>
                  {displayVerdict === "HIGH" ? "High Confidence"
                    : displayVerdict === "MEDIUM" ? "Med Confidence"
                    : displayVerdict === "LOW" ? "Low Confidence"
                    : displayVerdict.replace(/_/g, " ")}
                </span>
              )}
              {open && anomalyCount > 0 && (
                <span className="fc-badge fc-badge-danger flex items-center gap-1">
                  <AlertTriangle className="w-3.5 h-3.5" /> {anomalyCount}
                </span>
              )}
            </div>
            {open && (
              <div className="flex items-center gap-2.5 text-sm font-mono font-bold fc-text-muted flex-wrap">
                <span>{meta.role}</span>
                <span className="fc-text-faint">·</span>
                <span>{realFindings.length} checks</span>
                {totalTimingMs > 0 && (
                  <>
                    <span className="fc-text-faint">·</span>
                    <Clock className="w-3.5 h-3.5" />
                    <span>{totalTimingMs >= 1000 ? `${(totalTimingMs / 1000).toFixed(1)}s` : `${totalTimingMs}ms`}</span>
                  </>
                )}
              </div>
            )}
          </div>

          {/* Right: metrics revealed on expand; chevron always present */}
          <div className="flex items-center gap-3 shrink-0">
            {open && <ConfidenceBar value={confidence} />}
            {open && (
              <div className="hidden sm:block px-2.5 py-1 rounded-full border border-white/15 bg-white/[0.04] text-xs font-black tracking-wide fc-text-muted">
                {phase === 'deep' ? 'Deep' : 'Initial'}
              </div>
            )}
            <span
              className={clsx(
                "flex items-center gap-1.5 px-3.5 py-2 rounded-full text-xs font-black tracking-wide border transition-colors",
                open
                  ? "border-white/20 bg-white/[0.06] text-white/85"
                  : "border-white/10 bg-transparent fc-text-muted group-hover:border-white/20 group-hover:text-white"
              )}
              aria-hidden="true"
            >
              {open ? "Hide details" : "Show details"}
              <ChevronDown
                className={clsx(
                  "w-4 h-4 transition-transform duration-[160ms]",
                  open && "rotate-180"
                )}
              />
            </span>
          </div>
        </div>
      </button>

      {/* Expandable Content */}
      <AnimatePresence initial={false}>
        {open && (
        <motion.div
          id={`agent-content-${agentId}`}
          initial={{ height: 0, opacity: 0 }}
          animate={{ height: "auto", opacity: 1 }}
          exit={{ height: 0, opacity: 0 }}
          transition={{ duration: 0.16, ease: "easeOut" }}
          className="overflow-hidden"
        >
          <div className="px-6 pb-6 pt-3 space-y-4">

            {/* Agent overview narrative — full text, no clamp */}
            {parsedNarrative ? (
              <div className="space-y-4 mb-4">
                {/* Visual Context — the agent's visual axis (image integrity for
                    Agent1, object/scene for Agent3, metadata for Agent5). */}
                {parsedNarrative.visual_description && (
                  <div className="p-5 rounded-2xl bg-white/[0.015] border border-white/[0.08] space-y-2">
                    <div className="flex items-center gap-2 text-blue-300">
                      <Info className="w-4 h-4 shrink-0" />
                      <h4 className="text-xs font-black tracking-wider font-mono">Visual Context</h4>
                    </div>
                    <div className="text-xs fc-text-secondary leading-relaxed font-medium">
                      <BulletedText text={parsedNarrative.visual_description} colorClass="bg-blue-500/40" />
                    </div>
                  </div>
                )}

                {/* Agent Overview — the tools that ran and the verdict arrived. */}
                {parsedNarrative.agent_brief && (
                  <div className="p-5 rounded-2xl bg-white/[0.015] border border-white/[0.08] space-y-2">
                    <div className="flex items-center gap-2 text-primary">
                      <ShieldCheck className="w-4.5 h-4.5 shrink-0 text-primary" />
                      <h4 className="text-xs font-black tracking-wider font-mono text-primary">Agent Overview</h4>
                    </div>
                    <p className="text-sm text-white/90 leading-relaxed font-medium whitespace-pre-line">{parsedNarrative.agent_brief}</p>
                  </div>
                )}

                {/* Your Opinion — the arbiter's verdict reasoning for this agent. */}
                {parsedNarrative.opinion && (
                  <div className="p-5 rounded-2xl bg-white/[0.015] border border-white/[0.08] space-y-2">
                    <div className="flex items-center gap-2 text-success">
                      <Shield className="w-4 h-4 shrink-0 text-success" />
                      <h4 className="text-xs font-black tracking-wider font-mono">Your Opinion</h4>
                    </div>
                    <div className="text-xs fc-text-secondary leading-relaxed font-medium">
                      <BulletedText text={parsedNarrative.opinion} colorClass="bg-success/40" />
                    </div>
                  </div>
                )}

                {/* Key Findings list */}
                {(() => {
                  if (!parsedNarrative.key_findings) return null;
                  const kfLines = (parsedNarrative.key_findings.includes("\n")
                    ? parsedNarrative.key_findings.split("\n")
                    : parsedNarrative.key_findings.split(";")
                  ).filter((line) => line && !isNoiseKeyFinding(line));
                  if (kfLines.length === 0) return null;
                  return (
                    <div className="p-5 rounded-2xl bg-white/[0.015] border border-white/[0.08] space-y-3">
                      <div className="flex items-center gap-2 text-amber-300">
                        <Activity className="w-4 h-4 shrink-0" />
                        <h4 className="text-xs font-black tracking-wider font-mono">Key Findings</h4>
                      </div>
                      <div className="space-y-2">
                        {kfLines.map((line, idx) => (
                          <div key={idx} className="flex items-start gap-2.5 text-xs fc-text-secondary font-mono">
                            <span className="w-1.5 h-1.5 rounded-full bg-amber-400 mt-1.5 shrink-0" />
                            <span>{line.replace(/^-\s*/, "").trim()}</span>
                          </div>
                        ))}
                      </div>
                    </div>
                  );
                })()}
              </div>
            ) : (
              overview && (
                <div className="flex items-start gap-3 p-5 rounded-2xl bg-transparent border border-white/[0.08]">
                  <Activity className="w-4 h-4 text-primary/65 mt-1 shrink-0" />
                  <div className="flex-1">
                    <BulletedText text={overview} colorClass="bg-primary/40" />
                  </div>
                </div>
              )
            )}

            {/* Section groups */}
            <div className="space-y-3">
              {sections.map((section, idx) => (
                <SectionGroup
                  key={section.id}
                  section={section}
                  // Open the first two sections; let users opt in to the rest.
                  defaultExpanded={idx < 2 || section.flag === "bad" || section.flag === "warn"}
                />
              ))}
            </div>

            {bypassedFindings.length > 0 && (
              <div className="rounded-2xl border border-white/[0.06] bg-transparent px-5 py-4">
                <div className="flex items-center gap-2 mb-2.5">
                  <Info className="w-4 h-4 fc-text-muted" />
                  <span className="text-xs font-black tracking-wide fc-text-faint">
                    Bypassed Tools ({bypassedFindings.length})
                  </span>
                </div>
                <div className="flex flex-wrap gap-1.5">
                  {bypassedFindings.map((f, i) => {
                    const toolName = (f.metadata?.tool_name as string) || f.finding_type || "Unknown";
                    return (
                      <span
                        key={`${toolName}-${i}`}
                        className="text-xs font-mono fc-text-faint px-2.5 py-1 rounded-md bg-white/[0.04] border border-white/[0.08]"
                        title="Not applicable to this file type"
                      >
                        {fmtTool(toolName)}
                      </span>
                    );
                  })}
                </div>
              </div>
            )}

          </div>
        </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
}
