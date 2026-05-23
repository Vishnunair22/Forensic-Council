"use client";

import React, { useState } from "react";
import { BarChart3 } from "lucide-react";
import { clsx } from "clsx";
import { fmtTool } from "@/lib/fmtTool";
import { accentFor } from "@/lib/agentTheme";
import type { ReportDTO, AgentFindingDTO } from "@/lib/api";

interface FindingsMetadataProps {
  report: ReportDTO;
  activeAgentIds: string[];
}

export function FindingsMetadata({ report, activeAgentIds }: FindingsMetadataProps) {
  const [showAllTools, setShowAllTools] = useState(false);

  const allFindings = Object.values(report.per_agent_findings ?? {}).flat();
  const positiveSignals = allFindings.filter(
    (f) => f?.evidence_verdict === "POSITIVE"
  ).length;

  const totalTools = activeAgentIds.reduce((sum, id) => {
    const m = report.per_agent_metrics?.[id];
    return sum + (m?.total_tools_called ?? 0);
  }, 0);

  const toolsOk = activeAgentIds.reduce((sum, id) => {
    const m = report.per_agent_metrics?.[id];
    return sum + (m?.tools_succeeded ?? 0);
  }, 0);

  const toolsFailed = activeAgentIds.reduce((sum, id) => {
    const m = report.per_agent_metrics?.[id];
    return sum + (m?.tools_failed ?? 0);
  }, 0);

  const stats = [
    { label: "Positive Signals", value: String(positiveSignals) },
    { label: "Tools Invoked",    value: String(totalTools) },
    { label: "Coverage",         value: `${toolsOk} / ${toolsOk + toolsFailed} succeeded` },
  ];

  // Build tool log from per-agent findings
  const toolRows: Array<{
    index: number;
    toolName: string;
    agentId: string;
    durationMs: number | null;
    verdict: string;
    status: string;
  }> = [];

  let rowIndex = 0;
  for (const agentId of activeAgentIds) {
    const findings = report.per_agent_findings?.[agentId] ?? [];
    for (const f of findings as AgentFindingDTO[]) {
      const toolName = String(f.metadata?.tool_name ?? "");
      if (!toolName) continue;
      toolRows.push({
        index: ++rowIndex,
        toolName,
        agentId,
        durationMs: typeof f.metadata?.execution_time_ms === "number" ? f.metadata.execution_time_ms : null,
        verdict: f.evidence_verdict ?? f.status ?? "—",
        status: f.status ?? "—",
      });
    }
  }

  const PAGE = 8;
  const visibleTools = showAllTools ? toolRows : toolRows.slice(0, PAGE);
  const hiddenCount = toolRows.length - PAGE;

  return (
    <section className="relative flex flex-col overflow-hidden fc-surface" aria-label="Findings metadata">
      <div className="px-6 py-4 border-b border-white/[0.06] flex items-center gap-2">
        <BarChart3 className="w-4 h-4 text-primary/60" />
        <h2 className="text-sm font-bold fc-text-secondary">Analysis Metrics</h2>
      </div>

      <div className="p-6 space-y-6">
        {/* Stats grid */}
        <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
          {stats.map((s) => (
            <div key={s.label}>
              <div className="fc-eyebrow fc-text-muted mb-1">{s.label}</div>
              <div className="text-sm font-mono font-bold fc-text-secondary">{s.value}</div>
            </div>
          ))}
        </div>

        {/* Tool log table */}
        {toolRows.length > 0 && (
          <div>
            <div className="fc-eyebrow fc-text-muted mb-3">Tool Execution Log</div>
            <div className="border border-white/[0.06] rounded-xl overflow-hidden">
             <table className="w-full text-xs font-mono" aria-label="Tool execution log">
                <thead>
                  <tr className="border-b border-white/[0.06] bg-white/[0.02]">
                    <th scope="col" className="px-3 py-2 text-left fc-text-muted font-medium">#</th>
                    <th scope="col" className="px-3 py-2 text-left fc-text-muted font-medium">Tool</th>
                    <th scope="col" className="px-3 py-2 text-left fc-text-muted font-medium hidden sm:table-cell">Agent</th>
                    <th scope="col" className="px-3 py-2 text-right fc-text-muted font-medium hidden md:table-cell">Duration</th>
                    <th scope="col" className="px-3 py-2 text-left fc-text-muted font-medium">Verdict</th>
                  </tr>
                </thead>
                <tbody>
                  {visibleTools.map((row) => {
                    const accent = accentFor(row.agentId);
                    const verdictOk = /NEGATIVE|authentic|clean|NOT_APPLICABLE/i.test(row.verdict);
                    const verdictBad = /POSITIVE|manipul|tamper|forged|synthetic/i.test(row.verdict);
                    
                    let displayVerdict = row.verdict;
                    if (displayVerdict === "NEGATIVE" || displayVerdict === "NO_ANOMALIES") displayVerdict = "Clean";
                    if (displayVerdict === "POSITIVE") displayVerdict = "Flagged";
                    if (displayVerdict === "INCONCLUSIVE") displayVerdict = "Inconclusive";
                    if (displayVerdict === "NOT_APPLICABLE") displayVerdict = "Skipped";

                    return (
                      <tr key={`${row.agentId}-${row.index}`} className="border-b border-white/[0.04] last:border-0 hover:bg-white/[0.02] transition-colors">
                        <td className="px-3 py-2 fc-text-muted">{row.index}</td>
                        <td className="px-3 py-2 fc-text-secondary max-w-[160px] truncate">{fmtTool(row.toolName)}</td>
                        <td className="px-3 py-2 hidden sm:table-cell">
                          <span className="text-xs font-mono" style={{ color: accent.color }}>{row.agentId}</span>
                        </td>
                        <td className="px-3 py-2 text-right fc-text-muted hidden md:table-cell">
                          {row.durationMs !== null ? `${row.durationMs}ms` : "—"}
                        </td>
                        <td className="px-3 py-2">
                          <span className={clsx(
                            "text-xs font-mono whitespace-nowrap",
                            verdictOk && "text-success",
                            verdictBad && "text-danger",
                            !verdictOk && !verdictBad && "fc-text-muted"
                          )}>
                            {displayVerdict}
                          </span>
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
            {!showAllTools && hiddenCount > 0 && (
              <button
                type="button"
                onClick={() => setShowAllTools(true)}
                className="mt-2 fc-eyebrow fc-text-muted hover:text-white transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary/50 rounded px-1"
              >
                Show {hiddenCount} more
              </button>
            )}
          </div>
        )}

      </div>
    </section>
  );
}
