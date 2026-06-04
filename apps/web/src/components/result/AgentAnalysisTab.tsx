"use client";

import React, { useState, useMemo, useCallback } from "react";
import { motion, AnimatePresence, useReducedMotion } from "framer-motion";
import {
  ChevronDown,
  Cpu,
  Activity,
  ShieldCheck,
  ShieldAlert,
  Shield,
  ShieldX,
  AlertTriangle,
  CheckCircle2,
  XCircle,
  MinusCircle,
  Clock,
  type LucideIcon,
} from "lucide-react";
import { clsx } from "clsx";
import type { ReportDTO, AgentFindingDTO } from "@/lib/api";
import type { Finding } from "@/lib/types";
import { AgentFindingCard } from "@/components/ui/AgentFindingCard";
import { ExecutionTimeline } from "./ExecutionTimeline";
import { accentFor } from "@/lib/agentTheme";
import { fmtTool } from "@/lib/fmtTool";
import type { AgentUpdate } from "@/components/evidence/types";

// ─── Agent identity ───────────────────────────────────────────────────────────

const AGENT_META: Record<string, { name: string; role: string; icon: LucideIcon }> = {
  Agent1: { name: "Image Forensics", role: "Pixel Integrity & AI Detection", icon: ShieldCheck },
  Agent2: { name: "Audio Forensics", role: "Acoustic Integrity", icon: Activity },
  Agent3: { name: "Contextual Analysis", role: "Scene & Object Verification", icon: Shield },
  Agent4: { name: "Video Forensics", role: "Temporal Analysis", icon: ShieldAlert },
  Agent5: { name: "Metadata Expert", role: "Digital Provenance", icon: Cpu },
};

// ─── Tool log helpers ─────────────────────────────────────────────────────────

interface ToolLogEntry {
  agentId: string;
  agentName: string;
  toolName: string;
  verdict: string;
  confidence: number | null;
  durationMs: number | null;
  status: string;
}

function buildToolLog(report: ReportDTO, activeAgentIds: string[]): ToolLogEntry[] {
  const seen = new Set<string>();
  const entries: ToolLogEntry[] = [];
  for (const agentId of activeAgentIds) {
    const findings = report.per_agent_findings?.[agentId] ?? [];
    for (const f of findings) {
      const toolName = String((f.metadata?.tool_name as string) || f.finding_type || "");
      if (!toolName) continue;
      const key = `${agentId}:${toolName}`;
      if (seen.has(key)) continue;
      seen.add(key);
      entries.push({
        agentId,
        agentName: AGENT_META[agentId]?.name ?? agentId,
        toolName,
        verdict: f.evidence_verdict ?? "INCONCLUSIVE",
        confidence: f.raw_confidence_score ?? f.confidence_raw ?? null,
        durationMs: (f.metadata?.execution_time_ms as number) ?? null,
        status: f.status ?? "CONFIRMED",
      });
    }
  }
  return entries;
}

function VerdictIcon({ verdict }: { verdict: string }) {
  const v = verdict.toUpperCase();
  if (v === "POSITIVE") return <AlertTriangle className="w-3.5 h-3.5 text-warning shrink-0" />;
  if (v === "NEGATIVE") return <CheckCircle2 className="w-3.5 h-3.5 text-success shrink-0" />;
  if (v === "ERROR") return <XCircle className="w-3.5 h-3.5 text-danger shrink-0" />;
  if (v === "NOT_APPLICABLE") return <MinusCircle className="w-3.5 h-3.5 fc-text-faint shrink-0" />;
  return <MinusCircle className="w-3.5 h-3.5 fc-text-muted shrink-0" />;
}

// ─── Agent tile (collapsed state in the grid) ─────────────────────────────────

function AgentTile({
  agentId,
  isSelected,
  summary,
  onClick,
}: {
  agentId: string;
  isSelected: boolean;
  summary?: { verdict: string; confidence_pct: number };
  onClick: () => void;
}) {
  const meta = AGENT_META[agentId] ?? { name: agentId, role: "", icon: ShieldX };
  const accent = accentFor(agentId);
  const AgentIcon = meta.icon;

  const verdictUpper = summary?.verdict?.toUpperCase() ?? "";
  const dotColor =
    /MANIPULATED|AI_GENERATED/.test(verdictUpper)
      ? "bg-danger"
      : /SUSPICIOUS|INCONCLUSIVE/.test(verdictUpper)
      ? "bg-warning"
      : /AUTHENTIC|CLEAN/.test(verdictUpper)
      ? "bg-success"
      : "bg-white/25";

  return (
    <button
      type="button"
      onClick={onClick}
      className={clsx(
        "flex flex-col items-center gap-3 p-4 rounded-2xl border transition-all duration-[160ms] group focus-visible:outline-none focus-visible:ring-2",
        isSelected
          ? clsx(accent.borderClass, "ring-1", accent.ringClass, "bg-white/[0.04]")
          : "border-white/[0.08] hover:border-white/20 hover:bg-white/[0.03]"
      )}
      aria-pressed={isSelected}
      aria-label={`${isSelected ? "Collapse" : "Expand"} ${meta.name}`}
    >
      <div
        className={clsx(
          "w-14 h-14 rounded-2xl flex items-center justify-center border-2 transition-all duration-[160ms]",
          accent.borderClass, accent.textClass,
          isSelected ? "bg-white/[0.06]" : "bg-transparent"
        )}
      >
        <AgentIcon className="w-6 h-6" />
      </div>

      <div className="text-center min-w-0 w-full">
        <p className="text-xs font-bold text-white truncate">{meta.name}</p>
        {summary && (
          <div className="flex items-center justify-center gap-1.5 mt-1">
            <span className={clsx("w-1.5 h-1.5 rounded-full shrink-0", dotColor)} />
            <span className="text-xs font-mono fc-text-muted">{summary.confidence_pct}%</span>
          </div>
        )}
      </div>

      <ChevronDown
        className={clsx(
          "w-3.5 h-3.5 fc-text-muted transition-transform duration-[160ms]",
          isSelected && "rotate-180"
        )}
        aria-hidden="true"
      />
    </button>
  );
}

// ─── Skipped agent tile ───────────────────────────────────────────────────────

function SkippedAgentTile({
  agentId,
  reason,
  isOpen,
  onToggle,
}: {
  agentId: string;
  reason: string;
  isOpen: boolean;
  onToggle: () => void;
}) {
  const meta = AGENT_META[agentId] ?? { name: agentId, role: "Unknown", icon: ShieldX };
  const AgentIcon = meta.icon;

  return (
    <div className="rounded-2xl border border-white/[0.06] overflow-hidden">
      <button
        type="button"
        onClick={onToggle}
        className="w-full flex items-center gap-4 px-5 py-4 hover:bg-white/[0.02] transition-colors text-left group"
        aria-expanded={isOpen}
      >
        <div className="w-10 h-10 rounded-xl flex items-center justify-center border border-white/10 bg-white/[0.03] shrink-0 opacity-50">
          <AgentIcon className="w-5 h-5 fc-text-muted" />
        </div>
        <div className="flex-1 min-w-0">
          <p className="text-xs font-bold fc-text-muted">{meta.name}</p>
          <p className="text-xs fc-text-faint">{meta.role} · Protocol Skip</p>
        </div>
        <span className="text-xs font-mono fc-text-muted px-2.5 py-1 rounded-full border border-white/[0.08] shrink-0">
          Not Applicable
        </span>
        <ChevronDown
          className={clsx(
            "w-4 h-4 fc-text-muted transition-transform duration-[160ms] shrink-0",
            isOpen && "rotate-180"
          )}
        />
      </button>

      <AnimatePresence initial={false}>
        {isOpen && (
          <motion.div
            initial={{ height: 0, opacity: 0 }}
            animate={{ height: "auto", opacity: 1 }}
            exit={{ height: 0, opacity: 0 }}
            transition={{ duration: 0.16, ease: "easeOut" }}
            className="overflow-hidden"
          >
            <div className="px-5 py-4 border-t border-white/[0.06] bg-white/[0.01]">
              <p className="text-xs fc-text-muted leading-relaxed">{reason || "This agent's tools are not applicable to the submitted file type."}</p>
            </div>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
}

// ─── Tool execution log ───────────────────────────────────────────────────────

function ToolLog({ entries }: { entries: ToolLogEntry[] }) {
  const [open, setOpen] = useState(false);

  if (entries.length === 0) return null;

  const errorCount = entries.filter((e) => e.verdict === "ERROR").length;
  const positiveCount = entries.filter((e) => e.verdict === "POSITIVE").length;

  return (
    <div className="rounded-2xl border border-white/[0.06] overflow-hidden">
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        className="w-full flex items-center gap-3 px-5 py-4 hover:bg-white/[0.02] transition-colors text-left"
        aria-expanded={open}
      >
        <div className="p-1.5 rounded bg-white/[0.04] border border-white/[0.08]">
          <Activity className="w-4 h-4 fc-text-muted" />
        </div>
        <div className="flex-1">
          <span className="text-sm font-semibold fc-text-secondary">Tool Execution Log</span>
          <span className="text-xs fc-text-muted ml-2 font-mono">{entries.length} tools</span>
          {(errorCount > 0 || positiveCount > 0) && (
            <span className="ml-2 text-xs font-mono">
              {positiveCount > 0 && <span className="text-warning">{positiveCount} flagged</span>}
              {positiveCount > 0 && errorCount > 0 && <span className="fc-text-faint mx-1">·</span>}
              {errorCount > 0 && <span className="text-danger">{errorCount} errors</span>}
            </span>
          )}
        </div>
        <ChevronDown
          className={clsx("w-4 h-4 fc-text-muted transition-transform duration-[160ms]", open && "rotate-180")}
        />
      </button>

      <AnimatePresence initial={false}>
        {open && (
          <motion.div
            initial={{ height: 0, opacity: 0 }}
            animate={{ height: "auto", opacity: 1 }}
            exit={{ height: 0, opacity: 0 }}
            transition={{ duration: 0.18, ease: "easeOut" }}
            className="overflow-hidden"
          >
            <div className="border-t border-white/[0.06]">
              {/* Column headers */}
              <div className="grid grid-cols-[1fr_auto_auto_auto] gap-3 px-5 py-2.5 bg-white/[0.02] text-xs font-mono fc-text-faint uppercase tracking-wider">
                <span>Tool</span>
                <span className="text-right">Agent</span>
                <span className="text-right">Conf</span>
                <span className="text-right">Time</span>
              </div>

              <div className="divide-y divide-white/[0.04]">
                {entries.map((entry, i) => {
                  const accent = accentFor(entry.agentId);
                  return (
                    <div
                      key={`${entry.agentId}-${entry.toolName}-${i}`}
                      className="grid grid-cols-[1fr_auto_auto_auto] gap-3 px-5 py-3 items-center hover:bg-white/[0.015] transition-colors"
                    >
                      <div className="flex items-center gap-2.5 min-w-0">
                        <VerdictIcon verdict={entry.verdict} />
                        <span className="text-xs font-mono fc-text-secondary truncate">
                          {fmtTool(entry.toolName)}
                        </span>
                      </div>
                      <span
                        className="text-xs font-mono shrink-0"
                        style={{ color: accent.color }}
                      >
                        {AGENT_META[entry.agentId]?.name?.split(" ")[0] ?? entry.agentId}
                      </span>
                      <span className="text-xs font-mono tabular-nums fc-text-muted shrink-0 text-right">
                        {entry.confidence !== null
                          ? `${Math.round(entry.confidence * 100)}%`
                          : "—"}
                      </span>
                      <span className="text-xs font-mono tabular-nums fc-text-faint shrink-0 text-right flex items-center gap-1">
                        {entry.durationMs !== null ? (
                          <>
                            <Clock className="w-3 h-3" />
                            {entry.durationMs >= 1000
                              ? `${(entry.durationMs / 1000).toFixed(1)}s`
                              : `${entry.durationMs}ms`}
                          </>
                        ) : (
                          "—"
                        )}
                      </span>
                    </div>
                  );
                })}
              </div>
            </div>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
}

// ─── Main component ───────────────────────────────────────────────────────────

interface AgentAnalysisTabProps {
  report: ReportDTO;
  activeAgentIds: string[];
  isDeepPhase: boolean;
  agentTimeline?: AgentUpdate[];
  pipelineStartAt?: string | null;
}

export function AgentAnalysisTab({
  report,
  activeAgentIds,
  isDeepPhase,
  agentTimeline = [],
  pipelineStartAt = null,
}: AgentAnalysisTabProps) {
  const prefersReduced = useReducedMotion();
  const [selectedAgentId, setSelectedAgentId] = useState<string | null>(
    activeAgentIds[0] ?? null
  );
  const [openSkipped, setOpenSkipped] = useState<string | null>(null);

  const handleTileClick = useCallback(
    (agentId: string) => {
      setSelectedAgentId((prev) => (prev === agentId ? null : agentId));
    },
    []
  );

  const selectedFindings = useMemo(() => {
    if (!selectedAgentId) return { initial: [], deep: [] };
    const all = report.per_agent_findings?.[selectedAgentId] ?? [];
    return {
      initial: all.filter((f: Finding) => f?.metadata?.analysis_phase !== "deep"),
      deep: all.filter((f: Finding) => f?.metadata?.analysis_phase === "deep"),
    };
  }, [selectedAgentId, report.per_agent_findings]);

  const toolLog = useMemo(
    () => buildToolLog(report, activeAgentIds),
    [report, activeAgentIds]
  );

  const skippedEntries = Object.entries(report.skipped_agents ?? {});

  if (activeAgentIds.length === 0 && skippedEntries.length === 0) {
    return (
      <div className="rounded-2xl border border-dashed border-white/10 bg-white/[0.01] p-12 text-center flex flex-col items-center justify-center">
        <Cpu className="w-10 h-10 text-primary/20 mb-4" aria-hidden="true" />
        <p className="text-sm fc-text-muted">No agent findings available.</p>
      </div>
    );
  }

  return (
    <section className="space-y-4" aria-label="Agent analysis findings">

      {/* ── Section header ── */}
      <div className="flex items-center justify-between gap-3">
        <div className="flex items-center gap-2.5">
          <div className="p-1.5 rounded bg-primary/10 border border-primary/20">
            <Cpu className="w-4 h-4 text-primary" aria-hidden="true" />
          </div>
          <h2 className="text-sm font-semibold fc-text-primary">Agent Analysis</h2>
        </div>
        <div className="bg-white/[0.03] border border-white/10 px-2.5 py-1 rounded text-xs font-mono text-primary">
          {activeAgentIds.length} Active · {skippedEntries.length} Skipped
        </div>
      </div>

      {/* ── Active agent grid ── */}
      {activeAgentIds.length > 0 && (
        <div
          className={clsx(
            "grid gap-3",
            activeAgentIds.length === 1
              ? "grid-cols-1 max-w-[200px]"
              : activeAgentIds.length === 2
              ? "grid-cols-2 max-w-[420px]"
              : activeAgentIds.length >= 3
              ? "grid-cols-3 sm:grid-cols-3 md:grid-cols-5"
              : "grid-cols-3"
          )}
          role="tablist"
          aria-label="Active agents"
        >
          {activeAgentIds.map((agentId) => (
            <AgentTile
              key={agentId}
              agentId={agentId}
              isSelected={selectedAgentId === agentId}
              summary={report.per_agent_summary?.[agentId]}
              onClick={() => handleTileClick(agentId)}
            />
          ))}
        </div>
      )}

      {/* ── Selected agent detail panel ── */}
      <AnimatePresence mode="wait">
        {selectedAgentId && (
          <motion.div
            key={selectedAgentId}
            initial={prefersReduced ? false : { opacity: 0, y: 6 }}
            animate={{ opacity: 1, y: 0 }}
            exit={prefersReduced ? {} : { opacity: 0, y: -4 }}
            transition={{ duration: 0.18, ease: "easeOut" }}
          >
            <AgentFindingCard
              agentId={selectedAgentId}
              initialFindings={selectedFindings.initial}
              deepFindings={selectedFindings.deep}
              metrics={report.per_agent_metrics?.[selectedAgentId]}
              narrative={report.per_agent_analysis?.[selectedAgentId]}
              narrativeStructured={report.per_agent_narrative_structured?.[selectedAgentId]}
              agentSummary={report.per_agent_summary?.[selectedAgentId]}
              phase={isDeepPhase ? "deep" : "initial"}
              defaultOpen={true}
            />
          </motion.div>
        )}
      </AnimatePresence>

      {/* ── Skipped agents ── */}
      {skippedEntries.length > 0 && (
        <div className="space-y-2">
          <p className="text-xs font-mono fc-text-faint uppercase tracking-wider px-1">
            Skipped Agents
          </p>
          {skippedEntries.map(([agentId, reason]) => (
            <SkippedAgentTile
              key={agentId}
              agentId={agentId}
              reason={reason}
              isOpen={openSkipped === agentId}
              onToggle={() => setOpenSkipped((prev) => (prev === agentId ? null : agentId))}
            />
          ))}
        </div>
      )}

      {/* ── Tool execution log ── */}
      <ToolLog entries={toolLog} />

      {/* ── Analysis timeline ── */}
      <ExecutionTimeline
        report={report}
        activeAgentIds={activeAgentIds}
        agentTimeline={agentTimeline}
        pipelineStartAt={pipelineStartAt}
      />
    </section>
  );
}
