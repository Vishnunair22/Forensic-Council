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
   <div className="flex items-center gap-3 mb-4 px-1">
    <Cpu className="w-3.5 h-3.5 text-white/15" aria-hidden="true" />
    <h2 className="text-[10px] font-bold tracking-widest text-white/40 uppercase">
     Agent Forensic Findings
     <span className="ml-2 text-white/15">— {activeAgentIds.length} Nodes</span>
    </h2>
   </div>

    <div className="space-y-3">
     {activeAgentIds.map((agentId, _idx) => {
      const rawFindings = report?.per_agent_findings?.[agentId];
      const allFindings = Array.isArray(rawFindings) ? rawFindings : [];
      const metrics = report?.per_agent_metrics?.[agentId];
      const narrative = report?.per_agent_analysis?.[agentId];
      const agentSummary = report?.per_agent_summary?.[agentId];

      // Split findings by phase
      const initialFindings = allFindings.filter(
        (f: Finding) => f?.metadata?.analysis_phase !== "deep",
      );
      const deepFindings = allFindings.filter(
        (f: Finding) => f?.metadata?.analysis_phase === "deep",
      );

      const SKIP_TYPES = new Set(["file type not applicable", "format not supported"]);
      const firstActiveAgentId = activeAgentIds.find(id =>
        (report?.per_agent_findings?.[id] ?? []).some(
          (f: Finding) => !SKIP_TYPES.has(String(f?.finding_type || "").toLowerCase())
        )
      ) ?? activeAgentIds[0];

      return (
       <AgentFindingCard
        key={agentId}
        agentId={agentId}
        initialFindings={initialFindings}
        deepFindings={deepFindings}
        metrics={metrics}
        narrative={narrative}
        agentSummary={agentSummary}
        phase={isDeepPhase ? "deep" : "initial"}
        defaultOpen={agentId === firstActiveAgentId}
       />
     );
    })}
   </div>
  </section>
 );
}
