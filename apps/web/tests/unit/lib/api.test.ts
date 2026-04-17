import {
  getAuthToken,
  setAuthToken,
  clearAuthToken,
  isAuthenticated,
  login,
  logout,
  autoLoginAsInvestigator,
  ensureAuthenticated,
  startInvestigation,
  getReport,
  getBrief,
  getCheckpoints,
  submitHITLDecision,
  createLiveSocket,
  pollForReport,
} from "@/lib/api";

const store: Record<string, string> = {};
const mockStorage = {
  getItem: jest.fn((k: string) => store[k] ?? null),
  setItem: jest.fn((k: string, v: string) => {
    store[k] = v;
  }),
  removeItem: jest.fn((k: string) => {
    delete store[k];
  }),
  clear: jest.fn(() => {
    Object.keys(store).forEach((k) => delete store[k]);
  }),
};

Object.defineProperty(window, "sessionStorage", {
  value: mockStorage,
  writable: true,
});

Object.defineProperty(document, "cookie", {
  value: "",
  writable: true,
});

const mockResponses: Response[] = [];
global.fetch = jest.fn((url) => {
  // Always handle health check silently
  if (typeof url === 'string' && url.includes('/api/v1/health')) {
    return Promise.resolve({
      ok: true,
      status: 200,
      json: async () => ({}),
      headers: new Headers({ 'set-cookie': 'csrf_token=test-token' }),
    } as Response);
  }

  const response = mockResponses.shift();
  if (response) return Promise.resolve(response);
  
  // Fallback for unexpected calls to avoid "reading 'ok' of undefined"
  console.warn(`[Test] Unexpected fetch call to ${url}`);
  return Promise.resolve({
    ok: true,
    status: 200,
    json: async () => ({}),
    headers: new Headers(),
  } as Response);
});
const mockFetch = global.fetch as jest.Mock;

function respondJson(body: unknown, status = 200) {
  mockResponses.push({
    ok: status >= 200 && status < 300,
    status,
    json: jest.fn().mockResolvedValue(body),
    text: jest.fn().mockResolvedValue(JSON.stringify(body)),
    headers: { get: jest.fn(() => null) } as unknown as Headers,
  } as unknown as Response);
}

let socketInstance: {
  send: jest.Mock;
  close: jest.Mock;
  onopen: ((e: Event) => void) | null;
  onmessage: ((e: MessageEvent) => void) | null;
  onerror: ((e: Event) => void) | null;
  onclose: ((e: CloseEvent) => void) | null;
  _simulate?: (type: string, data: unknown) => void;
};

global.WebSocket = jest.fn().mockImplementation(() => {
  const listeners: Record<string, Array<(e: any) => void>> = {};
  socketInstance = {
    send: jest.fn(),
    close: jest.fn(),
    onopen: null,
    onmessage: null,
    onerror: null,
    onclose: null,
    addEventListener: jest.fn((type, listener) => {
      if (!listeners[type]) listeners[type] = [];
      listeners[type].push(listener);
    }),
    removeEventListener: jest.fn((type, listener) => {
      if (!listeners[type]) return;
      listeners[type] = listeners[type].filter(l => l !== listener);
    }),
    // Helper to simulate events in tests
    _simulate: (type: string, event: any) => {
      if (type === "message") socketInstance.onmessage?.(event);
      if (type === "open") socketInstance.onopen?.(event);
      if (type === "error") socketInstance.onerror?.(event);
      if (type === "close") socketInstance.onclose?.(event);
      listeners[type]?.forEach(l => l(event));
    }
  } as any;
  return socketInstance;
}) as unknown as typeof WebSocket;

beforeEach(() => {
  jest.clearAllMocks();
  Object.keys(store).forEach((k) => delete store[k]);
  document.cookie = "";
});

describe("token helpers", () => {
  it("stores and retrieves a token", () => {
    setAuthToken("tok", 3600);
    expect(getAuthToken()).toBe("tok");
    expect(mockStorage.setItem).toHaveBeenCalledWith(
      "forensic_auth_token",
      "tok",
    );
  });

  it("does not store an expiry when expiresIn is omitted", () => {
    setAuthToken("tok");
    const expiryCall = mockStorage.setItem.mock.calls.find(
      ([key]) => key === "forensic_auth_token_expiry",
    );
    expect(expiryCall).toBeUndefined();
  });

  it("clears expired tokens", () => {
    store.forensic_auth_token = "expired";
    store.forensic_auth_token_expiry = String(Date.now() - 1000);
    expect(getAuthToken()).toBeNull();
    expect(mockStorage.removeItem).toHaveBeenCalledWith("forensic_auth_token");
  });

  it("clears both storage keys", () => {
    clearAuthToken();
    expect(mockStorage.removeItem).toHaveBeenCalledWith("forensic_auth_token");
    expect(mockStorage.removeItem).toHaveBeenCalledWith(
      "forensic_auth_token_expiry",
    );
  });

  it("treats stored token as authenticated", () => {
    setAuthToken("tok", 3600);
    expect(isAuthenticated()).toBe(true);
  });
});

describe("auth API", () => {
  it("login submits form-encoded credentials and returns payload", async () => {
    respondJson({
      access_token: "jwt",
      token_type: "bearer",
      expires_in: 3600,
      user_id: "u1",
      role: "investigator",
    });

    const result = await login("user", "pass");
    const loginCall = mockFetch.mock.calls.find(c => c[0].includes("/api/v1/auth/login"));
    expect(loginCall).toBeTruthy();
    const [url, opts] = loginCall;

    expect(url).toContain("/api/v1/auth/login");
    expect(opts.method).toBe("POST");
    expect(opts.credentials).toBe("include");
    expect(opts.body).toContain("username=user");
    expect(result.access_token).toBe("jwt");
  });

  it("autoLoginAsInvestigator posts to the demo route", async () => {
    respondJson({
      access_token: "demo",
      token_type: "bearer",
      expires_in: 3600,
      user_id: "u1",
      role: "investigator",
    });

    const result = await autoLoginAsInvestigator();
    expect(mockFetch).toHaveBeenCalledWith("/api/auth/demo", expect.objectContaining({ method: "POST" }));
    expect(result.access_token).toBe("demo");
  });

  it("logout posts with cookie credentials", async () => {
    respondJson({});

    await logout();

    const logoutCall = mockFetch.mock.calls.find(c => c[0].includes("/api/v1/auth/logout"));
    expect(logoutCall).toBeTruthy();
    const [url, opts] = logoutCall;
    expect(url).toContain("/api/v1/auth/logout");
    expect(opts).toMatchObject({
      method: "POST",
      credentials: "include",
    });
  });

  it("ensureAuthenticated returns after a healthy /me check", async () => {
    respondJson({ user_id: "u1" });

    await expect(ensureAuthenticated()).resolves.toBeUndefined();
    expect(mockFetch).toHaveBeenCalledWith(
      expect.stringContaining("/api/v1/auth/me"),
      expect.objectContaining({ credentials: "include" }),
    );
  });

  it("ensureAuthenticated falls back to demo login when /me is unauthorized", async () => {
    respondJson({ detail: "Unauthorized" }, 401);
    respondJson({
      access_token: "demo",
      token_type: "bearer",
      expires_in: 3600,
      user_id: "u1",
      role: "investigator",
    });

    await ensureAuthenticated();

    expect(mockFetch.mock.calls[1][0]).toBe("/api/auth/demo");
  });
});

describe("investigation API", () => {
  it("starts an investigation with multipart upload", async () => {
    respondJson({
      session_id: "sess-1",
      case_id: "CASE-1234567890",
      status: "started",
      message: "OK",
    });

    const file = new File(["data"], "evidence.jpg", { type: "image/jpeg" });
    const result = await startInvestigation(
      file,
      "CASE-1234567890",
      "REQ-12345",
    );
    const investigationCall = mockFetch.mock.calls.find(c => c[0].includes("/api/v1/investigate"));
    expect(investigationCall).toBeTruthy();
    const [url, opts] = investigationCall;
    expect(url).toContain("/api/v1/investigate");
    expect(opts.method).toBe("POST");
    expect(opts.body).toBeInstanceOf(FormData);
    expect(result.session_id).toBe("sess-1");
  });

  it("gets report in progress on 202", async () => {
    respondJson({}, 202);
    await expect(getReport("sess")).resolves.toEqual({ status: "in_progress" });
  });

  it("gets a completed report on 200", async () => {
    respondJson({
      report_id: "r1",
      session_id: "sess",
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
      signed_utc: null,
    });

    const result = await getReport("sess");
    expect(result.status).toBe("complete");
    expect(result.report?.report_id).toBe("r1");
  });

  it("gets agent brief text", async () => {
    respondJson({ brief: "Agent finished analysis." });
    await expect(getBrief("sess", "Agent1")).resolves.toBe(
      "Agent finished analysis.",
    );
  });

  it("gets checkpoints", async () => {
    respondJson([
      {
        checkpoint_id: "cp1",
        session_id: "sess",
        agent_id: "Agent1",
        agent_name: "Image Analyst",
        brief_text: "Review needed",
        decision_needed: "APPROVE",
        created_at: "2025-01-01T00:00:00Z",
      },
    ]);

    const result = await getCheckpoints("sess");
    expect(result).toHaveLength(1);
  });

  it("submits a HITL decision", async () => {
    respondJson({});

    await submitHITLDecision({
      session_id: "sess",
      checkpoint_id: "cp",
      agent_id: "Agent1",
      decision: "APPROVE",
    });

    const decisionCall = mockFetch.mock.calls.find(c => c[0].includes("/api/v1/hitl/decision"));
    expect(decisionCall).toBeTruthy();
    const [url, opts] = decisionCall;
    expect(url).toContain("/api/v1/hitl/decision");
    expect(opts.method).toBe("POST");
  });
});

describe("live socket", () => {
  it("creates a session-scoped websocket URL", () => {
    createLiveSocket("sess-live");
    expect(global.WebSocket).toHaveBeenCalledWith(
      expect.stringContaining("sess-live/live"),
      ["forensic-v1"],
    );
  });

  it("does not send an AUTH message on open", () => {
    const { ws } = createLiveSocket("sess-live");
    socketInstance.onopen?.(new Event("open"));
    expect(ws.send).not.toHaveBeenCalled();
  });

  it("resolves connected on CONNECTED", async () => {
    const { connected } = createLiveSocket("sess-live");
    socketInstance._simulate!("message",
      new MessageEvent("message", {
        data: JSON.stringify({ type: "CONNECTED" }),
      }),
    );
    await expect(connected).resolves.toBeUndefined();
  });

  it("resolves connected on first AGENT_UPDATE", async () => {
    const { connected } = createLiveSocket("sess-live");
    socketInstance._simulate!("message",
      new MessageEvent("message", {
        data: JSON.stringify({ type: "AGENT_UPDATE" }),
      }),
    );
    await expect(connected).resolves.toBeUndefined();
  });

  it("rejects on websocket error", async () => {
    const { connected } = createLiveSocket("sess-live");
    socketInstance._simulate!("error", new Event("error"));
    await expect(connected).rejects.toThrow("WebSocket connection error");
  });
});

describe("pollForReport", () => {
  beforeEach(() => {
    jest.useFakeTimers();
  });

  afterEach(() => {
    jest.useRealTimers();
  });

  it("resolves after an in-progress poll turns complete", async () => {
    respondJson({}, 202);
    respondJson({
      report_id: "r-poll",
      session_id: "sess",
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
      signed_utc: null,
    });

    const onProgress = jest.fn();
    const promise = pollForReport("sess", onProgress, 100, 3);

    await Promise.resolve();
    jest.advanceTimersByTime(100);
    await Promise.resolve();

    const result = await promise;
    expect(onProgress).toHaveBeenCalledWith("in_progress");
    expect(result.report_id).toBe("r-poll");
  });
});
