/**
 * Forensic Council API Client
 * ==========================
 *
 * Client module for communicating with the FastAPI backend.
 */

// ── API Base URL ─────────────────────────────────────────────────────────────
//
// CORS FIX: browser requests use an empty string (relative URL) so they hit
// /api/v1/... on the same origin (localhost:3000).  Next.js rewrites in
// next.config.ts then proxy those requests server-side to the backend via
// the Docker-internal INTERNAL_API_URL — the browser never makes a
// cross-origin request and CORS is bypassed entirely.
//
// Server-side (SSR / Next.js API routes) use the absolute internal URL so
// they can reach the backend container directly without going through a port.
const API_BASE =
  typeof window === "undefined"
    ? // Server-side: use Docker-internal service name or fall back to localhost
    process.env.INTERNAL_API_URL ||
    process.env.NEXT_PUBLIC_API_URL ||
    "http://localhost:8000"
    : // Browser: empty string → relative path → no cross-origin request
    "";

// WebSocket requires an absolute URL — derive from the public-facing API URL.
// This remains cross-origin but browsers don't apply the same CORS rules to
// WS upgrades; the backend validates via its AUTH message handshake instead.
const _WS_HTTP_BASE =
  process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";
const WS_BASE = _WS_HTTP_BASE.replace(
  /^https?/,
  (m) => (m === "https" ? "wss" : "ws")
);

// Token storage key
const TOKEN_KEY = "forensic_auth_token";

/**
 * Types matching backend DTOs
 */

export interface AgentFindingDTO {
  finding_id: string;
  agent_id: string;
  agent_name: string;
  finding_type: string;
  status: string;
  confidence_raw: number;
  calibrated: boolean;
  calibrated_probability: number | null;
  court_statement: string | null;
  robustness_caveat: boolean;
  robustness_caveat_detail: string | null;
  reasoning_summary: string;
}

export interface ReportDTO {
  report_id: string;
  session_id: string;
  case_id: string;
  executive_summary: string;
  per_agent_findings: Record<string, AgentFindingDTO[]>;
  cross_modal_confirmed: AgentFindingDTO[];
  contested_findings: Record<string, unknown>[];
  tribunal_resolved: Record<string, unknown>[];
  incomplete_findings: AgentFindingDTO[];
  uncertainty_statement: string;
  cryptographic_signature: string;
  report_hash: string;
  signed_utc: string;
}

export interface BriefUpdate {
  type: "AGENT_UPDATE" | "HITL_CHECKPOINT" | "AGENT_COMPLETE" | "PIPELINE_COMPLETE" | "ERROR" | "CONNECTED" | "PIPELINE_PAUSED";
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

export type HITLDecision = "APPROVE" | "REDIRECT" | "OVERRIDE" | "TERMINATE" | "ESCALATE";

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

/**
 * Authentication Functions
 */

export function getAuthToken(): string | null {
  if (typeof window === "undefined") return null;
  return localStorage.getItem(TOKEN_KEY);
}

export function setAuthToken(token: string): void {
  if (typeof window === "undefined") return;
  localStorage.setItem(TOKEN_KEY, token);
}

export function clearAuthToken(): void {
  if (typeof window === "undefined") return;
  localStorage.removeItem(TOKEN_KEY);
}

export function isAuthenticated(): boolean {
  return !!getAuthToken();
}

export async function login(username: string, password: string): Promise<TokenResponse> {
  const formData = new URLSearchParams();
  formData.append("username", username);
  formData.append("password", password);

  const response = await fetch(`${API_BASE}/api/v1/auth/login`, {
    method: "POST",
    headers: { "Content-Type": "application/x-www-form-urlencoded" },
    body: formData.toString(),
  });

  if (!response.ok) {
    const error = await response.json().catch(() => ({ detail: "Login failed" }));
    throw new Error(error.detail || "Authentication failed");
  }

  const data: TokenResponse = await response.json();
  setAuthToken(data.access_token);
  return data;
}

export async function autoLoginAsInvestigator(): Promise<TokenResponse> {
  const response = await fetch("/api/auth/demo", { method: "POST" });

  if (!response.ok) {
    const error = await response.json().catch(() => ({ error: "Demo auth failed" }));
    throw new Error(error.error || "Authentication failed");
  }

  const data: TokenResponse = await response.json();
  setAuthToken(data.access_token);
  return data;
}

export async function ensureAuthenticated(): Promise<string> {
  let token = getAuthToken();
  if (!token) {
    const authData = await autoLoginAsInvestigator();
    token = authData.access_token;
  }
  return token;
}

export async function logout(): Promise<void> {
  const token = getAuthToken();
  if (token) {
    try {
      await fetch(`${API_BASE}/api/v1/auth/logout`, {
        method: "POST",
        headers: { Authorization: `Bearer ${token}` },
      });
    } catch {
      // ignore
    }
  }
  clearAuthToken();
}

export async function getCurrentUser(): Promise<UserInfo> {
  const token = await ensureAuthenticated();
  const response = await fetch(`${API_BASE}/api/v1/auth/me`, {
    headers: { Authorization: `Bearer ${token}` },
  });

  if (!response.ok) {
    const error = await response.json().catch(() => ({ detail: "Failed to get user info" }));
    throw new Error(error.detail || "Failed to get user info");
  }

  return response.json();
}

const MAX_AUTH_RETRIES = 1;
let authRetryCount = 0;

function resetAuthRetry(): void {
  authRetryCount = 0;
}

async function handleAuthError<T>(
  operation: () => Promise<T>,
  _errorMessage: string
): Promise<T> {
  try {
    const result = await operation();
    resetAuthRetry();
    return result;
  } catch (error) {
    if (
      error instanceof Error &&
      (error.message.includes("Invalid or expired token") ||
        error.message.includes("401") ||
        error.message.includes("Unauthorized"))
    ) {
      if (authRetryCount < MAX_AUTH_RETRIES) {
        authRetryCount++;
        console.warn("Token invalid, clearing and re-authenticating...");
        clearAuthToken();
        try {
          const result = await operation();
          resetAuthRetry();
          return result;
        } catch {
          clearAuthToken();
          if (typeof window !== "undefined") {
            window.location.href = "/session-expired";
          }
          throw error;
        }
      } else {
        clearAuthToken();
        if (typeof window !== "undefined") {
          window.location.href = "/session-expired";
        }
      }
    }
    throw error;
  }
}

async function getAuthHeaders(): Promise<HeadersInit> {
  const token = await ensureAuthenticated();
  return { Authorization: `Bearer ${token}` };
}

/**
 * Start a forensic investigation
 */
export async function startInvestigation(
  file: File,
  caseId: string,
  investigatorId: string
): Promise<InvestigationResponse> {
  const caseIdRegex =
    /^CASE-(?:\d{10,14}|[a-f0-9]{8}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{12})$/i;
  const investigatorIdRegex = /^REQ-\d{5,10}$/i;

  if (!caseIdRegex.test(caseId)) {
    throw new Error("Invalid Case ID format. Expected CASE-[timestamp] or CASE-[uuid].");
  }
  if (!investigatorIdRegex.test(investigatorId)) {
    throw new Error("Invalid Investigator ID format. Expected REQ-[5-10 digits].");
  }

  return handleAuthError(async () => {
    const formData = new FormData();
    formData.append("file", file);
    formData.append("case_id", caseId);
    formData.append("investigator_id", investigatorId);

    const headers = await getAuthHeaders();
    const response = await fetch(`${API_BASE}/api/v1/investigate`, {
      method: "POST",
      headers,
      body: formData,
    });

    if (!response.ok) {
      const errorBody = await response.json().catch(() => ({ detail: "Unknown error" }));
      // In dev mode the backend also sets `message` with the real Python exception.
      // Surface it so stack traces are visible in the browser console.
      const detail = errorBody.detail || `HTTP ${response.status}`;
      const devHint = errorBody.message ? ` — ${errorBody.message}` : "";
      throw new Error(`${detail}${devHint}`);
    }

    return response.json();
  }, "Failed to start investigation");
}

/**
 * Get the report for a session
 */
export async function getReport(sessionId: string): Promise<ReportResponse> {
  return handleAuthError(async () => {
    const headers = await getAuthHeaders();
    const response = await fetch(`${API_BASE}/api/v1/sessions/${sessionId}/report`, {
      headers,
    });

    if (response.status === 404) throw new Error("Session not found");
    if (response.status === 202) return { status: "in_progress" };

    if (!response.ok) {
      const error = await response.json().catch(() => ({ detail: "Unknown error" }));
      throw new Error(error.detail || `HTTP ${response.status}`);
    }

    const report: ReportDTO = await response.json();
    return { status: "complete", report };
  }, "Failed to get report");
}

export async function getBrief(sessionId: string, agentId: string): Promise<string> {
  return handleAuthError(async () => {
    const headers = await getAuthHeaders();
    const response = await fetch(`${API_BASE}/api/v1/sessions/${sessionId}/brief/${agentId}`, {
      headers,
    });

    if (response.status === 404) return "No brief available.";
    if (!response.ok) {
      const error = await response.json().catch(() => ({ detail: "Unknown error" }));
      throw new Error(error.detail || `HTTP ${response.status}`);
    }

    const data = await response.json();
    return data.brief || "No brief available.";
  }, "Failed to get brief");
}

export async function getCheckpoints(sessionId: string): Promise<HITLCheckpoint[]> {
  return handleAuthError(async () => {
    const headers = await getAuthHeaders();
    const response = await fetch(`${API_BASE}/api/v1/sessions/${sessionId}/checkpoints`, {
      headers,
    });

    if (response.status === 404) return [];
    if (!response.ok) {
      const error = await response.json().catch(() => ({ detail: "Unknown error" }));
      throw new Error(error.detail || `HTTP ${response.status}`);
    }

    return response.json();
  }, "Failed to get checkpoints");
}

export async function submitHITLDecision(decision: HITLDecisionRequest): Promise<void> {
  return handleAuthError(async () => {
    const headers = await getAuthHeaders();
    const response = await fetch(`${API_BASE}/api/v1/hitl/decision`, {
      method: "POST",
      headers: { ...headers, "Content-Type": "application/json" },
      body: JSON.stringify(decision),
    });

    if (!response.ok) {
      const error = await response.json().catch(() => ({ detail: "Unknown error" }));
      throw new Error(error.detail || `HTTP ${response.status}`);
    }
  }, "Failed to submit decision");
}

/**
 * Create a WebSocket connection for live updates.
 *
 * IMPORTANT — connection lifecycle:
 *   1. Client opens WS to /api/v1/sessions/{id}/live
 *   2. `onopen` fires → client sends {"type":"AUTH","token":"..."}
 *   3. Server validates token, registers the socket, sends {"type":"CONNECTED"}
 *   4. The `connected` Promise resolves only on step 3 (CONNECTED message).
 *      This ensures broadcasts that start immediately after /investigate
 *      are never lost because the socket wasn't registered yet.
 */
export function createLiveSocket(
  sessionId: string
): { ws: WebSocket; connected: Promise<void> } {
  const wsUrl = `${WS_BASE}/api/v1/sessions/${sessionId}/live`;
  const ws = new WebSocket(wsUrl, ["forensic-v1"]);

  let resolveConnected!: () => void;
  let rejectConnected!: (err: Error) => void;
  let settled = false;

  const connected = new Promise<void>((resolve, reject) => {
    resolveConnected = resolve;
    rejectConnected = reject;
  });

  const safeResolve = () => {
    if (!settled) {
      settled = true;
      resolveConnected();
    }
  };
  const safeReject = (err: Error) => {
    if (!settled) {
      settled = true;
      rejectConnected(err);
    }
  };

  // Connection timeout — if CONNECTED not received within 12 s, fail
  const connectTimeout = setTimeout(() => {
    safeReject(new Error("WebSocket connection timed out — no CONNECTED message received"));
    ws.close();
  }, 12_000);

  ws.onopen = () => {
    console.log("[WS] Connected, sending AUTH");
    const token = getAuthToken();
    if (token) {
      ws.send(JSON.stringify({ type: "AUTH", token }));
    } else {
      // No token — will be rejected server-side
      safeReject(new Error("No auth token available for WebSocket"));
    }
  };

  ws.onerror = (event) => {
    console.error("[WS] Connection error", event);
    clearTimeout(connectTimeout);
    safeReject(new Error("WebSocket connection error"));
  };

  ws.onclose = (event) => {
    console.log("[WS] Closed:", event.code, event.reason);
    clearTimeout(connectTimeout);
    if (!settled) {
      safeReject(
        new Error(
          event.reason
            ? `WebSocket closed: ${event.reason}`
            : `WebSocket closed unexpectedly (code ${event.code})`
        )
      );
    }
  };

  // The first incoming message handler resolves `connected` on CONNECTED type.
  // After that, messages are routed through the caller-supplied onmessage.
  const originalOnMessage = ws.onmessage;
  ws.onmessage = (event: MessageEvent) => {
    try {
      const msg = JSON.parse(event.data as string);
      if ((msg.type === "CONNECTED" || msg.type === "AGENT_UPDATE") && !settled) {
        clearTimeout(connectTimeout);
        safeResolve();
      }
    } catch {
      // non-JSON or parse error — still resolve (unexpected but harmless)
      if (!settled) {
        clearTimeout(connectTimeout);
        safeResolve();
      }
    }
    // Forward to caller's handler if already attached
    if (originalOnMessage) {
      originalOnMessage.call(ws, event);
    }
    // Also call any handler set after this bootstrap listener
    // (will be overridden by useSimulation which sets ws.onmessage directly)
  };

  return { ws, connected };
}

/**
 * Poll for report completion
 */
export async function pollForReport(
  sessionId: string,
  onProgress: (status: string) => void,
  intervalMs = 5000,
  maxAttempts = 60
): Promise<ReportDTO> {
  return new Promise((resolve, reject) => {
    let intervalId: ReturnType<typeof setInterval>;
    let finished = false;
    let attempts = 0;

    const poll = async () => {
      if (finished) return;
      attempts++;
      if (attempts > maxAttempts) {
        finished = true;
        clearInterval(intervalId);
        reject(new Error("Polling timeout — investigation took too long"));
        return;
      }

      try {
        const result = await getReport(sessionId);
        if (result.status === "complete" && result.report) {
          finished = true;
          clearInterval(intervalId);
          resolve(result.report);
        } else {
          onProgress("in_progress");
        }
      } catch (error) {
        finished = true;
        clearInterval(intervalId);
        reject(error);
      }
    };

    intervalId = setInterval(poll, intervalMs);
    poll();
  });
}
