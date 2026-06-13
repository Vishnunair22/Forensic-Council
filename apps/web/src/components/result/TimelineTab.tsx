"use client";

import React, { useMemo } from "react";
import type { ReportDTO } from "@/lib/api";
import type { AgentUpdate } from "@/components/evidence/types";
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
    <section>
      <div className="border border-white/[0.06] rounded-2xl overflow-hidden">

        {/* Header */}
        <div className="px-6 py-4 border-b border-white/[0.06] flex items-center justify-between gap-6">
          <div className="flex flex-col gap-0.5">
            <h3 className="text-sm font-bold fc-text-primary">Execution Timeline</h3>
            <p className="fc-eyebrow fc-text-faint">Per-agent tool execution</p>
          </div>
          {pipelineStartAt && report.signed_utc && (
            <div className="px-3 py-1.5 rounded-lg bg-primary/5 border border-primary/20 fc-eyebrow fc-text-primary-accent">
              Total time: {fmtDuration(pipelineStartAt, report.signed_utc)}
            </div>
          )}
        </div>

        <div className="p-6 md:p-8 relative">
          {/* Timeline Line */}
            <div className="absolute left-6 md:left-8 top-6 bottom-6 w-px bg-white/[0.05]" />

            <div className="space-y-10">

              {/* 1. Evidence Ingress */}
              {pipelineStartAt && (
                <div className="relative pl-10">
                  <div className="absolute left-[-5px] top-1.5 w-2 h-2 rounded-full bg-white/20 border border-white/30" />
                  <div className="space-y-2">
                    <span className="fc-eyebrow fc-text-primary-accent opacity-80">Phase 01</span>
                    <h4 className="text-sm font-heading font-bold fc-text-primary">Evidence Intake</h4>
                    <p className="text-xs fc-text-faint leading-relaxed max-w-xl italic">
                      Evidence received; metadata and integrity checks completed.
                    </p>
                    <div className="text-xs font-mono fc-text-faint">[{fmtTime(pipelineStartAt)}] Received</div>
                  </div>
                </div>
              )}

              {/* 2. Tool Execution Nodes */}
              <div className="relative pl-10">
                <div
                  className="absolute left-[-4px] top-1.5 w-2 h-2 rounded-full bg-primary"
                />
                <div className="space-y-8">
                  <div className="space-y-2">
                    <span className="fc-eyebrow fc-text-primary-accent opacity-80">Phase 02</span>
                    <h4 className="text-sm font-heading font-bold fc-text-primary">Agent Analysis</h4>
                    <p className="text-xs fc-text-faint leading-relaxed max-w-xl italic">
                      Specialist agents ran their forensic tools on the evidence.
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
                          initial={{ opacity: 0, y: 4 }}
                          animate={{ opacity: 1, y: 0 }}
                          transition={{ duration: 0.16, ease: "easeOut" }}
                          className="flex items-center gap-4 py-4 group border-t border-white/5 first:border-t-0"
                        >
                          <div className="w-2 h-2 rounded-full shrink-0" style={{ backgroundColor: theme.color }} />
                          <div className="flex-1">
                            <span className="fc-eyebrow" style={{ color: theme.color }}>
                              {"agent_name" in update ? update.agent_name : agentId}
                            </span>
                            <div className="text-xs font-mono fc-text-faint mt-0.5 truncate">
                              {"message" in update ? update.message : "Analysis completed"}
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
                    className="absolute left-[-4px] top-1.5 w-2 h-2 rounded-full bg-success"
                  />
                  <div className="space-y-2">
                    <span className="fc-eyebrow fc-text-success opacity-80">Phase 03</span>
                    <h4 className="text-sm font-heading font-bold fc-text-primary">Synthesis &amp; Verdict</h4>
                    <p className="text-xs fc-text-faint leading-relaxed max-w-xl italic">
                      Arbiter consolidated the findings, computed the verdict, and signed the report.
                    </p>
                    <div className="text-xs font-mono fc-text-faint">
                      [{fmtTime(report.signed_utc)}] Report signed
                      {lastAgentTime && ` // Deliberation: ${fmtDuration(lastAgentTime, report.signed_utc)}`}
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

