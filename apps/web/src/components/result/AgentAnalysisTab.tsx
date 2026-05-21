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
      <div className="flex items-center gap-3 mb-4 px-1">
        <Cpu className="w-3.5 h-3.5 text-white/15" aria-hidden="true" />
        <h2 className="fc-eyebrow fc-text-faint">
          Agent Forensic Findings
          <span className="ml-2 fc-text-faint">— {activeAgentIds.length} Nodes</span>
        </h2>
      </div>

      <div className="space-y-3">
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
              // Every agent card opens by default — collapsing the rest behind
              // a tiny chevron made users think findings were missing.
              defaultOpen={true}
            />
          );
        })}
      </div>
    </section>
  );
}
