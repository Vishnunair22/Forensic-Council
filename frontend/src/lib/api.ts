/**
 * Forensic Council API Client
 * ==========================
 *
 * Client module for communicating with the FastAPI backend.
 */

import { ReportDTOSchema } from "@/lib/schemas";

function _parseReportDTO(raw: unknown): ReportDTO {
  try {
    return ReportDTOSchema.parse(raw) as unknown as ReportDTO;
  } catch {
    // Schema validation failed — return the raw data cast to ReportDTO so the
    // UI still renders rather than silently breaking.
    return raw as ReportDTO;
  }
}

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
export const API_BASE =
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
    ? (() => {
        // Preference 1: Manually set NEXT_PUBLIC_WS_URL
        if (process.env.NEXT_PUBLIC_WS_URL) return process.env.NEXT_PUBLIC_WS_URL;

        const { protocol, host, port } = window.location;
        const wsProto = protocol === "https:" ? "wss" : "ws";

        // Preference 2: Development direct-to-backend fallback
        // If the frontend is on port 3000 (Next.js dev), it CANNOT proxy WebSockets
        // through its App Router 'proxy' route. We must connect directly to the
        // backend port (default 8000) instead.
        if (port === "3000") {
          return `${wsProto}://localhost:8000`;
        }

        // Preference 3: Standard same-origin (handled by reverse proxy like Caddy)
        return `${wsProto}://${host}`;
      })()
    : // Server-side (fallback): use API URL base
      (() => {
        const base =
          process.env.INTERNAL_API_URL ||
          process.env.NEXT_PUBLIC_API_URL ||
          "http://localhost:8000";
        return base.replace(/^https?/, (m) => (m === "https" ? "wss" : "ws"));
      })();

// Token storage key — used for non-HttpOnly auth flows and test compatibility
const _TOKEN_KEY = "forensic_auth_token";
const _TOKEN_EXPIRY_KEY = "forensic_auth_token_expiry";

function readCookie(name: string): string | null {
  if (typeof document === "undefined") return null;

  const match = document.cookie.match(
    new RegExp(`(?:^|; )${name.replace(/[.*+?^${}()|[\]\\]/g, "\\$&")}=([^;]*)`),
  );
  return match ? decodeURIComponent(match[1]) : null;
}

async function _waitForCookie(name: string, maxMs = 2000): Promise<string | null> {
  const start = Date.now();
  while (Date.now() - start < maxMs) {
    const val = readCookie(name);
    if (val) return val;
    await new Promise((r) => setTimeout(r, 100));
  }
  return null;
}

async function ensureCsrfToken(): Promise<string | null> {
  if (typeof window === "undefined") return null;

  const token = readCookie("csrf_token");
  if (token) return token;

  try {
    // Hit health endpoint to get the CSRF cookie — wait for browser to persist it.
    // The Next.js API proxy forwards the Set-Cookie header.
    await fetch(`${API_BASE}/api/v1/health`, {
      method: "GET",
      credentials: "include",
      cache: "no-store",
      signal: AbortSignal.timeout(5_000),
    });
    return await _waitForCookie("csrf_token");
  } catch {
    return null;
  }
}

export async function getMutationHeaders(init?: HeadersInit): Promise<Headers> {
  const headers = new Headers(init);
  const csrfToken = await ensureCsrfToken();

  if (csrfToken) {
    headers.set("X-CSRF-Token", csrfToken);
  }

  return headers;
}

export const API_TIMEOUT = 30000;

export function withTimeout<T>(
  promise: Promise<T>,
  timeoutMs: number = API_TIMEOUT,
): Promise<T> {
  return Promise.race([
    promise,
    new Promise<T>((_, reject) =>
      setTimeout(
        () => reject(new Error(`Request timeout after ${timeoutMs}ms`)),
        timeoutMs,
      ),
    ),
  ]);
}

/**
 * Set an auth token in sessionStorage (compatibility wrapper).
 * HttpOnly cookie flow is the primary auth mechanism, but this is
 * retained for test suites and optional bearer-token flows.
 */
export function setAuthToken(token: string, expiresInSec?: number): void {
  if (typeof window !== "undefined") {
    sessionStorage.setItem(_TOKEN_KEY, token);
    if (expiresInSec) {
      sessionStorage.setItem(
        _TOKEN_EXPIRY_KEY,
        String(Date.now() + expiresInSec * 1000),
      );
    }
  }
}

/**
 * Retrieve the stored auth token, or null if absent/expired.
 */
export function getAuthToken(): string | null {
  if (typeof window === "undefined") return null;
  const expiry = sessionStorage.getItem(_TOKEN_EXPIRY_KEY);
  if (expiry && Date.now() > Number(expiry)) {
    sessionStorage.removeItem(_TOKEN_KEY);
    sessionStorage.removeItem(_TOKEN_EXPIRY_KEY);
    return null;
  }
  return sessionStorage.getItem(_TOKEN_KEY);
}

/**
 * Clear the stored auth token.
 */
export function clearAuthToken(): void {
  if (typeof window !== "undefined") {
    sessionStorage.removeItem(_TOKEN_KEY);
    sessionStorage.removeItem(_TOKEN_EXPIRY_KEY);
  }
}

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
  calibrated_probability: number | null; // DEPRECATED — use raw_confidence_score
  raw_confidence_score: number | null;
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
  // Degradation transparency — non-empty when analysis ran in reduced-capability mode.
  // Always render a visible warning when this array is non-empty.
  degradation_flags?: string[];
}

export interface BriefUpdate {
  type:
    | "AGENT_UPDATE"
    | "HITL_CHECKPOINT"
    | "AGENT_COMPLETE"
    | "PIPELINE_COMPLETE"
    | "ERROR"
    | "CONNECTED"
    | "PIPELINE_PAUSED";
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

export function isAuthenticated(): boolean {
  // HttpOnly cookies are not visible to JavaScript.
  // If a session token is explicitly stored (test/compatibility flow), use it.
  // Otherwise, assume the HttpOnly cookie auth flow is active and let the
  // API call determine validity (401 triggers re-auth in handleAuthError).
  if (getAuthToken() !== null) return true;
  // Only check for actual forensic council session cookies
  if (typeof document !== "undefined") {
    return (
      document.cookie.includes("fc_session=") ||
      document.cookie.includes("sessionid=")
    );
  }
  return false;
}

export async function login(
  username: string,
  password: string,
): Promise<TokenResponse> {
  const formData = new URLSearchParams();
  formData.append("username", username);
  formData.append("password", password);

  const response = await fetch(`${API_BASE}/api/v1/auth/login`, {
    method: "POST",
    headers: await getMutationHeaders({
      "Content-Type": "application/x-www-form-urlencoded",
    }),
    body: formData.toString(),
    credentials: "include", // Required for cookies
  });

  if (!response.ok) {
    const error = await response
      .json()
      .catch(() => ({ detail: "Login failed" }));
    throw new Error(error.detail || "Authentication failed");
  }

  const data: TokenResponse = await response.json();
  return data;
}

let _pendingAuth: Promise<TokenResponse> | null = null;

export async function autoLoginAsInvestigator(): Promise<TokenResponse> {
  if (_pendingAuth) return _pendingAuth;

  _pendingAuth = (async () => {
    try {
      const response = await fetch("/api/auth/demo", {
        method: "POST",
        signal: AbortSignal.timeout(12_000),
      });

      if (!response.ok) {
        const error = await response
          .json()
          .catch(() => ({ error: "Demo auth failed" }));
        throw new Error(error.error || "Authentication failed");
      }

      const data: TokenResponse = await response.json();

      // CRITICAL: Store the token in sessionStorage so that createLiveSocket can
      // include it in the WebSocket subprotocol (`token.<JWT>`).
      //
      // Why this is necessary:
      //   - In dev, WS connects directly to ws://localhost:8000 (not through the
      //     Next.js proxy on :3000). The auth cookie is set by the Next.js demo
      //     route on the :3000 origin and is HttpOnly (invisible to JS).
      //   - Same-site=strict / cross-origin rules mean the :3000 cookie is NEVER
      //     sent to the :8000 WebSocket endpoint.
      //   - The backend WS handler falls back to the `token.<JWT>` subprotocol,
      //     but only if the token was passed in — which requires it to be readable
      //     by JS (sessionStorage is the correct place here).
      if (data.access_token && typeof data.expires_in === "number") {
        setAuthToken(data.access_token, data.expires_in);
      }

      return data;
    } finally {
      // Clear the lock after a small delay to allow subsequent legitimate calls
      // but block immediate rapid-fire bursts from a React render loop.
      setTimeout(() => {
        _pendingAuth = null;
      }, 500);
    }
  })();

  return _pendingAuth;
}

export async function ensureAuthenticated(): Promise<void> {
  // Verify the session is active by hitting the /me endpoint.
  // If the cookie is missing or expired, attempt a demo re-login.
  try {
    const res = await fetch(`${API_BASE}/api/v1/auth/me`, {
      credentials: "include",
      signal: AbortSignal.timeout(5_000),
    });
    if (res.ok) return;
  } catch {
    // network error — fall through to re-login attempt
  }
  // Session invalid or expired — attempt auto-login
  await autoLoginAsInvestigator();
}

export async function logout(): Promise<void> {
  try {
    const headers = await getMutationHeaders();
    await fetch(`${API_BASE}/api/v1/auth/logout`, {
      method: "POST",
      headers,
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
    const error = await response
      .json()
      .catch(() => ({ detail: "Failed to get user info" }));
    throw new Error(error.detail || "Failed to get user info");
  }

  return response.json();
}

// E6 fix: use a per-invocation retry flag instead of a shared module-level
// counter, which was not safe for concurrent requests (two simultaneous 401s
// would both increment the counter and block each other's legitimate retry).
async function handleAuthError<T>(operation: () => Promise<T>): Promise<T> {
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
    }
    throw error;
  }
}


/** Redis/content dedup: same file + case already has an active session (HTTP 409). */
export class DuplicateInvestigationError extends Error {
  readonly existingSessionId: string;

  constructor(existingSessionId: string, message?: string) {
    super(
      message ?? `Duplicate evidence — existing session ${existingSessionId}`,
    );
    this.name = "DuplicateInvestigationError";
    this.existingSessionId = existingSessionId;
  }
}

function _parseSessionIdFromDetail(detail: unknown): string | null {
  const d = typeof detail === "string" ? detail : "";
  const m = d.match(
    /([0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12})/i,
  );
  return m?.[1] ?? null;
}

/**
 * Start a forensic investigation
 */
export async function startInvestigation(
  file: File,
  caseId: string,
  investigatorId: string,
): Promise<InvestigationResponse> {
  const caseIdRegex =
    /^CASE-(?:\d{10,14}|[a-f0-9]{8}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{12})$/i;
  const investigatorIdRegex = /^REQ-\d{5,10}$/i;

  if (!caseIdRegex.test(caseId)) {
    throw new Error(
      "Invalid Case ID format. Expected CASE-[timestamp] or CASE-[uuid].",
    );
  }
  if (!investigatorIdRegex.test(investigatorId)) {
    throw new Error(
      "Invalid Investigator ID format. Expected REQ-[5-10 digits].",
    );
  }

  return handleAuthError(async () => {
    const formData = new FormData();
    formData.append("file", file);
    formData.append("case_id", caseId);
    formData.append("investigator_id", investigatorId);

    // Retry on network errors (backend may still be booting)
    const maxRetries = 3;
    let lastError: unknown;
    for (let attempt = 0; attempt <= maxRetries; attempt++) {
      try {
        const headers = await getMutationHeaders();
        const response = await fetch(`${API_BASE}/api/v1/investigate`, {
          method: "POST",
          headers,
          body: formData,
          credentials: "include",
          signal: AbortSignal.timeout(25_000), // Uploads take longer but must still timeout
        });

        if (!response.ok) {
          const errorBody = await response
            .json()
            .catch(() => ({ detail: `HTTP ${response.status} ${response.statusText}`.trim() }));
          const detailRaw = errorBody.detail;
          const detail =
            typeof detailRaw === "string"
              ? detailRaw
              : Array.isArray(detailRaw)
                ? JSON.stringify(detailRaw)
                : String(detailRaw ?? `HTTP ${response.status}`);
          const devHint = errorBody.message ? ` — ${errorBody.message}` : "";

          if (response.status === 409) {
            const fromHeader = response.headers
              .get("X-Existing-Session")
              ?.trim();
            const existing =
              (fromHeader && /^[0-9a-f-]{36}$/i.test(fromHeader)
                ? fromHeader
                : null) ?? _parseSessionIdFromDetail(detail);
            if (existing) {
              throw new DuplicateInvestigationError(
                existing,
                `${detail}${devHint}`,
              );
            }
          }

          throw new Error(`${detail}${devHint}`);
        }

        return response.json();
      } catch (err) {
        lastError = err;
        // Only retry on network errors (TypeError: Failed to fetch)
        if (err instanceof TypeError && attempt < maxRetries) {
          const delay = Math.min(1000 * 2 ** attempt, 4000);
          dbg.warn(
            `Investigation fetch failed (attempt ${attempt + 1}/${maxRetries + 1}), retrying in ${delay}ms...`,
          );
          await new Promise((r) => setTimeout(r, delay));
          continue;
        }
        throw err;
      }
    }
    throw lastError;
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
export async function getArbiterStatus(
  sessionId: string,
): Promise<ArbiterStatusResponse> {
  return handleAuthError(async () => {
    const response = await fetch(
      `${API_BASE}/api/v1/sessions/${sessionId}/arbiter-status`,
      {
        credentials: "include",
      },
    );
    if (response.status === 404) return { status: "not_found" };
    if (!response.ok) {
      const errText = await response.text().catch(() => response.statusText);
      return {
        status: "running",
        message: `Server error (${response.status}): ${errText.slice(0, 100)}`,
      };
    }
    return response.json();
  });
}

/**
 * Get the report for a session
 */
export async function getReport(
  sessionId: string,
  timeoutMs = 30_000,
): Promise<ReportResponse> {
  return handleAuthError(async () => {
    const controller = new AbortController();
    const timeoutId = setTimeout(() => controller.abort(), timeoutMs);
    try {
      const response = await fetch(
        `${API_BASE}/api/v1/sessions/${sessionId}/report`,
        {
          credentials: "include",
          signal: controller.signal,
        },
      );

      if (response.status === 404) throw new Error("Session not found");
      if (response.status === 202) return { status: "in_progress" };

      if (!response.ok) {
        const error = await response
          .json()
          .catch(() => ({ detail: "Unknown error" }));
        throw new Error(error.detail || `HTTP ${response.status}`);
      }

      const rawData: unknown = await response.json();
      const report: ReportDTO = _parseReportDTO(rawData);
      return { status: "complete", report };
    } finally {
      clearTimeout(timeoutId);
    }
  });
}

export async function getBrief(
  sessionId: string,
  agentId: string,
): Promise<string> {
  return handleAuthError(async () => {
    const response = await fetch(
      `${API_BASE}/api/v1/sessions/${sessionId}/brief/${agentId}`,
      {
        credentials: "include",
      },
    );

    if (response.status === 404) return "No brief available.";
    if (!response.ok) {
      const error = await response
        .json()
        .catch(() => ({ detail: "Unknown error" }));
      throw new Error(error.detail || `HTTP ${response.status}`);
    }

    const data = await response.json();
    return data.brief || "No brief available.";
  });
}

export async function getCheckpoints(
  sessionId: string,
): Promise<HITLCheckpoint[]> {
  return handleAuthError(async () => {
    const response = await fetch(
      `${API_BASE}/api/v1/sessions/${sessionId}/checkpoints`,
      {
        credentials: "include",
      },
    );

    if (response.status === 404) return [];
    if (!response.ok) {
      const error = await response
        .json()
        .catch(() => ({ detail: "Unknown error" }));
      throw new Error(error.detail || `HTTP ${response.status}`);
    }

    return response.json();
  });
}

export async function submitHITLDecision(
  decision: HITLDecisionRequest,
): Promise<void> {
  return handleAuthError(async () => {
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
      const error = await response
        .json()
        .catch(() => ({ detail: "Unknown error" }));
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
export function createLiveSocket(sessionId: string): {
  ws: WebSocket;
  connected: Promise<void>;
} {
  const wsUrl = `${WS_BASE}/api/v1/sessions/${sessionId}/live`;

  // Include the auth token in subprotocols (token.<JWT>) as a robust fallback
  // if cookies are stripped by a proxy or blocked in certain cross-origin dev flows.
  const protocols = ["forensic-v1"];
  const token = readCookie("access_token") || readCookie("fc_session") || readCookie("sessionid") || getAuthToken();
  if (token) {
    protocols.push(`token.${token}`);
  }

  const ws = new WebSocket(wsUrl, protocols);

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
    safeReject(
      new Error(
        "WebSocket connection timed out — no CONNECTED message received",
      ),
    );
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
            : `WebSocket closed unexpectedly (code ${event.code})`,
        ),
      );
    }
  };

  // Register an event listener for resolving connection state (Issue 11.2 fix)
  const bootstrapListener = (event: MessageEvent) => {
    if (settled) return;
    try {
      const msg = JSON.parse(event.data as string);
      if (msg.type === "CONNECTED" || msg.type === "AGENT_UPDATE") {
        clearTimeout(connectTimeout);
        safeResolve();
        ws.removeEventListener("message", bootstrapListener);
      }
    } catch {
      clearTimeout(connectTimeout);
      safeResolve();
      ws.removeEventListener("message", bootstrapListener);
    }
  };
  ws.addEventListener("message", bootstrapListener);

  return { ws, connected };
}

/**
 * Poll for report completion
 */
export async function pollForReport(
  sessionId: string,
  onProgress: (status: string) => void,
  intervalMs = 3000,
  maxAttempts = 60,
): Promise<ReportDTO> {
  return new Promise((resolve, reject) => {
    let timeoutId: ReturnType<typeof setTimeout>;
    let finished = false;
    let attempts = 0;

    const poll = async () => {
      if (finished) return;
      attempts++;
      if (attempts > maxAttempts) {
        finished = true;
        reject(new Error("Polling timeout — investigation took too long"));
        return;
      }

      try {
        const result = await getReport(sessionId);
        if (result.status === "complete" && result.report) {
          finished = true;
          resolve(result.report);
        } else {
          onProgress("in_progress");
          const nextDelay = Math.min(
            intervalMs * Math.pow(1.5, attempts),
            15000,
          );
          const jitter = nextDelay * 0.2 * (Math.random() - 0.5);
          timeoutId = setTimeout(poll, nextDelay + jitter);
        }
      } catch (error) {
        finished = true;
        reject(error);
      }
    };

    timeoutId = setTimeout(poll, intervalMs);
    poll();
  });
}
