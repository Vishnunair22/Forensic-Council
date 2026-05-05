"use client";

import React, { useMemo } from "react";
import type { ReportDTO } from "@/lib/api";
import type { AgentUpdate } from "@/components/evidence/AgentProgressDisplay";
import { motion } from "framer-motion";

type TimelineItem = { agent_id: string } | AgentUpdate;

interface TimelineTabProps {
  report: ReportDTO;
  activeAgentIds: string[];
  agentTimeline: AgentUpdate[];
  pipelineStartAt: string | null;
}

const AGENT_THEMES: Record<string, { color: string }> = {
  Agent1: { color: "#00FFFF" },
  Agent2: { color: "#00FFFF" },
  Agent3: { color: "#F59E0B" },
  Agent4: { color: "#F43F5E" },
  Agent5: { color: "#8B5CF6" },
  Arbiter: { color: "#10B981" },
};

export function TimelineTab({
  report,
  activeAgentIds,
  agentTimeline,
  pipelineStartAt,
}: TimelineTabProps) {
  const hasLiveTimeline = agentTimeline.length > 0;

  const lastAgentTime = useMemo(() => {
    if (agentTimeline.length === 0) return null;
    const comps = agentTimeline.map(u => u.completed_at).filter(Boolean) as string[];
    if (comps.length === 0) return null;
    return new Date(Math.max(...comps.map(c => new Date(c).getTime()))).toISOString();
  }, [agentTimeline]);

  return (
    <section className="space-y-8">
      <div className="flex items-center gap-4">
         <span className="text-[10px] font-mono font-bold text-white/30 uppercase tracking-[0.3em]">Forensic_Execution_Lifecycle</span>
         <div className="h-px flex-1 bg-white/5" />
      </div>

      <div className="bg-[#070A12] border border-white/8 rounded-2xl shadow-[0_4px_24px_rgba(0,0,0,0.5),0_1px_0_rgba(255,255,255,0.04)_inset] overflow-hidden">
        <div className="bg-[#020617]/40">

          {/* Header */}
          <div className="px-10 py-8 border-b border-white/5 flex items-center justify-between gap-6">
            <div className="flex flex-col gap-1">
              <h3 className="text-xl font-heading font-bold text-white tracking-tight">Sequence Registry</h3>
              <p className="text-[10px] font-mono font-bold text-white/20 uppercase tracking-widest">Atomic_Tool_Execution_Logs</p>
            </div>
            {pipelineStartAt && report.signed_utc && (
              <div className="px-4 py-2 rounded-lg bg-primary/5 border border-primary/20 text-[10px] font-mono font-bold text-primary uppercase tracking-widest">
                Cycle_Time: {fmtDuration(pipelineStartAt, report.signed_utc)}
              </div>
            )}
          </div>

          <div className="p-12 relative">
            {/* Timeline Line */}
            <div className="absolute left-12 top-12 bottom-12 w-px bg-white/5" />

            <div className="space-y-16">

              {/* 1. Evidence Ingress */}
              {pipelineStartAt && (
                <div className="relative pl-10">
                  <div className="absolute left-[-5px] top-1.5 w-2.5 h-2.5 rounded-full bg-white/10 border border-white/20 shadow-[0_0_10px_rgba(255,255,255,0.1)]" />
                  <div className="space-y-2">
                    <span className="text-[9px] font-mono font-bold text-primary/40 uppercase tracking-[0.2em]">Phase_01</span>
                    <h4 className="text-sm font-heading font-bold text-white/80">Evidence Ingress</h4>
                    <p className="text-xs text-white/40 leading-relaxed max-w-xl italic">
                      Secure intake of forensic evidence. Metadata extraction and integrity pre-check completed.
                    </p>
                    <div className="text-[10px] font-mono text-white/20">[{fmtTime(pipelineStartAt)}] Transmission_Secured</div>
                  </div>
                </div>
              )}

              {/* 2. Tool Execution Nodes */}
              <div className="relative pl-10">
                <div className="absolute left-[-5px] top-1.5 w-2.5 h-2.5 rounded-full bg-primary shadow-[0_0_10px_#00FFFF]" />
                <div className="space-y-8">
                  <div className="space-y-2">
                    <span className="text-[9px] font-mono font-bold text-primary/40 uppercase tracking-[0.2em]">Phase_02</span>
                    <h4 className="text-sm font-heading font-bold text-white/80">Forensic Agent Scans</h4>
                    <p className="text-xs text-white/40 leading-relaxed max-w-xl italic">
                      Execution of deep neural probes and specialized investigative agents.
                    </p>
                  </div>

                  <div className="grid gap-4 max-w-2xl">
                    {(hasLiveTimeline ? agentTimeline : activeAgentIds.map(id => ({ agent_id: id }))).map((update: TimelineItem, idx) => {
                      const agentId = update.agent_id;
                      const theme = AGENT_THEMES[agentId] || { color: "#00FFFF" };
                      const completionTime = "completed_at" in update ? update.completed_at : null;
                      const duration = (pipelineStartAt && completionTime) ? fmtDuration(pipelineStartAt, completionTime) : null;

                      return (
                        <motion.div
                          key={idx}
                          initial={{ opacity: 0, x: -10 }}
                          animate={{ opacity: 1, x: 0 }}
                          className="flex items-center gap-4 p-4 rounded-xl border border-white/5 bg-white/[0.02] group"
                        >
                          <div className="w-2 h-2 rounded-full shrink-0" style={{ backgroundColor: theme.color, boxShadow: `0 0 10px ${theme.color}` }} />
                          <div className="flex-1">
                            <span className="text-[10px] font-mono font-bold uppercase tracking-widest" style={{ color: theme.color }}>
                              {"agent_name" in update ? update.agent_name : agentId}
                            </span>
                            <div className="text-[10px] font-mono text-white/20 mt-0.5 truncate uppercase">
                              {"message" in update ? update.message : "Verification Protocol Applied"}
                            </div>
                          </div>
                          <div className="text-right shrink-0">
                             {duration && (
                               <div className="text-[9px] font-mono text-white/40 mb-1">{duration}</div>
                             )}
                             {completionTime && (
                               <div className="text-[9px] font-mono text-white/10 italic">
                                 [{fmtTime(completionTime)}]
                               </div>
                             )}
                          </div>
                        </motion.div>
                      );
                    })}
                  </div>
                </div>
              </div>

              {/* 3. Synthesis */}
              {report.signed_utc && (
                <div className="relative pl-10">
                  <div className="absolute left-[-5px] top-1.5 w-2.5 h-2.5 rounded-full bg-accent shadow-[0_0_10px_#8B5CF6]" />
                  <div className="space-y-2">
                    <span className="text-[9px] font-mono font-bold text-accent/40 uppercase tracking-[0.2em]">Phase_03</span>
                    <h4 className="text-sm font-heading font-bold text-white/80">Consensus Synthesis</h4>
                    <p className="text-xs text-white/40 leading-relaxed max-w-xl italic">
                      Arbiter consolidation of all agent findings. Final verdict calculation and cryptographic signing.
                    </p>
                    <div className="text-[10px] font-mono text-white/20">
                      [{fmtTime(report.signed_utc)}] Consensus_Reached
                      {lastAgentTime && ` // Deliberation: ${fmtDuration(lastAgentTime, report.signed_utc)}`}
                    </div>
                  </div>
                </div>
              )}

            </div>
          </div>

        </div>
      </div>
    </section>
  );
}

function fmtTime(iso: string): string {
  try {
    const d = new Date(iso);
    return `${d.getHours().toString().padStart(2, '0')}:${d.getMinutes().toString().padStart(2, '0')}:${d.getSeconds().toString().padStart(2, '0')}.${d.getMilliseconds().toString().padStart(3, '0')}`;
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
