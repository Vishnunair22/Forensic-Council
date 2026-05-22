"use client";

import React from "react";
import { motion } from "framer-motion";
import { clsx } from "clsx";
import type { AgentUpdate } from "./types";
import { AGENT_ICONS } from "./AgentStatusCard";
import { accentFor } from "@/lib/agentTheme";
import { Activity, SkipForward } from "lucide-react";

interface AgentStatusSummaryProps {
  visibleAgents: Array<{ id: string; name: string }>;
  skippedAgents: Array<{ id: string; name: string }>;
  agentUpdates: Record<string, { status: string; thinking?: string }>;
  completedAgents: AgentUpdate[];
}

const ALERT_VERDICTS = new Set([
  "SUSPICIOUS", "TAMPERED", "NEEDS_REVIEW",
  "LIKELY_MANIPULATED", "LIKELY_AI_GENERATED", "LIKELY_SPOOFED", "LIKELY_SYNTHETIC",
]);

function normalizeVerdict(v?: string): string {
  if (!v) return "Pending";
  return v.replace(/_/g, " ").toLowerCase().replace(/\b\w/g, c => c.toUpperCase());
}

export function AgentStatusSummary({
  visibleAgents,
  skippedAgents,
  agentUpdates,
  completedAgents,
}: AgentStatusSummaryProps) {
  const getAgentStatus = (agentId: string) => {
    const completed = completedAgents?.find((c) => c.agent_id === agentId);
    if (completed) {
      if (completed.status === "error" || completed.status === "failed") return "error";
      return "complete";
    }
    const liveStatus = agentUpdates[agentId]?.status;
    if (liveStatus === "error" || liveStatus === "failed") return "error";
    if (liveStatus === "running") return "running";
    if (agentUpdates[agentId]) return "running";
    return "waiting";
  };

  const total = visibleAgents.length;
  const doneCount = visibleAgents.filter(a => {
    const s = getAgentStatus(a.id);
    return s === "complete" || s === "error";
  }).length;
  const flaggedAgents = completedAgents.filter(a =>
    ALERT_VERDICTS.has(a.agent_verdict || "") || (a.verdict_score ?? 0) > 0.6
  );
  const anyRunning = visibleAgents.some(a => getAgentStatus(a.id) === "running");
  const allDone = doneCount === total && total > 0;

  const pipelineSignal =
    flaggedAgents.length > 0 ? "flagged"
    : allDone ? "clear"
    : "active";

  return (
    <div className="fc-surface-quiet rounded-2xl overflow-hidden min-w-[220px] max-w-[270px] flex flex-col">
      {/* Pipeline signal header */}
      <div className="px-5 pt-4 pb-3 border-b border-white/5">
        <div className="flex items-center justify-between mb-2.5">
          <span className="fc-eyebrow fc-text-muted">Pipeline</span>
          <span className={clsx(
            "text-xs font-mono font-bold tabular-nums",
            pipelineSignal === "flagged" ? "text-danger" :
            pipelineSignal === "clear"   ? "text-success" :
                                           "text-primary"
          )}>
            {doneCount}/{total}
          </span>
        </div>

        {/* Progress bar */}
        <div className="relative w-full h-[3px] bg-white/8 rounded-full overflow-hidden">
          <motion.div
            className={clsx(
              "absolute top-0 bottom-0 left-0 rounded-full",
              pipelineSignal === "flagged" ? "bg-danger" :
              pipelineSignal === "clear"   ? "bg-success" :
                                             "bg-primary"
            )}
            animate={{ width: total > 0 ? `${(doneCount / total) * 100}%` : "0%" }}
            transition={{ duration: 0.2, ease: "easeOut" }}
          />
        </div>

        {/* Signal label */}
        <p className={clsx(
          "text-xs font-semibold mt-2",
          pipelineSignal === "flagged" ? "text-danger" :
          pipelineSignal === "clear"   ? "text-success" :
                                         "text-primary"
        )}>
          {pipelineSignal === "flagged"
            ? `${flaggedAgents.length} specialist${flaggedAgents.length > 1 ? "s" : ""} flagged`
            : pipelineSignal === "clear"
            ? "All clear"
            : anyRunning ? "Scanning in progress" : "Initializing specialists"}
        </p>
      </div>

      {/* Per-agent rows */}
      <div className="flex flex-col py-2">
        {visibleAgents.map((agent) => {
          const status = getAgentStatus(agent.id);
          const completed = completedAgents?.find((c) => c.agent_id === agent.id);
          const isAlert = ALERT_VERDICTS.has(completed?.agent_verdict || "") || (completed?.verdict_score ?? 0) > 0.6;
          const accent = accentFor(agent.id);
          const Icon = AGENT_ICONS[agent.id] ?? Activity;
          const confidence = completed?.confidence != null
            ? Math.round(completed.confidence * 100)
            : null;

          return (
            <div
              key={agent.id}
              className="flex items-center gap-3 px-5 py-2.5 hover:bg-white/2 transition-colors"
            >
              <Icon className={clsx(
                "w-3.5 h-3.5 shrink-0 transition-opacity",
                status === "waiting" ? "opacity-30" : "",
                status === "complete" || status === "running" ? accent.textClass : "text-white/30"
              )} />

              <span className={clsx(
                "text-xs font-medium min-w-0 flex-1 truncate",
                status === "waiting" ? "fc-text-faint" : "fc-text-secondary"
              )}>
                {agent.name}
              </span>

              {status === "running" && (
                <span className="flex items-center gap-1 shrink-0">
                  <motion.div
                    className="w-1.5 h-1.5 rounded-full bg-primary"
                    animate={{ opacity: [1, 0.3, 1] }}
                    transition={{ duration: 1.2, repeat: Infinity }}
                  />
                </span>
              )}
              {status === "complete" && completed && (
                <span className={clsx(
                  "text-xs font-mono font-bold tabular-nums shrink-0",
                  isAlert ? "text-danger" :
                  (completed.agent_verdict === "INCONCLUSIVE") ? "text-warning" :
                  "text-success"
                )}>
                  {confidence != null ? `${confidence}%` : normalizeVerdict(completed.agent_verdict)}
                </span>
              )}
              {status === "error" && (
                <span className="text-xs font-mono font-bold text-danger shrink-0">Err</span>
              )}
              {status === "waiting" && (
                <span className="w-1.5 h-1.5 rounded-full bg-white/10 shrink-0" />
              )}
            </div>
          );
        })}
      </div>

      {/* Verdict strip — only when all complete */}
      {completedAgents.length > 0 && allDone && (
        <div className="border-t border-white/5 px-5 py-3">
          <div className="flex flex-wrap gap-1.5">
            {completedAgents
              .filter(a => a.agent_verdict)
              .map(a => {
                const isAlert = ALERT_VERDICTS.has(a.agent_verdict || "") || (a.verdict_score ?? 0) > 0.6;
                const isInconclusive = a.agent_verdict === "INCONCLUSIVE";
                return (
                  <span
                    key={a.agent_id}
                    className={clsx(
                      "fc-badge",
                      isAlert ? "fc-badge-danger" : isInconclusive ? "fc-badge-warning" : "fc-badge-success"
                    )}
                    title={`${a.agent_name}: ${normalizeVerdict(a.agent_verdict)}`}
                  >
                    {normalizeVerdict(a.agent_verdict)}
                  </span>
                );
              })}
          </div>
        </div>
      )}

      {/* Skipped agents — compact footer */}
      {skippedAgents.length > 0 && (
        <div className="border-t border-white/5 px-5 py-3 flex items-center gap-2">
          <SkipForward className="w-3 h-3 fc-text-faint shrink-0" />
          <span className="text-xs fc-text-faint truncate">
            {skippedAgents.map(a => a.name).join(", ")} skipped
          </span>
        </div>
      )}
    </div>
  );
}
