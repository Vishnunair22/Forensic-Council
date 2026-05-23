"use client";

import React, { useState } from "react";
import { AlertTriangle, BarChart3 } from "lucide-react";
import { clsx } from "clsx";
import { fmtTool } from "@/lib/fmtTool";
import { accentFor } from "@/lib/agentTheme";
import type { ReportDTO, AgentFindingDTO } from "@/lib/api";

interface FindingsMetadataProps {
  report: ReportDTO;
  activeAgentIds: string[];
}

function toPct(v: number | null | undefined): string {
  return `${Math.max(0, Math.min(100, Math.round(Number(v ?? 0) * 100)))}%`;
}

export function FindingsMetadata({ report, activeAgentIds }: FindingsMetadataProps) {
  const [showAllTools, setShowAllTools] = useState(false);

  const totalFindings = Object.values(report.per_agent_findings ?? {})
    .flat()
    .length;

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
    { label: "Confidence",       value: toPct(report.overall_confidence) },
    { label: "Manip. Prob.",     value: toPct(report.manipulation_probability) },
    { label: "Error Rate",       value: toPct(report.overall_error_rate) },
    { label: "Agent Spread",     value: toPct(report.confidence_std_dev) },
    { label: "Active Agents",    value: String(activeAgentIds.length) },
    { label: "Total Findings",   value: String(totalFindings) },
    { label: "Tools Called",     value: String(totalTools) },
    { label: "Tools OK / Fail",  value: `${toolsOk} / ${toolsFailed}` },
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

  const flags = report.degradation_flags ?? [];

  return (
    <section className="relative flex flex-col overflow-hidden fc-surface" aria-label="Findings metadata">
      <div className="px-6 py-4 border-b border-white/[0.06] flex items-center gap-2">
        <BarChart3 className="w-4 h-4 text-primary/60" />
        <h2 className="text-sm font-bold fc-text-secondary">Analysis Metrics</h2>
      </div>

      <div className="p-6 space-y-6">
        {/* Stats grid */}
        <div className="grid grid-cols-2 sm:grid-cols-4 gap-4">
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
               <table className="w-full text-xs font-mono">
                <thead>
                  <tr className="border-b border-white/[0.06] bg-white/[0.02]">
                    <th className="px-3 py-2 text-left fc-text-muted font-medium">#</th>
                    <th className="px-3 py-2 text-left fc-text-muted font-medium">Tool</th>
                    <th className="px-3 py-2 text-left fc-text-muted font-medium hidden sm:table-cell">Agent</th>
                    <th className="px-3 py-2 text-right fc-text-muted font-medium hidden md:table-cell">Duration</th>
                    <th className="px-3 py-2 text-left fc-text-muted font-medium">Verdict</th>
                  </tr>
                </thead>
                <tbody>
                  {visibleTools.map((row) => {
                    const accent = accentFor(row.agentId);
                    const verdictOk = /NEGATIVE|authentic|clean|NOT_APPLICABLE/i.test(row.verdict);
                    const verdictBad = /POSITIVE|manipul|tamper|forged|synthetic/i.test(row.verdict);
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
                            "text-xs font-mono",
                            verdictOk && "text-success",
                            verdictBad && "text-danger",
                            !verdictOk && !verdictBad && "fc-text-muted"
                          )}>
                            {row.verdict}
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
                className="mt-2 fc-eyebrow fc-text-muted hover:text-white/70 transition-colors"
              >
                Show {hiddenCount} more
              </button>
            )}
          </div>
        )}

        {/* Arbiter notes (Groq-generated) */}
        {(report.reliability_note || report.uncertainty_statement || report.analysis_coverage_note) && (
          <div className="pt-4 border-t border-white/[0.04] grid grid-cols-1 sm:grid-cols-3 gap-4">
            {report.reliability_note && (
              <div>
                <div className="fc-eyebrow fc-text-muted mb-1">Reliability</div>
                <p className="text-xs fc-text-muted leading-relaxed">{report.reliability_note}</p>
              </div>
            )}
            {report.uncertainty_statement && (
              <div>
                <div className="fc-eyebrow fc-text-muted mb-1">Uncertainty</div>
                <p className="text-xs fc-text-muted leading-relaxed">{report.uncertainty_statement}</p>
              </div>
            )}
            {report.analysis_coverage_note && (
              <div>
                <div className="fc-eyebrow fc-text-muted mb-1">Coverage</div>
                <p className="text-xs fc-text-muted leading-relaxed">{report.analysis_coverage_note}</p>
              </div>
            )}
          </div>
        )}

        {/* Degradation flags */}
        {flags.length > 0 && (
          <div className="pt-4 border-t border-white/[0.04]">
            <div className="flex items-center gap-1.5 fc-eyebrow fc-text-muted mb-3">
              <AlertTriangle className="w-3 h-3 text-warning" />
              Degradation Flags
            </div>
            <div className="space-y-1.5">
              {flags.map((flag, i) => (
                <div key={i} className="flex items-start gap-2">
                  <span className="w-1 h-1 rounded-full bg-warning/60 mt-1.5 shrink-0" />
                  <p className="text-xs fc-text-muted">{flag}</p>
                </div>
              ))}
            </div>
          </div>
        )}
      </div>
    </section>
  );
}
