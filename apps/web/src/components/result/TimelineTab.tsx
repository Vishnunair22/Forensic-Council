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
  Agent1: { dot: "bg-primary", text: "text-primary", bg: "bg-primary/5" },
  Agent2: { dot: "bg-primary", text: "text-primary", bg: "bg-primary/5" },
  Agent3: { dot: "bg-warning", text: "text-warning", bg: "bg-warning/5" },
  Agent4: { dot: "bg-danger", text: "text-danger", bg: "bg-danger/5" },
  Agent5: { dot: "bg-accent", text: "text-accent", bg: "bg-accent/5" },
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

      <div className="rounded-[2.5rem] border border-border-subtle overflow-hidden premium-glass">
        {/* Timeline Header */}
        <div className="px-10 py-8 border-b border-border-subtle bg-surface-low/50 flex items-center justify-between">
          <div className="flex flex-col gap-1">
            <h3 className="text-lg font-black text-white uppercase tracking-tighter">
              Sequence Registry
            </h3>
            <p className="text-[10px] font-black text-white/20 tracking-[0.3em] uppercase">Atomic tool execution and consensus deliberation</p>
          </div>
          {pipelineStartAt && report.signed_utc && (
            <div className="px-4 py-2 rounded-full bg-surface-1 border border-border-subtle text-[10px] font-black text-primary uppercase tracking-[0.2em] shadow-inner">
              Cycle Time: {fmtDuration(pipelineStartAt, report.signed_utc)}
            </div>
          )}
        </div>

        <div className="p-10">
          <div className="relative pl-10 border-l border-white/[0.05] space-y-16 ml-2">
            
            {/* 1. Evidence Ingress Phase */}
            {pipelineStartAt && (
              <div className="relative group">
                <div className="absolute -left-[49px] top-1 w-4 h-4 rounded-full border border-border-subtle bg-surface-low shadow-xl transition-all group-hover:bg-primary/20" />
                <div className="space-y-1">
                  <span className="text-[10px] font-black text-primary/40 tracking-[0.4em] uppercase">Phase 01</span>
                  <h4 className="text-sm font-black text-white/80 uppercase tracking-tighter">Evidence Ingress</h4>
                  <p className="text-[11px] text-white/50 font-medium leading-relaxed max-w-xl">
                    Secure intake of forensic evidence. Metadata extraction and integrity pre-check completed.
                  </p>
                  <div className="pt-2 text-[10px] font-mono text-white/10 uppercase tracking-tight">[{fmtTime(pipelineStartAt)}] TRANSMISSION_SECURED</div>
                </div>
              </div>
            )}

            {/* 2. Tool Volley Phase */}
            <div className="relative group">
              <div className="absolute -left-[49px] top-1 w-4 h-4 rounded-full border border-primary/30 bg-primary/20 shadow-[0_0_20px_rgba(34,211,238,0.2)]" />
              <div className="space-y-6">
                <div className="space-y-1">
                  <span className="text-[10px] font-black text-primary/40 tracking-[0.4em] uppercase">Phase 02</span>
                  <h4 className="text-sm font-black text-white/80 uppercase tracking-tighter">Tool Volley</h4>
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
                        <div key={idx} className="flex items-center gap-4 p-4 rounded-2xl premium-card group transition-colors">
                          <div className={clsx("w-2 h-2 rounded-full", theme.dot)} />
                          <div className="flex-1 min-w-0">
                            <h5 className={clsx("text-[10px] font-black uppercase tracking-widest", theme.text)}>
                              {update.agent_name || update.agent_id}
                            </h5>
                            <p className="text-[10px] font-mono font-black text-white/20 truncate uppercase tracking-tight">{update.message || "Executing investigative probe..."}</p>
                          </div>
                          {update.completed_at && (
                            <span className="text-[10px] font-mono text-white/10 shrink-0 uppercase">
                              [{fmtTime(update.completed_at)}]
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
                <div className="absolute -left-[49px] top-1 w-4 h-4 rounded-full border border-accent/30 bg-accent/20 shadow-[0_0_20px_rgba(139,92,246,0.2)]" />
                <div className="space-y-1">
                  <span className="text-[10px] font-black text-accent/40 tracking-[0.4em] uppercase">Phase 03</span>
                  <h4 className="text-sm font-black text-white/80 uppercase tracking-tighter">Council Synthesis</h4>
                  <p className="text-[11px] text-white/50 font-medium leading-relaxed max-w-xl">
                    Arbiter consolidation of all agent findings. Final verdict calculation and cryptographic signing.
                  </p>
                  <div className="pt-2 text-[10px] font-mono text-white/10 uppercase tracking-tight">
                    [{fmtTime(report.signed_utc)}] CONSENSUS_REACHED 
                    {lastAgentTime && ` // DELIBERATION: ${fmtDuration(lastAgentTime, report.signed_utc)}`}
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
