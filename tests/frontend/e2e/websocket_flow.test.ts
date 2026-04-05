import { createLiveSocket, getReport } from "@/lib/api";

let wsInstance: MockWS;

class MockWS {
  send = jest.fn();
  close = jest.fn();
  onopen: ((e: Event) => void) | null = null;
  onmessage: ((e: MessageEvent) => void) | null = null;
  onerror: ((e: Event) => void) | null = null;
  onclose: ((e: CloseEvent) => void) | null = null;

  constructor(
    public url: string,
    public protocols?: string | string[],
  ) {
    wsInstance = this;
  }

  simulateOpen() {
    this.onopen?.(new Event("open"));
  }

  simulateMessage(data: unknown) {
    this.onmessage?.(
      new MessageEvent("message", { data: JSON.stringify(data) }),
    );
  }

  simulateError() {
    this.onerror?.(new Event("error"));
  }

  simulateClose(code = 1000, reason = "") {
    this.onclose?.(new CloseEvent("close", { code, reason }));
  }
}

global.WebSocket = MockWS as unknown as typeof WebSocket;
global.fetch = jest.fn();
const mockFetch = global.fetch as jest.Mock;

function respondJson(body: unknown, status = 200) {
  mockFetch.mockResolvedValueOnce({
    ok: status >= 200 && status < 300,
    status,
    json: jest.fn().mockResolvedValue(body),
    text: jest.fn().mockResolvedValue(JSON.stringify(body)),
    headers: {
      get: jest.fn(() => null),
    },
  });
}

beforeEach(() => {
  jest.clearAllMocks();
});

describe("WebSocket lifecycle", () => {
  it("resolves when the backend confirms connection", async () => {
    const { connected } = createLiveSocket("sess-conn");
    wsInstance.simulateOpen();
    wsInstance.simulateMessage({ type: "CONNECTED", session_id: "sess-conn" });
    await expect(connected).resolves.toBeUndefined();
  });

  it("also resolves when the first live agent update arrives before CONNECTED", async () => {
    const { connected } = createLiveSocket("sess-race");
    wsInstance.simulateOpen();
    wsInstance.simulateMessage({
      type: "AGENT_UPDATE",
      session_id: "sess-race",
      data: { agent_id: "Agent1" },
    });
    await expect(connected).resolves.toBeUndefined();
  });

  it("rejects when the websocket errors before it is established", async () => {
    const { connected } = createLiveSocket("sess-err");
    wsInstance.simulateError();
    await expect(connected).rejects.toThrow("WebSocket connection error");
  });

  it("rejects with server close reason before the handshake completes", async () => {
    const { connected } = createLiveSocket("sess-close");
    wsInstance.simulateOpen();
    wsInstance.simulateClose(4001, "Session not found");
    await expect(connected).rejects.toThrow("Session not found");
  });
});

describe("report polling contract", () => {
  it("returns in-progress while the report is still compiling", async () => {
    respondJson({}, 202);
    await expect(getReport("sess-pending")).resolves.toEqual({
      status: "in_progress",
    });
  });

  it("returns a finished report payload when compilation completes", async () => {
    respondJson({
      report_id: "r1",
      session_id: "sess-ready",
      case_id: "CASE-1",
      executive_summary: "Done",
      per_agent_findings: {},
      per_agent_metrics: {},
      per_agent_analysis: {},
      overall_confidence: 0.9,
      overall_error_rate: 0,
      overall_verdict: "LIKELY",
      cross_modal_confirmed: [],
      contested_findings: [],
      tribunal_resolved: [],
      incomplete_findings: [],
      uncertainty_statement: "",
      cryptographic_signature: "sig",
      report_hash: "hash",
      signed_utc: "2025-01-01T00:00:00Z",
    });

    const result = await getReport("sess-ready");
    expect(result.status).toBe("complete");
    expect(result.report?.report_id).toBe("r1");
  });
});
