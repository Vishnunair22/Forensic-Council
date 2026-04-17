"use client";

import React, { useMemo } from "react";
import { Clock } from "lucide-react";
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

  // Derive Synthesis Phase (from the time the last agent finished to the time the report was signed)
  const lastAgentTime = useMemo(() => {
    if (agentTimeline.length === 0) return null;
    const comps = agentTimeline.map(u => u.completed_at).filter(Boolean) as string[];
    if (comps.length === 0) return null;
    return new Date(Math.max(...comps.map(c => new Date(c).getTime()))).toISOString();
  }, [agentTimeline]);

  return (
    <section aria-label="Forensic Execution Timeline" className="space-y-6 pt-4">
      <div className="flex items-center gap-3 px-1">
        <Clock className="w-4 h-4 text-white/20" />
        <h2 className="text-[10px] font-bold tracking-[0.2em] text-white/50">
          Forensic Execution Lifecycle
        </h2>
      </div>

      <div className="rounded-[2.5rem] border border-white/5 overflow-hidden glass-panel">
        {/* Timeline Header */}
        <div className="px-10 py-8 border-b border-white/5 bg-white/[0.01] flex items-center justify-between">
          <div className="flex flex-col gap-1">
            <h3 className="text-lg font-bold text-white/70">
              Sequence Registry
            </h3>
            <p className="text-[11px] font-medium text-white/20 tracking-wide">Atomic tool execution and consensus deliberation</p>
          </div>
          {pipelineStartAt && report.signed_utc && (
            <div className="px-4 py-2 rounded-full bg-white/[0.03] border border-white/10 text-[10px] font-bold text-cyan-400/60">
              Cycle Time: {fmtDuration(pipelineStartAt, report.signed_utc)}
            </div>
          )}
        </div>

        <div className="p-10">
          <div className="relative pl-10 border-l border-white/[0.05] space-y-16 ml-2">
            
            {/* 1. Evidence Ingress Phase */}
            {pipelineStartAt && (
              <div className="relative group">
                <div className="absolute -left-[49px] top-1 w-4 h-4 rounded-full border border-white/10 bg-white/5 shadow-xl transition-all group-hover:bg-cyan-500/20" />
                <div className="space-y-1">
                  <span className="text-[10px] font-bold text-cyan-500/40 tracking-widest">Phase 01</span>
                  <h4 className="text-sm font-bold text-white/70">Evidence Ingress</h4>
                  <p className="text-[11px] text-white/50 font-medium leading-relaxed max-w-xl">
                    Secure intake of forensic evidence. Metadata extraction and integrity pre-check completed.
                  </p>
                  <div className="pt-2 text-[10px] font-mono text-white/10">{fmtTime(pipelineStartAt)} {"//"} Transmission Secured</div>
                </div>
              </div>
            )}

            {/* 2. Tool Volley Phase */}
            <div className="relative group">
              <div className="absolute -left-[49px] top-1 w-4 h-4 rounded-full border border-white/20 bg-emerald-500/20 shadow-[0_0_20px_rgba(16,185,129,0.1)]" />
              <div className="space-y-6">
                <div className="space-y-1">
                  <span className="text-[10px] font-bold text-emerald-500/40 tracking-widest">Phase 02</span>
                  <h4 className="text-sm font-bold text-white/70">Tool Volley</h4>
                  <p className="text-[11px] text-white/50 font-medium leading-relaxed max-w-xl">
                    Parallel execution of deep neural probes and investigative agents.
                  </p>
                </div>

                <div className="grid gap-3">
                  {hasLiveTimeline ? (
                    agentTimeline.map((update, idx) => {
                      const theme = AGENT_THEMES[update.agent_id ?? ""] || { dot: "bg-white/20", text: "text-white/40", bg: "bg-white/5" };
                      // const isComplete = !!update.completed_at;

                      return (
                        <div key={idx} className="flex items-center gap-4 p-4 rounded-2xl bg-white/[0.01] border border-white/5 hover:bg-white/[0.02] transition-colors">
                          <div className={clsx("w-2 h-2 rounded-full", theme.dot)} />
                          <div className="flex-1 min-w-0">
                            <h5 className={clsx("text-[11px] font-bold", theme.text)}>
                              {update.agent_name || update.agent_id}
                            </h5>
                            <p className="text-[10px] text-white/20 truncate">{update.message || "Executing investigative probe..."}</p>
                          </div>
                          {update.completed_at && (
                            <span className="text-[10px] font-mono text-white/10 shrink-0">
                              {fmtTime(update.completed_at)}
                            </span>
                          )}
                        </div>
                      );
                    })
                  ) : (
                    activeAgentIds.map((agentId) => {
                      const metrics = report.per_agent_metrics?.[agentId];
                      const theme = AGENT_THEMES[agentId] || { dot: "bg-white/20", text: "text-white/40", bg: "bg-white/5" };
                      return (
                        <div key={agentId} className="flex items-center gap-4 p-4 rounded-2xl bg-white/[0.01] border border-white/5">
                           <div className={clsx("w-2 h-2 rounded-full", theme.dot)} />
                           <span className={clsx("text-[11px] font-bold", theme.text)}>{metrics?.agent_name || agentId}</span>
                           <span className="ml-auto text-[10px] font-mono text-white/10">Verification Protocol Applied</span>
                        </div>
                      );
                    })
                  )}
                </div>
              </div>
            </div>

            {/* 3. Synthesis Phase */}
            {report.signed_utc && (
              <div className="relative group">
                <div className="absolute -left-[49px] top-1 w-4 h-4 rounded-full border border-white/20 bg-violet-500/20 shadow-[0_0_20px_rgba(139,92,246,0.1)]" />
                <div className="space-y-1">
                  <span className="text-[10px] font-bold text-violet-500/40 tracking-widest">Phase 03</span>
                  <h4 className="text-sm font-bold text-white/70">Council Synthesis</h4>
                  <p className="text-[11px] text-white/50 font-medium leading-relaxed max-w-xl">
                    Arbiter consolidation of all agent findings. Final verdict calculation and cryptographic signing.
                  </p>
                  <div className="pt-2 text-[10px] font-mono text-white/10">
                    {fmtTime(report.signed_utc)} {"//"} Consensus Reached 
                    {lastAgentTime && ` // ${fmtDuration(lastAgentTime, report.signed_utc)} deliberation`}
                  </div>
                </div>
              </div>
            )}

          </div>
        </div>
      </div>
    </section>
  );
}

function fmtTime(iso: string): string {
  try {
    const d = new Date(iso);
    return `${d.getHours().toString().padStart(2, '0')}:${d.getMinutes().toString().padStart(2, '0')}:${d.getSeconds().toString().padStart(2, '0')}:${d.getMilliseconds().toString().padStart(3, '0')}`;
  } catch { return iso; }
}

function fmtDuration(from: string, to: string): string {
  try {
    const ms = new Date(to).getTime() - new Date(from).getTime();
    if (ms < 0) return "—";
    if (ms < 1000) return `${ms}ms`;
    if (ms < 60000) return `${(ms / 1000).toFixed(1)}s`;
    return `${Math.floor(ms / 60000)}m ${Math.floor((ms % 60000) / 1000)}s`;
  } catch { return "—"; }
}
