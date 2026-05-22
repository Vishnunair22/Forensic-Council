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

export function AgentsStrip({ perAgentMetrics, skippedAgents, activeAgentIds }: AgentsStripProps) {
  const activeSet = new Set(activeAgentIds);
  const skippedSet = new Set(Object.keys(skippedAgents ?? {}));

  const activeCount = activeAgentIds.length;
  const skippedCount = skippedSet.size;

  return (
    <section className="rounded-2xl border border-white/[0.06] px-5 py-4 flex items-center gap-4 flex-wrap">
      {/* Counts */}
      <div className="flex items-center gap-3 shrink-0">
        <div className="flex items-center gap-1.5">
          <Cpu className="w-3.5 h-3.5 text-primary/60" />
          <span className="fc-eyebrow text-white/70">
            {activeCount} active
          </span>
        </div>
        {skippedCount > 0 && (
          <>
            <span className="fc-text-faint text-xs">·</span>
            <span className="fc-eyebrow fc-text-faint">{skippedCount} skipped</span>
          </>
        )}
      </div>

      <div className="h-4 w-px bg-white/[0.08] shrink-0 hidden sm:block" />

      {/* Agent badge row */}
      <div className="flex items-center gap-2 flex-wrap">
        {ALL_AGENT_IDS.map((agentId) => {
          const accent = accentFor(agentId);
          const isActive = activeSet.has(agentId);
          const isSkipped = skippedSet.has(agentId);
          const metrics = perAgentMetrics?.[agentId];
          const label = AGENT_LABELS[agentId] ?? agentId;
          const confPct = metrics ? Math.round(metrics.confidence_score * 100) : null;

          return (
            <div
              key={agentId}
              className={clsx(
                "flex items-center gap-1.5 px-2.5 py-1 rounded border fc-eyebrow transition-colors",
                isActive
                  ? "border-white/[0.12] bg-white/[0.04]"
                  : "border-white/[0.05] bg-transparent opacity-40"
              )}
            >
              <span
                className="w-1.5 h-1.5 rounded-full shrink-0"
                style={{ backgroundColor: isActive ? accent.color : "rgba(255,255,255,0.2)" }}
              />
              <span
                className="text-[10px] font-mono font-bold"
                style={{ color: isActive ? accent.color : "rgba(255,255,255,0.3)" }}
              >
                {label}
              </span>
              {isActive && confPct !== null && (
                <span className="text-[10px] font-mono fc-text-faint">{confPct}%</span>
              )}
              {isSkipped && (
                <span className="text-[10px] font-mono fc-text-faint">skip</span>
              )}
            </div>
          );
        })}
      </div>
    </section>
  );
}
