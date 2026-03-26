/**
 * Forensic Council API Client
 * ==========================
 *
 * Client module for communicating with the FastAPI backend.
 */

/** Dev-only logger — silenced in production builds */
const isDev = process.env.NODE_ENV !== "production";
const dbg = {
    log: isDev ? console.log.bind(console) : () => {},
    warn: isDev ? console.warn.bind(console) : () => {},
    error: isDev ? console.error.bind(console) : () => {},
};

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

// WebSocket — must use the SAME origin as the page so the browser sends the
// HttpOnly auth cookie with the upgrade request.  Connecting cross-origin
// (e.g. ws://localhost:8000 from a page on localhost:3000) causes the browser
// to omit the cookie, which closes the WS immediately with code 4001.
// Using window.location.host means the WS upgrade goes through the same
// origin (Next.js dev server or Caddy) which rewrites it to the backend —
// the proxy forwards all request headers including Cookie.
const WS_BASE =
  typeof window !== "undefined"
    ? `${window.location.protocol === "https:" ? "wss" : "ws"}://${window.location.host}`
    : (() => {
        const base = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";
        return base.replace(/^https?/, (m) => (m === "https" ? "wss" : "ws"));
      })();

// Token storage key
const TOKEN_KEY = "forensic_auth_token";
const TOKEN_EXPIRY_KEY = "forensic_auth_token_expiry";

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
  metadata: Record<string, unknown> | null;
  severity_tier?: string; // INFO / LOW / MEDIUM / HIGH / CRITICAL
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
  // Structured summary (Groq-synthesized)
  verdict_sentence?: string;
  key_findings?: string[];
  reliability_note?: string;
  manipulation_probability?: number;
  // Confidence range across active agents (C)
  confidence_min?: number;
  confidence_max?: number;
  confidence_std_dev?: number;
  applicable_agent_count?: number;
  skipped_agents?: Record<string, string>;
  analysis_coverage_note?: string;
  // Flat per-agent summary (D)
  per_agent_summary?: Record<string, {
    agent_name: string;
    verdict: string;
    confidence_pct: number;
    tools_ok: number;
    tools_total: number;
    findings: number;
    error_rate_pct: number;
    skipped: boolean;
  }>;
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

export function isAuthenticated(): boolean {
  return true; // With HttpOnly cookies, we assume authed if server doesn't return 401
}

export async function login(username: string, password: string): Promise<TokenResponse> {
  const formData = new URLSearchParams();
  formData.append("username", username);
  formData.append("password", password);

  const response = await fetch(`${API_BASE}/api/v1/auth/login`, {
    method: "POST",
    headers: { "Content-Type": "application/x-www-form-urlencoded" },
    body: formData.toString(),
    credentials: "include", // Required for cookies
  });

  if (!response.ok) {
    const error = await response.json().catch(() => ({ detail: "Login failed" }));
    throw new Error(error.detail || "Authentication failed");
  }

  const data: TokenResponse = await response.json();
  return data;
}

export async function autoLoginAsInvestigator(): Promise<TokenResponse> {
  const response = await fetch("/api/auth/demo", { method: "POST" });

  if (!response.ok) {
    const error = await response.json().catch(() => ({ error: "Demo auth failed" }));
    throw new Error(error.error || "Authentication failed");
  }

  const data: TokenResponse = await response.json();
  return data;
}

export async function ensureAuthenticated(): Promise<void> {
  // We don't check for token locally anymore; assume authed or let 401 trigger logic
}

export async function logout(): Promise<void> {
  try {
    await fetch(`${API_BASE}/api/v1/auth/logout`, {
      method: "POST",
      credentials: "include",
    });
  } catch {
    // ignore
  }
}

export async function getCurrentUser(): Promise<UserInfo> {
  const response = await fetch(`${API_BASE}/api/v1/auth/me`, {
    credentials: "include",
  });

  if (!response.ok) {
    const error = await response.json().catch(() => ({ detail: "Failed to get user info" }));
    throw new Error(error.detail || "Failed to get user info");
  }

  return response.json();
}

// E6 fix: use a per-invocation retry flag instead of a shared module-level
// counter, which was not safe for concurrent requests (two simultaneous 401s
// would both increment the counter and block each other's legitimate retry).
async function handleAuthError<T>(
  operation: () => Promise<T>
): Promise<T> {
  let retried = false;
  try {
    return await operation();
  } catch (error) {
    if (
      error instanceof Error &&
      (error.message.includes("Invalid or expired token") ||
        error.message.includes("401") ||
        error.message.includes("Unauthorized") ||
        error.message.includes("Not authenticated"))
    ) {
      if (!retried) {
        retried = true;
        dbg.warn("Token invalid, re-authenticating...");
        try {
          await autoLoginAsInvestigator();
          return await operation();
        } catch {
          if (typeof window !== "undefined") {
            window.location.href = "/session-expired";
          }
          throw error;
        }
      } else {
        if (typeof window !== "undefined") {
          window.location.href = "/session-expired";
        }
      }
    }
    throw error;
  }
}

async function getAuthHeaders(): Promise<HeadersInit> {
  return {}; // Auth now handled via HttpOnly cookies automatically
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

    const response = await fetch(`${API_BASE}/api/v1/investigate`, {
      method: "POST",
      body: formData,
      credentials: "include", // Send HttpOnly cookie
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
  });
}

export interface ArbiterStatusResponse {
  status: "running" | "complete" | "error" | "not_found";
  message?: string;
  report_id?: string;
}

/**
 * Poll arbiter compilation status (lightweight — no report body)
 */
export async function getArbiterStatus(sessionId: string): Promise<ArbiterStatusResponse> {
  return handleAuthError(async () => {
    const response = await fetch(`${API_BASE}/api/v1/sessions/${sessionId}/arbiter-status`, {
      credentials: "include",
    });
    if (!response.ok) return { status: "not_found" };
    return response.json();
  });
}

/**
 * Get the report for a session
 */
export async function getReport(sessionId: string): Promise<ReportResponse> {
  return handleAuthError(async () => {
    const response = await fetch(`${API_BASE}/api/v1/sessions/${sessionId}/report`, {
      credentials: "include",
    });

    if (response.status === 404) throw new Error("Session not found");
    if (response.status === 202) return { status: "in_progress" };

    if (!response.ok) {
      const error = await response.json().catch(() => ({ detail: "Unknown error" }));
      throw new Error(error.detail || `HTTP ${response.status}`);
    }

    const report: ReportDTO = await response.json();
    return { status: "complete", report };
  });
}

export async function getBrief(sessionId: string, agentId: string): Promise<string> {
  return handleAuthError(async () => {
    const response = await fetch(`${API_BASE}/api/v1/sessions/${sessionId}/brief/${agentId}`, {
      credentials: "include",
    });

    if (response.status === 404) return "No brief available.";
    if (!response.ok) {
      const error = await response.json().catch(() => ({ detail: "Unknown error" }));
      throw new Error(error.detail || `HTTP ${response.status}`);
    }

    const data = await response.json();
    return data.brief || "No brief available.";
  });
}

export async function getCheckpoints(sessionId: string): Promise<HITLCheckpoint[]> {
  return handleAuthError(async () => {
    const response = await fetch(`${API_BASE}/api/v1/sessions/${sessionId}/checkpoints`, {
      credentials: "include",
    });

    if (response.status === 404) return [];
    if (!response.ok) {
      const error = await response.json().catch(() => ({ detail: "Unknown error" }));
      throw new Error(error.detail || `HTTP ${response.status}`);
    }

    return response.json();
  });
}

export async function submitHITLDecision(decision: HITLDecisionRequest): Promise<void> {
  return handleAuthError(async () => {
    const response = await fetch(`${API_BASE}/api/v1/hitl/decision`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      credentials: "include",
      body: JSON.stringify(decision),
    });

    if (!response.ok) {
      const error = await response.json().catch(() => ({ detail: "Unknown error" }));
      throw new Error(error.detail || `HTTP ${response.status}`);
    }
  });
}

/**
 * Create a WebSocket connection for live updates.
 *
 * IMPORTANT — connection lifecycle:
 *   1. Client opens WS to /api/v1/sessions/{id}/live
 *   2. `onopen` fires
 *   3. Server validates cookie, registers the socket, sends {"type":"CONNECTED"}
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
    dbg.log("[WS] Connected");
    // AUTH message no longer needed; server checks cookie on handshake
  };

  ws.onerror = (event) => {
    dbg.error("[WS] Connection error", event);
    clearTimeout(connectTimeout);
    safeReject(new Error("WebSocket connection error"));
  };

  ws.onclose = (event) => {
    dbg.log("[WS] Closed:", event.code, event.reason);
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
    // eslint-disable-next-line prefer-const -- intervalId must be declared before poll function that uses it
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
