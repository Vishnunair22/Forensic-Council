/**
 * Forensic Council API Client
 * ==========================
 *
 * Client module for communicating with the FastAPI backend.
 */

// Use Next.js public runtime config for environment variables
const API_BASE = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";
const WS_BASE = API_BASE.replace(/^http/, "ws");

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
  type: "AGENT_UPDATE" | "HITL_CHECKPOINT" | "AGENT_COMPLETE" | "PIPELINE_COMPLETE" | "ERROR";
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

/**
 * Get the stored JWT token
 */
export function getAuthToken(): string | null {
  if (typeof window === "undefined") return null;
  return localStorage.getItem(TOKEN_KEY);
}

/**
 * Store the JWT token
 */
export function setAuthToken(token: string): void {
  if (typeof window === "undefined") return;
  localStorage.setItem(TOKEN_KEY, token);
}

/**
 * Clear the stored JWT token
 */
export function clearAuthToken(): void {
  if (typeof window === "undefined") return;
  localStorage.removeItem(TOKEN_KEY);
}

/**
 * Check if user is authenticated
 */
export function isAuthenticated(): boolean {
  return !!getAuthToken();
}

/**
 * Login with username and password
 */
export async function login(username: string, password: string): Promise<TokenResponse> {
  const formData = new URLSearchParams();
  formData.append("username", username);
  formData.append("password", password);

  const response = await fetch(`${API_BASE}/api/v1/auth/login`, {
    method: "POST",
    headers: {
      "Content-Type": "application/x-www-form-urlencoded",
    },
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

/**
 * Auto-login as demo investigator
 * Used for demo/development when no explicit login is performed
 * NOTE: Credentials should be provided via environment variables in production
 */
export async function autoLoginAsInvestigator(): Promise<TokenResponse> {
  // Use credentials from environment variables or prompt (never hardcode)
  const demoUsername = process.env.NEXT_PUBLIC_DEMO_USERNAME || "investigator";
  const demoPassword = process.env.NEXT_PUBLIC_DEMO_PASSWORD;
  
  if (!demoPassword) {
    throw new Error("Demo credentials not configured. Set NEXT_PUBLIC_DEMO_PASSWORD environment variable.");
  }
  
  return await login(demoUsername, demoPassword);
}

/**
 * Ensure user is authenticated (auto-login if needed)
 */
export async function ensureAuthenticated(): Promise<string> {
  let token = getAuthToken();
  if (!token) {
    const authData = await autoLoginAsInvestigator();
    token = authData.access_token;
  }
  return token;
}

/**
 * Logout the current user
 */
export async function logout(): Promise<void> {
  const token = getAuthToken();
  if (token) {
    try {
      await fetch(`${API_BASE}/api/v1/auth/logout`, {
        method: "POST",
        headers: {
          "Authorization": `Bearer ${token}`,
        },
      });
    } catch (error) {
      // Ignore errors during logout
    }
  }
  clearAuthToken();
}

/**
 * Get current user info
 */
export async function getCurrentUser(): Promise<UserInfo> {
  const token = await ensureAuthenticated();
  const response = await fetch(`${API_BASE}/api/v1/auth/me`, {
    headers: {
      "Authorization": `Bearer ${token}`,
    },
  });

  if (!response.ok) {
    const error = await response.json().catch(() => ({ detail: "Failed to get user info" }));
    throw new Error(error.detail || "Failed to get user info");
  }

  return response.json();
}

/**
 * Maximum number of retry attempts for authentication failures
 */
const MAX_AUTH_RETRIES = 1;

/**
 * Track retry attempts to prevent infinite loops
 */
let authRetryCount = 0;

/**
 * Reset retry count - should be called after successful requests
 */
function resetAuthRetry(): void {
  authRetryCount = 0;
}

/**
 * Handle authentication errors by clearing token and retrying
 */
async function handleAuthError<T>(
  operation: () => Promise<T>,
  errorMessage: string
): Promise<T> {
  try {
    const result = await operation();
    resetAuthRetry();
    return result;
  } catch (error) {
    // Check if it's an authentication error
    if (error instanceof Error && 
        (error.message.includes("Invalid or expired token") || 
         error.message.includes("401") ||
         error.message.includes("Unauthorized"))) {
      
      if (authRetryCount < MAX_AUTH_RETRIES) {
        authRetryCount++;
        console.warn("Token invalid or expired, clearing and re-authenticating...");
        clearAuthToken();
        
        // Retry the operation with fresh authentication
        try {
          const result = await operation();
          resetAuthRetry();
          return result;
        } catch (retryError) {
          throw retryError;
        }
      }
    }
    throw error;
  }
}

/**
 * Get default headers with authentication
 */
async function getAuthHeaders(): Promise<HeadersInit> {
  const token = await ensureAuthenticated();
  return {
    "Authorization": `Bearer ${token}`,
  };
}

/**
 * API Functions
 */

/**
 * Start a forensic investigation
 */
export async function startInvestigation(
  file: File,
  caseId: string,
  investigatorId: string
): Promise<InvestigationResponse> {
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
      const error = await response.json().catch(() => ({ detail: "Unknown error" }));
      throw new Error(error.detail || `HTTP ${response.status}`);
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

    if (response.status === 404) {
      throw new Error("Session not found");
    }

    if (response.status === 202) {
      return { status: "in_progress" };
    }

    if (!response.ok) {
      const error = await response.json().catch(() => ({ detail: "Unknown error" }));
      throw new Error(error.detail || `HTTP ${response.status}`);
    }

    const report: ReportDTO = await response.json();
    return { status: "complete", report };
  }, "Failed to get report");
}

/**
 * Get the brief for an agent in a session
 */
export async function getBrief(sessionId: string, agentId: string): Promise<string> {
  return handleAuthError(async () => {
    const headers = await getAuthHeaders();
    const response = await fetch(`${API_BASE}/api/v1/sessions/${sessionId}/brief/${agentId}`, {
      headers,
    });

    if (response.status === 404) {
      return "No brief available.";
    }

    if (!response.ok) {
      const error = await response.json().catch(() => ({ detail: "Unknown error" }));
      throw new Error(error.detail || `HTTP ${response.status}`);
    }

    const data = await response.json();
    return data.brief || "No brief available.";
  }, "Failed to get brief");
}

/**
 * Get pending HITL checkpoints for a session
 */
export async function getCheckpoints(sessionId: string): Promise<HITLCheckpoint[]> {
  return handleAuthError(async () => {
    const headers = await getAuthHeaders();
    const response = await fetch(`${API_BASE}/api/v1/sessions/${sessionId}/checkpoints`, {
      headers,
    });

    if (response.status === 404) {
      return [];
    }

    if (!response.ok) {
      const error = await response.json().catch(() => ({ detail: "Unknown error" }));
      throw new Error(error.detail || `HTTP ${response.status}`);
    }

    return response.json();
  }, "Failed to get checkpoints");
}

/**
 * Submit a HITL decision
 */
export async function submitHITLDecision(decision: HITLDecisionRequest): Promise<void> {
  return handleAuthError(async () => {
    const headers = await getAuthHeaders();
    const response = await fetch(`${API_BASE}/api/v1/hitl/decision`, {
      method: "POST",
      headers: {
        ...headers,
        "Content-Type": "application/json",
      },
      body: JSON.stringify(decision),
    });

    if (!response.ok) {
      const error = await response.json().catch(() => ({ detail: "Unknown error" }));
      throw new Error(error.detail || `HTTP ${response.status}`);
    }
  }, "Failed to submit decision");
}

/**
 * Create a WebSocket connection for live updates
 * Token is sent after connection via subprotocol to avoid logging in URL
 * Returns both the WebSocket and a Promise that resolves when connected
 */
export function createLiveSocket(
  sessionId: string
): { ws: WebSocket; connected: Promise<void> } {
  const wsUrl = `${WS_BASE}/api/v1/sessions/${sessionId}/live`;
  // Use subprotocol for authentication to avoid token in URL (which gets logged)
  const ws = new WebSocket(wsUrl, ["forensic-v1"]);

  let settle: (() => void) | null = null;
  let connected = new Promise<void>((resolve) => {
    settle = resolve;
  });

  // Track if we've already settled the promise to prevent double-resolution
  let settled = false;
  const safeSettle = () => {
    if (!settle) return;
    if (!settled) {
      settled = true;
      settle();
    }
  };

  // Set all handlers atomically in one pass to avoid race conditions
  ws.onopen = () => {
    console.log("WebSocket connected");
    // Send authentication after connection established
    const token = getAuthToken();
    if (token) {
      ws.send(JSON.stringify({ type: "AUTH", token }));
    }
    // Resolve the promise - connection is ready
    safeSettle();
  };

  ws.onerror = (error) => {
    console.error("WebSocket error:", error);
    // Reject the promise - connection failed
    safeSettle();
  };

  ws.onclose = (event) => {
    console.log("WebSocket disconnected:", event.code, event.reason);
    // Note: onclose fires after onopen succeeds normally
    // For error handling, the caller should check ws.readyState or use the connected promise
    safeSettle();
  };

  // onmessage is set by the caller via the returned ws object

  return { ws, connected };
}

/**
 * Poll for report completion
 */
export async function pollForReport(
  sessionId: string,
  onProgress: (status: string) => void,
  intervalMs: number = 5000,
  maxAttempts: number = 60
): Promise<ReportDTO> {
  return new Promise((resolve, reject) => {
    let intervalId: NodeJS.Timeout;
    let hasFinished = false;
    let attempts = 0;

    const poll = async () => {
      if (hasFinished) return;

      attempts++;
      if (attempts > maxAttempts) {
        hasFinished = true;
        clearInterval(intervalId);
        reject(new Error("Polling timeout — investigation took too long"));
        return;
      }

      try {
        const result = await getReport(sessionId);

        if (result.status === "complete" && result.report) {
          hasFinished = true;
          clearInterval(intervalId);
          resolve(result.report);
        } else {
          onProgress("in_progress");
        }
      } catch (error) {
        hasFinished = true;
        clearInterval(intervalId);
        reject(error);
      }
    };

    // Start polling
    intervalId = setInterval(poll, intervalMs);

    // Initial poll
    poll();
  });
}
