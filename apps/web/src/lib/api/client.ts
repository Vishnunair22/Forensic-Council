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
 * Authenticated fetch wrapper that intercepts 401 responses.
 * On 401, clears auth state and redirects to session-expired page.
 */
export async function apiFetch(url: string, options: RequestInit = {}): Promise<Response> {
  const response = await fetch(url, { credentials: "include", ...options });
  if (response.status === 401) {
    // HttpOnly cookies cannot be cleared via document.cookie — the server-side
    // logout endpoint sets Max-Age=0. We only dispatch the session-expired event
    // so the UI can redirect; cookie cleanup happens on the next server-side logout.
    if (typeof window !== "undefined") {
      window.dispatchEvent(new CustomEvent("fc:session-expired"));
    }
  }
  return response;
}

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

  console.error("[telemetry] schema_validation_error:", {
    schema: "ReportDTO",
    error: result.error.errors,
    url: typeof window !== "undefined" ? window.location.href : "server",
  });

  // Log strictly but allow the UI to try and render whatever matches the interface.
  return raw as ReportDTO;
}

/**
 * Attempt to refresh the auth token. Uses the shared apiFetch wrapper so that
 * a 401 from the refresh endpoint triggers the session-expired redirect instead
 * of silently failing in the WS reconnect path.
 * Returns true if the refresh succeeded.
 */
export async function refreshAuthToken(): Promise<boolean> {
  try {
    const response = await apiFetch(`${API_BASE}/api/v1/auth/refresh`, {
      method: "POST",
    });
    return response.ok;
  } catch {
    dbg.warn("[api] Token refresh network error");
    return false;
  }
}

export class ProtocolWarmingError extends Error {
  constructor(message = "Protocol warming up — system dependencies initializing") {
    super(message);
    this.name = "ProtocolWarmingError";
  }
}

export class WorkerWarmupError extends Error {
  constructor(message = "System warming up — forensic worker is initializing") {
    super(message);
    this.name = "WorkerWarmupError";
  }
}

export class DuplicateInvestigationError extends Error {
  constructor(public existingSessionId: string, message = "Duplicate investigation request") {
    super(message);
    this.name = "DuplicateInvestigationError";
  }
}

function normalizeApiDetail(detail: unknown, fallback: string): string {
  if (!detail) return fallback;

  if (typeof detail === "string") return detail;

  if (Array.isArray(detail)) {
    return detail
      .map((item) => {
        if (typeof item === "string") return item;
        if (item && typeof item === "object") {
          const record = item as Record<string, unknown>;
          return String(record.msg ?? record.message ?? JSON.stringify(record));
        }
        return String(item);
      })
      .join("; ");
  }

  if (typeof detail === "object") {
    const record = detail as Record<string, unknown>;
    return String(
      record.message ??
      record.detail ??
      record.error ??
      JSON.stringify(record),
    );
  }

  return String(detail);
}

function extractDuplicateSessionId(detail: unknown): string | null {
  if (detail === null || detail === undefined) return null;

  if (typeof detail === "string") {
    const match = detail.match(/Duplicate detected:\s*session\s+(?:b['"])?([0-9a-fA-F-]+)/);
    if (match) return match[1];
    return null;
  }

  if (typeof detail === "object") {
    const d = detail as Record<string, unknown>;
    if (d.existing_session_id && typeof d.existing_session_id === "string") {
      return d.existing_session_id;
    }
    if (d.session_id && typeof d.session_id === "string") {
      return d.session_id;
    }
    if (d.code === "duplicate_investigation") {
      return typeof d.existing_session_id === "string" ? d.existing_session_id : null;
    }
    if (d.detail && typeof d.detail === "object") {
      const nested = d.detail as Record<string, unknown>;
      if (nested.existing_session_id && typeof nested.existing_session_id === "string") {
        return nested.existing_session_id;
      }
      if (nested.session_id && typeof nested.session_id === "string") {
        return nested.session_id;
      }
      if (nested.code === "duplicate_investigation") {
        return typeof nested.existing_session_id === "string" ? nested.existing_session_id : null;
      }
    }
  }

  return null;
}


/**
 * Checks backend health and warming status.
 */
export async function checkBackendHealth(): Promise<{ ok: boolean; warmingUp?: boolean; message: string }> {
  try {
    const response = await fetch(`${API_BASE}/api/v1/health`, {
      method: "GET",
      cache: "no-store",
      // Allow Docker cold starts and first-use Next proxy compilation to finish.
      signal: AbortSignal.timeout(120_000),
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

  const promise = (async (): Promise<TokenResponse> => {
    const maxRetries = 3;
    for (let attempt = 0; attempt <= maxRetries; attempt++) {
      try {
        const response = await fetch("/api/auth/demo", {
          method: "POST",
          signal: AbortSignal.timeout(120_000),
        });

        if (!response.ok) {
          if (response.status === 503 && attempt < maxRetries) throw new ProtocolWarmingError();
          throw new Error("Authentication failed");
        }

        const data: TokenResponse = await response.json();
        return data;
      } catch (err) {
        if (attempt === maxRetries) throw err;
        await new Promise((r) => setTimeout(r, Math.min(1000 * 2 ** attempt, 5000)));
      }
    }
    throw new Error("Demo login exhausted retries");
  })();

  _pendingAuth = promise;

  try {
    return await promise;
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
    const isCsrfError = msg.includes("403") || msg.includes("CSRF");

    if ((isAuthError || isCsrfError) && _retryCount < 2) {
      dbg.warn("Session/CSRF invalid, re-authenticating...");
      await autoLoginAsInvestigator();
      const healthCheck = await fetch(`${API_BASE}/api/v1/health`, { credentials: "include", cache: "no-store" });
      if (healthCheck.ok) {
        return await handleAuthError(operation, _retryCount + 1);
      }
      // Re-auth failed - redirect to session expiry page
      if (typeof window !== "undefined") {
        window.location.href = "/session-expired";
        return Promise.reject(new Error("Session expired"));
      }
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
  clientSha256?: string | null,
): Promise<InvestigationResponse> {
  return handleAuthError(async () => {
    const formData = new FormData();
    formData.append("file", file);
    formData.append("case_id", caseId);
    formData.append("investigator_id", investigatorId);
    if (clientSha256) {
      formData.append("client_sha256", clientSha256);
    }

    const headers = await getMutationHeaders();
    const response = await fetch(`${API_BASE}/api/v1/investigate`, {
      method: "POST",
      headers,
      body: formData,
      credentials: "include",
      signal: AbortSignal.timeout(60_000), // 60s timeout for file upload
    });

    if (!response.ok) {
      const err = await response.json().catch(() => ({ detail: "Upload failed" }));
      if (response.status === 409) {
        const existingSessionId = extractDuplicateSessionId(err.detail);
        if (existingSessionId) {
          throw new DuplicateInvestigationError(
            existingSessionId,
            normalizeApiDetail(err.detail, "Duplicate investigation request"),
          );
        }
      }
      if (response.status === 503) {
        const detailStr = typeof err.detail === "string" ? err.detail : "";
        if (detailStr.includes("worker is not running") || detailStr.includes("warming up")) {
          throw new WorkerWarmupError(detailStr);
        }
      }
      throw new Error(normalizeApiDetail(err.detail, `HTTP ${response.status}`));
    }
    return response.json();
  });
}

export async function getBrief(sessionId: string, agentId: string): Promise<string> {
  return handleAuthError(async () => {
    const response = await fetch(
      `${API_BASE}/api/v1/sessions/${encodeURIComponent(sessionId)}/brief/${encodeURIComponent(agentId)}`,
      { credentials: "include", cache: "no-store" },
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
      { credentials: "include", cache: "no-store" },
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
  const wsBase = getWSBase();  // Call function, not use constant
  // Use only the forensic-v1 subprotocol. The access_token is always sent
  // as an HttpOnly cookie in the WS upgrade request (post-demo-login).
  // If no csrf_token (proxy for auth readiness) is present, the caller
  // must re-auth before opening the socket.
  const ws = new WebSocket(
    `${wsBase}/api/v1/sessions/${encodeURIComponent(sessionId)}/live`,
    ["forensic-v1"],
  );

  const connected = new Promise<void>((resolve, reject) => {
    let settled = false;
    let receivedBootstrap = false;

    const handleError = () => settle(() => reject(new Error("WebSocket connection error")));
    const handleMessage = (event: MessageEvent) => {
      try {
        const payload = JSON.parse(event.data) as { type?: unknown };
        if (payload.type === "CONNECTED" || payload.type === "AGENT_UPDATE") {
          receivedBootstrap = true;
          settle(resolve);
        }
      } catch {
        // Ignore malformed bootstrap messages. The main socket consumer logs
        // parse failures and the timeout still protects this handshake.
      }
    };
    const handleClose = (event: CloseEvent) => {
      if (event.code === 1000 && receivedBootstrap) {
        settle(resolve);
        return;
      }
      settle(() => reject(new Error(event.reason || `WebSocket closed before connection was ready (${event.code})`)));
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
  connected.catch(() => {});

  return { ws, connected };
}

export interface SSEConnection {
  close: () => void;
}

export function connectLiveSSE(
  sessionId: string,
  onMessage: (data: unknown) => void,
  onError?: (err: Error) => void
): SSEConnection {
  let es: EventSource | null = null;
  let closed = false;
  let reconnectAttempt = 0;
  let reconnectTimer: NodeJS.Timeout | null = null;

  const retryDelays = [1500, 3000, 6000];

  function getRetryDelay(attempt: number): number {
    if (attempt < retryDelays.length) {
      return retryDelays[attempt];
    }
    return retryDelays[retryDelays.length - 1];
  }

  function connect() {
    if (closed) return;

    const url = `${API_BASE}/api/v1/sessions/${encodeURIComponent(sessionId)}/progress`;

    es = new EventSource(url, { withCredentials: true });

    es.onopen = () => {
      reconnectAttempt = 0;
    };

    es.onmessage = (event) => {
      try {
        const data = JSON.parse(event.data);
        onMessage(data);
      } catch (err) {
        dbg.error("[SSE] Failed to parse message:", err);
      }
    };

    es.onerror = () => {
      if (closed) return;
      dbg.warn("[SSE] Connection error. Attempting reconnect...");
      
      if (es) {
        es.close();
        es = null;
      }

      const delay = getRetryDelay(reconnectAttempt);
      reconnectAttempt++;

      if (onError) {
        onError(new Error(`Connection lost. Reconnecting in ${delay / 1000}s...`));
      }

      reconnectTimer = setTimeout(() => {
        connect();
      }, delay);
    };
  }

  connect();

  return {
    close: () => {
      closed = true;
      if (reconnectTimer) {
        clearTimeout(reconnectTimer);
      }
      if (es) {
        es.close();
        es = null;
      }
    }
  };
}

export async function getReport(sessionId: string): Promise<ReportResponse> {
  return handleAuthError(async () => {
    const response = await fetch(`${API_BASE}/api/v1/sessions/${encodeURIComponent(sessionId)}/report`, {
      credentials: "include",
      // The report can change for the same session (initial → deep, or re-run),
      // so it must never be served from the browser HTTP cache — that surfaced
      // stale findings after deep analysis completed.
      cache: "no-store",
    });

    if (response.status === 202) return { status: "in_progress" };
    if (!response.ok) throw new Error(`HTTP ${response.status}`);

    const rawData = await response.json();

    const reportPayload =
      rawData &&
      typeof rawData === "object" &&
      "report" in rawData
        ? (rawData as { report: unknown }).report
        : rawData;

    return { status: "complete", report: _parseReportDTO(reportPayload) };
  });
}

export async function getArbiterStatus(sessionId: string): Promise<ArbiterStatusResponse> {
  return handleAuthError(async () => {
    const response = await apiFetch(
      `${API_BASE}/api/v1/sessions/${encodeURIComponent(sessionId)}/arbiter-status`,
      {
        cache: "no-store",
      },
    );

    if (response.status === 404) return { status: "not_found" };

    if (!response.ok) {
      throw new Error(`Arbiter status failed (${response.status})`);
    }

    return response.json();
  }).catch((error) => {
    dbg.warn("[api] getArbiterStatus error:", error);
    if (error instanceof Error && (error.message.includes("401") || error.message.includes("Session expired"))) {
      throw error;
    }
    return {
      status: "unreachable",
      message: error instanceof Error ? error.message : "Backend unreachable",
    } as ArbiterStatusResponse;
  });
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
