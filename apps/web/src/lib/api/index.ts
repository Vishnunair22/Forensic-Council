/**
 * Forensic Council — API Module
 */

export * from "./types";
export * from "./utils";
export {
  DuplicateInvestigationError,
  ProtocolWarmingError,
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
  startInvestigation,
  submitHITLDecision,
  getAuthToken,
} from "./client";
