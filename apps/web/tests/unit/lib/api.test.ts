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

class MockWebSocket {
  static instances: MockWebSocket[] = [];

  url: string;
  protocols?: string | string[];
  readyState: number = WebSocket.CONNECTING;

  send = jest.fn();
  close = jest.fn(() => {
    this.readyState = WebSocket.CLOSED;
    this.onclose?.(new CloseEvent("close", { code: 1000 }));
    for (const listener of this.listeners["close"] || []) {
      listener(new CloseEvent("close", { code: 1000 }));
    }
  });

  onopen: ((event: Event) => void) | null = null;
  onclose: ((event: CloseEvent) => void) | null = null;
  onerror: ((event: Event) => void) | null = null;
  onmessage: ((event: MessageEvent) => void) | null = null;

  private listeners: Record<string, Array<(event: any) => void>> = {};

  constructor(url: string, protocols?: string | string[]) {
    this.url = url;
    this.protocols = protocols;
    MockWebSocket.instances.push(this);
  }

  addEventListener(type: string, listener: (event: any) => void) {
    this.listeners[type] ||= [];
    this.listeners[type].push(listener);
  }

  removeEventListener(type: string, listener: (event: any) => void) {
    this.listeners[type] = (this.listeners[type] || []).filter((l) => l !== listener);
  }

  _simulate(type: string, event: any) {
    if (type === "open") {
      this.readyState = WebSocket.OPEN;
      this.onopen?.(event);
    }

    if (type === "message") {
      this.onmessage?.(event as MessageEvent);
    }

    if (type === "error") {
      this.onerror?.(event);
    }

    if (type === "close") {
      this.readyState = WebSocket.CLOSED;
      this.onclose?.(event as CloseEvent);
    }

    for (const listener of this.listeners[type] || []) {
      listener(event);
    }
  }
}

global.WebSocket = MockWebSocket as any;
let socketInstance: MockWebSocket;

beforeEach(() => {
  jest.clearAllMocks();
  Object.keys(store).forEach((k) => delete store[k]);
  document.cookie = "csrf_token=test-token";
  // In the createLiveSocket tests, we need to capture the instance
  jest.spyOn(global, 'WebSocket').mockImplementation((url, protocols) => {
    socketInstance = new MockWebSocket(url as string, protocols as string | string[]);
    return socketInstance as any;
  });
});

afterEach(() => {
  for (const socket of MockWebSocket.instances) {
    socket.onopen = null;
    socket.onclose = null;
    socket.onerror = null;
    socket.onmessage = null;
    (socket as any).listeners = {};
  }
  MockWebSocket.instances = [];
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
      overall_verdict: "LIKELY_AUTHENTIC",
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
    const { connected } = createLiveSocket("sess-live");
    connected.catch(() => {});
    expect(global.WebSocket).toHaveBeenCalledWith(
      expect.stringContaining("sess-live/live"),
      ["forensic-v1"],
    );
  });

  it("does not send an AUTH message on open", () => {
    const { ws, connected } = createLiveSocket("sess-live");
    connected.catch(() => {});
    socketInstance.onopen?.(new Event("open"));
    expect(ws.send).not.toHaveBeenCalled();
  });

  it("resolves connected on CONNECTED", async () => {
    const { connected } = createLiveSocket("sess-live");
    socketInstance!._simulate("message",
      new MessageEvent("message", {
        data: JSON.stringify({ type: "CONNECTED" }),
      }),
    );
    await expect(connected).resolves.toBeUndefined();
  });

  it("resolves connected on first AGENT_UPDATE", async () => {
    const { connected } = createLiveSocket("sess-live");
    socketInstance!._simulate("message",
      new MessageEvent("message", {
        data: JSON.stringify({ type: "AGENT_UPDATE" }),
      }),
    );
    await expect(connected).resolves.toBeUndefined();
  });

  it("rejects on websocket error", async () => {
    const { connected } = createLiveSocket("sess-live");
    socketInstance!._simulate("error", new Event("error"));
    await expect(connected).rejects.toThrow("WebSocket connection error");
  });
});

describe("getReport schema fallback", () => {
  it("getReport falls back gracefully on schema mismatch without crashing", async () => {
    respondJson({ status: "complete", report: { foo: "bar" } });

    let consoleErrorCalled = false;
    const origError = console.error;
    console.error = jest.fn(() => { consoleErrorCalled = true; });
    try {
      const result = await getReport("sess");
      expect(result.status).toBe("complete");
      expect(result.report).toEqual({ foo: "bar" });
      expect(consoleErrorCalled).toBe(true);
    } finally {
      console.error = origError;
    }
  });

  it("getReport returns valid parsed report on success", async () => {
    respondJson({
      status: "complete",
      report: {
        session_id: "11111111-1111-4111-8111-111111111111",
        report_id: "22222222-2222-4222-8222-222222222222",
        case_id: "CASE-1",
        overall_verdict: "LIKELY_MANIPULATED",
        overall_confidence: 0.9,
      },
    });

    const result = await getReport("sess");
    expect(result.status).toBe("complete");
    expect(result.report?.report_id).toBe("22222222-2222-4222-8222-222222222222");
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
      report_id: "11111111-1111-4111-8111-111111111111",
      session_id: "22222222-2222-4222-8222-222222222222",
      case_id: "CASE-1",
      executive_summary: "Done",
      per_agent_findings: {},
      per_agent_metrics: {},
      per_agent_analysis: {},
      overall_confidence: 0.9,
      overall_error_rate: 0,
      overall_verdict: "LIKELY_AUTHENTIC",
      cross_modal_confirmed: [],
      contested_findings: [],
      tribunal_resolved: [],
      incomplete_findings: [],
      uncertainty_statement: "",
      cryptographic_signature: "sig",
      report_hash: "hash",
      signed_utc: "2026-04-30T00:00:00Z",
    });

    const onProgress = jest.fn();
    const promise = pollForReport("sess", onProgress, 100, 3);

    await jest.advanceTimersByTimeAsync(100);

    const result = await promise;
    expect(onProgress).toHaveBeenCalledWith("in_progress");
    expect(result.report_id).toBe("11111111-1111-4111-8111-111111111111");
  });
});

describe("DuplicateInvestigationError handling", () => {
  const { DuplicateInvestigationError } = require("@/lib/api/client");

  it("throws DuplicateInvestigationError for string detail with session ID", async () => {
    respondJson({ detail: "Duplicate detected: session 550e8400-e29b-41d4-a716-446655440000" }, 409);

    const file = new File(["data"], "evidence.jpg", { type: "image/jpeg" });
    await expect(startInvestigation(file, "CASE-1234567890", "REQ-12345")).rejects.toThrow(
      DuplicateInvestigationError
    );
  });

  it("throws DuplicateInvestigationError for object with existing_session_id", async () => {
    respondJson({ detail: { existing_session_id: "550e8400-e29b-41d4-a716-446655440000" } }, 409);

    const file = new File(["data"], "evidence.jpg", { type: "image/jpeg" });
    await expect(startInvestigation(file, "CASE-1234567890", "REQ-12345")).rejects.toThrow(
      DuplicateInvestigationError
    );
  });

  it("throws DuplicateInvestigationError for structured detail with code", async () => {
    respondJson(
      {
        detail: {
          code: "duplicate_investigation",
          existing_session_id: "550e8400-e29b-41d4-a716-446655440000",
          message: "Duplicate investigation already exists",
        },
      },
      409
    );

    const file = new File(["data"], "evidence.jpg", { type: "image/jpeg" });
    const error = await startInvestigation(file, "CASE-1234567890", "REQ-12345").catch((e) => e);
    expect(error).toBeInstanceOf(DuplicateInvestigationError);
    expect(error.existingSessionId).toBe("550e8400-e29b-41d4-a716-446655440000");
  });

  it("throws normal Error for 409 without session id", async () => {
    respondJson({ detail: "Conflict" }, 409);

    const file = new File(["data"], "evidence.jpg", { type: "image/jpeg" });
    await expect(startInvestigation(file, "CASE-1234567890", "REQ-12345")).rejects.toThrow("Conflict");
  });
});
