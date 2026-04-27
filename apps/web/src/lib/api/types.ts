/**
 * Forensic Council — API Types & DTOs
 */

export interface AgentFindingDTO {
  finding_id: string;
  agent_id: string;
  agent_name: string;
  finding_type: string;
  status: string;
  confidence_raw: number | null;
  evidence_verdict?: "POSITIVE" | "NEGATIVE" | "INCONCLUSIVE" | "NOT_APPLICABLE" | "ERROR";
  calibrated: boolean;
  raw_confidence_score: number | null;
  court_statement: string | null;
  robustness_caveat: boolean;
  robustness_caveat_detail: string | null;
  reasoning_summary: string;
  metadata: Record<string, unknown> | null;
  severity_tier?: "INFO" | "LOW" | "MEDIUM" | "HIGH" | "CRITICAL";
}

export interface AgentMetricsDTO {
  agent_id: string;
  agent_name: string;
  total_tools_called: number;
  tools_succeeded: number;
  tools_failed: number;
  tools_not_applicable?: number;
  error_rate: number;
  confidence_score: number;
  finding_count: number;
  skipped: boolean;
}

export interface ReportDTO {
  report_id: string;
  session_id: string;
  case_id: string;
  executive_summary: string;
  per_agent_findings: Record<string, AgentFindingDTO[]>;
  per_agent_metrics: Record<string, AgentMetricsDTO>;
  per_agent_analysis: Record<string, string>;
  overall_confidence: number;
  overall_error_rate: number;
  overall_verdict: string;
  cross_modal_confirmed: AgentFindingDTO[];
  contested_findings: Record<string, unknown>[];
  tribunal_resolved: Record<string, unknown>[];
  incomplete_findings: AgentFindingDTO[];
  uncertainty_statement: string;
  cryptographic_signature: string;
  report_hash: string;
  signed_utc: string | null;
  verdict_sentence?: string;
  key_findings?: string[];
  reliability_note?: string;
  manipulation_probability?: number;
  confidence_min?: number;
  confidence_max?: number;
  confidence_std_dev?: number;
  applicable_agent_count?: number;
  skipped_agents?: Record<string, string>;
  analysis_coverage_note?: string;
  per_agent_summary?: Record<
    string,
    {
      agent_name: string;
      verdict: string;
      confidence_pct: number;
      tools_ok: number;
      tools_total: number;
      findings: number;
      error_rate_pct: number;
      skipped: boolean;
    }
  >;
  degradation_flags?: string[];
  compression_penalty?: number;
  cross_modal_fusion?: Record<string, unknown>;
}

export interface BriefUpdate {
  type:
    | "AGENT_UPDATE"
    | "HITL_CHECKPOINT"
    | "AGENT_COMPLETE"
    | "PIPELINE_COMPLETE"
    | "ERROR"
    | "CONNECTED"
    | "PIPELINE_PAUSED"
    | "PIPELINE_QUARANTINED"
    | "REPORT_READY";
  session_id: string;
  agent_id: string | null;
  agent_name: string | null;
  message: string;
  data: Record<string, unknown> | null;
}

export interface HITLCheckpoint {
  checkpoint_id: string;
  session_id: string;
  agent_id: string;
  agent_name: string;
  brief_text: string;
  decision_needed: string;
  created_at: string;
}

export type HITLDecision =
  | "APPROVE"
  | "REDIRECT"
  | "OVERRIDE"
  | "TERMINATE"
  | "ESCALATE";

export interface HITLDecisionRequest {
  session_id: string;
  checkpoint_id: string;
  agent_id: string;
  decision: HITLDecision;
  note?: string;
  override_finding?: Record<string, unknown>;
}

export interface InvestigationResponse {
  session_id: string;
  case_id: string;
  status: string;
  message: string;
}

export interface ReportResponse {
  status: "complete" | "in_progress";
  report?: ReportDTO;
}

export interface TokenResponse {
  access_token: string;
  token_type: string;
  expires_in: number;
  user_id: string;
  role: string;
}

export interface UserInfo {
  user_id: string;
  username: string;
  role: string;
}

export interface ArbiterStatusResponse {
  status: "running" | "complete" | "error" | "not_found";
  message?: string;
  report_id?: string;
}
