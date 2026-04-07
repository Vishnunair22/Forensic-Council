"use client";

import React from "react";
import { CheckCircle2, Clock, Activity, AlertTriangle, ShieldCheck } from "lucide-react";
import { clsx } from "clsx";
import type { ReportDTO } from "@/lib/api";
import type { AgentUpdate } from "@/components/evidence/AgentProgressDisplay";

interface TimelineTabProps {
  report: ReportDTO;
  activeAgentIds: string[];
  agentTimeline: AgentUpdate[];
  pipelineStartAt: string | null;
}

const AGENT_THEMES: Record<string, { dot: string; text: string; bg: string }> = {
  Agent1: { dot: "bg-cyan-400", text: "text-cyan-400", bg: "bg-cyan-500/5" },
  Agent2: { dot: "bg-blue-400", text: "text-blue-400", bg: "bg-blue-500/5" },
  Agent3: { dot: "bg-amber-400", text: "text-amber-400", bg: "bg-amber-500/5" },
  Agent4: { dot: "bg-teal-400", text: "text-teal-400", bg: "bg-teal-500/5" },
  Agent5: { dot: "bg-violet-400", text: "text-violet-400", bg: "bg-violet-500/5" },
};

export function TimelineTab({
  report,
  activeAgentIds,
  agentTimeline,
  pipelineStartAt,
}: TimelineTabProps) {
  const hasLiveTimeline = agentTimeline.length > 0;

  return (
    <section aria-label="Forensic Execution Timeline" className="space-y-6">
      <div className="flex items-center gap-3 px-1">
        <Clock className="w-4 h-4 text-white/20" />
        <h2 className="text-[10px] font-black font-mono uppercase tracking-[0.3em] text-white/30">
          Neural Execution Timeline
        </h2>
      </div>

      <div className="rounded-3xl border border-white/5 overflow-hidden glass-panel">
        {/* Timeline Header */}
        <div className="px-8 py-5 border-b border-white/5 bg-white/[0.02] flex items-center justify-between">
          <div className="flex items-center gap-3">
            <ShieldCheck className="w-4 h-4 text-cyan-400/50" />
            <span className="text-[11px] font-black uppercase tracking-widest text-white/60 font-heading">
              Pipeline Sequence
            </span>
          </div>
          {pipelineStartAt && report.signed_utc && (
            <div className="px-3 py-1 rounded-full bg-cyan-400/5 border border-cyan-400/10 text-[9px] font-mono text-cyan-400/60 font-bold uppercase tracking-widest">
              Total Duration: {fmtDuration(pipelineStartAt, report.signed_utc)}
            </div>
          )}
        </div>

        <div className="p-10">
          <div className="relative pl-8 border-l border-white/5 space-y-12 ml-4">
            {hasLiveTimeline ? (
              /* ── High-Fidelity Live Timeline ── */
              agentTimeline.map((update, idx) => {
                const theme = AGENT_THEMES[update.agent_id ?? ""] || { dot: "bg-white/20", text: "text-white/40", bg: "bg-white/5" };
                const isComplete = !!update.completed_at;

                return (
                  <div key={idx} className="relative group">
                    {/* Node Dot */}
                    <div className={clsx(
                      "absolute -left-[37px] top-1 w-4 h-4 rounded-full border-2 border-[#06090F] transition-all duration-500",
                      theme.dot,
                      !isComplete ? "animate-pulse shadow-[0_0_15px_rgba(255,255,255,0.3)]" : "shadow-none"
                    )} />
                    
                    <div className="flex flex-col md:flex-row md:items-start justify-between gap-4">
                      <div className="space-y-1">
                        <h4 className={clsx("text-xs font-black uppercase tracking-widest", theme.text)}>
                          {update.agent_name || update.agent_id}
                        </h4>
                        {update.message && (
                          <p className="text-[11px] text-white/40 font-mono italic leading-relaxed max-w-xl">
                            {update.message}
                          </p>
                        )}
                      </div>
                      
                      <div className="flex items-center gap-4 shrink-0 self-end md:self-start">
                        {update.completed_at && (
                          <span className="text-[10px] font-mono text-white/10 font-black">
                            {fmtTime(update.completed_at)}
                          </span>
                        )}
                        <div className={clsx(
                          "w-8 h-8 rounded-lg flex items-center justify-center border transition-all duration-500",
                          isComplete ? "bg-emerald-500/5 border-emerald-500/20 text-emerald-400" : "bg-cyan-500/5 border-cyan-500/20 text-cyan-400"
                        )}>
                          {isComplete ? <CheckCircle2 className="w-4 h-4" /> : <Activity className="w-4 h-4 animate-spin-slow" />}
                        </div>
                      </div>
                    </div>
                  </div>
                );
              })
            ) : (
              /* ── Derived Static Summary ── */
              activeAgentIds.map((agentId) => {
                const metrics = report.per_agent_metrics?.[agentId];
                const theme = AGENT_THEMES[agentId] || { dot: "bg-white/20", text: "text-white/40", bg: "bg-white/5" };
                const isSkipped = metrics?.skipped;

                return (
                  <div key={agentId} className="relative">
                    <div className={clsx(
                      "absolute -left-[37px] top-1 w-4 h-4 rounded-full border-2 border-[#06090F]",
                      isSkipped ? "bg-white/10" : theme.dot
                    )} />
                    <div className="flex items-start justify-between gap-4">
                      <div className="space-y-1">
                        <h4 className={clsx("text-xs font-black uppercase tracking-widest", isSkipped ? "text-white/20" : theme.text)}>
                          {metrics?.agent_name || agentId}
                        </h4>
                        {!isSkipped && (
                          <p className="text-[10px] font-mono font-bold text-white/30 uppercase tracking-widest">
                            {metrics?.tools_succeeded}/{metrics?.total_tools_called} Probes Verified · {Math.round((metrics?.confidence_score || 0) * 100)}% Conf
                          </p>
                        )}
                        {isSkipped && <p className="text-[10px] font-mono text-white/10 italic">Agent skipped by protocol</p>}
                      </div>
                      <div className={clsx(
                        "w-8 h-8 rounded-lg flex items-center justify-center border",
                        isSkipped ? "border-white/5 text-white/10" : "bg-emerald-500/5 border-emerald-500/20 text-emerald-400"
                      )}>
                        {isSkipped ? <AlertTriangle className="w-4 h-4" /> : <CheckCircle2 className="w-4 h-4" />}
                      </div>
                    </div>
                  </div>
                );
              })
            )}
          </div>
        </div>
      </div>
    </section>
  );
}

function fmtTime(iso: string): string {
  try {
    return new Date(iso).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit", second: "2-digit" });
  } catch { return iso; }
}

function fmtDuration(from: string, to: string): string {
  try {
    const ms = new Date(to).getTime() - new Date(from).getTime();
    if (ms < 0) return "—";
    if (ms < 1000) return `${ms}ms`;
    return `${(ms / 1000).toFixed(1)}s`;
  } catch { return "—"; }
}
