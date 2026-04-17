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
  UserInfo,
} from "./types";

/**
 * Partial Validation Parser
 * Uses Zod but falls back to raw data on minor validation errors
 * to prevent complete UI failure during rapid schema evolution.
 */
function _parseReportDTO(raw: unknown): ReportDTO {
  const result = ReportDTOSchema.safeParse(raw);
  if (result.success) return result.data as ReportDTO;

  dbg.error("[api] Report validation failed. Falling back to passthrough.", result.error);
  // Log strictly but allow the UI to try and render whatever matches the interface.
  return raw as ReportDTO;
}

export class ProtocolWarmingError extends Error {
  constructor(message = "Protocol warming up — system dependencies initializing") {
    super(message);
    this.name = "ProtocolWarmingError";
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
          signal: AbortSignal.timeout(15_000),
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

async function handleAuthError<T>(operation: () => Promise<T>): Promise<T> {
  try {
    return await operation();
  } catch (error) {
    const msg = error instanceof Error ? error.message : String(error);
    if (msg.includes("401") || msg.includes("Unauthorized") || msg.includes("authenticated")) {
      dbg.warn("Session invalid, re-authenticating...");
      await autoLoginAsInvestigator();
      return await operation();
    }
    throw error;
  }
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
      throw new Error(err.detail || `HTTP ${response.status}`);
    }
    return response.json();
  });
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

/** Legacy support and misc endpoints... (abbreviated for brevity) */
export async function logout(): Promise<void> {
    const headers = await getMutationHeaders();
    await fetch(`${API_BASE}/api/v1/auth/logout`, { method: "POST", headers, credentials: "include" });
    clearAuthToken();
}
