/**
 * Unified Registry of Web Storage Keys
 * Prevents magic-string mismatch bugs across pages, components, hooks, and tests.
 */
export const STORAGE_KEYS = {
  // Session / Authentication Keys
  SESSION_ID: "forensic_session_id",
  AUTH_TOKEN: "forensic_auth_token",
  AUTH_TOKEN_EXPIRY: "forensic_auth_token_expiry",

  // Investigation State & Metadata
  HISTORY: "forensic_history",
  INVESTIGATION_CTX: "forensic_investigation_ctx",
  THUMBNAIL: "forensic_thumbnail",
  MIME_TYPE: "forensic_mime_type",
  FILE_NAME: "forensic_file_name",
  CASE_ID: "forensic_case_id",
  PIPELINE_START: "forensic_pipeline_start",
  HITL_CHECKPOINT: "forensic_hitl_checkpoint",
  IS_DEEP: "forensic_is_deep",
  AUTO_START: "forensic_auto_start",
  RESULT_PHASE: "forensic_result_phase",

  // Agent State & Updates
  INITIAL_AGENTS: "forensic_initial_agents",
  DEEP_AGENTS: "forensic_deep_agents",

  // Identity
  INVESTIGATOR_ID: "forensic_investigator_id",
  AUTH_OK: "forensic_auth_ok",

  // Ephemeral flow-control flags (sessionStorage only, cleared by resetActiveInvestigation)
  FC_SHOW_LOADING: "fc_show_loading",
  FC_NO_RECONNECT: "fc_no_reconnect",
  FC_REPORT_READY: "fc_report_ready",
  FC_OPEN_UPLOAD_ONCE: "fc_open_upload_once",
  FC_PENDING_FILE_META: "fc_pending_file_meta",
  FC_RESUME_REQUESTED: "fc_resume_requested",
} as const;
