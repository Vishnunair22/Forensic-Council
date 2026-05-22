"use client";

import React from "react";
import { Clock } from "lucide-react";
import { clsx } from "clsx";
import { fmtTime, fmtDuration } from "@/lib/fmt";
import { accentFor } from "@/lib/agentTheme";
import type { ReportDTO } from "@/lib/api";
import type { AgentUpdate } from "@/components/evidence/types";

interface ExecutionTimelineProps {
  report: ReportDTO;
  activeAgentIds: string[];
  agentTimeline: AgentUpdate[];
  pipelineStartAt: string | null;
}

const AGENT_LABELS: Record<string, string> = {
  Agent1: "Image Analysis",
  Agent2: "Audio Analysis",
  Agent3: "Object Detection",
  Agent4: "Video Analysis",
  Agent5: "Metadata Analysis",
};

export function ExecutionTimeline({
  report,
  activeAgentIds,
  agentTimeline,
  pipelineStartAt,
}: ExecutionTimelineProps) {
  const hasLiveTimeline = agentTimeline.length > 0;

  const steps: Array<{
    key: string;
    label: string;
    time: string | null;
    dot: "start" | "agent" | "synthesis" | "complete" | "skip";
    agentId?: string;
    duration?: string;
  }> = [];

  // Upload / Evidence Ingress
  if (pipelineStartAt) {
    steps.push({
      key: "upload",
      label: "Evidence Ingested",
      time: fmtTime(pipelineStartAt),
      dot: "start",
    });
  }

  if (hasLiveTimeline) {
    for (const update of agentTimeline) {
      const agentId = update.agent_id;
      const label = AGENT_LABELS[agentId] ?? agentId;
      const skipped = !activeAgentIds.includes(agentId);
      steps.push({
        key: agentId,
        label: skipped ? `${label} (Skipped)` : label,
        time: update.completed_at ? fmtTime(update.completed_at) : null,
        dot: skipped ? "skip" : "agent",
        agentId,
        duration: undefined,
      });
    }
  } else {
    for (const agentId of activeAgentIds) {
      steps.push({
        key: agentId,
        label: AGENT_LABELS[agentId] ?? agentId,
        time: null,
        dot: "agent",
        agentId,
      });
    }
  }

  // Report complete (signed_utc is when synthesis + signing finished)
  if (report.signed_utc) {
    steps.push({
      key: "complete",
      label: "Report Signed & Sealed",
      time: fmtTime(report.signed_utc),
      dot: "complete",
      duration: pipelineStartAt
        ? fmtDuration(pipelineStartAt, report.signed_utc)
        : undefined,
    });
  } else {
    steps.push({
      key: "complete",
      label: "Report Generated",
      time: null,
      dot: "complete",
    });
  }

  return (
    <section className="rounded-2xl border border-white/[0.06] overflow-hidden" aria-label="Execution timeline">
      <div className="px-6 py-4 border-b border-white/[0.06] flex items-center justify-between gap-3">
        <div className="flex items-center gap-2">
          <Clock className="w-4 h-4 text-primary/60" />
          <h2 className="text-sm font-bold text-white/85">Execution Timeline</h2>
        </div>
        {pipelineStartAt && report.signed_utc && (
          <span className="fc-eyebrow fc-text-faint">
            Total: {fmtDuration(pipelineStartAt, report.signed_utc)}
          </span>
        )}
      </div>

      <div className="p-6 relative">
        {/* Vertical line */}
        <div className="absolute left-9 top-6 bottom-6 w-px bg-white/[0.06]" />

        <div className="space-y-6">
          {steps.map((step) => {
            const accent = step.agentId ? accentFor(step.agentId) : null;
            return (
              <div key={step.key} className="relative pl-12">
                {/* Dot */}
                <div
                  className={clsx(
                    "absolute left-[26px] top-1 w-2.5 h-2.5 rounded-full border",
                    step.dot === "start"    && "bg-white/30 border-white/50",
                    step.dot === "agent"    && "border-white/20",
                    step.dot === "synthesis"&& "bg-success/20 border-success/40",
                    step.dot === "complete" && "bg-success border-success",
                    step.dot === "skip"     && "bg-transparent border-white/15"
                  )}
                  style={step.dot === "agent" && accent ? {
                    backgroundColor: `${accent.color}30`,
                    borderColor: `${accent.color}60`,
                  } : undefined}
                />

                <div className="flex items-start justify-between gap-4">
                  <div>
                    <p
                      className={clsx(
                        "text-sm font-medium leading-tight",
                        step.dot === "skip" ? "fc-text-faint" : "text-white/75",
                        step.dot === "complete" && "text-success"
                      )}
                      style={step.dot === "agent" && accent ? { color: accent.color } : undefined}
                    >
                      {step.label}
                    </p>
                    {step.duration && (
                      <p className="text-xs font-mono fc-text-faint mt-0.5">{step.duration}</p>
                    )}
                  </div>
                  {step.time && (
                    <span className="text-xs font-mono fc-text-faint shrink-0">{step.time}</span>
                  )}
                </div>
              </div>
            );
          })}
        </div>
      </div>
    </section>
  );
}
