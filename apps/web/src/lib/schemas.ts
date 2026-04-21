import { z } from "zod";
import { VERDICTS } from "@/types";

export const AgentResultSchema = z.object({
  id: z.string(),
  name: z.string(),
  role: z.string(),
  result: z.string(),
  confidence: z.number(),
  thinking: z.string().optional(),
  metadata: z.record(z.string(), z.unknown()).optional(),
});

export const ReportSchema = z.object({
  id: z.string(),
  fileName: z.string(),
  timestamp: z.string(),
  summary: z.string(),
  agents: z.array(AgentResultSchema),
  verdict: z.enum(VERDICTS),
});

export const HistorySchema = z.array(ReportSchema);

export const ReportDTOSchema = z.object({
  session_id: z.string().uuid(),
  report_id: z.string().uuid(),
  case_id: z.string(),
  overall_verdict: z.enum(VERDICTS),
  overall_confidence: z.number().min(0).max(1),
  overall_error_rate: z.number().min(0).max(1).optional(),
  manipulation_probability: z.number().min(0).max(1).optional(),
  compression_penalty: z.number().min(0).max(1).optional(),
  signed_utc: z.string().datetime().optional(),
  report_hash: z.string().optional(),
  cryptographic_signature: z.string().optional(),
  per_agent_findings: z.record(z.string(), z.array(z.unknown())).optional(),
  per_agent_metrics: z.record(z.string(), z.unknown()).optional(),
  per_agent_summary: z.record(z.string(), z.unknown()).optional(),
  per_agent_analysis: z.record(z.string(), z.string()).optional(),
  key_findings: z.array(z.string()).optional(),
  executive_summary: z.string().optional(),
  verdict_sentence: z.string().optional(),
  reliability_note: z.string().optional(),
  uncertainty_statement: z.string().optional(),
  degradation_flags: z.array(z.string()).optional(),
  applicable_agent_count: z.number().optional(),
  confidence_min: z.number().optional(),
  confidence_max: z.number().optional(),
  analysis_coverage_note: z.string().optional(),
  case_linking_flags: z.array(z.unknown()).optional(),
  chain_of_custody_log: z.array(z.unknown()).optional(),
  evidence_version_trees: z.array(z.unknown()).optional(),
  react_chains: z.record(z.string(), z.array(z.unknown())).optional(),
  self_reflection_outputs: z.record(z.string(), z.unknown()).optional(),
  cross_modal_fusion: z.record(z.string(), z.unknown()).optional(),
  cross_modal_confirmed: z.array(z.unknown()).optional(),
  contested_findings: z.array(z.unknown()).optional(),
  tribunal_resolved: z.array(z.unknown()).optional(),
  gemini_vision_findings: z.array(z.unknown()).optional(),
}).passthrough();
