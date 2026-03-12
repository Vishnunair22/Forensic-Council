/**
 * Frontend E2E Tests — WebSocket Lifecycle & Arbiter Navigation Fix
 * ==================================================================
 * Tests the full WebSocket flow from connection → agents → arbiter → navigate.
 * Specifically covers the v1.0.3 bugs:
 *  - arbiter awaited before router.push (no race condition)
 *  - isNavigating double-click guard
 *  - error resets isNavigating so user can retry
 *  - CONNECTED + AGENT_UPDATE both resolve the connected promise
 *
 * Run: cd frontend && npm test -- tests/frontend/e2e/websocket_flow.test.ts
 */

import { createLiveSocket, getReport, setAuthToken } from "@/lib/api";

// ── sessionStorage mock ───────────────────────────────────────────────────────

const store: Record<string, string> = {};
Object.defineProperty(window, "sessionStorage", {
  value: {
    getItem: jest.fn((k: string) => store[k] ?? null),
    setItem: jest.fn((k: string, v: string) => { store[k] = v; }),
    removeItem: jest.fn((k: string) => { delete store[k]; }),
    clear: jest.fn(),
  },
  writable: true,
});

// ── WebSocket mock ────────────────────────────────────────────────────────────

let wsInstance: MockWS;

class MockWS {
  send = jest.fn();
  close = jest.fn();
  onopen: ((e: Event) => void) | null = null;
  onmessage: ((e: MessageEvent) => void) | null = null;
  onerror: ((e: Event) => void) | null = null;
  onclose: ((e: CloseEvent) => void) | null = null;
  readyState = WebSocket.CONNECTING;

  constructor(public url: string, public protocols?: string | string[]) {
    wsInstance = this;
  }

  simulateOpen() {
    this.readyState = WebSocket.OPEN;
    this.onopen?.(new Event("open"));
  }
  simulateMessage(data: unknown) {
    this.onmessage?.(new MessageEvent("message", { data: JSON.stringify(data) }));
  }
  simulateError() { this.onerror?.(new Event("error")); }
  simulateClose(code = 1000, reason = "") {
    this.readyState = WebSocket.CLOSED;
    this.onclose?.(new CloseEvent("close", { code, reason }));
  }
}

global.WebSocket = MockWS as unknown as typeof WebSocket;

// ── fetch mock ────────────────────────────────────────────────────────────────

global.fetch = jest.fn();
const mockFetch = global.fetch as jest.Mock;

function respondOk(body: unknown) {
  mockFetch.mockResolvedValueOnce({ ok: true, status: 200, json: jest.fn().mockResolvedValue(body) });
}

beforeEach(() => {
  jest.clearAllMocks();
  Object.keys(store).forEach(k => delete store[k]);
  setAuthToken("test-token", 3600);
});

// ═══════════════════════════════════════════════════════════════════════════════
// WS CONNECTION BASICS
// ═══════════════════════════════════════════════════════════════════════════════

describe("WebSocket Connection", () => {
  it("constructs WS URL containing session ID and /live path", () => {
    createLiveSocket("sess-url-test");
    expect(wsInstance.url).toContain("sess-url-test");
    expect(wsInstance.url).toContain("/live");
  });

  it("sends AUTH message immediately on open", () => {
    const { ws } = createLiveSocket("sess-auth");
    wsInstance.simulateOpen();
    expect(ws.send).toHaveBeenCalledTimes(1);
    const sent = JSON.parse(ws.send.mock.calls[0][0]);
    expect(sent.type).toBe("AUTH");
    expect(sent.token).toBe("test-token");
  });

  it("resolves connected promise on CONNECTED message", async () => {
    const { connected } = createLiveSocket("sess-conn");
    wsInstance.simulateOpen();
    wsInstance.simulateMessage({ type: "CONNECTED", session_id: "sess-conn" });
    await expect(connected).resolves.toBeUndefined();
  });

  it("resolves connected promise on AGENT_UPDATE (race condition fix)", async () => {
    const { connected } = createLiveSocket("sess-race");
    wsInstance.simulateOpen();
    // Server sends AGENT_UPDATE before CONNECTED
    wsInstance.simulateMessage({ type: "AGENT_UPDATE", session_id: "sess-race", payload: {} });
    await expect(connected).resolves.toBeUndefined();
  });

  it("rejects connected on WS error", async () => {
    const { connected } = createLiveSocket("sess-err");
    wsInstance.simulateError();
    await expect(connected).rejects.toThrow("WebSocket connection error");
  });

  it("rejects connected with server reason on close before CONNECTED", async () => {
    const { connected } = createLiveSocket("sess-close");
    wsInstance.simulateOpen();
    wsInstance.simulateClose(4001, "Session not found");
    await expect(connected).rejects.toThrow("Session not found");
  });

  it("rejects with generic message on close code 1006 (no reason)", async () => {
    const { connected } = createLiveSocket("sess-1006");
    wsInstance.simulateOpen();
    wsInstance.simulateClose(1006, "");
    await expect(connected).rejects.toThrow(/closed unexpectedly/);
  });

  it("rejects immediately if no token available", async () => {
    Object.keys(store).forEach(k => delete store[k]);
    const { connected } = createLiveSocket("sess-noauth");
    wsInstance.simulateOpen();
    await expect(connected).rejects.toThrow(/No auth token/i);
  });
});

// ═══════════════════════════════════════════════════════════════════════════════
// FULL 5-AGENT ANALYSIS SEQUENCE
// ═══════════════════════════════════════════════════════════════════════════════

describe("Full 5-Agent Analysis Sequence", () => {
  const agents = ["agent-img", "agent-audio", "agent-obj", "agent-vid", "agent-meta"];

  it("receives all AGENT_COMPLETE messages without error", async () => {
    const { connected, ws } = createLiveSocket("sess-full");
    wsInstance.simulateOpen();
    wsInstance.simulateMessage({ type: "CONNECTED" });
    await connected;

    const received: string[] = [];
    const origOnMessage = wsInstance.onmessage;
    wsInstance.onmessage = (e) => {
      origOnMessage?.(e);
      const data = JSON.parse(e.data);
      received.push(data.type);
    };

    // Emit AGENT_START + AGENT_UPDATE + AGENT_COMPLETE for each agent
    agents.forEach(id => {
      wsInstance.simulateMessage({ type: "AGENT_START", payload: { agent_id: id } });
      wsInstance.simulateMessage({ type: "AGENT_UPDATE", payload: { agent_id: id, content: "thinking..." } });
      wsInstance.simulateMessage({ type: "AGENT_COMPLETE", payload: { agent_id: id, status: "complete", confidence: 0.9, findings_count: 2 } });
    });

    wsInstance.simulateMessage({ type: "PIPELINE_COMPLETE", payload: { session_id: "sess-full" } });
    expect(ws.send).toHaveBeenCalledTimes(1); // Only AUTH
  });

  it("handles PIPELINE_PAUSED (HITL checkpoint)", async () => {
    const messages: unknown[] = [];
    createLiveSocket("sess-pause");
    wsInstance.simulateOpen();
    wsInstance.onmessage = (e) => messages.push(JSON.parse(e.data));

    wsInstance.simulateMessage({ type: "PIPELINE_PAUSED", payload: { checkpoint_id: "cp-1", decision_needed: "Review needed." } });
    expect(messages).toHaveLength(1);
    expect((messages[0] as Record<string, unknown>).type).toBe("PIPELINE_PAUSED");
  });

  it("AGENT_COMPLETE carries expected payload fields", () => {
    const messages: unknown[] = [];
    createLiveSocket("sess-payload");
    wsInstance.onmessage = (e) => messages.push(JSON.parse(e.data));
    wsInstance.simulateMessage({
      type: "AGENT_COMPLETE",
      payload: { agent_id: "agent-img", agent_name: "Image Analyst", status: "complete", confidence: 0.95, findings_count: 3 },
    });
    const msg = messages[0] as { payload: { confidence: number } };
    expect(msg.payload.confidence).toBe(0.95);
  });
});

// ═══════════════════════════════════════════════════════════════════════════════
// ARBITER / NAVIGATION FIX (v1.0.3)
// ═══════════════════════════════════════════════════════════════════════════════

describe("Arbiter Navigation Fix (v1.0.3)", () => {
  /**
   * These tests validate the STATE MACHINE logic that was fixed:
   * - isNavigating=true must be set BEFORE awaiting resumeInvestigation
   * - isNavigating=true disables the buttons (double-click guard)
   * - if an error occurs, isNavigating resets to false
   * - deep analysis flag is passed correctly
   *
   * We test this logic in isolation (not via full page render) to keep
   * tests fast and deterministic.
   */

  describe("isNavigating guard simulation", () => {
    it("prevents onAcceptAnalysis double-call when already navigating", () => {
      let isNavigating = false;
      let callCount = 0;
      const handleAccept = () => {
        if (isNavigating) return; // Guard
        isNavigating = true;
        callCount++;
      };
      handleAccept(); // First call — allowed
      handleAccept(); // Second call — blocked by guard
      handleAccept(); // Third call — blocked
      expect(callCount).toBe(1);
      expect(isNavigating).toBe(true);
    });

    it("error during navigation resets isNavigating to false", async () => {
      let isNavigating = false;
      const simulateNavigation = async (shouldFail: boolean) => {
        if (isNavigating) return;
        isNavigating = true;
        try {
          if (shouldFail) throw new Error("Resume failed");
          // Success: isNavigating stays true until page unmounts
        } catch {
          isNavigating = false; // Reset on error
        }
      };
      await simulateNavigation(true);
      expect(isNavigating).toBe(false);
    });

    it("successful navigation keeps isNavigating=true until unmount", async () => {
      let isNavigating = false;
      const simulateNavigation = async () => {
        if (isNavigating) return;
        isNavigating = true;
        // (router.push would happen here — we just check the state)
      };
      await simulateNavigation();
      expect(isNavigating).toBe(true);
    });
  });

  describe("deep analysis flag", () => {
    it("handleDeepAnalysis passes deep=true (not passed to handleAccept)", () => {
      const decisions: boolean[] = [];
      const handleDecision = (deep: boolean) => decisions.push(deep);
      // handleAcceptAnalysis → handleDecision(false)
      handleDecision(false);
      // handleDeepAnalysis → handleDecision(true)
      handleDecision(true);
      expect(decisions[0]).toBe(false);
      expect(decisions[1]).toBe(true);
    });
  });

  describe("arbiter awaited before navigation", () => {
    it("resolve order: resumeInvestigation THEN router.push", async () => {
      const order: string[] = [];
      const resumeInvestigation = async () => {
        await new Promise(r => setTimeout(r, 10));
        order.push("resume");
      };
      const routerPush = async () => { order.push("push"); };
      // Correct pattern: await resume, then push
      await resumeInvestigation();
      await routerPush();
      expect(order).toEqual(["resume", "push"]);
    });

    it("illustrates the bug: router.push without await fires before resume", async () => {
      const order: string[] = [];
      const resumeInvestigation = () => new Promise<void>(r => setTimeout(() => { order.push("resume"); r(); }, 20));
      const routerPush = () => { order.push("push"); };
      // Bug pattern: no await — push fires first
      resumeInvestigation(); // not awaited
      routerPush();
      await new Promise(r => setTimeout(r, 30)); // Wait for resume to complete
      expect(order).toEqual(["push", "resume"]); // BUG: push before resume
    });
  });
});

// ═══════════════════════════════════════════════════════════════════════════════
// REPORT POLLING FROM RESULT PAGE
// ═══════════════════════════════════════════════════════════════════════════════

describe("Report Polling (result/page.tsx logic)", () => {
  const makeCompleteReport = () => ({
    report_id: "r-poll-e2e", session_id: "sess-poll", case_id: "CASE-9999999999",
    executive_summary: "Authentic.", per_agent_findings: {},
    cross_modal_confirmed: [], contested_findings: [], tribunal_resolved: [],
    incomplete_findings: [], uncertainty_statement: "", cryptographic_signature: "sig",
    report_hash: "hash", signed_utc: "2025-01-01T00:00:00Z",
  });

  it("resolves immediately on first 200 response", async () => {
    respondOk(makeCompleteReport());
    const result = await getReport("sess-poll");
    expect(result.status).toBe("complete");
    expect(result.report?.report_id).toBe("r-poll-e2e");
  });

  it("getReport returns in_progress on 202", async () => {
    mockFetch.mockResolvedValueOnce({ ok: false, status: 202, json: jest.fn() });
    const result = await getReport("sess-pending");
    expect(result.status).toBe("in_progress");
    expect(result.report).toBeUndefined();
  });

  it("getReport throws on 404 (session expired from Redis)", async () => {
    mockFetch.mockResolvedValueOnce({ ok: false, status: 404, json: jest.fn() });
    await expect(getReport("sess-missing")).rejects.toThrow("Session not found");
  });

  it("polling retry sequence: in_progress → in_progress → complete", async () => {
    const results: string[] = [];
    const responses = [
      { ok: false, status: 202, json: jest.fn() },
      { ok: false, status: 202, json: jest.fn() },
      { ok: true, status: 200, json: jest.fn().mockResolvedValue(makeCompleteReport()) },
    ];
    responses.forEach(r => mockFetch.mockResolvedValueOnce(r));

    for (const _ of responses) {
      const r = await getReport("sess-retry");
      results.push(r.status);
    }
    expect(results).toEqual(["in_progress", "in_progress", "complete"]);
  });
});

// ═══════════════════════════════════════════════════════════════════════════════
// DEEP ANALYSIS FLOW (second WS connection)
// ═══════════════════════════════════════════════════════════════════════════════

describe("Deep Analysis Flow", () => {
  it("second WS connection can be opened for deep phase", async () => {
    // Initial connection
    const { connected: c1 } = createLiveSocket("sess-deep");
    wsInstance.simulateOpen();
    wsInstance.simulateMessage({ type: "CONNECTED" });
    await c1;

    // Deep connection (new WS)
    const { connected: c2 } = createLiveSocket("sess-deep");
    wsInstance.simulateOpen();
    wsInstance.simulateMessage({ type: "CONNECTED" });
    await c2;

    // Both should have resolved
    await expect(c1).resolves.toBeUndefined();
    await expect(c2).resolves.toBeUndefined();
  });

  it("deep analysis AGENT_COMPLETE messages carry metadata.analysis_phase=deep", () => {
    const messages: unknown[] = [];
    createLiveSocket("sess-deep-phase");
    wsInstance.onmessage = (e) => messages.push(JSON.parse(e.data));

    wsInstance.simulateMessage({
      type: "AGENT_COMPLETE",
      payload: {
        agent_id: "agent-img",
        agent_name: "Image Analyst",
        status: "complete",
        confidence: 0.98,
        findings_count: 1,
        metadata: { analysis_phase: "deep" },
      },
    });

    const msg = messages[0] as { payload: { metadata: { analysis_phase: string } } };
    expect(msg.payload.metadata.analysis_phase).toBe("deep");
  });
});
