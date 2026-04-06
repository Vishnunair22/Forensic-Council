"use client";

import { CheckCircle2, Clock, Activity, AlertTriangle } from "lucide-react";
import clsx from "clsx";
import type { ReportDTO } from "@/lib/api";
import type { AgentUpdate } from "@/components/evidence/AgentProgressDisplay";
import { SurfaceCard } from "@/components/ui/SurfaceCard";

interface TimelineTabProps {
  report: ReportDTO;
  activeAgentIds: string[];
  agentTimeline: AgentUpdate[];
  pipelineStartAt: string | null;
}

function fmtTime(iso: string): string {
  try {
    return new Date(iso).toLocaleTimeString([], {
      hour: "2-digit",
      minute: "2-digit",
      second: "2-digit",
    });
  } catch {
    return iso;
  }
}

function fmtDuration(from: string, to: string): string {
  try {
    const ms = new Date(to).getTime() - new Date(from).getTime();
    if (ms < 0) return "—";
    if (ms < 1000) return `${ms}ms`;
    return `${(ms / 1000).toFixed(1)}s`;
  } catch {
    return "—";
  }
}

const AGENT_COLORS: Record<string, { dot: string; label: string }> = {
  Agent1: { dot: "bg-cyan-400",   label: "text-cyan-400" },
  Agent2: { dot: "bg-indigo-400", label: "text-indigo-400" },
  Agent3: { dot: "bg-sky-400",    label: "text-sky-400" },
  Agent4: { dot: "bg-teal-400",   label: "text-teal-400" },
  Agent5: { dot: "bg-blue-400",   label: "text-blue-400" },
};

export function TimelineTab({
  report,
  activeAgentIds,
  agentTimeline,
  pipelineStartAt,
}: TimelineTabProps) {
  // If we have a live timeline from the websocket, render that
  const hasLiveTimeline = agentTimeline.length > 0;

  return (
    <section aria-label="Agent execution timeline">
      <div className="flex items-center gap-2 mb-4">
        <Clock className="w-3.5 h-3.5 text-white/30" aria-hidden="true" />
        <h2 className="text-[10px] font-mono font-bold uppercase tracking-widest text-white/35">
          Execution Timeline
        </h2>
      </div>

      <SurfaceCard className="p-0 overflow-hidden">
        {/* Header */}
        <div className="px-5 py-3.5 border-b border-white/[0.05] bg-white/[0.02] flex items-center justify-between">
          <div className="flex items-center gap-2">
            <Activity className="w-3.5 h-3.5 text-cyan-400/60" aria-hidden="true" />
            <span className="text-[10px] font-bold uppercase tracking-widest text-white/50">
              Pipeline Run
            </span>
          </div>
          {pipelineStartAt && report.signed_utc && (
            <span className="text-[9px] font-mono text-white/25">
              Total: {fmtDuration(pipelineStartAt, report.signed_utc)}
            </span>
          )}
        </div>

        <div className="p-5 space-y-3">
          {hasLiveTimeline ? (
            /* ── Live timeline from websocket ── */
            <ol className="relative border-l border-white/[0.06] ml-3 space-y-4" aria-label="Agent events">
              {agentTimeline.map((update, idx) => {
                const colors = AGENT_COLORS[update.agent_id ?? ""] ?? {
                  dot: "bg-white/30",
                  label: "text-white/50",
                };
                const isComplete = Boolean(update.completed_at);

                return (
                  <li key={idx} className="ml-5 relative">
                    {/* Dot */}
                    <span
                      className={clsx(
                        "absolute -left-[1.65rem] top-1 w-2.5 h-2.5 rounded-full border-2 border-black",
                        colors.dot,
                        !isComplete && "animate-pulse",
                      )}
                      aria-hidden="true"
                    />

                    <div className="flex items-start justify-between gap-3">
                      <div className="min-w-0">
                        <p
                          className={clsx(
                            "text-[11px] font-bold uppercase tracking-wide",
                            colors.label,
                          )}
                        >
                          {update.agent_name ?? update.agent_id}
                        </p>
                        {update.message && (
                          <p className="text-[10px] text-white/40 font-mono leading-relaxed mt-0.5 line-clamp-2">
                            {update.message}
                          </p>
                        )}
                      </div>

                      <div className="shrink-0 text-right space-y-1">
                        {update.completed_at && (
                          <p className="text-[9px] font-mono text-white/25">
                            {fmtTime(update.completed_at)}
                          </p>
                        )}
                        {isComplete ? (
                          <CheckCircle2
                            className="w-3.5 h-3.5 text-emerald-400/70 ml-auto"
                            aria-label="Complete"
                          />
                        ) : (
                          <Activity
                            className="w-3.5 h-3.5 text-cyan-400/60 ml-auto animate-pulse"
                            aria-label="Running"
                          />
                        )}
                      </div>
                    </div>
                  </li>
                );
              })}
            </ol>
          ) : (
            /* ── Fallback: derive from per_agent_metrics ── */
            activeAgentIds.length > 0 ? (
              <ol className="relative border-l border-white/[0.06] ml-3 space-y-4" aria-label="Agent summary">
                {activeAgentIds.map((agentId) => {
                  const metrics = report.per_agent_metrics?.[agentId];
                  const colors = AGENT_COLORS[agentId] ?? {
                    dot: "bg-white/30",
                    label: "text-white/50",
                  };
                  const isSkipped = metrics?.skipped ?? false;

                  return (
                    <li key={agentId} className="ml-5 relative">
                      <span
                        className={clsx(
                          "absolute -left-[1.65rem] top-1 w-2.5 h-2.5 rounded-full border-2 border-black",
                          isSkipped ? "bg-white/20" : colors.dot,
                        )}
                        aria-hidden="true"
                      />
                      <div className="flex items-start justify-between gap-3">
                        <div className="min-w-0">
                          <p
                            className={clsx(
                              "text-[11px] font-bold uppercase tracking-wide",
                              isSkipped ? "text-white/25" : colors.label,
                            )}
                          >
                            {metrics?.agent_name ?? agentId}
                          </p>
                          {metrics && !isSkipped && (
                            <p className="text-[10px] text-white/35 font-mono mt-0.5">
                              {metrics.tools_succeeded}/{metrics.total_tools_called} tools ·{" "}
                              {Math.round(metrics.confidence_score * 100)}% confidence
                            </p>
                          )}
                          {isSkipped && (
                            <p className="text-[10px] text-white/20 font-mono mt-0.5">
                              Skipped — file type not applicable
                            </p>
                          )}
                        </div>
                        <div className="shrink-0">
                          {isSkipped ? (
                            <AlertTriangle
                              className="w-3.5 h-3.5 text-white/20"
                              aria-label="Skipped"
                            />
                          ) : (
                            <CheckCircle2
                              className="w-3.5 h-3.5 text-emerald-400/70"
                              aria-label="Complete"
                            />
                          )}
                        </div>
                      </div>
                    </li>
                  );
                })}
              </ol>
            ) : (
              <p className="text-sm text-white/30 font-mono text-center py-4">
                No timeline data available.
              </p>
            )
          )}
        </div>
      </SurfaceCard>
    </section>
  );
}
