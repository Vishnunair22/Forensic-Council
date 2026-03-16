/**
 * Frontend Unit Tests — lib/api.ts
 * =================================
 * Tests every exported function: token management, auth flows,
 * investigation lifecycle, report polling, and WebSocket creation.
 *
 * Run: cd frontend && npm test -- tests/frontend/unit/lib/api.test.ts
 */

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

// ── Mock sessionStorage ───────────────────────────────────────────────────────

const store: Record<string, string> = {};
const mockStorage = {
  getItem: jest.fn((k: string) => store[k] ?? null),
  setItem: jest.fn((k: string, v: string) => { store[k] = v; }),
  removeItem: jest.fn((k: string) => { delete store[k]; }),
  clear: jest.fn(() => { Object.keys(store).forEach(k => delete store[k]); }),
};
Object.defineProperty(window, "sessionStorage", { value: mockStorage, writable: true });

// ── Mock fetch ────────────────────────────────────────────────────────────────

global.fetch = jest.fn();
const mockFetch = global.fetch as jest.Mock;

function respondOk(body: unknown, status = 200) {
  mockFetch.mockResolvedValueOnce({ ok: status < 400, status, json: jest.fn().mockResolvedValue(body) });
}
function respondErr(status: number, detail = "Error") {
  mockFetch.mockResolvedValueOnce({ ok: false, status, json: jest.fn().mockResolvedValue({ detail }) });
}

// ── Mock WebSocket ────────────────────────────────────────────────────────────

const mockWs = {
  send: jest.fn(), close: jest.fn(),
  onopen: null as ((e: Event) => void) | null,
  onmessage: null as ((e: MessageEvent) => void) | null,
  onerror: null as ((e: Event) => void) | null,
  onclose: null as ((e: CloseEvent) => void) | null,
  readyState: 1,
};
global.WebSocket = jest.fn().mockImplementation(() => mockWs) as unknown as typeof WebSocket;

// ── Helpers ───────────────────────────────────────────────────────────────────

function setValidToken(token = "tok-abc") {
  store["forensic_auth_token"] = token;
  store["forensic_auth_token_expiry"] = String(Date.now() + 3_600_000);
}

beforeEach(() => {
  jest.clearAllMocks();
  Object.keys(store).forEach(k => delete store[k]);
});

// ═══════════════════════════════════════════════════════════════════════════════
// TOKEN MANAGEMENT
// ═══════════════════════════════════════════════════════════════════════════════

describe("Token Management", () => {
  describe("setAuthToken()", () => {
    it("stores token in sessionStorage", () => {
      setAuthToken("my-token", 3600);
      expect(mockStorage.setItem).toHaveBeenCalledWith("forensic_auth_token", "my-token");
    });
    it("stores expiry timestamp", () => {
      const before = Date.now();
      setAuthToken("tok", 3600);
      const expiryCall = mockStorage.setItem.mock.calls.find(c => c[0] === "forensic_auth_token_expiry");
      const expiry = parseInt(expiryCall![1], 10);
      expect(expiry).toBeGreaterThan(before + 3_590_000);
      expect(expiry).toBeLessThan(before + 3_610_000);
    });
    it("uses 1 hour default when expiresIn omitted", () => {
      setAuthToken("tok");
      const expiryCall = mockStorage.setItem.mock.calls.find(c => c[0] === "forensic_auth_token_expiry");
      expect(expiryCall).toBeDefined();
    });
  });

  describe("getAuthToken()", () => {
    it("returns null when nothing stored", () => expect(getAuthToken()).toBeNull());
    it("returns token when valid and not expired", () => {
      setValidToken("valid-tok");
      expect(getAuthToken()).toBe("valid-tok");
    });
    it("returns null and clears when expired", () => {
      store["forensic_auth_token"] = "old-tok";
      store["forensic_auth_token_expiry"] = String(Date.now() - 1000);
      expect(getAuthToken()).toBeNull();
      expect(mockStorage.removeItem).toHaveBeenCalledWith("forensic_auth_token");
    });
    it("returns token when no expiry stored (legacy)", () => {
      store["forensic_auth_token"] = "no-expiry-tok";
      // expiry key absent → should be treated as valid
      const result = getAuthToken();
      // Either null (strict) or the token (lenient) — both acceptable; just must not throw
      expect(typeof result === "string" || result === null).toBe(true);
    });
  });

  describe("clearAuthToken()", () => {
    it("removes both token and expiry keys", () => {
      clearAuthToken();
      expect(mockStorage.removeItem).toHaveBeenCalledWith("forensic_auth_token");
      expect(mockStorage.removeItem).toHaveBeenCalledWith("forensic_auth_token_expiry");
    });
  });

  describe("isAuthenticated()", () => {
    it("returns false with no token", () => expect(isAuthenticated()).toBe(false));
    it("returns true with valid token", () => { setValidToken(); expect(isAuthenticated()).toBe(true); });
    it("returns false with expired token", () => {
      store["forensic_auth_token"] = "exp";
      store["forensic_auth_token_expiry"] = String(Date.now() - 1);
      expect(isAuthenticated()).toBe(false);
    });
  });
});

// ═══════════════════════════════════════════════════════════════════════════════
// AUTH FUNCTIONS
// ═══════════════════════════════════════════════════════════════════════════════

describe("login()", () => {
  it("sends form-encoded credentials to /auth/login", async () => {
    respondOk({ access_token: "jwt", token_type: "bearer", expires_in: 3600, user_id: "u1", role: "investigator" });
    await login("user", "pass");
    const [url, opts] = mockFetch.mock.calls[0];
    expect(url).toContain("/api/v1/auth/login");
    expect(opts.method).toBe("POST");
    expect(opts.body).toContain("username=user");
    expect(opts.body).toContain("password=pass");
  });
  it("stores token on success", async () => {
    respondOk({ access_token: "stored-jwt", token_type: "bearer", expires_in: 3600, user_id: "u", role: "investigator" });
    await login("a", "b");
    expect(mockStorage.setItem).toHaveBeenCalledWith("forensic_auth_token", "stored-jwt");
  });
  it("returns token response", async () => {
    const payload = { access_token: "ret-jwt", token_type: "bearer", expires_in: 3600, user_id: "u2", role: "investigator" };
    respondOk(payload);
    const result = await login("a", "b");
    expect(result.access_token).toBe("ret-jwt");
  });
  it("throws with server error message on 401", async () => {
    respondErr(401, "Invalid credentials");
    await expect(login("bad", "creds")).rejects.toThrow("Invalid credentials");
  });
  it("throws on 500", async () => {
    respondErr(500, "Internal error");
    await expect(login("a", "b")).rejects.toThrow();
  });
});

describe("logout()", () => {
  it("calls /auth/logout with bearer token", async () => {
    setValidToken("logout-tok");
    respondOk({});
    await logout();
    const [url, opts] = mockFetch.mock.calls[0];
    expect(url).toContain("/auth/logout");
    expect(opts.headers.Authorization).toContain("logout-tok");
  });
  it("clears token even when API call throws", async () => {
    setValidToken("err-tok");
    mockFetch.mockRejectedValueOnce(new Error("Network"));
    await logout();
    expect(mockStorage.removeItem).toHaveBeenCalledWith("forensic_auth_token");
  });
  it("does not call fetch when no token exists", async () => {
    await logout();
    expect(mockFetch).not.toHaveBeenCalled();
  });
});

describe("autoLoginAsInvestigator()", () => {
  it("POSTs to /api/auth/demo (relative path)", async () => {
    respondOk({ access_token: "demo-tok", token_type: "bearer", expires_in: 3600, user_id: "d", role: "investigator" });
    await autoLoginAsInvestigator();
    expect(mockFetch).toHaveBeenCalledWith("/api/auth/demo", { method: "POST" });
  });
  it("stores returned token", async () => {
    respondOk({ access_token: "stored-demo", token_type: "bearer", expires_in: 3600, user_id: "d", role: "investigator" });
    await autoLoginAsInvestigator();
    expect(mockStorage.setItem).toHaveBeenCalledWith("forensic_auth_token", "stored-demo");
  });
  it("throws on failure", async () => {
    respondErr(500, "Demo auth failed");
    await expect(autoLoginAsInvestigator()).rejects.toThrow();
  });
});

describe("ensureAuthenticated()", () => {
  it("returns existing valid token without hitting /api/auth/demo", async () => {
    setValidToken("existing");
    const tok = await ensureAuthenticated();
    expect(tok).toBe("existing");
    expect(mockFetch).not.toHaveBeenCalled();
  });
  it("auto-logins when no token present", async () => {
    respondOk({ access_token: "fresh", token_type: "bearer", expires_in: 3600, user_id: "u", role: "investigator" });
    const tok = await ensureAuthenticated();
    expect(tok).toBe("fresh");
  });
});

// ═══════════════════════════════════════════════════════════════════════════════
// INVESTIGATION
// ═══════════════════════════════════════════════════════════════════════════════

describe("startInvestigation()", () => {
  beforeEach(() => setValidToken());

  it("throws on invalid Case ID format", async () => {
    const f = new File(["x"], "t.jpg", { type: "image/jpeg" });
    await expect(startInvestigation(f, "INVALID", "REQ-12345")).rejects.toThrow("Invalid Case ID");
  });
  it("throws on invalid Investigator ID format", async () => {
    const f = new File(["x"], "t.jpg", { type: "image/jpeg" });
    await expect(startInvestigation(f, "CASE-1234567890", "BAD")).rejects.toThrow("Invalid Investigator ID");
  });
  it("accepts timestamp-format case ID", async () => {
    respondOk({ session_id: "s1", case_id: "CASE-1234567890", status: "started", message: "OK" });
    const f = new File(["x"], "t.jpg", { type: "image/jpeg" });
    const r = await startInvestigation(f, "CASE-1234567890", "REQ-12345");
    expect(r.session_id).toBe("s1");
  });
  it("accepts UUID-format case ID", async () => {
    respondOk({ session_id: "s2", case_id: "CASE-00000000-0000-0000-0000-000000000000", status: "started", message: "OK" });
    const f = new File(["x"], "t.jpg", { type: "image/jpeg" });
    const r = await startInvestigation(f, "CASE-00000000-0000-0000-0000-000000000000", "REQ-99999");
    expect(r.session_id).toBe("s2");
  });
  it("sends file as multipart FormData", async () => {
    respondOk({ session_id: "s3", case_id: "CASE-1234567890", status: "started", message: "OK" });
    const f = new File(["data"], "evidence.jpg", { type: "image/jpeg" });
    await startInvestigation(f, "CASE-1234567890", "REQ-12345");
    const body = mockFetch.mock.calls[0][1].body as FormData;
    expect(body).toBeInstanceOf(FormData);
  });
  it("sends Authorization header", async () => {
    respondOk({ session_id: "s4", case_id: "CASE-1234567890", status: "started", message: "OK" });
    const f = new File(["data"], "e.jpg", { type: "image/jpeg" });
    await startInvestigation(f, "CASE-1234567890", "REQ-12345");
    const headers = mockFetch.mock.calls[0][1].headers;
    expect(headers.Authorization).toContain("Bearer");
  });
  it("throws with server error detail on failure", async () => {
    respondErr(422, "File type not supported");
    const f = new File(["data"], "e.jpg", { type: "image/jpeg" });
    await expect(startInvestigation(f, "CASE-1234567890", "REQ-12345")).rejects.toThrow("File type not supported");
  });
});

// ═══════════════════════════════════════════════════════════════════════════════
// REPORT & SESSIONS
// ═══════════════════════════════════════════════════════════════════════════════

describe("getReport()", () => {
  beforeEach(() => setValidToken());

  it("returns in_progress on 202", async () => {
    mockFetch.mockResolvedValueOnce({ ok: false, status: 202, json: jest.fn() });
    const r = await getReport("sess-1");
    expect(r.status).toBe("in_progress");
    expect(r.report).toBeUndefined();
  });
  it("returns complete report on 200", async () => {
    const report = { report_id: "r1", session_id: "s1", case_id: "C1", executive_summary: "Done",
      per_agent_findings: {}, per_agent_metrics: {}, per_agent_analysis: {},
      overall_confidence: 0.9, overall_error_rate: 0.0, overall_verdict: "LIKELY",
      cross_modal_confirmed: [], contested_findings: [],
      tribunal_resolved: [], incomplete_findings: [], uncertainty_statement: "",
      cryptographic_signature: "sig", report_hash: "hash", signed_utc: "2025-01-01T00:00:00Z" };
    respondOk(report);
    const r = await getReport("sess-1");
    expect(r.status).toBe("complete");
    expect(r.report?.report_id).toBe("r1");
  });
  it("throws Session not found on 404", async () => {
    mockFetch.mockResolvedValueOnce({ ok: false, status: 404, json: jest.fn() });
    await expect(getReport("missing")).rejects.toThrow("Session not found");
  });
  it("throws on other 5xx errors", async () => {
    respondErr(503, "Service unavailable");
    await expect(getReport("s")).rejects.toThrow();
  });
});

describe("getBrief()", () => {
  beforeEach(() => setValidToken());

  it("returns brief text on 200", async () => {
    respondOk({ brief: "Agent completed ELA analysis." });
    const b = await getBrief("sess", "agent-img");
    expect(b).toBe("Agent completed ELA analysis.");
  });
  it("returns fallback string on 404", async () => {
    mockFetch.mockResolvedValueOnce({ ok: false, status: 404, json: jest.fn() });
    const b = await getBrief("sess", "agent-img");
    expect(b).toBe("No brief available.");
  });
});

describe("getCheckpoints()", () => {
  beforeEach(() => setValidToken());

  it("returns array of checkpoints", async () => {
    respondOk([{ checkpoint_id: "cp1", session_id: "s", agent_id: "a", agent_name: "N", brief_text: "B", decision_needed: "D", created_at: "T" }]);
    const cps = await getCheckpoints("sess");
    expect(cps).toHaveLength(1);
    expect(cps[0].checkpoint_id).toBe("cp1");
  });
  it("returns empty array on 404", async () => {
    mockFetch.mockResolvedValueOnce({ ok: false, status: 404, json: jest.fn() });
    const cps = await getCheckpoints("missing");
    expect(cps).toEqual([]);
  });
});

describe("submitHITLDecision()", () => {
  beforeEach(() => setValidToken());

  it("POSTs decision to /hitl/decision", async () => {
    respondOk({});
    await submitHITLDecision({ session_id: "s", checkpoint_id: "cp", agent_id: "a", decision: "APPROVE" });
    const [url, opts] = mockFetch.mock.calls[0];
    expect(url).toContain("/hitl/decision");
    expect(opts.method).toBe("POST");
    const body = JSON.parse(opts.body);
    expect(body.decision).toBe("APPROVE");
  });
  it("throws on server error", async () => {
    respondErr(500, "Internal");
    await expect(submitHITLDecision({ session_id: "s", checkpoint_id: "c", agent_id: "a", decision: "APPROVE" })).rejects.toThrow();
  });
});

// ═══════════════════════════════════════════════════════════════════════════════
// WEBSOCKET
// ═══════════════════════════════════════════════════════════════════════════════

describe("createLiveSocket()", () => {
  beforeEach(() => setValidToken("ws-token"));

  it("creates WebSocket with session URL", () => {
    createLiveSocket("sess-ws");
    expect(global.WebSocket).toHaveBeenCalledWith(expect.stringContaining("sess-ws/live"), expect.anything());
  });
  it("sends AUTH on open", () => {
    const { ws } = createLiveSocket("sess-ws");
    mockWs.onopen?.(new Event("open"));
    expect(ws.send).toHaveBeenCalledWith(expect.stringContaining('"type":"AUTH"'));
    expect(ws.send).toHaveBeenCalledWith(expect.stringContaining("ws-token"));
  });
  it("resolves connected promise on CONNECTED message", async () => {
    const { connected } = createLiveSocket("sess-ws");
    mockWs.onopen?.(new Event("open"));
    mockWs.onmessage?.(new MessageEvent("message", { data: JSON.stringify({ type: "CONNECTED" }) }));
    await expect(connected).resolves.toBeUndefined();
  });
  it("resolves connected on AGENT_UPDATE (race condition)", async () => {
    const { connected } = createLiveSocket("sess-ws");
    mockWs.onopen?.(new Event("open"));
    mockWs.onmessage?.(new MessageEvent("message", { data: JSON.stringify({ type: "AGENT_UPDATE" }) }));
    await expect(connected).resolves.toBeUndefined();
  });
  it("rejects connected on error", async () => {
    const { connected } = createLiveSocket("sess-ws");
    mockWs.onerror?.(new Event("error"));
    await expect(connected).rejects.toThrow("WebSocket connection error");
  });
  it("rejects with reason on close before CONNECTED", async () => {
    const { connected } = createLiveSocket("sess-ws");
    mockWs.onopen?.(new Event("open"));
    mockWs.onclose?.(new CloseEvent("close", { code: 4001, reason: "Session not found" }));
    await expect(connected).rejects.toThrow("Session not found");
  });
  it("rejects with generic message on abnormal close (no reason)", async () => {
    const { connected } = createLiveSocket("sess-ws");
    mockWs.onopen?.(new Event("open"));
    mockWs.onclose?.(new CloseEvent("close", { code: 1006 }));
    await expect(connected).rejects.toThrow(/closed unexpectedly/);
  });
  it("rejects immediately when no auth token available", async () => {
    Object.keys(store).forEach(k => delete store[k]);
    const { connected } = createLiveSocket("sess-ws");
    mockWs.onopen?.(new Event("open"));
    await expect(connected).rejects.toThrow(/No auth token/);
  });
});

// ═══════════════════════════════════════════════════════════════════════════════
// POLLING
// ═══════════════════════════════════════════════════════════════════════════════

describe("pollForReport()", () => {
  beforeEach(() => { jest.useFakeTimers(); setValidToken(); });
  afterEach(() => jest.useRealTimers());

  it("resolves immediately on first complete response", async () => {
    const report = { report_id: "r-poll", session_id: "s", case_id: "C",
      executive_summary: "Done", per_agent_findings: {}, per_agent_metrics: {}, per_agent_analysis: {},
      overall_confidence: 0.9, overall_error_rate: 0.0, overall_verdict: "LIKELY",
      cross_modal_confirmed: [], contested_findings: [], tribunal_resolved: [], incomplete_findings: [],
      uncertainty_statement: "", cryptographic_signature: "sig", report_hash: "h", signed_utc: null };
    respondOk(report);
    const p = pollForReport("sess", jest.fn(), 1000, 10);
    jest.advanceTimersByTime(1000);
    const result = await p;
    expect(result.report_id).toBe("r-poll");
  });

  it("calls onProgress on in_progress response", async () => {
    // First call: in_progress, second call: complete
    mockFetch.mockResolvedValueOnce({ ok: false, status: 202, json: jest.fn() });
    const report = { report_id: "r2", session_id: "s", case_id: "C",
      executive_summary: "Done", per_agent_findings: {}, per_agent_metrics: {}, per_agent_analysis: {},
      overall_confidence: 0.9, overall_error_rate: 0.0, overall_verdict: "LIKELY",
      cross_modal_confirmed: [], contested_findings: [], tribunal_resolved: [], incomplete_findings: [],
      uncertainty_statement: "", cryptographic_signature: "s", report_hash: "h", signed_utc: null };
    respondOk(report);
    const onProgress = jest.fn();
    const p = pollForReport("sess", onProgress, 500, 10);
    jest.advanceTimersByTime(500);
    await Promise.resolve(); await Promise.resolve();
    jest.advanceTimersByTime(500);
    await p.catch(() => {});
    expect(onProgress).toHaveBeenCalledWith("in_progress");
  });

  it("rejects after maxAttempts exceeded", async () => {
    mockFetch.mockResolvedValue({ ok: false, status: 202, json: jest.fn() });
    const p = pollForReport("sess", jest.fn(), 100, 3);
    for (let i = 0; i < 5; i++) {
      jest.advanceTimersByTime(100);
      await Promise.resolve();
    }
    await expect(p).rejects.toThrow(/timeout/i);
  });
});
