/**
 * Forensic Council API Client
 * ==========================
 * 
 * Client module for communicating with the FastAPI backend.
 */

// Use Next.js public runtime config for environment variables
const API_BASE = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";
const WS_BASE = API_BASE.replace(/^http/, "ws");

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
  const formData = new FormData();
  formData.append("file", file);
  formData.append("case_id", caseId);
  formData.append("investigator_id", investigatorId);

  const response = await fetch(`${API_BASE}/api/v1/investigate`, {
    method: "POST",
    body: formData,
  });

  if (!response.ok) {
    const error = await response.json().catch(() => ({ detail: "Unknown error" }));
    throw new Error(error.detail || `HTTP ${response.status}`);
  }

  return response.json();
}

/**
 * Get the report for a session
 */
export async function getReport(sessionId: string): Promise<ReportResponse> {
  const response = await fetch(`${API_BASE}/api/v1/sessions/${sessionId}/report`);

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
}

/**
 * Get the brief for an agent in a session
 */
export async function getBrief(sessionId: string, agentId: string): Promise<string> {
  const response = await fetch(`${API_BASE}/api/v1/sessions/${sessionId}/brief/${agentId}`);

  if (response.status === 404) {
    return "No brief available.";
  }

  if (!response.ok) {
    const error = await response.json().catch(() => ({ detail: "Unknown error" }));
    throw new Error(error.detail || `HTTP ${response.status}`);
  }

  const data = await response.json();
  return data.brief || "No brief available.";
}

/**
 * Get pending HITL checkpoints for a session
 */
export async function getCheckpoints(sessionId: string): Promise<HITLCheckpoint[]> {
  const response = await fetch(`${API_BASE}/api/v1/sessions/${sessionId}/checkpoints`);

  if (response.status === 404) {
    return [];
  }

  if (!response.ok) {
    const error = await response.json().catch(() => ({ detail: "Unknown error" }));
    throw new Error(error.detail || `HTTP ${response.status}`);
  }

  return response.json();
}

/**
 * Submit a HITL decision
 */
export async function submitHITLDecision(decision: HITLDecisionRequest): Promise<void> {
  const response = await fetch(`${API_BASE}/api/v1/hitl/decision`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
    },
    body: JSON.stringify(decision),
  });

  if (!response.ok) {
    const error = await response.json().catch(() => ({ detail: "Unknown error" }));
    throw new Error(error.detail || `HTTP ${response.status}`);
  }
}

/**
 * Create a WebSocket connection for live updates
 */
export function createLiveSocket(
  sessionId: string,
  onMessage: (update: BriefUpdate) => void,
  onClose: () => void
): WebSocket {
  const wsUrl = `${WS_BASE}/api/v1/sessions/${sessionId}/live`;
  const ws = new WebSocket(wsUrl);

  ws.onopen = () => {
    console.log("WebSocket connected");
  };

  ws.onmessage = (event) => {
    try {
      const update: BriefUpdate = JSON.parse(event.data);
      onMessage(update);
    } catch (error) {
      console.error("Failed to parse WebSocket message:", error);
    }
  };

  ws.onclose = () => {
    console.log("WebSocket disconnected");
    onClose();
  };

  ws.onerror = (error) => {
    console.error("WebSocket error:", error);
  };

  return ws;
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
