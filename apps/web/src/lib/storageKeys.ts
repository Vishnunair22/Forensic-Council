export const STORAGE_KEYS = {
  SESSION_ID: "forensic_session_id",
  AUTH_TOKEN: "forensic_auth_token",
  AUTH_TOKEN_EXPIRY: "forensic_auth_token_expiry",

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

  INITIAL_AGENTS: "forensic_initial_agents",
  DEEP_AGENTS: "forensic_deep_agents",

  INVESTIGATOR_ID: "forensic_investigator_id",
  AUTH_OK: "forensic_auth_ok",

  HISTORY: "forensic_history",

  FC_SHOW_LOADING: "fc_show_loading",
  FC_LOADING_TEXT: "fc_loading_text",
  FC_LOADING_DISPATCHED: "fc_loading_dispatched",
  FC_NO_RECONNECT: "fc_no_reconnect",
  FC_REPORT_READY: "fc_report_ready",
  FC_OPEN_UPLOAD_ONCE: "fc_open_upload_once",
  FC_PENDING_FILE_META: "fc_pending_file_meta",
  FC_RESUME_REQUESTED: "fc_resume_requested",
  FC_HANDOFF_FIRED: "fc_handoff_fired",
  FC_ARBITER_TRANSITIONING: "fc_arbiter_transitioning",
  FC_HARD_REFRESH_GUARD: "fc_hard_refresh_guard",
} as const;
