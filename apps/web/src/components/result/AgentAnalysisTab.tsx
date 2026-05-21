"use client";

import { AgentFindingCard } from "@/components/ui/AgentFindingCard";
import type { ReportDTO } from "@/lib/api";
import type { Finding } from "@/lib/types";
import { Cpu } from "lucide-react";

interface AgentAnalysisTabProps {
  report: ReportDTO;
  activeAgentIds: string[];
  isDeepPhase: boolean;
}

export function AgentAnalysisTab({
  report,
  activeAgentIds,
  isDeepPhase,
}: AgentAnalysisTabProps) {
  if (activeAgentIds.length === 0) {
    return (
      <div className="rounded-2xl border border-white/[0.06] bg-transparent p-8 text-center">
        <Cpu className="w-8 h-8 text-white/15 mx-auto mb-3" aria-hidden="true" />
        <p className="text-sm fc-text-faint font-medium">No agent findings available.</p>
      </div>
    );
  }

  return (
    <section aria-label="Agent analysis findings">
      <div className="flex items-center justify-between gap-3 mb-3 px-1">
        <div className="flex items-center gap-2">
          <Cpu className="w-4 h-4 text-primary/60" aria-hidden="true" />
          <h2 className="text-sm font-bold text-white/85">Agent Findings</h2>
        </div>
        <span className="fc-eyebrow fc-text-faint">{activeAgentIds.length} node{activeAgentIds.length === 1 ? "" : "s"}</span>
      </div>

      <div className="space-y-2.5">
        {activeAgentIds.map((agentId) => {
          const rawFindings = report?.per_agent_findings?.[agentId];
          const allFindings = Array.isArray(rawFindings) ? rawFindings : [];

          const initialFindings = allFindings.filter(
            (f: Finding) => f?.metadata?.analysis_phase !== "deep",
          );
          const deepFindings = allFindings.filter(
            (f: Finding) => f?.metadata?.analysis_phase === "deep",
          );

          return (
            <AgentFindingCard
              key={agentId}
              agentId={agentId}
              initialFindings={initialFindings}
              deepFindings={deepFindings}
              metrics={report?.per_agent_metrics?.[agentId]}
              narrative={report?.per_agent_analysis?.[agentId]}
              agentSummary={report?.per_agent_summary?.[agentId]}
              phase={isDeepPhase ? "deep" : "initial"}
              defaultOpen={false}
            />
          );
        })}
      </div>
    </section>
  );
}
