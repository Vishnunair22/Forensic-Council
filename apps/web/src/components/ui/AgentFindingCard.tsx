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
import { motion } from "framer-motion";
import { AgentFindingDTO, AgentMetricsDTO } from "@/lib/api";
import {
  ConfidenceBar,
  ToolRow
} from "@/components/result/AgentFindingSubComponents";

export interface AgentFindingCardProps {
  agentId: string;
  initialFindings: AgentFindingDTO[];
  deepFindings: AgentFindingDTO[];
  metrics?: AgentMetricsDTO;
  narrative?: string;
  phase?: "initial" | "deep";
  defaultOpen?: boolean;
}

const AGENT_META: Record<string, { name: string; role: string; color: string; icon: LucideIcon }> = {
  "Agent1": { name: "Agent 01", role: "Visual Integrity", color: "cyan", icon: ShieldCheck },
  "Agent2": { name: "Agent 02", role: "Acoustic Forensic", color: "blue", icon: Activity },
  "Agent3": { name: "Agent 03", role: "Contextual Analysis", color: "amber", icon: Shield },
  "Agent4": { name: "Agent 04", role: "Temporal Analysis", color: "teal", icon: ShieldAlert },
  "Agent5": { name: "Agent 05", role: "Metadata Expert", color: "violet", icon: Cpu },
};

const COLOR_MAP: Record<string, { bg: string; border: string; text: string; glow: string }> = {
  cyan: { bg: "bg-primary/5", border: "border-primary/20", text: "text-primary", glow: "shadow-[0_0_30px_rgba(var(--color-primary-rgb),0.1)]" },
  blue: { bg: "bg-blue-500/5", border: "border-blue-500/20", text: "text-blue-400", glow: "shadow-[0_0_30px_rgba(59,130,246,0.1)]" },
  amber: { bg: "bg-amber-500/5", border: "border-amber-500/20", text: "text-amber-400", glow: "shadow-[0_0_30px_rgba(245,158,11,0.1)]" },
  teal: { bg: "bg-teal-500/5", border: "border-teal-500/20", text: "text-teal-400", glow: "shadow-[0_0_30px_rgba(45,212,191,0.1)]" },
  violet: { bg: "bg-violet-500/5", border: "border-violet-500/20", text: "text-violet-400", glow: "shadow-[0_0_30px_rgba(139,92,246,0.1)]" },
};

const FLAG_CONFIG = {
  bad: { color: "text-danger", bg: "bg-danger/10", border: "border-danger/20", icon: AlertTriangle, label: "Anomaly Detected" },
  warn: { color: "text-warning", bg: "bg-warning/10", border: "border-warning/20", icon: AlertTriangle, label: "Warning" },
  ok: { color: "text-primary", bg: "bg-primary/10", border: "border-primary/20", icon: CheckCircle2, label: "Clean" },
  info: { color: "text-white/40", bg: "bg-white/5", border: "border-border-subtle", icon: Info, label: "Info" },
};

interface Section {
  id: string;
  label: string;
  flag: string;
  keySignal: string;
  analysis: string;
  findings: AgentFindingDTO[];
}

function groupFindingsBySection(findings: AgentFindingDTO[]): Section[] {
  const groupMap = new Map<string, Section>();

  for (const f of findings) {
    const sectionId = (f.metadata?.section_id as string) || "other";
    const sectionLabel = (f.metadata?.section_label as string) || "Other Analysis";
    const sectionFlag = (f.metadata?.section_flag as string) || "info";
    const keySignal = (f.metadata?.section_key_signal as string) || "";
    const analysis = (f.metadata?.llm_synthesis as string) || "";

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

  // Sort: bad → warn → ok → info → other
  const flagOrder: Record<string, number> = { bad: 0, warn: 1, ok: 2, info: 3 };
  return Array.from(groupMap.values()).sort(
    (a, b) => (flagOrder[a.flag] ?? 4) - (flagOrder[b.flag] ?? 4)
  );
}

function cleanSummary(text: string, maxLen = 210) {
  const stripped = text.replace(/^[^:]{1,55}:\s*/, "").trim();
  if (stripped.length <= maxLen) return stripped;
  const clipped = stripped.slice(0, maxLen);
  const lastSpace = clipped.lastIndexOf(" ");
  return (lastSpace > 40 ? clipped.slice(0, lastSpace) : clipped) + "...";
}

function buildAgentOverview(findings: AgentFindingDTO[], metrics?: AgentMetricsDTO, narrative?: string) {
  if (narrative && narrative.trim().length > 0) {
    return cleanSummary(narrative.trim(), 360);
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
    .map((f) => cleanSummary((f.metadata?.llm_refined_summary as string) || f.reasoning_summary || "", 120))
    .filter(Boolean)
    .join(" ");

  return `${lead}. Confidence is ${confidence}% with ${errorRate}% tool error rate. ${highlights || "Open each tool result for the exact diagnostic metrics."}${errors.length ? ` ${errors.length} check${errors.length === 1 ? "" : "s"} did not complete and are treated only as coverage limits.` : ""}`;
}

function SectionGroup({ section }: { section: Section }) {
  const [open, setOpen] = useState(section.flag === "bad" || section.flag === "warn");
  const [showAnalysis, setShowAnalysis] = useState(false);
  const flagCfg = FLAG_CONFIG[section.flag as keyof typeof FLAG_CONFIG] ?? FLAG_CONFIG.info;
  const FlagIcon = flagCfg.icon;

  return (
    <motion.div
      layout
      className={clsx(
        "rounded-[1.25rem] border overflow-hidden transition-all duration-500 relative group premium-card",
        open && "bg-surface-3",
        !open && flagCfg.bg,
        flagCfg.border
      )}
      whileHover={{ scale: 1.002, borderColor: open ? "rgba(255,255,255,0.15)" : undefined }}
    >
      <div className={clsx(
        "absolute inset-0 opacity-0 group-hover:opacity-10 pointer-events-none transition-opacity duration-700 bg-grid-small",
      )} />
      {/* Section Header */}
      <button
        onClick={() => setOpen(!open)}
        className="w-full flex items-center gap-3 px-5 py-4 text-left transition-all z-10 relative"
        aria-expanded={open}
      >
        <FlagIcon className={clsx("w-3.5 h-3.5 shrink-0", flagCfg.color)} />
        <span className={clsx("flex-1 text-[10px] font-black tracking-wide", flagCfg.color)}>
          {section.label}
        </span>
        <span className="text-[10px] font-mono font-black text-white/20 mr-2">
          {section.findings.length} Signals
        </span>
        {section.keySignal && (
          <span className="hidden sm:block text-[9px] font-mono font-black text-white/40 truncate max-w-[200px] mr-2">
            {section.keySignal}
          </span>
        )}
        <ChevronDown className={clsx("w-3.5 h-3.5 text-white/20 transition-transform duration-300 shrink-0", open && "rotate-180")} />
      </button>

      {/* Tools in this section */}
      {open && (
        <div className="border-t border-white/[0.04]">
          <div className="bg-[#000]/10">
            {section.findings.map((f, i) => (
              <ToolRow key={f.finding_id ?? `${f.finding_type}-${i}`} finding={f} isLast={i === section.findings.length - 1} />
            ))}
          </div>

          {/* Section-level LLM analysis (collapsed by default) */}
          {section.analysis && section.analysis.length > 20 && (
            <div className="border-t border-white/[0.03]">
              <button
                onClick={() => setShowAnalysis(!showAnalysis)}
                className="w-full flex items-center gap-2 px-4 py-2.5 text-left hover:bg-white/[0.02] transition-all"
              >
                <Activity className="w-3 h-3 text-primary/40 shrink-0" />
                <span className="text-[10px] font-bold tracking-wide text-white/20 flex-1">
                  Section Analysis
                </span>
                <ChevronDown className={clsx("w-3 h-3 text-white/15 transition-transform duration-300", showAnalysis && "rotate-180")} />
              </button>
              {showAnalysis && (
                <div className="px-4 pb-4 animate-in fade-in duration-200">
                  <p className="text-[12px] text-white/50 leading-relaxed font-medium italic border-l-2 border-white/10 pl-3">
                    {section.analysis}
                  </p>
                </div>
              )}
            </div>
          )}
        </div>
      )}
    </motion.div>
  );
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
  const [open, setOpen] = useState(defaultOpen);
  const meta = AGENT_META[agentId] || { name: agentId, role: "Unknown", color: "cyan", icon: ShieldX };
  const theme = COLOR_MAP[meta.color];

  const findings = phase === "deep" ? deepFindings : initialFindings;
  const SKIP_TYPES = new Set(["file type not applicable", "format not supported"]);
  const realFindings = findings.filter(f => !SKIP_TYPES.has(String(f.finding_type).toLowerCase()));

  const isSkipped = realFindings.length === 0 && findings.some(f => SKIP_TYPES.has(String(f.finding_type).toLowerCase()));
  const confidence = metrics?.confidence_score ?? 0;

  const totalTimingMs = useMemo(() => {
    return realFindings.reduce((acc, f) => acc + ((f.metadata?.execution_time_ms as number) || 0), 0);
  }, [realFindings]);

  const sections = useMemo(() => groupFindingsBySection(realFindings), [realFindings]);
  const overview = useMemo(
    () => buildAgentOverview(realFindings, metrics, narrative),
    [realFindings, metrics, narrative]
  );

  // Count anomalies for the header badge
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

  if (isSkipped) {
    return (
      <div className="rounded-3xl p-6 border border-white/[0.03] bg-white/[0.01] opacity-30 flex items-center justify-between group grayscale hover:grayscale-0 transition-all duration-700">
        <div className="flex items-center gap-4">
          <div className="w-11 h-11 rounded-2xl bg-white/5 border border-white/10 flex items-center justify-center">
            <meta.icon className="w-5 h-5" />
          </div>
          <div>
            <h3 className="text-xs font-bold text-white/50 tracking-wide">{meta.name}</h3>
            <p className="text-[10px] font-mono font-bold text-white/20 mt-0.5">{meta.role} · Protocol Skip</p>
          </div>
        </div>
        <span className="text-[10px] font-bold tracking-wide text-white/10 px-3 py-1 rounded-full border border-white/5">Not Applicable</span>
      </div>
    );
  }

  return (
    <motion.div className={clsx(
      "rounded-2xl overflow-hidden premium-glass border transition-all duration-500",
      open ? "border-primary/20 shadow-[0_32px_64px_rgba(0,0,0,0.5)]" : "border-border-subtle shadow-none"
    )}>
      {/* Header Button */}
      <button
        onClick={() => setOpen(!open)}
        className={clsx(
          "w-full p-6 text-left transition-all relative overflow-hidden group",
          open ? "bg-white/[0.04]" : "hover:bg-white/[0.02]"
        )}
        aria-expanded={open}
        aria-controls={`agent-content-${agentId}`}
        aria-label={`${open ? "Collapse" : "Expand"} ${meta.name} findings`}
      >
        <div className="flex items-start justify-between gap-6 relative z-10">
          <div className="flex items-center gap-5">
            <div className={clsx(
              "w-14 h-14 rounded-2xl flex items-center justify-center shrink-0 border transition-all duration-500",
              theme.bg, theme.border, theme.text, open && "scale-105 shadow-[0_0_20px_rgba(var(--color-primary-rgb),0.1)]"
            )}>
              <meta.icon className="w-7 h-7" />
            </div>
            <div className="space-y-1">
              <div className="flex items-center gap-2 flex-wrap">
                <h3 className="text-sm font-black text-white tracking-tighter">{meta.name}</h3>
                <span className="text-[10px] text-white/40 font-black tracking-wide">{meta.role}</span>
                {anomalyCount > 0 && (
                  <span className="flex items-center gap-1 px-2 py-0.5 rounded-full bg-danger/10 border border-danger/20 text-danger text-[10px] font-black">
                    <AlertTriangle className="w-2.5 h-2.5" /> {anomalyCount} Flags
                  </span>
                )}
              </div>
              <p className="text-[10px] font-mono font-black text-white/40 flex items-center gap-2 tracking-tight">
                {sections.length} Sectors
                <span className="text-white/10">·</span>
                {realFindings.length} Signals
                <span className="text-white/10">·</span>
                <Clock className="w-3 h-3" /> {totalTimingMs >= 1000 ? `${(totalTimingMs / 1000).toFixed(1)}s` : `${totalTimingMs}ms`}
              </p>
            </div>
          </div>

          <div className="flex flex-col items-end gap-3 text-right shrink-0">
            <ConfidenceBar value={confidence} />
            <div className="flex items-center gap-2">
              <div className="px-3 py-1 rounded-full border border-border-subtle bg-surface-1 text-[9px] font-black tracking-wide text-white/40">
                {phase === 'deep' ? 'Deep Analysis' : 'Intake Scan'}
              </div>
              <div className={clsx(
                "p-2 rounded-xl border transition-all duration-500",
                open ? "bg-primary/10 border-primary/30 text-primary rotate-180" : "bg-surface-1 border-border-subtle text-white/20"
              )}>
                <ChevronDown className="w-4 h-4" />
              </div>
            </div>
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
          <div className="p-6 pt-3 space-y-6 animate-in fade-in slide-in-from-top-4 duration-700">

            {/* Agent narrative (court_notes / reliability note) — concise, not primary */}
            {overview && (
              <div className="relative p-4 rounded-2xl bg-[#000]/30 border border-white/5">
                <div className="flex items-center gap-2 mb-2">
                  <Activity className="w-3 h-3 text-primary/50" />
                  <span className="text-[10px] font-black tracking-wide text-white/20">Precise Overview</span>
                </div>
                <p className="text-[12px] text-white/60 leading-relaxed font-medium">
                  {overview}
                </p>
              </div>
            )}

            {/* Sections — one per tool group */}
            <div className="space-y-3">
              <div className="flex items-center justify-between border-b border-white/5 pb-2">
                <div className="flex items-center gap-2">
                  <Cpu className="w-3 h-3 text-white/20" />
                  <span className="text-[10px] font-black tracking-wide text-white/20">Tool Results by Section</span>
                </div>
                <span className="text-[10px] font-mono text-white/10 font-black">
                  {realFindings.length} tool{realFindings.length !== 1 ? "s" : ""} · {sections.length} group{sections.length !== 1 ? "s" : ""}
                </span>
              </div>

              <div className="space-y-2">
                {sections.map(section => (
                  <SectionGroup key={section.id} section={section} />
                ))}
              </div>
            </div>
          </div>
        </div>
      </div>
    </motion.div>
  );
}
