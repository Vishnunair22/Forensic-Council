import { Report, AgentResult } from "@/types";
import { ReportDTO } from "@/lib/api";

// Map backend ReportDTO to frontend Report format for tests
export function mapReportDtoToReport(dto: ReportDTO): Report {
  const agentResults: AgentResult[] = [];

  // Flatten per-agent findings with deduplication transparency
  const seenKeys = new Set<string>();

  for (const [agentId, findings] of Object.entries(dto.per_agent_findings ?? {})) {
    for (const finding of findings) {
      const phase =
        ((finding.metadata as Record<string, unknown>)
          ?.analysis_phase as string) ?? "initial";
      const toolName =
        ((finding.metadata as Record<string, unknown>)?.tool_name as string) ??
        finding.finding_type;
      const dedupKey = `${agentId}:${finding.finding_type}:${toolName}`;

      const isDuplicate = seenKeys.has(dedupKey) && phase === "deep";
      seenKeys.add(dedupKey);
      const evidenceVerdict = finding.evidence_verdict ?? "INCONCLUSIVE";
      const confidence =
        evidenceVerdict === "NOT_APPLICABLE" || evidenceVerdict === "ERROR"
          ? 0
          : (finding.raw_confidence_score ??
            finding.confidence_raw ??
            0);

      agentResults.push({
        id: agentId,
        name: finding.agent_name,
        role: finding.agent_name,
        result: finding.court_statement || finding.reasoning_summary,
        confidence,
        thinking: finding.reasoning_summary,
        metadata: {
          ...finding.metadata,
          _deduplication: isDuplicate
            ? "confirmed_in_deep"
            : phase === "deep"
              ? "new_in_deep"
              : "initial",
        },
      });
    }
  }

  return {
    id: dto.report_id,
    fileName: dto.case_id,
    timestamp: dto.signed_utc ?? new Date().toISOString(),
    summary: dto.executive_summary ?? "",
    agents: agentResults,
    verdict: (dto.overall_verdict ?? "INCONCLUSIVE") as Report["verdict"],
  };
}
