/**
 * Forensic Council — API Module
 */

export * from "./types";
export * from "./utils";
export {
  DuplicateInvestigationError,
  ProtocolWarmingError,
  apiFetch,
  autoLoginAsInvestigator,
  checkBackendHealth,
  createLiveSocket,
  connectLiveSSE,
  type SSEConnection,
  ensureAuthenticated,
  getArbiterStatus,
  getBrief,
  getCheckpoints,
  getReport,
  login,
  logout,
  pollForReport,
  refreshAuthToken,
  startInvestigation,
  submitHITLDecision,
  getAuthToken,
} from "./client";
