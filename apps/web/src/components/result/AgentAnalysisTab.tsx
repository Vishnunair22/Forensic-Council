"use client";

import { motion } from "framer-motion";
import { AgentFindingCard } from "@/components/ui/AgentFindingCard";
import type { ReportDTO } from "@/lib/api";
import type { Finding } from "@/lib/types";
import { Cpu, TerminalSquare } from "lucide-react";

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
      <div className="rounded-2xl border border-dashed border-white/10 bg-black/20 p-12 text-center relative overflow-hidden flex flex-col items-center justify-center">
        {/* Animated Scanner line */}
        <motion.div
          className="absolute inset-x-0 h-px bg-primary/30 shadow-[0_0_20px_rgba(var(--color-primary-rgb),0.5)]"
          animate={{ top: ["0%", "100%", "0%"] }}
          transition={{ duration: 4, ease: "linear", repeat: Infinity }}
        />
        <TerminalSquare className="w-10 h-10 text-primary/20 mb-4" aria-hidden="true" />
        <p className="text-sm font-mono uppercase tracking-widest fc-text-muted">No raw logs extracted.</p>
      </div>
    );
  }

  return (
    <section aria-label="Agent analysis findings" className="bg-white/[0.01] border border-white/[0.04] rounded-2xl p-1">
      <div className="flex items-center justify-between gap-3 mb-4 px-4 pt-4">
        <div className="flex items-center gap-2.5">
          <div className="p-1.5 rounded bg-primary/10 border border-primary/20">
            <Cpu className="w-4 h-4 text-primary" aria-hidden="true" />
          </div>
          <h2 className="text-sm font-mono font-bold tracking-widest uppercase text-white/90">Diagnostic Logs</h2>
        </div>
        <div className="bg-black/40 border border-white/10 px-2 py-0.5 rounded text-xs font-mono text-primary uppercase">
          {activeAgentIds.length} Active Node{activeAgentIds.length === 1 ? "" : "s"}
        </div>
      </div>

      <div className="space-y-1.5">
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
              narrativeStructured={report?.per_agent_narrative_structured?.[agentId]}
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
