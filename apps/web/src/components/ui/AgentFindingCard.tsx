"use client";

import React, { useState, useMemo } from "react";
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
import {
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
  agentSummary?: NonNullable<ReportDTO["per_agent_summary"]>[string];
  phase?: "initial" | "deep";
  defaultOpen?: boolean;
}

const AGENT_META: Record<string, { name: string; role: string; color: string; icon: LucideIcon }> = {
  "Agent1": { name: "Image Forensics", role: "Pixel Integrity & AI Detection", color: "cyan", icon: ShieldCheck },
  "Agent2": { name: "Audio Forensics", role: "Acoustic Integrity", color: "blue", icon: Activity },
  "Agent3": { name: "Contextual Analysis", role: "Scene & Object Verification", color: "amber", icon: Shield },
  "Agent4": { name: "Video Forensics", role: "Temporal Analysis", color: "teal", icon: ShieldAlert },
  "Agent5": { name: "Metadata Expert", role: "Digital Provenance", color: "violet", icon: Cpu },
};

const COLOR_MAP: Record<string, { bg: string; border: string; text: string; ring: string }> = {
  cyan:   { bg: "bg-transparent", border: "border-primary/30",     text: "text-primary",      ring: "ring-primary/25" },
  blue:   { bg: "bg-transparent", border: "border-blue-500/30",    text: "text-blue-300",     ring: "ring-blue-500/25" },
  amber:  { bg: "bg-transparent", border: "border-amber-500/30",   text: "text-amber-300",    ring: "ring-amber-500/25" },
  teal:   { bg: "bg-transparent", border: "border-blue-500/30",    text: "text-blue-300",     ring: "ring-blue-500/25" },
  violet: { bg: "bg-transparent", border: "border-violet-500/30",  text: "text-violet-300",   ring: "ring-violet-500/25" },
};

const FLAG_CONFIG = {
  bad:  { color: "text-danger",  bg: "bg-transparent", border: "border-danger/25",  icon: AlertTriangle, label: "Anomaly" },
  warn: { color: "text-warning", bg: "bg-transparent", border: "border-warning/25", icon: AlertTriangle, label: "Warning" },
  ok:   { color: "text-primary", bg: "bg-transparent", border: "border-primary/25", icon: CheckCircle2,  label: "Clean"   },
  info: { color: "text-white/55",bg: "bg-transparent", border: "border-white/[0.08]",icon: Info,         label: "Info"    },
};

interface Section {
  id: string;
  label: string;
  flag: string;
  keySignal: string;
  analysis: string;
  findings: AgentFindingDTO[];
}

// ─── Dedup + stale/template filter ───────────────────────────────────────────
// Many runs leak duplicate tool entries (re-runs append new findings without
// retiring the prior ones) and stub findings whose entire content is a
// generic template. We pick the richest version per tool, then drop anything
// that has no actionable signal left.
function dedupeAndFilter(findings: AgentFindingDTO[]): AgentFindingDTO[] {
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
    // Keep the richer entry. Ties go to the later one (assumed freshest).
    const newScore = summaryRichness(f);
    const oldScore = summaryRichness(existing);
    if (newScore >= oldScore) byKey.set(key, f);
  }

  const deduped = Array.from(byKey.values());

  return deduped.filter((f) => {
    const verdict = String(f.evidence_verdict || "").toUpperCase();
    // Keep flagged/error/NA regardless — those are informative even without text.
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

function groupFindingsBySection(findings: AgentFindingDTO[]): Section[] {
  const groupMap = new Map<string, Section>();

  for (const f of findings) {
    const sectionId = (f.metadata?.section_id as string) || "other";
    const sectionLabel = (f.metadata?.section_label as string) || "Other Analysis";
    const sectionFlag = (f.metadata?.section_flag as string) || "info";
    const keySignal = cleanFindingText((f.metadata?.section_key_signal as string) || "");
    const analysis = cleanFindingText((f.metadata?.llm_synthesis as string) || "");

    let group = groupMap.get(sectionId);
    if (!group) {
      group = {
        id: sectionId,
        label: sectionLabel,
        flag: sectionFlag,
        keySignal,
        analysis,
        findings: [],
      };
      groupMap.set(sectionId, group);
    }
    group.findings.push(f);
  }

  const flagOrder: Record<string, number> = { bad: 0, warn: 1, ok: 2, info: 3 };
  const sorted = Array.from(groupMap.values()).sort(
    (a, b) => (flagOrder[a.flag] ?? 4) - (flagOrder[b.flag] ?? 4)
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
  const lead =
    positives.length > 0
      ? `${positives.length} check${positives.length === 1 ? "" : "s"} reported manipulation signals`
      : negatives.length > 0
        ? `${negatives.length} check${negatives.length === 1 ? "" : "s"} supported clean evidence for their specific tests`
        : "The agent found no decisive manipulation signal";

  const highlights = top
    .map((f) => cleanSummary((f.metadata?.llm_refined_summary as string) || f.reasoning_summary || "", 220))
    .filter(Boolean)
    .join(" ");

  return cleanFindingText(
    `${lead}. Confidence is ${confidence}% with ${errorRate}% tool error rate. ${highlights || "Open each tool result for the exact diagnostic metrics."}${errors.length ? ` ${errors.length} check${errors.length === 1 ? "" : "s"} did not complete and are treated only as coverage limits.` : ""}`,
  );
}

function normalizeVerdict(verdict?: string) {
  return String(verdict || "").trim().toUpperCase();
}

function verdictClasses(verdict: string) {
  if (["AUTHENTIC", "LIKELY_AUTHENTIC", "VERIFIED"].includes(verdict)) {
    return "bg-emerald-500/15 border border-emerald-500/35 text-emerald-300";
  }
  if (["SUSPICIOUS", "LIKELY_MANIPULATED", "INCONCLUSIVE", "ABSTAIN"].includes(verdict)) {
    return "bg-amber-500/15 border border-amber-500/35 text-amber-300";
  }
  if (["MANIPULATED", "TAMPERED"].includes(verdict)) {
    return "bg-red-500/15 border border-red-500/35 text-red-300";
  }
  return "bg-white/8 border border-white/15 text-white/55";
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
      "rounded-2xl border-2 overflow-hidden bg-transparent transition-colors duration-300",
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
          <span className="hidden md:block text-xs font-mono text-white/55 truncate max-w-[260px]">
            {section.keySignal}
          </span>
        )}
        <span className="text-xs font-mono font-black text-white/55 shrink-0 px-2 py-0.5 rounded-md bg-white/[0.04] border border-white/[0.08]">
          {section.findings.length} {section.findings.length === 1 ? "tool" : "tools"}
        </span>
        <span
          className="flex items-center gap-1.5 text-xs font-black tracking-wide text-white/60 group-hover/section:text-white transition-colors"
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
              className="w-full px-5 py-3 text-xs font-black tracking-wide fc-text-faint hover:text-white/75 hover:bg-white/[0.03] transition-colors border-t border-white/[0.06] flex items-center justify-center gap-2"
            >
              Collapse to top {INITIAL_TOOLS_PER_SECTION}
              <ChevronDown className="w-3 h-3 rotate-180" />
            </button>
          )}

          {section.analysis && section.analysis.length > 30 && (
            <div className="px-5 py-4 border-t border-white/[0.06] flex items-start gap-2.5 bg-white/[0.02]">
              <Activity className="w-4 h-4 text-primary/60 mt-0.5 shrink-0" />
              <p className="text-[14px] text-white/70 leading-relaxed font-medium italic">
                {section.analysis}
              </p>
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
  agentSummary,
  phase = "initial",
  defaultOpen = false,
}: AgentFindingCardProps) {
  const [open, setOpen] = useState(defaultOpen);
  const meta = AGENT_META[agentId] || { name: agentId, role: "Unknown", color: "cyan", icon: ShieldX };
  const theme = COLOR_MAP[meta.color];

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
  const parsedNarrative = useMemo(() => {
    if (!narrative) return null;
    try {
      const cleanNarrative = narrative.trim();
      const firstBrace = cleanNarrative.indexOf("{");
      const lastBrace = cleanNarrative.lastIndexOf("}");
      if (firstBrace !== -1 && lastBrace !== -1) {
        const parsed = JSON.parse(cleanNarrative.slice(firstBrace, lastBrace + 1));
        if (
          parsed &&
          typeof parsed === "object" &&
          "evidence_assessment" in parsed &&
          "deep_analysis" in parsed &&
          "reliability_verdict" in parsed
        ) {
          return parsed as {
            evidence_assessment: string;
            deep_analysis: string;
            reliability_verdict: string;
          };
        }
      }
    } catch {
      // Not valid JSON narrative format
    }
    return null;
  }, [narrative]);

  const overview = useMemo(() => {
    if (parsedNarrative) {
      return `${parsedNarrative.evidence_assessment} ${parsedNarrative.reliability_verdict}`;
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
    if (fromSummary) return fromSummary;
    if (anomalyCount > 0) return "SUSPICIOUS";
    if ((metrics?.error_rate ?? 0) > 0.2) return "INCONCLUSIVE";
    return "AUTHENTIC";
  }, [agentSummary?.verdict, anomalyCount, metrics?.error_rate]);

  if (isSkipped) {
    return (
      <div className="fc-surface-quiet p-6 border border-white/[0.05] bg-white/[0.015] opacity-40 flex items-center justify-between group grayscale hover:grayscale-0 transition-all duration-700">
        <div className="flex items-center gap-4">
          <div className="w-12 h-12 rounded-2xl bg-white/5 border border-white/10 flex items-center justify-center">
            <meta.icon className="w-5 h-5" />
          </div>
          <div>
            <h3 className="text-sm font-bold text-white/65 tracking-wide">{meta.name}</h3>
            <p className="text-xs font-mono font-bold fc-text-faint mt-0.5">{meta.role} · Protocol Skip</p>
          </div>
        </div>
        <span className="text-xs font-bold tracking-wide fc-text-faint px-3 py-1.5 rounded-full border border-white/10">Not Applicable</span>
      </div>
    );
  }

  return (
    <div
      className={clsx(
        "rounded-2xl overflow-hidden transition-all duration-500 fc-surface-quiet",
        open
          ? clsx(theme.border, "ring-1", theme.ring)
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
            "w-[52px] h-[52px] rounded-2xl flex items-center justify-center shrink-0 border-2 transition-all duration-500",
            theme.bg, theme.border, theme.text
          )}>
            <meta.icon className="w-6 h-6" />
          </div>

          {/* Name + meta */}
          <div className="flex-1 min-w-0 space-y-2">
            <div className="flex items-center gap-2 flex-wrap">
              <h3 className="text-[18px] font-black text-white tracking-tight">{meta.name}</h3>
              {metrics && (
                <span className={clsx("px-2.5 py-1 rounded-full text-xs font-black tracking-wider", verdictClasses(displayVerdict))}>
                  {displayVerdict.replace(/_/g, " ")}
                </span>
              )}
              {anomalyCount > 0 && (
                <span className="flex items-center gap-1 px-2.5 py-1 rounded-full bg-danger/15 border border-danger/35 text-danger text-xs font-black">
                  <AlertTriangle className="w-3.5 h-3.5" /> {anomalyCount}
                </span>
              )}
            </div>
            <div className="flex items-center gap-2.5 text-xs font-mono font-bold text-white/55 flex-wrap">
              <span>{meta.role}</span>
              <span className="text-white/25">·</span>
              <span>{realFindings.length} checks</span>
              {totalTimingMs > 0 && (
                <>
                  <span className="text-white/25">·</span>
                  <Clock className="w-3.5 h-3.5" />
                  <span>{totalTimingMs >= 1000 ? `${(totalTimingMs / 1000).toFixed(1)}s` : `${totalTimingMs}ms`}</span>
                </>
              )}
            </div>
            {!open && overview && (
              <p className="text-sm text-white/55 leading-relaxed font-medium line-clamp-3 italic">
                {overview}
              </p>
            )}
          </div>

          {/* Right: confidence + show/hide pill */}
          <div className="flex items-center gap-3 shrink-0">
            <ConfidenceBar value={confidence} />
            <div className="hidden sm:block px-2.5 py-1 rounded-full border border-white/15 bg-white/[0.04] text-xs font-black tracking-wide text-white/65">
              {phase === 'deep' ? 'Deep' : 'Initial'}
            </div>
            <span
              className={clsx(
                "flex items-center gap-1.5 px-3.5 py-2 rounded-full text-xs font-black tracking-wide border transition-colors",
                open
                  ? "border-white/20 bg-white/[0.06] text-white/85"
                  : "border-white/10 bg-transparent text-white/60 group-hover:border-white/20 group-hover:text-white"
              )}
              aria-hidden="true"
            >
              {open ? "Hide details" : "Show details"}
              <ChevronDown
                className={clsx(
                  "w-4 h-4 transition-transform duration-300",
                  open && "rotate-180"
                )}
              />
            </span>
          </div>
        </div>
      </button>

      {/* Expandable Content */}
      <div
        id={`agent-content-${agentId}`}
        className={clsx(
          "grid transition-all duration-500 ease-in-out",
          open ? "grid-rows-[1fr] opacity-100" : "grid-rows-[0fr] opacity-0"
        )}
      >
        <div className="overflow-hidden">
          <div className="px-6 pb-6 pt-3 space-y-4 animate-in fade-in duration-300">

            {/* Agent overview narrative — full text, no clamp */}
            {parsedNarrative ? (
              <div className="grid grid-cols-1 md:grid-cols-3 gap-4 mb-4">
                {/* Evidence Assessment Column */}
                <div className="p-5 rounded-2xl bg-white/[0.015] border border-white/[0.08] space-y-2">
                  <div className="flex items-center gap-2 text-cyan-400">
                    <ShieldCheck className="w-4 h-4 shrink-0 text-cyan-400" />
                    <h4 className="text-xs font-black tracking-wider font-mono text-cyan-400">Evidence Assessment</h4>
                  </div>
                  <p className="text-[14px] text-white/70 leading-relaxed font-medium">
                    {parsedNarrative.evidence_assessment}
                  </p>
                </div>

                {/* Deep Cross-Validation Column */}
                <div className="p-5 rounded-2xl bg-white/[0.015] border border-white/[0.08] space-y-2">
                  <div className="flex items-center gap-2 text-blue-400">
                    <Activity className="w-4 h-4 shrink-0 text-blue-400" />
                    <h4 className="text-xs font-black tracking-wider font-mono text-blue-400">Deep Validation</h4>
                  </div>
                  <p className="text-[14px] text-white/70 leading-relaxed font-medium">
                    {parsedNarrative.deep_analysis}
                  </p>
                </div>

                {/* Reliability & Verdict Column */}
                <div className="p-5 rounded-2xl bg-white/[0.015] border border-white/[0.08] space-y-2">
                  <div className="flex items-center gap-2 text-violet-400">
                    <Shield className="w-4 h-4 shrink-0 text-violet-400" />
                    <h4 className="text-xs font-black tracking-wider font-mono text-violet-400">Reliability & Verdict</h4>
                  </div>
                  <p className="text-[14px] text-white/70 leading-relaxed font-medium">
                    {parsedNarrative.reliability_verdict}
                  </p>
                </div>
              </div>
            ) : (
              overview && (
                <div className="flex items-start gap-3 p-5 rounded-2xl bg-transparent border border-white/[0.08]">
                  <Activity className="w-4 h-4 text-primary/65 mt-1 shrink-0" />
                  <p className="text-[15px] text-white/80 leading-relaxed font-medium">
                    {overview}
                  </p>
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
                  <Info className="w-4 h-4 text-white/45" />
                  <span className="text-xs font-black tracking-wide text-white/55">
                    Bypassed Tools ({bypassedFindings.length})
                  </span>
                </div>
                <div className="flex flex-wrap gap-1.5">
                  {bypassedFindings.map((f, i) => {
                    const toolName = (f.metadata?.tool_name as string) || f.finding_type || "Unknown";
                    return (
                      <span
                        key={`${toolName}-${i}`}
                        className="text-xs font-mono text-white/55 px-2.5 py-1 rounded-md bg-white/[0.04] border border-white/[0.08]"
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
        </div>
      </div>
    </div>
  );
}
