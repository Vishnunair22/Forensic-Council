"use client";

import React from "react";
import { Clock } from "lucide-react";
import { motion } from "framer-motion";
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
    <section className="relative flex flex-col overflow-hidden fc-surface" aria-label="Execution timeline">
      <div className="px-6 py-4 border-b border-white/[0.06] flex items-center justify-between gap-3">
        <div className="flex items-center gap-2">
          <Clock className="w-4 h-4 text-primary/60" />
          <h2 className="text-sm font-bold fc-text-secondary">Execution Timeline</h2>
        </div>
        {pipelineStartAt && report.signed_utc && (
          <span className="fc-eyebrow fc-text-muted">
            Total: {fmtDuration(pipelineStartAt, report.signed_utc)}
          </span>
        )}
      </div>

      <div className="p-6 relative">
        {/* The Tactical Guide Line */}
        <div className="absolute left-[38px] top-8 bottom-8 w-[2px] bg-white/[0.05] rounded-full overflow-hidden">
          {/* Animated Data Tracer */}
          <motion.div
            className="absolute top-0 w-full h-32 bg-gradient-to-b from-transparent via-primary/50 to-primary shadow-[0_0_10px_rgba(var(--color-primary-rgb),1)]"
            animate={{ top: ["-20%", "120%"] }}
            transition={{ duration: 2.5, repeat: Infinity, ease: "linear" }}
          />
        </div>

        <div className="space-y-7 relative z-10">
          {steps.map((step, index) => {
            const accent = step.agentId ? accentFor(step.agentId) : null;
            const isComplete = step.dot === "complete";

            return (
              <motion.div
                key={step.key}
                initial={{ opacity: 0, x: -10 }}
                whileInView={{ opacity: 1, x: 0 }}
                viewport={{ once: true }}
                transition={{ duration: 0.3, delay: index * 0.1 }}
                className="relative flex items-start gap-5 pl-4"
              >
                {/* Tactical Crosshair / Node */}
                <div
                  className={clsx(
                    "relative flex items-center justify-center w-6 h-6 shrink-0 bg-background border rounded shadow-sm z-10 mt-0.5",
                    step.dot === "start"    && "border-white/30 text-white/50",
                    step.dot === "agent"    && "border-white/20",
                    step.dot === "synthesis"&& "border-success/40 text-success/50 bg-success/5",
                    step.dot === "complete" && "border-success bg-success/10",
                    step.dot === "skip"     && "border-white/10 border-dashed"
                  )}
                  style={step.dot === "agent" && accent ? {
                    borderColor: `${accent.color}50`,
                    backgroundColor: `${accent.color}10`,
                  } : undefined}
                >
                  {isComplete ? (
                     <div className="w-2 h-2 rounded-full bg-success shadow-[0_0_8px_rgba(var(--color-success-rgb),0.8)]" />
                  ) : (
                     <span className="text-[10px] font-mono leading-none" style={accent ? { color: accent.color } : {}}>+</span>
                  )}
                </div>

                <div className="flex-1 flex items-start justify-between gap-4 pt-1">
                  <div>
                    <p
                      className={clsx(
                        "text-sm font-mono tracking-wide uppercase",
                        step.dot === "skip" ? "fc-text-muted opacity-50" : "fc-text-secondary",
                        step.dot === "complete" && "text-success font-bold drop-shadow-sm"
                      )}
                      style={step.dot === "agent" && accent ? { color: accent.color } : undefined}
                    >
                      {step.label}
                    </p>
                    {step.duration && (
                      <p className="text-xs font-mono fc-text-muted mt-1.5 flex items-center gap-1.5">
                        <span className="w-1 h-1 bg-white/20 rounded-full" />
                        Latency: {step.duration}
                      </p>
                    )}
                  </div>

                  {/* Server-style Timestamp */}
                  {step.time && (
                    <div className="shrink-0 bg-black/40 border border-white/5 rounded px-2 py-1 flex items-center">
                      <span className="text-xs font-mono text-primary/70">{step.time}</span>
                    </div>
                  )}
                </div>
              </motion.div>
            );
          })}
        </div>
      </div>
    </section>
  );
}
