"use client";

import React from "react";
import { Cpu } from "lucide-react";
import { clsx } from "clsx";
import { accentFor } from "@/lib/agentTheme";
import type { AgentMetricsDTO } from "@/lib/api";

const ALL_AGENT_IDS = ["Agent1", "Agent2", "Agent3", "Agent4", "Agent5"] as const;

const AGENT_LABELS: Record<string, string> = {
  Agent1: "Image",
  Agent2: "Audio",
  Agent3: "Scene",
  Agent4: "Video",
  Agent5: "Meta",
};

interface AgentsStripProps {
  perAgentMetrics?: Record<string, AgentMetricsDTO>;
  skippedAgents?: Record<string, string>;
  activeAgentIds: string[];
}

function agentVerdictStatus(metrics: AgentMetricsDTO | undefined): "danger" | "warning" | "success" | "neutral" {
  if (!metrics) return "neutral";
  const v = String((metrics as unknown as Record<string, unknown>).agent_verdict ?? "").toUpperCase();
  if (/MANIPULATED|AI_GENERATED|TAMPERED/.test(v)) return "danger";
  if (/SUSPICIOUS|INCONCLUSIVE|ABSTAIN|NEEDS_REVIEW/.test(v)) return "warning";
  if (/AUTHENTIC|CLEAN|CERTAIN/.test(v)) return "success";
  return "neutral";
}

const STATUS_DOT_CLS: Record<string, string> = {
  danger:  "bg-danger",
  warning: "bg-warning",
  success: "bg-success",
  neutral: "bg-white/25",
};

export function AgentsStrip({ perAgentMetrics, skippedAgents, activeAgentIds }: AgentsStripProps) {
  const activeSet = new Set(activeAgentIds);
  const skippedSet = new Set(Object.keys(skippedAgents ?? {}));

  const activeCount = activeAgentIds.length;

  const anomalyCount = activeAgentIds.filter((id) => {
    const status = agentVerdictStatus(perAgentMetrics?.[id]);
    return status === "danger";
  }).length;

  const suspiciousCount = activeAgentIds.filter((id) => {
    const status = agentVerdictStatus(perAgentMetrics?.[id]);
    return status === "warning";
  }).length;

  const summaryLabel = anomalyCount > 0
    ? `${anomalyCount} anomal${anomalyCount === 1 ? "y" : "ies"} detected`
    : suspiciousCount > 0
      ? `${suspiciousCount} uncertain`
      : activeCount > 0
        ? "all clean"
        : null;

  return (
    <section className="relative flex items-center gap-4 flex-wrap px-5 py-3.5 fc-surface">
      {/* Count + summary */}
      <div className="flex items-center gap-3 shrink-0">
        <div className="flex items-center gap-1.5">
          <Cpu className="w-3.5 h-3.5 text-primary/60" aria-hidden="true" />
          <span className="fc-eyebrow fc-text-secondary">{activeCount} agent{activeCount === 1 ? "" : "s"}</span>
        </div>
        {summaryLabel && (
          <>
            <span className="fc-text-muted text-xs" aria-hidden="true">·</span>
            <span className={clsx(
              "fc-eyebrow",
              anomalyCount > 0 ? "text-danger" : suspiciousCount > 0 ? "text-warning" : "text-success"
            )}>
              {summaryLabel}
            </span>
          </>
        )}
        {skippedSet.size > 0 && (
          <>
            <span className="fc-text-muted text-xs" aria-hidden="true">·</span>
            <span className="fc-eyebrow fc-text-muted">{skippedSet.size} skipped</span>
          </>
        )}
      </div>

      <div className="h-4 w-px bg-white/[0.08] shrink-0 hidden sm:block" aria-hidden="true" />

      {/* Agent badge row */}
      <div className="flex items-center gap-2 flex-wrap">
        {ALL_AGENT_IDS.map((agentId) => {
          const accent = accentFor(agentId);
          const isActive = activeSet.has(agentId);
          const isSkipped = skippedSet.has(agentId);
          const metrics = perAgentMetrics?.[agentId];
          const label = AGENT_LABELS[agentId] ?? agentId;
          const confPct = metrics ? Math.round(metrics.confidence_score * 100) : null;
          const verdictStatus = agentVerdictStatus(metrics);

          return (
            <div
              key={agentId}
              className={clsx(
                "flex items-center gap-1.5 px-2.5 py-1 rounded-full border fc-eyebrow transition-colors",
                isActive
                  ? "border-white/[0.12] bg-white/[0.04]"
                  : "border-white/[0.05] bg-transparent opacity-35"
              )}
            >
              <span
                className={clsx(
                  "w-1.5 h-1.5 rounded-full shrink-0",
                  isActive ? STATUS_DOT_CLS[verdictStatus] : "bg-white/20"
                )}
              />
              <span
                className="text-xs font-mono font-bold"
                style={{ color: isActive ? accent.color : undefined }}
              >
                {label}
              </span>
              {isActive && confPct !== null && (
                <span className="text-xs font-mono fc-text-muted">{confPct}%</span>
              )}
              {isSkipped && (
                <span className="text-xs font-mono fc-text-muted">Skip</span>
              )}
            </div>
          );
        })}
      </div>
    </section>
  );
}
