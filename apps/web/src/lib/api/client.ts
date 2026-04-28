/**
 * Forensic Council — Core API Client
 */

import { ReportDTOSchema } from "@/lib/schemas";
import {
  API_BASE,
  clearAuthToken,
  dbg,
  getAuthToken,
  getMutationHeaders,
  getWSBase,
  setAuthToken,
} from "./utils";
import {
  ArbiterStatusResponse,
  HITLCheckpoint,
  HITLDecisionRequest,
  InvestigationResponse,
  ReportDTO,
  ReportResponse,
  TokenResponse,
} from "./types";

const LIVE_SOCKET_CONNECT_TIMEOUT_MS = 20_000;

/**
 * Partial Validation Parser
 * Uses Zod but falls back to raw data on minor validation errors
 * to prevent complete UI failure during rapid schema evolution.
 */
function _parseReportDTO(raw: unknown): ReportDTO {
  const result = ReportDTOSchema.safeParse(raw);
  if (result.success) return result.data as unknown as ReportDTO;

  dbg.error(
    "[api] Report validation failed. Falling back to passthrough.",
    result.error.message,
  );
  
  // Fire-and-forget telemetry for schema evolution monitoring
  fetch(`${API_BASE}/api/v1/telemetry`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      event: "schema_validation_error",
      schema: "ReportDTO",
      error: result.error.errors,
      url: window.location.href,
    }),
  }).catch(() => {}); // Ignore telemetry failures

  // Log strictly but allow the UI to try and render whatever matches the interface.
  return raw as ReportDTO;
}

export class ProtocolWarmingError extends Error {
  constructor(message = "Protocol warming up — system dependencies initializing") {
    super(message);
    this.name = "ProtocolWarmingError";
  }
}

export class DuplicateInvestigationError extends Error {
  constructor(public existingSessionId: string, message = "Duplicate investigation request") {
    super(message);
    this.name = "DuplicateInvestigationError";
  }
}

function extractDuplicateSessionId(detail: unknown): string | null {
  if (typeof detail !== "string") return null;
  const match = detail.match(/Duplicate detected:\s*session\s+(?:b['"])?([0-9a-fA-F-]+)/);
  return match?.[1] ?? null;
}


/**
 * Checks backend health and warming status.
 */
export async function checkBackendHealth(): Promise<{ ok: boolean; warmingUp?: boolean; message: string }> {
  try {
    const response = await fetch(`${API_BASE}/api/v1/health`, {
      method: "GET",
      cache: "no-store",
      // Increased timeout for slow Docker cold-starts/DNS resolution
      signal: AbortSignal.timeout(10000),
    });

    if (response.ok) return { ok: true, message: "Healthy" };

    if (response.status === 503) {
      return { ok: false, warmingUp: true, message: "Protocol warming up" };
    }

    return { ok: false, message: `System status: ${response.status}` };
  } catch (err) {
    const msg = err instanceof Error ? err.message : "Unknown error";
    return { ok: false, message: `Backend unreachable (${msg})` };
  }
}



// ── Auth Actions ─────────────────────────────────────────────────────────────

let _pendingAuth: Promise<TokenResponse> | null = null;

export async function autoLoginAsInvestigator(): Promise<TokenResponse> {
  if (_pendingAuth) return _pendingAuth;

  _pendingAuth = (async () => {
    const maxRetries = 3;
    for (let attempt = 0; attempt <= maxRetries; attempt++) {
      try {
        const response = await fetch("/api/auth/demo", {
          method: "POST",
          signal: AbortSignal.timeout(10_000),
        });

        if (!response.ok) {
          if (response.status === 503 && attempt < maxRetries) throw new ProtocolWarmingError();
          throw new Error("Authentication failed");
        }

        const data: TokenResponse = await response.json();
        if (data.access_token && typeof data.expires_in === "number") {
          setAuthToken(data.access_token, data.expires_in);
        }
        return data;
      } catch (err) {
        if (attempt === maxRetries) throw err;
        await new Promise((r) => setTimeout(r, Math.min(1000 * 2 ** attempt, 5000)));
      }
    }
    throw new Error("Demo login exhausted retries");
  })();

  try {
    return await _pendingAuth;
  } finally {
    _pendingAuth = null;
  }
}

async function handleAuthError<T>(operation: () => Promise<T>, _retryCount = 0): Promise<T> {
  try {
    return await operation();
  } catch (error) {
    const msg = error instanceof Error ? error.message : String(error);
    const isAuthError = msg.includes("401") || msg.includes("Unauthorized") || msg.includes("authenticated");
    
    if (isAuthError && _retryCount < 2) {
      dbg.warn("Session invalid, re-authenticating...");
      await autoLoginAsInvestigator();
      return await handleAuthError(operation, _retryCount + 1);
    }
    throw error;
  }
}

export async function login(username: string, password: string): Promise<TokenResponse> {
  const body = new URLSearchParams();
  body.set("username", username);
  body.set("password", password);

  const headers = await getMutationHeaders({
    "Content-Type": "application/x-www-form-urlencoded",
  });

  const response = await fetch(`${API_BASE}/api/v1/auth/login`, {
    method: "POST",
    headers,
    body: body.toString(),
    credentials: "include",
  });

  if (!response.ok) throw new Error(`Authentication failed (${response.status})`);

  const data: TokenResponse = await response.json();
  if (data.access_token && typeof data.expires_in === "number") {
    setAuthToken(data.access_token, data.expires_in);
  }
  return data;
}

export async function ensureAuthenticated(): Promise<void> {
  const response = await fetch(`${API_BASE}/api/v1/auth/me`, {
    credentials: "include",
    cache: "no-store",
  });

  if (response.ok) return;
  if (response.status === 401 || response.status === 403) {
    await autoLoginAsInvestigator();
    return;
  }

  throw new Error(`Authentication check failed (${response.status})`);
}

// ── Forensic Actions ─────────────────────────────────────────────────────────

export async function startInvestigation(
  file: File,
  caseId: string,
  investigatorId: string,
): Promise<InvestigationResponse> {
  return handleAuthError(async () => {
    const formData = new FormData();
    formData.append("file", file);
    formData.append("case_id", caseId);
    formData.append("investigator_id", investigatorId);

    const headers = await getMutationHeaders();
    const response = await fetch(`${API_BASE}/api/v1/investigate`, {
      method: "POST",
      headers,
      body: formData,
      credentials: "include",
    });

    if (!response.ok) {
      const err = await response.json().catch(() => ({ detail: "Upload failed" }));
      if (response.status === 409) {
        const existingSessionId = extractDuplicateSessionId(err.detail);
        if (existingSessionId) {
          throw new DuplicateInvestigationError(existingSessionId, err.detail);
        }
      }
      throw new Error(err.detail || `HTTP ${response.status}`);
    }
    return response.json();
  });
}

export async function getBrief(sessionId: string, agentId: string): Promise<string> {
  return handleAuthError(async () => {
    const response = await fetch(
      `${API_BASE}/api/v1/sessions/${encodeURIComponent(sessionId)}/brief/${encodeURIComponent(agentId)}`,
      { credentials: "include" },
    );
    if (!response.ok) throw new Error(`HTTP ${response.status}`);
    const body = (await response.json()) as { brief?: string };
    return body.brief ?? "";
  });
}

export async function getCheckpoints(sessionId: string): Promise<HITLCheckpoint[]> {
  return handleAuthError(async () => {
    const response = await fetch(
      `${API_BASE}/api/v1/sessions/${encodeURIComponent(sessionId)}/checkpoints`,
      { credentials: "include" },
    );
    if (!response.ok) throw new Error(`HTTP ${response.status}`);
    return response.json();
  });
}

export async function submitHITLDecision(decision: HITLDecisionRequest): Promise<void> {
  await handleAuthError(async () => {
    const headers = await getMutationHeaders({
      "Content-Type": "application/json",
    });
    const response = await fetch(`${API_BASE}/api/v1/hitl/decision`, {
      method: "POST",
      headers,
      credentials: "include",
      body: JSON.stringify(decision),
    });

    if (!response.ok) {
      const body = await response.json().catch(() => ({ detail: `HTTP ${response.status}` }));
      throw new Error(body.detail || `HTTP ${response.status}`);
    }
  });
}

export function createLiveSocket(sessionId: string): { ws: WebSocket; connected: Promise<void> } {
  const token = getAuthToken();
  const wsBase = getWSBase();  // Call function, not use constant
  const protocols = token ? ["forensic-v1", `token.${token}`] : ["forensic-v1"];
  const ws = new WebSocket(
    `${wsBase}/api/v1/sessions/${encodeURIComponent(sessionId)}/live`,
    protocols,
  );

  const connected = new Promise<void>((resolve, reject) => {
    let settled = false;

    const handleMessage = (event: MessageEvent) => {
      try {
        const payload = JSON.parse(event.data) as { type?: string; message?: string };
        if (
          payload.type === "CONNECTED" ||
          payload.type === "AGENT_UPDATE" ||
          payload.type === "PIPELINE_PAUSED" ||
          payload.type === "AGENT_COMPLETE" ||
          payload.type === "PIPELINE_COMPLETE" ||
          payload.type === "REPORT_READY" ||
          payload.type === "PIPELINE_QUARANTINED"
        ) {
          settle(resolve);
        } else if (payload.type === "ERROR") {
          const msg = payload.message || "WebSocket investigation error";
          settle(() => reject(new Error(msg)));
        }
      } catch {
        // Runtime messages are processed by useSimulation.
      }
    };

    const handleError = () => settle(() => reject(new Error("WebSocket connection error")));
    const handleClose = (event: CloseEvent) => {
      settle(() => reject(new Error(event.reason || `WebSocket closed unexpectedly (${event.code})`)));
    };

    const settle = (fn: () => void) => {
      if (settled) return;
      settled = true;
      clearTimeout(timeout);
      ws.removeEventListener("message", handleMessage);
      ws.removeEventListener("error", handleError);
      ws.removeEventListener("close", handleClose);
      fn();
    };

    const timeout = setTimeout(
      () => settle(() => reject(new Error("WebSocket connection timed out"))),
      LIVE_SOCKET_CONNECT_TIMEOUT_MS,
    );

    ws.addEventListener("message", handleMessage);
    ws.addEventListener("error", handleError);
    ws.addEventListener("close", handleClose);
  });

  return { ws, connected };
}

export async function getReport(sessionId: string): Promise<ReportResponse> {
  return handleAuthError(async () => {
    const response = await fetch(`${API_BASE}/api/v1/sessions/${sessionId}/report`, {
      credentials: "include",
    });

    if (response.status === 202) return { status: "in_progress" };
    if (!response.ok) throw new Error(`HTTP ${response.status}`);

    const rawData = await response.json();
    return { status: "complete", report: _parseReportDTO(rawData) };
  });
}

export async function getArbiterStatus(sessionId: string): Promise<ArbiterStatusResponse> {
    const response = await fetch(`${API_BASE}/api/v1/sessions/${sessionId}/arbiter-status`, {
        credentials: "include",
    });
    if (response.status === 404) return { status: "not_found" };
    return response.json();
}

export async function pollForReport(
  sessionId: string,
  onProgress?: (status: ReportResponse["status"]) => void,
  intervalMs = 2000,
  maxAttempts = 60,
): Promise<ReportDTO> {
  for (let attempt = 0; attempt < maxAttempts; attempt++) {
    const response = await getReport(sessionId);
    onProgress?.(response.status);
    if (response.status === "complete" && response.report) return response.report;
    
    if (attempt < maxAttempts - 1) {
      await new Promise((resolve) => setTimeout(resolve, intervalMs));
    }
  }
  throw new Error("Report polling timed out");
}

/** Legacy support and misc endpoints... (abbreviated for brevity) */
export async function logout(): Promise<void> {
    const headers = await getMutationHeaders();
    await fetch(`${API_BASE}/api/v1/auth/logout`, { method: "POST", headers, credentials: "include" });
    clearAuthToken();
}

export { getAuthToken };
