"use client";

import { AgentFindingCard } from "@/components/ui/AgentFindingCard";
import type { ReportDTO } from "@/lib/api";
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
      <div className="rounded-2xl border border-white/[0.06] bg-white/[0.02] p-8 text-center">
        <Cpu className="w-8 h-8 text-white/15 mx-auto mb-3" aria-hidden="true" />
        <p className="text-sm text-white/35 font-medium">
          No agent findings available.
        </p>
      </div>
    );
  }

  return (
    <section aria-label="Agent analysis findings">
      <div className="flex items-center gap-2 mb-4">
        <Cpu className="w-3.5 h-3.5 text-white/30" aria-hidden="true" />
        <h2 className="text-[10px] font-mono font-bold uppercase tracking-widest text-white/35">
          Agent Analysis
          <span className="ml-2 text-white/20">— {activeAgentIds.length} specialist{activeAgentIds.length !== 1 ? "s" : ""}</span>
        </h2>
      </div>

      <div className="space-y-3">
        {activeAgentIds.map((agentId, idx) => {
          const allFindings = report.per_agent_findings[agentId] ?? [];
          const metrics = report.per_agent_metrics?.[agentId];
          const narrative = report.per_agent_analysis?.[agentId];

          // Split findings by phase
          const initialFindings = allFindings.filter(
            (f) =>
              !f.metadata ||
              (f.metadata as Record<string, unknown>)?.analysis_phase !== "deep",
          );
          const deepFindings = allFindings.filter(
            (f) =>
              f.metadata &&
              (f.metadata as Record<string, unknown>)?.analysis_phase === "deep",
          );

          return (
            <AgentFindingCard
              key={agentId}
              agentId={agentId}
              initialFindings={initialFindings}
              deepFindings={deepFindings}
              metrics={metrics}
              narrative={narrative}
              phase={isDeepPhase ? "deep" : "initial"}
              defaultOpen={idx === 0}
            />
          );
        })}
      </div>
    </section>
  );
}
