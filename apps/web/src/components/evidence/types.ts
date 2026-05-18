export interface FindingPreview {
  tool: string;
  summary: string;
  confidence?: number | null;
  flag?: string;
  severity?: string;
  verdict?: string;
  key_signal?: string;
  section?: string;
  elapsed_s?: number | null;
  degraded?: boolean | null;
  fallback_reason?: string | null;
}

export interface AgentUpdate {
  agent_id: string;
  agent_name: string;
  message: string;
  summary?: string;
  status: "running" | "complete" | "skipped" | "error" | "failed";
  confidence: number;
  findings_count: number;
  error?: string;
  deep_analysis_pending?: boolean;
  agent_verdict?:
    | "AUTHENTIC"
    | "CLEAN"
    | "INCONCLUSIVE"
    | "SUSPICIOUS"
    | "TAMPERED"
    | "NEEDS_REVIEW"
    | "LIKELY_MANIPULATED"
    | "LIKELY_AI_GENERATED"
    | "LIKELY_SPOOFED"
    | "LIKELY_SYNTHETIC";
  tool_error_rate?: number;
  section_flags?: Array<{ id: string; label: string; flag: string; key_signal?: string }>;
  findings_preview?: FindingPreview[];
  tools_ran?: number;
  tools_skipped?: number;
  tools_failed?: number;
  verdict_score?: number;
  degraded?: boolean;
  fallback_reason?: string;
  completed_at?: string;
}
