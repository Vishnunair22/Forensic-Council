"use client";

import React, { useMemo } from "react";
import type { ReportDTO } from "@/lib/api";
import type { AgentUpdate } from "@/components/evidence/AgentProgressDisplay";
import { motion } from "framer-motion";
import { fmtTime, fmtDuration } from "@/lib/fmt";
import { accentFor } from "@/lib/agentTheme";

type TimelineItem = { agent_id: string } | AgentUpdate;

interface TimelineTabProps {
  report: ReportDTO;
  activeAgentIds: string[];
  agentTimeline: AgentUpdate[];
  pipelineStartAt: string | null;
}

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
         <span className="fc-eyebrow fc-text-muted">Forensic Execution Lifecycle</span>
         <div className="h-px flex-1 bg-white/5" />
      </div>

      <div className="bg-[#02040A] border border-white/5 rounded-2xl shadow-xl overflow-hidden">
        <div className="bg-transparent">

          {/* Header */}
          <div className="px-10 py-8 border-b border-white/5 flex items-center justify-between gap-6">
            <div className="flex flex-col gap-1">
              <h3 className="text-xl font-heading font-bold text-white tracking-tight">Sequence Registry</h3>
              <p className="fc-eyebrow fc-text-faint">Atomic Tool Execution Logs</p>
            </div>
            {pipelineStartAt && report.signed_utc && (
              <div className="px-4 py-2 rounded-lg bg-primary/5 border border-primary/20 fc-eyebrow fc-text-primary-accent">
                Cycle Time: {fmtDuration(pipelineStartAt, report.signed_utc)}
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
                    <span className="fc-eyebrow fc-text-primary-accent opacity-80">Phase 01</span>
                    <h4 className="text-sm font-heading font-bold text-white/80">Evidence Ingress</h4>
                    <p className="text-xs text-white/40 leading-relaxed max-w-xl italic">
                      Secure intake of forensic evidence. Metadata extraction and integrity pre-check completed.
                    </p>
                    <div className="text-xs font-mono fc-text-faint">[{fmtTime(pipelineStartAt)}] Transmission Secured</div>
                  </div>
                </div>
              )}

              {/* 2. Tool Execution Nodes */}
              <div className="relative pl-10">
                <div
                  className="absolute left-[-5px] top-1.5 w-2.5 h-2.5 rounded-full bg-primary"
                  style={{ boxShadow: "0 0 10px var(--color-primary)" }}
                />
                <div className="space-y-8">
                  <div className="space-y-2">
                    <span className="fc-eyebrow fc-text-primary-accent opacity-80">Phase 02</span>
                    <h4 className="text-sm font-heading font-bold text-white/80">Forensic Agent Scans</h4>
                    <p className="text-xs text-white/40 leading-relaxed max-w-xl italic">
                      Execution of deep neural probes and specialized investigative agents.
                    </p>
                  </div>

                  <div className="flex flex-col max-w-2xl">
                    {(hasLiveTimeline ? agentTimeline : activeAgentIds.map(id => ({ agent_id: id }))).map((update: TimelineItem, idx) => {
                      const agentId = update.agent_id;
                      const theme = { color: accentFor(agentId).color };
                      const completionTime = "completed_at" in update ? update.completed_at : null;
                      const duration = (pipelineStartAt && completionTime) ? fmtDuration(pipelineStartAt, completionTime) : null;
                      // F-L-3: stable key derived from agentId + completion time,
                      // falling back to idx only when neither is available.
                      const stableKey = `${agentId}-${completionTime ?? idx}`;

                      return (
                        <motion.div
                          key={stableKey}
                          initial={{ opacity: 0, x: -10 }}
                          animate={{ opacity: 1, x: 0 }}
                          className="flex items-center gap-4 py-4 group border-t border-white/5 first:border-t-0"
                        >
                          <div className="w-2 h-2 rounded-full shrink-0" style={{ backgroundColor: theme.color, boxShadow: `0 0 10px ${theme.color}` }} />
                          <div className="flex-1">
                            <span className="fc-eyebrow" style={{ color: theme.color }}>
                              {"agent_name" in update ? update.agent_name : agentId}
                            </span>
                            <div className="text-xs font-mono fc-text-faint mt-0.5 truncate">
                              {"message" in update ? update.message : "Verification Protocol Applied"}
                            </div>
                          </div>
                          <div className="text-right shrink-0">
                             {duration && (
                               <div className="text-xs font-mono fc-text-muted mb-1">{duration}</div>
                             )}
                             {completionTime && (
                               <div className="text-xs font-mono fc-text-faint italic">
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
                  <div
                    className="absolute left-[-5px] top-1.5 w-2.5 h-2.5 rounded-full"
                    style={{
                      backgroundColor: "var(--color-success)",
                      boxShadow: "0 0 10px var(--color-success)",
                    }}
                  />
                  <div className="space-y-2">
                    <span className="fc-eyebrow fc-text-success opacity-80">Phase 03</span>
                    <h4 className="text-sm font-heading font-bold text-white/80">Consensus Synthesis</h4>
                    <p className="text-xs text-white/40 leading-relaxed max-w-xl italic">
                      Arbiter consolidation of all agent findings. Final verdict calculation and cryptographic signing.
                    </p>
                    <div className="text-xs font-mono fc-text-faint">
                      [{fmtTime(report.signed_utc)}] Consensus Reached
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

